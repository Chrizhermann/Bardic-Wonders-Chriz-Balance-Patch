"""Real-WeiDU tests of the kit descriptions that list granted spells.

The production Troubadour, Darkbloom and Deathsinger descriptions and their
C0_BW_NAME_KIT_SPELLS calls run against synthetic spell copies whose names are
vanilla, Spell Revisions-like, translated, added in the same component (as the
bundled spells are) or missing. The tests verify the installed description,
unchanged other strings, reinstall and uninstall. The spell copies themselves
are covered by the priest-spell import tests; ADD_KIT_EX and the game engine
are not run.
"""
from __future__ import annotations

from pathlib import Path
import re
import tempfile
import unittest

from tests.spell_fixtures import (
    MOD, NONE, Ability, Fx, Spell, copy_libraries, file_snapshot, make_game, run_weidu,
    tlk_string,
)


KITS = {
    "troubadour.tpa": ("c0_trb", [f"C0TRBS{n}" for n in range(1, 7)]),
    "darkbloom.tpa": ("c0_bdd", [f"C0BDDS{n}" for n in range(1, 8)]),
    "deathsinger.tpa": ("c0_des", [f"C0DESP{n}" for n in range(1, 7)]),
}
FILL = "// Name the granted spells in the kit description"
VANILLA = {
    "C0TRBS1": "Cure Light Wounds", "C0TRBS2": "Aid", "C0TRBS3": "Cure Medium Wounds",
    "C0TRBS4": "Cure Serious Wounds", "C0TRBS5": "Mass Cure", "C0TRBS6": "Heal",
    "C0BDDS1": "Curse", "C0BDDS2": "Beast Claw", "C0BDDS3": "Mold Touch",
    "C0BDDS4": "Thorn Spray", "C0BDDS5": "Insect Plague", "C0BDDS6": "Fire Seeds",
    "C0BDDS7": "Mist of Eldath",
    "C0DESP1": "Doom", "C0DESP2": "Death Armor", "C0DESP3": "Bestow Curse",
    "C0DESP4": "Cloak of Fear", "C0DESP5": "Slay Living", "C0DESP6": "Destruction",
}
# Spell Revisions renames the cures in place; Mist of Eldath shares a name
# string that reads Healing Mist in the inspected installations.
SPELL_REVISIONS = VANILLA | {"C0TRBS3": "Cure Serious Wounds", "C0TRBS4": "Cure Critical Wounds",
                             "C0BDDS7": "Healing Mist"}
TRANSLATED = VANILLA | {"C0TRBS1": "Leichte Wunden heilen", "C0TRBS6": "Heilung",
                        "C0BDDS3": "Schimmelberührung", "C0BDDS7": "治愈之雾",
                        "C0DESP2": "Todesrüstung", "C0DESP6": "Zerstörung"}
# Bundled copies get their names in the same component.
NAMED_DURING_INSTALL = ("C0TRBS6", "C0BDDS7", "C0DESP2")


def production(kit: str) -> tuple[str, str, str]:
    """Return the kit's description definition, its placeholder text and its
    spell-name call, as written in the production source."""
    text = (MOD / "lib" / kit).read_text(encoding="utf-8")
    var, _spells = KITS[kit]
    definition = re.search(rf"OUTER_SET {var}_help = RESOLVE_STR_REF\(~(.*?)~\)\n", text, re.S)
    call = re.search(rf"{FILL}.*?\nLAF C0_BW_NAME_KIT_SPELLS [^\n]*\n", text, re.S)
    if not definition or not call:
        raise AssertionError(f"{kit}: description or spell-name call not found")
    return definition[0], definition[1], call[0]


def normalized(text: str) -> str:
    return text.replace("\r\n", "\n")


class KitSpellNameTests(unittest.TestCase):
    def test_descriptions_name_every_granted_spell_after_it_is_final(self):
        for kit, (var, spells) in KITS.items():
            with self.subTest(kit=kit):
                source = (MOD / "lib" / kit).read_text(encoding="utf-8")
                _definition, text, call = production(kit)
                self.assertEqual(sorted(f"<{spell}>" for spell in spells),
                                 sorted(re.findall(r"<C0[A-Z0-9]+>", text)))
                self.assertIn(f"    help          = {var}_help\n", source)
                self.assertIn(f"INT_VAR description = {var}_help STR_VAR spells = {var}_kit_spells END",
                              call)
                # No granted spell is copied or patched after its name is read.
                after = source[source.index(call) + len(call):]
                for spell in spells:
                    self.assertNotIn(spell.lower(), after.lower(), spell)

    def build(self, root: Path, names: dict[str, str | None]) -> tuple[Path, list[str]]:
        strings = ["", "Unrelated string", ""]
        name_refs = {}
        for spell, name in names.items():
            if name is None or spell in NAMED_DURING_INSTALL:
                continue
            strings.append(name)
            name_refs[spell] = len(strings) - 1
        override = make_game(root, strings)
        for spell, name in names.items():
            # Missing names: no strref, the reserved strref 0, an empty string.
            ref = {None: NONE, "": 2}.get(name, name_refs.get(spell, NONE))
            if name is None and spell.startswith("C0DESP"):
                ref = 0
            effects = (Fx(12, parameter2=0x100000, dice_count=1, dice_size=4),)
            (override / f"{spell}.SPL").write_bytes(Spell((Ability(effects),), name=ref).pack())
        mod = root / "BardicWonders"
        copy_libraries(mod, "kit_strref.tpa")
        definitions = "".join(production(kit)[0] for kit in KITS)
        renames = "".join(f"COPY_EXISTING ~{spell}.SPL~ ~override~\n  SAY NAME1 ~{names[spell]}~\n"
                          for spell in NAMED_DURING_INSTALL if names[spell])
        calls = "".join(production(kit)[2] for kit in KITS)
        report = "PRINT ~descriptions:" + "".join(f" %{var}_help%" for var, _s in KITS.values()) + "~\n"
        (root / "test.tp2").write_text(
            "BACKUP ~BardicWonders/backup~\nAUTHOR ~test~\n"
            "ALWAYS\n  INCLUDE ~BardicWonders/lib/kit_strref.tpa~\nEND\n"
            "BEGIN ~Kit spell names~ DESIGNATED 0\n" + definitions + renames + calls + report,
            encoding="utf-8",
        )
        return override, strings

    def descriptions(self, output: str) -> list[int]:
        match = re.search(r"descriptions: (\d+) (\d+) (\d+)", output)
        self.assertIsNotNone(match, output)
        return [int(value) for value in match.groups()]

    def assert_named(self, root: Path, refs: list[int], names: dict[str, str]):
        for kit, ref in zip(KITS, refs):
            text = production(kit)[1]
            for spell in KITS[kit][1]:
                text = text.replace(f"<{spell}>", names[spell])
            self.assertEqual(normalized(text), normalized(tlk_string(root / "dialog.tlk", ref)), kit)

    def install(self, names: dict[str, str | None]):
        directory = tempfile.TemporaryDirectory(prefix="bw-kit-spell-names-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        override, strings = self.build(root, names)
        before = file_snapshot(override)
        output = run_weidu(root, "test.tp2", install=[0])
        refs = self.descriptions(output)
        for ref, string in enumerate(strings):
            self.assertEqual(string, tlk_string(root / "dialog.tlk", ref))  # Other strings unchanged.
        return root, override, before, output, refs

    def test_descriptions_show_installed_names(self):
        for label, names in (("vanilla", VANILLA), ("spell revisions", SPELL_REVISIONS),
                             ("translated", TRANSLATED)):
            with self.subTest(names=label):
                root, override, before, output, refs = self.install(names)
                self.assertIn("SUCCESSFULLY INSTALLED", output, output)
                self.assertNotRegex(output, r"INSTALLED WITH WARNINGS|has no name")
                self.assert_named(root, refs, names)
                if label == "spell revisions":
                    installed = file_snapshot(override)
                    # A reinstall in one WeiDU run gives each description a new
                    # string; the earlier one gets its placeholder text back.
                    output = run_weidu(root, "test.tp2", uninstall=[0], install=[0])
                    self.assertIn("SUCCESSFULLY INSTALLED", output, output)
                    refs = self.descriptions(output)
                    self.assert_named(root, refs, names)
                    self.assertEqual(installed, file_snapshot(override))
                    run_weidu(root, "test.tp2", uninstall=[0])
                    self.assertEqual(before, file_snapshot(override))
                    for kit, ref in zip(KITS, refs):  # WeiDU restores the placeholder text.
                        self.assertEqual(normalized(production(kit)[1]),
                                         normalized(tlk_string(root / "dialog.tlk", ref)))

    def test_unnamed_copy_warns_and_shows_its_file_name(self):
        names = VANILLA | {"C0TRBS1": None, "C0BDDS1": "", "C0DESP1": None}
        root, _override, _before, output, refs = self.install(names)
        self.assertIn("INSTALLED WITH WARNINGS", output, output)
        for spell in ("C0TRBS1", "C0BDDS1", "C0DESP1"):
            self.assertIn(f"{spell}.SPL has no name, so the kit description shows its file name.", output)
        self.assert_named(root, refs, VANILLA | {spell: spell for spell in ("C0TRBS1", "C0BDDS1", "C0DESP1")})


if __name__ == "__main__":
    unittest.main()
