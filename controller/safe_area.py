"""3:4 master image to centered 9:16 live-frame safe-area geometry."""


def centered_live_crop(width: int, height: int) -> dict:
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    if width * 4 != height * 3:
        raise ValueError("source image must have a 3:4 aspect ratio")
    kept_width = height * 9 / 16
    margin = (width - kept_width) / 2
    return {
        "source_width": width,
        "source_height": height,
        "crop_left": margin,
        "crop_right": width - margin,
        "crop_width": kept_width,
        "left_removed_fraction": margin / width,
        "right_removed_fraction": margin / width,
        "kept_width_fraction": kept_width / width,
        "target_ratio": "9:16",
    }
