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
            "C0ABETS2.EFF",
            "READ_ASCII 0x30",
            "C0SINGIN",
            "C0SINGI2",
            "C0_VALIDATE_ABETTOR_FINITE_CONTROLLER",
            "FILE_EXISTS_IN_GAME",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.integration)

    def test_integration_adds_abettor_only_start_and_end_hooks(self) -> None:
        for token in ("C0ABIVI", "C0ABIVS", "C0ABIVE", "CLONE_EFFECT"):
            with self.subTest(token=token):
                self.assertIn(token, self.integration)

        self.assertRegex(
            self.integration,
            re.compile(r"match_resource\s*=\s*C0SINGIN.*resource\s*=\s*C0ABIVS", re.DOTALL),
        )
        self.assertRegex(
            self.integration,
            re.compile(r"match_resource\s*=\s*C0SINGI2.*resource\s*=\s*C0ABIVE", re.DOTALL),
        )
        self.assertIn("projectile = c0_abettor_party_projectile", self.integration)
        self.assertNotIn("projectile = c0bardso", self.integration)

    def test_hla_row_is_added_only_on_the_validated_path(self) -> None:
        self.assertIn("patch_add_hla", self.integration)
        self.assertIn("ability = ~AP_C0ABETHL~", self.integration)
        self.assertIn("prerequisite = ~AP_C0ABETT5~", self.integration)
        self.assertIn("skipping Symphony of the Dark Children", self.integration)


if __name__ == "__main__":
    unittest.main()
