import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "build_report.py"
spec = importlib.util.spec_from_file_location("build_report", SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class BuildReportTest(unittest.TestCase):
    def test_snapshot_redacts_urls_and_records_resolved_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (root / "android15-6.6" / "common" / ".git").mkdir(parents=True)
            inputs = {"custom_kernel_source": "https://secret@host/kernel", "clang_custom_link": "secret", "prepare_only": True}
            with patch.dict(os.environ, {"BUILD_INPUTS": json.dumps(inputs)}), patch.object(report, "command", return_value="revision"):
                report.snapshot(root, artifacts)
            content = (artifacts / "manifest.json").read_text()
            self.assertNotIn("secret", content)
            self.assertEqual(json.loads(content)["repositories"][str(Path("android15-6.6/common"))]["commit"], "revision")

    def test_failure_before_snapshot_still_collects_diagnostics_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            kernel = root / "android15-6.6" / "common"
            kernel.mkdir(parents=True)
            (kernel / "failed.patch.rej").write_text("rejected hunk")
            output = root / "android15-6.6" / "out"
            output.mkdir()
            (output / ".config").write_text("CONFIG_KSU=y\n")
            with patch.dict(os.environ, {"BUILD_RESULT": "failure", "GITHUB_STEP_SUMMARY": str(root / "summary")}), patch.object(report, "command", return_value="diagnostics"):
                report.finalize(root, artifacts)
            self.assertEqual(json.loads((artifacts / "manifest.json").read_text())["result"], "failure")
            self.assertEqual((artifacts / "patch-rejects" / "failed.patch.rej").read_text(), "rejected hunk")
            self.assertTrue((artifacts / "configs" / "make" / ".config").exists())
            for line in (artifacts / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256((artifacts / name).read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
