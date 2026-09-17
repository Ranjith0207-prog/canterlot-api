import re
import sys
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
STAGE_MARKER_RE = re.compile(r"\x1b\[36m")
COVERAGE_TABLE_START_RE = re.compile(r"^Name\s+Stmts")
COVERAGE_TABLE_END_RE = re.compile(r"^Required test coverage")


def _keep_from_last_stage(lines: list[str]) -> list[str]:
    markers = [i for i, line in enumerate(lines) if STAGE_MARKER_RE.search(line)]
    return lines[markers[-1] :] if markers else lines


def _omit_coverage_table(lines: list[str]) -> list[str]:
    start = next((i for i, line in enumerate(lines) if COVERAGE_TABLE_START_RE.match(ANSI_RE.sub("", line))), None)
    end = next((i for i, line in enumerate(lines) if COVERAGE_TABLE_END_RE.match(ANSI_RE.sub("", line))), None)

    if start is None or end is None or end < start:
        return lines

    return [*lines[:start], "... (per-file coverage table omitted) ...", *lines[end:]]


def extract_error_output(raw_text: str) -> str:
    lines = _keep_from_last_stage(raw_text.splitlines())
    lines = _omit_coverage_table(lines)
    return "\n".join(ANSI_RE.sub("", line) for line in lines)


def main() -> None:
    log_path = Path(sys.argv[1])
    print(extract_error_output(log_path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
