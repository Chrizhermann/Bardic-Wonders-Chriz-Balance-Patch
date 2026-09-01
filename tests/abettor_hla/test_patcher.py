from __future__ import annotations

from pathlib import Path
import hashlib
import struct
import subprocess
import sys
import tempfile
import unittest

from .ie_resources import parse_spl


ROOT = Path(__file__).resolve().parents[2]
PATCHER = ROOT / "tools" / "rebalance_abettor_hla.py"


def effect_bytes(
    opcode: int,
    *,
    target: int,
    power: int = 0,
    parameter1: int = 0,
    parameter2: int = 0,
    timing: int = 0,
    duration: int = 6,
    probability1: int = 100,
    probability2: int = 0,
    resource: str = "",
    resist_dispel: int = 0,
    dice_count: int = 0,
    dice_size: int = 0,
    save_type: int = 0,
    save_bonus: int = 0,
    special: int = 0,
) -> bytes:
    effect = bytearray(0x30)
    struct.pack_into("<H", effect, 0x00, opcode)
    effect[0x02] = target
    effect[0x03] = power
    struct.pack_into("<i", effect, 0x04, parameter1)
    struct.pack_into("<i", effect, 0x08, parameter2)
    effect[0x0C] = timing
    effect[0x0D] = resist_dispel
    struct.pack_into("<I", effect, 0x0E, duration)
    effect[0x12] = probability1
    effect[0x13] = probability2
    effect[0x14:0x1C] = resource.encode("ascii").ljust(8, b"\0")
    struct.pack_into("<I", effect, 0x1C, dice_count)
    struct.pack_into("<I", effect, 0x20, dice_size)
    struct.pack_into("<I", effect, 0x24, save_type)
    struct.pack_into("<i", effect, 0x28, save_bonus)
    struct.pack_into("<I", effect, 0x2C, special)
    return bytes(effect)


def legacy_mutable_effects() -> list[bytes]:
    return [
        effect_bytes(219, target=1, parameter1=1, parameter2=8),
        effect_bytes(33, target=2, parameter1=5),
        effect_bytes(22, target=1, parameter1=6),
        effect_bytes(34, target=2, parameter1=5),
        effect_bytes(0, target=1, parameter1=4, parameter2=2),
        effect_bytes(35, target=2, parameter1=5),
        effect_bytes(250, target=1, parameter1=6),
        effect_bytes(20, target=1, parameter2=0, duration=12, probability1=20),
        effect_bytes(36, target=2, parameter1=5),
        effect_bytes(292, target=1, parameter2=1),
        effect_bytes(
            146,
            target=1,
            parameter2=1,
            timing=1,
            duration=0,
            probability1=5,
            resource="SPSD02",
        ),
        effect_bytes(37, target=2, parameter1=5),
        effect_bytes(0, target=1, parameter1=4, parameter2=0),
        effect_bytes(219, target=1, parameter1=1, parameter2=8),
    ]


def overpowered_effects() -> list[bytes]:
    effects = [
        effect_bytes(
            321,
            target=2,
            parameter2=0,
            timing=1,
            duration=0,
            resource="C0ABETS2",
        ),
        effect_bytes(215, target=2, parameter2=1, duration=8, resource="C0ABETT1"),
        *(effect_bytes(opcode, target=2, parameter1=70) for opcode in (92, 91, 90, 275, 59, 276, 277)),
        effect_bytes(150, target=2),
        effect_bytes(65, target=2),
        effect_bytes(0, target=2, parameter1=3),
        effect_bytes(20, target=1, parameter2=1),
        effect_bytes(69, target=2),
        effect_bytes(142, target=2, parameter2=40),
        effect_bytes(142, target=2, parameter2=58),
        effect_bytes(142, target=2, parameter2=31),
        effect_bytes(326, target=1, timing=10, resource="C0BSNGEF", special=77123),
        *legacy_mutable_effects(),
    ]
    return effects


def spell_bytes(effects: list[bytes]) -> bytes:
    ability_offset = 0x72
    effect_offset = ability_offset + 0x28
    data = bytearray(effect_offset)
    data[:8] = b"SPL V1  "
    struct.pack_into("<H", data, 0x1C, 5)
    struct.pack_into("<I", data, 0x64, ability_offset)
    struct.pack_into("<H", data, 0x68, 1)
    struct.pack_into("<I", data, 0x6A, effect_offset)
    struct.pack_into("<H", data, 0x70, 0)
    data[ability_offset] = 1
    data[ability_offset + 0x02] = 4
    data[ability_offset + 0x0C] = 5
    struct.pack_into("<H", data, ability_offset + 0x0E, 50)
    struct.pack_into("<H", data, ability_offset + 0x10, 1)
    struct.pack_into("<H", data, ability_offset + 0x16, 6)
    struct.pack_into("<H", data, ability_offset + 0x1C, 1)
    struct.pack_into("<H", data, ability_offset + 0x1E, len(effects))
    struct.pack_into("<H", data, ability_offset + 0x20, 0)
    struct.pack_into("<H", data, ability_offset + 0x22, 1)
    struct.pack_into("<H", data, ability_offset + 0x24, 1)
    struct.pack_into("<H", data, ability_offset + 0x26, 158)
    return bytes(data) + b"".join(effects)


class SemanticPatcherTests(unittest.TestCase):
    def run_patcher(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PATCHER), str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_patches_reordered_effects_and_preserves_unmatched_effects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            path.write_bytes(spell_bytes(overpowered_effects()))

            result = self.run_patcher(path)

            self.assertEqual(0, result.returncode, result.stderr)
            spell = parse_spl(path)
            for opcode in (33, 34, 35, 36, 37):
                effects = spell.find_effects(opcode=opcode, target=2)
                self.assertEqual(1, len(effects))
                self.assertEqual(1, effects[0].parameter1)
            self.assertEqual(0, len(spell.find_effects(opcode=22, target=1)))
            preserved = spell.find_effects(opcode=326, resource="C0BSNGEF")
            self.assertEqual(1, len(preserved))
            self.assertEqual(77123, preserved[0].special)

    def test_second_run_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            path.write_bytes(spell_bytes(overpowered_effects()))
            first = self.run_patcher(path)
            first_hash = hashlib.sha256(path.read_bytes()).hexdigest()

            second = self.run_patcher(path)
            second_hash = hashlib.sha256(path.read_bytes()).hexdigest()

            self.assertEqual(0, first.returncode, first.stderr)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(first_hash, second_hash)
            self.assertIn("already balanced", second.stdout.lower())

    def test_refuses_partial_or_drifted_input_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            effects = overpowered_effects()
            effects = [
                effect_bytes(37, target=2, parameter1=4)
                if struct.unpack_from("<H", effect, 0)[0] == 37
                else effect
                for effect in effects
            ]
            path.write_bytes(spell_bytes(effects))
            before = hashlib.sha256(path.read_bytes()).hexdigest()

            result = self.run_patcher(path)

            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(before, after)
            self.assertIn("refusing", result.stderr.lower())

    def test_refuses_input_missing_a_retained_effect_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            effects = [
                effect
                for effect in overpowered_effects()
                if struct.unpack_from("<H", effect, 0)[0] != 65
            ]
            path.write_bytes(spell_bytes(effects))
            before = hashlib.sha256(path.read_bytes()).hexdigest()

            result = self.run_patcher(path)

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_refuses_balanced_input_with_an_extra_save_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            patched, changed = __import__(
                "tools.rebalance_abettor_hla", fromlist=["patch_bytes"]
            ).patch_bytes(spell_bytes(overpowered_effects()))
            self.assertTrue(changed)
            data = bytearray(patched)
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
            effect_count = struct.unpack_from("<H", data, ability_offset + 0x1E)[0]
            data.extend(effect_bytes(33, target=2, parameter1=5))
            struct.pack_into("<H", data, ability_offset + 0x1E, effect_count + 1)
            path.write_bytes(data)
            before = hashlib.sha256(path.read_bytes()).hexdigest()

            result = self.run_patcher(path)

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_refuses_balanced_input_with_a_drifted_luck_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            patcher = __import__("tools.rebalance_abettor_hla", fromlist=["patch_bytes"])
            patched, changed = patcher.patch_bytes(spell_bytes(overpowered_effects()))
            self.assertTrue(changed)
            data = bytearray(patched)
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            effect_count = struct.unpack_from("<H", data, ability_offset + 0x1E)[0]
            data.extend(effect_bytes(22, target=1, parameter1=5))
            struct.pack_into("<H", data, ability_offset + 0x1E, effect_count + 1)
            path.write_bytes(data)

            result = self.run_patcher(path)

            self.assertNotEqual(0, result.returncode)

    def test_refuses_old_effect_with_tail_field_drift_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            effects = [
                effect_bytes(22, target=1, parameter1=6, special=1)
                if struct.unpack_from("<H", effect, 0)[0] == 22
                else effect
                for effect in overpowered_effects()
            ]
            path.write_bytes(spell_bytes(effects))
            before = hashlib.sha256(path.read_bytes()).hexdigest()

            result = self.run_patcher(path)

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_preserves_an_unrelated_later_save_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.spl"
            later = effect_bytes(
                33,
                target=1,
                parameter1=2,
                resource="LATE33",
                special=9123,
            )
            path.write_bytes(spell_bytes(overpowered_effects() + [later]))

            result = self.run_patcher(path)

            self.assertEqual(0, result.returncode, result.stderr)
            spell = parse_spl(path)
            preserved = spell.find_effects(opcode=33, target=1, resource="LATE33")
            self.assertEqual(1, len(preserved))
            self.assertEqual(9123, preserved[0].special)


if __name__ == "__main__":
    unittest.main()
