"""Run the real component-2004 producer before validating its finite controller.

All inputs come from the repository; WeiDU runs only inside TemporaryDirectory.
In particular, these tests never manufacture a C0ABETS2 controller or its EFF.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from .ie_resources import parse_spl, read_eff_resource
from .test_tail_patch_integration import tlk_string, tlk_with_original_description
from .test_weidu_finite_integration import HLA_TABLE


ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "BardicWonders"
WEIDU = ROOT / "Setup-BardicWonders.exe"


def resource(directory: Path, name: str) -> Path:
    matches = [path for path in directory.iterdir() if path.name.upper() == name.upper()]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one {name} in {directory}: {matches}")
    return matches[0]


def effect_records(path: Path) -> tuple[tuple[bytes, ...], tuple[tuple[bytes, ...], ...]]:
    """Keep raw records, including fields the semantic parser does not expose."""
    data = path.read_bytes()
    abilities = struct.unpack_from("<I", data, 0x64)[0]
    count = struct.unpack_from("<H", data, 0x68)[0]
    effects = struct.unpack_from("<I", data, 0x6A)[0]

    def records(first: int, length: int) -> tuple[bytes, ...]:
        return tuple(data[effects + n * 48 : effects + (n + 1) * 48] for n in range(first, first + length))

    global_first, global_count = struct.unpack_from("<HH", data, 0x6E)
    headers = []
    for index in range(count):
        length, first = struct.unpack_from("<HH", data, abilities + index * 40 + 0x1E)
        headers.append(records(first, length))
    return records(global_first, global_count), tuple(headers)


class Component2004ProducerTests(unittest.TestCase):
    def make_fixture(self, root: Path, *, existing_projectile: int, reserve_payload_name: bool = False) -> None:
        override = root / "override"
        override.mkdir()
        library = root / "testmod" / "lib"
        library.mkdir(parents=True)
        shutil.copytree(MOD / "bardsong", root / "testmod" / "bardsong")
        for name in ("bardsongtweaks.tpa", "hla_actions.tpa"):
            shutil.copy2(MOD / "lib" / name, library / name)
        shutil.copy2(MOD / "lib" / "abettor_hla_finite.tpa", library / "finite_actual.tpa")
        # Capture what the unchanged producer actually emits immediately before
        # its existing finite-integration INCLUDE. No producer code is replaced.
        (library / "abettor_hla_finite.tpa").write_text(
            "COPY ~override~ ~producer-snapshot~\nINCLUDE ~testmod/lib/finite_actual.tpa~\n",
            encoding="ascii",
        )
        for name in ("c0abets2.spl", "c0abethl.spl"):
            shutil.copy2(MOD / "abettor" / name, override / name)
        (override / "LUC0ABET.2DA").write_text(HLA_TABLE, encoding="ascii")
        (override / "KITLIST.2DA").write_text(
            "2DA V1.0\n*\n LABEL NAME LOWER MIXED HELP CLAB PROF UNUSABLE CLASS KITIDS\n"
            "0 MAGE 0 0 0 0 CLABMA01 0 0 1 0\n",
            encoding="ascii",
        )
        (override / "PROJECTL.IDS").write_text(f"IDS V1.0\n{existing_projectile} EXISTING\n", encoding="ascii")
        (override / "MISSILE.IDS").write_text("IDS V1.0\n0 NONE\n", encoding="ascii")
        (override / "ENGINEST.2DA").write_text(
            "2DA V1.0\n0\n STRREF\nSTRREF_FEEDBACK_BATTLESONGBEGIN 0\nSTRREF_FEEDBACK_BATTLESONGEND 0\n",
            encoding="ascii",
        )
        for name in ("INAREANP", "INAREA", "INAREASM", "BIGNAREA", "INAREAPA"):
            shutil.copy2(MOD / "bardsong" / "c0bardso.PRO", override / f"{name}.PRO")
        shutil.copy2(MOD / "items" / "c0bwam1.itm", override / "FIXTURE.ITM")
        # A genuine empty compiled script exercises the component's final scan.
        (override / "FIXTURE.BCS").write_text("SC\nSC\n", encoding="ascii")
        (root / "chitin.key").write_bytes(b"KEY V1  " + struct.pack("<IIII", 0, 0, 24, 24))
        (root / "dialog.tlk").write_bytes(tlk_with_original_description())
        (root / "WeiDU.log").write_text("", encoding="ascii")
        allocator_seed = (
            "COPY_EXISTING ~C0ABETHL.SPL~ ~override~\n"
            " LPF GET_UNIQUE_FILE_NAME STR_VAR extension = ~SPL~ base = ~FIXTURE~ RET fixture_name = filename END\n"
            "BUT_ONLY\n"
            if reserve_payload_name else ""
        )
        (root / "testmod" / "setup-test.tp2").write_text(
            "BACKUP ~testmod/backup~\nAUTHOR ~test~\n"
            "ALWAYS\n INCLUDE ~testmod/lib/hla_actions.tpa~\nEND\n"
            "LANGUAGE ~English~ ~english~\n"
            "BEGIN ~Bard Song Mechanics Tweak producer regression~ DESIGNATED 2004\n"
            + allocator_seed +
            "INCLUDE ~testmod/lib/bardsongtweaks.tpa~\n",
            encoding="ascii",
        )

    def install(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(WEIDU), "testmod/setup-test.tp2", "--no-auto-tp2", "--game", str(root), "--no-exit-pause",
             "--language", "0", "--force-install-list", "2004"],
            cwd=root, text=True, capture_output=True, check=False, timeout=60,
        )

    def test_real_producer_accepts_dynamic_ids_without_phantom_base_eff(self) -> None:
        payloads: list[str] = []
        projectile_ids: list[int] = []
        for projectile_seed in (558, 1200):
            with self.subTest(projectile_seed=projectile_seed), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(root, existing_projectile=projectile_seed, reserve_payload_name=bool(payloads))
                result = self.install(root)
                output = result.stdout + result.stderr
                before = root / "producer-snapshot"
                self.assertTrue(before.is_dir(), output)
                original = parse_spl(resource(before, "C0ABETS2.SPL"))
                payload = next(effect.resource for effect in original.abilities[0].effects if effect.opcode == 177 and effect.timing == 10)
                payloads.append(payload)
                projectile_ids.append(original.abilities[0].projectile)
                self.assertFalse((before / "C0ABETS2.EFF").exists())
                self.assertEqual(payload, read_eff_resource(resource(before, f"{payload}.EFF")))
                self.assertEqual(11, len(original.abilities))
                self.assertNotEqual(1, original.abilities[0].projectile)
                projectile_entry = next(
                    line.split() for line in resource(before, "PROJECTL.IDS").read_text().splitlines()
                    if line.split() and line.split()[-1].upper() == "C0BARDSO"
                )
                self.assertEqual(int(projectile_entry[0]) + 1, original.abilities[0].projectile)
                self.assertEqual(0, next(effect.parameter2 for effect in original.abilities[0].effects if effect.resource == "C0BARDSX"))
                singing = parse_spl(resource(before, "C0SINGIN.SPL"))
                display = next(effect for effect in singing.effects if effect.opcode == 139)
                self.assertGreater(display.parameter1, 0)
                self.assertEqual("Singing Bard Song", tlk_string(root / "dialog.tlk", display.parameter1))
                self.assertEqual(0, result.returncode, output)
                self.assertNotIn("skipping Symphony of the Dark Children", output)
                self.assertIn("Symphony of the Dark Children enabled", output)

                after = root / "override"
                patched = parse_spl(resource(after, "C0ABETS2.SPL"))
                before_globals, before_headers = effect_records(resource(before, "C0ABETS2.SPL"))
                after_globals, after_headers = effect_records(resource(after, "C0ABETS2.SPL"))
                self.assertEqual(before_globals, after_globals)
                for index, (old, new) in enumerate(zip(original.abilities, patched.abilities, strict=True)):
                    self.assertEqual(old.projectile, new.projectile)
                    self.assertEqual(old.required_level, new.required_level)
                    starts = [effect for effect in new.effects if effect.resource == "C0ABIVS"]
                    ends = [effect for effect in new.effects if effect.resource == "C0ABIVE"]
                    self.assertEqual(1, len(starts))
                    self.assertEqual(1, len(ends))
                    self.assertTrue(starts[0].matches(opcode=177, target=9, timing=1, duration=0))
                    duration = next(effect.duration for effect in old.effects if effect.resource == "C0SINGI2")
                    self.assertEqual(600 + index * 100, duration)
                    self.assertEqual(1 if index == 0 else index * 5, new.required_level)
                    self.assertTrue(ends[0].matches(opcode=272, target=9, timing=10, duration=duration, parameter1=6, parameter2=3, special=40))
                    retained = tuple(record for record in after_headers[index] if record[0x14:0x1C].split(b"\0", 1)[0] not in (b"C0ABIVS", b"C0ABIVE"))
                    self.assertEqual(before_headers[index], retained)
                self.assertEqual(resource(before, f"{payload}.SPL").read_bytes(), resource(after, f"{payload}.SPL").read_bytes())
                self.assertEqual(resource(before, "C0BARDSX.SPL").read_bytes(), resource(after, "C0BARDSX.SPL").read_bytes())
                cooldown = parse_spl(resource(after, "C0BARDSX.SPL"))
                self.assertEqual(1, len(cooldown.find_effects(opcode=144, target=9, parameter2=10, timing=10, duration=1000)))
                self.assertEqual(1, len(cooldown.find_effects(opcode=139, target=9, timing=3, duration=66)))
                self.assertFalse((after / "C0ABETS2.EFF").exists())
                self.assertEqual(1, resource(after, "LUC0ABET.2DA").read_text().count("AP_C0ABETHL"))
                invisibility = parse_spl(resource(after, "C0ABIVI.SPL"))
                self.assertEqual(158, invisibility.abilities[0].projectile)
                self.assertEqual(5, invisibility.abilities[0].target)
                self.assertEqual(1, len(invisibility.effects))
                self.assertTrue(invisibility.effects[0].matches(opcode=20, target=2, parameter2=0, timing=0, duration=6))
        self.assertEqual(2, len(set(projectile_ids)))
        self.assertEqual(2, len(set(payloads)))


if __name__ == "__main__":
    unittest.main()
