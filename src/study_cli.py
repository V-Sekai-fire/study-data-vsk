"""Study (Burrito readiness): rank repos by how close they are to a shippable Elixir
binary, framed as hexagonal ports and adapters. The core is the domain code (C/C++
sim, Python ML, Elixir lib); the escript is the driving adapter; Burrito/hex.pm is the
distribution adapter. Three routes reach one binary: elixir (native), c (NIF/port),
python (pythonx -> hex.pm).

Reads lake/repo_packaging + lake/repos, writes lake/cli_readiness.parquet and
reports/burrito_candidates.md. "now" is the snapshot time, so ranking is reproducible.
"""

from __future__ import annotations

import sys
from datetime import datetime

import polars as pl

import common as c

# The joyful finish-today picks, chosen from the top burrito-ready candidates for
# being end-to-end usable avatar tools that are nearly done (see report rationale).
PRIMARY = "V-Sekai-fire/cloth-fit"
FALLBACK = "V-Sekai/TOOL_cloth_dynamics"


def _log(msg: str) -> None:
    print(f"[study-cli] {msg}", file=sys.stderr)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _score(r: dict, now: datetime) -> tuple[int, list[str]]:
    s = 0
    why: list[str] = []
    route, cli = r["route"], r["is_cli"]

    if route == "elixir" and cli:
        s += 6
        why.append("escript/Unifex CLI adapter present")
    elif route == "elixir":
        s += 3
        why.append("Elixir core, add an escript adapter")
    elif route == "c" and cli:
        s += 4
        why.append("C/C++ executable core, wrap via NIF/port")
    elif route == "python" and cli:
        s += 3
        why.append("Python CLI entrypoint")

    if r["has_unifex"]:
        s += 3
        why.append("native core already bound via Unifex")
    if r["has_burrito"]:
        s += 3
        why.append("Burrito distribution configured")
    if r["is_ml"]:
        s += 4
        why.append("ML core, ship via pythonx and hex.pm")
    if not (r["is_web"] or r["is_server"]):
        s += 2
    else:
        s -= 5
        why.append("web/server driving adapter, not a CLI")
    if r["description"]:
        s += 1

    pushed = r.get("pushed_at")
    if pushed:
        days = (now - _dt(pushed)).days
        if days < 180:
            s += 2
        elif days < 365:
            s += 1
    return s, why


def main() -> None:
    pkg = pl.read_parquet(c.LAKE / "repo_packaging.parquet")
    repos = pl.read_parquet(c.LAKE / "repos.parquet").select(
        "repo_uuid", "full_name", "pushed_at", "open_issues_count", "stars"
    )
    snap = pl.read_parquet(c.LAKE / "snapshot.parquet")
    now = _dt(snap["captured_at"][0])

    df = pkg.filter(pl.col("has_manifest")).join(repos, on="repo_uuid", how="left")

    scored = []
    for r in df.to_dicts():
        s, why = _score(r, now)
        scored.append(
            {
                "repo_uuid": r["repo_uuid"],
                "repo": r["full_name"],
                "route": r["route"],
                "language": r["language"],
                "is_cli": r["is_cli"],
                "is_ml": r["is_ml"],
                "has_burrito": r["has_burrito"],
                "has_unifex": r["has_unifex"],
                "pushed": (r["pushed_at"] or "")[:10],
                "open": r["open_issues_count"],
                "evidence": r["cli_evidence"],
                "burrito_readiness": s,
                "reasons": " · ".join(why),
            }
        )

    scored.sort(key=lambda x: (-x["burrito_readiness"], x["pushed"]), reverse=False)
    scored.sort(key=lambda x: -x["burrito_readiness"])
    for i, x in enumerate(scored, 1):
        x["rank"] = i

    pl.DataFrame(scored).select(
        "repo_uuid", "rank", "route", "burrito_readiness", "reasons"
    ).write_parquet(c.LAKE / "cli_readiness.parquet")
    _log(f"scored {len(scored)} repos -> lake/cli_readiness.parquet")

    _write_report(scored, snap)


def _by_name(scored: list[dict], name: str) -> dict | None:
    return next((x for x in scored if x["repo"] == name), None)


def _write_report(scored: list[dict], snap: pl.DataFrame) -> None:
    primary = _by_name(scored, PRIMARY) or (scored[0] if scored else None)
    fallback = _by_name(scored, FALLBACK) or (scored[1] if len(scored) > 1 else None)

    lines: list[str] = []
    lines.append("# V-Sekai — Burrito-ready candidates\n")
    lines.append(
        f"_Snapshot `{snap['captured_at'][0]}` · {len(scored)} Elixir/C/C++/Python repos scored for "
        "how close they are to a shippable Elixir binary. Hexagonal read: domain core, an escript "
        "driving adapter, and a Burrito/hex.pm distribution adapter._\n"
    )

    lines.append("## Chosen finish-today tasks\n")
    lines.append(
        "Picked from the top burrito-ready candidates for being end-to-end usable avatar tools "
        "that are nearly done and bring closure.\n"
    )
    if primary:
        lines.append(f"### Primary: [{primary['repo']}](https://github.com/{primary['repo']})\n")
        lines.append(
            f"Route {primary['route']}, score {primary['burrito_readiness']}, "
            f"{primary['open']} open issue(s), pushed {primary['pushed']}. "
            f"{primary['evidence']}. Finish the CLI adapter and add a Burrito release to ship a "
            "cross-platform binary that dresses an avatar.\n"
        )
    if fallback:
        lines.append(f"### Fallback: [{fallback['repo']}](https://github.com/{fallback['repo']})\n")
        lines.append(
            f"Route {fallback['route']}, score {fallback['burrito_readiness']}, "
            f"{fallback['open']} open issue(s), pushed {fallback['pushed']}. "
            f"{fallback['evidence']}. Independent backup with the same avatar-cloth payoff.\n"
        )

    lines.append("## Top 20 burrito-ready repos\n")
    lines.append("| Rank | Repo | Route | Lang | CLI | ML | Burrito | Pushed | Score | Why |")
    lines.append("|------|------|-------|------|-----|----|---------|--------|-------|-----|")
    for x in scored[:20]:
        lines.append(
            f"| {x['rank']} | `{x['repo']}` | {x['route'] or '-'} | {x['language']} "
            f"| {'yes' if x['is_cli'] else 'no'} | {'yes' if x['is_ml'] else 'no'} "
            f"| {'yes' if x['has_burrito'] else 'no'} | {x['pushed']} "
            f"| **{x['burrito_readiness']}** | {x['reasons']} |"
        )
    lines.append("")
    lines.append("### Score model\n")
    lines.append(
        "- driving adapter: elixir escript/Unifex CLI (+6); elixir library, add escript (+3); "
        "C/C++ executable (+4); Python CLI entrypoint (+3).\n"
        "- native core bound via Unifex (+3); Burrito distribution configured (+3).\n"
        "- ML core, ship via pythonx and hex.pm (+4).\n"
        "- self-contained core, not web/server (+2); alive: pushed <6mo (+2) / <1y (+1); "
        "has description (+1); web/server driving adapter (−5).\n"
    )
    (c.REPORTS / "burrito_candidates.md").write_text("\n".join(lines), encoding="utf-8")
    _log(f"wrote reports/burrito_candidates.md (primary={PRIMARY}, fallback={FALLBACK})")


if __name__ == "__main__":
    main()
