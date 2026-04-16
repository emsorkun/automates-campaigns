# AutoMates Campaign Manager — CLAUDE.md

Development reference for Claude Code sessions. Read this before making any changes.

---

## What This Is

A Flask web app for AutoMates Auto Rentals (Dubai) that lets marketing managers create and manage promotional campaigns. A campaign is a landing page + social media image set generated from a plain-text description using an LLM. Everything is stored in SQLite and served directly from the DB — no static file hosting, no GitHub Pages deploy step.

**Deployed on Railway.** The SQLite database lives on a persistent volume mounted at `/data/campaigns.db`.

---

## File Map

```
app.py               Flask app — all routes, DB helpers, session auth
campaign_engine.py   LLM parsing, HTML generation, car image download
image_engine.py      Pillow-based social image generation (4 layouts × 3 formats)
templates/
  layout.html        Base admin template (header, nav, CSS variables)
  login.html         Standalone login page (no layout.html extension)
  campaigns.html     Campaign list (index)
  create.html        New campaign form
  detail.html        Campaign workspace (left panel + tabbed right panel)
requirements.txt
Dockerfile
```

---

## Database Schema

Three tables live in `campaigns.db` (Railway: `/data/campaigns.db`, local: same directory as `app.py`):

```sql
campaigns (
  slug         TEXT PRIMARY KEY,
  title        TEXT,
  data         TEXT,          -- JSON blob (full campaign dict)
  html         TEXT,          -- Complete landing page HTML stored verbatim
  share_image  BLOB,          -- classic__og image bytes (legacy, kept for OG meta)
  active       INTEGER,       -- 1=live, 0=expired overlay shown
  created_at   TEXT,
  updated_at   TEXT
)

car_images (
  slug  TEXT,
  idx   INTEGER,
  data  BLOB,                 -- Raw JPEG bytes
  PRIMARY KEY (slug, idx)
)
-- idx=0   → landing page photo (variant 1, default)
-- idx=10  → landing page photo variant 2
-- idx=20  → landing page photo variant 3
-- idx=1,2 → second/third car image (if campaign has multiple cars)

social_images (
  slug  TEXT,
  key   TEXT,                 -- See "Social Image Key Format" below
  data  BLOB,
  PRIMARY KEY (slug, key)
)

analytics (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  slug  TEXT,
  event TEXT,                 -- 'view' | 'cta_whatsapp' | 'cta_call'
  ts    TEXT,
  ua    TEXT,
  ref   TEXT
)
```

---

## Social Image Key Format

Keys follow the pattern `{layout}__{format}` with optional photo variant suffix:

```
classic__og            bold__og            cinematic__og            split__og
classic__post          bold__post          cinematic__post          split__post
classic__story         bold__story         cinematic__story         split__story

classic__og__v2        (photo variant 2)
classic__og__v3        (photo variant 3)
... (same pattern for all 12 base keys)
```

Total: up to 36 images per campaign (12 base × 3 photo variants).

**Layouts** (`image_engine.py`):
- `classic` — full bleed photo, dark gradient, gold bottom bar
- `bold` — full bleed photo with vignette, oversized offer number/badge
- `cinematic` — diagonal dark band across photo, stamp badge
- `split` — half dark editorial panel / half car photo

**Formats** (`image_engine.py`):
- `og` — 1200×630 (Facebook/OG meta)
- `post` — 1080×1080 (Instagram square)
- `story` — 1080×1920 (Instagram/TikTok story)

---

## Key Data Flows

### Creating a campaign

1. User submits free text → `POST /create`
2. `parse_campaign(free_text)` calls LLM → returns structured campaign dict with slug, cars, offer, headline, etc.
3. `_build_campaign_assets(campaign, slug, active=True)`:
   - Fetches 3 photo variants from Pexels (`fetch_multiple_photos`, n=3)
   - Stores photo 1 at `car_images(slug, 0)`, photo 2 at `(slug, 10)`, photo 3 at `(slug, 20)`
   - For campaigns with multiple cars, downloads individual images for cars[1], cars[2], etc. at idx=1, 2, ...
   - Calls `generate_html(campaign, car_image_urls=[...])` — produces full HTML stored verbatim in `campaigns.html`
   - Calls `generate_social_images(campaign, photo_bytes_list=[...])` — produces up to 36 images stored in `social_images`
4. Campaign row inserted into `campaigns` table

### Editing a campaign

1. User submits instruction text → `POST /campaigns/<slug>/edit`
2. `edit_campaign(existing_data, instruction)` calls LLM → returns updated campaign dict
3. Same `_build_campaign_assets` flow as create (replaces all images)

### Serving the landing page

`GET /p/<slug>` reads the stored HTML verbatim and serves it as `text/html`. One regex fix is applied at serve time to rewrite any absolute car-image URLs (from old deployments that baked `http://localhost:5001` into the HTML) to relative paths.

### Landing page photo selection

`POST /campaigns/<slug>/set-car-photo` with `variant=0|10|20` — runs a regex over the stored HTML to replace `url('/p/<slug>/img/N')` with the chosen variant index, then saves the updated HTML back to the DB.

---

## Car Image URL in HTML — Critical Convention

Car images are embedded in the landing page HTML as CSS background-image. The format is:

```css
background-image:url('/p/slug/img/0');
```

**Must use single quotes inside the CSS url()** — the entire style attribute uses double quotes, so using double quotes inside url() breaks the HTML attribute at the first inner double-quote.

The regex in `set_car_photo` and `serve_page` both assume this single-quote format. Do not change it.

---

## LLM Setup

Configured via `LLM_PROVIDER` env var (default: `fireworks`).

| Provider | Env vars needed | Model |
|---|---|---|
| `fireworks` (default) | `FIREWORKS_API_KEY` | `kimi-k2p5` |
| `claude` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `moonshot` | `KIMI_API_KEY` | `moonshot-v1-8k` |

Fireworks uses streaming with the OpenAI-compatible SDK. Claude uses the Anthropic SDK directly.

---

## Photo Fetching

`fetch_multiple_photos(query, n=3)` in `image_engine.py` — calls Pexels API, tries each photo at `large2x` → `large` → `medium` size keys before giving up on that photo. Requires `PEXELS_API_KEY`.

`download_car_image(query)` in `campaign_engine.py` — used for cars[1+] only. Falls back Pexels → Unsplash → Pixabay.

Photo fetch happens **once before the car loop** in `_build_campaign_assets`. If the first fetch returns nothing, it retries with just the make name (e.g. "BMW car" instead of "BMW 3 Series car"). Pass `None` (not `[]`) to `generate_social_images` when no photos available — passing an empty list is falsy differently in the internal check.

---

## Social Image Font

Montserrat variable font downloaded at runtime to `/tmp/montserrat_var.ttf` from GitHub:
`https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf`

Font weight is set via `font.set_variation_by_axes([800])` for ExtraBold (headlines/badges) and `[700]` for Bold (body text). The cached font objects are keyed by `(size, xbold)` tuple.

Font sizes (`_FS` dict in `image_engine.py`) are defined per-format to account for the very different canvas heights.

---

## Admin Authentication

Session-based with a single global password. Routes protected with `@login_required` decorator:
- `index`, `new_campaign`, `create`, `detail`, `edit`, `toggle`, `delete_campaign`, `set_car_photo`

Password: configured via `ADMIN_PASSWORD` env var (default: `12345678` for dev).
Secret key: `SECRET_KEY` env var (default: `automates-dev-key` — set a real value in production).

Public routes (no auth): `/p/<slug>`, `/p/<slug>/img/<idx>`, `/p/<slug>/social/<key>.jpg`, `/p/<slug>/track`, `/p/<slug>/share.png`.

---

## Brand Constants

Defined in `campaign_engine.py` under `BRAND` dict and hardcoded in `image_engine.py` as RGB tuples:

```python
GOLD  = (200, 169, 97)   # #C8A961
DARK  = (11,  12,  16)   # #0B0C10
WHITE = (255, 255, 255)
LIGHT = (176, 176, 196)  # #B0B0C4
```

WhatsApp: `971585532282`, Phone: `+971 58 553 2282`, Website: `automates.ae`

---

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `PEXELS_API_KEY` | Yes | — | Car photo fetch |
| `FIREWORKS_API_KEY` | Yes (default LLM) | hardcoded dev key | LLM calls |
| `ANTHROPIC_API_KEY` | If `LLM_PROVIDER=claude` | — | Claude LLM |
| `KIMI_API_KEY` | If `LLM_PROVIDER=moonshot` | — | Moonshot LLM |
| `LLM_PROVIDER` | No | `fireworks` | `fireworks` / `claude` / `moonshot` |
| `ADMIN_PASSWORD` | No | `12345678` | Campaign manager password |
| `SECRET_KEY` | No | `automates-dev-key` | Flask session key |
| `DB_PATH` | No | `./campaigns.db` | SQLite path (Railway: `/data/campaigns.db`) |
| `PORT` | No | `5000` | Gunicorn bind port |
| `UNSPLASH_ACCESS_KEY` | No | — | Fallback photo source |
| `PIXABAY_API_KEY` | No | — | Fallback photo source |

---

## Deployment

Railway with Docker. `Dockerfile` installs `libjpeg-dev libpng-dev libfreetype6-dev` for Pillow. Gunicorn runs with `--workers 2 --timeout 120` (generous timeout because campaign creation makes several slow API calls).

The Railway persistent volume must be mounted at `/data` so `DB_PATH=/data/campaigns.db` survives redeploys.

---

## Local Development

```bash
pip install -r requirements.txt
PEXELS_API_KEY=... FIREWORKS_API_KEY=... python app.py
# Runs on http://localhost:5000
```

---

## Known Gotchas

1. **CSS url() quoting** — always `url('/p/slug/img/N')` with single quotes. Double quotes break the HTML attribute.

2. **Absolute URLs in stored HTML** — never use `_external=True` in `url_for()` calls that produce URLs stored in the DB. The `serve_page` route has a fallback regex that fixes old records, but don't create new ones.

3. **Photo bytes vs None vs []** — `generate_social_images` checks `if photo_bytes_list:` to decide whether to fetch internally. Pass `None` to trigger internal fetch. Passing `[]` also triggers it (falsy), but is confusing — always use `None` explicitly.

4. **Variant idx spacing** — car_images uses idx=10/20 (not 1/2) for photo variants to avoid colliding with idx=1/2 used for second/third car in multi-car campaigns.

5. **Font download on first use** — `/tmp/montserrat_var.ttf` is downloaded once per container lifetime. If Railway restarts the container, the font is re-downloaded automatically.

6. **Social image layout positioning** — font sizes were significantly increased in a past session. All pixel positions in `image_engine.py` are calibrated to the current `_FS` values. If you change font sizes, re-audit all `ty` (top-y) and badge height calculations in all 4 layout functions.
