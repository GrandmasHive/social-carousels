#!/usr/bin/env python3
"""render_social_card.py -- turn a post hook into a branded 1080x1350 social card (PIL, no browser).

Used by the daily social cloud routine: each post's hook becomes a branded image card, which
upload_media.py then hosts on WordPress for Buffer/LinkedIn/Instagram to fetch.

Three brand lanes, each drawn by hand (fonts vendored in ./fonts, logos in ./brand -- no network,
no system fonts, no Chromium). Emphasis: wrap the ONE phrase to accent in *asterisks*.

Usage:
  python render_social_card.py --brand b2bindemand \
      --hook "Your MQL chart is *lying* to your board." --eyebrow "DEMAND GEN" --out card.png
  python render_social_card.py --brand grandmashive --hook "Safe content is the *expensive* kind." --out gh.png
  python render_social_card.py --brand simplified-management --hook "The property should run itself. *Not you*." --out sm.png

Brands: b2bindemand | grandmashive | simplified-management. --height 1350 (default) or 1080.
Exits nonzero (writes nothing) if the hook cannot fit even at the minimum size -- shorten and re-run.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
BRAND = HERE / "brand"
W = 1080
PAD_X = 88

BRANDS = {
    "b2bindemand": {
        "bg": (10, 10, 15), "ink": (244, 244, 245), "accent": (242, 108, 30), "muted": (154, 154, 166),
        "eyebrow_default": "DEMAND GEN",
        "head_font": "Fraunces-Display-600.ttf", "head_em_font": "Fraunces-Display-Italic-400.ttf",
        "label_font": "LiberationSans-Bold.ttf", "body_font": "LiberationSans-Regular.ttf",
        "head_min": 60, "head_max": 98, "em_italic": True, "em_style": "color",
        "logo": "b2bindemand-white.png", "wordmark": None, "decor": "rings",
    },
    "grandmashive": {
        "bg": (0, 0, 0), "ink": (255, 255, 255), "accent": (222, 255, 0), "muted": (140, 140, 140),
        "eyebrow_default": "MARKETING, DECODED",
        "head_font": "LiberationSans-Bold.ttf", "head_em_font": "LiberationSans-Bold.ttf",
        "label_font": "LiberationSans-Bold.ttf", "body_font": "LiberationSans-Regular.ttf",
        "head_min": 72, "head_max": 120, "em_italic": False, "em_style": "block",
        "logo": None, "wordmark": "grandma's hive", "decor": "bar",
    },
    "simplified-management": {
        "bg": (255, 255, 255), "ink": (15, 23, 42), "accent": (37, 99, 235), "muted": (100, 116, 139),
        "eyebrow_default": "OPERATOR NOTE",
        "head_font": "Inter-700.ttf", "head_em_font": "Inter-700.ttf",
        "label_font": "Inter-700.ttf", "body_font": "Inter-500.ttf",
        "head_min": 52, "head_max": 82, "em_italic": False, "em_style": "color",
        "logo": "sm-icon-512.png", "wordmark": "Simplified Management", "decor": "dotgrid",
        "tagline": "Keep it simple.",
    },
}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def tokenize(hook: str):
    """[(word, is_emphasis)] -- split on *emphasis* spans, then on spaces."""
    out = []
    for i, seg in enumerate(re.split(r"\*(.+?)\*", hook)):
        em = (i % 2 == 1)
        for word in seg.split():
            out.append((word, em))
    return out


def wrap(tokens, fnt, em_fnt, max_w, draw):
    """Greedy word-wrap into lines; each line is a list of (word, em)."""
    space = draw.textlength(" ", font=fnt)
    lines, cur, cur_w = [], [], 0.0
    for word, em in tokens:
        wf = em_fnt if em else fnt
        ww = draw.textlength(word, font=wf)
        add = ww if not cur else cur_w + space + ww
        if cur and add > max_w:
            lines.append(cur)
            cur, cur_w = [(word, em)], ww
        else:
            cur.append((word, em))
            cur_w = add
    if cur:
        lines.append(cur)
    return lines


def line_width(line, fnt, em_fnt, draw):
    space = draw.textlength(" ", font=fnt)
    total = 0.0
    for i, (word, em) in enumerate(line):
        wf = em_fnt if em else fnt
        total += draw.textlength(word, font=wf) + (space if i else 0)
    return total


def fit_headline(tokens, cfg, box_w, box_h, draw):
    """Largest head size in [min,max] where the wrapped headline fits box_w x box_h. Returns (size, lines) or None."""
    for size in range(cfg["head_max"], cfg["head_min"] - 1, -2):
        fnt = font(cfg["head_font"], size)
        em_fnt = font(cfg["head_em_font"], size)
        lines = wrap(tokens, fnt, em_fnt, box_w, draw)
        lh = int(size * 1.08)
        if all(line_width(ln, fnt, em_fnt, draw) <= box_w for ln in lines) and len(lines) * lh <= box_h:
            return size, lines, fnt, em_fnt, lh
    return None


def draw_headline(draw, lines, x, y, fnt, em_fnt, lh, cfg, img):
    space = draw.textlength(" ", font=fnt)
    ink, accent = cfg["ink"], cfg["accent"]
    for line in lines:
        cx = x
        for i, (word, em) in enumerate(line):
            wf = em_fnt if em else fnt
            if i:
                cx += space
            ww = draw.textlength(word, font=wf)
            if em and cfg["em_style"] == "block":
                # accent highlight block behind the word (GH)
                pad = 10
                asc, desc = wf.getmetrics()
                draw.rounded_rectangle([cx - pad, y - 2, cx + ww + pad, y + asc + desc * 0.5], radius=6, fill=accent)
                draw.text((cx, y), word, font=wf, fill=cfg["bg"])
            elif em:
                draw.text((cx, y), word, font=wf, fill=accent)
            else:
                draw.text((cx, y), word, font=wf, fill=ink)
            cx += ww
        y += lh
    return y


def paste_logo(img, path, target_h, x, y):
    logo = Image.open(path).convert("RGBA")
    scale = target_h / logo.height
    logo = logo.resize((int(logo.width * scale), target_h), Image.LANCZOS)
    img.paste(logo, (x, y), logo)
    return logo.width


def draw_decor(draw, img, cfg):
    kind = cfg["decor"]; accent = cfg["accent"]
    if kind == "rings":
        for r, a in ((300, 40), (200, 55)):
            bb = [W - 120 - r, 1350 - 120 - r, W - 120 + r, 1350 - 120 + r]
            draw.ellipse(bb, outline=(accent[0], accent[1], accent[2], a), width=2)
    elif kind == "bar":
        draw.rectangle([PAD_X, 92, PAD_X + 72, 98], fill=accent)
    elif kind == "dotgrid":
        step, r = 34, 2
        for gy in range(150, 1200, step):
            for gx in range(PAD_X, W - PAD_X, step):
                draw.ellipse([gx - r, gy - r, gx + r, gy + r], fill=(226, 232, 240))


def render(brand: str, hook: str, eyebrow: str | None, out: Path, height: int):
    cfg = BRANDS[brand]
    H = height
    img = Image.new("RGB", (W, H), cfg["bg"])
    draw = ImageDraw.Draw(img, "RGBA")

    draw_decor(draw, img, cfg)

    # eyebrow + rule (top)
    eb = (eyebrow or cfg["eyebrow_default"]).upper()
    eb_font = font(cfg["label_font"], 26)
    top = 96
    if brand == "simplified-management":
        # pill eyebrow
        tw = draw.textlength(eb, font=eb_font)
        draw.rounded_rectangle([PAD_X, top, PAD_X + tw + 44, top + 52], radius=26, fill=(239, 244, 255))
        draw.text((PAD_X + 22, top + 13), eb, font=eb_font, fill=cfg["accent"])
        head_top = top + 120
    else:
        draw.text((PAD_X, top), eb, font=eb_font, fill=cfg["accent"])
        draw.rectangle([PAD_X, top + 44, PAD_X + 64, top + 46], fill=cfg["accent"])
        head_top = top + 104

    # headline auto-fit box
    box_w = W - 2 * PAD_X
    foot_h = 150
    box_h = H - head_top - foot_h
    tokens = tokenize(hook)
    fit = fit_headline(tokens, cfg, box_w, box_h, draw)
    if not fit:
        sys.stderr.write(f"OVERFLOW: hook too long for {brand} at min size {cfg['head_min']}px. Shorten it.\n")
        return 2
    size, lines, fnt, em_fnt, lh = fit
    # vertically center the headline block within the body box for balance
    text_h = len(lines) * lh
    head_y = head_top + max(0, (box_h - text_h) // 2)
    draw_headline(draw, lines, PAD_X, head_y, fnt, em_fnt, lh, cfg, img)

    # footer: logo / wordmark
    fy = H - 100
    if cfg["logo"]:
        lw = paste_logo(img, BRAND / cfg["logo"], 44 if brand == "simplified-management" else 40, PAD_X, fy - 8)
        if cfg.get("wordmark"):
            wf = font(cfg["label_font"], 30)
            draw.text((PAD_X + lw + 22, fy), cfg["wordmark"], font=wf, fill=cfg["ink"])
    elif cfg.get("wordmark"):
        wf = font(cfg["label_font"], 34)
        draw.text((PAD_X, fy), cfg["wordmark"], font=wf, fill=cfg["ink"])
        ww = draw.textlength(cfg["wordmark"], font=wf)
        draw.ellipse([PAD_X + ww + 10, fy + 24, PAD_X + ww + 26, fy + 40], fill=cfg["accent"])

    if brand == "b2bindemand":
        draw.ellipse([W - PAD_X - 14, fy + 12, W - PAD_X, fy + 26], fill=cfg["accent"])
    if brand == "simplified-management" and cfg.get("tagline"):
        tf = font(cfg["body_font"], 26)
        tw = draw.textlength(cfg["tagline"], font=tf)
        draw.text((W - PAD_X - tw, fy + 8), cfg["tagline"], font=tf, fill=cfg["muted"])

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    kb = out.stat().st_size / 1024
    if kb > 5120:
        sys.stderr.write(f"WARNING: {out.name} is {kb/1024:.1f}MB, over LinkedIn 5MB.\n")
    sys.stderr.write(f"OK {out.name} {W}x{H} head={size}px lines={len(lines)} {kb:.0f}KB\n")
    print(str(out))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--brand", required=True, choices=list(BRANDS))
    ap.add_argument("--hook", required=True, help="hook text; wrap the ONE accent phrase in *asterisks*")
    ap.add_argument("--eyebrow", default=None)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--height", type=int, default=1350, choices=[1350, 1080])
    a = ap.parse_args()
    return render(a.brand, a.hook, a.eyebrow, a.out, a.height)


if __name__ == "__main__":
    raise SystemExit(main())
