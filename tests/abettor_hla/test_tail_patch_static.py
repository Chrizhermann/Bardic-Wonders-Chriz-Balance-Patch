from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TAIL_ROOT = ROOT / "live-patch" / "abettor-hla"
TP2 = TAIL_ROOT / "Setup-AbettorHLARebalance.tp2"
PATCH_TPA = TAIL_ROOT / "abettor-hla-rebalance" / "lib" / "patch.tpa"
README = TAIL_ROOT / "README.md"


class TailPatchStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tp2 = TP2.read_text(encoding="utf-8") if TP2.exists() else ""
        cls.patch = PATCH_TPA.read_text(encoding="utf-8") if PATCH_TPA.exists() else ""
        cls.readme = README.read_text(encoding="utf-8") if README.exists() else ""

    def test_tail_component_is_single_scoped_and_reversible(self) -> None:
        self.assertTrue(TP2.exists())
        self.assertEqual(1, self.tp2.count("BEGIN ~"))
        self.assertIn("BACKUP", self.tp2)
        self.assertIn("DESIGNATED 0", self.tp2)
        self.assertIn("INCLUDE ~abettor-hla-rebalance/lib/patch.tpa~", self.tp2)

    def test_tail_patch_resolves_the_payload_dynamically(self) -> None:
        self.assertTrue(PATCH_TPA.exists())
        self.assertIn("C0ABETS2.EFF", self.patch)
        self.assertIn("READ_ASCII 0x30", self.patch)
        self.assertIn("FILE_EXISTS_IN_GAME ~%c0_abettor_payload%.SPL~", self.patch)
        self.assertNotIn("C0ABETS4", self.patch)

    def test_tail_patch_has_semantic_drift_guards(self) -> None:
        for token in (
            "C0_VALIDATE_ABETTOR_PAYLOAD",
            "ALTER_EFFECT",
            "DELETE_EFFECT",
            "C0_VALIDATE_ABETTOR_FINITE_CONTROLLER",
            "C0BSNGEF",
            "C0BWHLAB",
            "FAIL",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.patch)

    def test_weidu_effect_selectors_use_supported_tail_field_names(self) -> None:
        for invalid in ("match_dicethrown", "match_dicesides", "match_savetype"):
            with self.subTest(invalid=invalid):
                self.assertNotIn(invalid, self.patch)
        for supported in ("match_dicenumber", "match_dicesize", "match_savingthrow"):
            with self.subTest(supported=supported):
                self.assertIn(supported, self.patch)

    def test_tail_patch_adds_only_the_approved_hooks_and_description(self) -> None:
        for token in (
            "C0ABIVI",
            "C0ABIVS",
            "C0ABIVE",
            "match_resource = C0SINGIN",
            "match_resource = C0SINGI2",
            "COPY_EXISTING ~C0ABETHL.SPL~",
            "SAY NAME1 ~Symphony of the Dark Children~",
            "SAY NAME2 ~Symphony of the Dark Children~",
            "SAY UNIDENTIFIED_DESC ~Symphony of the Dark Children",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.patch)

        self.assertNotIn("STRING_SET_EVALUATE", self.patch)

    def test_readme_requires_last_position_closed_game_and_confirmed_target(self) -> None:
        self.assertTrue(README.exists())
        for phrase in (
            "last component",
            "Baldur.exe",
            "InfinityLoader.exe",
            "confirm the exact game directory",
            "uninstall",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.readme)


if __name__ == "__main__":
    unittest.main()
