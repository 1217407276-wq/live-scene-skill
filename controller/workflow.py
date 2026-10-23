"""Persistent workflow state and image-asset binding for Live Scene Skill.

This module controls workflow state. It deliberately does not implement image
generation; a provider must implement the explicit file-based adapter below.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sqlite3
import zlib
import uuid
from datetime import datetime, timezone
from pathlib import Path


class WorkflowError(RuntimeError):
    pass


class ImageProvider:
    """Integration contract. Refinement MUST receive the selected source file."""

    def generate_three(self, project: dict, round_number: int, destination: Path) -> list[Path]:
        raise NotImplementedError

    def edit_three(
        self,
        source_image: Path,
        project: dict,
        round_number: int,
        changes: dict,
        destination: Path,
    ) -> list[Path]:
        raise NotImplementedError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise WorkflowError("provider outputs must be PNG files")
    offset, width, height, idat, saw_end = 8, None, None, bytearray(), False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            raise WorkflowError("provider returned a truncated PNG chunk")
        payload = data[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length:end])[0]
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != expected_crc:
            raise WorkflowError("provider returned a PNG with an invalid chunk checksum")
        if kind == b"IHDR":
            if length != 13 or width is not None:
                raise WorkflowError("provider returned a malformed PNG header")
            width, height = struct.unpack(">II", payload[:8])
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            saw_end = True
            if length != 0 or end != len(data):
                raise WorkflowError("provider returned a malformed PNG end chunk")
            break
        offset = end
    if width is None or height is None or not idat or not saw_end:
        raise WorkflowError("provider outputs must be complete PNG files with IHDR, IDAT, and IEND")
    try:
        zlib.decompress(idat)
    except zlib.error as exc:
        raise WorkflowError("provider returned a PNG with invalid compressed image data") from exc
    return width, height


class Workflow:
    def __init__(self, db_path: str | Path, asset_root: str | Path, provider: ImageProvider):
        self.db_path = Path(db_path)
        self.asset_root = Path(asset_root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.asset_root.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    round_number INTEGER NOT NULL, phase TEXT NOT NULL,
                    brief_json TEXT NOT NULL, confirmed_direction TEXT,
                    locked_asset_id TEXT, last_changes_json TEXT NOT NULL,
                    last_error TEXT
                );
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, round_number INTEGER NOT NULL,
                    variant TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
                    source_asset_id TEXT, created_at TEXT NOT NULL,
                    UNIQUE(project_id, round_number, variant),
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );
            """)

    def _db(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def create_project(self, brief: dict) -> dict:
        project_id = "LS-" + uuid.uuid4().hex[:12].upper()
        now = utc_now()
        with self._db() as db:
            db.execute("INSERT INTO projects VALUES (?, ?, ?, 0, 'planning', ?, NULL, NULL, '{}', NULL)",
                       (project_id, now, now, json.dumps(brief, ensure_ascii=False)))
        (self.asset_root / project_id).mkdir(parents=True, exist_ok=True)
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> dict:
        with self._db() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
            if not row:
                raise WorkflowError("unknown project")
            result = dict(row)
            result["brief"] = json.loads(result.pop("brief_json"))
            result["last_changes"] = json.loads(result.pop("last_changes_json"))
            result["assets"] = [dict(a) for a in db.execute(
                "SELECT * FROM assets WHERE project_id=? ORDER BY round_number, variant", (project_id,)
            )]
            return result

    def confirm_direction(self, project_id: str, direction: str) -> dict:
        if not direction.strip():
            raise WorkflowError("confirmed direction cannot be empty")
        p = self.get_project(project_id)
        if p["phase"] not in ("planning", "feedback"):
            raise WorkflowError("direction can only be confirmed during planning or feedback")
        with self._db() as db:
            db.execute("UPDATE projects SET confirmed_direction=?, phase='confirmed', last_error=NULL, updated_at=? WHERE id=?",
                       (direction.strip(), utc_now(), project_id))
        return self.get_project(project_id)

    def lock_asset(self, project_id: str, asset_id: str, changes: dict | None = None) -> dict:
        p = self.get_project(project_id)
        if p["phase"] != "feedback":
            raise WorkflowError("an image can only be locked from the feedback phase")
        asset = next((a for a in p["assets"] if a["id"] == asset_id), None)
        if asset is None:
            raise WorkflowError("asset does not belong to this project")
        path = Path(asset["path"])
        if not path.is_file() or sha256_file(path) != asset["sha256"]:
            self._set_error(project_id, "Selected image is missing or its checksum changed; restore the exact source asset.")
            raise WorkflowError("selected source image is missing or changed")
        with self._db() as db:
            db.execute("UPDATE projects SET locked_asset_id=?, phase='locked', last_changes_json=?, last_error=NULL, updated_at=? WHERE id=?",
                       (asset_id, json.dumps(changes or {}, ensure_ascii=False), utc_now(), project_id))
        return self.get_project(project_id)

    def generate(self, project_id: str) -> dict:
        p = self.get_project(project_id)
        if p["phase"] != "confirmed" or not p["confirmed_direction"]:
            raise WorkflowError("confirm a design direction before generating")
        return self._run_variants(p, changes=None)

    def refine(self, project_id: str, changes: dict) -> dict:
        p = self.get_project(project_id)
        if p["phase"] != "locked" or not p["locked_asset_id"]:
            raise WorkflowError("select and lock a source image before refinement")
        source = next((a for a in p["assets"] if a["id"] == p["locked_asset_id"]), None)
        if source is None:
            raise WorkflowError("locked source asset is not in this project")
        source_path = Path(source["path"])
        if not source_path.is_file() or sha256_file(source_path) != source["sha256"]:
            self._set_error(project_id, "Locked source image is missing or changed; no edit was sent to the provider.")
            raise WorkflowError("locked source image is missing or changed")
        if not changes.get("allow"):
            raise WorkflowError("explicit allow-list is required for every refinement")
        if not changes.get("preserve") or not changes.get("forbid"):
            raise WorkflowError("preserve and forbid lists are required for every refinement")
        return self._run_variants(p, changes=changes, source_path=source_path)

    def _run_variants(self, project: dict, changes: dict | None, source_path: Path | None = None) -> dict:
        project_id = project["id"]
        round_number = project["round_number"] + 1
        dest = self.asset_root / project_id / f"round-{round_number:03d}"
        dest.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("UPDATE projects SET phase='generating', round_number=?, last_changes_json=?, last_error=NULL, updated_at=? WHERE id=?",
                       (round_number, json.dumps(changes or {}, ensure_ascii=False), utc_now(), project_id))
        try:
            outputs = (self.provider.generate_three(project, round_number, dest) if source_path is None
                       else self.provider.edit_three(source_path, project, round_number, changes or {}, dest))
            outputs = [Path(p) for p in outputs]
            if len(outputs) != 3:
                raise WorkflowError(f"provider returned {len(outputs)} images; exactly 3 independent images are required")
            if len({str(p.resolve()) for p in outputs}) != 3:
                raise WorkflowError("provider outputs must be three distinct files, not a collage or duplicate path")
            if any(not p.is_file() or p.stat().st_size == 0 for p in outputs):
                raise WorkflowError("provider returned a missing or empty image file")
            dims = [png_dimensions(p) for p in outputs]
            if any(w <= 0 or h <= 0 or w * 4 != h * 3 for w, h in dims):
                raise WorkflowError("each provider output must be a 3:4 PNG image")
            if len({sha256_file(p) for p in outputs}) != 3:
                raise WorkflowError("provider outputs must be three different image files")
            with self._db() as db:
                for variant, path in zip(("A", "B", "C"), outputs):
                    asset_id = f"{project_id}-R{round_number:03d}-{variant}-{uuid.uuid4().hex[:8]}"
                    db.execute("INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                        asset_id, project_id, round_number, variant, str(path.resolve()), sha256_file(path),
                        project["locked_asset_id"] if source_path else None, utc_now()))
                db.execute("UPDATE projects SET phase='feedback', locked_asset_id=NULL, last_error=NULL, updated_at=? WHERE id=?",
                           (utc_now(), project_id))
        except Exception as exc:
            # Keep round number and confirmed state so the same round can be retried.
            fallback = "locked" if source_path else "confirmed"
            with self._db() as db:
                db.execute("UPDATE projects SET phase=?, round_number=?, last_error=?, updated_at=? WHERE id=?",
                           (fallback, round_number - 1, str(exc), utc_now(), project_id))
            raise
        return self.get_project(project_id)

    def recover(self, project_id: str) -> dict:
        p = self.get_project(project_id)
        missing = [a["id"] for a in p["assets"] if not Path(a["path"]).is_file()]
        if missing:
            self._set_error(project_id, "Missing asset files: " + ", ".join(missing))
            p = self.get_project(project_id)
            p["missing_assets"] = missing
        elif p["phase"] == "generating":
            with self._db() as db:
                db.execute("UPDATE projects SET phase='confirmed', round_number=MAX(0, round_number-1), last_error='Interrupted generation; retry is available.', updated_at=? WHERE id=?",
                           (utc_now(), project_id))
            p = self.get_project(project_id)
        return p

    def _set_error(self, project_id: str, message: str):
        with self._db() as db:
            db.execute("UPDATE projects SET last_error=?, updated_at=? WHERE id=?", (message, utc_now(), project_id))

    def asset(self, project_id: str, asset_id: str) -> dict:
        p = self.get_project(project_id)
        asset = next((a for a in p["assets"] if a["id"] == asset_id), None)
        if asset is None:
            raise WorkflowError("asset does not belong to this project")
        return asset


def project_summary(project: dict) -> dict:
    return {k: project[k] for k in ("id", "round_number", "phase", "confirmed_direction", "locked_asset_id", "last_error")}
