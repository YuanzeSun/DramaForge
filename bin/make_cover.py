#!/usr/bin/env python3
"""Compose a 16:9 Bilibili cover (1146x717) from a vertical generated frame.

The video model cannot spell Chinese reliably, so every character here is drawn in post.
Weight is synthesised with stroke rendering because only a regular-weight CJK font is installed.
"""
import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = os.environ.get("DRAMA_FONT", "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf")
W, H = 1146, 717
INK = "#FFFFFF"
ACCENT = "#FFD24A"


def font(size):
    return ImageFont.truetype(FONT, size)


def heavy(draw, xy, text, size, fill=INK, weight=0.03, shadow=True):
    """Draw text with a stroke to fake a bold weight, plus a soft drop shadow."""
    f = font(size)
    stroke = max(1, round(size * weight))
    if shadow:
        draw.text((xy[0] + 3, xy[1] + 4), text, font=f, fill=(0, 0, 0, 170),
                  stroke_width=stroke, stroke_fill=(0, 0, 0, 170))
    draw.text(xy, text, font=f, fill=fill, stroke_width=stroke, stroke_fill=fill)
    return draw.textbbox(xy, text, font=f, stroke_width=stroke)


def build(source, top, title, latin, hook, badge, out, anchor="left"):
    frame = Image.open(source).convert("RGB")
    band = round(frame.width * 9 / 16)
    top = max(0, min(top, frame.height - band))
    photo = frame.crop((0, top, frame.width, top + band)).resize((W, H), Image.LANCZOS)

    # Readability scrim on the title side, strongest at the edge.
    scrim = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(scrim)
    for i in range(W):
        t = i / W if anchor == "left" else 1 - i / W
        sd.line([(i, 0), (i, H)], fill=int(246 * max(0.0, 1 - t * 2.35) ** 1.15))
    photo = Image.composite(Image.new("RGB", (W, H), (6, 14, 24)), photo, scrim.filter(ImageFilter.GaussianBlur(12)))

    # Slight vignette at the bottom so the badge row stays legible.
    foot = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(foot)
    for j in range(H):
        fd.line([(0, j), (W, j)], fill=int(150 * max(0.0, (j / H - 0.74) / 0.26) ** 1.2))
    photo = Image.composite(Image.new("RGB", (W, H), (4, 10, 18)), photo, foot)

    card = photo.convert("RGBA")
    draw = ImageDraw.Draw(card, "RGBA")
    x = 62 if anchor == "left" else W - 62

    size = 128 if len(title) <= 4 else 104
    if anchor == "right":
        x -= draw.textlength(title, font=font(size))
    box = heavy(draw, (x, 92), title, size, weight=0.026)

    y = box[3] + 18
    draw.line([(x + 4, y), (x + 4 + min(360, draw.textlength(latin, font=font(34)) + 40), y)], fill=ACCENT, width=5)
    draw.text((x + 4, y + 20), latin, font=font(34), fill=ACCENT)

    if hook:
        y += 86
        for line in hook.split("\n"):
            heavy(draw, (x + 4, y), line, 46, weight=0.03)
            y += 68

    if badge:
        f = font(38)
        tw = draw.textlength(badge, font=f)
        draw.rounded_rectangle((x, H - 112, x + tw + 56, H - 44), radius=34, fill=ACCENT)
        draw.text((x + 28, H - 102), badge, font=f, fill="#1A1206")

    card.convert("RGB").save(out, quality=95, subsampling=0)
    print(f"{out}  {W}x{H}  {Path(out).stat().st_size // 1024} KB")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--top", type=int, default=250, help="crop offset into the vertical frame")
    p.add_argument("--title", required=True)
    p.add_argument("--latin", default="", help="optional latin subtitle line")
    p.add_argument("--hook", default="")
    p.add_argument("--badge", default="")
    p.add_argument("--anchor", default="left", choices=["left", "right"])
    p.add_argument("--out", required=True)
    build(**vars(p.parse_args()))
