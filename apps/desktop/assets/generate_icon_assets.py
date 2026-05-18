from __future__ import annotations

import struct
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - exercised in packaging environments without Pillow
    Image = None


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
SOURCE_LOGO_PATH = ROOT / "mission-control-logo.png"
DASHBOARD_PUBLIC_ROOT = REPO_ROOT / "apps" / "dashboard" / "public"
DASHBOARD_FAVICON_PATH = DASHBOARD_PUBLIC_ROOT / "mission-control-mark.png"
PNG_SIZES = [16, 32, 64, 128, 256, 512, 1024]
ICO_SIZE = 256


def generated_png_paths() -> list[Path]:
    return [ROOT / f"mission-control-icon-{size}.png" for size in PNG_SIZES]


def required_output_paths() -> list[Path]:
    return generated_png_paths() + [ROOT / "mission-control.ico", DASHBOARD_FAVICON_PATH]


def write_ico(path: Path, png_path: Path) -> None:
    png_bytes = png_path.read_bytes()
    size = ICO_SIZE if ICO_SIZE < 256 else 0
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack(
        "<BBBBHHII",
        size,
        size,
        0,
        0,
        1,
        32,
        len(png_bytes),
        6 + 16,
    )
    path.write_bytes(header + entry + png_bytes)


def ensure_source_logo() -> None:
    if not SOURCE_LOGO_PATH.exists():
        raise FileNotFoundError(f"Missing source logo: {SOURCE_LOGO_PATH}")


def can_skip_generation() -> bool:
    return all(path.exists() for path in required_output_paths())


def require_pillow() -> None:
    if Image is not None:
        return
    if can_skip_generation():
        return
    raise RuntimeError(
        "Pillow is required to regenerate icon assets. "
        "Install it locally with `python -m pip install pillow` or use an environment where Pillow is available."
    )


def generate_pngs() -> None:
    assert Image is not None
    source = Image.open(SOURCE_LOGO_PATH).convert("RGBA")
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    for size in PNG_SIZES:
        target_path = ROOT / f"mission-control-icon-{size}.png"
        source.resize((size, size), resampling).save(target_path, format="PNG")
    DASHBOARD_PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    source.resize((256, 256), resampling).save(DASHBOARD_FAVICON_PATH, format="PNG")


def main() -> None:
    ensure_source_logo()
    require_pillow()
    if Image is None:
        return
    generate_pngs()
    write_ico(ROOT / "mission-control.ico", ROOT / f"mission-control-icon-{ICO_SIZE}.png")


if __name__ == "__main__":
    main()
