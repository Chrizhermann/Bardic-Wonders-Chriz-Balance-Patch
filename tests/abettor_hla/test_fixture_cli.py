from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from .ie_resources import read_controller_payload
from . import test_tail_patch_integration as fixture_support
from .make_fixture import build_fixture
from .verify_fixture import verify


ROOT = Path(__file__).resolve().parents[2]


class DisposableFixtureCliTests(unittest.TestCase):
    def test_builds_and_verifies_an_isolated_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-game"
            fixture = root / "fixture"
            fixture_support.TailPatchIntegrationTests().make_fixture(
                source,
                include_later_save=True,
                include_later_luck=True,
            )
            language = source / "lang" / "en_US"
            language.mkdir(parents=True)
            shutil.copy2(source / "dialog.tlk", language / "dialog.tlk")

            make = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.abettor_hla.make_fixture",
                    "--source",
                    str(source),
                    "--destination",
                    str(fixture),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, make.returncode, make.stdout + make.stderr)
            self.assertTrue((fixture / "fixture-manifest.json").exists())
            self.assertEqual(
                fixture_support.PAYLOAD_RESREF,
                read_controller_payload(fixture / "override" / "C0ABETS2.SPL"),
            )

            verify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.abettor_hla.verify_fixture",
                    "--fixture",
                    str(fixture),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, verify.returncode, verify.stdout + verify.stderr)
            self.assertIn("DISPOSABLE_FIXTURE_VERIFICATION=PASS", verify.stdout)

    def test_builder_refuses_each_reserved_output_collision(self) -> None:
        for name in ("C0ABIVI.SPL", "C0ABIVS.EFF", "C0ABIVE.EFF"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source-game"
                fixture_support.TailPatchIntegrationTests().make_fixture(source)
                (source / "override" / name).write_bytes(b"collision")

                with self.assertRaisesRegex(RuntimeError, "reserved"):
                    build_fixture(source, root / "fixture")

    def test_builder_refuses_destination_inside_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source-game"
            fixture_support.TailPatchIntegrationTests().make_fixture(source)

            with self.assertRaisesRegex(RuntimeError, "outside"):
                build_fixture(source, source / "disposable-fixture")

    def test_builder_refuses_malformed_controller_payload_resref(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-game"
            fixture_support.TailPatchIntegrationTests().make_fixture(source)
            pointer = source / "override" / "C0ABETS2.SPL"
            data = bytearray(pointer.read_bytes())
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
            first_effect = struct.unpack_from("<H", data, ability_offset + 0x20)[0]
            offset = effect_offset + (first_effect + 2) * 0x30 + 0x14
            data[offset:offset + 8] = b"QXP\0BAD!"
            pointer.write_bytes(data)

            with self.assertRaisesRegex(ValueError, "padding"):
                build_fixture(source, root / "fixture")

    def test_verifier_refuses_fixture_drift_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-game"
            fixture = root / "fixture"
            fixture_support.TailPatchIntegrationTests().make_fixture(source)
            language = source / "lang" / "en_US"
            language.mkdir(parents=True)
            shutil.copy2(source / "dialog.tlk", language / "dialog.tlk")
            build_fixture(source, fixture)
            (fixture / "override" / "C0ABETHL.SPL").write_bytes(b"drift")

            verify = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.abettor_hla.verify_fixture",
                    "--fixture",
                    str(fixture),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, verify.returncode)
            self.assertIn("drifted since creation", verify.stderr)

    def test_verifier_refuses_a_nonempty_game_resource_index(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-game"
            fixture = root / "fixture"
            fixture_support.TailPatchIntegrationTests().make_fixture(source)
            build_fixture(source, fixture)
            key = fixture / "chitin.key"
            data = bytearray(key.read_bytes())
            struct.pack_into("<I", data, 8, 1)
            key.write_bytes(data)

            with self.assertRaisesRegex(AssertionError, "empty synthetic"):
                verify(fixture)

    def test_verifier_refuses_game_executables_in_the_fixture(self) -> None:
        for marker in ("Baldur.exe", "InfinityLoader.exe"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source-game"
                fixture = root / "fixture"
                fixture_support.TailPatchIntegrationTests().make_fixture(source)
                build_fixture(source, fixture)
                (fixture / marker).write_bytes(b"game executable marker")

                with self.assertRaisesRegex(AssertionError, "game-like fixture"):
                    verify(fixture)


if __name__ == "__main__":
    unittest.main()
