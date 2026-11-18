"""Read stable public releases from the project's GitHub repository."""
from pathlib import Path
from dataclasses import dataclass
import re
import sys

import httpx

REPOSITORY = "tonythewizard/SubtitleForEveryone"
RELEASES = f"https://github.com/{REPOSITORY}/releases"
_VERSION = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_DIGEST = re.compile(r"sha256:([0-9a-fA-F]{64})")


@dataclass(frozen=True)
class Release:
    tag: str
    page: str
    name: str = ""
    url: str = ""
    size: int = 0
    digest: str = ""


def installed_version():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def latest_update(client):
    response = client.get(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "SubtitleForEveryone"},
    )
    if response.status_code == 404:
        return "unavailable", None
    response.raise_for_status()
    release = response.json()
    if not isinstance(release, dict):
        raise ValueError("Invalid GitHub response")
    tag = release.get("tag_name", "")
    latest = _VERSION.fullmatch(tag) if isinstance(tag, str) else None
    current = _VERSION.fullmatch(installed_version())
    if not latest or not current or release.get("draft") or release.get("prerelease"):
        raise ValueError("Invalid stable release")
    if tuple(map(int, latest.groups())) <= tuple(map(int, current.groups())):
        return "current", None
    version = tag.removeprefix("v")
    name = f"SubtitleForEveryone-Setup-{version}-x64.exe"
    url = f"{RELEASES}/download/{tag}/{name}"
    page = f"{RELEASES}/tag/{tag}"
    assets = release.get("assets")
    for asset in assets if isinstance(assets, list) else ():
        if not isinstance(asset, dict) or asset.get("name") != name or asset.get("state") != "uploaded":
            continue
        size = asset.get("size")
        digest = _DIGEST.fullmatch(str(asset.get("digest") or ""))
        if (asset.get("browser_download_url") == url and type(size) is int
                and 0 < size < 2 * 1024**3 and digest):
            return "available", Release(tag, page, name, url, size, digest[1].lower())
    return "available", Release(tag, page)
