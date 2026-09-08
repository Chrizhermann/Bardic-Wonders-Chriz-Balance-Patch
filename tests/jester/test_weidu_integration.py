from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.abettor_hla.ie_resources import Spell, parse_spl


ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "BardicWonders"
WEIDU = ROOT / "Setup-BardicWonders.exe"
ORIGINAL_DESCRIPTION = "Original Jester description"


def original_tlk() -> bytes:
    text = ORIGINAL_DESCRIPTION.encode("ascii")
    entry = bytearray(0x1A)
    struct.pack_into("<H", entry, 0, 7)
    struct.pack_into("<II", entry, 0x12, 0, len(text))
    return b"TLK V1  " + struct.pack("<HII", 0, 1, 0x2C) + entry + text


def tlk_string(path: Path, strref: int) -> str:
    data = path.read_bytes()
    if data[:8] != b"TLK V1  ":
        raise AssertionError("invalid TLK signature")
    count, string_data = struct.unpack_from("<II", data, 0x0A)
    if not 0 <= strref < count:
        raise AssertionError(f"strref {strref} outside TLK with {count} entries")
    offset, length = struct.unpack_from("<II", data, 0x12 + strref * 0x1A + 0x12)
    return data[string_data + offset : string_data + offset + length].decode("utf-8")


def resource(root: Path, name: str) -> Path:
    matches = [path for path in (root / "override").iterdir() if path.name.upper() == name.upper()]
    if len(matches) != 1:
        raise AssertionError(f"expected one installed {name}, found {matches}")
    return matches[0]


def override_snapshot(root: Path) -> dict[str, bytes]:
    return {path.name.upper(): path.read_bytes() for path in (root / "override").iterdir()}


def make_fixture(root: Path) -> None:
    """Use the complete component and real donor SPLs; mock only game tables/TLK."""
    override = root / "override"
    library = root / "BardicWonders" / "lib"
    override.mkdir()
    library.mkdir(parents=True)
    shutil.copytree(MOD / "Jester", root / "BardicWonders" / "Jester")
    for name in ("jester.tpa", "kit_strref.tpa"):
        shutil.copy2(MOD / "lib" / name, library / name)
    (override / "KITLIST.2DA").write_text(
        "2DA V1.0\n*\n    ROWNAME LOWER MIXED HELP\n0   JESTER  0     0     0\n",
        encoding="ascii",
    )
    (override / "LUABBR.2DA").write_text(
        "2DA V1.0\n*\n       ABBREV\nBARD   BA0\nJESTER BA0\nSKALD  BA0\n",
        encoding="ascii",
    )
    (override / "LUBA0.2DA").write_text(
        "2DA V1.0\n*\n    ABILITY ICON STRREF MIN_LEV MAX_LEVEL NUM_ALLOWED PREREQUISITE EXCLUDED_BY\n"
        "0   AP_SPCL920 * * 1 99 1 * *\n1   AP_SPCL921 * * 1 99 1 * *\n",
        encoding="ascii",
    )
    # Exercise restoration of overwritten resources as well as deletion of new ones.
    shutil.copy2(MOD / "Jester" / "spells" / "SPCL751A.SPL", override / "SPCL751A.SPL")
    (override / "CLABBA03.2DA").write_bytes(b"Original CLAB table\r\n")
    (override / "UNRELATED.TXT").write_bytes(b"untouched fixture resource\x00\xff")
    (root / "dialog.tlk").write_bytes(original_tlk())
    (root / "Setup-JesterTest.tp2").write_text(
        "BACKUP ~BardicWonders/backup~\nAUTHOR ~test~\n"
        "LANGUAGE ~English~ ~english~\n"
        "BEGIN ~Jester integration test~ DESIGNATED 0\n"
        "INCLUDE ~BardicWonders/lib/kit_strref.tpa~\n"
        "INCLUDE ~BardicWonders/lib/jester.tpa~\n",
        encoding="ascii",
    )


def run_weidu(root: Path, operation: str = "install") -> subprocess.CompletedProcess[str]:
    operation_args = {
        "install": ["--force-install-list", "0"],
        "uninstall": ["--force-uninstall-list", "0"],
        "reinstall": ["--force-uninstall-list", "0", "--force-install-list", "0"],
    }[operation]
    return subprocess.run(
        [
            str(WEIDU), "--no-auto-tp2", "--noautoupdate", "--nogame",
            "--search", "override", "--tlkin", "dialog.tlk", "--tlkout", "dialog.tlk",
            "--no-exit-pause", "--language", "0", "Setup-JesterTest.tp2", *operation_args,
        ],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
        check=False,
    )


class JesterWeiduIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory(prefix="jester-weidu-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        make_fixture(cls.root)
        installed = run_weidu(cls.root)
        if installed.returncode != 0 or "SUCCESSFULLY INSTALLED" not in installed.stdout + installed.stderr:
            raise AssertionError(installed.stdout + installed.stderr)

    def spell(self, name: str) -> Spell:
        return parse_spl(resource(self.root, name))

    def description(self, name: str) -> str:
        data = resource(self.root, name).read_bytes()
        strref = struct.unpack_from("<I", data, 0x50)[0]
        return tlk_string(self.root / "dialog.tlk", strref)

    def test_normal_song_scaling_at_every_ability_tier(self) -> None:
        song = self.spell("SPCL751A.SPL")
        self.assertEqual([1, 10, 15, 20], [ability.required_level for ability in song.abilities])
        for ability, ac, miscast, crit in zip(song.abilities, (-2, -2, -3, -4), (12, 20, 27, 27), (0, 1, 1, 2)):
            with self.subTest(level=ability.required_level):
                self.assertEqual([ac], [e.parameter1 for e in ability.effects if e.opcode == 0 and e.target == 2])
                self.assertEqual({0: miscast, 1: miscast}, {e.parameter2: e.parameter1 for e in ability.effects if e.opcode == 60})
                self.assertEqual(crit, sum(e.parameter1 for e in ability.effects if e.opcode == 362))

    def test_hla_enemy_penalties_and_singer_defenses(self) -> None:
        song = self.spell("C0JES03A.SPL")
        self.assertEqual(1, len(song.abilities))
        self.assertEqual([-6], [e.parameter1 for e in song.find_effects(opcode=0, target=2)])
        self.assertEqual({0: 35, 1: 35}, {e.parameter2: e.parameter1 for e in song.find_effects(opcode=60)})
        self.assertEqual([3], [e.parameter1 for e in song.find_effects(opcode=362)])
        # General +5 and an additional missile-only +5 give +10 against ranged attacks.
        self.assertEqual({0: 5, 2: 5}, {e.parameter2: e.parameter1 for e in song.find_effects(opcode=0, target=1)})
        self.assertEqual([-20], [e.parameter1 for e in song.find_effects(opcode=301, target=2)])

    def test_heckle_all_tiers_are_spell_protection_susceptible_and_rebalanced(self) -> None:
        heckle = self.spell("C0JES01.SPL")
        self.assertEqual([1, 6, 12, 18, 24, 30, 36], [a.required_level for a in heckle.abilities])
        for ability in heckle.abilities:
            with self.subTest(level=ability.required_level):
                self.assertEqual({1}, {e.power for e in ability.effects})
                self.assertEqual([3], [e.parameter1 for e in ability.effects if e.opcode == 362])
                self.assertEqual({0: 40, 1: 40}, {e.parameter2: e.parameter1 for e in ability.effects if e.opcode == 60})
                berserk = [e for e in ability.effects if e.opcode == 3 or (e.opcode == 142 and e.parameter2 == 4)]
                self.assertEqual(2, len(berserk))
                for effect in berserk:
                    self.assertEqual(6, effect.duration)
                    self.assertEqual(2, effect.save_type)
                    self.assertEqual(-(ability.required_level // 6), effect.save_bonus)
                self.assertEqual({2}, {e.resist_dispel for e in ability.effects if e.opcode != 321})
                self.assertEqual({6}, {e.duration for e in ability.effects if e.opcode != 321})

    def test_song_and_heckle_preserve_unrequested_effect_fields(self) -> None:
        for name, mutable_opcodes in (("SPCL751A.SPL", {0, 60}), ("C0JES03A.SPL", {0, 60, 362}), ("C0JES01.SPL", {60, 362})):
            donor_path = next(path for path in (MOD / "Jester" / "spells").iterdir() if path.name.upper() == name)
            donor = parse_spl(donor_path)
            actual = self.spell(name)
            self.assertEqual(len(donor.abilities), len(actual.abilities))
            for old_ability, new_ability in zip(donor.abilities, actual.abilities):
                self.assertEqual(replace(old_ability, effects=()), replace(new_ability, effects=()))
                self.assertEqual(len(old_ability.effects), len(new_ability.effects))
                for old, new in zip(old_ability.effects, new_ability.effects):
                    with self.subTest(spell=name, level=old_ability.required_level, opcode=old.opcode):
                        ignored = {"parameter1": old.parameter1} if old.opcode in mutable_opcodes else {}
                        if name == "C0JES01.SPL":
                            ignored["power"] = old.power
                            if old.opcode == 3 or (old.opcode == 142 and old.parameter2 == 4):
                                ignored["duration"] = old.duration
                        self.assertEqual(old, replace(new, **ignored))

    def test_mad_ramble_granted_only_at_levels_11_15_19(self) -> None:
        lines = resource(self.root, "CLABBA03.2DA").read_text(encoding="ascii").splitlines()
        levels = lines[2].split()
        grants = [int(level) for line in lines[3:] for level, ability in zip(levels, line.split()[1:]) if ability == "GA_C0JES02"]
        self.assertEqual([11, 15, 19], grants)

    def test_installed_descriptions_match_the_mechanics(self) -> None:
        kit = tlk_string(self.root / "dialog.tlk", 0)
        for level, ac, miscast in ((1, 2, 12), (10, 2, 20), (15, 3, 27), (20, 4, 27)):
            self.assertRegex(kit, rf"{level}(?:st|th) level:.*?-{ac} penalty to Armor Class.*?{miscast}% chance")
        self.assertRegex(kit, r"11th level.*Mad Ramble.*15th and 19th level")
        for description in (kit, self.description("C0JES01.SPL")):
            self.assertIn("critical miss modifier by 3", description)
            self.assertIn("40% chance for spell failure", description)
            self.assertIn("berserk for 1 round", description)
            self.assertIn("spell protections", description)
        hla = self.description("C0JES03.SPL")
        for phrase in ("-6 penalty to all enemies' Armor Class", "35% chance", "critical miss modifier by 3", "bonus of 5 to Armor Class", "doubled to 10 against ranged attacks"):
            self.assertIn(phrase, hla)

    def test_casting_effects_and_mad_ramble_payload_are_preserved(self) -> None:
        for source in (MOD / "Jester" / "spells").iterdir():
            old = source.read_bytes()
            new = resource(self.root, source.name).read_bytes()
            old_offset = struct.unpack_from("<I", old, 0x6A)[0]
            new_offset = struct.unpack_from("<I", new, 0x6A)[0]
            old_first, old_count = struct.unpack_from("<HH", old, 0x6E)
            new_first, new_count = struct.unpack_from("<HH", new, 0x6E)
            with self.subTest(spell=source.name):
                self.assertEqual((old_first, old_count), (new_first, new_count))
                self.assertEqual(
                    old[old_offset + old_first * 0x30 : old_offset + (old_first + old_count) * 0x30],
                    new[new_offset + new_first * 0x30 : new_offset + (new_first + new_count) * 0x30],
                )
        self.assertEqual(
            parse_spl(MOD / "Jester" / "spells" / "c0jes02.SPL"),
            self.spell("C0JES02.SPL"),
        )

    def test_hla_remains_wired_to_jester_table_without_changing_other_kits(self) -> None:
        rows = dict(line.split() for line in resource(self.root, "LUABBR.2DA").read_text().splitlines()[3:])
        self.assertEqual({"BARD": "BA0", "JESTER": "BA2", "SKALD": "BA0"}, rows)
        table = resource(self.root, "LUBA2.2DA").read_text()
        self.assertIn("AP_C0JES03", table)
        self.assertIn("AP_SPCL921", table)
        self.assertNotIn("AP_SPCL920", table)

    def test_reinstall_is_stable_and_uninstall_restores_original_resources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="jester-uninstall-") as directory:
            root = Path(directory)
            make_fixture(root)
            before = override_snapshot(root)
            for install_index, operation in enumerate(("install", "reinstall")):
                result = run_weidu(root, operation)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("SUCCESSFULLY INSTALLED", result.stdout + result.stderr)
                if install_index == 0:
                    installed = override_snapshot(root)
                else:
                    self.assertEqual(installed, override_snapshot(root))
            result = run_weidu(root, "uninstall")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(before, override_snapshot(root))
            # WeiDU keeps unused appended TLK strings after uninstall; the prior entry must restore.
            self.assertEqual(ORIGINAL_DESCRIPTION, tlk_string(root / "dialog.tlk", 0))


if __name__ == "__main__":
    unittest.main()
