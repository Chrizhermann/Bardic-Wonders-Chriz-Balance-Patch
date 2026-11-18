from pathlib import Path
import unittest


LIBRARY = Path(__file__).resolve().parents[2] / "BardicWonders/lib"


class SourceFiniteIntegrationTests(unittest.TestCase):
    def test_component_2004_writes_the_controller_before_adding_the_finale(self):
        component = (LIBRARY / "bardsongtweaks.tpa").read_text()
        self.assertLess(
            component.index("RET symphony_payload = song_name"),
            component.index("INCLUDE ~%MOD_FOLDER%/lib/abettor_hla_finite.tpa~"),
        )
