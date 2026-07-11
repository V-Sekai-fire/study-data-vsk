"""Ad-hoc SQL over the parquet lake with DuckDB. `pixi run lake`.

Prints a couple of sanity queries that cross-check reports/finishable_tasks.md, and
leaves a connection pattern you can copy for your own exploration.
"""

from __future__ import annotations

import sys

import duckdb

import common as c

LAKE = str(c.LAKE).replace("\\", "/")


def q(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    print(f"\n>>> {sql.strip()}")
    try:
        print(con.sql(sql))
    except Exception as exc:  # pragma: no cover - diagnostic helper
        print(f"  (query failed: {exc})", file=sys.stderr)


def main() -> None:
    con = duckdb.connect()
    # register each parquet as a view named after the file
    for name in [
        "orgs", "repos", "users", "issues", "labels", "issue_labels",
        "repo_topics", "decisions", "joy_scores", "snapshot",
    ]:
        path = c.LAKE / f"{name}.parquet"
        if path.exists():
            con.sql(
                f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{LAKE}/{name}.parquet')"
            )

    q(con, "SELECT captured_at, orgs FROM snapshot")

    q(con, """
        SELECT r.full_name, i.number, i.title
        FROM repos r JOIN issues i USING (repo_uuid)
        WHERE r.open_issues_count = 1 AND r.archived = false AND r.fork = false
        ORDER BY i.created_at
        LIMIT 10
    """)

    q(con, """
        SELECT r.full_name, js.total_score, i.title
        FROM joy_scores js
        JOIN issues i USING (issue_uuid)
        JOIN repos  r USING (repo_uuid)
        ORDER BY js.rank
        LIMIT 10
    """)

    q(con, """
        SELECT COUNT(*) AS repos_one_from_zero
        FROM repos
        WHERE open_issues_count = 1 AND archived = false AND fork = false
    """)


if __name__ == "__main__":
    main()
