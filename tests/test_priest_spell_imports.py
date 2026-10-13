"""Real-WeiDU tests of the kit and New Bard Spells priest-spell copies.

The production Troubadour, Deathsinger and New Bard Spells import blocks run
against synthetic installations whose SPELL.IDS follows vanilla BG2:EE, Spell
Revisions (renamed cures, added self-references) and a layout where symbols
point to other SPPRxxx files. They verify spell identity, mechanics, type,
level and kit availability, failure rollback, reinstall and uninstall. They do
not run ADD_KIT_EX or the game engine.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
import tempfile
import unittest

from tests.spell_fixtures import (
    MOD, Ability, Fx, Spell, copy_libraries, file_snapshot, imported, make_game,
    resource, run_weidu, section, spell_ids, tlk_string,
)


# (symbol, vanilla resref, copy, copy level, name in the vanilla fixture)
TROUBADOUR = [
    ("CLERIC_CURE_LIGHT_WOUNDS", "SPPR103", "C0TRBS1", 1, "Cure Light Wounds"),
    ("CLERIC_AID", "SPPR201", "C0TRBS2", 2, "Aid"),
    ("CLERIC_CURE_MEDIUM_WOUNDS", "SPPR315", "C0TRBS3", 3, "Cure Medium Wounds"),
    ("CLERIC_CURE_SERIOUS_WOUNDS", "SPPR401", "C0TRBS4", 4, "Cure Serious Wounds"),
    ("CLERIC_MASS_CURE", "SPPR514", "C0TRBS5", 5, "Mass Cure"),
    ("CLERIC_HEAL", "SPPR607", "C0TRBS6", 6, "Heal"),
]
DEATHSINGER = [
    ("CLERIC_DOOM", "SPPR113", "C0DESP1", 1, "Doom"),
    ("CLERIC_CLOAK_OF_FEAR", "SPPR416", "C0DESP4", 4, "Cloak of Fear"),
    ("CLERIC_SLAY_LIVING", "SPPR511", "C0DESP5", 5, "Slay Living"),
]
NEW_BARD_SPELLS = [
    ("CLERIC_REMOVE_PARALYSIS", "SPPR308", "C0BW303", 3, "Remove Paralysis"),
    ("CLERIC_FREE_ACTION", "SPPR403", "C0BW401", 4, "Free Action"),
    ("CLERIC_DEFENSIVE_HARMONY", "SPPR406", "C0BW402", 4, "Defensive Harmony"),
    ("CLERIC_CHAOTIC_COMMANDS", "SPPR508", "C0BW501", 5, "Chaotic Commands"),
    ("CLERIC_WONDROUS_RECALL", "SPPR611", "C0BW602", 6, "Wondrous Recall"),
]
ALL = TROUBADOUR + DEATHSINGER + NEW_BARD_SPELLS
# Spell Revisions renames the level-3 and level-4 cures in place.
SR_NAMES = {"SPPR315": "Cure Serious Wounds", "SPPR401": "Cure Critical Wounds"}
# Kit tables grant the copies at these character levels.
KIT_TABLES = {
    MOD / "troubadour" / "c0trb.2da": {"GA_C0TRBS1": 2, "GA_C0TRBS2": 4, "GA_C0TRBS3": 7,
                                       "GA_C0TRBS4": 10, "GA_C0TRBS5": 13, "GA_C0TRBS6": 16},
    MOD / "deathsinger" / "c0deaths.2da": {"GA_C0DESP1": 2, "GA_C0DESP4": 10, "GA_C0DESP5": 13},
}


def clab_grants(path: Path) -> dict[str, int]:
    rows = [line.split() for line in path.read_text(encoding="ascii").splitlines()[3:]]
    return {cell: level for row in rows for level, cell in enumerate(row[1:], 1) if cell != "****"}


def source_spell(resref: str, name: int, *, kind: str, variant: str) -> Spell:
    """A small priest spell standing in for the vanilla spell ``kind``. Spell
    Revisions-like sources add self-references in every identity opcode, extra
    abilities and a casting slice."""
    main = [Fx(17, parameter1=8, dice_count=1, dice_size=8),
            Fx(142, parameter2=int(resref[4:]) % 50 + 1, duration=30)]
    # The same resref outside the identity opcodes must stay untouched.
    main.append(Fx(172, target=1, resource=resref))
    if kind in ("SPPR113", "SPPR406"):
        main.insert(0, Fx(321, resource=resref))  # Vanilla BG2:EE self-refresh.
    if kind == "SPPR611":
        main = [Fx(261, target=1, parameter1=5, parameter2=1), Fx(139, parameter1=0)]
    abilities = [Ability(tuple(main), icon=resref + "B", level=1)]
    casting: tuple[Fx, ...] = ()
    if variant == "sr":
        refresh = [Fx(321, resource=resref.lower()), Fx(206, resource=resref, duration=60),
                   Fx(318, parameter2=55, resource=resref, duration=6),
                   Fx(324, parameter2=68, resource=resref)]
        abilities = [Ability(tuple(refresh) + tuple(main), icon=resref + "B", level=level)
                     for level in (1, 10, 20)]
        casting = (Fx(146, target=1, parameter1=1, parameter2=1, resource="DW#BLHDA"),)
    return Spell(tuple(abilities), name=name, description=name, level=int(resref[4]),
                 icon=resref + "C", casting=casting, flags=0x4000, exclusion=0x40000000)


def recall_wizard_spells(spell: Spell) -> Spell:
    """Bards recall arcane spells too: a wizard copy precedes each priest recall."""

    def convert(effects):
        result = []
        for fx in effects:
            if fx.opcode == 261 and fx.parameter2 == 1:
                result.append(replace(fx, parameter2=0))
            result.append(fx)
        return tuple(result)

    return replace(spell, casting=convert(spell.casting),
                   abilities=tuple(replace(a, effects=convert(a.effects)) for a in spell.abilities))


class PriestSpellImportTests(unittest.TestCase):
    def build(self, root: Path, *, variant: str = "vanilla", drop: str | None = None,
              truncate: str | None = None, ids_number: dict[str, int] | None = None):
        """Return the installed sources: {copy: (source resref, Spell, name)}."""
        names = [""]
        sources = {}
        ids = {}
        unrelated = Spell((Ability((Fx(12, parameter2=0x100000, dice_count=2, dice_size=6),)),),
                          name=1, level=1)
        names.append("Unrelated Slot Spell")
        for symbol, vanilla, copy, _level, name in ALL:
            if symbol == drop:
                continue
            resref = vanilla
            if variant == "moved":
                # SPELL.IDS names a different file; the vanilla slot holds another spell.
                resref = f"SPPR{int(vanilla[4]) }{int(vanilla[5:]) + 40:02d}"
            shown = SR_NAMES.get(vanilla, name) if variant == "sr" else name
            names.append(shown)
            spell = source_spell(resref, len(names) - 1, kind=vanilla, variant=variant)
            sources[copy] = (resref, spell, shown)
            ids[symbol] = (ids_number or {}).get(symbol, 1000 + int(resref[4:]))
        override = make_game(root, names)
        (override / "SPELL.IDS").write_text(spell_ids(ids), encoding="ascii")
        for copy, (resref, spell, _name) in sources.items():
            data = spell.pack()
            if resref == truncate:
                data = data[:0x90]
            (override / f"{resref}.SPL").write_bytes(data)
        if variant == "moved":
            for _symbol, vanilla, _copy, _level, _name in ALL:
                (override / f"{vanilla}.SPL").write_bytes(unrelated.pack())
        (override / "UNRELATED.TXT").write_bytes(b"Unrelated fixture resource\x00\xff")
        mod = root / "BardicWonders"
        copy_libraries(mod, "priest_spell_import.tpa")
        actions = (
            section(MOD / "lib" / "troubadour.tpa", "// Priest spells granted by the kit table.",
                    "COPY ~%MOD_FOLDER%/troubadour/c0trbhl.spl~")
            + section(MOD / "lib" / "deathsinger.tpa", "// Priest spells granted by the kit table.",
                      "COPY ~%MOD_FOLDER%/DEATHSINGER/C0DESP2.SPL~")
            + section(MOD / "lib" / "deathsinger.tpa", "// Cloak of Fear and Slay Living",
                      "COPY ~%MOD_FOLDER%/DEATHSINGER/C0DESP6.SPL~")
            + section(MOD / "lib" / "new_spells.tpa", "// Priest spells shared with bards.",
                      "ACTION_IF NOT FILE_EXISTS_IN_GAME ~SPPR308C.ITM~")
        )
        for _symbol, _vanilla, copy, _level, _name in ALL:
            self.assertEqual(1, len(re.findall(rf"destination = ~{copy}~", actions)), copy)
        self.assertNotRegex(actions, r"COPY_EXISTING ~SPPR\d{3}")
        (root / "test.tp2").write_text(
            "BACKUP ~BardicWonders/backup~\nAUTHOR ~test~\n"
            "ALWAYS\n  OUTER_SPRINT MOD_FOLDER ~BardicWonders~\n"
            "  INCLUDE ~BardicWonders/lib/priest_spell_import.tpa~\nEND\n"
            "BEGIN ~Priest spell imports~ DESIGNATED 0\n" + actions,
            encoding="utf-8",
        )
        return override, sources

    def install_and_verify(self, variant: str, **options) -> dict[str, bytes]:
        with tempfile.TemporaryDirectory(prefix="bw-priest-imports-") as directory:
            root = Path(directory)
            override, sources = self.build(root, variant=variant, **options)
            before = file_snapshot(override)
            output = run_weidu(root, "test.tp2", install=[0])
            self.assertIn("SUCCESSFULLY INSTALLED", output, output)
            for copy, (resref, source, name) in sources.items():
                with self.subTest(copy=copy, variant=variant):
                    level = next(level for _s, _v, c, level, _n in ALL if c == copy)
                    path = resource(override, f"{copy}.SPL")
                    actual = Spell.read(path)
                    installed_source = Spell.read(override / f"{resref}.SPL")
                    expected = imported(installed_source, resref, copy, 1, level)
                    if copy == "C0BW602":
                        expected = recall_wizard_spells(expected)
                    self.assertEqual(expected, actual)
                    self.assertEqual(name, tlk_string(root / "dialog.tlk", actual.name))
                    # No self-reference may still point only at the original.
                    for fx in actual.effects:
                        if fx.opcode in (206, 318, 321, 324) and fx.resource == resref:
                            self.assertTrue(any(other.opcode == fx.opcode and other.resource == copy
                                                for other in actual.effects))
                    # Header bytes other than type and level are the installed spell's.
                    original, copied = (override / f"{resref}.SPL").read_bytes(), path.read_bytes()
                    for start, end in ((0, 0x1C), (0x1E, 0x34), (0x38, 0x64)):
                        self.assertEqual(original[start:end], copied[start:end])
            installed = file_snapshot(override)
            for name, data in before.items():
                self.assertEqual(data, installed[name], name)  # Sources and unrelated data unchanged.
            self.assertIn("SUCCESSFULLY INSTALLED", run_weidu(root, "test.tp2", uninstall=[0], install=[0]))
            self.assertEqual(installed, file_snapshot(override))
            run_weidu(root, "test.tp2", uninstall=[0])
            self.assertEqual(before, file_snapshot(override))
            return {name: data for name, data in installed.items() if name.startswith("c0")}

    def test_vanilla_layout_copies_each_symbolic_spell(self):
        self.install_and_verify("vanilla")

    def test_spell_revisions_layout_keeps_identity_and_renamed_cures(self):
        self.install_and_verify("sr")

    def test_copies_follow_spell_ids_not_vanilla_file_names(self):
        installed = self.install_and_verify("moved")
        self.assertTrue(installed)

    def test_kit_tables_and_bard_lists_grant_each_copy(self):
        for table, grants in KIT_TABLES.items():
            actual = clab_grants(table)
            for entry, level in grants.items():
                self.assertEqual(level, actual.get(entry), f"{table.name}: {entry}")
        source = (MOD / "lib" / "new_spells.tpa").read_text(encoding="utf-8")
        for copy, scroll in (("C0BW303", "SPPR308C"), ("C0BW401", "SCRL58"), ("C0BW402", "SCRL59"),
                             ("C0BW501", "SCRL5F"), ("C0BW602", "C0BW602A")):
            self.assertIn(f"LAF ADD_CLASS_SPELL STR_VAR resref=~{copy}~ scroll = ~{scroll}~ "
                          "class_include=~{'BARD', }~ END", source)

    def assert_rolled_back(self, message: str, **options):
        with tempfile.TemporaryDirectory(prefix="bw-priest-imports-") as directory:
            root = Path(directory)
            override, _sources = self.build(root, **options)
            before = file_snapshot(override)
            output = run_weidu(root, "test.tp2", install=[0])
            self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
            self.assertIn(message, output)
            self.assertEqual(before, file_snapshot(override))

    def test_missing_symbol_fails_and_rolls_back(self):
        self.assert_rolled_back("does not define Slay Living", drop="CLERIC_SLAY_LIVING")

    def test_non_priest_symbol_fails_and_rolls_back(self):
        self.assert_rolled_back("does not define Cloak of Fear",
                                ids_number={"CLERIC_CLOAK_OF_FEAR": 2416})

    def test_truncated_installed_spell_fails_and_rolls_back(self):
        self.assert_rolled_back("SPPR416.SPL, which is not a valid SPL V1 file", truncate="SPPR416")


if __name__ == "__main__":
    unittest.main()
