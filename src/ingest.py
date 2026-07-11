"""Ingest: pull raw GitHub JSON for the V-Sekai orgs into raw/*.parquet.

All persisted data lives in parquet. Raw API objects are stored verbatim as a JSON
string in a `payload` column (raw/orgs.parquet, raw/repos.parquet, raw/issues.parquet);
capture metadata is raw/snapshot.parquet. normalize.py and study.py read ONLY from
these parquet files, so downstream runs are deterministic against a fixed snapshot.

Endpoints (public data only):
  - GET /orgs/{org}
  - GET /orgs/{org}/repos            (paginated, type=public)
  - GET /search/issues?q=org:{org} state:open type:issue   (paginated)
"""

from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime, timezone

import httpx
import polars as pl

import common as c


def _log(msg: str) -> None:
    print(f"[ingest] {msg}", file=sys.stderr)


def _paginate(client: httpx.Client, url: str, params: dict) -> list[dict]:
    """Follow RFC-5988 `Link: rel=next` pagination, returning all items."""
    items: list[dict] = []
    params = dict(params, per_page=100)
    page_url: str | None = url
    while page_url:
        resp = client.get(page_url, params=params if page_url == url else None)
        resp.raise_for_status()
        payload = resp.json()
        batch = payload["items"] if isinstance(payload, dict) else payload
        items.extend(batch)
        page_url = resp.links.get("next", {}).get("url")
        if page_url:  # search API allows ~30 req/min; be gentle
            time.sleep(0.4)
    return items


def _write_raw(name: str, rows: list[dict]) -> None:
    """Persist raw API objects as a single JSON `payload` column in parquet."""
    df = pl.DataFrame({"payload": [json.dumps(r, ensure_ascii=False) for r in rows]})
    df.write_parquet(c.RAW / f"{name}.parquet")
    _log(f"wrote {len(rows):>5} -> raw/{name}.parquet")


def main() -> None:
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    orgs_raw: list[dict] = []
    repos_raw: list[dict] = []
    issues_raw: list[dict] = []

    with httpx.Client(
        base_url=c.GITHUB_API, headers=c.auth_headers(), timeout=30.0
    ) as client:
        for org in c.ORGS:
            _log(f"org {org}")
            r = client.get(f"/orgs/{org}")
            r.raise_for_status()
            orgs_raw.append(r.json())

            repos = _paginate(client, f"/orgs/{org}/repos", {"type": "public"})
            repos_raw.extend(repos)
            _log(f"  repos: {len(repos)}")

            issues = _paginate(
                client, "/search/issues", {"q": f"org:{org} state:open type:issue"}
            )
            issues_raw.extend(issues)
            _log(f"  open issues: {len(issues)}")

    _write_raw("orgs", orgs_raw)
    _write_raw("repos", repos_raw)
    _write_raw("issues", issues_raw)

    pl.DataFrame(
        [
            {
                "snapshot_uuid": c.snapshot_uuid(captured_at),
                "captured_at": captured_at,
                "orgs": ", ".join(c.ORGS),
                "query": "org:{org} state:open type:issue  (public repos, type=issue)",
                "counts": json.dumps(
                    {"orgs": len(orgs_raw), "repos": len(repos_raw), "issues": len(issues_raw)}
                ),
                "tool_versions": json.dumps(
                    {
                        "python": platform.python_version(),
                        "httpx": httpx.__version__,
                        "polars": pl.__version__,
                        "platform": platform.platform(),
                    }
                ),
            }
        ]
    ).write_parquet(c.RAW / "snapshot.parquet")
    _log(f"snapshot {c.snapshot_uuid(captured_at)} @ {captured_at}")
    _log("done")


if __name__ == "__main__":
    main()
