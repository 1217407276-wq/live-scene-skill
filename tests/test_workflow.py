import tempfile
import unittest
import struct
import zlib
import hashlib
from pathlib import Path

from controller.workflow import ImageProvider, Workflow, WorkflowError
from controller.server import render
from controller.brand_assets import inspect_brand_assets
from controller.safe_area import centered_live_crop


def png_chunk(name, payload):
    return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)


class FakeProvider(ImageProvider):
    def __init__(self):
        self.edit_calls = []
        self.fail = False

    def generate_three(self, project, round_number, destination):
        if self.fail:
            raise RuntimeError("injected generator failure")
        return self.write_three(destination, f"original-round-{round_number}".encode())

    def edit_three(self, source_image, project, round_number, changes, destination):
        source_bytes = source_image.read_bytes()
        self.edit_calls.append((source_image.resolve(), source_bytes, changes.copy()))
        if self.fail:
            raise RuntimeError("injected editor failure")
        return self.write_three(destination, source_bytes + f"|edit-round-{round_number}".encode())

    @staticmethod
    def write_three(destination, prefix):
        paths = []
        for letter in "ABC":
            path = destination / f"{letter}.png"
            seed = hashlib.sha256(prefix + letter.encode()).digest()
            ihdr = struct.pack(">II", 3, 4) + b"\x08\x02\x00\x00\x00"
            raw = b"".join(b"\0" + bytes(seed[(row * 9 + i) % len(seed)] for i in range(9)) for row in range(4))
            image = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", zlib.compress(raw)) + png_chunk(b"IEND", b""))
            path.write_bytes(image)
            paths.append(path)
        return paths


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.provider = FakeProvider()
        self.wf = Workflow(root / "state.sqlite3", root / "assets", self.provider)
        self.project = self.wf.create_project({"brand": "Purcotton", "ratio": "3:4"})
        self.pid = self.project["id"]

    def tearDown(self):
        self.temp.cleanup()

    def new_round(self):
        self.wf.confirm_direction(self.pid, "奶油白卧室，布局固定")
        p = self.wf.generate(self.pid)
        self.assertEqual(p["phase"], "feedback")
        self.assertEqual(len([a for a in p["assets"] if a["round_number"] == p["round_number"]]), 3)
        self.assertEqual({a["variant"] for a in p["assets"] if a["round_number"] == p["round_number"]}, set("ABC"))
        return p

    def test_direction_gate_and_exactly_three_distinct_assets(self):
        with self.assertRaisesRegex(WorkflowError, "confirm"):
            self.wf.generate(self.pid)
        p = self.new_round()
        round_assets = [a for a in p["assets"] if a["round_number"] == 1]
        self.assertEqual(len({a["id"] for a in round_assets}), 3)
        self.assertEqual(len({a["sha256"] for a in round_assets}), 3)

    def test_multiround_lock_edit_uses_exact_selected_source_and_persists(self):
        p1 = self.new_round()
        chosen = next(a for a in p1["assets"] if a["variant"] == "B" and a["round_number"] == 1)
        before = Path(chosen["path"]).read_bytes()
        changes = {"allow": ["棉花数量"], "preserve": ["沙发与窗户位置"], "forbid": ["重构布局"], "free_text": "棉花减少30%"}
        locked = self.wf.lock_asset(self.pid, chosen["id"], changes)
        self.assertIn("棉花减少30%", render(locked))
        self.assertIn("沙发与窗户位置", render(locked))
        p2 = self.wf.refine(self.pid, changes)
        self.assertEqual(self.provider.edit_calls[-1][0], Path(chosen["path"]).resolve())
        self.assertEqual(self.provider.edit_calls[-1][1], before)
        self.assertEqual(p2["phase"], "feedback")
        round2 = [a for a in p2["assets"] if a["round_number"] == 2]
        self.assertEqual(len(round2), 3)
        self.assertTrue(all(a["source_asset_id"] == chosen["id"] for a in round2))
        self.assertEqual(len({a["sha256"] for a in round2}), 3)
        # Simulate a process restart: the project and panel inventory remain in SQLite.
        reopened = Workflow(self.wf.db_path, self.wf.asset_root, self.provider).get_project(self.pid)
        self.assertEqual(reopened["round_number"], 2)
        self.assertEqual(reopened["phase"], "feedback")
        panel = render(reopened)
        self.assertIn("第 2 轮反馈", panel)
        self.assertIn("name=\"asset_id\"", panel)
        self.assertIn('type="checkbox" name="allow"', panel)
        self.assertIn("textarea", panel)

    def test_refinement_requires_locked_file_allow_preserve_and_forbid(self):
        p = self.new_round()
        with self.assertRaisesRegex(WorkflowError, "lock"):
            self.wf.refine(self.pid, {"allow": ["光线"]})
        a = p["assets"][0]
        self.wf.lock_asset(self.pid, a["id"])
        with self.assertRaisesRegex(WorkflowError, "allow-list"):
            self.wf.refine(self.pid, {"preserve": ["layout"], "forbid": ["rebuild"]})
        with self.assertRaisesRegex(WorkflowError, "preserve and forbid"):
            self.wf.refine(self.pid, {"allow": ["光线"]})
        self.assertEqual(self.provider.edit_calls, [])

    def test_failed_generation_restores_confirmed_stage_for_retry(self):
        self.wf.confirm_direction(self.pid, "方向一")
        self.provider.fail = True
        with self.assertRaisesRegex(RuntimeError, "injected"):
            self.wf.generate(self.pid)
        failed = self.wf.get_project(self.pid)
        self.assertEqual(failed["phase"], "confirmed")
        self.assertIn("injected generator failure", failed["last_error"])
        self.provider.fail = False
        self.assertEqual(self.wf.generate(self.pid)["phase"], "feedback")

    def test_missing_asset_is_reported_and_never_sent_for_edit(self):
        p = self.new_round()
        a = next(x for x in p["assets"] if x["variant"] == "A")
        Path(a["path"]).unlink()
        recovered = self.wf.recover(self.pid)
        self.assertIn(a["id"], recovered["missing_assets"])
        with self.assertRaisesRegex(WorkflowError, "missing or changed"):
            self.wf.lock_asset(self.pid, a["id"])
        self.assertEqual(self.provider.edit_calls, [])

    def test_three_output_contract_rejects_collage_or_wrong_count(self):
        class BadProvider(FakeProvider):
            def generate_three(self, project, round_number, destination):
                paths = self.write_three(destination, b"x")
                return paths[:1]
        bad = Workflow(self.wf.db_path, self.wf.asset_root, BadProvider())
        # New project to isolate its state.
        p = bad.create_project({})
        bad.confirm_direction(p["id"], "confirmed")
        with self.assertRaisesRegex(WorkflowError, "exactly 3"):
            bad.generate(p["id"])
        self.assertEqual(bad.get_project(p["id"])["phase"], "confirmed")

    def test_brand_asset_checker_reports_missing_and_readable_files(self):
        root = Path(self.temp.name) / "repo"
        (root / "assets/logos").mkdir(parents=True)
        (root / "assets/colors").mkdir(parents=True)
        signature = b"\x89PNG\r\n\x1a\n" + b"fixture"
        for rel in ("assets/logos/三层LOGO-绿.png", "assets/logos/三层LOGO-白.png", "assets/logos/LOGO.png"):
            (root / rel).write_bytes(signature)
        (root / "assets/colors/purcotton-green.svg").write_text('<svg fill="#00AC97">#00AC97</svg>', encoding="utf-8")
        result = inspect_brand_assets(root)
        self.assertTrue(result["purcotton_green_exact"])
        self.assertTrue(result["naisi_logo"]["valid_format"])
        (root / "assets/logos/LOGO.png").unlink()
        self.assertFalse(inspect_brand_assets(root)["naisi_logo"]["exists"])

    def test_live_crop_preserves_center_75_percent_width(self):
        crop = centered_live_crop(900, 1200)
        self.assertEqual(crop["crop_width"], 675)
        self.assertAlmostEqual(crop["left_removed_fraction"], 0.125)
        self.assertAlmostEqual(crop["right_removed_fraction"], 0.125)
        self.assertAlmostEqual(crop["kept_width_fraction"], 0.75)
        with self.assertRaisesRegex(ValueError, "3:4"):
            centered_live_crop(900, 1600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
