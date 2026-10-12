"""Verify ZIP resources, isolated launch, and safe archive publication."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pvz_zipapp_builder", ROOT / "tools/build_zipapp.py")
builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = builder
SPEC.loader.exec_module(builder)


class ZipappTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pvz-zipapp-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        shutil.copytree(ROOT / "pvz", self.source / "pvz",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.output = self.root / "dist" / "game.pyz"

    def run_python(self, *args):
        unrelated = self.root / "unrelated"
        unrelated.mkdir(exist_ok=True)
        return subprocess.run([sys.executable, "-I", *map(str, args)], cwd=unrelated,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30)

    def test_archive_launches_outside_checkout_and_reads_zip_resources(self):
        for name in (".git/config", "secrets/token.txt", "tests/private.py",
                     "docs/scenarios/solutions/private.json", "pvz/data/progress.json",
                     "pvz/secrets.py", "pvz/data/__pycache__/private.pyc"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("local-only", encoding="utf-8")
        payload_names = builder.build_archive(self.source, self.output)
        expected_ids = sorted(path.stem for path in (ROOT / "pvz/data").glob("*.json"))
        with zipfile.ZipFile(self.output) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            self.assertEqual(sorted(members), sorted(payload_names))
            self.assertNotIn("pvz/secrets.py", members)
            self.assertNotIn("pvz/data/progress.json", members)
            self.assertEqual(sum(name.endswith(".json") for name in members), len(expected_ids))
        listing = self.run_python(self.output, "--list-scenarios")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(sorted(line.split("\t")[0] for line in listing.stdout.splitlines()), expected_ids)
        inspect = ("import sys, json; sys.path.insert(0, sys.argv[1]); "
                   "from importlib.resources import files; from pvz.content import list_scenarios; "
                   "import pvz; print(json.dumps({'loader': type(pvz.__loader__).__name__, "
                   "'ids': [s.id for s in list_scenarios()], 'resource': "
                   "files('pvz.data').joinpath('campaign-01-first-sprout.json').read_text(encoding='utf-8')}))")
        result = self.run_python("-c", inspect, self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        loaded = json.loads(result.stdout)
        self.assertEqual(loaded["loader"], "zipimporter")
        self.assertEqual(sorted(loaded["ids"]), expected_ids)
        self.assertEqual(json.loads(loaded["resource"])["id"], "campaign-01-first-sprout")
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])
        self.assertFalse((self.root / "unrelated/progress.json").exists())

    def test_archive_preserves_cli_error_exit_codes(self):
        builder.build_archive(self.source, self.output)
        for args in (("--tick-ms", "0"), ("--scenario", "missing-scenario")):
            with self.subTest(args=args):
                result = self.run_python(self.output, *args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_dry_run_creates_neither_archive_nor_parent_directory(self):
        result = self.run_python(ROOT / "tools/build_zipapp.py", "--dry-run", "--output", self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[1:-1], [item.name for item in builder.collect_payload(ROOT)])
        self.assertIn("no files written", lines[-1])
        self.assertFalse(self.output.parent.exists())

    def test_existing_output_and_symbolic_link_are_preserved(self):
        self.output.parent.mkdir()
        self.output.write_bytes(b"previous archive")
        with self.assertRaises(FileExistsError):
            builder.build_archive(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous archive")
        link = self.output.parent / "linked.pyz"
        link.symlink_to(self.output)
        with self.assertRaises(FileExistsError):
            builder.build_archive(self.source, link)
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.output.read_bytes(), b"previous archive")

    def test_racing_output_wins_without_partial_archive_or_staging_files(self):
        def concurrent_publish(*args):
            self.output.write_bytes(b"concurrent result")
            raise FileExistsError("destination was created during build")
        with mock.patch.object(builder.os, "link", side_effect=concurrent_publish):
            with self.assertRaises(FileExistsError):
                builder.build_archive(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"concurrent result")
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_failed_assembly_leaves_no_archive_or_temporary_files(self):
        with mock.patch.object(builder.zipapp, "create_archive", side_effect=OSError("assembly failed")):
            with self.assertRaises(OSError):
                builder.build_archive(self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_runtime_symlinks_are_rejected_before_output_is_created(self):
        runtime = self.source / "pvz/game.py"
        runtime.unlink()  # Disposable fixture created by setUp.
        runtime.symlink_to(ROOT / "pvz/game.py")
        with self.assertRaises(builder.BuildError):
            builder.build_archive(self.source, self.output)
        self.assertFalse(self.output.parent.exists())

    def test_invalid_scenario_id_is_rejected_before_output_is_created(self):
        resource = self.source / "pvz/data/campaign-01-first-sprout.json"
        data = json.loads(resource.read_text(encoding="utf-8"))
        data["id"] = "another-scenario"
        resource.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(builder.BuildError):
            builder.build_archive(self.source, self.output)
        self.assertFalse(self.output.parent.exists())

    def test_same_payload_produces_identical_archives(self):
        second = self.output.with_name("second.pyz")
        builder.build_archive(self.source, self.output)
        builder.build_archive(self.source, second)
        self.assertEqual(self.output.read_bytes(), second.read_bytes())
        self.assertTrue(os.stat(self.output).st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
