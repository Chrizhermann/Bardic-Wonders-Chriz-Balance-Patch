"""Real-WeiDU tests of the Gallant (1012) and New Bard Spells (2008) integration.

Production slices of both components install in either order on synthetic
installations with vanilla-like and Spell Revisions-like priest spells. The
tests verify that both orders give the Gallant the same spells, kit table and
kit description, that uninstalling or reinstalling either component restores
the matching state, and that other tables and kit rows do not change. The
rows ADD_KIT_EX writes are simulated; the game engine is not run.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import tempfile
import unittest

from tests.spell_fixtures import (
    MOD, copy_libraries, file_snapshot, make_game, resource, run_weidu, section, spell_ids, tlk_string,
)
from tests.test_priest_spell_imports import NEW_BARD_SPELLS, source_spell


TP2 = "BardicWonders/Setup-BardicWonders.tp2"
GALLANT, SPELLS = 1012, 2008
# The bard spells the Gallant receives as priest spells (C0GALL3 grants C0GA*).
SHARED = ["101", "102", "103", "201", "202", "203", "301", "302", "401", "402", "403", "501", "502", "601"]
COPIES = {f"c0ga{number}.spl" for number in SHARED}
ADDED_LINE = "– Gains Bard-exclusive spells as priest spells."
CLAB = "2DA V1.0\n****\n" + " ".join(str(level) for level in range(1, 51)) + "\n"


def clab(rows: dict[str, dict[int, str]]) -> str:
    return CLAB + "".join(
        name + " " + " ".join(cells.get(level, "****") for level in range(1, 51)) + "\n"
        for name, cells in rows.items())


def rows(path: Path) -> list[list[str]]:
    return [line.split() for line in path.read_text(encoding="utf-8").splitlines()[3:] if line.split()]


class GallantNewSpellsTests(unittest.TestCase):
    def build(self, root: Path, variant: str) -> Path:
        names = ["", "Paladin help", "Troubadour help", "Bard help"]
        ids, spells = {}, {}
        for symbol, resref, _copy, _level, name in NEW_BARD_SPELLS:
            names.append(name)
            ids[symbol] = 1000 + int(resref[4:])
            spells[resref] = source_spell(resref, len(names) - 1, kind=resref, variant=variant)
        override = make_game(root, names)
        (override / "SPELL.IDS").write_text(spell_ids(ids), encoding="ascii")
        for resref, spell in spells.items():
            (override / f"{resref}.SPL").write_bytes(spell.pack())
        (override / "CLABPA01.2DA").write_text(clab({
            "ABILITY1": {1: "AP_C0PAL00", 3: "GA_SPCL122"}, "ABILITY2": {1: "AP_SPCL123"}}), encoding="ascii")
        # Other kits' tables: the integration must leave them alone.
        (override / "CLABBA01.2DA").write_text(clab({"ABILITY1": {1: "GA_SPCL900"}}), encoding="ascii")
        (override / "C0TRB.2DA").write_text(clab({"ABILITY1": {2: "GA_C0TRBS1"}, "ABILITY2": {1: "AP_C0GALL3"}}),
                                             encoding="ascii")
        (override / "CLASTEXT.2DA").write_text(
            "2DA V1.0\n-1\nCLASSID LOWER MIXED HELP DESC FALLEN FALLEN_NOTICE\n"
            "PALADIN 6 7 8 1 9 -1 -1\nC0_TROUBADOUR 5 7 8 2 9 -1 -1\n", encoding="ascii")
        (override / "KITLIST.2DA").write_text(
            "2DA V1.0\n0\nROWNAME LOWER MIXED HELP ABILITIES PROFICIENCY UNUSABLE CLASS\n"
            "0 RESERVE * * * * * * *\n1 C0_TROUBADOUR 7 8 2 C0TRB 0x00004000 0x00000000 5\n"
            "2 BARD_EXTRA 7 8 3 CLABBA01 0x00004000 0x00000000 5\n", encoding="ascii")
        (override / "UNRELATED.TXT").write_bytes(b"Unrelated fixture resource\x00\xff")

        mod = root / "BardicWonders"
        copy_libraries(mod, "functions.tph", "priest_spell_import.tpa", "gallant_new_spells.tpa")
        shutil.copytree(MOD / "gallant" / "spells", mod / "gallant" / "spells")
        shutil.copytree(MOD / "new_spells" / "spl", mod / "new_spells" / "spl")
        kit, new_spells = MOD / "lib" / "gallant.tpa", MOD / "lib" / "new_spells.tpa"
        tp2 = (MOD / "Setup-BardicWonders.tp2").read_text(encoding="utf-8")
        for library in ("priest_spell_import.tpa", "gallant_new_spells.tpa"):
            self.assertIn(f"INCLUDE ~%MOD_FOLDER%/lib/{library}~", tp2[:tp2.index("BEGIN ")])
        gallant = (
            section(kit, "COPY ~%MOD_FOLDER%/gallant/spells~ ~override~", "INCLUDE ~%MOD_FOLDER%/eeex/")
            + section(kit, "COPY_EXISTING ~CLABPA01.2DA~ ~OVERRIDE/C0GALLAN.2DA~", "LAF ADD_KIT_EX")
            # The CLASTEXT and KITLIST rows ADD_KIT_EX writes for the kit.
            + "OUTER_SET c0_test_help = RESOLVE_STR_REF (~%kit_description%~)\n"
              "APPEND ~CLASTEXT.2DA~ ~C0_GALLANT 6 7 8 %c0_test_help% 9 -1 -1~\n"
              "APPEND ~KITLIST.2DA~ ~3 C0_GALLANT 7 8 %c0_test_help% C0GALLAN 0x00004000 0x00000000 6~\n"
            + section(kit, "// New Bard Spells installed before this kit"))
        spells = (
            section(new_spells, "COPY ~%MOD_FOLDER%/NEW_SPELLS/SPL~ ~OVERRIDE~", "\n") + "\n"
            + section(new_spells, "// Priest spells shared with bards.",
                      "ACTION_IF NOT FILE_EXISTS_IN_GAME ~SPPR308C.ITM~")
            + section(new_spells, "// The Gallant integration runs"))
        (mod / "Setup-BardicWonders.tp2").write_text(
            "BACKUP ~BardicWonders/backup~\nAUTHOR ~test~\n"
            "ALWAYS\n  OUTER_SPRINT MOD_FOLDER ~BardicWonders~\n"
            "  INCLUDE ~BardicWonders/lib/functions.tph~\n"
            "  INCLUDE ~BardicWonders/lib/priest_spell_import.tpa~\n"
            "  INCLUDE ~BardicWonders/lib/gallant_new_spells.tpa~\nEND\n"
            f"BEGIN ~Gallant Paladin Kit~ DESIGNATED {GALLANT}\n{gallant}\n"
            f"BEGIN ~New Bard Spells~ DESIGNATED {SPELLS}\n{spells}\n"
            # Runs the integration again, as a reinstall cascade could.
            "BEGIN ~Repeat~ DESIGNATED 9000\nLAF C0_BW_GALLANT_NEW_SPELLS END\n",
            encoding="utf-8",
        )
        return override

    def weidu(self, root: Path, *, install=(), uninstall=()) -> str:
        output = run_weidu(root, TP2, install=install, uninstall=uninstall)
        self.assertNotRegex(output, r"\bERROR\b|INSTALLED WITH WARNINGS")
        if install:
            self.assertIn("SUCCESSFULLY INSTALLED", output, output)
        else:
            self.assertIn("SUCCESSFULLY REMOVED", output, output)
        return output

    def state(self, root: Path, override: Path) -> dict:
        """Override files with the kit's help strref resolved to text: strrefs
        depend on the order in which components added strings."""
        files = file_snapshot(override)
        help_text = {}
        # The HELP column follows CLASSID LOWER MIXED (CLASTEXT) or LOWER MIXED (KITLIST).
        for table, offset in (("CLASTEXT.2DA", 4), ("KITLIST.2DA", 3)):
            lines = files[table.lower()].decode("utf-8").split("\n")
            for index, line in enumerate(lines):
                cells = list(re.finditer(r"\S+", line))
                names = [cell[0] for cell in cells]
                if index >= 3 and "C0_GALLANT" in names:
                    cell = cells[names.index("C0_GALLANT") + offset]
                    help_text[table] = tlk_string(root / "dialog.tlk", int(cell[0]))
                    lines[index] = line[:cell.start()] + "<help>" + line[cell.end():]
            files[table.lower()] = "\n".join(lines).encode("utf-8")
        return {"files": files, "help": help_text}

    def scenario(self, variant: str, first: int, second: int):
        directory = tempfile.TemporaryDirectory(prefix="bw-gallant-spells-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        override = self.build(root, variant)
        states = {"none": self.state(root, override)}
        self.weidu(root, install=[first])
        states["first"] = self.state(root, override)
        self.weidu(root, install=[second])
        states["both"] = self.state(root, override)
        return root, override, states

    def assert_integrated(self, root: Path, override: Path, state: dict, before: dict) -> None:
        files = state["files"]
        self.assertEqual(set(), COPIES - files.keys())
        for number in SHARED:
            source = bytearray(files[f"c0bw{number}.spl"])
            source[0x1C:0x1E] = b"\x02\x00"  # Priest spell; all other bytes are New Bard Spells'.
            self.assertEqual(bytes(source), files[f"c0ga{number}.spl"], number)
        grants = [row for row in rows(resource(override, "C0GALLAN.2DA")) if "AP_C0GALL3" in row]
        self.assertEqual(1, len(grants))
        self.assertEqual(1, grants[0].index("AP_C0GALL3"))
        self.assertEqual(1, sum(row.count("AP_C0GALL3") for row in rows(resource(override, "C0GALLAN.2DA"))))
        # The placeholder becomes the added line; the rest of the help is unchanged.
        original = before["help"]["CLASTEXT.2DA"]
        self.assertIn("<BARDIC_SPELLS>", original)
        self.assertIn(state["help"]["CLASTEXT.2DA"],
                      [original.replace("<BARDIC_SPELLS>", newline + ADDED_LINE) for newline in ("\r\n", "\n")])
        self.assertEqual(state["help"]["CLASTEXT.2DA"], state["help"]["KITLIST.2DA"])

    def assert_unrelated_unchanged(self, initial: dict, state: dict) -> None:
        for name in ("clabba01.2da", "c0trb.2da", "clabpa01.2da", "unrelated.txt", "spell.ids"):
            self.assertEqual(initial["files"][name], state["files"][name], name)
        for table in ("clastext.2da", "kitlist.2da"):
            old = [line.split() for line in initial["files"][table].decode().splitlines()[3:]]
            new = [line.split() for line in state["files"][table].decode().splitlines()[3:]
                   if "C0_GALLANT" not in line]
            self.assertEqual(old, new, table)

    def check_variant(self, variant: str) -> None:
        root_a, override_a, kit_first = self.scenario(variant, GALLANT, SPELLS)
        root_b, override_b, spells_first = self.scenario(variant, SPELLS, GALLANT)
        initial = kit_first["none"]

        # Without the other component there is no integration.
        self.assertFalse(COPIES & kit_first["first"]["files"].keys())
        self.assertIn("<BARDIC_SPELLS>", kit_first["first"]["help"]["CLASTEXT.2DA"])
        self.assertFalse(COPIES & spells_first["first"]["files"].keys())
        self.assertNotIn("c0gallan.2da", spells_first["first"]["files"])

        # Both orders give the same integration.
        self.assert_integrated(root_a, override_a, kit_first["both"], kit_first["first"])
        self.assert_integrated(root_b, override_b, spells_first["both"], kit_first["first"])
        self.assertEqual(kit_first["both"], spells_first["both"])
        for state in (kit_first["first"], spells_first["first"], kit_first["both"]):
            self.assert_unrelated_unchanged(initial, state)

        # Repeating the integration changes nothing.
        self.weidu(root_a, install=[9000])
        self.assertEqual(kit_first["both"], self.state(root_a, override_a))
        self.weidu(root_a, uninstall=[9000])

        # Reinstalling either component, in either order, restores the same state.
        for root, override, both in ((root_a, override_a, kit_first), (root_b, override_b, spells_first)):
            for component in (GALLANT, SPELLS):
                self.weidu(root, install=[component])
                self.assertEqual(both["both"], self.state(root, override), (variant, component))

        # Uninstalling one component leaves exactly the other one's state.
        self.weidu(root_a, uninstall=[SPELLS])
        self.assertEqual(kit_first["first"], self.state(root_a, override_a))
        self.weidu(root_a, install=[SPELLS])
        self.weidu(root_a, uninstall=[GALLANT])
        self.assertEqual(spells_first["first"]["files"], self.state(root_a, override_a)["files"])
        self.weidu(root_b, uninstall=[GALLANT])
        self.assertEqual(spells_first["first"], self.state(root_b, override_b))
        self.weidu(root_b, install=[GALLANT])
        self.weidu(root_b, uninstall=[SPELLS])
        self.assertEqual(kit_first["first"]["files"], self.state(root_b, override_b)["files"])

        # A full uninstall restores the original files byte for byte.
        self.weidu(root_a, uninstall=[SPELLS])
        self.weidu(root_b, uninstall=[GALLANT])
        self.assertEqual(initial["files"], file_snapshot(override_a))
        self.assertEqual(initial["files"], file_snapshot(override_b))

    def test_vanilla_layout_is_order_independent(self):
        self.check_variant("vanilla")

    def test_spell_revisions_layout_is_order_independent(self):
        self.check_variant("sr")


if __name__ == "__main__":
    unittest.main()
