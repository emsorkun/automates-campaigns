"""
GitHub REST API wrapper for AutoMates Campaign Manager.
Uses only the GitHub REST API (no git/gh CLI) so it works on Railway.
"""

import os
import base64
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = "emsorkun/automates-campaigns"
GITHUB_API   = "https://api.github.com"
PAGES_BASE   = "https://emsorkun.github.io/automates-campaigns"

LOCAL_LOGO_PATH = "/Users/enver/Documents/Github/automates-campaigns/logo.png"


def _headers() -> dict:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_file_sha(path: str):
    """Return sha of file at path in the repo, or None if not found."""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    if resp.status_code == 200:
        return resp.json().get("sha")
    return None


def put_file(path: str, content_str: str, message: str):
    """Create or update a file in the repo. content_str is the raw text content."""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"

    encoded = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    payload = {
        "message": message,
        "content": encoded,
    }

    sha = get_file_sha(path)
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def put_binary_file(path: str, content_bytes: bytes, message: str):
    """Create or update a binary file (e.g. image) in the repo."""
    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"

    encoded = base64.b64encode(content_bytes).decode("utf-8")
    payload = {
        "message": message,
        "content": encoded,
    }

    sha = get_file_sha(path)
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def delete_file(path: str, message: str):
    """Delete a file from the repo if it exists."""
    sha = get_file_sha(path)
    if sha is None:
        return  # File doesn't exist, nothing to do

    url = f"{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}"
    payload = {
        "message": message,
        "sha": sha,
    }
    resp = requests.delete(url, headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def ensure_repo():
    """
    Check if the repo exists. If not, create it and enable GitHub Pages.
    Also push logo.png if it doesn't already exist in the repo.
    """
    # Check if repo exists
    repo_url = f"{GITHUB_API}/repos/{GITHUB_REPO}"
    resp = requests.get(repo_url, headers=_headers(), timeout=15)

    if resp.status_code == 404:
        # Create the repo
        create_url = f"{GITHUB_API}/user/repos"
        create_payload = {
            "name": "automates-campaigns",
            "description": "AutoMates Campaign Landing Pages",
            "private": False,
            "auto_init": True,
        }
        create_resp = requests.post(create_url, headers=_headers(), json=create_payload, timeout=30)
        create_resp.raise_for_status()

        # Enable GitHub Pages on main branch
        pages_url = f"{GITHUB_API}/repos/{GITHUB_REPO}/pages"
        pages_payload = {
            "source": {
                "branch": "main",
                "path": "/"
            }
        }
        requests.post(pages_url, headers=_headers(), json=pages_payload, timeout=15)
        # Pages may return 409 if already configured; ignore errors here

    # Push logo.png if it doesn't exist in the repo
    logo_sha = get_file_sha("logo.png")
    if logo_sha is None:
        try:
            with open(LOCAL_LOGO_PATH, "rb") as f:
                logo_bytes = f.read()
            put_binary_file("logo.png", logo_bytes, "chore: add AutoMates logo")
        except FileNotFoundError:
            pass  # Logo not available locally, skip
