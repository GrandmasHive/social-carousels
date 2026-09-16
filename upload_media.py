#!/usr/bin/env python3
"""
upload_media.py — upload a social card to a WordPress media library and print its public URL.

Why this exists: `.gitignore` excludes `publications/*/outputs/*`, so a card rendered inside a
cloud run is destroyed when the runner exits. Rows in social-queue.csv were recording
`asset_path` values pointing at files that no longer existed anywhere. A scheduler (Buffer,
Publer) also needs a publicly fetchable URL, not a repo path. The site's own media library is
already authenticated by the publishing pipeline, so it is the natural host.

Credentials, in order of preference (same convention as the publish prompts):
  1. <PUB>_WP_URL / <PUB>_WP_USER / <PUB>_WP_APP_PASSWORD   (e.g. B2BID_WP_URL)
  2. WP_URL / WP_USER / WP_APP_PASSWORD
  3. the same names in ./.env

Usage:
  python automation/upload_media.py --file card.png --pub b2bindemand \
      --alt "B2BinDemand: nobody decided what to outsource" [--title ...]

Prints the public URL on stdout and nothing else, so it can be captured directly:
  URL=$(python automation/upload_media.py --file card.png --pub b2bindemand --alt "...")
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Env prefix per lane. The pubs each have their own WordPress; b2bindemand's backend is the
# old-backup host, which is what B2BID_WP_URL points at.
PREFIX = {
    "b2bindemand": "B2BID",
    "martech": "MARTECH",
    "salestech": "SALESTECH",
    "fintech": "FINTECH",
    "hrtech": "HRTECH",
    "cybertech": "CYBERTECH",
}


def load_dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    for p in (ROOT / ".env", Path.cwd() / ".env"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return out


def creds(pub: str) -> tuple[str, str, str]:
    env = {**load_dotenv(), **os.environ}
    pre = PREFIX.get(pub, pub.upper())
    for keys in ((f"{pre}_WP_URL", f"{pre}_WP_USER", f"{pre}_WP_APP_PASSWORD"),
                 ("WP_URL", "WP_USER", "WP_APP_PASSWORD")):
        url, user, pw = (env.get(k, "") for k in keys)
        if url and user and pw:
            return url.rstrip("/"), user, pw
    raise SystemExit(
        f"No WordPress credentials for {pub}. Set {pre}_WP_URL / {pre}_WP_USER / "
        f"{pre}_WP_APP_PASSWORD, or the unprefixed WP_* equivalents.")


def request(url: str, user: str, pw: str, data: bytes | None = None,
            headers: dict[str, str] | None = None, method: str = "GET") -> dict:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    h = {"Authorization": f"Basic {token}", "User-Agent": "gtm-pubs-media/1.0"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - fixed, trusted hosts
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        raise SystemExit(f"WordPress returned {e.code} for {method} {url}: {body}")


def upload(path: Path, pub: str, alt: str, title: str | None = None) -> str:
    if not path.exists():
        raise SystemExit(f"No such file: {path}")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > 5:
        raise SystemExit(f"{path.name} is {size_mb:.1f}MB — over LinkedIn's 5MB image limit.")

    base, user, pw = creds(pub)
    rest = f"{base}/wp-json/wp/v2"
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    media = request(
        f"{rest}/media", user, pw, data=path.read_bytes(), method="POST",
        headers={"Content-Type": ctype,
                 "Content-Disposition": f'attachment; filename="{path.name}"'})

    # alt_text has to be set in a second call; the upload request body is the binary itself.
    payload = json.dumps({"alt_text": alt, "title": title or alt}).encode()
    media = request(f"{rest}/media/{media['id']}", user, pw, data=payload, method="POST",
                    headers={"Content-Type": "application/json"})

    src = media.get("source_url", "")
    if not src.startswith("http"):
        raise SystemExit(f"Upload succeeded but returned no source_url: {media}")
    return src


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload a card to WordPress media, print its URL.")
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--pub", required=True, help=f"one of: {', '.join(PREFIX)}")
    ap.add_argument("--alt", required=True, help="alt text — describes the card, not the article")
    ap.add_argument("--title", default=None)
    a = ap.parse_args()

    url = upload(a.file, a.pub, a.alt, a.title)
    print(url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
