"""Sort a codespell report (as produced for spellFix.py) alphabetically by typo word."""
import argparse
import re
from pathlib import Path

# Matches codespell report lines: <path>:<line>: <typo> ==> <corrections>
# Optionally prefixed with a [FIXED] or [SKIPPED] marker.
REPORT_LINE_PATTERN = re.compile(r"^(\[FIXED\]|\[SKIPPED\]\s*)?(.+?):(\d+):\s+(.+?)\s+=+>\s+(.+)$")


def sort_key(line):
    """Extract the typo word from a report line for sorting; unparsable lines sort first."""
    match = REPORT_LINE_PATTERN.match(line.strip())
    if not match:
        return ""
    return match.group(4).strip().lower()


def sort_report(input_path, output_path, encoding):
    with open(input_path, "r", encoding=encoding, errors="ignore") as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    lines.sort(key=sort_key)

    with open(output_path, "w", encoding=encoding) as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Sort a codespell report by typo word.")
    parser.add_argument("report", help="Path to the codespell report file")
    parser.add_argument("-o", "--output", help="Output path (default: <report>_sorted.txt)")
    parser.add_argument("--encoding", default="utf-16", help="File encoding (default: utf-16, matching spellFix.py)")
    args = parser.parse_args()

    input_path = Path(args.report)
    if not input_path.exists():
        parser.error(f"Report file not found: {input_path}")

    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_sorted{input_path.suffix}")

    sort_report(input_path, output_path, args.encoding)
    print(f"Sorted report written to {output_path}")


if __name__ == "__main__":
    main()
