"""Exercise the main installer with component #2004 before and after Bard options."""
from pathlib import Path
import re
import shutil
import struct
import subprocess
import unittest

from . import test_component_2004_producer as producer
from .test_tail_patch_integration import tlk_string


class BardDescriptionOrderTests(unittest.TestCase):
    def installed_description(self, first, second) -> str:
        with producer.disposable_game() as game:
            producer.Component2004ProducerTests().make_fixture(game, existing_projectile=520, snapshot=False)
            shutil.copytree(producer.MOD, game / "BardicWonders")
            override = game / "override"
            # WeiDU uses OH6000.ARE's presence in KEY to identify BG2:EE.
            marker = struct.pack("<8sHI", b"OH6000", 0x3F2, 0)
            (game / "chitin.key").write_bytes(b"KEY V1  " + struct.pack("<IIII", 0, 1, 24, 24) + marker)
            language = game / "lang/en_US"
            language.mkdir(parents=True)
            (game / "dialog.tlk").rename(language / "dialog.tlk")

            (override / "CLASTEXT.2DA").write_text(
                "2DA V1.0\n0\nCLASS MASK NAME DESC\nBARD 5 0 0 0\n", encoding="ascii",
            )
            (override / "ALIGNMNT.2DA").write_text(
                "2DA V1.0\n0\nLG LN LE NG NN NE CG CN CE\n"
                "MAGE 1 1 1 1 1 1 1 1 1\nBARD 0 1 0 1 1 1 0 1 0\n", encoding="ascii",
            )
            (override / "CLASS.IDS").write_text(
                "IDS V1.0\n1 MAGE\n2 FIGHTER\n3 CLERIC\n4 THIEF\n5 BARD\n6 PALADIN\n", encoding="ascii",
            )
            (override / "LUABBR.2DA").write_text(
                "2DA V1.0\n*\nABBREV\nMAGE MA0\nBARD BA0\n", encoding="ascii",
            )
            for batch in (first, second):
                proc = subprocess.run(
                    [str(producer.WEIDU), "--no-auto-tp2", "--noautoupdate", "--no-exit-pause",
                     "--game", str(game), "--use-lang", "en_US", "--language", "0",
                     "BardicWonders/Setup-BardicWonders.tp2", "--force-install-list", *map(str, batch)],
                    cwd=game, text=True, capture_output=True, timeout=60,
                )
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            log = (game / "WeiDU.log").read_text(encoding="latin-1")
            ids = tuple(map(int, re.findall(
                r"(?im)^~BARDICWONDERS/SETUP-BARDICWONDERS.TP2~ #\d+ #(\d+)", log,
            )))
            self.assertEqual(first + second, ids)
            row = next(line.split() for line in (override / "CLASTEXT.2DA").read_text().splitlines()
                       if line.split()[:1] == ["BARD"])
            return tlk_string(language / "dialog.tlk", int(row[4]))

    def test_bard_description_is_identical_in_both_install_orders(self):
        options = (2003, 2012, 2010)
        late = self.installed_description(options, (2004,))
        early = self.installed_description((2004,), options)
        self.assertEqual(
            """BARD: A wandering musician and storyteller, the Bard uses charm, lore, arcane magic and song to support the party.

Class features:
– May not wear armor heavier than chain mail. (Spells may be cast while wearing up to studded leather armor.)
– May equip shields up to medium size.
– Can become Proficient (one slot) in weapon and fighting-style proficiencies.
– Can Pick Pockets and gains an increased Lore score.
– Gains arcane spellcasting at 2nd level.
– Alignment restricted to any non-lawful. Bards are wanderers, guided by whim and intuition.
– Hit Die: d6.

Bard Song
The Bard can sing at will. A song lasts six rounds, plus one round for every five Bard levels. After activating a song, the Bard must wait one turn to sing again. The standard song protects allies from fear and morale failure, and grants +1 Luck. Luck rises to +2 at level 15 and +3 at level 20.""",
            late,
        )
        self.assertEqual(late, early)
