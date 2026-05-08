from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PNG_SIZES = [16, 32, 64, 128, 256, 512, 1024]
ICO_SIZE = 256


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def smooth_coverage(distance: float, aa: float = 1.4) -> float:
    return clamp(0.5 - (distance / aa))


def mix_channel(start: int, end: int, factor: float) -> int:
    return int(round(start + (end - start) * clamp(factor)))


def blend(dst: tuple[int, int, int, int], src: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    sr, sg, sb, sa = src
    dr, dg, db, da = dst
    src_alpha = sa / 255.0
    dst_alpha = da / 255.0
    out_alpha = src_alpha + (dst_alpha * (1.0 - src_alpha))
    if out_alpha <= 0:
        return (0, 0, 0, 0)
    out_r = int(round(((sr * src_alpha) + (dr * dst_alpha * (1.0 - src_alpha))) / out_alpha))
    out_g = int(round(((sg * src_alpha) + (dg * dst_alpha * (1.0 - src_alpha))) / out_alpha))
    out_b = int(round(((sb * src_alpha) + (db * dst_alpha * (1.0 - src_alpha))) / out_alpha))
    return (out_r, out_g, out_b, int(round(out_alpha * 255)))


def circle_sdf(x: float, y: float, cx: float, cy: float, radius: float) -> float:
    return math.hypot(x - cx, y - cy) - radius


def union_sdf(x: float, y: float, circles: list[tuple[float, float, float]]) -> float:
    return min(circle_sdf(x, y, cx, cy, radius) for cx, cy, radius in circles)


def segment_distance(x: float, y: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx = bx - ax
    aby = by - ay
    apx = x - ax
    apy = y - ay
    length_squared = (abx * abx) + (aby * aby)
    if length_squared <= 0:
        return math.hypot(apx, apy)
    t = clamp(((apx * abx) + (apy * aby)) / length_squared)
    proj_x = ax + (abx * t)
    proj_y = ay + (aby * t)
    return math.hypot(x - proj_x, y - proj_y)


def render_icon(size: int) -> bytes:
    viewbox = 512.0
    pixels = bytearray(size * size * 4)
    scale = viewbox / size

    cloud_circles = [
        (170, 283, 84),
        (247, 220, 104),
        (332, 232, 95),
        (389, 276, 74),
        (282, 304, 112),
    ]
    bubble_large = (120, 366, 22)
    bubble_small = (82, 407, 13)
    outline_width = 10.0

    for py in range(size):
        for px in range(size):
            x = (px + 0.5) * scale
            y = (py + 0.5) * scale
            color = (0, 0, 0, 0)

            aura_distance = math.hypot(x - 256, y - 250)
            aura_alpha = clamp(1.0 - (aura_distance / 176.0), 0.0, 1.0) ** 2
            if aura_alpha > 0:
                color = blend(color, (44, 224, 255, int(round(aura_alpha * 72))))

            shadow_sdf = union_sdf(x - 12, y - 16, cloud_circles)
            shadow_cov = smooth_coverage(shadow_sdf, aa=2.2)
            if shadow_cov > 0:
                color = blend(color, (9, 19, 31, int(round(shadow_cov * 42))))

            cloud_sdf = union_sdf(x, y, cloud_circles)
            bubble_sdf = min(
                circle_sdf(x, y, *bubble_large),
                circle_sdf(x, y, *bubble_small),
            )

            for sdf in (cloud_sdf, bubble_sdf):
                fill_cov = smooth_coverage(sdf)
                outline_cov = clamp((outline_width - abs(sdf)) / 2.2)
                if fill_cov > 0:
                    fill_mix = clamp((y - 126) / 238.0)
                    fill_color = (
                        mix_channel(246, 195, fill_mix),
                        mix_channel(251, 241, fill_mix),
                        mix_channel(255, 255, fill_mix),
                        int(round(fill_cov * 255)),
                    )
                    color = blend(color, fill_color)
                if outline_cov > 0:
                    color = blend(color, (15, 32, 51, int(round(outline_cov * 255))))

            chevron_left = segment_distance(x, y, 184, 228, 236, 270)
            chevron_right = segment_distance(x, y, 236, 270, 184, 312)
            underscore = segment_distance(x, y, 277, 318, 352, 318)
            terminal_distance = min(chevron_left, chevron_right, underscore)
            terminal_cov = clamp((14.0 - terminal_distance) / 2.4)
            if terminal_cov > 0:
                glow_mix = clamp((x - 180) / 180.0)
                terminal_color = (
                    mix_channel(25, 116, glow_mix),
                    mix_channel(217, 255, glow_mix),
                    mix_channel(255, 184, glow_mix),
                    int(round(terminal_cov * 255)),
                )
                color = blend(color, terminal_color)

            index = (py * size + px) * 4
            pixels[index : index + 4] = bytes(color)
    return bytes(pixels)


def write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    stride = width * 4
    for row in range(height):
        start = row * stride
        rows.append(b"\x00" + rgba[start : start + stride])
    raw = b"".join(rows)
    compressed = zlib.compress(raw, 9)

    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)

    png = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", compressed),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(png)


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


def main() -> None:
    for size in PNG_SIZES:
        rgba = render_icon(size)
        write_png(ROOT / f"mission-control-icon-{size}.png", size, size, rgba)
    write_ico(ROOT / "mission-control.ico", ROOT / f"mission-control-icon-{ICO_SIZE}.png")


if __name__ == "__main__":
    main()
