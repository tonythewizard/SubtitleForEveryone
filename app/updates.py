"""Read stable public releases from the project's GitHub repository."""
from pathlib import Path
import re
import sys

import httpx

REPOSITORY = "tonythewizard/SubtitleForEveryone"
RELEASES = f"https://github.com/{REPOSITORY}/releases"
_VERSION = re.compile(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def installed_version():
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return (root / "VERSION").read_text(encoding="utf-8").strip()


def latest_update(client):
    response = client.get(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "SubtitleForEveryone"},
    )
    if response.status_code == 404:
        return "unavailable", ""
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
        return "current", ""
    return "available", tag
