"""Verify Kapellmeister resources and component 2004 with real disposable WeiDU.

The pulse model exercises source ownership and adversarial recipient ordering;
it is not a substitute for live-engine timing/targeting acceptance.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.abettor_hla.ie_resources import parse_spl, read_eff_resource
from tests.jester.test_weidu_integration import original_tlk, tlk_string
from tests.test_dancer_balance import file_snapshot


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
SPELLS = MOD / "Kapellmeister" / "spells"
HELPER = "C0KMHAF"


class KapellmeisterBalanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="kapellmeister-balance-")
        self.addCleanup(self.directory.cleanup)
        self.game = Path(self.directory.name)
        self.override = self.game / "override"
        self.override.mkdir()
        fixture = self.game / "BardicWonders"
        shutil.copytree(MOD / "Kapellmeister", fixture / "Kapellmeister")
        shutil.copytree(MOD / "bardsong", fixture / "bardsong")
        (fixture / "lib").mkdir()
        for name in ("functions.tph", "kapellmeister_balance.tpa"):
            shutil.copy2(MOD / "lib" / name, fixture / "lib" / name)
        self.sources_before = file_snapshot(fixture)
        self.donors_before = file_snapshot(SPELLS)
        (self.game / "dialog.tlk").write_bytes(original_tlk())
        (self.game / "chitin.key").write_bytes(
            b"KEY V1  " + struct.pack("<IIII", 0, 0, 24, 24)
        )
        (self.override / "GET_UNIQUE_FILENAME_SPL.IDS").write_text("IDS V1.0\n")
        (self.override / "STATDESC.2DA").write_text(
            "2DA V1.0\n*\n  DESCRIPTION BAM\n0 0 ORIGINAL\n"
        )
        previous = bytearray((SPELLS / "C0KM#SOH.SPL").read_bytes())
        previous[-1] ^= 0x5A
        (self.override / "C0KM#SOH.SPL").write_bytes(previous)
        (self.override / "UNRELATED.TXT").write_bytes(b"Keep this resource.\x00\xff")
        self.before = file_snapshot(self.override)
        source = (MOD / "lib" / "kapellmeister.tpa").read_text(encoding="utf-8")
        # Run every production resource COPY/patch/SAY. Only ADD_KIT_EX is
        # excluded; it requires full game kit tables and is unchanged here.
        actions = source.split("LAF ADD_KIT_EX", 1)[0]
        actions += source[source.index("DEFINE_ACTION_FUNCTION cd_new_portrait_icon"):]
        self.assertTrue(actions.rstrip().endswith(
            "INCLUDE ~%MOD_FOLDER%/lib/kapellmeister_balance.tpa~"
        ))
        transform = (MOD / "lib" / "bardsongtweaks.tpa").read_text(encoding="utf-8")
        transform = transform[transform.index("COPY_EXISTING_REGEXP GLOB"):
                              transform.index("INCLUDE ~%MOD_FOLDER%/lib/abettor_hla_finite.tpa~")]
        (self.game / "test.tp2").write_text(
            "BACKUP ~backup~\nAUTHOR ~test~\n"
            "ALWAYS\nOUTER_SPRINT MOD_FOLDER ~BardicWonders~\n"
            "INCLUDE ~BardicWonders/lib/functions.tph~\nEND\nLANGUAGE ~English~ ~english~\n"
            "BEGIN ~Kapellmeister resource actions~\n" + actions
            + "\nBEGIN ~Production component 2004 transformation~\n"
            "OUTER_SET c0bardso = 1\n"
            "COPY ~BardicWonders/bardsong/c0bardx.spl~ ~override~\n"
            + transform,
            encoding="utf-8",
        )
        self.weidu(install=(0,))

    def weidu(self, *, install=(), uninstall=()) -> None:
        options = []
        if uninstall:
            options += ["--force-uninstall-list", *(str(n) for n in uninstall)]
        if install:
            options += ["--force-install-list", *(str(n) for n in install)]
        result = subprocess.run(
            [str(ROOT / "Setup-BardicWonders.exe"), "--no-auto-tp2", "--noautoupdate",
             "--game", str(self.game), "--tlkin", "dialog.tlk", "--tlkout", "dialog.tlk",
             "--no-exit-pause", "--language", "0", "test.tp2", *options],
            cwd=self.game, capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, output)
        if install:
            self.assertIn("SUCCESSFULLY INSTALLED", output)

    def spell(self, name: str):
        return parse_spl(self.override / f"{name}.SPL")

    def test_singer_and_recipient_bonuses_use_distinct_refresh_sources(self) -> None:
        song = self.spell("C0KM#SOH")
        helper = self.spell(HELPER)
        first = song.effects[0]
        self.assertEqual((321, 1, "C0KM#SOH", 1, 2),
                         (first.opcode, first.target, first.resource, first.timing, first.resist_dispel))
        self.assertEqual({166: 25, 37: 5},
                         {e.opcode: e.parameter1 for e in song.effects if e.opcode in (166, 37)})
        self.assertFalse([e for e in song.effects if e.opcode in (19, 191, 189)])
        self.assertEqual([(146, 2, 1)], [(e.opcode, e.target, e.parameter2)
                                       for e in song.effects if e.resource == HELPER])
        first = helper.effects[0]
        self.assertEqual((321, 2, HELPER, 1, 2),
                         (first.opcode, first.target, first.resource, first.timing, first.resist_dispel))
        self.assertEqual(5, helper.spell_type)
        self.assertFalse(helper.find_effects(opcode=142, parameter2=40))
        self.assertEqual((7, 0, 1), (helper.abilities[0].target, helper.abilities[0].range,
                                    helper.abilities[0].projectile))
        self.assertEqual({19: 4, 191: 4, 189: 1},
                         {e.opcode: e.parameter1 for e in helper.effects if e.opcode != 321})
        for e in song.effects + helper.effects:
            if e.opcode in (19, 191, 189, 166, 37):
                self.assertEqual((0, 10, 100), (e.parameter2, e.timing, e.duration))
        guard, = song.find_effects(opcode=318)
        self.assertEqual((2, 66, "C0KM#SOH"), (guard.target, guard.parameter2, guard.resource))
        guard_index = song.effects.index(guard)
        for child in (HELPER, "C0KM#SO1", "C0KM#SO2"):
            dispatch, = song.find_effects(opcode=146, resource=child)
            self.assertLess(guard_index, song.effects.index(dispatch), child)
        # The original force-visible casting effect remains singer-only; the
        # recipient helper has no casting features or inherited op136.
        donor = (SPELLS / "C0KM#SOH.SPL").read_bytes()
        current = (self.override / "C0KM#SOH.SPL").read_bytes()
        for data in (donor, current):
            self.assertEqual(1, struct.unpack_from("<H", data, 0x70)[0])
        old_fx = struct.unpack_from("<I", donor, 0x6A)[0]
        new_fx = struct.unpack_from("<I", current, 0x6A)[0]
        self.assertEqual(donor[old_fx:old_fx + 48], current[new_fx:new_fx + 48])
        self.assertEqual(0, struct.unpack_from("<H", (self.override / f"{HELPER}.SPL").read_bytes(), 0x70)[0])

    def test_restoration_normal_song_cadence_and_spell_slots_are_preserved(self) -> None:
        # These are exact-byte checks, not just counts of opcodes.
        changed = {"C0KM#H1.SPL", "C0KM#H2.SPL", "C0KM#H3.SPL", "C0KM#H4.SPL",
                   "C0KM#S0.SPL", "C0KM#SO3.SPL", "C0KM#SO4.SPL", "C0KM#01A.SPL", "C0KM#SOH.SPL"}
        for donor in SPELLS.iterdir():
            if donor.name.upper() not in changed:
                self.assertEqual(donor.read_bytes(), (self.override / donor.name).read_bytes(), donor.name)
        donor = parse_spl(SPELLS / "C0KM#SOH.SPL")
        actual = self.spell("C0KM#SOH")
        for child in ("C0KM#SO1", "C0KM#SO2"):
            self.assertEqual(donor.find_effects(opcode=146, resource=child),
                             actual.find_effects(opcode=146, resource=child))
        description_bytes = (self.override / "C0KM#H4.SPL").read_bytes()
        description = tlk_string(self.game / "dialog.tlk", struct.unpack_from("<I", description_bytes, 0x50)[0])
        for text in ("5-point bonus", "25% bonus", "+4 bonus to Intelligence and Arcane Casting Level",
                     "+1 bonus to Casting Speed", "a chance each round to restore expended arcane spells"):
            self.assertIn(text, description)
        self.assertNotIn("two rolls for a 30%", description)

    def test_component_2004_rewrites_only_payload_refresh_and_keeps_controller(self) -> None:
        before_helper = (self.override / f"{HELPER}.SPL").read_bytes()
        self.weidu(install=(1,))
        controller = self.spell("C0KM#SOH")
        effect, = controller.abilities[0].effects[2:3]
        self.assertEqual((177, 9), (effect.opcode, effect.target))
        payload = effect.resource
        self.assertEqual(payload, read_eff_resource(self.override / f"{payload}.EFF"))
        for ability in controller.abilities:
            first = [e for e in ability.effects if e.opcode == 177 and e.resource == payload]
            pulses = [e for e in ability.effects if e.opcode == 272 and e.resource == payload]
            self.assertEqual(1, len(first))
            self.assertEqual(1, len(pulses))
            self.assertEqual((6, 3, 9), (pulses[0].parameter1, pulses[0].parameter2, pulses[0].target))
            self.assertEqual(first[0].duration, pulses[0].duration)
        cloned = self.spell(payload)
        self.assertEqual((321, 1, payload),
                         (cloned.effects[0].opcode, cloned.effects[0].target, cloned.effects[0].resource))
        self.assertEqual([payload], [e.resource for e in cloned.find_effects(opcode=318)])
        self.assertFalse(cloned.find_effects(opcode=321, resource="C0KM#SOH"))
        self.assertEqual(before_helper, (self.override / f"{HELPER}.SPL").read_bytes())
        self.assertEqual(["C0KM#SOH"], [e.resource for e in self.spell("C0KM#H4").find_effects(opcode=251)])
        self.assertTrue(self.spell("C0KM#H4").find_effects(opcode=309, resource=payload))
        self.assert_pulse_ownership(payload)

    def assert_pulse_ownership(self, name: str) -> None:
        spells = {name: self.spell(name), HELPER: self.spell(HELPER)}
        # Deliberately exercise caster effects once per recipient, which is the
        # dangerous processing order for a shared source. Track only additive
        # fields and explicit source removals; no claim about engine scheduling.
        state = {actor: [] for actor in ("singer", "ally1", "ally2")}

        def apply(spell_name, caster, recipient, now):
            for e in spells[spell_name].effects:
                actual = caster if e.target == 1 else recipient
                state[actual] = [fx for fx in state[actual] if fx[3] > now]
                if e.opcode == 321:
                    state[actual] = [fx for fx in state[actual] if fx[0] != e.resource]
                elif e.opcode == 146 and e.resource == HELPER:
                    apply(HELPER, actual, actual, now)
                elif e.opcode in (19, 191, 189, 166, 37):
                    self.assertEqual(10, e.timing)
                    state[actual].append((spell_name, e.opcode, e.parameter1, now + e.duration))

        for order in (("singer", "ally1", "ally2"), ("ally2", "ally1", "singer")):
            for actor in state:
                state[actor] = []
            for now in (0, 90, 180, 270):
                for recipient in order:
                    apply(name, "singer", recipient, now)
                for actor, effects in state.items():
                    totals = {op: sum(fx[2] for fx in effects if fx[1] == op)
                              for op in (19, 191, 189, 166, 37)}
                    self.assertEqual({19: 4, 191: 4, 189: 1, 166: 25 if actor == "singer" else 0,
                                      37: 5 if actor == "singer" else 0}, totals)
                self.assertTrue(all(fx[3] == now + 100 for effects in state.values() for fx in effects))

    def test_repeated_modal_pulses_preserve_singers_recipient_bonuses(self) -> None:
        self.assert_pulse_ownership("C0KM#SOH")

    def test_reinstall_is_stable_and_uninstall_restores_existing_resources(self) -> None:
        self.weidu(install=(1,))
        installed = file_snapshot(self.override)
        self.weidu(uninstall=(1, 0), install=(0, 1))
        self.assertEqual(installed, file_snapshot(self.override))
        self.weidu(uninstall=(1, 0))
        # WeiDU's GET_UNIQUE_FILE_NAME allocator deliberately keeps its mapping
        # after uninstall. Assert those exact registrations; every other file
        # must be restored byte-for-byte, including the overwritten old song.
        restored = file_snapshot(self.override)
        allocator = "get_unique_filename_spl.ids"
        expected = dict(self.before)
        expected[allocator] += b"0 C0KM#SO\r\n1 C0KM#SOH\r\n"
        self.assertEqual(expected, restored)
        self.assertEqual(self.sources_before, file_snapshot(self.game / "BardicWonders"))
        self.assertEqual(self.donors_before, file_snapshot(SPELLS))


if __name__ == "__main__":
    unittest.main()
