"""Disposable real-WeiDU tests of Battleluck's production resource actions.

This checks resource semantics and rollback, not live projectile delivery.
The spell is bundled/owned: SR's priest imports are outside this action slice.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from tests.abettor_hla.ie_resources import parse_spl
from tests.abettor_hla.test_tail_patch_integration import tlk_string, tlk_with_original_description
from tests.test_dancer_balance import file_snapshot

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
WEIDU = ROOT / "Setup-BardicWonders.exe"
SOURCE = MOD / "new_spells/spl/C0BW302.SPL"
ICON = 420


def fixture(*, varied: bool = False) -> bytes:
    data = SOURCE.read_bytes()
    if not varied:
        return data
    ao, ac, eo = struct.unpack_from("<IHI", data, 0x64)
    headers, blocks = [], []
    # A caster-side marker must survive and keep its own indexed slice.
    cast = bytearray(48)
    struct.pack_into("<HBBiiBBI", cast, 0, 328, 1, 0, 0, 96, 9, 2, 0)
    cast[0x12] = 100
    effects = [bytes(cast)]
    for index in reversed(range(ac)):
        header = bytearray(data[ao + index * 40:ao + (index + 1) * 40])
        count, first = struct.unpack_from("<HH", header, 0x1e)
        block = [bytearray(data[eo + i * 48:eo + (i + 1) * 48]) for i in range(first, first + count)]
        block.reverse()
        # Existing gameplay values and related-record counts are not a gate.
        for effect in block:
            opcode = struct.unpack_from("<H", effect)[0]
            if opcode in (301, 362):
                struct.pack_into("<I", effect, 0x0e, 75)
                struct.pack_into("<i", effect, 4, 4 if opcode == 301 else -9)
        block.append(next(bytearray(e) for e in block if struct.unpack_from("<H", e)[0] == 301))
        # Foreign timed buff, portrait icon and refresh must survive exactly.
        for opcode, p1, p2, res in [(54, 3, 0, ""), (142, 0, 99, ""), (321, 0, 2, "OTHER")]:
            effect = bytearray(48)
            struct.pack_into("<HBBiiBBI", effect, 0, opcode, 2, 3, p1, p2, 0, 3, 87)
            effect[0x12] = 73
            effect[0x14:0x1c] = res.encode().ljust(8, b"\0")
            block.append(effect)
        headers.append(header)
        blocks.append(block)
    # An unrelated extra ability must not acquire Battleluck's projectile/guards.
    header = bytearray(headers[0])
    struct.pack_into("<H", header, 0x10, 22)
    headers.append(header)
    blocks.append([bytes(cast)])
    for header, block in zip(headers, blocks):
        struct.pack_into("<HH", header, 0x1e, len(block), len(effects))
        effects.extend(bytes(e) for e in block)
    out = bytearray(data[:0x72])
    struct.pack_into("<IHIHH", out, 0x64, 0x72, len(headers), 0x72 + 40 * len(headers), 0, 1)
    return bytes(out) + b"".join(headers) + b"".join(effects)


class BattleluckBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (MOD / "lib/new_spells.tpa").read_text(encoding="utf-8")
        cls.gallant = (MOD / "lib/gallant_new_spells.tpa").read_text(encoding="utf-8")
        cls.kit = (MOD / "lib/gallant.tpa").read_text(encoding="utf-8")

    def resource_actions(self):
        description = self.source[self.source.index("OUTER_SPRINT C0BW302_NAME1"):self.source.index("OUTER_SPRINT C0BW403_NAME1")]
        start = self.source.index("COPY_EXISTING C0BW302.SPL")
        stop = self.source.index("COPY_EXISTING C0BW403.SPL", start)
        actions = self.source[start:stop]
        self.assertIn("INCLUDE ~%MOD_FOLDER%/lib/battleluck_balance.tpa~", actions)
        # The actual Gallant COPY must inherit the patched spell. The shared
        # integration runs after the patch in component 2008, or in the kit
        # component once 2008 (and so the patch) is already installed.
        call = re.compile(r"ACTION_IF MOD_IS_INSTALLED ~BardicWonders/Setup-BardicWonders.tp2~ ~(\d+)~ THEN BEGIN\s*"
                          r"LAF C0_BW_GALLANT_NEW_SPELLS END\s*END")
        in_spells = call.search(self.source)
        self.assertIsNotNone(in_spells)
        self.assertEqual("1012", in_spells[1])
        self.assertGreater(in_spells.start(), stop)
        self.assertEqual(["2008"], call.findall(self.kit))
        alias = re.search(r"COPY_EXISTING ~C0BW302.SPL~ ~OVERRIDE/C0GA302.SPL~\s*WRITE_SHORT 0x1C 2", self.gallant, re.IGNORECASE)
        self.assertIsNotNone(alias)
        return description + actions + "\n" + alias.group(0)

    def weidu(self, root, *, operation="install", success=True):
        args = ["--force-uninstall-list", "0"] if operation in ("uninstall", "reinstall") else []
        if operation != "uninstall":
            args += ["--force-install-list", "0"]
        result = subprocess.run(
            [str(WEIDU), "--no-auto-tp2", "--noautoupdate", "--nogame", "--search", "override",
             "--search-ids", "override", "--tlkin", "dialog.tlk", "--tlkout", "dialog.tlk",
             "--no-exit-pause", "--language", "0", "testmod/setup-test.tp2", *args],
            cwd=root, capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(0, result.returncode, output)
            if operation != "uninstall":
                self.assertIn("SUCCESSFULLY INSTALLED", output)
        else:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        return output

    @contextmanager
    def installed(self, *, varied=False, repeat=False, malformed=False, missing=False):
        with tempfile.TemporaryDirectory(prefix="battleluck-balance-") as directory:
            root = Path(directory)
            mod, override = root / "testmod", root / "override"
            (mod / "lib").mkdir(parents=True)
            (mod / "new_spells/pro").mkdir(parents=True)
            override.mkdir()
            shutil.copy2(MOD / "lib/battleluck_balance.tpa", mod / "lib")
            shutil.copy2(MOD / "new_spells/pro/C0BW203P.PRO", mod / "new_spells/pro")
            for name in ("projectl.ids", "missile.ids"):
                (override / name).write_text("IDS V1.0\n0 NONE\n7 FOREIGN\n", encoding="ascii")
            data = fixture(varied=varied)
            if malformed:
                data = data[:120]
            if missing:
                data = bytearray(data)
                eo = struct.unpack_from("<I", data, 0x6a)[0]
                for offset in range(eo, len(data), 48):
                    if struct.unpack_from("<H", data, offset)[0] in (301, 362):
                        struct.pack_into("<H", data, offset, 54)
                data = bytes(data)
            (override / "c0bw302.spl").write_bytes(data)
            (override / "unrelated.bin").write_bytes(b"preserve")
            (root / "dialog.tlk").write_bytes(tlk_with_original_description())
            actions = self.resource_actions()
            if repeat:
                actions += "\nINCLUDE ~%MOD_FOLDER%/lib/battleluck_balance.tpa~\n"
                actions += "COPY_EXISTING ~C0GA302.SPL~ ~override~ LPF c0_patch_battleluck INT_VAR party_projectile=C0BWLCK luck_icon=C0BW302I END\n"
            (mod / "setup-test.tp2").write_text(
                "BACKUP ~testmod/backup~\nAUTHOR ~test~\nBEGIN ~Battleluck resource test~\n"
                f"OUTER_SPRINT MOD_FOLDER ~testmod~\nOUTER_SET C0BW302I = {ICON}\n" + actions,
                encoding="utf-8",
            )
            before = file_snapshot(override)
            output = self.weidu(root, success=not (malformed or missing))
            if malformed or missing:
                self.assertEqual(before, file_snapshot(override))
                yield root, output
                return
            yield root, data
            after = file_snapshot(override)
            self.weidu(root, operation="reinstall")
            self.assertEqual(after, file_snapshot(override))
            self.weidu(root, operation="uninstall")
            self.assertEqual(before, file_snapshot(override))

    def assert_spell(self, path, original, projectile):
        actual = parse_spl(path)
        self.assertEqual(len(original.abilities), len(actual.abilities))
        for old, new in zip(original.abilities, actual.abilities):
            if not any(e.opcode == 301 for e in old.effects):
                self.assertEqual(old, new)
                continue
            self.assertEqual((5, 0, projectile, old.required_level), (new.target, new.range, new.projectile, new.required_level))
            guards = new.effects[:2]
            self.assertEqual(["C0BW302", "C0GA302"], [e.resource for e in guards])
            for guard in guards:
                self.assertEqual((321, 2, 2, 1, 2, 0, 100, 0),
                                 (guard.opcode, guard.target, guard.parameter2, guard.timing, guard.resist_dispel,
                                  guard.duration, guard.probability1, guard.save_type))
            expected = []
            for effect in old.effects:
                if effect.opcode in (301, 362) and effect.parameter2 == 0:
                    effect = replace(effect, target=2, timing=0, duration=30)
                elif effect.opcode == 142 and effect.parameter2 == 0:
                    effect = replace(effect, parameter2=ICON, target=2, timing=0, duration=30)
                elif effect.opcode == 174 and effect.timing == 4 and effect.resource == "EFF_E04":
                    effect = replace(effect, target=2, duration=30)
                elif effect.opcode == 139:
                    # Production resolves this display string in the temporary TLK.
                    effect = replace(effect, parameter1=next(e.parameter1 for e in new.effects if e.opcode == 139))
                expected.append(effect)
            self.assertEqual(tuple(expected), new.effects[2:])

    def test_actual_resource_delivery_alias_and_rollback(self):
        with self.installed() as (root, _):
            override = root / "override"
            projectile = next(int(row.split()[0]) + 1 for row in (override / "projectl.ids").read_text().splitlines()
                              if len(row.split()) == 2 and row.split()[1].upper() == "C0BWLCK")
            for name in ("c0bw302.spl", "c0ga302.spl"):
                self.assert_spell(override / name, parse_spl(SOURCE), projectile)
            pro = (override / "c0bwlck.pro").read_bytes()
            self.assertEqual((3, 0, 0, 0xc0, 480, 480, 0, 1, 0),
                (struct.unpack_from("<H", pro, 8)[0], struct.unpack_from("<I", pro, 0xc)[0],
                 struct.unpack_from("<I", pro, 0x2c)[0], struct.unpack_from("<H", pro, 0x200)[0],
                 struct.unpack_from("<H", pro, 0x204)[0], struct.unpack_from("<H", pro, 0x206)[0],
                 struct.unpack_from("<H", pro, 0x210)[0], pro[0x216], struct.unpack_from("<H", pro, 0x21a)[0]))
            data = (override / "c0bw302.spl").read_bytes()
            desc = tlk_string(root / "dialog.tlk", struct.unpack_from("<I", data, 0x50)[0])
            for text in ("Duration: 5 rounds", "30-ft. radius", "caster and nearby allies", "refreshes its duration"):
                self.assertIn(text, desc)
            self.assertNotIn("next hour", desc)

    def test_reordered_extra_records_modded_values_and_repeat_are_preserved(self):
        snapshots = []
        for repeat in (False, True):
            with self.installed(varied=True, repeat=repeat) as (root, data):
                original = root / "original.spl"
                original.write_bytes(data)
                result = root / "override/c0bw302.spl"
                projectile = parse_spl(result).abilities[0].projectile
                self.assert_spell(result, parse_spl(original), projectile)
                # Casting effect bytes and spell metadata survive table insertion.
                patched = result.read_bytes()
                eo = struct.unpack_from("<I", patched, 0x6a)[0]
                first, count = struct.unpack_from("<HH", patched, 0x6e)
                old_eo = struct.unpack_from("<I", data, 0x6a)[0]
                self.assertEqual(1, count)
                self.assertEqual(data[old_eo:old_eo + 48], patched[eo + first * 48:eo + (first + 1) * 48])
                snapshots.append({n: (root / "override" / n).read_bytes() for n in ("c0bw302.spl", "c0ga302.spl", "c0bwlck.pro")})
        self.assertEqual(*snapshots)

    def test_truncated_spell_fails_and_rolls_back(self):
        with self.installed(malformed=True) as (_, output):
            self.assertIn("Battleluck", output)

    def test_missing_payload_fails_and_rolls_back(self):
        with self.installed(missing=True) as (_, output):
            self.assertIn("no direct critical-hit/miss ability", output)


if __name__ == "__main__":
    unittest.main()
