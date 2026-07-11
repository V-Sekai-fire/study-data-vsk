"""Shared config, paths, HTTP client, and deterministic UUIDv5 key helpers.

Keys in the datalake are UUIDv5 (namespaced SHA-1 of a natural key) so they are
reproducible and stable across snapshots without depending on GitHub's integer ids.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

# ── Study configuration ──────────────────────────────────────────────────────

ORGS = ["V-Sekai", "V-Sekai-fire", "V-Sekai-multiplayer-fabric"]

GITHUB_API = "https://api.github.com"
USER_AGENT = "study-data-vsk (chibifire.com)"

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
LAKE = ROOT / "lake"
REPORTS = ROOT / "reports"
for _d in (RAW, LAKE, REPORTS):
    _d.mkdir(exist_ok=True)

# ── Deterministic UUIDv5 keys ────────────────────────────────────────────────
# Fixed namespace: hash of a project URL under the DNS namespace. Pure function
# of its input — no randomness or time — so every run yields identical keys.

NS = uuid.uuid5(uuid.NAMESPACE_URL, "chibifire.com/study-data-vsk")


def _uuid(kind: str, natural_key: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{natural_key}"))


def org_uuid(login: str) -> str:
    return _uuid("org", login)


def repo_uuid(full_name: str) -> str:
    return _uuid("repo", full_name)


def user_uuid(login: str) -> str:
    return _uuid("user", login)


def issue_uuid(full_name: str, number: int) -> str:
    return _uuid("issue", f"{full_name}#{number}")


def label_uuid(full_name: str, label_name: str) -> str:
    return _uuid("label", f"{full_name}:{label_name}")


def snapshot_uuid(captured_at: str) -> str:
    return _uuid("snapshot", captured_at)


def decision_uuid(full_name: str, path: str) -> str:
    return _uuid("decision", f"{full_name}:{path}")


# ── GitHub auth ──────────────────────────────────────────────────────────────


def github_token() -> str:
    """Token from GITHUB_TOKEN, else the local `gh` CLI login. No secret is stored."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        tok = out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(
            "No GitHub token: set GITHUB_TOKEN or run `gh auth login`."
        ) from exc
    if not tok:
        raise SystemExit("No GitHub token: set GITHUB_TOKEN or run `gh auth login`.")
    return tok


def auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {github_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
