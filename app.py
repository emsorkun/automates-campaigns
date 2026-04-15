"""
AutoMates Campaign Manager - Flask Application
Pages are served directly from SQLite — no GitHub, no deploy wait.
"""

import os
import json
import sqlite3
import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, Response

from campaign_engine import parse_campaign, edit_campaign, generate_html
from image_engine import generate_share_image

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "automates-dev-key")

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "campaigns.db")
)

UTM_PLATFORMS = [
    {"id": "instagram", "label": "Instagram", "icon": "📸", "medium": "social"},
    {"id": "facebook",  "label": "Facebook",  "icon": "👤", "medium": "social"},
    {"id": "google",    "label": "Google Ads", "icon": "🔍", "medium": "cpc"},
    {"id": "tiktok",    "label": "TikTok",     "icon": "🎵", "medium": "social"},
    {"id": "whatsapp",  "label": "WhatsApp",   "icon": "💬", "medium": "messaging"},
    {"id": "email",     "label": "Email",      "icon": "✉️",  "medium": "email"},
    {"id": "sms",       "label": "SMS",        "icon": "📱", "medium": "sms"},
]


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                slug         TEXT PRIMARY KEY,
                title        TEXT NOT NULL,
                data         TEXT NOT NULL,
                html         TEXT NOT NULL DEFAULT '',
                share_image  BLOB,
                active       INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            )
        """)
        for col, definition in [
            ("html",        "TEXT NOT NULL DEFAULT ''"),
            ("share_image", "BLOB"),
        ]:
            try:
                conn.execute(f"ALTER TABLE campaigns ADD COLUMN {col} {definition}")
            except Exception:
                pass
        conn.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _page_url(slug: str) -> str:
    """Public URL for a campaign landing page."""
    return url_for("serve_page", slug=slug, _external=True)


def _build_utm_links(slug: str) -> list:
    base = _page_url(slug)
    return [
        {
            "platform": p,
            "url": f"{base}?utm_source={p['id']}&utm_medium={p['medium']}&utm_campaign={slug}",
        }
        for p in UTM_PLATFORMS
    ]


def _offer_label(offer: dict) -> str:
    if offer.get("type") == "discount_percent" and offer.get("discount_percent"):
        return f"{offer['discount_percent']}% OFF"
    elif offer.get("type") == "fixed_price" and offer.get("price_per_day"):
        return f"{offer.get('price_currency', 'AED')} {offer['price_per_day']}/day"
    elif offer.get("custom_label"):
        return offer["custom_label"]
    return "Special Offer"


def _row_to_campaign(row) -> dict:
    try:
        data = json.loads(row["data"])
    except Exception:
        data = {}
    slug = row["slug"]
    return {
        "slug":           slug,
        "title":          row["title"],
        "active":         bool(row["active"]),
        "created_at":     row["created_at"],
        "updated_at":     row["updated_at"],
        "data":           data,
        "offer_label":    _offer_label(data.get("offer", {})),
        "cars_str":       " · ".join(
            f"{c.get('make','')} {c.get('model','')}".strip()
            for c in data.get("cars", [])
        ),
        "validity_label": data.get("validity", {}).get("label", ""),
        "preview_url":    url_for("serve_page", slug=slug),
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_campaign_assets(campaign: dict, slug: str, active: bool):
    """Generate HTML + share image for a campaign. Returns (html, img_bytes)."""
    og_url = url_for("share_image", slug=slug, _external=True)
    html   = generate_html(campaign, active=active, og_image_url=og_url)
    try:
        img = generate_share_image(campaign)
    except Exception:
        img = None
    return html, img


# ── Public landing page route ─────────────────────────────────────────────────

@app.route("/p/<slug>/share.png")
def share_image(slug: str):
    """Serve the pre-generated social share image (1200×630 JPEG)."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT share_image FROM campaigns WHERE slug = ?", (slug,)
            ).fetchone()
    except Exception:
        return "Not found", 404
    if row is None or not row["share_image"]:
        return "Not found", 404
    return Response(row["share_image"], mimetype="image/jpeg")


@app.route("/p/<slug>")
def serve_page(slug: str):
    """Serve the campaign landing page directly from the database."""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT html, data, active FROM campaigns WHERE slug = ?", (slug,)
            ).fetchone()
    except Exception:
        return "Not found", 404

    if row is None:
        return "Not found", 404

    # If toggled off, regenerate with the expired overlay on the fly
    if not row["active"]:
        try:
            data = json.loads(row["data"])
            html = generate_html(data, active=False)
        except Exception:
            html = row["html"]
    else:
        html = row["html"]

    return Response(html, mimetype="text/html")


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT slug, title, data, active, created_at, updated_at FROM campaigns ORDER BY created_at DESC"
            ).fetchall()
    except Exception as e:
        flash(f"Database error: {e}", "error")
        rows = []

    campaigns = [_row_to_campaign(r) for r in rows]
    return render_template("campaigns.html", campaigns=campaigns)


@app.route("/new")
def new_campaign():
    return render_template("create.html")


@app.route("/create", methods=["POST"])
def create():
    free_text = request.form.get("free_text", "").strip()
    if not free_text:
        flash("Please enter a campaign description.", "error")
        return redirect(url_for("new_campaign"))

    try:
        campaign = parse_campaign(free_text)
    except Exception as e:
        flash(f"Failed to parse campaign: {e}", "error")
        return redirect(url_for("new_campaign"))

    slug = campaign.get("slug", "")
    if not slug:
        flash("Could not generate a slug for this campaign.", "error")
        return redirect(url_for("new_campaign"))

    try:
        html, img = _build_campaign_assets(campaign, slug, active=True)
    except Exception as e:
        flash(f"Failed to generate page: {e}", "error")
        return redirect(url_for("new_campaign"))

    now = datetime.datetime.utcnow().isoformat()
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO campaigns
                   (slug, title, data, html, share_image, active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
                (slug, campaign.get("campaign_title", slug),
                 json.dumps(campaign), html, img, now, now)
            )
            conn.commit()
    except Exception as e:
        flash(f"Failed to save campaign: {e}", "error")
        return redirect(url_for("new_campaign"))

    flash(f"Campaign '{campaign.get('campaign_title', slug)}' is live!", "success")
    return redirect(url_for("detail", slug=slug))


@app.route("/campaigns/<slug>")
def detail(slug: str):
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT slug, title, data, active, created_at, updated_at FROM campaigns WHERE slug = ?",
                (slug,)
            ).fetchone()
    except Exception as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for("index"))

    if row is None:
        flash("Campaign not found.", "error")
        return redirect(url_for("index"))

    campaign = _row_to_campaign(row)
    utm_links = _build_utm_links(slug)
    return render_template("detail.html", campaign=campaign, utm_links=utm_links)


@app.route("/campaigns/<slug>/edit", methods=["POST"])
def edit(slug: str):
    instruction = request.form.get("instruction", "").strip()
    if not instruction:
        flash("Please enter an edit instruction.", "error")
        return redirect(url_for("detail", slug=slug))

    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT data, active FROM campaigns WHERE slug = ?", (slug,)
            ).fetchone()
    except Exception as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for("detail", slug=slug))

    if row is None:
        flash("Campaign not found.", "error")
        return redirect(url_for("index"))

    try:
        existing_data = json.loads(row["data"])
    except Exception:
        flash("Could not parse campaign data.", "error")
        return redirect(url_for("detail", slug=slug))

    try:
        updated_data = edit_campaign(existing_data, instruction)
        updated_data["slug"] = slug  # never change the slug
    except Exception as e:
        flash(f"Failed to apply edit: {e}", "error")
        return redirect(url_for("detail", slug=slug))

    try:
        html, img = _build_campaign_assets(updated_data, slug, active=bool(row["active"]))
    except Exception as e:
        flash(f"Failed to regenerate page: {e}", "error")
        return redirect(url_for("detail", slug=slug))

    now = datetime.datetime.utcnow().isoformat()
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE campaigns SET data=?, html=?, share_image=?, title=?, updated_at=? WHERE slug=?",
                (json.dumps(updated_data), html, img,
                 updated_data.get("campaign_title", slug), now, slug)
            )
            conn.commit()
    except Exception as e:
        flash(f"Failed to save update: {e}", "error")
        return redirect(url_for("detail", slug=slug))

    flash("Campaign updated — live instantly.", "success")
    return redirect(url_for("detail", slug=slug))


@app.route("/campaigns/<slug>/toggle", methods=["POST"])
def toggle(slug: str):
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT active FROM campaigns WHERE slug = ?", (slug,)
            ).fetchone()
    except Exception as e:
        flash(f"Database error: {e}", "error")
        return redirect(url_for("detail", slug=slug))

    if row is None:
        flash("Campaign not found.", "error")
        return redirect(url_for("index"))

    new_active = 0 if row["active"] else 1
    now = datetime.datetime.utcnow().isoformat()
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE campaigns SET active=?, updated_at=? WHERE slug=?",
                (new_active, now, slug)
            )
            conn.commit()
    except Exception as e:
        flash(f"Failed to toggle: {e}", "error")
        return redirect(url_for("detail", slug=slug))

    flash(f"Campaign {'activated' if new_active else 'deactivated'}.", "success")
    return redirect(url_for("detail", slug=slug))


@app.route("/campaigns/<slug>/delete", methods=["POST"])
def delete_campaign(slug: str):
    try:
        with get_db() as conn:
            conn.execute("DELETE FROM campaigns WHERE slug=?", (slug,))
            conn.commit()
    except Exception as e:
        flash(f"Failed to delete: {e}", "error")
        return redirect(url_for("detail", slug=slug))

    flash("Campaign deleted.", "success")
    return redirect(url_for("index"))


# ── Startup ───────────────────────────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
