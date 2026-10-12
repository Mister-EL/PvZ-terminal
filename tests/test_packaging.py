"""Exercise distribution contents and an actual isolated installation."""
from __future__ import annotations

import email
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUILD_TOOLS = all(importlib.util.find_spec(name) is not None
                  for name in ("build", "setuptools", "wheel", "ensurepip"))


def run_command(args, *, cwd, env=None):
    result = subprocess.run(args, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=90)
    if result.returncode:
        raise AssertionError(f"{args[0]} exited {result.returncode}\n"
                             f"{result.stdout}\n{result.stderr}")
    return result.stdout


@unittest.skipUnless(BUILD_TOOLS, "wheel verification needs local build/setuptools/wheel/ensurepip")
class WheelInstallationTests(unittest.TestCase):
    def test_wheel_installs_offline_with_resources_and_console_entrypoint(self):
        with tempfile.TemporaryDirectory(prefix="pvz-wheel-test-") as temporary:
            temporary = Path(temporary)
            source = temporary / "source"
            source.mkdir()
            for name in ("pyproject.toml", "README.md"):
                shutil.copy2(ROOT / name, source / name)
            shutil.copytree(ROOT / "pvz", source / "pvz",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            # Typical local state must never become application resources.
            for relative in ("secrets/token.txt", "tests/private.py",
                             "docs/scenarios/solutions/proof.json", ".git/config",
                             "pvz/data/progress.json", "pvz/data/secrets.json"):
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("local-only", encoding="utf-8")
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            environment["PIP_NO_INDEX"] = "1"
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            distributions = temporary / "dist"
            run_command([sys.executable, "-m", "build", "--wheel", "--no-isolation",
                         "--outdir", str(distributions)], cwd=source, env=environment)
            wheels = list(distributions.glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            expected_ids = sorted(path.stem for path in (ROOT / "pvz/data").glob("*.json"))
            with zipfile.ZipFile(wheels[0]) as archive:
                members = archive.namelist()
                resource_ids = sorted(Path(name).stem for name in members
                                      if name.startswith("pvz/data/") and name.endswith(".json"))
                self.assertEqual(resource_ids, expected_ids)
                self.assertTrue(all(name.startswith("pvz/") or ".dist-info/" in name
                                    for name in members), members)
                self.assertFalse(any("__pycache__" in name or name.endswith(".pyc")
                                     for name in members))
                metadata_name = next(name for name in members if name.endswith(".dist-info/METADATA"))
                metadata = email.message_from_bytes(archive.read(metadata_name))
                self.assertEqual(metadata["Requires-Python"], ">=3.12")
                self.assertFalse(metadata.get_all("Requires-Dist"))
            environment_path = temporary / "venv"
            run_command([sys.executable, "-m", "venv", str(environment_path)],
                        cwd=temporary, env=environment)
            binary = environment_path / ("Scripts" if os.name == "nt" else "bin")
            python = binary / ("python.exe" if os.name == "nt" else "python")
            command = binary / ("pvz-terminal.exe" if os.name == "nt" else "pvz-terminal")
            run_command([str(python), "-m", "pip", "install", "--no-index", "--no-deps",
                         "--disable-pip-version-check", str(wheels[0])],
                        cwd=temporary, env=environment)
            unrelated = temporary / "unrelated"
            unrelated.mkdir()
            output = run_command([str(command), "--list-scenarios"],
                                 cwd=unrelated, env=environment)
            self.assertEqual(sorted(line.split("\t")[0] for line in output.splitlines()), expected_ids)
            inspect = ("import json; from importlib.resources import files; "
                       "from pvz.content import list_scenarios; "
                       "print(json.dumps({'ids': [s.id for s in list_scenarios()], "
                       "'resource': files('pvz.data').joinpath('campaign-01-first-sprout.json')"
                       ".read_text(encoding='utf-8')}))")
            installed = json.loads(run_command([str(python), "-I", "-c", inspect],
                                               cwd=unrelated, env=environment))
            self.assertEqual(sorted(installed["ids"]), expected_ids)
            self.assertEqual(json.loads(installed["resource"])["id"], "campaign-01-first-sprout")
            self.assertFalse((unrelated / "progress.json").exists())


if __name__ == "__main__":
    unittest.main()
