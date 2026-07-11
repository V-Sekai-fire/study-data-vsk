"""Study: rank open issues by a 'finish-it-today' joy score and write a report.

Joy (per chibifire.com): finishing off preexisting, long-haunting work that can be
completed today to a high level of polish. Score = finishability + haunting + doability.

Reads the lake, writes lake/joy_scores.parquet and reports/finishable_tasks.md.
"now" is the snapshot capture time (not wall-clock), so the ranking is reproducible.
"""

from __future__ import annotations

import sys
from datetime import datetime

import polars as pl

import common as c

# ── Tunable weights ──────────────────────────────────────────────────────────

FINISH_WORDS = ("finish", "polish", "cleanup", "clean up", "final", "remaining", "last", "todo")
EPIC_WORDS = ("epic", "tracking", "meta ", "roadmap", "umbrella", "megaissue", "mega issue")
LABEL_BONUS = {"good first issue", "help wanted", "documentation", "docs", "polish", "cleanup", "easy"}
LABEL_PENALTY = {"epic", "needs-design", "needs design", "needs-info", "discussion"}
LABEL_EXCLUDE = {"blocked", "wontfix", "won't fix", "invalid", "duplicate"}
# Elixir affinity — bump tasks doable via Elixir/BEAM.
ELIXIR_WORDS = ("elixir", "phoenix", "beam", "erlang", " otp", "ecto", "liveview", "mix ", "genserver")
# CLI-shaped tasks: any CLI can be shipped as an Elixir binary via Burrito.
CLI_WORDS = (
    "cli", "command-line", "command line", "convert ", "export", "import ", "generate",
    "script", "packaging", "batch", "automate", "automated test", "parser", "encode", "decode",
)
CLI_LANGS = {"Shell", "Python", "Ruby", "Perl"}


def _log(msg: str) -> None:
    print(f"[study] {msg}", file=sys.stderr)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _finishability(oic: int) -> tuple[int, str | None]:
    if oic == 1:
        return 6, "last open issue in the repo, so closing it finishes the repo"
    if oic == 2:
        return 4, "1 of 2 open issues, repo nearly done"
    if oic == 3:
        return 2, "1 of 3 open issues"
    if oic <= 5:
        return 1, "few open issues in the repo"
    return 0, None


def _haunting(age_days: int, stale_days: int) -> tuple[int, str | None]:
    if age_days > 730:
        base, why = 4, f"haunting for {age_days // 365}y"
    elif age_days > 365:
        base, why = 3, f"open ~{age_days // 365}y"
    elif age_days > 180:
        base, why = 2, "open >6 months"
    elif age_days > 90:
        base, why = 1, "open >3 months"
    else:
        base, why = 0, None
    if stale_days > 365:
        base += 1
        why = (why + ", untouched >1y") if why else "untouched >1y"
    return base, why


def _doability(row: dict, labels: set[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    comments = row["comments"]
    if comments <= 1:
        score += 2
        reasons.append("little discussion")
    elif comments <= 3:
        score += 1
    if row["body_len"] < 280:
        score += 1
        reasons.append("short body")
    title = (row["title"] or "").lower()
    if any(w in title for w in FINISH_WORDS):
        score += 2
        reasons.append("title reads like a finishing task")
    if any(w in title for w in EPIC_WORDS):
        score -= 4
        reasons.append("looks like an epic/tracker")
    if labels & LABEL_BONUS:
        score += 2
        reasons.append("labelled " + "/".join(sorted(labels & LABEL_BONUS)))
    if labels & LABEL_PENALTY:
        score -= 3
        reasons.append("labelled " + "/".join(sorted(labels & LABEL_PENALTY)))
    return score, reasons


def _elixir(row: dict) -> tuple[int, str | None]:
    """Bump tasks doable via Elixir/BEAM, incl. CLI tasks shippable as an
    Elixir binary with Burrito. Repo language + Elixir/CLI keywords in the title."""
    score = 0
    parts: list[str] = []
    lang = row.get("language") or ""
    title = (row["title"] or "").lower()
    if lang == "Elixir":
        score += 4
        parts.append("Elixir repo")
    if any(w in title for w in ELIXIR_WORDS):
        score += 3
        parts.append("Elixir-flavoured")
    cli = any(w in title for w in CLI_WORDS) or lang in CLI_LANGS
    if cli and lang != "Elixir":
        score += 2
        parts.append("CLI → Elixir via Burrito")
    return score, (" · ".join(parts) if parts else None)


def main() -> None:
    issues = pl.read_parquet(c.LAKE / "issues.parquet")
    repos = pl.read_parquet(c.LAKE / "repos.parquet")
    labels = pl.read_parquet(c.LAKE / "labels.parquet")
    issue_labels = pl.read_parquet(c.LAKE / "issue_labels.parquet")
    snap = pl.read_parquet(c.LAKE / "snapshot.parquet")
    now = _dt(snap["captured_at"][0])

    # labels per issue (lowercased names)
    lab = (
        issue_labels.join(labels.select("label_uuid", "name"), on="label_uuid", how="left")
        .group_by("issue_uuid")
        .agg(pl.col("name").str.to_lowercase().alias("labels"))
    )

    df = (
        issues.join(
            repos.select(
                "repo_uuid", "full_name", "archived", "fork", "open_issues_count", "language"
            ),
            on="repo_uuid",
            how="left",
        )
        .join(lab, on="issue_uuid", how="left")
    )

    rows = df.to_dicts()
    scored = []
    for r in rows:
        labs = set(r.get("labels") or [])
        # hard filters
        if r["archived"] or r["fork"] or r["state"] != "open":
            continue
        if labs & LABEL_EXCLUDE:
            continue
        age_days = (now - _dt(r["created_at"])).days
        stale_days = (now - _dt(r["updated_at"])).days
        fin, fin_why = _finishability(r["open_issues_count"])
        ha, ha_why = _haunting(age_days, stale_days)
        do, do_why = _doability(r, labs)
        el, el_why = _elixir(r)
        total = fin + ha + do + el
        reasons = [x for x in (fin_why, ha_why) if x] + do_why + ([el_why] if el_why else [])
        scored.append(
            {
                "issue_uuid": r["issue_uuid"],
                "repo": r["full_name"],
                "number": r["number"],
                "title": r["title"],
                "url": r["html_url"],
                "open_issues_count": r["open_issues_count"],
                "age_days": age_days,
                "comments": r["comments"],
                "labels_str": ", ".join(sorted(labs)) if labs else "",
                "language": r.get("language"),
                "finishability": fin,
                "haunting": ha,
                "doability": do,
                "elixir": el,
                "total_score": total,
                "reasons": " · ".join(reasons),
            }
        )

    scored.sort(key=lambda x: (-x["total_score"], -x["elixir"], -x["finishability"], -x["age_days"]))
    for i, s in enumerate(scored, 1):
        s["rank"] = i

    out = pl.DataFrame(scored)
    out.select(
        "issue_uuid", "rank", "finishability", "haunting", "doability", "elixir",
        "total_score", "reasons",
    ).write_parquet(c.LAKE / "joy_scores.parquet")
    _log(f"scored {len(scored)} candidate issues -> lake/joy_scores.parquet")

    decisions = _load_open_decisions()
    _write_report(scored, now, snap, decisions)


# explicit MADR statuses that mean "still an open todo" (legacy free-form docs
# without frontmatter are excluded — they are historical records, not todos).
OPEN_DECISION_STATUS = {"proposed", "draft", "wip", "idea"}


def _load_open_decisions() -> list[dict]:
    path = c.LAKE / "decisions.parquet"
    if not path.exists():
        return []
    repos = pl.read_parquet(c.LAKE / "repos.parquet").select("repo_uuid", "full_name")
    df = pl.read_parquet(path).join(repos, on="repo_uuid", how="left")
    rows = [
        {**r, "_repo": r["full_name"]}
        for r in df.to_dicts()
        if (r["status"] or "") in OPEN_DECISION_STATUS and "template" not in r["path"].lower()
    ]
    # oldest first = most haunting; undated sink to the end
    rows.sort(key=lambda r: r["date"] or "9999")
    return rows


def _write_report(
    scored: list[dict], now: datetime, snap: pl.DataFrame, decisions: list[dict]
) -> None:
    finish_to_zero = [s for s in scored if s["open_issues_count"] == 1 and s["total_score"] > 0]
    finish_to_zero.sort(key=lambda x: (-x["total_score"], -x["age_days"]))
    top = scored[:20]

    lines: list[str] = []
    lines.append("# V-Sekai — finish-it-today tasks\n")
    lines.append(
        f"_Snapshot `{snap['captured_at'][0]}` · {len(scored)} candidate open issues "
        f"scored for finishability + haunting + doability. Higher = more joyful to close today._\n"
    )

    lines.append("## Finish a repo to zero\n")
    lines.append(
        "Each of these is the last open issue in its repo, so closing one finishes that repo outright.\n"
    )
    if finish_to_zero:
        lines.append("| # | Repo | Issue | Age | 💬 | Score | Why |")
        lines.append("|---|------|-------|-----|----|-------|-----|")
        for s in finish_to_zero[:15]:
            lines.append(
                f"| {s['rank']} | `{s['repo']}` | [#{s['number']} {_trim(s['title'])}]({s['url']}) "
                f"| {s['age_days']}d | {s['comments']} | {s['total_score']} | {s['reasons']} |"
            )
    else:
        lines.append("_No single-issue repos passed the filters this snapshot._")
    lines.append("")

    lines.append("## Top 20 finishable issues overall\n")
    lines.append("| Rank | Repo | Issue | Lang | Open | Age | 💬 | Score | Why |")
    lines.append("|------|------|-------|------|------|-----|----|-------|-----|")
    for s in top:
        lines.append(
            f"| {s['rank']} | `{s['repo']}` | [#{s['number']} {_trim(s['title'])}]({s['url']}) "
            f"| {s['language'] or '-'} | {s['open_issues_count']} | {s['age_days']}d | {s['comments']} "
            f"| **{s['total_score']}** | {s['reasons']} |"
        )
    lines.append("")
    if decisions:
        lines.append("## Haunting decisions in the manuals\n")
        lines.append(
            "MADR decision records explicitly marked `proposed`/`draft` are documented "
            "intentions waiting to be finished and accepted. Oldest first.\n"
        )
        lines.append("| Repo | Decision | Date | Status |")
        lines.append("|------|----------|------|--------|")
        for d in decisions[:20]:
            url = f"https://github.com/{d['_repo']}/blob/HEAD/{d['path']}"
            status = d["status"] or "(none)"
            lines.append(
                f"| `{d['_repo']}` | [{_trim(d['title'])}]({url}) "
                f"| {d['date'] or '-'} | {status} |"
            )
        lines.append("")

    lines.append("### Score model\n")
    lines.append(
        "- finishability: repo has 1 open issue (+6), 2 (+4), 3 (+2), ≤5 (+1); closing empties the repo.\n"
        "- haunting: issue age >2y (+4), >1y (+3), >6mo (+2), >3mo (+1); +1 if untouched >1y.\n"
        "- doability: ≤1 comment (+2)/≤3 (+1); short body (+1); finishing-task title (+2); "
        "good-first/help-wanted/docs label (+2); epic title (−4); epic/needs-design label (−3).\n"
        "- elixir: Elixir repo (+4); Elixir/BEAM keywords in title (+3); CLI-shaped task "
        "(+2), since any CLI ships as an Elixir binary via Burrito. Ties break toward Elixir.\n"
        "- Excluded: archived or fork repos, and issues labelled blocked/wontfix/invalid/duplicate.\n"
    )
    (c.REPORTS / "finishable_tasks.md").write_text("\n".join(lines), encoding="utf-8")
    _log(f"wrote reports/finishable_tasks.md ({len(finish_to_zero)} finish-to-zero, top {len(top)})")


def _trim(title: str, n: int = 60) -> str:
    title = (title or "").replace("|", "\\|").strip()
    return title if len(title) <= n else title[: n - 1] + "…"


if __name__ == "__main__":
    main()
