#!/usr/bin/env python3
"""Build a self-contained application archive using only Python's standard library."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import zipapp


SOURCE_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = tuple(f"pvz/{name}.py" for name in (
    "__init__", "__main__", "cli", "constants", "content", "game", "grid",
    "progress", "recording", "replay", "types", "ui",
)) + ("pvz/data/__init__.py",)
SCENARIO_FILE = re.compile(r"(?:campaign|challenge)-[a-z0-9]+(?:-[a-z0-9]+)*\.json\Z")
ARCHIVE_MAIN = b"from pvz.cli import main\nraise SystemExit(main())\n"
ARCHIVE_TIME = 315619200  # 1980-01-02 UTC; remains in ZIP range in every timezone.


class BuildError(ValueError):
    """The application cannot be assembled safely from this source tree."""


@dataclass(frozen=True)
class PayloadFile:
    name: str
    data: bytes


def collect_payload(source: Path) -> tuple[PayloadFile, ...]:
    """Snapshot an explicit runtime allowlist; ignore repository and user state."""
    source = Path(source)
    for directory in (source, source / "pvz", source / "pvz/data"):
        if directory.is_symlink() or not directory.is_dir():
            raise BuildError(f"source directory is missing or is a symbolic link: {directory}")
    selected = list(RUNTIME_FILES)
    scenarios = sorted(path for path in (source / "pvz/data").iterdir()
                       if SCENARIO_FILE.fullmatch(path.name))
    if not scenarios:
        raise BuildError("no campaign/challenge scenario JSON files found")
    selected.extend(path.relative_to(source).as_posix() for path in scenarios)
    payload = [PayloadFile("__main__.py", ARCHIVE_MAIN)]
    for name in sorted(selected):
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise BuildError(f"runtime file is missing or is a symbolic link: {name}")
        data = path.read_bytes()
        if name.endswith(".json"):
            try:
                scenario = json.loads(data)
            except (UnicodeError, ValueError) as exc:
                raise BuildError(f"invalid scenario JSON: {name}") from exc
            if not isinstance(scenario, dict) or scenario.get("id") != path.stem:
                raise BuildError(f"scenario ID does not match filename: {name}")
        payload.append(PayloadFile(name, data))
    return tuple(payload)


def build_archive(source: Path, output: Path) -> tuple[str, ...]:
    """Publish a complete archive atomically; an existing output always wins."""
    output = Path(output).absolute()
    if os.path.lexists(output):
        raise FileExistsError(f"refusing to replace existing output: {output}")
    payload = collect_payload(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pvz-stage-", dir=output.parent) as temporary:
        staging = Path(temporary)
        for item in payload:
            target = staging / item.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.data)
        # Stable timestamps make two builds of the same payload/runtime identical.
        for target in staging.rglob("*"):
            os.utime(target, (ARCHIVE_TIME, ARCHIVE_TIME))
        descriptor, archive_name = tempfile.mkstemp(prefix=".pvz-archive-", suffix=".pyz",
                                                    dir=output.parent)
        os.close(descriptor)
        archive = Path(archive_name)
        try:
            zipapp.create_archive(staging, archive, interpreter="/usr/bin/env python3",
                                  compressed=True)
            os.chmod(archive, 0o755)
            # Both names are on the same filesystem; link is atomic and never replaces.
            os.link(archive, output)
        finally:
            archive.unlink(missing_ok=True)
    return tuple(item.name for item in payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/pvz-terminal.pyz"),
                        help="destination archive; existing files are never replaced")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the application file allowlist without writing anything")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            payload = collect_payload(SOURCE_ROOT)
            print(f"Preview: {args.output.absolute()}")
            for item in payload:
                print(item.name)
            print(f"{len(payload)} application files; no files written")
        else:
            names = build_archive(SOURCE_ROOT, args.output)
            print(f"Built {args.output.absolute()} ({len(names)} application files)")
    except (BuildError, OSError) as exc:
        parser.exit(2, f"build failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
