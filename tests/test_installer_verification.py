from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.verify_installers import parse_installer


class InstallerVerificationTests(unittest.TestCase):
    def test_real_parser_accepts_valid_library_and_rejects_malformed_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "sample.tpa"
            library.write_text("OUTER_SET example = 1\n")
            parse_installer(library, root)
            library.write_text("OUTER_SET example =\n")
            with self.assertRaisesRegex(SystemExit, "Parse failed"):
                parse_installer(library, root)

    def test_zero_exit_without_success_cannot_reuse_a_previous_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "parse.log").write_text("sample was successfully parsed")
            result = subprocess.CompletedProcess([], 0, "WeiDU version 24900", "")
            with patch("tools.verify_installers.subprocess.run", return_value=result):
                with self.assertRaisesRegex(SystemExit, "Parse failed"):
                    parse_installer(root / "sample.tpa", root)

    def test_error_output_overrides_success_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for diagnostic in ("FATAL: parsing", "ERROR: parsing"):
                result = subprocess.CompletedProcess([], 0, "sample was successfully parsed", diagnostic)
                with self.subTest(diagnostic=diagnostic), patch("tools.verify_installers.subprocess.run", return_value=result):
                    with self.assertRaisesRegex(SystemExit, "Parse failed"):
                        parse_installer(root / "sample.tpa", root)
