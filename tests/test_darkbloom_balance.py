"""Run Darkbloom's production resource actions with WeiDU in a disposable fixture.

This verifies copied resources, projectile registration, balance and rollback.
It does not exercise ADD_KIT_EX, priest-spell imports or the live game engine.
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
from tests.test_dancer_balance import effect_offsets, file_snapshot


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
RESOURCES = MOD / "darkbloom"
WEIDU = ROOT / "Setup-BardicWonders.exe"


class DarkbloomBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (MOD / "lib" / "darkbloom.tpa").read_text(encoding="utf-8")

    def resource_actions(self) -> str:
        prefix = self.source.split("COPY_EXISTING ~LUBA0.2DA~", 1)[0]
        start = self.source.index("COPY_EXISTING ~C0BDDHL.spl~")
        end = self.source.index("// Curse", start)
        actions = prefix + self.source[start:end]
        include = "INCLUDE ~%MOD_FOLDER%/lib/darkbloom_balance.tpa~"
        self.assertIn(include, actions)
        # The production include must follow every later COPY of a patched file.
        for match in re.finditer(
            r"^COPY\s+~%MOD_FOLDER%/darkbloom/(?:C0BDD#1|C0BDD#BS|C0BDD#S2)\.spl~",
            self.source, re.MULTILINE | re.IGNORECASE,
        ):
            self.assertLess(match.start(), self.source.index(include))
        return actions

    def weidu(self, root: Path, *, uninstall: bool = False, reinstall: bool = False) -> None:
        operations = ["--force-uninstall-list", "0"] if uninstall or reinstall else []
        if not uninstall:
            operations += ["--force-install-list", "0"]
        result = subprocess.run(
            [str(WEIDU), "--no-auto-tp2", "--noautoupdate", "--nogame",
             "--search", "override", "--search-ids", "override", "--tlkin", "dialog.tlk", "--tlkout", "dialog.tlk",
             "--no-exit-pause", "--language", "0", "testmod/setup-test.tp2", *operations],
            cwd=root, text=True, capture_output=True, check=False, timeout=60,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        if not uninstall:
            self.assertIn("SUCCESSFULLY INSTALLED", result.stdout, result.stdout + result.stderr)

    @contextmanager
    def installed(self):
        original_sources = file_snapshot(RESOURCES)
        with tempfile.TemporaryDirectory(prefix="darkbloom-balance-") as directory:
            root = Path(directory)
            mod = root / "testmod"
            shutil.copytree(RESOURCES, mod / "darkbloom")
            (mod / "lib").mkdir()
            shutil.copy2(MOD / "lib" / "darkbloom_balance.tpa", mod / "lib")
            override = root / "override"
            override.mkdir()
            for name in ("projectl.ids", "missile.ids"):
                (override / name).write_text("IDS V1.0\n0 NONE\n", encoding="ascii")
            previous = bytearray((RESOURCES / "c0bdd#1.spl").read_bytes())
            previous[-1] ^= 0x5A
            (override / "c0bdd#1.spl").write_bytes(previous)
            (override / "unrelated.txt").write_bytes(b"Unrelated fixture resource\n")
            before_override = file_snapshot(override)
            (root / "dialog.tlk").write_bytes(tlk_with_original_description())
            (mod / "setup-test.tp2").write_text(
                "BACKUP ~testmod/backup~\nAUTHOR ~test~\n"
                "BEGIN ~Darkbloom balance resource test~ DESIGNATED 0\n"
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
            self.assertEqual(original_sources, file_snapshot(mod / "darkbloom"))
        self.assertEqual(original_sources, file_snapshot(RESOURCES))

    def test_poison_and_backstab_match_documented_chance_duration_and_dice(self) -> None:
        with self.installed() as root:
            override = root / "override"
            poison = parse_spl(override / "c0bdd#1.spl").find_effects(opcode=25)
            self.assertEqual(1, len(poison))
            self.assertEqual(
                (1, 2, 0, 5, 10, 0, 1, 3, 1),
                (poison[0].parameter1, poison[0].parameter2, poison[0].timing,
                 poison[0].duration, poison[0].probability1, poison[0].probability2,
                 poison[0].save_type, poison[0].save_bonus, poison[0].resist_dispel),
            )
            icon = parse_spl(override / "c0bdd#1.spl").find_effects(opcode=142, parameter2=6)
            self.assertEqual(1, len(icon))
            self.assertEqual((5, 10, 0, 1, 3),
                             (icon[0].duration, icon[0].probability1, icon[0].probability2,
                              icon[0].save_type, icon[0].save_bonus))
            acid = parse_spl(override / "c0bdd#bs.spl").find_effects(opcode=12)
            self.assertEqual(1, len(acid))
            self.assertEqual((2, 8, 65536), (acid[0].dice_count, acid[0].dice_size, acid[0].parameter2))
            for name in ("c0bdd#1.spl", "c0bdd#bs.spl"):
                expected = bytearray((RESOURCES / name).read_bytes())
                actual = (override / name).read_bytes()
                for offset in effect_offsets(expected):
                    opcode = struct.unpack_from("<H", expected, offset)[0]
                    if opcode == 25 or (opcode == 142 and struct.unpack_from("<I", expected, offset + 8)[0] == 6):
                        expected[offset + 0x12] = 10
                        struct.pack_into("<I", expected, offset + 0x0E, 5)
                    elif opcode == 12:
                        struct.pack_into("<II", expected, offset + 0x1C, 2, 8)
                if name == "c0bdd#1.spl":
                    ability = struct.unpack_from("<I", expected, 0x64)[0]
                    projectile_id = next(
                        int(line.split()[0]) for line in (override / "projectl.ids").read_text().splitlines()
                        if len(line.split()) == 2 and line.split()[1].upper() == "C0BDD#1"
                    ) + 1
                    self.assertEqual(projectile_id, struct.unpack_from("<H", actual, ability + 0x26)[0])
                    struct.pack_into("<H", expected, ability + 0x26, projectile_id)
                    # The production action assigns the two display strings.
                    for offset in (0x08, 0x50):
                        expected[offset:offset + 4] = actual[offset:offset + 4]
                self.assertEqual(bytes(expected), actual, name)

    def test_hla_reduces_mr_and_arcane_level_without_changing_other_effects(self) -> None:
        with self.installed() as root:
            path = root / "override" / "c0bdd#s2.spl"
            song = parse_spl(path)
            self.assertEqual([(-50, 0)], [(e.parameter1, e.parameter2) for e in song.find_effects(opcode=166)])
            self.assertEqual([(3, 0, 6)], [(e.parameter1, e.parameter2, e.target) for e in song.find_effects(opcode=191)])
            self.assertEqual([(1, 0, 6)], [(e.parameter1, e.parameter2, e.target) for e in song.find_effects(opcode=189)])
            expected = bytearray((RESOURCES / path.name).read_bytes())
            for offset in effect_offsets(expected):
                opcode = struct.unpack_from("<H", expected, offset)[0]
                if opcode == 166:
                    struct.pack_into("<ii", expected, offset + 4, -50, 0)
                elif opcode == 191:
                    struct.pack_into("<i", expected, offset + 4, 3)
                elif opcode == 189:
                    struct.pack_into("<i", expected, offset + 4, 1)
            self.assertEqual(bytes(expected), path.read_bytes())
            hla = (root / "override" / "c0bddhl.spl").read_bytes()
            description = tlk_string(root / "dialog.tlk", struct.unpack_from("<I", hla, 0x50)[0])
            for phrase in ("arcane casting level by 3", "casting speed by 1", "50 percentage points", "Save vs. Spell at -6", "replaces the current Bard Song"):
                self.assertIn(phrase, description)
            switch = parse_spl(root / "override" / "c0bddhl.spl").find_effects(opcode=251)
            self.assertEqual(["C0BDD#S2"], [e.resource for e in switch])
            for name in ("c0bdd.2da", "c0bdd#2.spl", "c0bdd#3.spl", "c0bdd#4.spl"):
                self.assertEqual((RESOURCES / name).read_bytes(), (root / "override" / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
