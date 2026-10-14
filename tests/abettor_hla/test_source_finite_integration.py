from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
BARDSOUND_TWEAKS = ROOT / "BardicWonders" / "lib" / "bardsongtweaks.tpa"
FINITE_INTEGRATION = ROOT / "BardicWonders" / "lib" / "abettor_hla_finite.tpa"


class SourceFiniteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tweaks = BARDSOUND_TWEAKS.read_text(encoding="utf-8")
        cls.integration = (
            FINITE_INTEGRATION.read_text(encoding="utf-8")
            if FINITE_INTEGRATION.exists()
            else ""
        )

    def test_component_2004_includes_the_abettor_integration_after_transform(self) -> None:
        transform_position = self.tweaks.find(
            "COPY ~%MOD_FOLDER%/bardsong/c0bardso.eff~"
        )
        include_position = self.tweaks.find(
            "INCLUDE ~%MOD_FOLDER%/lib/abettor_hla_finite.tpa~"
        )
        self.assertGreater(transform_position, -1)
        self.assertGreater(include_position, transform_position)

    def test_integration_validates_the_finite_controller_and_dynamic_payload(self) -> None:
        self.assertTrue(FINITE_INTEGRATION.exists())
        for token in (
            "C0_RESOLVE_ABETTOR_PAYLOAD",
            "READ_ASCII 0x30",
            "C0SINGIN",
            "C0SINGI2",
            "C0_VALIDATE_ABETTOR_FINITE_CONTROLLER",
            "expected_controller_projectile",
            "FILE_EXISTS_IN_GAME",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.integration)
        self.assertNotIn("FILE_EXISTS_IN_GAME ~C0ABETS2.EFF~", self.integration)

    def test_integration_adds_abettor_only_start_and_end_hooks(self) -> None:
        for token in ("C0ABIVI", "C0ABIVS", "CLONE_EFFECT", "LPF C0_ADD_ABETTOR_FINALE"):
            with self.subTest(token=token):
                self.assertIn(token, self.integration)

        self.assertRegex(
            self.integration,
            re.compile(r"match_resource\s*=\s*C0SINGIN.*resource\s*=\s*C0ABIVS", re.DOTALL),
        )
        finale = re.search(
            r"DEFINE_PATCH_FUNCTION C0_ADD_ABETTOR_FINALE\b.*?\nEND\n",
            self.integration.replace("\r\n", "\n"),
            re.DOTALL,
        )
        self.assertIsNotNone(finale)
        self.assertRegex(
            finale[0],
            re.compile(r"opcode\s*=\s*326.*timing\s*=\s*4.*resource\s*=\s*C0ABIVI", re.DOTALL),
        )
        # The finale is not cloned from the disabled-singer check.
        self.assertNotRegex(self.integration, r"match_resource\s*=\s*C0SINGI2")
        self.assertNotIn("C0ABIVE.EFF", self.integration)
        self.assertIn("projectile = c0_abettor_party_projectile", self.integration)
        self.assertIn("c0_abettor_controller_projectile = c0bardso", self.integration)

    def test_hla_row_is_added_only_on_the_validated_path(self) -> None:
        self.assertIn("patch_add_hla", self.integration)
        self.assertIn("ability = ~AP_C0ABETHL~", self.integration)
        self.assertIn("prerequisite = ~AP_C0ABETT5~", self.integration)
        self.assertIn("skipping Symphony of the Dark Children", self.integration)


if __name__ == "__main__":
    unittest.main()
