"""Exercise the production Dancer resource actions with real WeiDU in temp dirs.

This covers resource installation, not ADD_KIT_EX or live engine acceptance.
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


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
WEIDU = ROOT / "Setup-BardicWonders.exe"
DANCER = MOD / "dancer"


def file_snapshot(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix().lower(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def effect_offsets(data: bytes) -> list[int]:
    """Include casting effects as well as each ability's effect list."""
    abilities = struct.unpack_from("<I", data, 0x64)[0]
    count = struct.unpack_from("<H", data, 0x68)[0]
    effects = struct.unpack_from("<I", data, 0x6A)[0]
    first, length = struct.unpack_from("<HH", data, 0x6E)
    indices = set(range(first, first + length))
    for index in range(count):
        length, first = struct.unpack_from("<HH", data, abilities + index * 0x28 + 0x1E)
        indices.update(range(first, first + length))
    return [effects + index * 0x30 for index in sorted(indices)]


def clab_rows(path: Path) -> dict[str, list[str]]:
    lines = path.read_text(encoding="ascii").splitlines()
    return {tokens[0]: tokens[1:] for line in lines[3:] if (tokens := line.split())}


class DancerBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (MOD / "lib" / "dancer.tpa").read_text(encoding="utf-8")

    def resource_actions(self, *, rr: bool) -> str:
        # Run the actual first COPY and balance include, and the actual later
        # song normalization. Re-copying the unbalanced source here regresses
        # the installed-song assertions even if the library itself is correct.
        prefix = self.source.split("COPY_EXISTING ~LUBA0.2DA~", 1)[0]
        self.assertIn("INCLUDE ~%MOD_FOLDER%/lib/dancer_balance.tpa~", prefix)
        normalization = re.search(
            r"^COPY(?:_EXISTING)?\s+~[^~]*c0dancso\.spl~\s+~[^~]+~"
            r"\s+LPF ALTER_EFFECT\b.*?^\s*END\b",
            self.source,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(normalization, "production normal-song action missing")
        rr_copies = re.findall(
            r"^COPY\s+~%MOD_FOLDER%/dancer/rr~\s+~override~",
            self.source,
            re.IGNORECASE | re.MULTILINE,
        )
        self.assertEqual(2, len(rr_copies))
        return "\n".join(
            [prefix]
            + ([rr_copies[0]] if rr else [])
            + [normalization.group(0)]
            + ([rr_copies[1]] if rr else [])
        )

    def weidu(self, root: Path, operation: str = "install") -> None:
        result = subprocess.run(
            [
                str(WEIDU), "--no-auto-tp2", "--noautoupdate", "--nogame",
                "--search", "override", "--no-exit-pause", "--language", "0",
                f"--force-{operation}", "0", "testmod/setup-test.tp2",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    @contextmanager
    def installed(self, *, rr: bool = False):
        original_sources = file_snapshot(DANCER)
        with tempfile.TemporaryDirectory(prefix="dancer-balance-") as directory:
            root = Path(directory)
            fixture_mod = root / "testmod"
            shutil.copytree(DANCER, fixture_mod / "dancer")
            (fixture_mod / "lib").mkdir()
            shutil.copy2(MOD / "lib" / "dancer_balance.tpa", fixture_mod / "lib")
            override = root / "override"
            override.mkdir()
            # Preserve a pre-existing overridden resource, including bytes that
            # differ from the shipped source, and an unrelated file on uninstall.
            previous = bytearray((DANCER / "c0dance1.spl").read_bytes())
            previous[-1] ^= 0x5A
            (override / "c0dance1.spl").write_bytes(previous)
            (override / "other.txt").write_bytes(b"Unrelated fixture resource\n")
            before_override = file_snapshot(override)
            before_fixture_sources = file_snapshot(fixture_mod / "dancer")
            (fixture_mod / "setup-test.tp2").write_text(
                "BACKUP ~testmod/backup~\nAUTHOR ~test~\n"
                "LANGUAGE ~English~ ~english~\n"
                "BEGIN ~Dancer balance integration test~ DESIGNATED 0\n"
                "OUTER_SPRINT MOD_FOLDER ~testmod~\n"
                + self.resource_actions(rr=rr) + "\n",
                encoding="utf-8",
            )
            self.weidu(root)
            yield root
            self.assertEqual(before_fixture_sources, file_snapshot(fixture_mod / "dancer"))
            self.weidu(root, "uninstall")
            self.assertEqual(before_override, file_snapshot(override))
        self.assertEqual(original_sources, file_snapshot(DANCER))

    def assert_parameter_changes_only(
        self, output: Path, changes: dict[int, list[int]], *, normalize: bool = False
    ) -> None:
        expected = bytearray((DANCER / output.name.lower()).read_bytes())
        counts = dict.fromkeys(changes, 0)
        for offset in effect_offsets(expected):
            opcode = struct.unpack_from("<H", expected, offset)[0]
            if opcode in changes:
                index = counts[opcode]
                self.assertLess(index, len(changes[opcode]))
                struct.pack_into("<i", expected, offset + 4, changes[opcode][index])
                counts[opcode] += 1
            if normalize:
                expected[offset + 3] = 0
                expected[offset + 0x0C] = 10
                struct.pack_into("<I", expected, offset + 0x0E, 100)
                struct.pack_into("<I", expected, offset + 0x24, 0)
        self.assertEqual({opcode: len(values) for opcode, values in changes.items()}, counts)
        self.assertEqual(bytes(expected), output.read_bytes(), output.name)

    def test_balance_is_installed_before_the_kit_consumes_the_clab(self) -> None:
        include = self.source.index("INCLUDE ~%MOD_FOLDER%/lib/dancer_balance.tpa~")
        self.assertLess(self.source.index("COPY ~%MOD_FOLDER%/dancer~ ~override~"), include)
        self.assertLess(include, self.source.index("LAF ADD_KIT_EX"))
        self.assertRegex(self.source, r"clab_path\s*=\s*~override/C0DANCE\.2da~")

    def test_base_ac_halves_the_bonus_instead_of_the_absolute_ac(self) -> None:
        with self.installed() as root:
            output = root / "override" / "c0dance1.spl"
            spell = parse_spl(output)
            self.assertEqual([1, 10, 20, 30, 40], [a.required_level for a in spell.abilities])
            self.assertEqual(
                [9, 9, 8, 8, 7],
                [e.parameter1 for a in spell.abilities for e in a.effects if e.opcode == 0],
            )
            self.assert_parameter_changes_only(output, {0: [9, 9, 8, 8, 7]})

    def test_missile_ac_is_half_the_cumulative_bonus_at_every_level(self) -> None:
        with self.installed() as root:
            before = clab_rows(DANCER / "c0dance.2da")
            after = clab_rows(root / "override" / "c0dance.2da")
            self.assertEqual(before.keys(), after.keys())
            before_total = after_total = 0
            for level in range(1, 41):
                before_total += sum(row[level - 1] == "AP_C0DANCE2" for row in before.values())
                after_total += sum(row[level - 1] == "AP_C0DANCE2" for row in after.values())
                with self.subTest(level=level):
                    self.assertEqual(before_total // 2, after_total)
            self.assertEqual(
                [5, 15, 25, 35],
                [i + 1 for i, value in enumerate(after["ABILITY2"]) if value == "AP_C0DANCE2"],
            )
            for label, row in before.items():
                self.assertEqual(len(row), len(after[label]))
                for index, cell in enumerate(row):
                    if cell != "AP_C0DANCE2":
                        self.assertEqual(cell, after[label][index], (label, index + 1))
                    else:
                        expected = cell if index + 1 in (5, 15, 25, 35) else "****"
                        self.assertEqual(expected, after[label][index], (label, index + 1))
            self.assertEqual(
                [line.split() for line in (DANCER / "c0dance.2da").read_text().splitlines()[:3]],
                [line.split() for line in (root / "override" / "c0dance.2da").read_text().splitlines()[:3]],
            )
            self.assertEqual(
                (DANCER / "c0dance2.spl").read_bytes(),
                (root / "override" / "c0dance2.spl").read_bytes(),
            )

    def test_every_normal_song_header_retains_balance_after_normalization(self) -> None:
        with self.installed() as root:
            output = root / "override" / "c0dancso.spl"
            spell = parse_spl(output)
            self.assertEqual([1, 6, 11, 16, 21], [a.required_level for a in spell.abilities])
            self.assertEqual([1, 2, 3, 4, 5], [e.parameter1 for e in spell.find_effects(opcode=0)])
            for ability in spell.abilities:
                for effect in ability.effects:
                    self.assertEqual((10, 100, 0, 0), (effect.timing, effect.duration, effect.power, effect.save_type))
            self.assert_parameter_changes_only(output, {0: [1, 2, 3, 4, 5]}, normalize=True)

    def test_enhanced_song_matches_level_21_hit_and_both_damage_bonuses(self) -> None:
        with self.installed() as root:
            output = root / "override" / "c0dancs2.spl"
            enhanced = parse_spl(output)
            normal = parse_spl(root / "override" / "c0dancso.spl").abilities[-1]
            expected_hit = next(e.parameter1 for e in normal.effects if e.opcode == 278)
            expected_damage = next(e.parameter1 for e in normal.effects if e.opcode == 73)
            self.assertEqual((5, 5), (expected_hit, expected_damage))
            for opcode, expected in ((0, 10), (278, expected_hit), (285, expected_damage), (286, expected_damage)):
                self.assertEqual([expected], [e.parameter1 for e in enhanced.find_effects(opcode=opcode)])
            self.assert_parameter_changes_only(output, {0: [10], 278: [5], 285: [5], 286: [5]})

    def test_hla_switch_proc_penalty_and_unrelated_resources_are_preserved(self) -> None:
        with self.installed() as root:
            override = root / "override"
            changed = {"c0dance.2da", "c0dance1.spl", "c0dancso.spl", "c0dancs2.spl"}
            for path in DANCER.iterdir():
                if path.is_file() and path.name.lower() not in changed:
                    self.assertEqual(path.read_bytes(), (override / path.name).read_bytes(), path.name)
            switch = parse_spl(override / "c0danchl.spl").find_effects(opcode=251)
            self.assertEqual(["C0DANCS2"], [e.resource for e in switch])
            proc = parse_spl(override / "c0dancs2.spl").find_effects(opcode=146, resource="C0DANCE3")
            self.assertEqual([(5, 0)], [(e.probability1, e.probability2) for e in proc])
            penalties = parse_spl(override / "c0dance3.spl").find_effects(opcode=0)
            self.assertGreater(len(penalties), 0)
            self.assertTrue(all(e.parameter1 == -4 for e in penalties))

    def test_rogue_rebalancing_resource_copies_keep_all_balance_values(self) -> None:
        with self.installed(rr=True) as root:
            override = root / "override"
            self.assertEqual((DANCER / "RR" / "c0dns.spl").read_bytes(), (override / "c0dns.spl").read_bytes())
            self.assert_parameter_changes_only(override / "c0dance1.spl", {0: [9, 9, 8, 8, 7]})
            self.assert_parameter_changes_only(override / "c0dancso.spl", {0: [1, 2, 3, 4, 5]}, normalize=True)
            self.assert_parameter_changes_only(override / "c0dancs2.spl", {0: [10], 278: [5], 285: [5], 286: [5]})
            rows = clab_rows(override / "c0dance.2da")
            self.assertEqual([5, 15, 25, 35], [i + 1 for i, value in enumerate(rows["ABILITY2"]) if value == "AP_C0DANCE2"])


if __name__ == "__main__":
    unittest.main()
