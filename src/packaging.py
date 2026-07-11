"""Ingest packaging shape: 'can this ship as a Burrito binary?' is a repo-shape
question, and three routes reach a single distributable Elixir binary:

  elixir  — an escript/Mix release wrapped by Burrito (native).
  c       — a C/C++ CLI wrapped via a NIF/port, then Burrito.
  python  — a Python/ML app embedded via pythonx, distributed on hex.pm, then Burrito.

For each candidate repo (Elixir / C / C++ / Python) fetch the build manifest and
detect: is it a CLI, is it ML, is it a web service, and is Burrito/escript already set
up. Only parquet is written (raw/packaging.parquet); the repo list comes from
raw/repos.parquet.
"""

from __future__ import annotations

import base64
import json
import re
import sys

import httpx
import polars as pl

import common as c

LANGS = {"Elixir", "C", "C++", "Python"}

# candidate manifests per language, tried in order
MANIFESTS = {
    "Elixir": ["mix.exs"],
    "C": ["CMakeLists.txt", "Makefile"],
    "C++": ["CMakeLists.txt", "Makefile"],
    "Python": ["pyproject.toml", "setup.py", "setup.cfg"],
}

ML_LIBS = (
    "torch", "tensorflow", "numpy", "scipy", "scikit", "sklearn", "transformers",
    "jax", "onnx", "pandas", "opencv", "diffusers", "keras", "xgboost", "lightgbm",
    "autogluon", "nx", "axon", "bumblebee", "pythonx",
)
DESC_RE = re.compile(r'description:\s*"([^"]*)"')
MAIN_RE = re.compile(r"main_module:\s*([A-Za-z0-9_.]+)")


def _log(msg: str) -> None:
    print(f"[packaging] {msg}", file=sys.stderr)


def _detect(language: str, manifest: str, text: str) -> dict:
    low = text.lower()
    is_ml = any(lib in low for lib in ML_LIBS)
    if language == "Elixir":
        main = MAIN_RE.search(text)
        desc = DESC_RE.search(text)
        is_cli = "escript:" in low or main is not None
        return {
            "route": "elixir",
            "is_cli": is_cli,
            "cli_evidence": "escript main_module" if is_cli else "library (add escript)",
            "is_ml": is_ml,
            "is_web": any(d in low for d in (":phoenix", ":plug", ":bandit", ":cowboy")),
            "is_server": "mcp" in low or "hermes" in low,
            "has_burrito": "burrito" in low,
            "entry": main.group(1) if main else None,
            "description": desc.group(1) if desc else None,
        }
    if language == "Python":
        is_cli = any(
            s in low for s in
            ("[project.scripts]", "console_scripts", "entry_points",
             "[tool.poetry.scripts]", "click", "typer", "argparse")
        )
        return {
            "route": "python",
            "is_cli": is_cli,
            "cli_evidence": "console entrypoint / arg parser" if is_cli else "no CLI entrypoint declared",
            "is_ml": is_ml,
            "is_web": any(s in low for s in ("fastapi", "flask", "django", "uvicorn", "starlette")),
            "is_server": "mcp" in low,
            "has_burrito": False,
            "entry": None,
            "description": None,
        }
    # C / C++
    is_cli = "add_executable" in low or (manifest == "Makefile" and "gcc" in low or "g++" in low)
    return {
        "route": "c",
        "is_cli": bool(is_cli),
        "cli_evidence": "builds an executable" if is_cli else "no executable target",
        "is_ml": is_ml,
        "is_web": False,
        "is_server": False,
        "has_burrito": False,
        "entry": None,
        "description": None,
    }


def _get(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response | None:
    """GET with a few retries on transient 5xx; returns None if it never succeeds."""
    for attempt in range(4):
        resp = client.get(url, params=params)
        if resp.status_code < 500:
            return resp
        # transient server error — vary the wait deterministically by attempt
        import time
        time.sleep(0.5 * (attempt + 1))
    return None


def _fetch(client: httpx.Client, full: str, names: list[str]) -> tuple[str | None, str]:
    for name in names:
        resp = _get(client, f"/repos/{full}/contents/{name}")
        if resp is None:
            continue
        if resp.status_code == 200:
            return name, base64.b64decode(resp.json()["content"]).decode("utf-8", "replace")
        if resp.status_code not in (404,):
            resp.raise_for_status()
    return None, ""


def _tree(client: httpx.Client, full: str, branch: str) -> list[str]:
    resp = _get(client, f"/repos/{full}/git/trees/{branch}", {"recursive": "1"})
    if resp is None or resp.status_code != 200:
        return []
    return [t["path"] for t in resp.json().get("tree", []) if t.get("type") == "blob"]


def _elixir_subcli(paths: list[str]) -> str | None:
    """Directory of an Elixir sub-project CLI (e.g. cloth_fit_cli/mix.exs). Shallowest wins."""
    mixes = sorted((p for p in paths if p.endswith("/mix.exs")), key=lambda p: p.count("/"))
    return mixes[0].rsplit("/mix.exs", 1)[0] if mixes else None


def main() -> None:
    repos = [json.loads(p) for p in pl.read_parquet(c.RAW / "repos.parquet")["payload"].to_list()]
    # Include forks: V-Sekai heavily customizes upstream research forks (cloth-fit,
    # DiffCloth, …), and those customized tools are exactly the joyful candidates.
    candidates = [
        r for r in repos
        if r.get("language") in LANGS and not r.get("archived")
    ]
    _log(f"{len(candidates)} candidate repos (Elixir/C/C++/Python, forks included)")

    rows: list[dict] = []
    with httpx.Client(base_url=c.GITHUB_API, headers=c.auth_headers(), timeout=30.0) as client:
        for r in candidates:
            full, language = r["full_name"], r["language"]
            paths = _tree(client, full, r.get("default_branch", "main"))
            has_unifex = any("bundlex.exs" in p or "unifex" in p.lower() for p in paths)
            # A C/C++/Python repo whose CLI is an Elixir/Unifex subdir is on the elixir route.
            subdir = _elixir_subcli(paths) if language != "Elixir" else None
            base = {
                "repo_full_name": full, "language": language,
                "has_elixir_subcli": subdir is not None, "subcli_dir": subdir,
                "has_unifex": has_unifex,
            }
            if subdir is not None:
                _, text = _fetch(client, full, [f"{subdir}/mix.exs"])
                det = _detect("Elixir", "mix.exs", text)
                det["route"] = "elixir"  # native BEAM CLI over a C/C++/Python core via NIF
                if has_unifex and not det["is_cli"]:
                    det["is_cli"] = True
                    det["cli_evidence"] = "Elixir/Unifex CLI subdir wrapping a native core"
                rows.append(base | {"manifest": f"{subdir}/mix.exs", "has_manifest": True} | det)
            else:
                manifest, text = _fetch(client, full, MANIFESTS[language])
                det = _detect(language, manifest, text) if manifest else dict(_EMPTY)
                rows.append(base | {"manifest": manifest, "has_manifest": manifest is not None} | det)

    ready = sum(1 for x in rows if x.get("has_burrito") or (x["route"] == "elixir" and x.get("is_cli")))
    _log(f"{sum(x['is_cli'] for x in rows)} CLI-shaped, {sum(x['is_ml'] for x in rows)} ML, "
         f"{sum(x['has_elixir_subcli'] for x in rows)} elixir-subcli, {ready} escript/burrito-ready")

    pl.DataFrame(rows, schema=_SCHEMA).write_parquet(c.RAW / "packaging.parquet")
    _log(f"wrote {len(rows)} -> raw/packaging.parquet")


_SCHEMA = {
    "repo_full_name": pl.Utf8, "language": pl.Utf8, "manifest": pl.Utf8,
    "has_manifest": pl.Boolean, "has_elixir_subcli": pl.Boolean, "subcli_dir": pl.Utf8,
    "has_unifex": pl.Boolean, "route": pl.Utf8, "is_cli": pl.Boolean,
    "cli_evidence": pl.Utf8, "is_ml": pl.Boolean, "is_web": pl.Boolean,
    "is_server": pl.Boolean, "has_burrito": pl.Boolean, "entry": pl.Utf8,
    "description": pl.Utf8,
}
_EMPTY = {
    "route": None, "is_cli": False, "cli_evidence": "no manifest found", "is_ml": False,
    "is_web": False, "is_server": False, "has_burrito": False, "entry": None,
    "description": None,
}


if __name__ == "__main__":
    main()
