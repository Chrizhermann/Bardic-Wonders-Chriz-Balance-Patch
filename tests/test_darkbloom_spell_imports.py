"""Real-WeiDU tests of Darkbloom's druidic spell list (component 1006).

The production spell section runs against synthetic installations shaped like
vanilla BG2:EE, Spell Revisions (unrelated spells in the IWD slots) and
IWDification/IWD:EE (the IWD spells exist under their SPELL.IDS symbols). The
tests verify each copy's name, mechanics, type, level and kit-table grant, that
no installed resource is replaced, and failure rollback, reinstall and
uninstall. They do not run ADD_KIT_EX or the game engine.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import struct
import tempfile
import unittest

from tests.spell_fixtures import (
    IDENTITY_OPCODES, MOD, Ability, Fx, Spell, copy_libraries, file_snapshot, imported,
    make_game, resource, resref, run_weidu, section, spell_ids, tlk_string,
)


BUNDLED = MOD / "darkbloom" / "BGEE"
# copy, symbol, wizard level, kit name, bundled fallback (None: no fallback)
SPELLS = [
    ("C0BDDS1", "CLERIC_CURSE", 1, "Curse", "SPPR112"),
    ("C0BDDS2", "CLERIC_BEAST_CLAW", 2, "Beast Claw", "SPPR219"),
    ("C0BDDS3", "CLERIC_MOLD_TOUCH", 3, "Mold Touch", "SPPR326"),
    ("C0BDDS4", "CLERIC_THORN_SPRAY", 4, "Thorn Spray", "SPPR427"),
    ("C0BDDS5", "CLERIC_INSECT_PLAGUE", 5, "Insect Plague", None),
    ("C0BDDS6", "CLERIC_FIRE_SEEDS", 6, "Fire Seeds", None),
    ("C0BDDS7", "CLERIC_MIST_OF_ELDATH", 7, "Mist of Eldath", "SPPR736"),
]
# Character levels at which the kit table grants each copy.
GRANTS = {"GA_C0BDDS1": 2, "GA_C0BDDS2": 4, "GA_C0BDDS3": 7, "GA_C0BDDS4": 10,
          "GA_C0BDDS5": 13, "GA_C0BDDS6": 16, "GA_C0BDDS7": 30}
# Spell Revisions puts these spells in the IWD files Darkbloom used to copy.
SR_SLOTS = {
    "CLERIC_STRENGTH_OF_STONE": ("SPPR112", "Strength of Stone"),
    "CLERIC_CAUSE_MODERATE_WOUNDS": ("SPPR219", "Cause Moderate Wounds"),
    "CLERIC_ICELANCE": ("SPPR326", "Icelance"),
    "CLERIC_SMASHING_WAVE": ("SPPR427", "Smashing Wave"),
    "CLERIC_DESTRUCTION": ("SPPR736", "Destruction"),
}
# IWDification numbering on BG2:EE (IWD:EE uses the vanilla IWD files).
IWD_SLOTS = {"CLERIC_CURSE": "SPPR121", "CLERIC_BEAST_CLAW": "SPPR222",
             "CLERIC_MOLD_TOUCH": "SPPR333", "CLERIC_THORN_SPRAY": "SPPR428",
             "CLERIC_MIST_OF_ELDATH": "SPPR738"}
# Resource names the bundled fallbacks are built from. Other installations own
# these names (vanilla icons and Mold Touch animation, IWDification resources).
FOREIGN = ["SPPR112B.BAM", "SPPR112C.BAM", "SPPR326B.SPL", "MTOUCHH.BAM", "MTOUCHH.VVC",
           "BCLAW.ITM", "IBCLAW.BAM", "#BLESS.VVC", "AREA1X.BAM", "TSPRAYT.BAM",
           "IDPRO237.PRO", "IDPRO303.PRO", "IDPRO307.PRO", "IDMOLD.PRO", "SPPR427B.BAM"]


def installed_spell(resref_: str, name: int, *, mold: bool = False, self_refresh: bool = False) -> Spell:
    effects = [Fx(12, parameter2=0x10000, dice_count=2, dice_size=4), Fx(139, parameter1=name)]
    if self_refresh:
        effects.insert(0, Fx(321, resource=resref_))
    if mold:
        # IWDification + SCS Mold Touch: self-protections and an unnamed sub-spell.
        effects = [Fx(324, parameter2=68, resource=resref_), Fx(324, parameter2=55, resource=resref_),
                   Fx(78, parameter1=4, parameter2=12, timing=3, special=7),
                   Fx(206, parameter1=-1, duration=1, resource=resref_.lower()),
                   Fx(78, parameter1=2, parameter2=12, timing=3, special=7),
                   Fx(146, parameter2=2, timing=4, duration=7, resource=resref_ + "A"),
                   Fx(318, duration=20, resource=resref_)]
    abilities = tuple(Ability(tuple(effects), icon=resref_ + "B", level=level) for level in (1, 10))
    return Spell(abilities, name=name, description=name, level=int(resref_[4]),
                 icon=resref_ + "C", casting=(Fx(146, target=1, resource="DW#BLHDA"),))


def projectile_id(override: Path, name: str) -> int:
    for line in resource(override, "PROJECTL.IDS").read_text(encoding="ascii").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].upper() == name:
            return int(parts[0]) + 1
    raise AssertionError(f"{name} is not in PROJECTL.IDS")


def write_resref(data: bytearray, offset: int, value: str) -> None:
    data[offset:offset + 8] = value.encode("ascii").ljust(8, b"\0")


def private_fallback(source: bytes, *, identity: str, destination: str, spell_type: int = 0,
                     level: int = 0, projectile: int = 0, subspell: str = "",
                     renames: dict[tuple[int, str], str] | None = None) -> bytearray:
    """The documented fallback transformation of a bundled spell."""
    data = bytearray(source)
    if spell_type:
        struct.pack_into("<H", data, 0x1C, spell_type)
    if level:
        struct.pack_into("<I", data, 0x34, level)
    if resref(data[0x3A:0x42]) == identity + "C":
        write_resref(data, 0x3A, destination + "C")
    abilities, count, effects = struct.unpack_from("<IHI", data, 0x64)
    total = struct.unpack_from("<H", data, 0x70)[0]
    for index in range(count):
        offset = abilities + 0x28 * index
        if resref(data[offset + 4:offset + 12]) == identity + "B":
            write_resref(data, offset + 4, destination + "B")
        if projectile:
            struct.pack_into("<H", data, offset + 0x26, projectile)
        total += struct.unpack_from("<H", data, offset + 0x1E)[0]
    for index in range(total):
        offset = effects + 0x30 * index
        opcode, = struct.unpack_from("<H", data, offset)
        kind, = struct.unpack_from("<i", data, offset + 8)
        target = resref(data[offset + 0x14:offset + 0x1C])
        if opcode in IDENTITY_OPCODES and target == identity:
            write_resref(data, offset + 0x14, destination)
        elif opcode == 78 and kind in (11, 12) and not target and subspell:
            write_resref(data, offset + 0x14, subspell)
        elif (opcode, target) in (renames or {}):
            write_resref(data, offset + 0x14, renames[(opcode, target)])
    return data


def adopt_strings(expected: bytearray, actual: bytes, offsets) -> bytes:
    """Strrefs are allocated by WeiDU; the tests check their text separately."""
    for offset in offsets:
        expected[offset:offset + 4] = actual[offset:offset + 4]
    return bytes(expected)


def effect_offsets(data: bytes, opcode: int) -> list[int]:
    abilities, count, effects = struct.unpack_from("<IHI", data, 0x64)
    total = struct.unpack_from("<H", data, 0x70)[0] + sum(
        struct.unpack_from("<H", data, abilities + 0x28 * i + 0x1E)[0] for i in range(count))
    return [effects + 0x30 * i for i in range(total)
            if struct.unpack_from("<H", data, effects + 0x30 * i)[0] == opcode]


class DarkbloomSpellImportTests(unittest.TestCase):
    def build(self, root: Path, layout: str, *, drop: str | None = None, truncate: str | None = None):
        names = ["", "Bless", "Insect Plague", "Fire Seeds"]
        ids = {"CLERIC_BLESS": 1101, "CLERIC_INSECT_PLAGUE": 1517, "CLERIC_FIRE_SEEDS": 1606}
        spells = {"SPPR101": installed_spell("SPPR101", 1), "SPPR517": installed_spell("SPPR517", 2),
                  "SPPR606": installed_spell("SPPR606", 3)}
        if layout in ("sr", "iwd", "iwd-without-mist"):
            for symbol, (slot, name) in SR_SLOTS.items():
                names.append(name)
                ids[symbol] = 1000 + int(slot[4:])
                spells[slot] = installed_spell(slot, len(names) - 1, self_refresh=True)
        if layout in ("iwd", "iwd-without-mist"):
            for symbol, slot in IWD_SLOTS.items():
                if layout == "iwd-without-mist" and symbol == "CLERIC_MIST_OF_ELDATH":
                    continue
                names.append(next(name for _c, s, _l, name, _f in SPELLS if s == symbol))
                ids[symbol] = 1000 + int(slot[4:])
                spells[slot] = installed_spell(slot, len(names) - 1, mold=slot == "SPPR333",
                                               self_refresh=slot == "SPPR121")
        if drop:
            del ids[drop]
        override = make_game(root, names)
        (override / "SPELL.IDS").write_text(spell_ids(ids), encoding="ascii")
        for slot, spell in spells.items():
            data = spell.pack()
            (override / f"{slot}.SPL").write_bytes(data[:0x80] if slot == truncate else data)
        for number, name in enumerate(FOREIGN):
            (override / name).write_bytes(f"foreign {name} {number}".encode("ascii"))
        (override / "PROJECTL.IDS").write_text("IDS V1.0\n0 NONE\n1 ARROW\n356 IDPRO237\n", encoding="ascii")
        (override / "MISSILE.IDS").write_text("IDS V1.0\n0 None\n1 Arrow\n357 Foreign_Curse\n", encoding="ascii")
        mod = root / "BardicWonders"
        shutil.copytree(MOD / "darkbloom", mod / "darkbloom")
        copy_libraries(mod, "priest_spell_import.tpa")
        source = MOD / "lib" / "darkbloom.tpa"
        actions = (section(source, "COPY ~%MOD_FOLDER%/darkbloom~ ~override~", "COPY_EXISTING ~LUBA0.2DA~")
                   + section(source, "// Druidic spells."))
        self.assertNotRegex(actions, r"COPY_EXISTING ~SPPR")
        (root / "test.tp2").write_text(
            "BACKUP ~BardicWonders/backup~\nAUTHOR ~test~\n"
            "ALWAYS\n  OUTER_SPRINT MOD_FOLDER ~BardicWonders~\n"
            "  INCLUDE ~BardicWonders/lib/priest_spell_import.tpa~\nEND\n"
            "BEGIN ~Darkbloom spells~ DESIGNATED 0\n" + actions,
            encoding="utf-8",
        )
        return override, spells

    def install(self, layout: str):
        directory = tempfile.TemporaryDirectory(prefix="bw-darkbloom-spells-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        override, spells = self.build(root, layout)
        before = file_snapshot(override)
        output = run_weidu(root, "test.tp2", install=[0])
        self.assertIn("SUCCESSFULLY INSTALLED", output, output)
        installed = file_snapshot(override)
        # Darkbloom adds only its own resources and (for fallbacks) projectile rows.
        for name, data in before.items():
            if name not in ("projectl.ids", "missile.ids"):
                self.assertEqual(data, installed[name], f"{name} was replaced")
        for name in set(installed) - set(before):
            self.assertTrue(name.startswith("c0bdd"), name)
        # Each kit-table grant names a wizard copy of the documented level.
        table = resource(override, "C0BDD.2DA").read_text(encoding="ascii").splitlines()[3:]
        grants = {cell: level for row in table for level, cell in enumerate(row.split()[1:], 1)
                  if cell.startswith("GA_C0BDDS")}
        self.assertEqual(GRANTS, grants)
        for copy, _symbol, level, _name, _fallback in SPELLS:
            spell = Spell.read(resource(override, f"{copy}.SPL"))
            self.assertEqual((1, level), (spell.spell_type, spell.level), copy)
        return root, override, spells, before, installed

    def assert_reversible(self, root: Path, override: Path, before, installed) -> None:
        self.assertIn("SUCCESSFULLY INSTALLED", run_weidu(root, "test.tp2", uninstall=[0], install=[0]))
        self.assertEqual(installed, file_snapshot(override))
        run_weidu(root, "test.tp2", uninstall=[0])
        self.assertEqual(before, file_snapshot(override))

    def assert_imported(self, root, override, spells, copy, symbol_slot, level, name):
        source = Spell.read(override / f"{symbol_slot}.SPL")
        actual = Spell.read(resource(override, f"{copy}.SPL"))
        self.assertEqual(imported(source, symbol_slot, copy, 1, level), actual)
        self.assertEqual(name, tlk_string(root / "dialog.tlk", actual.name))

    def assert_fallbacks(self, root: Path, override: Path, *, only=("C0BDDS1", "C0BDDS2", "C0BDDS3",
                                                                      "C0BDDS4", "C0BDDS7")):
        tlk = root / "dialog.tlk"

        def check_spell(copy, expected: bytearray, name: str, *, strings=(0x08, 0x50)):
            actual = resource(override, f"{copy}.SPL").read_bytes()
            self.assertEqual(adopt_strings(expected, actual, strings), actual, copy)
            self.assertEqual(name, tlk_string(tlk, struct.unpack_from("<I", actual, 0x08)[0]))
            description = tlk_string(tlk, struct.unpack_from("<I", actual, 0x50)[0])
            self.assertTrue(description.startswith(name + "\n"), description[:40])
            return actual

        def same(name: str, private: str):
            self.assertEqual((BUNDLED / name).read_bytes(), resource(override, private).read_bytes())

        if "C0BDDS1" in only:
            for original, private in (("SPPR112B.BAM", "C0BDDS1B.BAM"), ("SPPR112C.BAM", "C0BDDS1C.BAM"),
                                      ("AREA1X.BAM", "C0BDDA1.BAM")):
                same(original, private)
            vvc = bytearray((BUNDLED / "#BLESS.VVC").read_bytes())
            write_resref(vvc, 0x08, "C0BDDA1")
            self.assertEqual(bytes(vvc), resource(override, "C0BDDV1.VVC").read_bytes())
            pro = bytearray((BUNDLED / "IDPRO237.PRO").read_bytes())
            write_resref(pro, 0x21C, "C0BDDV1")
            self.assertEqual(bytes(pro), resource(override, "C0BDDP1.PRO").read_bytes())
            expected = private_fallback((BUNDLED / "SPPR112.SPL").read_bytes(), identity="SPPR112",
                                        destination="C0BDDS1", spell_type=1, level=1,
                                        projectile=projectile_id(override, "C0BDDP1"))
            message = effect_offsets(expected, 139)
            actual = check_spell("C0BDDS1", expected, "Curse", strings=[0x08, 0x50] + [o + 4 for o in message])
            self.assertEqual("Cursed", tlk_string(tlk, struct.unpack_from("<I", actual, message[0] + 4)[0]))
        if "C0BDDS2" in only:
            for original, private in (("SPPR219B.BAM", "C0BDDS2B.BAM"), ("SPPR219C.BAM", "C0BDDS2C.BAM"),
                                      ("IBCLAW.BAM", "C0BDDS2I.BAM")):
                same(original, private)
            item = bytearray((BUNDLED / "BCLAW.ITM").read_bytes())
            write_resref(item, 0x3A, "C0BDDS2I")
            abilities, count = struct.unpack_from("<IH", item, 0x64)
            for index in range(count):
                write_resref(item, abilities + 0x38 * index + 4, "C0BDDS2I")
            self.assertEqual(bytes(item), resource(override, "C0BDDS2W.ITM").read_bytes())
            check_spell("C0BDDS2", private_fallback(
                (BUNDLED / "SPPR219.SPL").read_bytes(), identity="SPPR219", destination="C0BDDS2",
                spell_type=1, level=2, renames={(111, "BCLAW"): "C0BDDS2W"}), "Beast Claw")
        if "C0BDDS3" in only:
            for original, private in (("SPPR326B.BAM", "C0BDDS3B.BAM"), ("SPPR326C.BAM", "C0BDDS3C.BAM"),
                                      ("MTOUCHH.BAM", "C0BDDA3.BAM"), ("idmold.PRO", "C0BDDP3.PRO")):
                same(original, private)
            vvc = bytearray((BUNDLED / "MTOUCHH.VVC").read_bytes())
            write_resref(vvc, 0x08, "C0BDDA3")
            self.assertEqual(bytes(vvc), resource(override, "C0BDDV3.VVC").read_bytes())
            # The sub-spell spreads the mold; both resources name it explicitly.
            sub = private_fallback((BUNDLED / "sppr326b.SPL").read_bytes(), identity="SPPR326B",
                                   destination="C0BDDS3B", subspell="C0BDDS3B",
                                   projectile=projectile_id(override, "C0BDDP3"))
            self.assertEqual(bytes(sub), resource(override, "C0BDDS3B.SPL").read_bytes())
            check_spell("C0BDDS3", private_fallback(
                (BUNDLED / "SPPR326.SPL").read_bytes(), identity="SPPR326", destination="C0BDDS3",
                spell_type=1, level=3, subspell="C0BDDS3B", renames={(215, "MTOUCHH"): "C0BDDV3"}),
                "Mold Touch")
            mold = Spell.read(resource(override, "C0BDDS3.SPL"))
            self.assertEqual({"C0BDDS3B"}, {fx.resource for fx in mold.effects if fx.opcode == 78})
        if "C0BDDS4" in only:
            for original, private in (("SPPR427B.BAM", "C0BDDS4B.BAM"), ("SPPR427C.BAM", "C0BDDS4C.BAM"),
                                      ("tsprayt.BAM", "C0BDDA4.BAM")):
                same(original, private)
            pro = bytearray((BUNDLED / "IDPRO303.PRO").read_bytes())
            write_resref(pro, 0x230, "C0BDDA4")
            self.assertEqual(bytes(pro), resource(override, "C0BDDP4.PRO").read_bytes())
            check_spell("C0BDDS4", private_fallback(
                (BUNDLED / "SPPR427.SPL").read_bytes(), identity="SPPR427", destination="C0BDDS4",
                spell_type=1, level=4, projectile=projectile_id(override, "C0BDDP4")), "Thorn Spray")
        if "C0BDDS7" in only:
            for original, private in (("SPPR736B.BAM", "C0BDDS7B.BAM"), ("SPPR736C.BAM", "C0BDDS7C.BAM"),
                                      ("IDPRO307.PRO", "C0BDDP7.PRO")):
                same(original, private)
            check_spell("C0BDDS7", private_fallback(
                (BUNDLED / "SPPR736.SPL").read_bytes(), identity="SPPR736", destination="C0BDDS7",
                spell_type=1, level=7, projectile=projectile_id(override, "C0BDDP7")), "Mist of Eldath")
        # No copy refers to the resref an installed spell may own.
        for copy in only:
            spell = Spell.read(resource(override, f"{copy}.SPL"))
            fallback = next(f for c, _s, _l, _n, f in SPELLS if c == copy)
            self.assertFalse([fx for fx in spell.effects if fx.resource.startswith(fallback)], copy)

    def test_vanilla_layout_installs_private_fallbacks(self):
        root, override, spells, before, installed = self.install("vanilla")
        self.assert_fallbacks(root, override)
        self.assert_imported(root, override, spells, "C0BDDS5", "SPPR517", 5, "Insect Plague")
        self.assert_imported(root, override, spells, "C0BDDS6", "SPPR606", 6, "Fire Seeds")
        self.assert_reversible(root, override, before, installed)

    def test_spell_revisions_layout_ignores_unrelated_slot_spells(self):
        root, override, spells, before, installed = self.install("sr")
        self.assert_fallbacks(root, override)
        for slot, name in SR_SLOTS.values():
            self.assertEqual(before[f"{slot.lower()}.spl"], resource(override, f"{slot}.SPL").read_bytes())
            for copy, *_ in SPELLS:
                self.assertNotEqual(name, tlk_string(root / "dialog.tlk",
                                                     Spell.read(resource(override, f"{copy}.SPL")).name))
        self.assert_reversible(root, override, before, installed)

    def test_iwd_spells_are_copied_by_symbol(self):
        root, override, spells, before, installed = self.install("iwd")
        for copy, symbol, level, name, _fallback in SPELLS:
            slot = IWD_SLOTS.get(symbol) or {"C0BDDS5": "SPPR517", "C0BDDS6": "SPPR606"}[copy]
            self.assert_imported(root, override, spells, copy, slot, level, name)
        mold = Spell.read(resource(override, "C0BDDS3.SPL"))
        self.assertEqual({"SPPR333B"}, {fx.resource for fx in mold.effects if fx.opcode == 78})
        self.assertEqual(before["projectl.ids"], installed["projectl.ids"])
        self.assertEqual(before["missile.ids"], installed["missile.ids"])
        self.assertFalse([name for name in installed if name[:6] in ("c0bddp", "c0bdda", "c0bddv")])
        self.assert_reversible(root, override, before, installed)

    def test_missing_iwd_spell_uses_its_fallback_only(self):
        root, override, spells, before, installed = self.install("iwd-without-mist")
        self.assert_fallbacks(root, override, only=("C0BDDS7",))
        self.assert_imported(root, override, spells, "C0BDDS1", "SPPR121", 1, "Curse")
        self.assertNotIn("c0bddp1.pro", installed)
        self.assert_reversible(root, override, before, installed)

    def assert_rolled_back(self, message: str, layout: str, **options):
        with tempfile.TemporaryDirectory(prefix="bw-darkbloom-spells-") as directory:
            root = Path(directory)
            override, _spells = self.build(root, layout, **options)
            before = file_snapshot(override)
            output = run_weidu(root, "test.tp2", install=[0])
            self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
            self.assertIn(message, output)
            self.assertEqual(before, file_snapshot(override))

    def test_spell_without_fallback_must_exist(self):
        self.assert_rolled_back("does not define Fire Seeds", "sr", drop="CLERIC_FIRE_SEEDS")

    def test_truncated_installed_spell_fails_and_rolls_back(self):
        self.assert_rolled_back("SPPR121.SPL, which is not a valid SPL V1 file", "iwd", truncate="SPPR121")


if __name__ == "__main__":
    unittest.main()
