"""Normalize: raw/ JSON -> lake/*.parquet in Essential Tuple Normal Form.

Entity relations (candidate key = *_uuid, plus retained natural key):
  snapshot, orgs, repos, users, issues, labels
Junction relations (all-key -> 5NF -> ETNF):
  issue_labels, repo_topics

Reads ONLY from raw/, so output is deterministic against a fixed snapshot.
Runs PK-uniqueness and FK-integrity checks; `--validate-only` re-checks an existing lake.
"""

from __future__ import annotations

import json
import sys

import polars as pl

import common as c


def _log(msg: str) -> None:
    print(f"[normalize] {msg}", file=sys.stderr)


def _read_raw(name: str) -> list[dict]:
    """Load raw API objects from a parquet `payload` (JSON string) column."""
    path = c.RAW / f"{name}.parquet"
    if not path.exists():
        raise SystemExit(f"missing {path}; run `pixi run ingest` first.")
    return [json.loads(p) for p in pl.read_parquet(path)["payload"].to_list()]


def _slen(v) -> int:
    return len(v) if isinstance(v, str) else 0


# ── Builders ─────────────────────────────────────────────────────────────────


def build_snapshot() -> pl.DataFrame:
    return pl.read_parquet(c.RAW / "snapshot.parquet")


def build_orgs(orgs_raw: list[dict]) -> pl.DataFrame:
    rows = [
        {
            "org_uuid": c.org_uuid(o["login"]),
            "org_login": o["login"],
            "name": o.get("name"),
            "public_repos": o.get("public_repos"),
            "created_at": o.get("created_at"),
        }
        for o in orgs_raw
    ]
    return pl.DataFrame(rows)


def build_repos(repos_raw: list[dict]) -> pl.DataFrame:
    rows = []
    for r in repos_raw:
        full_name = r["full_name"]
        rows.append(
            {
                "repo_uuid": c.repo_uuid(full_name),
                "org_uuid": c.org_uuid(r["owner"]["login"]),
                "name": r["name"],
                "full_name": full_name,
                "fork": bool(r.get("fork", False)),
                "archived": bool(r.get("archived", False)),
                "disabled": bool(r.get("disabled", False)),
                "stars": r.get("stargazers_count", 0),
                "forks": r.get("forks_count", 0),
                "open_issues_count": r.get("open_issues_count", 0),
                "watchers": r.get("watchers_count", 0),
                "size_kb": r.get("size", 0),
                "language": r.get("language"),
                "license_spdx": (r.get("license") or {}).get("spdx_id"),
                "default_branch": r.get("default_branch"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "pushed_at": r.get("pushed_at"),
                "description_len": _slen(r.get("description")),
                "homepage_present": bool((r.get("homepage") or "").strip()),
            }
        )
    return pl.DataFrame(rows)


def _repo_full_name(issue: dict) -> str:
    # search/issues gives repository_url = https://api.github.com/repos/{owner}/{repo}
    return issue["repository_url"].split("/repos/", 1)[1]


def build_users(issues_raw: list[dict]) -> pl.DataFrame:
    seen: dict[str, dict] = {}
    for it in issues_raw:
        u = it.get("user") or {}
        login = u.get("login")
        if login and login not in seen:
            seen[login] = {
                "user_uuid": c.user_uuid(login),
                "user_login": login,
                "user_type": u.get("type"),
            }
    return pl.DataFrame(list(seen.values()))


def build_issues(issues_raw: list[dict]) -> pl.DataFrame:
    rows = []
    for it in issues_raw:
        if "pull_request" in it:  # defensive: exclude PRs
            continue
        full_name = _repo_full_name(it)
        u = it.get("user") or {}
        reactions = it.get("reactions") or {}
        rows.append(
            {
                "issue_uuid": c.issue_uuid(full_name, it["number"]),
                "repo_uuid": c.repo_uuid(full_name),
                "number": it["number"],
                "title": it.get("title", ""),
                "state": it.get("state"),
                "comments": it.get("comments", 0),
                "reactions_total": reactions.get("total_count", 0),
                "author_uuid": c.user_uuid(u["login"]) if u.get("login") else None,
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "body_len": _slen(it.get("body")),
                "locked": bool(it.get("locked", False)),
                "html_url": it.get("html_url"),
            }
        )
    return pl.DataFrame(rows)


def build_labels_and_bridge(
    issues_raw: list[dict],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    labels: dict[str, dict] = {}
    bridge: set[tuple[str, str]] = set()
    for it in issues_raw:
        if "pull_request" in it:
            continue
        full_name = _repo_full_name(it)
        iu = c.issue_uuid(full_name, it["number"])
        for lb in it.get("labels", []):
            name = lb.get("name")
            if not name:
                continue
            lu = c.label_uuid(full_name, name)
            labels.setdefault(
                lu,
                {
                    "label_uuid": lu,
                    "repo_uuid": c.repo_uuid(full_name),
                    "name": name,
                    "color": lb.get("color"),
                    "description": lb.get("description"),
                },
            )
            bridge.add((iu, lu))
    labels_df = pl.DataFrame(list(labels.values())) if labels else pl.DataFrame(
        schema={"label_uuid": pl.Utf8, "repo_uuid": pl.Utf8, "name": pl.Utf8,
                "color": pl.Utf8, "description": pl.Utf8}
    )
    bridge_df = pl.DataFrame(
        [{"issue_uuid": i, "label_uuid": l} for i, l in sorted(bridge)]
    ) if bridge else pl.DataFrame(schema={"issue_uuid": pl.Utf8, "label_uuid": pl.Utf8})
    return labels_df, bridge_df


def build_decisions() -> pl.DataFrame:
    """MADR decision records from the manuals repos (raw/decisions.parquet).

    Entity relation, PK decision_uuid; repo_uuid FK -> repos. A `status: proposed`
    decision is an open todo. Absent if `pixi run ingest-manuals` hasn't run.
    """
    path = c.RAW / "decisions.parquet"
    schema = {
        "decision_uuid": pl.Utf8, "repo_uuid": pl.Utf8, "path": pl.Utf8,
        "title": pl.Utf8, "date": pl.Utf8, "status": pl.Utf8, "tier": pl.Utf8,
        "raw_len": pl.Int64, "has_frontmatter": pl.Boolean,
    }
    if not path.exists():
        return pl.DataFrame(schema=schema)
    raw = pl.read_parquet(path)
    rows = [
        {
            "decision_uuid": c.decision_uuid(r["repo_full_name"], r["path"]),
            "repo_uuid": c.repo_uuid(r["repo_full_name"]),
            "path": r["path"],
            "title": r["title"],
            "date": r["date"],
            "status": r["status"],
            "tier": r["tier"],
            "raw_len": r["raw_len"],
            "has_frontmatter": r["has_frontmatter"],
        }
        for r in raw.to_dicts()
    ]
    return pl.DataFrame(rows, schema=schema)


def build_repo_packaging() -> pl.DataFrame:
    """Burrito-packaging shape per Elixir/C/C++/Python repo (raw/packaging.parquet).

    Entity relation, PK decision by repo_uuid; FK -> repos. 1:1 subset of repos.
    Absent if `pixi run ingest-packaging` has not run.
    """
    path = c.RAW / "packaging.parquet"
    schema = {
        "repo_uuid": pl.Utf8, "full_name": pl.Utf8, "language": pl.Utf8, "route": pl.Utf8,
        "manifest": pl.Utf8, "has_manifest": pl.Boolean, "is_cli": pl.Boolean,
        "cli_evidence": pl.Utf8, "has_elixir_subcli": pl.Boolean, "subcli_dir": pl.Utf8,
        "has_unifex": pl.Boolean, "is_ml": pl.Boolean, "is_web": pl.Boolean,
        "is_server": pl.Boolean, "has_burrito": pl.Boolean, "entry": pl.Utf8,
        "description": pl.Utf8,
    }
    if not path.exists():
        return pl.DataFrame(schema=schema)
    raw = pl.read_parquet(path)
    rows = [
        {
            "repo_uuid": c.repo_uuid(r["repo_full_name"]),
            "full_name": r["repo_full_name"],
            "language": r["language"], "route": r["route"], "manifest": r["manifest"],
            "has_manifest": r["has_manifest"], "is_cli": r["is_cli"],
            "cli_evidence": r["cli_evidence"], "has_elixir_subcli": r["has_elixir_subcli"],
            "subcli_dir": r["subcli_dir"], "has_unifex": r["has_unifex"], "is_ml": r["is_ml"],
            "is_web": r["is_web"], "is_server": r["is_server"], "has_burrito": r["has_burrito"],
            "entry": r["entry"], "description": r["description"],
        }
        for r in raw.to_dicts()
    ]
    return pl.DataFrame(rows, schema=schema)


def build_repo_topics(repos_raw: list[dict]) -> pl.DataFrame:
    rows = []
    for r in repos_raw:
        for topic in r.get("topics", []) or []:
            rows.append({"repo_uuid": c.repo_uuid(r["full_name"]), "topic": topic})
    return pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"repo_uuid": pl.Utf8, "topic": pl.Utf8}
    )


# ── Integrity checks ─────────────────────────────────────────────────────────


def _check_pk(df: pl.DataFrame, cols: list[str], table: str) -> list[str]:
    if df.height == 0:
        return []
    dups = df.height - df.select(cols).unique().height
    return [f"{table}: PK {cols} has {dups} duplicate rows"] if dups else []


def _check_fk(
    child: pl.DataFrame, col: str, parent: pl.DataFrame, pcol: str, table: str
) -> list[str]:
    if child.height == 0:
        return []
    vals = child.filter(pl.col(col).is_not_null()).select(col).unique()
    valid = parent.select(pl.col(pcol).alias(col))
    orphans = vals.join(valid, on=col, how="anti").height
    return [f"{table}.{col} -> {pcol}: {orphans} orphans"] if orphans else []


def validate(tables: dict[str, pl.DataFrame]) -> list[str]:
    errs: list[str] = []
    errs += _check_pk(tables["orgs"], ["org_uuid"], "orgs")
    errs += _check_pk(tables["repos"], ["repo_uuid"], "repos")
    errs += _check_pk(tables["users"], ["user_uuid"], "users")
    errs += _check_pk(tables["issues"], ["issue_uuid"], "issues")
    errs += _check_pk(tables["labels"], ["label_uuid"], "labels")
    errs += _check_pk(tables["issue_labels"], ["issue_uuid", "label_uuid"], "issue_labels")
    errs += _check_pk(tables["repo_topics"], ["repo_uuid", "topic"], "repo_topics")

    errs += _check_fk(tables["repos"], "org_uuid", tables["orgs"], "org_uuid", "repos")
    errs += _check_fk(tables["issues"], "repo_uuid", tables["repos"], "repo_uuid", "issues")
    errs += _check_fk(tables["issues"], "author_uuid", tables["users"], "user_uuid", "issues")
    errs += _check_fk(tables["labels"], "repo_uuid", tables["repos"], "repo_uuid", "labels")
    errs += _check_fk(tables["issue_labels"], "issue_uuid", tables["issues"], "issue_uuid", "issue_labels")
    errs += _check_fk(tables["issue_labels"], "label_uuid", tables["labels"], "label_uuid", "issue_labels")
    errs += _check_fk(tables["repo_topics"], "repo_uuid", tables["repos"], "repo_uuid", "repo_topics")
    if "decisions" in tables:
        errs += _check_pk(tables["decisions"], ["decision_uuid"], "decisions")
        errs += _check_fk(tables["decisions"], "repo_uuid", tables["repos"], "repo_uuid", "decisions")
    if "repo_packaging" in tables:
        errs += _check_pk(tables["repo_packaging"], ["repo_uuid"], "repo_packaging")
        errs += _check_fk(tables["repo_packaging"], "repo_uuid", tables["repos"], "repo_uuid", "repo_packaging")
    return errs


def _load_lake() -> dict[str, pl.DataFrame]:
    names = ["orgs", "repos", "users", "issues", "labels", "issue_labels",
             "repo_topics", "decisions", "repo_packaging"]
    return {
        n: pl.read_parquet(c.LAKE / f"{n}.parquet")
        for n in names
        if (c.LAKE / f"{n}.parquet").exists()
    }


def main() -> None:
    validate_only = "--validate-only" in sys.argv

    if validate_only:
        tables = _load_lake()
    else:
        orgs_raw = _read_raw("orgs")
        repos_raw = _read_raw("repos")
        issues_raw = _read_raw("issues")

        # Public-only scope: keep issues whose repo is in the public repos listing
        # (search may surface private-repo issues via the authed token) and drop PRs.
        public_names = {r["full_name"] for r in repos_raw}
        issues_pub = [
            it
            for it in issues_raw
            if "pull_request" not in it and _repo_full_name(it) in public_names
        ]
        dropped = len(issues_raw) - len(issues_pub)
        if dropped:
            _log(f"dropped {dropped} non-public/PR issues (public-only scope)")

        labels_df, issue_labels_df = build_labels_and_bridge(issues_pub)
        tables = {
            "snapshot": build_snapshot(),
            "orgs": build_orgs(orgs_raw),
            "repos": build_repos(repos_raw),
            "users": build_users(issues_pub),
            "issues": build_issues(issues_pub),
            "labels": labels_df,
            "issue_labels": issue_labels_df,
            "repo_topics": build_repo_topics(repos_raw),
            "decisions": build_decisions(),
            "repo_packaging": build_repo_packaging(),
        }
        for name, df in tables.items():
            df.write_parquet(c.LAKE / f"{name}.parquet")
            _log(f"wrote {df.height:>5} rows -> lake/{name}.parquet")

    errs = validate(tables if validate_only else {k: v for k, v in tables.items() if k != "snapshot"})
    if errs:
        for e in errs:
            _log(f"FAIL {e}")
        raise SystemExit(1)
    _log("integrity OK: PKs unique, FKs resolve")


if __name__ == "__main__":
    main()
