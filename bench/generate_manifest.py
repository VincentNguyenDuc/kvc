#!/usr/bin/env python3
"""Aggregate bench/output/**bench.json into docs/data/runs.json.

Also copies any flamegraph.svg files into docs/data/ so the static site
can serve them, and parses VERSIONS.md into docs/data/versions.json.

Run after a benchmark to update the dashboard:
    python bench/generate_manifest.py
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
RESULTS = ROOT / "bench" / "output"
OUT_DIR = ROOT / "docs" / "data"
OUT_FILE = OUT_DIR / "runs.json"
VERSIONS_MD = ROOT / "VERSIONS.md"
VERSIONS_OUT = OUT_DIR / "versions.json"


def parse_versions_md() -> list:
    """Parse the markdown table in VERSIONS.md into [{version, description}, ...] dicts."""
    versions = []
    text = VERSIONS_MD.read_text(encoding="utf-8")
    first_row = True
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 2:
            continue
        v_cell = cells[0]
        if first_row:
            first_row = False
            continue
        if re.match(r"^[-: ]+$", v_cell):
            continue
        version = v_cell.strip("`")
        description = cells[1]
        if version:
            versions.append({"version": version, "description": description})
    return versions


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if VERSIONS_MD.exists():
        versions = parse_versions_md()
        VERSIONS_OUT.write_text(json.dumps(versions, indent=4), encoding="utf-8")
        print(f"wrote {len(versions)} version(s) -> {VERSIONS_OUT.relative_to(ROOT)}")

    runs = []
    for bench_path in sorted(RESULTS.glob("**/bench.json")):
        run_dir = bench_path.parent
        try:
            data = json.loads(bench_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  skip {bench_path.relative_to(ROOT)}: {exc}")
            continue

        fg_src = run_dir / "flamegraph.svg"
        if fg_src.exists():
            version = data.get("version", run_dir.parent.name)
            run_id = data.get("run_id", run_dir.name)
            fg_dst = OUT_DIR / version / run_id / "flamegraph.svg"
            fg_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fg_src, fg_dst)
            data["flamegraph_url"] = f"data/{version}/{run_id}/flamegraph.svg"

        runs.append(data)

    OUT_FILE.write_text(json.dumps(runs, indent=4), encoding="utf-8")
    print(f"wrote {len(runs)} run(s) -> {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
