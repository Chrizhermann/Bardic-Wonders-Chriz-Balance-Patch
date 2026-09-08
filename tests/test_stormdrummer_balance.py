"""Run the production Storm Drummer resource actions with disposable WeiDU.

These checks cover installed resources and uninstall restoration, not live play.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.abettor_hla.ie_resources import parse_spl
from tests.abettor_hla.test_tail_patch_integration import (
    tlk_string,
    tlk_with_original_description,
)
from tests.test_dancer_balance import clab_rows, effect_offsets, file_snapshot


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
STORM = MOD / "storm"
SOURCE = MOD / "lib" / "stormdrummer.tpa"


class StormDrummerBalanceTests(unittest.TestCase):
    def weidu(self, root: Path, operation: str = "install") -> None:
        result = subprocess.run(
            [
                str(ROOT / "Setup-BardicWonders.exe"),
                "--no-auto-tp2", "--noautoupdate", "--nogame",
                "--search", "override", "--tlkin", "dialog.tlk",
                "--tlkout", "dialog.tlk", "--no-exit-pause",
                "--language", "0", f"--force-{operation}", "0",
                "testmod/setup-test.tp2",
            ],
            cwd=root, text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        marker = "SUCCESSFULLY INSTALLED" if operation == "install" else "SUCCESSFULLY REMOVED"
        self.assertIn(marker, result.stdout, result.stdout + result.stderr)

    @contextmanager
    def installed(self):
        original_sources = file_snapshot(STORM)
        source = SOURCE.read_text(encoding="utf-8")
        # Exercise the real first COPY and every later spell COPY/patch/SAY.
        # Kit registration itself requires a full game and is outside this test.
        prefix = source.split("COPY_EXISTING ~LUBA0.2da~", 1)[0]
        start = source.index("COPY ~%MOD_FOLDER%/storm/c0sdrum3.spl~ ~override~")
        with tempfile.TemporaryDirectory(prefix="stormdrummer-balance-") as directory:
            root = Path(directory)
            fixture = root / "testmod"
            shutil.copytree(STORM, fixture / "storm")
            before_fixture = file_snapshot(fixture / "storm")
            override = root / "override"
            override.mkdir()
            previous = bytearray((STORM / "c0sdrum4.spl").read_bytes())
            previous[-1] ^= 0x5A
            (override / "c0sdrum4.spl").write_bytes(previous)
            (override / "unrelated.txt").write_bytes(b"Preserve this fixture resource.\n")
            before_override = file_snapshot(override)
            (root / "dialog.tlk").write_bytes(tlk_with_original_description())
            (fixture / "setup-test.tp2").write_text(
                "BACKUP ~testmod/backup~\nAUTHOR ~test~\n"
                "LANGUAGE ~English~ ~english~\n"
                "BEGIN ~Storm Drummer regression~ DESIGNATED 0\n"
                "OUTER_SPRINT MOD_FOLDER ~testmod~\n"
                + prefix + source[start:],
                encoding="utf-8",
            )
            self.weidu(root)
            yield root
            self.assertEqual(before_fixture, file_snapshot(fixture / "storm"))
            self.weidu(root, "uninstall")
            self.assertEqual(before_override, file_snapshot(override))
        self.assertEqual(original_sources, file_snapshot(STORM))

    def test_installed_stun_and_spell_failure_have_separate_durations(self) -> None:
        with self.installed() as root:
            output = root / "override" / "c0sdrum4.spl"
            spell = parse_spl(output)
            self.assertEqual(1, len(spell.abilities))
            ability = spell.abilities[0]
            self.assertEqual((5, 216), (ability.target, ability.projectile))
            for opcode in (45, 141, 60, 142):
                effects = spell.find_effects(opcode=opcode)
                self.assertTrue(effects)
                for effect in effects:
                    stun_visual = effect.opcode == 141 or (effect.opcode == 142 and effect.parameter2 == 55)
                    duration = 6 if effect.opcode == 45 or stun_visual else 12
                    self.assertEqual((0, duration, 2, 1), (
                        effect.timing, effect.duration, effect.target,
                        effect.resist_dispel,
                    ))
            stun = spell.find_effects(opcode=45)[0]
            self.assertEqual((1, -4), (stun.save_type, stun.save_bonus))
            miscast = spell.find_effects(opcode=60)
            self.assertEqual([0, 1], [effect.parameter2 for effect in miscast])
            self.assertEqual([(25, 0), (25, 0)], [
                (effect.parameter1, effect.save_type) for effect in miscast
            ])
            self.assertEqual(3, spell.find_effects(opcode=269)[0].duration)

            data = output.read_bytes()
            description = tlk_string(
                root / "dialog.tlk", struct.unpack_from("<I", data, 0x50)[0]
            )
            for phrase in (
                "save vs. spells at -4 or be stunned for one round",
                "all targets are deafened for two rounds",
                "25% chance to miscast any spells",
                "Only the caster is immune",
            ):
                self.assertIn(phrase, description)
            source = SOURCE.read_text(encoding="utf-8")
            kit_line = next(line for line in source.splitlines() if line.startswith("THUNDERCLAP:"))
            self.assertEqual(description.split("\n", 1)[1], kit_line.split(": ", 1)[1])

            clab = clab_rows(root / "override" / "c0sdrum.2da")
            grants = [
                level for row in clab.values() for level, value in enumerate(row, 1)
                if value == "GA_C0SDRUM4"
            ]
            self.assertEqual([10], grants)

    def test_only_six_durations_two_miscast_values_and_text_references_change(self) -> None:
        with self.installed() as root:
            override = root / "override"
            output = (override / "c0sdrum4.spl").read_bytes()
            expected = bytearray((STORM / "c0sdrum4.spl").read_bytes())
            changes = 0
            for offset in effect_offsets(expected):
                opcode = struct.unpack_from("<H", expected, offset)[0]
                parameter2 = struct.unpack_from("<I", expected, offset + 8)[0]
                duration = struct.unpack_from("<I", expected, offset + 0x0E)[0]
                if duration == 60:
                    stun_visual = opcode == 141 or (opcode == 142 and parameter2 == 55)
                    duration = 6 if opcode == 45 or stun_visual else 12
                    struct.pack_into("<I", expected, offset + 0x0E, duration)
                    changes += 1
                if opcode == 60:
                    struct.pack_into("<I", expected, offset + 4, 25)
            self.assertEqual(6, changes)
            for offset in (0x08, 0x0C, 0x50):
                expected[offset : offset + 4] = output[offset : offset + 4]
            self.assertEqual(expected, output)
            for path in STORM.iterdir():
                if path.name.lower() == "c0sdrum4.spl":
                    continue
                expected = bytearray(path.read_bytes())
                actual = (override / path.name).read_bytes()
                if path.name.lower() in ("c0sdrum3.spl", "c0sdruhl.spl"):
                    # The existing installer assigns names/descriptions here.
                    for offset in (0x08, 0x0C, 0x50):
                        expected[offset : offset + 4] = actual[offset : offset + 4]
                self.assertEqual(expected, actual, path.name)
            self.assertEqual(
                {path.name.lower() for path in STORM.iterdir()} | {"unrelated.txt"},
                {path.name.lower() for path in override.iterdir()},
            )


if __name__ == "__main__":
    unittest.main()
