from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from .ie_resources import parse_spl, read_eff_resource
from .test_patcher import effect_bytes


ROOT = Path(__file__).resolve().parents[2]
WEIDU = ROOT / "Setup-BardicWonders.exe"
FINITE_TPA = ROOT / "BardicWonders" / "lib" / "abettor_hla_finite.tpa"
HLA_ACTIONS = ROOT / "BardicWonders" / "lib" / "hla_actions.tpa"


def controller_bytes(
    durations: tuple[int, ...] = (600, 700),
    *,
    payload_resource: str = "C0ABETS2",
    start_duration: int = 0,
    start_power: int = 0,
    start_special: int = 0,
    end_special: int = 40,
    first_global_opcode: int = 136,
    header_projectile: int = 1,
    start_probability: int = 100,
    extra_start_probability: int | None = None,
    extra_start_resist_dispel: int = 0,
    extra_start_dice_count: int = 0,
    extra_start_dice_size: int = 0,
    extra_start_save_type: int = 0,
    extra_start_resource: str = "C0SINGIN",
    extra_end_duration: int | None = None,
    extra_end_resist_dispel: int = 0,
    extra_end_resource: str = "C0SINGI2",
) -> bytes:
    ability_offset = 0x72
    global_effects = [
        effect_bytes(first_global_opcode, target=9, timing=1, duration=0),
        effect_bytes(
            146,
            target=9,
            parameter2=1,
            timing=1,
            duration=0,
            resource="C0BARDSX",
        ),
    ]
    effect_groups: list[list[bytes]] = []
    for duration in durations:
        effect_groups.append(
            [
                effect_bytes(138, target=9, parameter2=2, timing=1, duration=0),
                effect_bytes(
                    146,
                    target=9,
                    parameter2=1,
                    timing=1,
                    duration=0,
                    resource="C0BARDSX",
                ),
                effect_bytes(
                    177,
                    target=9,
                    power=start_power,
                    parameter2=2,
                    timing=10,
                    duration=duration,
                    resource=payload_resource,
                ),
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=duration,
                    resource=payload_resource,
                    special=end_special,
                ),
                effect_bytes(
                    177,
                    target=9,
                    parameter2=2,
                    timing=1,
                    duration=start_duration,
                    probability1=start_probability,
                    resource="C0SINGIN",
                    special=start_special,
                ),
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=duration,
                    resource="C0SINGIN",
                    special=end_special,
                ),
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=duration,
                    resource="C0SINGI2",
                    special=end_special,
                ),
                effect_bytes(
                    328,
                    target=9,
                    parameter2=85,
                    timing=10,
                    duration=duration,
                    resource=payload_resource,
                    special=1,
                ),
            ]
        )
        if extra_start_probability is not None:
            effect_groups[-1].append(
                effect_bytes(
                    177,
                    target=9,
                    parameter2=2,
                    timing=1,
                    duration=0,
                    probability1=extra_start_probability,
                    resource=extra_start_resource,
                    resist_dispel=extra_start_resist_dispel,
                    dice_count=extra_start_dice_count,
                    dice_size=extra_start_dice_size,
                    save_type=extra_start_save_type,
                )
            )
        if extra_end_duration is not None:
            effect_groups[-1].append(
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=extra_end_duration,
                    probability1=100,
                    resource=extra_end_resource,
                    resist_dispel=extra_end_resist_dispel,
                    special=40,
                )
            )

    effect_offset = ability_offset + len(effect_groups) * 0x28
    data = bytearray(effect_offset)
    data[:8] = b"SPL V1  "
    struct.pack_into("<H", data, 0x1C, 5)
    struct.pack_into("<I", data, 0x64, ability_offset)
    struct.pack_into("<H", data, 0x68, len(effect_groups))
    struct.pack_into("<I", data, 0x6A, effect_offset)
    struct.pack_into("<H", data, 0x6E, 0)
    struct.pack_into("<H", data, 0x70, len(global_effects))

    first_effect = len(global_effects)
    for index, effects in enumerate(effect_groups):
        offset = ability_offset + index * 0x28
        data[offset] = 1
        data[offset + 0x02] = 4
        data[offset + 0x0C] = 1
        struct.pack_into("<H", data, offset + 0x0E, 1)
        struct.pack_into("<H", data, offset + 0x10, index + 1)
        struct.pack_into("<H", data, offset + 0x1C, 1)
        struct.pack_into("<H", data, offset + 0x1E, len(effects))
        struct.pack_into("<H", data, offset + 0x20, first_effect)
        struct.pack_into("<H", data, offset + 0x22, 1)
        struct.pack_into("<H", data, offset + 0x24, 1)
        struct.pack_into("<H", data, offset + 0x26, header_projectile)
        first_effect += len(effects)

    return (
        bytes(data)
        + b"".join(global_effects)
        + b"".join(effect for group in effect_groups for effect in group)
    )


HLA_TABLE = """2DA V1.0
*
           ABILITY       ICON  STRREF  MIN_LEV  MAX_LEVEL  NUM_ALLOWED  PREREQUISITE  EXCLUDED_BY
C0ABET1    AP_C0ABETT5    *     *       1        99         1            *             *
C0ABET2    AP_C0ABETHL    *     *       1        99         1            AP_C0ABETT5   *
"""


class WeiduFiniteIntegrationTests(unittest.TestCase):
    def make_fixture(
        self,
        root: Path,
        *,
        finite: bool,
        payload_resref: str = "ZZPAYLD",
        start_duration: int = 0,
        start_power: int = 0,
        start_special: int = 0,
        end_special: int = 40,
        first_global_opcode: int = 136,
        header_projectile: int = 1,
        start_probability: int = 100,
        extra_start_probability: int | None = None,
        extra_start_resist_dispel: int = 0,
        extra_start_dice_count: int = 0,
        extra_start_dice_size: int = 0,
        extra_start_save_type: int = 0,
        extra_start_resource: str = "C0SINGIN",
        extra_end_duration: int | None = None,
        extra_end_resist_dispel: int = 0,
        extra_end_resource: str = "C0SINGI2",
    ) -> None:
        override = root / "override"
        library = root / "testmod" / "lib"
        override.mkdir(parents=True)
        library.mkdir(parents=True)

        shutil.copy2(FINITE_TPA, library / FINITE_TPA.name)
        shutil.copy2(HLA_ACTIONS, library / HLA_ACTIONS.name)
        shutil.copy2(
            ROOT / "BardicWonders" / "abettor" / "c0abethl.spl",
            override / "C0ABETHL.SPL",
        )
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
        shutil.copy2(
            ROOT / "BardicWonders" / "abettor" / "c0abets2.spl",
            override / f"{payload_resref}.SPL",
        )

        pointer = bytearray(
            (ROOT / "BardicWonders" / "bardsong" / "c0bardso.eff").read_bytes()
        )
        pointer[0x30:0x38] = payload_resref.encode("ascii").ljust(8, b"\0")
        (override / "C0ABETS2.EFF").write_bytes(pointer)
        (override / f"{payload_resref}.EFF").write_bytes(pointer)
        if finite:
            (override / "C0ABETS2.SPL").write_bytes(
                controller_bytes(
                    payload_resource=payload_resref,
                    start_duration=start_duration,
                    start_power=start_power,
                    start_special=start_special,
                    end_special=end_special,
                    first_global_opcode=first_global_opcode,
                    header_projectile=header_projectile,
                    start_probability=start_probability,
                    extra_start_probability=extra_start_probability,
                    extra_start_resist_dispel=extra_start_resist_dispel,
                    extra_start_dice_count=extra_start_dice_count,
                    extra_start_dice_size=extra_start_dice_size,
                    extra_start_save_type=extra_start_save_type,
                    extra_start_resource=extra_start_resource,
                    extra_end_duration=extra_end_duration,
                    extra_end_resist_dispel=extra_end_resist_dispel,
                    extra_end_resource=extra_end_resource,
                )
            )
        else:
            shutil.copy2(
                ROOT / "BardicWonders" / "abettor" / "c0abets2.spl",
                override / "C0ABETS2.SPL",
            )
        (override / "LUC0ABET.2DA").write_text(HLA_TABLE, encoding="ascii")

        (root / "testmod" / "setup-test.tp2").write_text(
            """BACKUP ~testmod/backup~
AUTHOR ~test~
ALWAYS
  INCLUDE ~testmod/lib/hla_actions.tpa~
END
LANGUAGE ~English~ ~english~
BEGIN ~Abettor finite integration test~ DESIGNATED 0
OUTER_SET c0bardso = 559
INCLUDE ~testmod/lib/abettor_hla_finite.tpa~
""",
            encoding="ascii",
        )

    def install(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(WEIDU),
                "--no-auto-tp2",
                "--nogame",
                "--search",
                "override",
                "--no-exit-pause",
                "--language",
                "0",
                "--force-install",
                "0",
                "testmod/setup-test.tp2",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_recognized_controller_gets_one_start_and_end_hook_per_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)

            result = self.install(root)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            controller = parse_spl(root / "override" / "C0ABETS2.SPL")
            for index, ability in enumerate(controller.abilities):
                with self.subTest(header=index):
                    self.assertEqual(
                        1,
                        sum(
                            effect.matches(
                                opcode=177,
                                target=9,
                                resource="C0ABIVS",
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
                                resource="C0ABIVE",
                            )
                            for effect in ability.effects
                        ),
                    )

            invisibility = parse_spl(root / "override" / "C0ABIVI.SPL")
            payload = parse_spl(root / "override" / "ZZPAYLD.SPL")
            self.assertNotEqual(559, payload.abilities[0].projectile)
            self.assertEqual(5, invisibility.abilities[0].target)
            self.assertEqual(50, invisibility.abilities[0].range)
            self.assertEqual(
                payload.abilities[0].projectile,
                invisibility.abilities[0].projectile,
            )
            self.assertEqual(1, len(invisibility.effects))
            self.assertTrue(
                invisibility.effects[0].matches(
                    opcode=20,
                    target=2,
                    parameter2=0,
                    timing=0,
                    duration=6,
                    probability1=100,
                )
            )
            self.assertEqual(
                "C0ABIVI", read_eff_resource(root / "override" / "C0ABIVS.EFF")
            )
            self.assertEqual(
                "C0ABIVI", read_eff_resource(root / "override" / "C0ABIVE.EFF")
            )
            for donor_name, clone_name in (
                ("C0SINGIN.EFF", "C0ABIVS.EFF"),
                ("C0SINGI2.EFF", "C0ABIVE.EFF"),
            ):
                donor = bytearray((root / "override" / donor_name).read_bytes())
                clone = bytearray((root / "override" / clone_name).read_bytes())
                donor[0x30:0x38] = clone[0x30:0x38]
                self.assertEqual(donor, clone)
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertEqual(1, table.count("AP_C0ABETHL"))
            self.assertEqual(
                "ZZPAYLD", read_eff_resource(root / "override" / "C0ABETS2.EFF")
            )

    def test_toggle_or_unrecognized_song_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=False)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_missing_hla_resource_still_removes_symphony_from_the_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            (root / "override" / "C0ABETHL.SPL").unlink()

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_probabilistic_start_controller_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True, start_probability=50)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_probabilistic_duplicate_is_not_cloned_into_an_extra_start_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(
                root,
                finite=True,
                extra_start_probability=50,
            )

            result = self.install(root)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            controller = parse_spl(root / "override" / "C0ABETS2.SPL")
            for index, ability in enumerate(controller.abilities):
                with self.subTest(header=index):
                    self.assertEqual(
                        1,
                        sum(effect.resource == "C0ABIVS" for effect in ability.effects),
                    )

    def test_tail_drifted_duplicate_is_not_cloned_into_an_extra_start_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(
                root,
                finite=True,
                extra_start_probability=100,
                extra_start_resist_dispel=1,
            )

            result = self.install(root)

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            controller = parse_spl(root / "override" / "C0ABETS2.SPL")
            for ability in controller.abilities:
                self.assertEqual(
                    1,
                    sum(effect.resource == "C0ABIVS" for effect in ability.effects),
                )

    def test_dice_and_save_drifted_duplicates_are_not_cloned(self) -> None:
        for field in ("extra_start_dice_count", "extra_start_dice_size", "extra_start_save_type"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(
                    root,
                    finite=True,
                    extra_start_probability=100,
                    **{field: 1},
                )

                result = self.install(root)

                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                controller = parse_spl(root / "override" / "C0ABETS2.SPL")
                for ability in controller.abilities:
                    self.assertEqual(
                        1,
                        sum(effect.resource == "C0ABIVS" for effect in ability.effects),
                    )

    def test_zero_duration_end_selector_duplicate_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True, extra_end_duration=0)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())

    def test_malformed_preexisting_hook_references_keep_symphony_unavailable(self) -> None:
        cases = (
            {
                "extra_start_probability": 50,
                "extra_start_resource": "C0ABIVS",
            },
            {
                "extra_end_duration": 0,
                "extra_end_resource": "C0ABIVE",
            },
            {
                "extra_start_probability": 50,
                "extra_start_resource": "C0ABIVI",
            },
        )
        for fixture_kwargs in cases:
            with self.subTest(fixture_kwargs=fixture_kwargs), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(root, finite=True, **fixture_kwargs)

                result = self.install(root)

                self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
                self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
                table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
                self.assertNotIn("AP_C0ABETHL", table)

    def test_drifted_end_hook_condition_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            end_hook = root / "override" / "C0SINGI2.EFF"
            data = bytearray(end_hook.read_bytes())
            struct.pack_into("<i", data, 0x1C, -2146422738)
            end_hook.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_drifted_hook_timing_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            start_hook = root / "override" / "C0SINGIN.EFF"
            data = bytearray(start_hook.read_bytes())
            struct.pack_into("<I", data, 0x24, 0x00010001)
            start_hook.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_non_song_invisibility_template_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            template = root / "override" / "C0SINGIN.SPL"
            data = bytearray(template.read_bytes())
            struct.pack_into("<H", data, 0x1C, 1)
            template.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_drifted_payload_pointer_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            pointer = root / "override" / "C0ABETS2.EFF"
            data = bytearray(pointer.read_bytes())
            struct.pack_into("<I", data, 0x10, 12)
            pointer.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_noninstant_start_effect_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True, start_duration=1)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_power_drift_in_start_effect_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True, start_power=1)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertIn(
                "skipping Symphony of the Dark Children",
                result.stdout + result.stderr,
            )
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_global_controller_drift_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True, first_global_opcode=12)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_start_special_drift_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True, start_special=1)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())

    def test_nonparty_payload_projectile_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            payload = root / "override" / "ZZPAYLD.SPL"
            data = bytearray(payload.read_bytes())
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            struct.pack_into("<H", data, ability_offset + 0x26, 177)
            payload.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())

    def test_hook_template_power_drift_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            hook = root / "override" / "C0SINGIN.EFF"
            data = bytearray(hook.read_bytes())
            struct.pack_into("<I", data, 0x18, 1)
            hook.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())

    def test_hook_template_reserved_field_drift_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            hook = root / "override" / "C0SINGIN.EFF"
            data = bytearray(hook.read_bytes())
            data[0x40] = 1
            hook.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())

    def test_pointer_secondary_signature_drift_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            pointer = root / "override" / "C0ABETS2.EFF"
            data = bytearray(pointer.read_bytes())
            data[0x08:0x10] = b"BROKEN!!"
            pointer.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())

    def test_reserved_output_collision_keeps_symphony_unavailable(self) -> None:
        for name in ("C0ABIVI.SPL", "C0ABIVS.EFF", "C0ABIVE.EFF"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(root, finite=True)
                collision = root / "override" / name
                collision.write_bytes(b"unrelated resource")
                before = collision.read_bytes()

                result = self.install(root)

                self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
                self.assertEqual(before, collision.read_bytes())
                table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_unusable_payload_header_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            payload = root / "override" / "ZZPAYLD.SPL"
            data = bytearray(payload.read_bytes())
            ability_offset = struct.unpack_from("<I", data, 0x64)[0]
            struct.pack_into("<H", data, ability_offset + 0x10, 0xFFFF)
            payload.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_missing_dynamic_payload_eff_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            (root / "override" / "ZZPAYLD.EFF").unlink()

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_malformed_dynamic_payload_eff_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True)
            payload_eff = root / "override" / "ZZPAYLD.EFF"
            data = bytearray(payload_eff.read_bytes())
            struct.pack_into("<I", data, 0x10, 145)
            payload_eff.write_bytes(data)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())
            table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
            self.assertNotIn("AP_C0ABETHL", table)

    def test_reserved_dynamic_payload_alias_keeps_symphony_unavailable(self) -> None:
        for payload_resref in ("C0ABIVI", "C0ABIVS", "C0ABIVE"):
            with self.subTest(payload_resref=payload_resref), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_fixture(root, finite=True, payload_resref=payload_resref)
                payload = root / "override" / f"{payload_resref}.SPL"
                payload_before = payload.read_bytes()

                result = self.install(root)

                self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
                self.assertEqual(payload_before, payload.read_bytes())
                table = (root / "override" / "LUC0ABET.2DA").read_text(encoding="ascii")
                self.assertNotIn("AP_C0ABETHL", table)

    def test_controller_header_projectile_drift_keeps_symphony_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_fixture(root, finite=True, header_projectile=177)

            result = self.install(root)

            self.assertIn(result.returncode, (0, 3), result.stdout + result.stderr)
            self.assertFalse((root / "override" / "C0ABIVI.SPL").exists())


if __name__ == "__main__":
    unittest.main()
