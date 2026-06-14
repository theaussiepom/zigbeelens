#!/usr/bin/env python3
"""Generate ZigbeeLens HA integration brand PNGs from the SVG design spec."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
HA = ROOT / "apps" / "ha_integration"
BRAND = HA / "custom_components" / "zigbeelens" / "brand"

BG_TOP = (0x12, 0x18, 0x20)
BG_BOTTOM = (0x0B, 0x0F, 0x14)
MESH_STROKE = (0xE6, 0xB8, 0x4A, 140)
MESH_NODE = (0xF0, 0xC9, 0x6A)
LENS_STROKE = (0x5B, 0x9F, 0xD4)
HANDLE = (0x8E, 0xC0, 0xF0)


def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))


def _gradient_bg(size: int, radius: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / max(2 * (size - 1), 1)
            px[x, y] = (
                _lerp(BG_TOP[0], BG_BOTTOM[0], t),
                _lerp(BG_TOP[1], BG_BOTTOM[1], t),
                _lerp(BG_TOP[2], BG_BOTTOM[2], t),
                255,
            )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    img.putalpha(mask)
    return img


def render_icon(size: int) -> Image.Image:
    base = 256 if size <= 256 else 512
    s = size / base
    radius = int(round(56 * s if base == 256 else 112 * s))
    img = _gradient_bg(size, radius)
    draw = ImageDraw.Draw(img, "RGBA")

    def pt(x: float, y: float) -> tuple[float, float]:
        return (x * s, y * s)

    lines = [(78, 92, 150, 78), (78, 92, 96, 166), (150, 78, 96, 166), (150, 78, 178, 150)]
    if base == 512:
        lines = [(156, 184, 300, 156), (156, 184, 192, 332), (300, 156, 192, 332), (300, 156, 356, 300)]

    stroke_w = max(2, int(round((6 if base == 256 else 12) * s)))
    for x1, y1, x2, y2 in lines:
        draw.line([pt(x1, y1), pt(x2, y2)], fill=MESH_STROKE, width=stroke_w)

    nodes = [(78, 92), (150, 78), (96, 166), (178, 150)]
    if base == 512:
        nodes = [(156, 184), (300, 156), (192, 332), (356, 300)]
    node_r = (14 if base == 256 else 28) * s
    for cx, cy in nodes:
        x0, y0 = pt(cx, cy)
        draw.ellipse((x0 - node_r, y0 - node_r, x0 + node_r, y0 + node_r), fill=MESH_NODE)

    lens_cx, lens_cy = (150, 138) if base == 256 else (300, 276)
    lens_r = (52 if base == 256 else 104) * s
    lens_w = max(3, int(round((14 if base == 256 else 28) * s)))
    lx, ly = pt(lens_cx, lens_cy)
    draw.ellipse(
        (lx - lens_r, ly - lens_r, lx + lens_r, ly + lens_r),
        outline=LENS_STROKE + (255,),
        width=lens_w,
    )

    if base == 256:
        handle = (188, 176, 214, 202)
    else:
        handle = (376, 352, 428, 404)
    handle_w = max(3, int(round((16 if base == 256 else 32) * s)))
    draw.line([pt(*handle[:2]), pt(*handle[2:])], fill=HANDLE + (255,), width=handle_w)
    return img


def main() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    icon = render_icon(256)
    logo = render_icon(512)
    icon.save(HA / "icon.png")
    logo.save(HA / "logo.png")
    icon.save(BRAND / "icon.png")
    icon.save(BRAND / "icon@2x.png")
    logo.save(BRAND / "logo.png")
    logo.save(BRAND / "logo@2x.png")
    print(f"Wrote brand assets under {HA}")


if __name__ == "__main__":
    main()
