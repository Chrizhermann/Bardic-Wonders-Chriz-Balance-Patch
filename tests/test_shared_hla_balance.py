"""Run the shared HLA resource installation with WeiDU in disposable fixtures."""

from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.abettor_hla.ie_resources import parse_spl
from tests.jester.test_weidu_integration import original_tlk, tlk_string
from tests.test_dancer_balance import effect_offsets


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
SOURCE = MOD / "hlas"


def snapshot(path: Path) -> dict[str, bytes]:
    return {p.name.upper(): p.read_bytes() for p in path.iterdir() if p.is_file()}


class SharedHlaBalanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="bard-hla-balance-")
        self.addCleanup(self.directory.cleanup)
        self.game = Path(self.directory.name)
        self.override = self.game / "override"
        self.override.mkdir()
        shutil.copytree(SOURCE, self.game / "BardicWonders" / "hlas")
        (self.override / "PROJECTL.IDS").write_text("IDS V1.0\n1 ARROW\n")
        (self.override / "MISSILE.IDS").write_text("IDS V1.0\n1 ARROW\n")
        (self.override / "UNRELATED.TXT").write_bytes(b"untouched\x00\xff")
        prior = bytearray((SOURCE / "c0bwhl4.spl").read_bytes())
        prior[-1] ^= 0x5A
        (self.override / "c0bwhl4.spl").write_bytes(prior)
        # A minimal KEY enables WeiDU's real IDS lookup for ADD_PROJECTILE.
        # All fixture resources live in override; there are no game archives.
        (self.game / "chitin.key").write_bytes(b"KEY V1  " + struct.pack("<IIII", 0, 0, 24, 24))
        (self.game / "dialog.tlk").write_bytes(original_tlk())
        self.before = snapshot(self.override)
        self.sources_before = snapshot(self.game / "BardicWonders" / "hlas")
        # Execute the entire production resource sequence, including registered
        # projectiles and descriptions. HLA table registration is outside this
        # resource fixture, and is unchanged by the balance corrections.
        source = (MOD / "lib" / "hlas.tpa").read_text(encoding="utf-8")
        actions = source.split("ACTION_IF FILE_EXISTS_IN_GAME ~LUC0AURA.2DA~", 1)[0]
        (self.game / "test.tp2").write_text(
            "BACKUP ~backup~\nAUTHOR ~test~\nLANGUAGE ~English~ ~english~\n"
            "BEGIN ~Shared HLA balance fixture~\n"
            "OUTER_SPRINT MOD_FOLDER ~BardicWonders~\n" + actions,
            encoding="utf-8",
        )
        self.weidu("install")

    def weidu(self, operation: str) -> None:
        options = {
            "install": ["--force-install-list", "0"],
            "uninstall": ["--force-uninstall-list", "0"],
            "reinstall": ["--force-uninstall-list", "0", "--force-install-list", "0"],
        }[operation]
        result = subprocess.run(
            [str(ROOT / "Setup-BardicWonders.exe"), "--no-auto-tp2", "--noautoupdate",
             "--game", str(self.game), "--tlkin", "dialog.tlk",
             "--tlkout", "dialog.tlk", "--no-exit-pause", "--language", "0",
             "test.tp2", *options],
            cwd=self.game, capture_output=True, text=True, timeout=30,
        )
        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        if operation != "uninstall":
            self.assertIn("SUCCESSFULLY INSTALLED", output)

    def description(self, name: str) -> str:
        data = (self.override / name).read_bytes()
        return tlk_string(self.game / "dialog.tlk", struct.unpack_from("<I", data, 0x50)[0])

    def test_legionnaire_uses_additive_accuracy_and_preserves_other_effects(self) -> None:
        actual = self.override / "c0bwhl4.spl"
        effect, = parse_spl(actual).find_effects(opcode=54)
        self.assertEqual((4, 0, 60, 2),
                         (effect.parameter1, effect.parameter2, effect.duration, effect.target))
        expected = bytearray((SOURCE / actual.name).read_bytes())
        output = actual.read_bytes()
        for offset in (0x08, 0x50):
            expected[offset:offset + 4] = output[offset:offset + 4]
        for offset in effect_offsets(expected):
            if struct.unpack_from("<H", expected, offset)[0] == 54:
                struct.pack_into("<ii", expected, offset + 4, 4, 0)
        self.assertEqual(bytes(expected), output)
        text = self.description(actual.name)
        self.assertIn("a +4 bonus to hit and damage", text)
        self.assertIn("This ability may be selected three times.", text)

    def test_hymn_halves_on_save_without_reverse_hp_drain(self) -> None:
        actual = self.override / "c0bwhl6b.spl"
        effect, = parse_spl(actual).find_effects(opcode=12)
        self.assertEqual((6, 10, 1, 256),
                         (effect.dice_count, effect.dice_size, effect.save_type, effect.special))
        expected = bytearray((SOURCE / actual.name).read_bytes())
        for offset in effect_offsets(expected):
            if struct.unpack_from("<H", expected, offset)[0] == 12:
                struct.pack_into("<I", expected, offset + 0x2C, 256)
        self.assertEqual(bytes(expected), actual.read_bytes())
        self.assertEqual((SOURCE / "c0bwhl6a.spl").read_bytes(),
                         (self.override / "c0bwhl6a.spl").read_bytes())
        self.assertIn("Save vs. Spell for half", self.description("c0bwhl6.spl"))

    def test_resonating_uses_two_six_sided_dice_and_preserves_stun(self) -> None:
        actual = self.override / "c0bwhl2b.spl"
        spell = parse_spl(actual)
        effect, = spell.find_effects(opcode=12)
        self.assertEqual((2, 6), (effect.dice_count, effect.dice_size))
        expected = bytearray((SOURCE / actual.name).read_bytes())
        output = actual.read_bytes()
        ability = struct.unpack_from("<I", expected, 0x64)[0]
        # The real ADD_PROJECTILE assigns an install-local identifier.
        expected[ability + 0x26:ability + 0x28] = output[ability + 0x26:ability + 0x28]
        for offset in effect_offsets(expected):
            if struct.unpack_from("<H", expected, offset)[0] == 12:
                struct.pack_into("<II", expected, offset + 0x1C, 2, 6)
        self.assertEqual(bytes(expected), output)
        stun, = spell.find_effects(opcode=45)
        self.assertEqual((10, 6, 4, -2),
                         (stun.probability1, stun.duration, stun.save_type, stun.save_bonus))
        self.assertEqual((SOURCE / "c0bwhl2.spl").read_bytes()[0x72:],
                         (self.override / "c0bwhl2.spl").read_bytes()[0x72:])

    def test_reinstall_and_uninstall_preserve_resources_and_original_strings(self) -> None:
        installed = snapshot(self.override)
        self.weidu("reinstall")
        self.assertEqual(installed, snapshot(self.override))
        self.assertEqual(self.sources_before, snapshot(self.game / "BardicWonders" / "hlas"))
        self.weidu("uninstall")
        self.assertEqual(self.before, snapshot(self.override))
        self.assertEqual("Original Jester description", tlk_string(self.game / "dialog.tlk", 0))


if __name__ == "__main__":
    unittest.main()
