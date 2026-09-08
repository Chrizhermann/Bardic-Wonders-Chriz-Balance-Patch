from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from .abettor_hla.ie_resources import parse_spl
from .abettor_hla.test_tail_patch_integration import (
    tlk_string,
    tlk_with_original_description,
)


ROOT = Path(__file__).resolve().parents[1]
SPELLS = ROOT / "BardicWonders" / "Skald" / "spells"
SKALD_TPA = ROOT / "BardicWonders" / "lib" / "skald.tpa"
RESISTANCES = (27, 28, 29, 30, 31, 86, 87, 88, 89)


def ability_effect_bytes(data: bytes) -> list[bytes]:
    ability_offset = struct.unpack_from("<I", data, 0x64)[0]
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    count, first = struct.unpack_from("<HH", data, ability_offset + 0x1E)
    return [
        data[effect_offset + index * 0x30 : effect_offset + (index + 1) * 0x30]
        for index in range(first, first + count)
    ]


class SkaldWarsongTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.game = Path(cls.directory.name)
        cls.override = cls.game / "override"
        shutil.copytree(SPELLS, cls.override)
        (cls.game / "dialog.tlk").write_bytes(tlk_with_original_description())

        # Execute the real installer actions, without loading unrelated kit setup.
        source = SKALD_TPA.read_text(encoding="utf-8")
        start = source.index("// CHRIZ BALANCE: Warsong of the Undying.")
        end = source.index(
            "INCLUDE ~%MOD_FOLDER%/effects/combat_casting.tpa~", start
        )
        (cls.game / "warsong.tp2").write_text(
            "BACKUP ~backup~\nAUTHOR ~test~\nBEGIN ~Warsong regression~\n"
            + source[start:end],
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                str(ROOT / "Setup-BardicWonders.exe"),
                "--no-auto-tp2",
                "--noautoupdate",
                "--nogame",
                "--search", "override",
                "--tlkin", "dialog.tlk",
                "--tlkout", "dialog.tlk",
                "--no-exit-pause",
                "--language", "0",
                "--force-install", "0",
                "warsong.tp2",
            ],
            cwd=cls.game,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode or "SUCCESSFULLY INSTALLED" not in result.stdout:
            raise AssertionError(result.stdout + result.stderr)

    def test_shared_song_has_requested_bonuses_without_self_duplicates(self) -> None:
        song = parse_spl(self.override / "c0skd02a.SPL")
        for opcode, bonus in ((0, 5), *((op, 15) for op in RESISTANCES)):
            with self.subTest(opcode=opcode):
                effects = song.find_effects(opcode=opcode, target=2)
                self.assertEqual(1, len(effects))
                self.assertEqual(bonus, effects[0].parameter1)
                self.assertEqual((), song.find_effects(opcode=opcode, target=1))
        for opcode in (278, 73):
            with self.subTest(opcode=opcode):
                effects = song.find_effects(opcode=opcode, target=2)
                self.assertEqual(1, len(effects))
                self.assertEqual(3, effects[0].parameter1)

    def test_other_song_bytes_are_preserved(self) -> None:
        before = (SPELLS / "c0skd02a.SPL").read_bytes()
        after = (self.override / "c0skd02a.SPL").read_bytes()
        self.assertEqual(before[:0x72], after[:0x72])
        ability_offset = struct.unpack_from("<I", before, 0x64)[0]
        self.assertEqual(1, struct.unpack_from("<H", before, 0x68)[0])
        before_ability = bytearray(before[ability_offset : ability_offset + 0x28])
        after_ability = bytearray(after[ability_offset : ability_offset + 0x28])
        self.assertEqual(
            struct.unpack_from("<H", before_ability, 0x1E)[0] - 5,
            struct.unpack_from("<H", after_ability, 0x1E)[0],
        )
        before_ability[0x1E:0x20] = after_ability[0x1E:0x20]
        self.assertEqual(before_ability, after_ability)

        # Global casting effects precede the ability's effects in this asset.
        effect_offset = struct.unpack_from("<I", before, 0x6A)[0]
        first_effect = struct.unpack_from("<H", before_ability, 0x20)[0]
        self.assertEqual(
            before[effect_offset : effect_offset + first_effect * 0x30],
            after[effect_offset : effect_offset + first_effect * 0x30],
        )
        originals = [
            effect for effect in ability_effect_bytes(before)
            if not (
                struct.unpack_from("<H", effect)[0] in (0, 86, 87, 88, 89)
                and effect[2] == 1
            )
        ]
        retained = ability_effect_bytes(after)
        self.assertEqual(len(originals), len(retained))
        changed = {(278, 2), (73, 2)}
        for original, actual in zip(originals, retained):
            key = (struct.unpack_from("<H", original)[0], original[2])
            with self.subTest(opcode=key[0], target=key[1]):
                if key in changed:
                    # Only parameter 1 may change; timing, flags and every other
                    # byte must survive. The numerical values are checked above.
                    self.assertEqual(original[:4] + original[8:], actual[:4] + actual[8:])
                else:
                    self.assertEqual(original, actual)
        self.assertEqual(len(before) - 5 * 0x30, len(after))

    def test_installed_description_matches_effects_and_preserves_hla_behavior(self) -> None:
        before = bytearray((SPELLS / "c0skd02.spl").read_bytes())
        after = (self.override / "c0skd02.spl").read_bytes()
        for offset in (0x08, 0x0C):
            strref = struct.unpack_from("<I", after, offset)[0]
            self.assertEqual("Warsong of the Undying", tlk_string(self.game / "dialog.tlk", strref))
        description = tlk_string(
            self.game / "dialog.tlk", struct.unpack_from("<I", after, 0x50)[0]
        )
        for text in (
            "a 5-point bonus to <PRO_HISHER> Armor Class and a 15% bonus to all resistances",
            "a +3 bonus to hit and damage rolls, a +5 bonus to Armor Class, +15% to all resistances",
            "immunity to fear, stun, and confusion, and Haste while the song is active",
            "This ability replaces the current Bard Song.",
        ):
            self.assertIn(text, description)
        for offset in (0x08, 0x0C, 0x50):
            before[offset : offset + 4] = after[offset : offset + 4]
        self.assertEqual(before, after)

        self.assertEqual(
            {path.name.casefold() for path in SPELLS.iterdir()},
            {path.name.casefold() for path in self.override.iterdir()},
        )
        for path in SPELLS.iterdir():
            if path.name.casefold() not in ("c0skd02.spl", "c0skd02a.spl"):
                with self.subTest(resource=path.name):
                    self.assertEqual(path.read_bytes(), (self.override / path.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
