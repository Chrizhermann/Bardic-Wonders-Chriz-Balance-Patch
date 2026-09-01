from __future__ import annotations

from pathlib import Path
import re
import unittest

from .ie_resources import parse_spl


ROOT = Path(__file__).resolve().parents[2]
PAYLOAD = ROOT / "BardicWonders" / "abettor" / "c0abets2.spl"
ABETTOR_TPA = ROOT / "BardicWonders" / "lib" / "abettor.tpa"


class SourcePayloadContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spell = parse_spl(PAYLOAD)

    def test_retains_all_seven_plus_70_skill_bonuses(self) -> None:
        for opcode in (92, 91, 90, 275, 59, 276, 277):
            with self.subTest(opcode=opcode):
                self.assertEqual(
                    1,
                    len(
                        self.spell.find_effects(
                            opcode=opcode,
                            target=2,
                            parameter1=70,
                        )
                    ),
                )

    def test_retains_the_ordinary_song_baseline(self) -> None:
        required = (
            {
                "opcode": 321,
                "target": 2,
                "timing": 1,
                "duration": 0,
                "resource": "C0ABETS2",
            },
            {
                "opcode": 215,
                "target": 2,
                "parameter2": 1,
                "duration": 8,
                "resource": "C0ABETT1",
            },
            {"opcode": 150, "target": 2},
            {"opcode": 65, "target": 2},
            {"opcode": 0, "target": 2, "parameter1": 3, "parameter2": 0},
            {"opcode": 69, "target": 2},
            {
                "opcode": 20,
                "target": 1,
                "parameter2": 1,
                "timing": 0,
                "duration": 6,
                "probability1": 100,
            },
        )
        for fields in required:
            with self.subTest(fields=fields):
                self.assertEqual(1, len(self.spell.find_effects(**fields)))

        for icon in (40, 58, 31):
            with self.subTest(icon=icon):
                self.assertEqual(
                    1,
                    len(
                        self.spell.find_effects(
                            opcode=142,
                            target=2,
                            parameter2=icon,
                            timing=0,
                            duration=6,
                        )
                    ),
                )

    def test_has_exactly_plus_1_to_each_save(self) -> None:
        for opcode in (33, 34, 35, 36, 37):
            with self.subTest(opcode=opcode):
                effects = self.spell.find_effects(opcode=opcode)
                self.assertEqual(1, len(effects))
                self.assertEqual(2, effects[0].target)
                self.assertEqual(1, effects[0].parameter1)

    def test_removes_the_old_singer_power_package(self) -> None:
        forbidden = (
            {"opcode": 22, "target": 1, "parameter1": 6},
            {"opcode": 250, "target": 1, "parameter1": 6},
            {"opcode": 0, "target": 1, "parameter1": 4, "parameter2": 0},
            {"opcode": 0, "target": 1, "parameter1": 4, "parameter2": 2},
            {"opcode": 219, "target": 1, "parameter1": 1, "parameter2": 8},
            {"opcode": 292, "target": 1, "parameter2": 1},
            {
                "opcode": 20,
                "target": 1,
                "parameter2": 0,
                "duration": 12,
                "probability1": 20,
            },
            {"opcode": 146, "target": 1, "resource": "SPSD02"},
        )
        for fields in forbidden:
            with self.subTest(fields=fields):
                self.assertEqual(0, len(self.spell.find_effects(**fields)))

        for opcode in (22, 250, 219, 292):
            with self.subTest(forbidden_opcode=opcode):
                self.assertEqual(
                    0,
                    len(self.spell.find_effects(opcode=opcode, target=1)),
                )


class SourceInstallerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = ABETTOR_TPA.read_text(encoding="utf-8")

    def test_kit_component_does_not_expose_symphony_before_component_2004(self) -> None:
        direct_hla_row = re.compile(
            r"patch_add_hla\b[^\r\n]*\bability\s*=\s*~AP_C0ABETHL~",
            re.IGNORECASE,
        )
        self.assertIsNone(direct_hla_row.search(self.text))

    def test_description_matches_the_approved_mechanics(self) -> None:
        for phrase in (
            "+70% to all thieving skills",
            "+3 bonus to Armor Class",
            "+1 bonus to all Saving Throws",
            "one round when the song begins",
            "one round when the song ends",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

        for removed_phrase in (
            "+6 to Luck",
            "immunity to backstab",
            "chance to stop time",
        ):
            with self.subTest(removed_phrase=removed_phrase):
                self.assertNotIn(removed_phrase, self.text)


if __name__ == "__main__":
    unittest.main()
