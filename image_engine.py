"""
Social media share image generator — 1200×630 JPEG.
Pillow-based, no AI, no API keys. Car photos from loremflickr (free Flickr CDN).
"""
import io
import os
import urllib.request
import requests
from PIL import Image, ImageDraw, ImageFont

# Brand colours (RGB)
GOLD  = (200, 169, 97)
DARK  = (11,  12,  16)
WHITE = (255, 255, 255)
LIGHT = (176, 176, 196)

W, H  = 1200, 630
BAR_H = 76
PAD   = 44

LOGO_URL  = "https://raw.githubusercontent.com/emsorkun/automates-campaigns/main/logo.png"
FONT_BOLD = "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf"
FONT_XBOLD= "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-ExtraBold.ttf"

_font_cache: dict = {}
_logo_cache = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _font(size: int, xbold: bool = False):
    key = (size, xbold)
    if key not in _font_cache:
        url  = FONT_XBOLD if xbold else FONT_BOLD
        name = "montserrat_xbold" if xbold else "montserrat_bold"
        path = f"/tmp/{name}.ttf"
        try:
            if not os.path.exists(path):
                urllib.request.urlretrieve(url, path)
            _font_cache[key] = ImageFont.truetype(path, size)
        except Exception:
            _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


def _logo():
    global _logo_cache
    if _logo_cache is None:
        try:
            r = requests.get(LOGO_URL, timeout=6)
            r.raise_for_status()
            _logo_cache = Image.open(io.BytesIO(r.content)).convert("RGBA")
        except Exception:
            _logo_cache = False
    return _logo_cache or None


def _car_photo(query: str):
    """Download a car photo from loremflickr — no API key required."""
    tags = ",".join(query.split()[:5])
    try:
        r = requests.get(
            f"https://loremflickr.com/{W}/{H}/{tags}",
            timeout=12, allow_redirects=True
        )
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            return Image.open(io.BytesIO(r.content)).convert("RGB").resize((W, H), Image.LANCZOS)
    except Exception:
        pass
    return None


def _wrap_text(text: str, font, max_px: int, draw) -> list:
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textlength(candidate, font=font) <= max_px:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines[:2]


# ── Main export ───────────────────────────────────────────────────────────────

def generate_share_image(campaign: dict) -> bytes:
    """Return JPEG bytes for a 1200×630 OG share image."""
    cars     = campaign.get("cars", [])
    offer    = campaign.get("offer", {})
    headline = campaign.get("headline", campaign.get("campaign_title", ""))
    validity = campaign.get("validity", {}).get("label", "")

    # ── Background ────────────────────────────────────────────────────────────
    query   = cars[0].get("image_query", "luxury car") if cars else "luxury car Dubai"
    car_img = _car_photo(query)
    base    = car_img.convert("RGBA") if car_img else Image.new("RGBA", (W, H), (*DARK, 255))

    # ── Dark gradient overlay (heavier at bottom) ─────────────────────────────
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    for y in range(H - BAR_H):
        alpha = int(60 + (y / (H - BAR_H)) * 170)
        d.line([(0, y), (W, y)], fill=(11, 12, 16, alpha))

    # ── Gold bottom bar ───────────────────────────────────────────────────────
    d.rectangle([(0, H - BAR_H), (W, H)], fill=(*GOLD, 250))

    base = Image.alpha_composite(base, ov)
    draw = ImageDraw.Draw(base)

    # ── AutoMates logo (top-left) ─────────────────────────────────────────────
    logo = _logo()
    if logo:
        lh = 44
        lw = int(logo.width * lh / logo.height)
        logo_r = logo.resize((lw, lh), Image.LANCZOS)
        base.paste(logo_r, (PAD, 36), logo_r)

    # ── Offer badge (top-right) ───────────────────────────────────────────────
    if offer.get("type") == "discount_percent" and offer.get("discount_percent"):
        badge = f"{offer['discount_percent']}% OFF"
    elif offer.get("type") == "fixed_price" and offer.get("price_per_day"):
        badge = f"AED {offer['price_per_day']}/day"
    elif offer.get("custom_label"):
        badge = offer["custom_label"]
    else:
        badge = None

    if badge:
        bf   = _font(26, xbold=True)
        bw   = int(draw.textlength(badge, font=bf)) + 40
        bh   = 48
        bx   = W - bw - PAD
        by   = 28
        draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=10, fill=GOLD)
        draw.text((bx + 20, by + 11), badge, font=bf, fill=DARK)

    # ── Car names label ───────────────────────────────────────────────────────
    cars_str = "  ·  ".join(
        f"{c.get('make','')} {c.get('model','')}".strip() for c in cars
    ).upper()
    cf = _font(20)
    draw.text((PAD, H - BAR_H - 148), cars_str, font=cf, fill=(*LIGHT, 220))

    # ── Headline (up to 2 lines) ──────────────────────────────────────────────
    hf    = _font(54, xbold=True)
    lines = _wrap_text(headline, hf, W - PAD * 2, draw)
    ty    = H - BAR_H - 112
    for ln in lines:
        draw.text((PAD, ty), ln, font=hf, fill=WHITE)
        ty += 62

    # ── Bottom bar: automates.ae (left) · validity (right) ───────────────────
    sitef = _font(24, xbold=True)
    draw.text((PAD, H - BAR_H + 20), "automates.ae", font=sitef, fill=DARK)

    if validity:
        vf = _font(20)
        vw = int(draw.textlength(validity, font=vf))
        draw.text((W - vw - PAD, H - BAR_H + 24), validity, font=vf, fill=DARK)

    # ── Export ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()
