from __future__ import annotations

from pathlib import Path
import hashlib
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

from .ie_resources import parse_spl, read_eff_resource
from .test_patcher import effect_bytes, legacy_mutable_effects, spell_bytes
from .test_weidu_finite_integration import controller_bytes


ROOT = Path(__file__).resolve().parents[2]
WEIDU = ROOT / "Setup-BardicWonders.exe"
TAIL_ROOT = ROOT / "live-patch" / "abettor-hla"
TP2_NAME = "Setup-AbettorHLARebalance.tp2"
PAYLOAD_RESREF = "QXPAYLD"


def overpowered_payload(
    *,
    first_skill_bonus: int = 70,
    legacy_luck_special: int = 0,
    include_later_save: bool = False,
    include_later_luck: bool = False,
) -> bytes:
    retained = [
        effect_bytes(215, target=2, parameter2=1, timing=0, duration=8, resource="C0ABETT1"),
        effect_bytes(92, target=2, parameter1=first_skill_bonus),
        *(effect_bytes(opcode, target=2, parameter1=70) for opcode in (91, 90, 275, 59, 276, 277)),
        effect_bytes(150, target=2),
        effect_bytes(65, target=2),
        effect_bytes(0, target=2, parameter1=3, parameter2=0),
        effect_bytes(20, target=1, parameter2=1),
        effect_bytes(69, target=2),
        effect_bytes(142, target=2, parameter2=40),
        effect_bytes(142, target=2, parameter2=58),
        effect_bytes(142, target=2, parameter2=31),
        effect_bytes(326, target=1, timing=10, resource="C0BSNGEF", special=77123),
        # A later-mod marker that deliberately shares the old singer-AC shape.
        effect_bytes(0, target=1, parameter1=4, parameter2=0, resource="LATEFX"),
    ]
    legacy = [
        effect_bytes(22, target=1, parameter1=6, special=legacy_luck_special)
        if struct.unpack_from("<H", effect, 0)[0] == 22
        else effect
        for effect in legacy_mutable_effects()
    ]
    if include_later_save:
        legacy.append(
            effect_bytes(
                33,
                target=1,
                parameter1=2,
                resource="LATE33",
                special=9123,
            )
        )
    if include_later_luck:
        legacy.append(
            effect_bytes(
                22,
                target=1,
                parameter1=99,
                timing=1,
                duration=0,
                resource="LATE22",
                special=9123,
            )
        )
    return spell_bytes(retained + legacy)


def hla_with_later_marker() -> bytes:
    data = bytearray(
        (ROOT / "BardicWonders" / "abettor" / "c0abethl.spl").read_bytes()
    )
    ability_offset = struct.unpack_from("<I", data, 0x64)[0]
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    effect_count = struct.unpack_from("<H", data, ability_offset + 0x1E)[0]
    first_effect = struct.unpack_from("<H", data, ability_offset + 0x20)[0]
    insert_at = effect_offset + (first_effect + effect_count) * 0x30
    marker = effect_bytes(
        309,
        target=2,
        parameter1=1,
        timing=1,
        duration=0,
        resource="C0BWHLAB",
    )
    data[insert_at:insert_at] = marker
    struct.pack_into("<H", data, ability_offset + 0x1E, effect_count + 1)
    struct.pack_into("<I", data, 0x50, 0)
    return bytes(data)


def tlk_with_original_description() -> bytes:
    text = b"Original Symphony description"
    entry = bytearray(0x1A)
    struct.pack_into("<H", entry, 0x00, 7)
    struct.pack_into("<I", entry, 0x12, 0)
    struct.pack_into("<I", entry, 0x16, len(text))
    return b"TLK V1  " + struct.pack("<HII", 0, 1, 0x12 + 0x1A) + entry + text


def tlk_string(path: Path, strref: int) -> str:
    data = path.read_bytes()
    if data[:8] != b"TLK V1  ":
        raise AssertionError("invalid TLK signature")
    string_count = struct.unpack_from("<I", data, 0x0A)[0]
    string_data_offset = struct.unpack_from("<I", data, 0x0E)[0]
    if not 0 <= strref < string_count:
        raise AssertionError(f"strref {strref} outside 0..{string_count - 1}")
    entry = 0x12 + strref * 0x1A
    offset = struct.unpack_from("<I", data, entry + 0x12)[0]
    length = struct.unpack_from("<I", data, entry + 0x16)[0]
    return data[string_data_offset + offset : string_data_offset + offset + length].decode(
        "utf-8"
    )


def tlk_entries(path: Path) -> list[tuple[int, str]]:
    data = path.read_bytes()
    string_count = struct.unpack_from("<I", data, 0x0A)[0]
    return [
        (
            struct.unpack_from("<H", data, 0x12 + index * 0x1A)[0],
            tlk_string(path, index),
        )
        for index in range(string_count)
    ]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def component_ids(path: Path) -> list[tuple[str, int, int]]:
    entries: list[tuple[str, int, int]] = []
    pattern = re.compile(r"^~([^~]+)~\s+#(\d+)\s+#(\d+)")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            entries.append((match.group(1).upper(), int(match.group(2)), int(match.group(3))))
    return entries


class TailPatchIntegrationTests(unittest.TestCase):
    def make_fixture(
        self,
        root: Path,
        *,
        finite: bool = True,
        payload_resref: str = PAYLOAD_RESREF,
        first_skill_bonus: int = 70,
        controller_start_duration: int = 0,
        controller_start_power: int = 0,
        controller_end_special: int = 40,
        legacy_luck_special: int = 0,
        include_later_save: bool = False,
        include_later_luck: bool = False,
        controller_decoy_probability: int = 50,
        controller_decoy_resist_dispel: int = 0,
        controller_decoy_dice_count: int = 0,
        controller_decoy_dice_size: int = 0,
        controller_decoy_save_type: int = 0,
        controller_decoy_resource: str = "C0SINGIN",
        controller_decoy_end_duration: int | None = None,
        controller_decoy_end_resource: str = "C0SINGI2",
    ) -> None:
        override = root / "override"
        override.mkdir(parents=True)
        shutil.copy2(TAIL_ROOT / TP2_NAME, root / TP2_NAME)
        shutil.copytree(
            TAIL_ROOT / "abettor-hla-rebalance",
            root / "abettor-hla-rebalance",
        )

        (override / "C0ABETS2.SPL").write_bytes(
            controller_bytes(
                payload_resource=payload_resref,
                start_duration=controller_start_duration,
                start_power=controller_start_power,
                end_special=controller_end_special,
                extra_start_probability=controller_decoy_probability,
                extra_start_resist_dispel=controller_decoy_resist_dispel,
                extra_start_dice_count=controller_decoy_dice_count,
                extra_start_dice_size=controller_decoy_dice_size,
                extra_start_save_type=controller_decoy_save_type,
                extra_start_resource=controller_decoy_resource,
                extra_end_duration=controller_decoy_end_duration,
                extra_end_resource=controller_decoy_end_resource,
            )
            if finite
            else overpowered_payload()
        )
        pointer = bytearray(
            (ROOT / "BardicWonders" / "bardsong" / "c0bardso.eff").read_bytes()
        )
        pointer[0x30:0x38] = payload_resref.encode("ascii").ljust(8, b"\0")
        (override / "C0ABETS2.EFF").write_bytes(pointer)
        (override / f"{payload_resref}.EFF").write_bytes(pointer)
        (override / f"{payload_resref}.SPL").write_bytes(
            overpowered_payload(
                first_skill_bonus=first_skill_bonus,
                legacy_luck_special=legacy_luck_special,
                include_later_save=include_later_save,
                include_later_luck=include_later_luck,
            )
        )
        (override / "C0ABETHL.SPL").write_bytes(hla_with_later_marker())
        (override / "SHARED.SPL").write_bytes(hla_with_later_marker())
        shutil.copy2(
            ROOT / "BardicWonders" / "bardsong" / "c0singin.spl",
            override / "C0SINGIN.SPL",
        )
        shutil.copy2(
            ROOT / "BardicWonders" / "bardsong" / "c0singin.eff",
            override / "C0SINGIN.EFF",
        )
        shutil.copy2(
            ROOT / "BardicWonders" / "bardsong" / "c0singi2.eff",
            override / "C0SINGI2.EFF",
        )
        (root / "dialog.tlk").write_bytes(tlk_with_original_description())
        (root / "WeiDU.log").write_text(
            "// Log of Currently Installed WeiDU Mods\n"
            "~DUMMY/SETUP-DUMMY.TP2~ #0 #0 // Existing component\n",
            encoding="ascii",
        )

    def weidu(self, root: Path, operation: str) -> subprocess.CompletedProcess[str]:
        switch = "--force-install" if operation == "install" else "--force-uninstall"
        return subprocess.run(
            [
                str(WEIDU),
                "--no-auto-tp2",
                "--noautoupdate",
                "--nogame",
                "--search",
                "override",
                "--tlkin",
                "dialog.tlk",
                "--tlkout",
                "dialog.tlk",
                "--no-exit-pause",
                "--language",
                "0",
                switch,
                "0",
                TP2_NAME,
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_install_uses_dynamic_payload_and_uninstall_restores_exact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            tracked = (
                override / "C0ABETS2.SPL",
                override / "C0ABETS2.EFF",
                override / f"{PAYLOAD_RESREF}.SPL",
                override / "C0ABETHL.SPL",
                override / "SHARED.SPL",
            )
            before = {path: sha256(path) for path in tracked}
            before_tlk_entries = tlk_entries(root / "dialog.tlk")
            prior_components = component_ids(root / "WeiDU.log")

            install = self.weidu(root, "install")

            self.assertEqual(0, install.returncode, install.stdout + install.stderr)
            self.assertEqual(
                PAYLOAD_RESREF,
                read_eff_resource(override / "C0ABETS2.EFF"),
            )
            payload = parse_spl(override / f"{PAYLOAD_RESREF}.SPL")
            for opcode in (33, 34, 35, 36, 37):
                effects = payload.find_effects(opcode=opcode, target=2)
                self.assertEqual(1, len(effects))
                self.assertEqual(1, effects[0].parameter1)
            self.assertEqual(0, len(payload.find_effects(opcode=22, target=1)))
            self.assertEqual(
                1,
                len(payload.find_effects(opcode=0, target=1, resource="LATEFX")),
            )
            self.assertEqual(1, len(payload.find_effects(opcode=326, resource="C0BSNGEF")))
            self.assertEqual(
                1,
                len(parse_spl(override / "C0ABETHL.SPL").find_effects(opcode=309, resource="C0BWHLAB")),
            )

            controller = parse_spl(override / "C0ABETS2.SPL")
            for ability in controller.abilities:
                self.assertEqual(
                    1,
                    sum(
                        effect.matches(
                            opcode=177,
                            target=9,
                            power=0,
                            parameter1=0,
                            parameter2=2,
                            timing=1,
                            duration=0,
                            probability1=100,
                            probability2=0,
                            resource="C0ABIVS",
                            special=0,
                        )
                        for effect in ability.effects
                    ),
                )
                self.assertEqual(
                    1,
                    sum(
                        effect.matches(
                            opcode=272,
                            target=9,
                            power=0,
                            parameter1=6,
                            parameter2=3,
                            timing=10,
                            probability1=100,
                            probability2=0,
                            resource="C0ABIVE",
                            special=40,
                        )
                        for effect in ability.effects
                    ),
                )
            invisibility = parse_spl(override / "C0ABIVI.SPL")
            self.assertEqual(5, invisibility.spell_type)
            self.assertEqual(5, invisibility.abilities[0].target)
            self.assertEqual(50, invisibility.abilities[0].range)
            self.assertEqual(158, invisibility.abilities[0].projectile)
            self.assertEqual(payload.abilities[0].projectile, invisibility.abilities[0].projectile)
            self.assertEqual(1, len(invisibility.effects))
            self.assertTrue(
                invisibility.effects[0].matches(
                    opcode=20,
                    target=2,
                    parameter2=0,
                    timing=0,
                    duration=6,
                )
            )
            for donor_name, clone_name in (
                ("C0SINGIN.EFF", "C0ABIVS.EFF"),
                ("C0SINGI2.EFF", "C0ABIVE.EFF"),
            ):
                donor = bytearray((override / donor_name).read_bytes())
                clone = bytearray((override / clone_name).read_bytes())
                donor[0x30:0x38] = clone[0x30:0x38]
                self.assertEqual(donor, clone)

            hla_data = (override / "C0ABETHL.SPL").read_bytes()
            description_strref = struct.unpack_from("<I", hla_data, 0x50)[0]
            description = tlk_string(root / "dialog.tlk", description_strref)
            self.assertIn("one round when the song begins", description)
            self.assertIn("one round when the song ends", description)
            shared_data = (override / "SHARED.SPL").read_bytes()
            shared_description_strref = struct.unpack_from("<I", shared_data, 0x50)[0]
            self.assertEqual(
                "Original Symphony description",
                tlk_string(root / "dialog.tlk", shared_description_strref),
            )
            installed_components = component_ids(root / "WeiDU.log")
            self.assertEqual(prior_components, installed_components[:-1])
            self.assertIn("SETUP-ABETTORHLAREBALANCE.TP2", installed_components[-1][0])

            uninstall = self.weidu(root, "uninstall")

            self.assertEqual(0, uninstall.returncode, uninstall.stdout + uninstall.stderr)
            for path, expected_hash in before.items():
                with self.subTest(restored=path.name):
                    self.assertEqual(expected_hash, sha256(path))
            self.assertEqual(
                before_tlk_entries,
                tlk_entries(root / "dialog.tlk")[: len(before_tlk_entries)],
            )
            self.assertGreaterEqual(
                len(tlk_entries(root / "dialog.tlk")),
                len(before_tlk_entries),
            )
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            self.assertFalse((override / "C0ABIVS.EFF").exists())
            self.assertFalse((override / "C0ABIVE.EFF").exists())
            self.assertEqual(prior_components, component_ids(root / "WeiDU.log"))

    def test_toggle_controller_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=False)
            override = root / "override"
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("recognized finite-song contract", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_retained_payload_drift_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, first_skill_bonus=69)
            override = root / "override"
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("recognized finite-song contract", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_drifted_end_hook_condition_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            end_hook = override / "C0SINGI2.EFF"
            data = bytearray(end_hook.read_bytes())
            struct.pack_into("<i", data, 0x1C, -2146422738)
            end_hook.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("recognized finite-song contract", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_drifted_hook_timing_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            start_hook = override / "C0SINGIN.EFF"
            data = bytearray(start_hook.read_bytes())
            struct.pack_into("<I", data, 0x24, 0x00010001)
            start_hook.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("recognized finite-song contract", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_non_song_invisibility_template_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            template = override / "C0SINGIN.SPL"
            data = bytearray(template.read_bytes())
            struct.pack_into("<H", data, 0x1C, 1)
            template.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("recognized finite-song contract", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_probabilistic_payload_pointer_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            pointer = override / "C0ABETS2.EFF"
            data = bytearray(pointer.read_bytes())
            struct.pack_into("<H", data, 0x2C, 50)
            pointer.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("dynamic Symphony payload pointer", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_noninstant_start_effect_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, controller_start_duration=1)
            override = root / "override"
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("recognized finite-song contract", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_power_drift_in_start_effect_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, controller_start_power=1)
            override = root / "override"
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertIn("recognized finite-song contract", install.stdout + install.stderr)
            self.assertEqual(before, {path: sha256(path) for path in tracked})
            self.assertFalse((override / "C0ABIVI.SPL").exists())
            log = (root / "WeiDU.log").read_text(encoding="utf-8")
            self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_end_special_drift_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, controller_end_special=41)
            override = root / "override"
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_tail_drifted_duplicate_is_not_cloned_into_an_extra_start_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(
                root,
                controller_decoy_probability=100,
                controller_decoy_resist_dispel=1,
            )
            override = root / "override"

            install = self.weidu(root, "install")

            self.assertEqual(0, install.returncode, install.stdout + install.stderr)
            controller = parse_spl(override / "C0ABETS2.SPL")
            for ability in controller.abilities:
                self.assertEqual(
                    1,
                    sum(effect.resource == "C0ABIVS" for effect in ability.effects),
                )

    def test_dice_and_save_drifted_duplicates_are_not_cloned(self) -> None:
        cases = (
            {"controller_decoy_dice_count": 1},
            {"controller_decoy_dice_size": 1},
            {"controller_decoy_save_type": 1},
        )
        for fixture_kwargs in cases:
            with self.subTest(fixture_kwargs=fixture_kwargs), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(
                    root,
                    controller_decoy_probability=100,
                    **fixture_kwargs,
                )

                install = self.weidu(root, "install")

                self.assertEqual(0, install.returncode, install.stdout + install.stderr)
                controller = parse_spl(root / "override" / "C0ABETS2.SPL")
                for ability in controller.abilities:
                    self.assertEqual(
                        1,
                        sum(effect.resource == "C0ABIVS" for effect in ability.effects),
                    )

    def test_zero_duration_end_selector_duplicate_is_refused_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, controller_decoy_end_duration=0)
            override = root / "override"
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_malformed_preexisting_hook_references_are_refused_before_writes(self) -> None:
        cases = (
            {
                "controller_decoy_probability": 50,
                "controller_decoy_resource": "C0ABIVS",
            },
            {
                "controller_decoy_end_duration": 0,
                "controller_decoy_end_resource": "C0ABIVE",
            },
            {
                "controller_decoy_probability": 50,
                "controller_decoy_resource": "C0ABIVI",
            },
        )
        for fixture_kwargs in cases:
            with self.subTest(fixture_kwargs=fixture_kwargs), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(root, **fixture_kwargs)
                override = root / "override"
                tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
                before = {path: sha256(path) for path in tracked}

                install = self.weidu(root, "install")

                self.assertNotEqual(0, install.returncode)
                self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_nonparty_payload_projectile_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            payload = override / f"{PAYLOAD_RESREF}.SPL"
            data = bytearray(payload.read_bytes())
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            struct.pack_into("<H", data, ability_offset + 0x26, 177)
            payload.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_unusable_payload_header_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            payload = override / f"{PAYLOAD_RESREF}.SPL"
            data = bytearray(payload.read_bytes())
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            struct.pack_into("<H", data, ability_offset + 0x10, 0xFFFF)
            payload.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_missing_dynamic_payload_eff_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            (override / f"{PAYLOAD_RESREF}.EFF").unlink()
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_malformed_dynamic_payload_eff_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            payload_eff = override / f"{PAYLOAD_RESREF}.EFF"
            data = bytearray(payload_eff.read_bytes())
            struct.pack_into("<I", data, 0x10, 145)
            payload_eff.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_reserved_dynamic_payload_alias_is_refused_before_any_resource_write(self) -> None:
        for payload_resref in ("C0ABIVI", "C0ABIVS", "C0ABIVE"):
            with self.subTest(payload_resref=payload_resref), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(root, payload_resref=payload_resref)
                override = root / "override"
                tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
                before = {path: sha256(path) for path in tracked}

                install = self.weidu(root, "install")

                self.assertNotEqual(0, install.returncode)
                self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_reserved_output_collision_is_refused_before_any_resource_write(self) -> None:
        for name in ("C0ABIVI.SPL", "C0ABIVS.EFF", "C0ABIVE.EFF"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(root)
                override = root / "override"
                collision = override / name
                collision.write_bytes(b"unrelated resource")
                tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
                before = {path: sha256(path) for path in tracked}

                install = self.weidu(root, "install")

                self.assertNotEqual(0, install.returncode)
                self.assertIn("reserved", (install.stdout + install.stderr).lower())
                self.assertEqual(before, {path: sha256(path) for path in tracked})
                log = (root / "WeiDU.log").read_text(encoding="utf-8")
                self.assertNotIn("SETUP-ABETTORHLAREBALANCE.TP2", log.upper())

    def test_payload_tail_field_drift_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, legacy_luck_special=1)
            override = root / "override"
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_unrelated_later_save_effect_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, include_later_save=True)
            override = root / "override"

            install = self.weidu(root, "install")

            self.assertEqual(0, install.returncode, install.stdout + install.stderr)
            payload = parse_spl(override / f"{PAYLOAD_RESREF}.SPL")
            preserved = payload.find_effects(opcode=33, target=1, resource="LATE33")
            self.assertEqual(1, len(preserved))
            self.assertEqual(9123, preserved[0].special)

    def test_hla_song_change_drift_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            hla = override / "C0ABETHL.SPL"
            data = bytearray(hla.read_bytes())
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
            first_effect = struct.unpack_from("<H", data, ability_offset + 0x20)[0]
            data[effect_offset + first_effect * 0x30 + 0x0C] = 8
            hla.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_malformed_pointer_padding_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            pointer = override / "C0ABETS2.EFF"
            data = bytearray(pointer.read_bytes())
            data[0x30:0x38] = b"QXP\0BAD!"
            pointer.write_bytes(data)
            (override / "QXP.SPL").write_bytes(
                (override / f"{PAYLOAD_RESREF}.SPL").read_bytes()
            )
            controller = override / "C0ABETS2.SPL"
            controller.write_bytes(controller_bytes(payload_resource="QXP"))
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})

    def test_pointer_reserved_field_drift_is_refused_before_any_resource_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root)
            override = root / "override"
            pointer = override / "C0ABETS2.EFF"
            data = bytearray(pointer.read_bytes())
            data[0x40] = 1
            pointer.write_bytes(data)
            tracked = tuple(override.iterdir()) + (root / "dialog.tlk",)
            before = {path: sha256(path) for path in tracked}

            install = self.weidu(root, "install")

            self.assertNotEqual(0, install.returncode)
            self.assertEqual(before, {path: sha256(path) for path in tracked})


if __name__ == "__main__":
    unittest.main()
