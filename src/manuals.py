"""Ingest manuals: the V-Sekai manuals repos track decisions (MADRs) whose
`status:` frontmatter is effectively a todo list. Pull each repo's tarball in memory,
parse the frontmatter of decisions/*.md, and persist to raw/decisions.parquet.

Only parquet is written; the tarball is processed in memory and never stored.
"""

from __future__ import annotations

import io
import sys
import tarfile

import httpx
import polars as pl

import common as c

# (full_name) — default branch resolved from the API so no branch is hardcoded.
MANUALS = ["V-Sekai/manuals", "v-sekai-multiplayer-fabric/multiplayer-fabric-manuals"]

FRONT_KEYS = ("title", "date", "status", "tier")


def _log(msg: str) -> None:
    print(f"[manuals] {msg}", file=sys.stderr)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Minimal flat-scalar YAML frontmatter parser (title/date/status/tier)."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        if key in FRONT_KEYS:
            out[key] = val.strip().strip("'\"")
    return out


def _decisions_from_tarball(client: httpx.Client, full_name: str) -> list[dict]:
    repo = client.get(f"/repos/{full_name}").json()
    branch = repo.get("default_branch", "main")
    tar_bytes = client.get(f"/repos/{full_name}/tarball/{branch}", timeout=120.0).content
    rows: list[dict] = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            # paths look like "{owner}-{repo}-{sha}/decisions/xxx.md"
            parts = member.name.split("/", 1)
            if len(parts) != 2:
                continue
            rel = parts[1]
            if not (rel.startswith("decisions/") and rel.endswith(".md")):
                continue
            if rel.count("/") != 1:  # only top-level decisions/*.md
                continue
            fh = tar.extractfile(member)
            if fh is None:
                continue
            text = fh.read().decode("utf-8", errors="replace")
            fm = _parse_frontmatter(text)
            rows.append(
                {
                    "repo_full_name": full_name,
                    "path": rel,
                    "title": fm.get("title") or _title_fallback(text, rel),
                    "date": fm.get("date"),
                    "status": (fm.get("status") or "").lower() or None,
                    "tier": fm.get("tier"),
                    "raw_len": len(text),
                    "has_frontmatter": bool(fm),
                }
            )
    return rows


def _title_fallback(text: str, rel: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return rel.rsplit("/", 1)[-1][:-3]


def main() -> None:
    all_rows: list[dict] = []
    with httpx.Client(
        base_url=c.GITHUB_API, headers=c.auth_headers(), timeout=60.0, follow_redirects=True
    ) as client:
        for full_name in MANUALS:
            rows = _decisions_from_tarball(client, full_name)
            all_rows.extend(rows)
            _log(f"{full_name}: {len(rows)} decisions")

    schema = {
        "repo_full_name": pl.Utf8, "path": pl.Utf8, "title": pl.Utf8, "date": pl.Utf8,
        "status": pl.Utf8, "tier": pl.Utf8, "raw_len": pl.Int64, "has_frontmatter": pl.Boolean,
    }
    df = pl.DataFrame(all_rows, schema=schema)
    df.write_parquet(c.RAW / "decisions.parquet")
    _log(f"wrote {len(all_rows)} -> raw/decisions.parquet")


if __name__ == "__main__":
    main()
