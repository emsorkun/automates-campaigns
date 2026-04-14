#!/usr/bin/env python3
"""
AutoMates Campaign Landing Page Generator
Usage: python3 generate_campaign.py "BMW 3 Series and X5, 25% off, valid until April 20"
"""

import sys
import os
import json
import re
import subprocess
import datetime
import base64
import warnings
warnings.filterwarnings("ignore")

import requests
try:
    import anthropic as _anthropic
except ImportError:
    _anthropic = None
try:
    from openai import OpenAI as _OpenAI
except ImportError:
    _OpenAI = None

# ── Config ──────────────────────────────────────────────────────────────────
# LLM_PROVIDER: "fireworks" (default, cheap), "moonshot" (direct Kimi), "claude"
LLM_PROVIDER        = os.environ.get("LLM_PROVIDER", "fireworks").lower()
ANTHROPIC_API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
KIMI_API_KEY        = os.environ.get("KIMI_API_KEY", "")
FIREWORKS_API_KEY   = os.environ.get("FIREWORKS_API_KEY", "fw_VrwvhttcmQb7ZCmEXLwojs")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
PEXELS_API_KEY      = os.environ.get("PEXELS_API_KEY", "")

# Provider endpoints (all OpenAI-compatible except Claude)
FIREWORKS_BASE_URL  = "https://api.fireworks.ai/inference/v1"
FIREWORKS_MODEL     = "accounts/fireworks/models/kimi-k2p5"
MOONSHOT_BASE_URL   = "https://api.moonshot.cn/v1"
MOONSHOT_MODEL      = "moonshot-v1-8k"
CLAUDE_MODEL        = "claude-sonnet-4-6"

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
CAMPAIGNS_DIR = os.path.join(REPO_DIR, "campaigns")
GITHUB_REPO = "emsorkun/automates-campaigns"
GITHUB_PAGES_BASE = f"https://emsorkun.github.io/automates-campaigns"

BRAND = {
    "company": "AutoMates Auto Rentals L.L.C.",
    "tagline": "Dubai's Trusted Premium Car Rental Partner",
    "website": "automates.ae",
    "phone1": "+971 58 553 2282",
    "phone2": "+971 58 573 8845",
    "instagram": "@automates",
    "whatsapp": "971585532282",
    "bg": "#0B0C10",
    "surface": "#14151B",
    "card": "#1A1B22",
    "gold": "#C8A961",
    "gold_light": "#E8D5A3",
    "white": "#FFFFFF",
    "light": "#B0B0C4",
    "muted": "#6E6E82",
}


# ── Step 1: Parse campaign from free text ───────────────────────────────────
PARSE_PROMPT = """You are a campaign data extractor for a Dubai premium car rental company.

Extract campaign details from this free text and return ONLY valid JSON (no markdown, no explanation):

Text: "{free_text}"

Return this exact JSON structure:
{{
  "campaign_title": "short catchy title for the campaign (e.g. 'Weekend Flash Deal')",
  "slug": "url-friendly-slug (lowercase, hyphens, no spaces, e.g. 'bmw-weekend-deal')",
  "cars": [
    {{
      "make": "BMW",
      "model": "3 Series",
      "year": null,
      "image_query": "BMW 3 Series car exterior"
    }}
  ],
  "offer": {{
    "type": "discount_percent | fixed_price | free_upgrade | custom",
    "discount_percent": null,
    "price_per_day": null,
    "price_currency": "AED",
    "custom_label": null
  }},
  "validity": {{
    "start": null,
    "end": null,
    "label": "human readable validity like 'Valid until April 20' or 'This weekend only'"
  }},
  "headline": "compelling marketing headline (max 60 chars)",
  "subheadline": "supporting text (max 120 chars)",
  "cta_text": "Book Now",
  "highlights": ["up to 3 short bullet points about the deal"]
}}

Rules:
- slug must be unique and descriptive, include car name and deal type
- If multiple cars, list each separately
- price_currency default is AED
- If no validity mentioned, set label to "Limited Time Offer"
- Make headline exciting and Dubai-luxury appropriate"""


def _extract_json(raw: str) -> dict:
    """Extract JSON from model output, handling reasoning models that think before answering."""
    # Try code fence first: ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    # Try last standalone JSON object in the text (reasoning models output thoughts then JSON)
    matches = list(re.finditer(r"\{[\s\S]*\}", raw))
    if matches:
        for m in reversed(matches):
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No valid JSON found in model output. Raw: {raw[:300]}")


def parse_campaign(free_text: str) -> dict:
    prompt = PARSE_PROMPT.format(free_text=free_text)

    if LLM_PROVIDER == "claude":
        if not _anthropic:
            raise RuntimeError("anthropic package not installed. Run: pip3 install anthropic")
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return _extract_json(msg.content[0].text)

    elif LLM_PROVIDER == "moonshot":
        if not _OpenAI:
            raise RuntimeError("openai package not installed. Run: pip3 install openai")
        if not KIMI_API_KEY:
            raise RuntimeError("KIMI_API_KEY not set")
        client = _OpenAI(api_key=KIMI_API_KEY, base_url=MOONSHOT_BASE_URL)
        resp = client.chat.completions.create(
            model=MOONSHOT_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        return _extract_json(resp.choices[0].message.content)

    else:  # fireworks (default) — Kimi K2 via Fireworks AI
        if not _OpenAI:
            raise RuntimeError("openai package not installed. Run: pip3 install openai")
        if not FIREWORKS_API_KEY:
            raise RuntimeError("FIREWORKS_API_KEY not set")
        client = _OpenAI(api_key=FIREWORKS_API_KEY, base_url=FIREWORKS_BASE_URL)
        # Use streaming (required for max_tokens > 4096 on Fireworks)
        # Collect full response via stream
        full_content = ""
        with client.chat.completions.create(
            model=FIREWORKS_MODEL,
            max_tokens=6000,
            stream=True,
            messages=[
                {"role": "system", "content": "You are a JSON-only extractor. Output ONLY valid JSON, no explanation, no markdown."},
                {"role": "user", "content": prompt}
            ]
        ) as stream:
            for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                    full_content += delta
        return _extract_json(full_content)


# ── Step 2: Fetch car image ─────────────────────────────────────────────────
def fetch_car_image(query: str) -> str:
    """Returns a URL to a car image. Falls back to gradient if no API keys."""

    # Try Pexels first
    if PEXELS_API_KEY:
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": query + " car rental Dubai", "per_page": 1, "orientation": "landscape"},
                timeout=5
            )
            if r.status_code == 200:
                photos = r.json().get("photos", [])
                if photos:
                    return photos[0]["src"]["large2x"]
        except Exception:
            pass

    # Try Unsplash
    if UNSPLASH_ACCESS_KEY:
        try:
            r = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 1, "orientation": "landscape", "client_id": UNSPLASH_ACCESS_KEY},
                timeout=5
            )
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    return results[0]["urls"]["regular"]
        except Exception:
            pass

    # Fallback: return empty string (CSS gradient will be used)
    return ""


# ── Step 3: Generate HTML ────────────────────────────────────────────────────
def render_car_card(car: dict, offer: dict, index: int) -> str:
    image_url = fetch_car_image(car.get("image_query", f"{car['make']} {car['model']}"))
    car_name = f"{car.get('make', '')} {car.get('model', '')}".strip()

    if offer["type"] == "discount_percent" and offer.get("discount_percent"):
        badge = f"{offer['discount_percent']}% OFF"
        price_html = f'<div class="price-badge">{badge}</div>'
    elif offer["type"] == "fixed_price" and offer.get("price_per_day"):
        currency = offer.get("price_currency", "AED")
        price_html = f'<div class="price-badge">{currency} {offer["price_per_day"]}<span>/day</span></div>'
    elif offer.get("custom_label"):
        price_html = f'<div class="price-badge">{offer["custom_label"]}</div>'
    else:
        price_html = ""

    if image_url:
        img_style = f'background-image:url("{image_url}"); background-size:cover; background-position:center;'
        img_overlay = '<div class="card-img-overlay"></div>'
    else:
        # Gold gradient fallback
        hue = (index * 47) % 360
        img_style = f'background: linear-gradient(135deg, #1A1B22 0%, #0B0C10 100%);'
        img_overlay = f'<div class="card-img-icon">🚗</div>'

    return f"""
    <div class="car-card">
      <div class="card-image" style="{img_style}">
        {img_overlay}
        {price_html}
      </div>
      <div class="card-body">
        <div class="car-make">{car.get('make', '')}</div>
        <div class="car-model">{car.get('model', '')}</div>
      </div>
    </div>"""


def generate_html(campaign: dict) -> str:
    cars = campaign["cars"]
    offer = campaign["offer"]
    validity = campaign["validity"]
    highlights = campaign.get("highlights", [])

    car_cards = "".join(render_car_card(c, offer, i) for i, c in enumerate(cars))

    highlights_html = ""
    if highlights:
        items = "".join(f'<li><span class="bullet">✦</span>{h}</li>' for h in highlights)
        highlights_html = f'<ul class="highlights">{items}</ul>'

    validity_label = validity.get("label", "Limited Time Offer")

    now = datetime.datetime.now().strftime("%B %Y")
    grid_class = "grid-1" if len(cars) == 1 else ("grid-2" if len(cars) == 2 else "grid-3")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{campaign['campaign_title']} – AutoMates</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:{BRAND['bg']};--surface:{BRAND['surface']};--card:{BRAND['card']};
  --gold:{BRAND['gold']};--gold-light:{BRAND['gold_light']};--gold-dim:rgba(200,169,97,0.15);
  --white:{BRAND['white']};--light:{BRAND['light']};--muted:{BRAND['muted']};
}}
body{{
  font-family:'Inter','Helvetica Neue',Arial,sans-serif;
  background:var(--bg);color:var(--white);min-height:100vh;
}}
h1,h2,h3,h4{{font-family:'Montserrat','Helvetica Neue',Arial,sans-serif}}

/* ── HEADER ── */
header{{
  display:flex;align-items:center;justify-content:space-between;
  padding:24px 48px;border-bottom:1px solid var(--gold-dim);
  background:rgba(11,12,16,0.95);backdrop-filter:blur(8px);
  position:sticky;top:0;z-index:100;
}}
.logo img{{height:44px;width:auto}}
.header-contact{{
  font-size:13px;color:var(--light);
  display:flex;gap:20px;align-items:center;
}}
.header-contact a{{
  color:var(--gold);text-decoration:none;font-weight:500;
  font-family:'Montserrat',sans-serif;letter-spacing:0.5px;
}}

/* ── HERO ── */
.hero{{
  text-align:center;padding:72px 48px 56px;
  background:
    radial-gradient(ellipse at 50% 0%, rgba(200,169,97,0.06) 0%, transparent 60%),
    linear-gradient(180deg,#0B0C10 0%,#0E0F15 100%);
  position:relative;overflow:hidden;
}}
.hero::before{{
  content:'';position:absolute;inset:0;
  background:repeating-linear-gradient(45deg,transparent,transparent 40px,rgba(200,169,97,0.012) 40px,rgba(200,169,97,0.012) 41px);
  pointer-events:none;
}}
.hero-label{{
  font-family:'Montserrat',sans-serif;font-size:11px;font-weight:600;
  letter-spacing:4px;text-transform:uppercase;color:var(--gold);
  margin-bottom:20px;position:relative;z-index:1;
}}
.hero h1{{
  font-size:clamp(32px,5vw,60px);font-weight:800;line-height:1.1;
  letter-spacing:-1px;position:relative;z-index:1;margin-bottom:16px;
}}
.hero h1 span{{
  background:linear-gradient(135deg,var(--gold),var(--gold-light));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}}
.hero-sub{{
  font-size:17px;color:var(--light);max-width:560px;margin:0 auto 32px;
  line-height:1.6;position:relative;z-index:1;
}}
.validity-tag{{
  display:inline-flex;align-items:center;gap:8px;
  background:var(--gold-dim);border:1px solid rgba(200,169,97,0.3);
  border-radius:100px;padding:8px 20px;
  font-family:'Montserrat',sans-serif;font-size:12px;font-weight:600;
  letter-spacing:2px;text-transform:uppercase;color:var(--gold);
  position:relative;z-index:1;
}}
.validity-tag::before{{content:'⏳';font-size:14px;}}

/* ── HIGHLIGHTS ── */
.highlights-section{{padding:0 48px 48px;display:flex;justify-content:center}}
.highlights{{
  list-style:none;display:flex;gap:32px;flex-wrap:wrap;justify-content:center;
  margin-top:0;
}}
.highlights li{{
  display:flex;align-items:center;gap:8px;
  font-size:13.5px;color:var(--light);font-weight:500;
}}
.bullet{{color:var(--gold);font-size:10px}}

/* ── CARS GRID ── */
.cars-section{{padding:0 48px 64px}}
.section-label{{
  text-align:center;font-family:'Montserrat',sans-serif;font-size:11px;
  font-weight:700;letter-spacing:4px;text-transform:uppercase;color:var(--gold);
  margin-bottom:32px;display:flex;align-items:center;gap:16px;
}}
.section-label::before,.section-label::after{{
  content:'';flex:1;height:1px;
  background:linear-gradient(90deg,transparent,var(--gold-dim),transparent);
}}
.cars-grid{{display:grid;gap:24px}}
.grid-1{{grid-template-columns:1fr;max-width:600px;margin:0 auto}}
.grid-2{{grid-template-columns:repeat(2,1fr)}}
.grid-3{{grid-template-columns:repeat(3,1fr)}}
@media(max-width:768px){{
  .grid-2,.grid-3{{grid-template-columns:1fr}}
}}

/* ── CAR CARD ── */
.car-card{{
  background:var(--card);border:1px solid var(--gold-dim);
  border-radius:16px;overflow:hidden;
  transition:transform 0.3s,box-shadow 0.3s;
}}
.car-card:hover{{
  transform:translateY(-4px);
  box-shadow:0 20px 60px rgba(200,169,97,0.12);
}}
.card-image{{
  height:240px;position:relative;background:var(--surface);
  display:flex;align-items:center;justify-content:center;
}}
.card-img-overlay{{
  position:absolute;inset:0;
  background:linear-gradient(to top,rgba(11,12,16,0.7) 0%,transparent 60%);
}}
.card-img-icon{{font-size:64px;opacity:0.15}}
.price-badge{{
  position:absolute;top:16px;right:16px;z-index:2;
  background:linear-gradient(135deg,var(--gold),var(--gold-light));
  color:#0B0C10;font-family:'Montserrat',sans-serif;
  font-size:18px;font-weight:800;letter-spacing:1px;
  padding:8px 16px;border-radius:10px;
  box-shadow:0 4px 20px rgba(200,169,97,0.4);
}}
.price-badge span{{font-size:12px;font-weight:600}}
.card-body{{padding:20px 24px 24px}}
.car-make{{
  font-family:'Montserrat',sans-serif;font-size:11px;font-weight:600;
  letter-spacing:3px;text-transform:uppercase;color:var(--gold);margin-bottom:4px;
}}
.car-model{{
  font-family:'Montserrat',sans-serif;font-size:22px;font-weight:700;color:var(--white);
}}

/* ── CTA SECTION ── */
.cta-section{{
  text-align:center;padding:56px 48px 72px;
  background:radial-gradient(ellipse at 50% 100%,rgba(200,169,97,0.04) 0%,transparent 60%);
}}
.cta-section h2{{
  font-size:28px;font-weight:700;margin-bottom:12px;
}}
.cta-section p{{font-size:15px;color:var(--light);margin-bottom:36px}}
.cta-buttons{{display:flex;gap:16px;justify-content:center;flex-wrap:wrap}}
.btn-primary{{
  display:inline-flex;align-items:center;gap:8px;
  background:linear-gradient(135deg,var(--gold),var(--gold-light));
  color:#0B0C10;font-family:'Montserrat',sans-serif;
  font-size:14px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  padding:16px 36px;border-radius:10px;text-decoration:none;
  transition:opacity 0.2s,transform 0.2s;
  box-shadow:0 4px 24px rgba(200,169,97,0.3);
}}
.btn-primary:hover{{opacity:0.9;transform:translateY(-2px)}}
.btn-secondary{{
  display:inline-flex;align-items:center;gap:8px;
  border:1px solid var(--gold);color:var(--gold);
  font-family:'Montserrat',sans-serif;font-size:14px;font-weight:600;
  letter-spacing:1.5px;text-transform:uppercase;
  padding:16px 36px;border-radius:10px;text-decoration:none;
  transition:background 0.2s,transform 0.2s;
}}
.btn-secondary:hover{{background:var(--gold-dim);transform:translateY(-2px)}}

/* ── FOOTER ── */
footer{{
  border-top:1px solid var(--gold-dim);padding:28px 48px;
  display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;
}}
.footer-left{{display:flex;align-items:center;gap:12px}}
.footer-left img{{height:28px;width:auto}}
.footer-left span{{font-size:12px;color:var(--muted);letter-spacing:1px}}
.footer-right{{font-size:12px;color:var(--muted)}}
.footer-right a{{color:var(--gold-light);text-decoration:none}}

@media(max-width:600px){{
  header{{padding:16px 20px}}
  .header-contact{{display:none}}
  .hero{{padding:48px 20px 40px}}
  .cars-section,.highlights-section,.cta-section{{padding-left:20px;padding-right:20px}}
  footer{{padding:20px}}
  .cta-buttons{{flex-direction:column;align-items:center}}
}}
</style>
</head>
<body>

<header>
  <div class="logo"><img src="../logo.png" alt="AutoMates"></div>
  <nav class="header-contact">
    <a href="tel:{BRAND['phone1'].replace(' ', '')}">{BRAND['phone1']}</a>
    <a href="https://{BRAND['website']}" target="_blank">{BRAND['website']}</a>
  </nav>
</header>

<section class="hero">
  <div class="hero-label">Exclusive Offer · AutoMates Dubai</div>
  <h1>{make_headline_html(campaign['headline'])}</h1>
  <p class="hero-sub">{campaign['subheadline']}</p>
  <div class="validity-tag">{validity_label}</div>
</section>

{f'<section class="highlights-section">{highlights_html}</section>' if highlights_html else ''}

<section class="cars-section">
  <div class="section-label">Featured Vehicles</div>
  <div class="cars-grid {grid_class}">
    {car_cards}
  </div>
</section>

<section class="cta-section">
  <h2>Ready to <span style="color:var(--gold)">Drive?</span></h2>
  <p>Contact us now to secure this deal before it expires.</p>
  <div class="cta-buttons">
    <a class="btn-primary" href="https://wa.me/{BRAND['whatsapp']}?text=Hi%2C+I'm+interested+in+the+{campaign['campaign_title'].replace(' ', '+')}" target="_blank">
      💬 {campaign['cta_text']} on WhatsApp
    </a>
    <a class="btn-secondary" href="tel:{BRAND['phone1'].replace(' ', '')}">
      📞 Call Us
    </a>
  </div>
</section>

<footer>
  <div class="footer-left">
    <img src="../logo.png" alt="AutoMates">
    <span>© {datetime.datetime.now().year} AutoMates Auto Rentals L.L.C.</span>
  </div>
  <div class="footer-right">
    <a href="https://instagram.com/automates" target="_blank">{BRAND['instagram']}</a>
    &nbsp;·&nbsp;
    <a href="https://{BRAND['website']}" target="_blank">{BRAND['website']}</a>
  </div>
</footer>

</body>
</html>"""


def make_headline_html(headline: str) -> str:
    """Wrap last word in gold gradient span for visual punch."""
    words = headline.strip().split()
    if len(words) > 1:
        return " ".join(words[:-1]) + f' <span>{words[-1]}</span>'
    return f"<span>{headline}</span>"


# ── Step 4: Generate campaign index page ─────────────────────────────────────
def update_index(all_campaigns: list[dict]):
    cards = ""
    for c in sorted(all_campaigns, key=lambda x: x.get("created", ""), reverse=True):
        slug = c["slug"]
        title = c["campaign_title"]
        cars_str = ", ".join(f"{v['make']} {v['model']}" for v in c["cars"])
        offer = c["offer"]
        if offer["type"] == "discount_percent" and offer.get("discount_percent"):
            deal = f"{offer['discount_percent']}% OFF"
        elif offer["type"] == "fixed_price" and offer.get("price_per_day"):
            deal = f"{offer.get('price_currency','AED')} {offer['price_per_day']}/day"
        elif offer.get("custom_label"):
            deal = offer["custom_label"]
        else:
            deal = "Special Offer"
        validity = c.get("validity", {}).get("label", "Limited Time")
        cards += f"""
    <a href="campaigns/{slug}.html" class="campaign-card">
      <div class="camp-deal">{deal}</div>
      <div class="camp-title">{title}</div>
      <div class="camp-cars">{cars_str}</div>
      <div class="camp-validity">⏳ {validity}</div>
    </a>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AutoMates – Active Campaigns</title>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#0B0C10;--card:#1A1B22;--gold:#C8A961;--gold-light:#E8D5A3;--gold-dim:rgba(200,169,97,0.15);--white:#fff;--light:#B0B0C4;--muted:#6E6E82}}
body{{font-family:'Inter',sans-serif;background:var(--bg);color:var(--white);min-height:100vh}}
header{{display:flex;align-items:center;gap:16px;padding:24px 48px;border-bottom:1px solid var(--gold-dim)}}
header img{{height:44px}}
header h1{{font-family:'Montserrat',sans-serif;font-size:16px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--gold)}}
.container{{max-width:1200px;margin:0 auto;padding:48px}}
.page-title{{font-family:'Montserrat',sans-serif;font-size:32px;font-weight:800;margin-bottom:8px}}
.page-sub{{color:var(--light);font-size:15px;margin-bottom:40px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}}
.campaign-card{{
  background:var(--card);border:1px solid var(--gold-dim);border-radius:14px;
  padding:24px;text-decoration:none;color:inherit;
  transition:transform 0.2s,box-shadow 0.2s;display:block;
}}
.campaign-card:hover{{transform:translateY(-3px);box-shadow:0 12px 40px rgba(200,169,97,0.1)}}
.camp-deal{{
  font-family:'Montserrat',sans-serif;font-size:22px;font-weight:800;
  color:var(--gold);margin-bottom:8px;
}}
.camp-title{{font-family:'Montserrat',sans-serif;font-size:16px;font-weight:700;margin-bottom:6px}}
.camp-cars{{font-size:13px;color:var(--light);margin-bottom:12px}}
.camp-validity{{font-size:12px;color:var(--muted)}}
footer{{border-top:1px solid var(--gold-dim);padding:24px 48px;font-size:12px;color:var(--muted);text-align:center}}
</style>
</head>
<body>
<header>
  <img src="logo.png" alt="AutoMates">
  <h1>Active Campaigns</h1>
</header>
<div class="container">
  <h2 class="page-title">Current <span style="color:var(--gold)">Deals</span></h2>
  <p class="page-sub">All active promotional campaigns – AutoMates Auto Rentals L.L.C.</p>
  <div class="grid">{cards}
  </div>
</div>
<footer>© {datetime.datetime.now().year} AutoMates Auto Rentals L.L.C. · automates.ae</footer>
</body>
</html>"""

    with open(os.path.join(REPO_DIR, "index.html"), "w") as f:
        f.write(html)
    print("  ✓ Updated campaign index (index.html)")


# ── Step 5: Push to GitHub ───────────────────────────────────────────────────
def ensure_repo():
    """Initialize git repo and create GitHub remote if needed."""
    os.chdir(REPO_DIR)

    # Init git if needed
    if not os.path.exists(os.path.join(REPO_DIR, ".git")):
        subprocess.run(["git", "init", "-b", "main"], check=True, capture_output=True)
        print("  ✓ Git repo initialized")

    # Check if GitHub repo exists
    gh_exists = subprocess.run(
        ["gh", "repo", "view", GITHUB_REPO],
        capture_output=True, text=True
    ).returncode == 0

    if not gh_exists:
        print(f"  Creating GitHub repo {GITHUB_REPO}...")
        # Create repo without --source so we manage remote ourselves
        subprocess.run(
            ["gh", "repo", "create", GITHUB_REPO,
             "--public", "--description", "AutoMates Campaign Landing Pages"],
            check=True, capture_output=True
        )
        # Enable GitHub Pages
        subprocess.run(
            ["gh", "api", f"repos/{GITHUB_REPO}/pages",
             "--method", "POST",
             "-f", "source[branch]=main",
             "-f", "source[path]=/"],
            capture_output=True
        )
        print(f"  ✓ GitHub repo created with Pages enabled")

    # Ensure remote origin is set correctly
    remotes = subprocess.run(["git", "remote"], capture_output=True, text=True).stdout.strip()
    if "origin" not in remotes.split():
        subprocess.run(["git", "remote", "add", "origin",
                        f"https://github.com/{GITHUB_REPO}.git"],
                       check=True, capture_output=True)
    else:
        subprocess.run(["git", "remote", "set-url", "origin",
                        f"https://github.com/{GITHUB_REPO}.git"],
                       check=True, capture_output=True)


def push_campaign(campaign: dict, html: str):
    os.makedirs(CAMPAIGNS_DIR, exist_ok=True)
    slug = campaign["slug"]
    html_path = os.path.join(CAMPAIGNS_DIR, f"{slug}.html")

    with open(html_path, "w") as f:
        f.write(html)
    print(f"  ✓ Saved campaigns/{slug}.html")

    # Load or init campaigns manifest
    manifest_path = os.path.join(REPO_DIR, "campaigns.json")
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            all_campaigns = json.load(f)
    else:
        all_campaigns = []

    # Update or add
    campaign["created"] = datetime.datetime.now().isoformat()
    existing = [i for i, c in enumerate(all_campaigns) if c["slug"] == slug]
    if existing:
        all_campaigns[existing[0]] = campaign
    else:
        all_campaigns.append(campaign)

    with open(manifest_path, "w") as f:
        json.dump(all_campaigns, f, indent=2)

    update_index(all_campaigns)

    # Git commit and push
    os.chdir(REPO_DIR)
    subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m",
         f"campaign: add '{campaign['campaign_title']}' ({slug})"],
        check=True, capture_output=True
    )
    result = subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # First push might need --force for new repos
        subprocess.run(["git", "push", "--set-upstream", "origin", "main", "--force"],
                       check=True)

    page_url = f"{GITHUB_PAGES_BASE}/campaigns/{slug}.html"
    print(f"\n  Live URL: {page_url}")
    return page_url


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_campaign.py \"<campaign description>\"")
        print('Example: python3 generate_campaign.py "BMW 3 Series and X5, 25% off, valid until April 20"')
        sys.exit(1)

    # Validate the right key for the chosen provider
    if LLM_PROVIDER == "claude" and not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set (needed for LLM_PROVIDER=claude)")
        sys.exit(1)
    if LLM_PROVIDER == "moonshot" and not KIMI_API_KEY:
        print("Error: KIMI_API_KEY not set (needed for LLM_PROVIDER=moonshot)")
        sys.exit(1)
    if LLM_PROVIDER == "fireworks" and not FIREWORKS_API_KEY:
        print("Error: FIREWORKS_API_KEY not set (needed for LLM_PROVIDER=fireworks)")
        sys.exit(1)

    free_text = " ".join(sys.argv[1:])
    provider_label = {"fireworks": "Kimi K2 via Fireworks", "moonshot": "Kimi via Moonshot", "claude": "Claude Sonnet"}.get(LLM_PROVIDER, LLM_PROVIDER)
    print(f"\n AutoMates Campaign Generator  [{provider_label}]")
    print(f"  Input: \"{free_text}\"\n")

    print("  [1/4] Parsing campaign with Claude...")
    campaign = parse_campaign(free_text)
    print(f"  ✓ Campaign: '{campaign['campaign_title']}' | Slug: {campaign['slug']}")
    print(f"  ✓ Cars: {', '.join(c['make']+' '+c['model'] for c in campaign['cars'])}")

    print("\n  [2/4] Generating HTML landing page...")
    html = generate_html(campaign)
    print(f"  ✓ HTML generated ({len(html):,} chars)")

    print("\n  [3/4] Setting up GitHub repo...")
    ensure_repo()

    print("\n  [4/4] Pushing to GitHub...")
    url = push_campaign(campaign, html)

    print(f"\n  Done! Campaign is live at:")
    print(f"  {url}")
    print(f"\n  (GitHub Pages may take 1-2 min to deploy on first push)\n")


if __name__ == "__main__":
    main()
