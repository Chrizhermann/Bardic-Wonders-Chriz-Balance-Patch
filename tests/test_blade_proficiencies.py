"""Exercise Blade's production cap actions with real WeiDU in temporary dirs.

The tests cover semantic table matching, real/varied SPL records, preservation,
repeat application and uninstall. They do not run a game or migrate characters.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.abettor_hla.test_tail_patch_integration import (
    tlk_string,
    tlk_with_original_description,
)
from tests.test_dancer_balance import effect_offsets, file_snapshot


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
HELPER = MOD / "lib" / "blade_proficiencies.tpa"
SPELL = MOD / "Blade" / "spells" / "c0bld00.spl"
GROUPS = {
    "BASTARDSWORD": 89, "LONGSWORD": 90, "SHORTSWORD": 91, "AXE": 92,
    "TWOHANDEDSWORD": 93, "KATANA": 94, "SCIMITARWAKISASHININJATO": 95,
    "DAGGER": 96, "SPEAR": 98, "HALBERD": 99, "2WEAPON": 114,
}


def table(*, reordered: bool = False, amount: int = 5) -> bytes:
    columns = ["ID", "NAME_REF", "DESC_REF", "FIGHTER", "BLADE", "OTHER_KIT"]
    rows = [("SPEAR", 3), ("AXE", 6), *GROUPS.items(),
            ("WARHAMMER", 97), ("2HANDED", 111), ("SINGLEWEAPON", 113),
            ("SWORDANDSHIELD", 112), ("EXTRA20", 134)]
    if reordered:
        columns = ["OTHER_KIT", "DESC_REF", "BLADE", "ID", "FIGHTER", "NAME_REF"]
        rows = list(reversed(rows))
    text = ["2DA V1.0", "0", " ".join(columns)]
    for index, (name, identifier) in enumerate(rows):
        values = dict(ID=str(identifier), NAME_REF=str(1000 + index),
                      DESC_REF=str(2000 + index), FIGHTER="5", BLADE=str(amount),
                      OTHER_KIT="4")
        text.append(" ".join([name, *(values[c] for c in columns)]))
    return ("\n".join(text) + "\n").encode("ascii")


def cells(data: bytes) -> tuple[list[str], list[list[str]]]:
    lines = [line.split() for line in data.decode("ascii").splitlines() if line.strip()]
    return lines[2], lines[3:]


def expected_spell(data: bytes) -> bytes:
    expected = bytearray(data)
    for offset in effect_offsets(data):
        opcode = struct.unpack_from("<H", data, offset)[0]
        amount, kind = struct.unpack_from("<II", data, offset + 4)
        if opcode == 233 and kind == 114 and amount > 3:
            struct.pack_into("<I", expected, offset + 4, 3)
    return bytes(expected)


def varied_spell() -> bytes:
    """Rebuild slices from the shipped file with extra/reordered headers/effects."""
    data = SPELL.read_bytes()
    abilities = struct.unpack_from("<I", data, 0x64)[0]
    effects = struct.unpack_from("<I", data, 0x6A)[0]
    headers, slices = [], []
    for index in (2, 0, 1):
        header = bytearray(data[abilities + 40 * index:abilities + 40 * (index + 1)])
        count, first = struct.unpack_from("<HH", header, 0x1E)
        records = [bytearray(data[effects + 48 * i:effects + 48 * (i + 1)])
                   for i in range(first, first + count)]
        # Unrelated marker effects: a weapon grant and a style increment.
        # This does not model an alternative implementation of the owned SET
        # grant, which remains direct in this private, bundled resource.
        # Also add another SET without relying on its old value.
        grant = next(r for r in records if struct.unpack_from("<H", r)[0] == 233)
        other = bytearray(grant)
        struct.pack_into("<II", other, 4, 5, 89)
        increment = bytearray(grant)
        struct.pack_into("<II", increment, 4, 2, 0x10000 | 114)
        extra = bytearray(grant)
        struct.pack_into("<I", extra, 4, 7)
        records = [other, *reversed(records), increment, extra]
        headers.append(header)
        slices.append(records)
    # A visual-only ability is valid: the patch owns grants, not header count.
    headers.append(bytearray(headers[0]))
    slices.append([bytearray(slices[0][2])])
    struct.pack_into("<H", slices[-1][0], 0, 142)
    global_grant = bytearray(slices[0][-1])
    struct.pack_into("<I", global_grant, 4, 6)
    records = [global_grant]
    for header, ability_effects in zip(headers, slices):
        struct.pack_into("<HH", header, 0x1E, len(ability_effects), len(records))
        records.extend(ability_effects)
    head = bytearray(data[:0x72])
    # Padding exercises offsets rather than the shipped contiguous layout.
    new_abilities = 0x80
    new_effects = new_abilities + 40 * len(headers) + 16
    struct.pack_into("<IHIHH", head, 0x64, new_abilities, len(headers), new_effects, 0, 1)
    return (bytes(head) + b"\xA5" * (new_abilities - len(head))
            + b"".join(headers) + b"\x5A" * 16 + b"".join(records)
            + b"preserve trailing metadata")


class BladeProficiencyTests(unittest.TestCase):
    def run_weidu(self, root: Path, operation: str = "install") -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(ROOT / "Setup-BardicWonders.exe"), "--no-auto-tp2", "--noautoupdate",
             "--nogame", "--search", "override", "--no-exit-pause", "--language", "0",
             "--tlkin", "dialog.tlk", "--tlkout", "dialog.tlk",
             "testmod/setup-test.tp2", f"--force-{operation}-list", "0"],
            cwd=root, text=True, capture_output=True, check=False, timeout=60,
        )

    @contextmanager
    def fixture(self, *, table_data: bytes | None = None, spell_data: bytes | None = None,
                repeats: int = 1, production: bool = False):
        with tempfile.TemporaryDirectory(prefix="blade-proficiencies-") as directory:
            root = Path(directory)
            mod, override = root / "testmod", root / "override"
            (mod / "lib").mkdir(parents=True)
            override.mkdir()
            shutil.copy2(HELPER, mod / "lib")
            (override / "weapprof.2da").write_bytes(table() if table_data is None else table_data)
            (override / "c0bld00.spl").write_bytes(SPELL.read_bytes() if spell_data is None else spell_data)
            (override / "unrelated.txt").write_bytes(b"Preserve this file.\n")
            (root / "dialog.tlk").write_bytes(tlk_with_original_description())
            before = file_snapshot(override)
            include = "INCLUDE ~%MOD_FOLDER%/lib/blade_proficiencies.tpa~\n"
            actions = include * repeats
            if production:
                shutil.copytree(MOD / "Blade", mod / "Blade")
                source = (MOD / "lib" / "blade.tpa").read_text(encoding="utf-8")
                self.assertEqual(1, source.count(include.strip()))
                prefix = source.split("LAF ~GET_KIT_STRREF~", 1)[0]
                description = source[source.index("STRING_SET_EVALUATE kit_strref"):]
                description = description.split("COPY_EXISTING ~luabbr.2da~", 1)[0]
                actions = prefix + "OUTER_SET kit_strref = 0\n" + description + include
            (mod / "setup-test.tp2").write_text(
                "BACKUP ~testmod/backup~\nAUTHOR ~test~\n"
                "BEGIN ~Blade proficiency test~ DESIGNATED 0\n"
                "OUTER_SPRINT MOD_FOLDER ~testmod~\n" + actions,
                encoding="utf-8",
            )
            yield root, before

    def assert_installed(self, root: Path) -> None:
        result = self.run_weidu(root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SUCCESSFULLY INSTALLED", result.stdout)

    def assert_table(self, before: bytes, after: bytes) -> None:
        columns, expected = cells(before)
        actual_columns, actual = cells(after)
        self.assertEqual(columns, actual_columns)
        blade, identifier = columns.index("BLADE") + 1, columns.index("ID") + 1
        for row in expected:
            if row[0] in GROUPS and int(row[identifier]) == GROUPS[row[0]]:
                row[blade] = "0" if row[0] == "2WEAPON" else "2"
        self.assertEqual(expected, actual)

    def assert_uninstall(self, root: Path, before: dict[str, bytes]) -> None:
        result = self.run_weidu(root, "uninstall")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SUCCESSFULLY REMOVED", result.stdout)
        self.assertEqual(before, file_snapshot(root / "override"))

    def test_table_layouts_old_caps_and_spell_preservation(self) -> None:
        for reordered, amount in ((False, 1), (False, 5), (True, 0), (True, 7)):
            with self.subTest(reordered=reordered, amount=amount):
                data = table(reordered=reordered, amount=amount)
                with self.fixture(table_data=data) as (root, before):
                    self.assert_installed(root)
                    self.assert_table(data, (root / "override/weapprof.2da").read_bytes())
                    self.assertEqual(expected_spell(SPELL.read_bytes()),
                                     (root / "override/c0bld00.spl").read_bytes())
                    self.assert_uninstall(root, before)

    def test_extra_reordered_global_and_ability_effects_preserved(self) -> None:
        data = varied_spell()
        with self.fixture(spell_data=data) as (root, before):
            self.assert_installed(root)
            self.assertEqual(expected_spell(data), (root / "override/c0bld00.spl").read_bytes())
            self.assert_uninstall(root, before)

    def test_effect_table_before_abilities_is_supported(self) -> None:
        data = SPELL.read_bytes()
        ability_start = struct.unpack_from("<I", data, 0x64)[0]
        effect_start = struct.unpack_from("<I", data, 0x6A)[0]
        effects = data[effect_start:]
        reordered = bytearray(data[:0x72] + effects + data[ability_start:effect_start])
        struct.pack_into("<I", reordered, 0x64, 0x72 + len(effects))
        struct.pack_into("<I", reordered, 0x6A, 0x72)
        with self.fixture(spell_data=bytes(reordered)) as (root, before):
            self.assert_installed(root)
            self.assertEqual(expected_spell(reordered), (root / "override/c0bld00.spl").read_bytes())
            self.assert_uninstall(root, before)

    def test_numeric_ids_allow_hex_and_case_insensitive_symbols(self) -> None:
        data = table().replace(b"AXE 92 ", b"axe 0x5c ").replace(b" BLADE ", b" blade ")
        with self.fixture(table_data=data) as (root, before):
            self.assert_installed(root)
            columns, rows = cells((root / "override/weapprof.2da").read_bytes())
            blade = columns.index("blade") + 1
            self.assertEqual("2", next(r[blade] for r in rows if r[0] == "axe"))
            self.assertEqual("5", next(r[blade] for r in rows if r[:2] == ["AXE", "6"]))
            self.assert_uninstall(root, before)

    def test_already_capped_lower_grants_and_repeated_application(self) -> None:
        data = bytearray(expected_spell(varied_spell()))
        for offset in effect_offsets(data):
            if struct.unpack_from("<H", data, offset)[0] == 233 and struct.unpack_from("<I", data, offset + 8)[0] == 114:
                struct.pack_into("<I", data, offset + 4, 2)
        results = []
        for repeats in (1, 2):
            with self.fixture(spell_data=bytes(data), repeats=repeats) as (root, before):
                self.assert_installed(root)
                self.assertEqual(bytes(data), (root / "override/c0bld00.spl").read_bytes())
                results.append(file_snapshot(root / "override"))
                self.assert_uninstall(root, before)
        self.assertEqual(results[0], results[1])

    def test_production_copy_wiring_text_and_unrelated_resources(self) -> None:
        original = file_snapshot(MOD / "Blade")
        with self.fixture(production=True) as (root, before):
            self.assert_installed(root)
            for name, data in original.items():
                actual = (root / "override" / Path(name).name).read_bytes()
                self.assertEqual(expected_spell(data) if name == "spells/c0bld00.spl" else data, actual, name)
            description = tlk_string(root / "dialog.tlk", 0)
            self.assertIn("Specialization (two slots)", description)
            for name in ("bastard swords", "long swords", "short swords", "two-handed swords",
                         "katanas", "scimitars", "wakizashis", "ninjatōs", "daggers", "axes", "spears", "halberds"):
                self.assertIn(name, description)
            self.assertIn("Gains Mastery in Two-Weapon Style at 1st level", description)
            self.assertNotIn("Grand Mastery", description)
            self.assert_uninstall(root, before)
        self.assertEqual(original, file_snapshot(MOD / "Blade"))

    def test_missing_and_ambiguous_table_targets_roll_back(self) -> None:
        baseline = table().decode("ascii")
        variants = {
            "missing BLADE": baseline.replace(" BLADE ", " REMOVED "),
            "duplicate BLADE": baseline.replace(" OTHER_KIT", " BLADE"),
            "missing ID": baseline.replace("\nID ", "\nREMOVED "),
            "missing weapon": baseline.replace("HALBERD 99", "REMOVED 99"),
            "wrong ID": baseline.replace("HALBERD 99", "HALBERD 120"),
            "duplicate active weapon": baseline + next(l for l in baseline.splitlines() if l.startswith("AXE 92 ")) + "\n",
        }
        for name, text in variants.items():
            with self.subTest(name=name), self.fixture(table_data=text.encode("ascii")) as (root, before):
                result = self.run_weidu(root)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", result.stdout)
                self.assertIn("Blade proficiencies: WEAPPROF.2DA", result.stdout)
                self.assertEqual(before, file_snapshot(root / "override"))

    def test_missing_style_and_corrupt_spells_roll_back_table_too(self) -> None:
        no_grant = bytearray(SPELL.read_bytes())
        for offset in effect_offsets(no_grant):
            if struct.unpack_from("<H", no_grant, offset)[0] == 233:
                struct.pack_into("<I", no_grant, offset + 8, 89)
        offsets = bytearray(SPELL.read_bytes())
        struct.pack_into("<I", offsets, 0x64, len(offsets) + 1)
        overlap = bytearray(SPELL.read_bytes())
        struct.pack_into("<I", overlap, 0x6A, 0x72)
        signature = bytearray(SPELL.read_bytes())
        signature[:8] = b"EFF V2.0"
        for data in (bytes(no_grant), bytes(offsets), bytes(overlap), bytes(signature), SPELL.read_bytes()[:30], SPELL.read_bytes()[:-1]):
            with self.subTest(length=len(data)), self.fixture(spell_data=data) as (root, before):
                result = self.run_weidu(root)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", result.stdout)
                self.assertIn("Blade proficiencies: C0BLD00.SPL", result.stdout)
                self.assertEqual(before, file_snapshot(root / "override"))


if __name__ == "__main__":
    unittest.main()
