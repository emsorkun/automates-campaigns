"""
Social media image generator — 4 layouts × 3 formats = 12 images per campaign.

Layouts:
  classic   — Full bleed photo · dark gradient · gold bottom bar       [Standard]
  bold      — Full bleed photo · vignette · oversized offer number     [Standard]
  cinematic — Full bleed photo · diagonal dark band · stamp badge      [Creative]
  split     — Half dark panel / half car photo · editorial clean       [Creative]

Formats:
  og    — 1200 × 630   Facebook / Twitter / OG meta
  post  — 1080 × 1080  Instagram Post / square
  story — 1080 × 1920  Instagram / TikTok Story
"""
import io
import os
import requests
from PIL import Image, ImageDraw, ImageFont

# ── Brand ─────────────────────────────────────────────────────────────────────
GOLD  = (200, 169, 97)
DARK  = (11,  12,  16)
WHITE = (255, 255, 255)
LIGHT = (176, 176, 196)

LOGO_URL   = "https://raw.githubusercontent.com/emsorkun/automates-campaigns/main/logo.png"
FONT_XBOLD = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"
FONT_BOLD  = "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf"

# ── Catalogues ────────────────────────────────────────────────────────────────
FORMATS = {
    "og":    (1200, 630),
    "post":  (1080, 1080),
    "story": (1080, 1920),
}

FORMAT_LABELS = {
    "og":    "Facebook / OG  ·  1200×630",
    "post":  "Instagram Post  ·  1080×1080",
    "story": "Instagram Story  ·  1080×1920",
}

LAYOUT_LABELS = {
    "classic":   "Classic",
    "bold":      "Bold",
    "cinematic": "Cinematic",
    "split":     "Split",
}

# Font sizes per format (headline, car label, badge, site, validity, big-number)
_FS = {
    "og":    dict(hl=70, car=24, badge=34, site=28, valid=26, big=150),
    "post":  dict(hl=86, car=30, badge=44, site=34, valid=30, big=186),
    "story": dict(hl=104, car=38, badge=54, site=40, valid=36, big=224),
}

_font_cache = {}
_logo_cache = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _font(size, xbold=False):
    key = (size, xbold)
    if key not in _font_cache:
        path = "/tmp/montserrat_var.ttf"
        try:
            if not os.path.exists(path):
                import urllib.request
                urllib.request.urlretrieve(FONT_XBOLD, path)
            font = ImageFont.truetype(path, size)
            # Set variable font weight axis: 800 = ExtraBold, 700 = Bold
            try:
                font.set_variation_by_axes([800 if xbold else 700])
            except Exception:
                pass
            _font_cache[key] = font
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


def fetch_multiple_photos(query, n=3):
    """
    Download up to n car photos from Pexels (single API call).
    Returns a list of bytes objects (may be shorter than n if fewer found).
    Falls back to Unsplash / Pixabay for single photo if Pexels unavailable.
    """
    UA      = {"User-Agent": "Mozilla/5.0 (compatible; AutoMatesCampaigns/1.0)"}
    results = []

    pexels_key = os.environ.get("PEXELS_API_KEY", "")
    if pexels_key:
        try:
            r = requests.get("https://api.pexels.com/v1/search",
                headers={"Authorization": pexels_key},
                params={"query": query + " luxury car", "per_page": n,
                        "orientation": "landscape"},
                timeout=8)
            photos = r.json().get("photos", []) if r.ok else []
            for photo in photos[:n]:
                for size_key in ("large2x", "large", "medium"):
                    try:
                        ir = requests.get(photo["src"][size_key], timeout=12, headers=UA)
                        if ir.ok:
                            results.append(ir.content)
                            break
                    except Exception:
                        pass
        except Exception:
            pass

    if not results:
        # Unsplash single-photo fallback
        unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
        if unsplash_key:
            try:
                r = requests.get("https://api.unsplash.com/search/photos",
                    params={"query": query, "per_page": 1, "orientation": "landscape",
                            "client_id": unsplash_key},
                    timeout=8)
                results_us = r.json().get("results", []) if r.ok else []
                if results_us:
                    ir = requests.get(results_us[0]["urls"]["regular"], timeout=12, headers=UA)
                    if ir.ok:
                        results.append(ir.content)
            except Exception:
                pass

    if not results:
        pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
        if pixabay_key:
            try:
                r = requests.get("https://pixabay.com/api/",
                    params={"key": pixabay_key, "q": query, "image_type": "photo",
                            "orientation": "horizontal", "per_page": 3, "safesearch": "true"},
                    timeout=8)
                hits = r.json().get("hits", []) if r.ok else []
                for hit in hits[:n]:
                    try:
                        ir = requests.get(hit["largeImageURL"], timeout=12, headers=UA)
                        if ir.ok:
                            results.append(ir.content)
                    except Exception:
                        pass
            except Exception:
                pass

    return results


def _fetch_photo(query, orient="landscape"):
    """Single-photo download helper (backward compat)."""
    photos = fetch_multiple_photos(query, n=1)
    return photos[0] if photos else None


def _fill(photo_bytes, W, H):
    """Resize photo to fill W×H exactly (crop-to-fill centre)."""
    img     = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    iw, ih  = img.size
    scale   = max(W / iw, H / ih)
    nw, nh  = int(iw * scale), int(ih * scale)
    img     = img.resize((nw, nh), Image.LANCZOS)
    x, y    = (nw - W) // 2, (nh - H) // 2
    return img.crop((x, y, x + W, y + H))


def _gradient_ov(W, H, top_a, bot_a):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    for y in range(H):
        a = int(top_a + (bot_a - top_a) * y / H)
        d.line([(0, y), (W, y)], fill=(11, 12, 16, a))
    return ov


def _wrap(text, font, max_px, draw, max_lines=2):
    words = text.split()
    lines, line = [], ""
    for w in words:
        cand = (line + " " + w).strip()
        if draw.textlength(cand, font=font) <= max_px:
            line = cand
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    return lines[:max_lines]


def _offer_text(offer):
    if offer.get("type") == "discount_percent" and offer.get("discount_percent"):
        return f"{offer['discount_percent']}% OFF"
    if offer.get("type") == "fixed_price" and offer.get("price_per_day"):
        return f"AED {offer['price_per_day']}/day"
    if offer.get("custom_label"):
        return offer["custom_label"]
    return None


def _paste_logo(base, W, H, x=None, y=None, h=None, align="left"):
    logo = _logo()
    if not logo:
        return 0
    lh  = h or int(H * 0.07)
    lw  = int(logo.width * lh / logo.height)
    lr  = logo.resize((lw, lh), Image.LANCZOS)
    pad = int(W * 0.037)
    xp  = x if x is not None else (pad if align == "left" else W - lw - pad)
    yp  = y if y is not None else int(H * 0.055)
    base.paste(lr, (xp, yp), lr)
    return lw


def _to_jpeg(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


def _fs(W, H):
    """Return font-size dict for given dimensions."""
    if W == 1200:
        return _FS["og"]
    return _FS["post"] if H == 1080 else _FS["story"]


# ── Layout 1: Classic ─────────────────────────────────────────────────────────

def _classic(photo, campaign, W, H):
    fs    = _fs(W, H)
    PAD   = int(W * 0.037)
    BAR_H = int(H * 0.12)

    base = photo.convert("RGBA") if photo else Image.new("RGBA", (W, H), (*DARK, 255))

    # Gradient overlay + gold bar
    ov     = _gradient_ov(W, H - BAR_H, 45, 200)
    full   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    full.paste(ov, (0, 0))
    d = ImageDraw.Draw(full)
    d.rectangle([(0, H - BAR_H), (W, H)], fill=(*GOLD, 255))
    base = Image.alpha_composite(base, full)
    draw = ImageDraw.Draw(base)

    # Logo top-left
    _paste_logo(base, W, H)

    # Offer badge top-right
    badge = _offer_text(campaign.get("offer", {}))
    if badge:
        bf  = _font(fs["badge"], xbold=True)
        bw  = int(draw.textlength(badge, font=bf)) + int(W * 0.05)
        bh  = int(fs["badge"] * 1.65)
        bx  = W - bw - PAD
        by  = int(H * 0.044)
        draw.rounded_rectangle([(bx, by), (bx+bw, by+bh)],
                                radius=int(bh * 0.28), fill=GOLD)
        draw.text((bx + int(W*0.025), by + int(bh*0.2)), badge, font=bf, fill=DARK)

    # Cars label
    cars     = campaign.get("cars", [])
    cars_str = "  ·  ".join(
        f"{c.get('make','')} {c.get('model','')}".strip() for c in cars).upper()
    cf    = _font(fs["car"])
    car_y = H - BAR_H - int(H * 0.265)
    draw.text((PAD, car_y), cars_str, font=cf, fill=(*LIGHT, 215))

    # Headline (up to 2 lines)
    headline = campaign.get("headline", campaign.get("campaign_title", ""))
    hf    = _font(fs["hl"], xbold=True)
    lines = _wrap(headline, hf, W - PAD * 2, draw)
    ty    = H - BAR_H - int(H * 0.254)
    for ln in lines:
        draw.text((PAD, ty), ln, font=hf, fill=WHITE)
        ty += int(fs["hl"] * 1.2)

    # Bar: domain · validity
    sf    = _font(fs["site"], xbold=True)
    bar_y = H - BAR_H + int(BAR_H * 0.26)
    draw.text((PAD, bar_y), "automates.ae", font=sf, fill=DARK)
    validity = campaign.get("validity", {}).get("label", "")
    if validity:
        vf = _font(fs["valid"])
        vw = int(draw.textlength(validity, font=vf))
        draw.text((W - vw - PAD, bar_y + int(BAR_H * 0.08)), validity, font=vf, fill=DARK)

    return base


# ── Layout 2: Bold ────────────────────────────────────────────────────────────

def _bold(photo, campaign, W, H):
    """Full bleed · strong vignette · oversized offer · left headline block."""
    fs  = _fs(W, H)
    PAD = int(W * 0.055)

    base = photo.convert("RGBA") if photo else Image.new("RGBA", (W, H), (*DARK, 255))

    # Heavy left-side vignette for text legibility
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d  = ImageDraw.Draw(ov)
    for y in range(H):
        a = int(80 + (y / H) * 80)
        d.line([(0, y), (W, y)], fill=(11, 12, 16, a))
    for x in range(int(W * 0.6)):
        t = 1 - x / (W * 0.6)
        d.line([(x, 0), (x, H)], fill=(11, 12, 16, int(t ** 1.4 * 110)))
    base = Image.alpha_composite(base, ov)
    draw = ImageDraw.Draw(base)

    # Logo top-left (small)
    _paste_logo(base, W, H, h=int(H * 0.058))

    # Oversized offer on right side
    offer = campaign.get("offer", {})
    if offer.get("type") == "discount_percent" and offer.get("discount_percent"):
        big_num = f"{offer['discount_percent']}%"
        sub_txt = "OFF"
        big_f   = _font(fs["big"], xbold=True)
        sub_f   = _font(int(fs["hl"] * 0.88), xbold=True)
        # For OG (landscape) sit right side; for post/story sit more centred-right
        cx = int(W * 0.76)
        cy = int(H * 0.46)
        r  = int(min(W, H) * 0.24)

        # Dark circle with gold border (high contrast so number pops)
        circ = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cd   = ImageDraw.Draw(circ)
        cd.ellipse([(cx-r, cy-r), (cx+r, cy+r)], fill=(*DARK, 210))
        base = Image.alpha_composite(base, circ)
        draw = ImageDraw.Draw(base)
        brd  = max(3, int(r * 0.06))
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], outline=GOLD, width=brd)

        nw = int(draw.textlength(big_num, font=big_f))
        sw = int(draw.textlength(sub_txt, font=sub_f))
        draw.text((cx - nw//2, cy - int(r*0.52)), big_num, font=big_f, fill=GOLD)
        draw.text((cx - sw//2, cy + int(r*0.20)), sub_txt, font=sub_f, fill=WHITE)

    elif offer.get("type") == "fixed_price" and offer.get("price_per_day"):
        big_num = f"AED {offer['price_per_day']}"
        sub_txt = "/ day"
        big_f   = _font(int(fs["big"] * 0.68), xbold=True)
        sub_f   = _font(fs["site"])
        cx, cy  = int(W * 0.76), int(H * 0.49)
        r       = int(min(W, H) * 0.24)
        circ2   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cd2     = ImageDraw.Draw(circ2)
        cd2.ellipse([(cx-r, cy-r), (cx+r, cy+r)], fill=(*DARK, 210))
        base    = Image.alpha_composite(base, circ2)
        draw    = ImageDraw.Draw(base)
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], outline=GOLD, width=max(3, int(r*0.06)))
        nw = int(draw.textlength(big_num, font=big_f))
        sw = int(draw.textlength(sub_txt, font=sub_f))
        draw.text((cx - nw//2, cy - int(r*0.38)), big_num, font=big_f, fill=GOLD)
        draw.text((cx - sw//2, cy + int(r*0.25)), sub_txt, font=sub_f, fill=WHITE)
    else:
        badge = _offer_text(offer)
        if badge:
            bf  = _font(fs["badge"], xbold=True)
            bw  = int(draw.textlength(badge, font=bf)) + int(W * 0.05)
            bh  = int(fs["badge"] * 1.65)
            bx  = W - bw - PAD
            by  = int(H * 0.04)
            draw.rounded_rectangle([(bx, by), (bx+bw, by+bh)],
                                    radius=int(bh * 0.3), fill=GOLD)
            draw.text((bx + int(W*0.025), by + int(bh*0.2)), badge, font=bf, fill=DARK)

    # Left text block — start higher on OG to avoid domain overlap
    cars     = campaign.get("cars", [])
    cars_str = " · ".join(
        f"{c.get('make','')} {c.get('model','')}".strip() for c in cars).upper()

    ty = int(H * 0.390) if W == 1200 else int(H * 0.54)

    # Gold accent rule
    rule_h = max(2, int(H * 0.004))
    draw.rectangle([(PAD, ty), (PAD + int(W * 0.06), ty + rule_h)], fill=GOLD)
    ty += rule_h + int(H * 0.016)

    cf = _font(fs["car"])
    draw.text((PAD, ty), cars_str, font=cf, fill=(*GOLD, 215))
    ty += int(fs["car"] * 1.65)

    headline = campaign.get("headline", campaign.get("campaign_title", ""))
    hf       = _font(int(fs["hl"] * 1.18), xbold=True)
    lines    = _wrap(headline, hf, int(W * 0.54), draw)
    for ln in lines:
        draw.text((PAD, ty), ln, font=hf, fill=WHITE)
        ty += int(fs["hl"] * 1.38)

    # Domain + validity at bottom-left
    sf       = _font(fs["site"], xbold=True)
    vf       = _font(fs["valid"])
    validity = campaign.get("validity", {}).get("label", "")
    sy       = H - PAD - int(fs["site"] * 1.4) - (int(fs["valid"] * 1.55) if validity else 0)
    draw.text((PAD, sy), "automates.ae", font=sf, fill=(*GOLD, 210))
    if validity:
        draw.text((PAD, sy + int(fs["site"] * 1.5)), validity, font=vf, fill=(*LIGHT, 180))

    return base


# ── Layout 3: Cinematic ───────────────────────────────────────────────────────

def _cinematic(photo, campaign, W, H):
    """Full bleed · angled dark band left · diagonal gold line · stamp badge right."""
    fs  = _fs(W, H)
    PAD = int(W * 0.04)

    base = photo.convert("RGBA") if photo else Image.new("RGBA", (W, H), (*DARK, 255))

    # Diagonal band polygon
    band_top = 0.50 if H <= 1080 else 0.58
    band_bot = 0.43 if H <= 1080 else 0.51
    ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d   = ImageDraw.Draw(ov)
    poly = [(0, 0), (int(W*band_top), 0), (int(W*band_bot), H), (0, H)]
    d.polygon(poly, fill=(11, 12, 16, 218))
    base = Image.alpha_composite(base, ov)

    # Gold diagonal line along band edge
    draw = ImageDraw.Draw(base)
    lw   = max(2, int(H * 0.003))
    draw.line([(int(W*band_top), 0), (int(W*band_bot), H)],
              fill=(*GOLD, 210), width=lw)

    # Logo top-right (on bright photo side)
    _paste_logo(base, W, H, align="right", h=int(H * 0.065))

    # Circular stamp badge (right side)
    offer = campaign.get("offer", {})
    badge = _offer_text(offer)
    if badge:
        r   = int(min(W, H) * 0.155)
        cx  = int(W * 0.74)
        cy  = int(H * 0.54)
        # Dark circle with gold border
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], fill=(*DARK, 228))
        brd = max(3, int(r * 0.065))
        draw.ellipse([(cx-r, cy-r), (cx+r, cy+r)], outline=GOLD, width=brd)

        # Inner decoration
        inner_f = _font(int(fs["car"] * 0.85))
        ex_txt  = "EXCLUSIVE"
        ew = int(draw.textlength(ex_txt, font=inner_f))
        draw.text((cx - ew//2, cy - int(r*0.70)), ex_txt, font=inner_f, fill=(*GOLD, 155))

        # Badge text (split last word to new line)
        bf     = _font(fs["badge"], xbold=True)
        parts  = badge.split()
        if len(parts) >= 2:
            top_t = " ".join(parts[:-1])
            bot_t = parts[-1]
            tf    = _font(fs["badge"], xbold=True)
            bf2   = _font(int(fs["badge"] * 0.72))
            tw    = int(draw.textlength(top_t, font=tf))
            bw2   = int(draw.textlength(bot_t, font=bf2))
            draw.text((cx - tw//2, cy - int(r*0.30)), top_t, font=tf, fill=GOLD)
            draw.text((cx - bw2//2, cy + int(r*0.14)), bot_t, font=bf2, fill=WHITE)
        else:
            bw = int(draw.textlength(badge, font=bf))
            draw.text((cx - bw//2, cy - int(fs["badge"]*0.5)), badge, font=bf, fill=GOLD)

        ae_txt = "automates.ae"
        aw = int(draw.textlength(ae_txt, font=inner_f))
        draw.text((cx - aw//2, cy + int(r*0.56)), ae_txt, font=inner_f, fill=(*GOLD, 135))

    # Text inside the dark band
    text_max = int(W * band_bot) - PAD * 2

    lbl_f = _font(int(fs["car"] * 0.88))
    draw.text((PAD, int(H * 0.07)), "AUTOMATES DUBAI", font=lbl_f, fill=(*GOLD, 170))

    cars     = campaign.get("cars", [])
    cars_str = "  ·  ".join(
        f"{c.get('make','')} {c.get('model','')}".strip() for c in cars).upper()
    cf = _font(fs["car"])
    draw.text((PAD, int(H * 0.20)), cars_str, font=cf, fill=(*LIGHT, 210))

    headline = campaign.get("headline", campaign.get("campaign_title", ""))
    hf       = _font(fs["hl"], xbold=True)
    lines    = _wrap(headline, hf, text_max, draw)
    ty       = int(H * 0.28)
    for ln in lines:
        draw.text((PAD, ty), ln, font=hf, fill=WHITE)
        ty += int(fs["hl"] * 1.2)

    # Gold accent rule below headline
    rule_y = ty + int(H * 0.022)
    rw     = min(text_max, PAD + int(W * 0.18))
    rh     = max(2, int(H * 0.003))
    draw.rectangle([(PAD, rule_y), (rw, rule_y + rh)], fill=(*GOLD, 175))

    validity = campaign.get("validity", {}).get("label", "")
    if validity:
        vf = _font(fs["valid"])
        draw.text((PAD, rule_y + int(H * 0.024)), validity, font=vf, fill=(*LIGHT, 195))

    return base


# ── Layout 4: Split ───────────────────────────────────────────────────────────

def _split(photo, campaign, W, H):
    """Editorial split: dark text panel + car photo half."""
    fs  = _fs(W, H)
    PAD = int(W * 0.055)

    base = Image.new("RGBA", (W, H), (*DARK, 255))
    draw = ImageDraw.Draw(base)

    if W > H:
        # ── Landscape (OG 1200×630): left dark panel · right car photo ──
        panel_w = int(W * 0.52)

        if photo:
            photo_w = W - panel_w
            scale   = max(photo_w / photo.width, H / photo.height)
            nw, nh  = int(photo.width * scale), int(photo.height * scale)
            resized = photo.resize((nw, nh), Image.LANCZOS)
            xo      = (nw - photo_w) // 2
            yo      = (nh - H) // 2
            cropped = resized.crop((xo, yo, xo + photo_w, yo + H))

            # Feather left edge
            pov = Image.new("RGBA", (photo_w, H), (0, 0, 0, 0))
            pd  = ImageDraw.Draw(pov)
            feather = int(photo_w * 0.28)
            for x in range(feather):
                a = int(220 * (1 - x / feather) ** 1.6)
                pd.line([(x, 0), (x, H)], fill=(11, 12, 16, a))
            photo_comp = Image.alpha_composite(cropped.convert("RGBA"), pov)
            base.paste(photo_comp.convert("RGB"), (panel_w, 0))
            draw = ImageDraw.Draw(base)

        # Gold separator
        sw = max(3, int(W * 0.003))
        draw.rectangle([(panel_w, 0), (panel_w + sw, H)], fill=GOLD)

        # Decorative gold lines
        for i in range(3):
            ly = int(H * 0.19) + i * int(H * 0.048)
            alpha = 80 - i * 20
            draw.rectangle(
                [(PAD, ly), (PAD + int(panel_w * 0.30), ly + max(2, int(H*0.004)))],
                fill=(*GOLD, alpha))

        # Logo
        _paste_logo(base, W, H, h=int(H * 0.076))

        # Cars
        cars     = campaign.get("cars", [])
        cars_str = " · ".join(
            f"{c.get('make','')} {c.get('model','')}".strip() for c in cars).upper()
        cf = _font(fs["car"])
        draw.text((PAD, int(H * 0.40)), cars_str, font=cf, fill=(*GOLD, 200))

        # Headline
        headline = campaign.get("headline", campaign.get("campaign_title", ""))
        hf    = _font(fs["hl"], xbold=True)
        lines = _wrap(headline, hf, panel_w - PAD * 2, draw)
        ty    = int(H * 0.48)
        for ln in lines:
            draw.text((PAD, ty), ln, font=hf, fill=WHITE)
            ty += int(fs["hl"] * 1.15)

        # Offer badge
        badge = _offer_text(campaign.get("offer", {}))
        if badge:
            bf  = _font(fs["badge"], xbold=True)
            bw  = int(draw.textlength(badge, font=bf)) + int(panel_w * 0.12)
            bh  = int(fs["badge"] * 1.65)
            bx, by = PAD, ty + int(H * 0.015)
            draw.rounded_rectangle([(bx, by), (bx+bw, by+bh)],
                                    radius=int(bh * 0.3), fill=GOLD)
            draw.text((bx + int(panel_w*0.06), by + int(bh*0.22)), badge, font=bf, fill=DARK)

        # Domain
        sf = _font(fs["site"], xbold=True)
        draw.text((PAD, H - PAD - int(fs["site"] * 1.3)), "automates.ae",
                  font=sf, fill=(*GOLD, 175))

    else:
        # ── Portrait (post 1080×1080 · story 1080×1920): top photo · bottom panel ──
        photo_h = int(H * 0.44)

        if photo:
            scale   = max(W / photo.width, photo_h / photo.height)
            nw, nh  = int(photo.width * scale), int(photo.height * scale)
            resized = photo.resize((nw, nh), Image.LANCZOS)
            xo      = (nw - W) // 2
            cropped = resized.crop((xo, 0, xo + W, photo_h))

            # Fade bottom of photo
            pov = Image.new("RGBA", (W, photo_h), (0, 0, 0, 0))
            pd  = ImageDraw.Draw(pov)
            fade = int(photo_h * 0.28)
            for y in range(photo_h - fade, photo_h):
                t = (y - (photo_h - fade)) / fade
                pd.line([(0, y), (W, y)], fill=(11, 12, 16, int(t * 165)))
            photo_comp = Image.alpha_composite(cropped.convert("RGBA"), pov)
            base.paste(photo_comp.convert("RGB"), (0, 0))
            draw = ImageDraw.Draw(base)

        # Gold separator
        sh = max(3, int(H * 0.003))
        draw.rectangle([(0, photo_h), (W, photo_h + sh)], fill=GOLD)

        # Decorative gold lines
        for i in range(3):
            lx    = int(W * 0.14) + i * int(W * 0.055)
            lw2   = int(W * 0.22) - i * int(W * 0.05)
            alpha = 80 - i * 20
            draw.rectangle(
                [(lx, photo_h + int(H*0.022)),
                 (lx + lw2, photo_h + int(H*0.022) + max(2, int(H*0.002)))],
                fill=(*GOLD, alpha))

        ty = photo_h + int((H - photo_h) * 0.07)

        # Logo centred
        logo = _logo()
        if logo:
            lh  = int(H * 0.040)
            lw2 = int(logo.width * lh / logo.height)
            lr  = logo.resize((lw2, lh), Image.LANCZOS)
            base.paste(lr, ((W - lw2) // 2, ty), lr)
            ty += lh + int((H - photo_h) * 0.05)
            draw = ImageDraw.Draw(base)

        # Cars centred
        cars     = campaign.get("cars", [])
        cars_str = " · ".join(
            f"{c.get('make','')} {c.get('model','')}".strip() for c in cars).upper()
        cf  = _font(fs["car"])
        cw  = int(draw.textlength(cars_str, font=cf))
        draw.text(((W - cw) // 2, ty), cars_str, font=cf, fill=(*GOLD, 200))
        ty += int(fs["car"] * 1.75)

        # Headline centred
        headline = campaign.get("headline", campaign.get("campaign_title", ""))
        hf    = _font(fs["hl"], xbold=True)
        lines = _wrap(headline, hf, W - PAD * 2, draw)
        for ln in lines:
            lw3 = int(draw.textlength(ln, font=hf))
            draw.text(((W - lw3) // 2, ty), ln, font=hf, fill=WHITE)
            ty += int(fs["hl"] * 1.18)

        # Offer badge centred
        badge = _offer_text(campaign.get("offer", {}))
        if badge:
            bf  = _font(fs["badge"], xbold=True)
            bw  = int(draw.textlength(badge, font=bf)) + int(W * 0.1)
            bh  = int(fs["badge"] * 1.65)
            bx  = (W - bw) // 2
            by  = ty + int((H - photo_h) * 0.022)
            draw.rounded_rectangle([(bx, by), (bx+bw, by+bh)],
                                    radius=int(bh * 0.35), fill=GOLD)
            draw.text((bx + int(W*0.05), by + int(bh*0.2)), badge, font=bf, fill=DARK)
            ty = by + bh + int((H - photo_h) * 0.03)

        # Domain + validity at bottom centred
        validity = campaign.get("validity", {}).get("label", "")
        sf  = _font(fs["site"], xbold=True)
        vf  = _font(fs["valid"])
        sy  = H - PAD - int(fs["site"] * 1.3) - (int(fs["valid"] * 1.55) if validity else 0)
        sw2 = int(draw.textlength("automates.ae", font=sf))
        draw.text(((W - sw2) // 2, sy), "automates.ae", font=sf, fill=(*GOLD, 178))
        if validity:
            vw = int(draw.textlength(validity, font=vf))
            draw.text(((W - vw) // 2, sy + int(fs["site"] * 1.5)),
                      validity, font=vf, fill=(*LIGHT, 180))

    return base


# ── Public API ────────────────────────────────────────────────────────────────

def generate_social_images(campaign, photo_bytes=None, photo_bytes_list=None):
    """
    Generate social images (4 layouts × 3 formats × up to 3 photo variants).
    Returns dict keyed by "{layout}__{format}" for v1, "{layout}__{format}__v2" for v2, etc.

    photo_bytes_list: list of up to 3 bytes objects (preferred).
    photo_bytes: single bytes object (backward compat — wraps into list).
    """
    cars  = campaign.get("cars", [])
    query = (cars[0].get("image_query") or
             f"{cars[0].get('make','')} {cars[0].get('model','')}".strip()
             if cars else "luxury car Dubai")

    # Resolve photo list
    if photo_bytes_list:
        photos = photo_bytes_list[:3]
    elif photo_bytes is not None:
        photos = [photo_bytes]
    else:
        photos = fetch_multiple_photos(query, n=3)
    if not photos:
        photos = [None]

    layout_fns = {
        "classic":   _classic,
        "bold":      _bold,
        "cinematic": _cinematic,
        "split":     _split,
    }

    # Variant suffix: index 0 → "" (v1), 1 → "__v2", 2 → "__v3"
    _suffix = ["", "__v2", "__v3"]

    results = {}
    for vi, pb in enumerate(photos):
        suffix = _suffix[vi]
        for fmt_key, (W, H) in FORMATS.items():
            car_img = None
            if pb:
                try:
                    car_img = _fill(pb, W, H)
                except Exception:
                    pass

            for layout_key, fn in layout_fns.items():
                key = f"{layout_key}__{fmt_key}{suffix}"
                try:
                    img          = fn(car_img, campaign, W, H)
                    results[key] = _to_jpeg(img)
                except Exception:
                    results[key] = None

    return results


def generate_share_image(campaign):
    """Backward-compatible: return Classic OG (1200×630) JPEG."""
    return generate_social_images(campaign).get("classic__og")
