"""Runtime checks for required brand files in an installed repository copy."""
from pathlib import Path

ASSETS = {
    "purcotton_green_logo": "assets/logos/三层LOGO-绿.png",
    "purcotton_white_logo": "assets/logos/三层LOGO-白.png",
    "naisi_logo": "assets/logos/LOGO.png",
    "purcotton_green_swatch": "assets/colors/purcotton-green.svg",
}


def inspect_brand_assets(repository_root: str | Path) -> dict:
    root = Path(repository_root)
    result = {}
    for key, rel in ASSETS.items():
        path = root / rel
        exists = path.is_file()
        readable = False
        valid_format = False
        if exists:
            try:
                data = path.read_bytes()
                readable = True
                if rel.endswith(".png"):
                    valid_format = data.startswith(b"\x89PNG\r\n\x1a\n")
                else:
                    text = data.decode("utf-8")
                    valid_format = "#00AC97" in text and 'fill="#00AC97"' in text
            except (OSError, UnicodeDecodeError):
                pass
        result[key] = {"path": rel, "exists": exists, "readable": readable, "valid_format": valid_format}
    result["purcotton_green_exact"] = all(
        result[k]["exists"] and result[k]["readable"] and result[k]["valid_format"]
        for k in ("purcotton_green_logo", "purcotton_green_swatch")
    )
    return result
