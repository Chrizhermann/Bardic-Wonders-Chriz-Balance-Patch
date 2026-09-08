"""Exercise Checkmate's production resource actions with disposable WeiDU.

The fixture verifies generated Intelligence variants, grant limits, text and
rollback. Kit registration and live engine behavior are outside its scope.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import re
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
RESOURCES = MOD / "strategist"
SOURCE = MOD / "lib" / "strategist.tpa"


class StrategistBalanceTests(unittest.TestCase):
    def resource_actions(self) -> str:
        source = SOURCE.read_text(encoding="utf-8")
        prefix = source.split("INCLUDE ~%MOD_FOLDER%/EFFECTS/ANALYZE.TPA~", 1)[0]
        intelligence_start = source.index("// INTELLIGENCE")
        intelligence_end = source.index("DEFINE_ACTION_FUNCTION cd_new_portrait_icon")
        checkmate_start = source.index("COPY_EXISTING ~C0STRA6.SPL~")
        checkmate_end = source.index("COPY_EXISTING ~C0STRH1.SPL~")
        # Run every Checkmate COPY, including the final generated variants.
        for match in re.finditer(r"^COPY[^\n]*C0STRA6", source, re.MULTILINE):
            self.assertTrue(checkmate_start <= match.start() < checkmate_end)
        return (
            prefix + source[intelligence_start:intelligence_end]
            + source[checkmate_start:checkmate_end]
        )

    def weidu(self, root: Path, *, reinstall: bool = False, uninstall: bool = False) -> None:
        operations = ["--force-uninstall-list", "0"] if reinstall or uninstall else []
        if not uninstall:
            operations += ["--force-install-list", "0"]
        result = subprocess.run(
            [str(ROOT / "Setup-BardicWonders.exe"),
             "--no-auto-tp2", "--noautoupdate", "--nogame",
             "--search", "override", "--tlkin", "dialog.tlk", "--tlkout", "dialog.tlk",
             "--no-exit-pause", "--language", "0", "testmod/setup-test.tp2", *operations],
            cwd=root, text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        marker = "SUCCESSFULLY REMOVED" if uninstall else "SUCCESSFULLY INSTALLED"
        self.assertIn(marker, result.stdout, result.stdout + result.stderr)

    @contextmanager
    def installed(self):
        before_sources = file_snapshot(RESOURCES)
        with tempfile.TemporaryDirectory(prefix="strategist-balance-") as directory:
            root = Path(directory)
            mod = root / "testmod"
            shutil.copytree(RESOURCES, mod / "strategist")
            override = root / "override"
            override.mkdir()
            rows = [f"{index} 0 0 0" for index in range(140)]
            rows[128] = "128_STAT_INT_GE 38 -1 4"
            rows[129] = "129_STAT_INT_LT 38 -1 2"
            (override / "splprot.2da").write_text(
                "2DA V1.0\n0\nSTAT VALUE RELATION\n" + "\n".join(rows) + "\n",
                encoding="ascii",
            )
            previous = bytearray((RESOURCES / "spells" / "C0STRA6.spl").read_bytes())
            previous[-1] ^= 0x5A
            (override / "C0STRA6.spl").write_bytes(previous)
            (override / "unrelated.txt").write_bytes(b"Unrelated fixture resource\n")
            before_override = file_snapshot(override)
            (root / "dialog.tlk").write_bytes(tlk_with_original_description())
            (mod / "setup-test.tp2").write_text(
                "BACKUP ~testmod/backup~\nAUTHOR ~test~\n"
                "BEGIN ~Strategist balance resource test~ DESIGNATED 0\n"
                "OUTER_SPRINT MOD_FOLDER ~testmod~\n" + self.resource_actions(),
                encoding="utf-8",
            )
            self.weidu(root)
            yield root
            installed_override = file_snapshot(override)
            self.weidu(root, reinstall=True)
            self.assertEqual(installed_override, file_snapshot(override))
            self.weidu(root, uninstall=True)
            self.assertEqual(before_override, file_snapshot(override))
            self.assertEqual(before_sources, file_snapshot(mod / "strategist"))
        self.assertEqual(before_sources, file_snapshot(RESOURCES))

    def test_every_final_variant_has_one_round_stun_and_capped_save(self) -> None:
        with self.installed() as root:
            override = root / "override"
            main = parse_spl(override / "C0STRA6.spl")
            self.assertEqual((4, 5, 158), (
                main.spell_type, main.abilities[0].target, main.abilities[0].projectile,
            ))
            self.assertEqual([(1, 10, 180, 2, 0)], [
                (effect.parameter2, effect.timing, effect.duration,
                 effect.resist_dispel, effect.save_type)
                for effect in main.find_effects(opcode=16)
            ])
            protections = main.find_effects(opcode=206)
            self.assertEqual(["SPRA301", "SPWI305", "SPCL521"], [e.resource for e in protections])
            self.assertEqual([(10, 180)] * 3, [(e.timing, e.duration) for e in protections])
            # The existing haste-expiration sound already occurs at 12 seconds.
            end_sound = main.find_effects(opcode=174, timing=4)
            self.assertEqual([12], [effect.duration for effect in end_sound])

            for intelligence, suffix in enumerate("ABCDEFGHIJ", 16):
                with self.subTest(intelligence=intelligence):
                    resref = f"C0STRA6{suffix}"
                    spell = parse_spl(override / f"{resref}.SPL")
                    self.assertEqual(159, spell.abilities[0].projectile)
                    self.assertEqual([(intelligence, 128, resref, 0)], [
                        (effect.parameter1, effect.parameter2, effect.resource, effect.save_type)
                        for effect in spell.find_effects(opcode=324)
                    ])
                    penalty = -min(intelligence - 16, 3)
                    self.assertEqual([(10, 90, 4, penalty, 2, 2)], [
                        (effect.timing, effect.duration, effect.save_type,
                         effect.save_bonus, effect.target, effect.resist_dispel)
                        for effect in spell.find_effects(opcode=45)
                    ])
                    icon = spell.find_effects(opcode=142, parameter2=55)
                    self.assertEqual([(10, 90, 4, penalty)], [
                        (effect.timing, effect.duration, effect.save_type, effect.save_bonus)
                        for effect in icon
                    ])
                    self.assertEqual({penalty}, {effect.save_bonus for effect in spell.effects})

    def test_intelligence_dispatch_daily_grant_and_descriptions(self) -> None:
        with self.installed() as root:
            override = root / "override"
            table = (override / "splprot.2da").read_text().splitlines()[3:]
            int_row = next(index for index, line in enumerate(table) if line.split()[0] == "C0HTINT")
            self.assertEqual(["38", "-1", "1"], table[int_row].split()[1:])
            main = parse_spl(override / "C0STRA6.spl")
            dispatch = main.find_effects(opcode=326)
            self.assertEqual([(17, 129, "C0STRA6A")] + [
                (intelligence, int_row, f"C0STRA6{suffix}")
                for intelligence, suffix in enumerate("BCDEFGHIJ", 17)
            ], [(effect.parameter1, effect.parameter2, effect.resource) for effect in dispatch])
            self.assertEqual({1}, {effect.target for effect in dispatch})
            self.assertEqual({0}, {effect.save_type for effect in dispatch})
            clab = clab_rows(override / "C0STRATE.2DA")
            self.assertEqual([20], [
                level for row in clab.values() for level, value in enumerate(row, 1)
                if value.upper() == "GA_C0STRA6"
            ])
            self.assertNotIn("C0STRA6", (override / "LUC0STRA.2DA").read_text().upper())
            data = (override / "C0STRA6.spl").read_bytes()
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            self.assertEqual(0, struct.unpack_from("<H", data, ability_offset + 0x12)[0])
            description = tlk_string(root / "dialog.tlk", struct.unpack_from("<I", data, 0x50)[0])
            for phrase in (
                "Saving Throw vs. Death", "maximum penalty of -3",
                "Stunned for one round", "Improved Haste for two rounds",
                "Intelligence equal to or greater than the strategist",
            ):
                self.assertIn(phrase, description)
            source = SOURCE.read_text(encoding="utf-8")
            kit_line = next(line for line in source.splitlines() if line.startswith("CHECKMATE:"))
            self.assertEqual(description.split("\n", 1)[1], kit_line.split(": ", 1)[1])
            self.assertIn("may use the Checkmate ability once per day", source)

    def test_only_approved_fields_and_existing_installer_fields_change(self) -> None:
        with self.installed() as root:
            override = root / "override"
            actual = (override / "C0STRA6.spl").read_bytes()
            expected = bytearray((RESOURCES / "spells" / "C0STRA6.spl").read_bytes())
            int_row = parse_spl(override / "C0STRA6.spl").find_effects(opcode=326)[1].parameter2
            for offset in effect_offsets(expected):
                opcode = struct.unpack_from("<H", expected, offset)[0]
                if opcode in (16, 206):
                    struct.pack_into("<I", expected, offset + 0x0E, 180)
                elif opcode == 326 and struct.unpack_from("<I", expected, offset + 8)[0] == 0:
                    struct.pack_into("<I", expected, offset + 8, int_row)
            for offset in (0x08, 0x0C, 0x50):
                expected[offset:offset + 4] = actual[offset:offset + 4]
            self.assertEqual(expected, actual)

            for intelligence, suffix in enumerate("ABCDEFGHIJ", 16):
                resref = f"C0STRA6{suffix}"
                expected = bytearray((RESOURCES / "spells" / "C0STRA6A.spl").read_bytes())
                for offset in effect_offsets(expected):
                    opcode = struct.unpack_from("<H", expected, offset)[0]
                    if opcode in (45, 142):
                        struct.pack_into("<I", expected, offset + 0x0E, 90)
                    elif opcode == 324:
                        struct.pack_into("<I", expected, offset + 4, intelligence)
                        expected[offset + 0x14:offset + 0x1C] = resref.encode().ljust(8, b"\0")
                    struct.pack_into("<i", expected, offset + 0x28, -min(intelligence - 16, 3))
                self.assertEqual(expected, (override / f"{resref}.SPL").read_bytes(), resref)

            for folder in ("2das", "spells"):
                for path in (RESOURCES / folder).iterdir():
                    if path.name.upper() in ("C0STRA6.SPL", "C0STRA6A.SPL"):
                        continue
                    self.assertEqual(path.read_bytes(), (override / path.name).read_bytes(), path.name)
            expected_names = {
                path.name.lower() for folder in ("2das", "spells")
                for path in (RESOURCES / folder).iterdir()
            } | {f"c0stra6{suffix}.spl" for suffix in "bcdefghij"} | {"splprot.2da", "unrelated.txt"}
            self.assertEqual(expected_names, {path.name.lower() for path in override.iterdir()})


if __name__ == "__main__":
    unittest.main()
