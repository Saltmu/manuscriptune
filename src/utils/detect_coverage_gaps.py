import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, cast


def format_missing_lines(lines: list[int]) -> str:
    """Format a list of integers into a string of ranges.

    e.g., [5, 6, 7, 9] -> "5-7, 9"
    """
    if not lines:
        return ""
    sorted_lines = sorted(list(set(lines)))
    ranges: list[str] = []
    start = sorted_lines[0]
    prev = sorted_lines[0]
    for line in sorted_lines[1:]:
        if line == prev + 1:
            prev = line
        else:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = line
            prev = line
    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")
    return ", ".join(ranges)


def detect_gaps(json_path: str = "") -> dict[str, Any]:
    """Run coverage json and parse it, or parse a given JSON file."""
    if json_path:
        with open(json_path) as f:
            return cast(dict[str, Any], json.load(f))

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_json = os.path.join(tmpdir, "coverage.json")
        # Run coverage json
        res = subprocess.run(
            ["poetry", "run", "coverage", "json", "-o", temp_json],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            print(f"Error running coverage json: {res.stderr}", file=sys.stderr)
            sys.exit(1)
        with open(temp_json) as f:
            return cast(dict[str, Any], json.load(f))


def generate_markdown(coverage_data: dict[str, Any]) -> str:
    """Generate Markdown report for coverage gaps."""
    files_data = coverage_data.get("files", {})
    gaps: list[dict[str, Any]] = []
    for filepath, info in files_data.items():
        summary = info.get("summary", {})
        pct = summary.get("percent_covered", 100.0)
        if pct < 100.0:
            missing = info.get("missing_lines", [])
            gaps.append(
                {
                    "file": filepath,
                    "coverage": f"{pct:.2f}%",
                    "missing": format_missing_lines(missing),
                    "pct_val": pct,
                }
            )

    if not gaps:
        return "# Coverage Report\n\nAll files have 100% test coverage! 🎉\n"

    gaps.sort(key=lambda x: x["pct_val"])

    md_lines = [
        "# Coverage Gaps",
        "",
        "The following files have test coverage below 100%:",
        "",
        "| File | Coverage | Missing Lines |",
        "| :--- | :---: | :--- |",
    ]
    for g in gaps:
        md_lines.append(f"| `{g['file']}` | {g['coverage']} | {g['missing']} |")

    return "\n".join(md_lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect test coverage gaps and output in Markdown"
    )
    parser.add_argument(
        "--output",
        help="Path to write the markdown report to. Prints to stdout if not specified.",
    )
    parser.add_argument(
        "--json-file",
        help="Path to pre-generated coverage json file. If not provided, it will generate it.",
    )
    args = parser.parse_args()

    try:
        data = detect_gaps(json_path=args.json_file or "")
        report = generate_markdown(data)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"Coverage gap report written to {args.output}")
        else:
            print(report)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
