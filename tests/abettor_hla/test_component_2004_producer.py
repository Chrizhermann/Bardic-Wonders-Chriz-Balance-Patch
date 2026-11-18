"""Run the real component-2004 producer before validating its finite controller.

All inputs come from the repository; WeiDU runs only in disposable directories.
In particular, these tests never manufacture a C0ABETS2 controller or its EFF.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from .ie_resources import parse_spl, read_eff_resource
from .test_tail_patch_integration import tlk_string, tlk_with_original_description
from .finite_fixtures import HLA_TABLE, is_finale, song_ticks


ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "BardicWonders"
WEIDU = ROOT / "Setup-BardicWonders.exe"


@contextmanager
def disposable_game():
    root = Path(tempfile.mkdtemp(prefix="sol62-bardic-unit-"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


def song_with_self_targeted_movement(source: bytes) -> bytes:
    song = bytearray(source)
    ability = struct.unpack_from("<I", song, 0x64)[0]
    effects = struct.unpack_from("<I", song, 0x6A)[0]
    count, first = struct.unpack_from("<HH", song, ability + 0x1E)
    for index in reversed(range(first, first + count)):
        offset = effects + index * 48
        opcode, = struct.unpack_from("<H", song, offset)
        if opcode != 142:
            struct.pack_into("<HBB", song, offset, 126, 1, 0)
            return bytes(song)
    raise AssertionError("Fixture needs a non-icon ability effect")


def song_with_wide_icon_parameter(source: bytes) -> bytes:
    song = bytearray(source)
    effects = struct.unpack_from("<I", song, 0x6A)[0]
    for offset in range(effects, len(song), 48):
        if struct.unpack_from("<H", song, offset)[0] == 142 and struct.unpack_from("<H", song, offset + 8)[0] == 40:
            struct.pack_into("<I", song, offset + 8, 0x00010028)
            return bytes(song)
    raise AssertionError("Fixture needs an opcode-142 effect for icon 40")


def effect_assigned_song() -> tuple[bytes, bytes]:
    spell = bytearray((MOD / "abettor/c0abethl.spl").read_bytes())
    effects = struct.unpack_from("<I", spell, 0x6A)[0]
    for offset in range(effects, len(spell), 48):
        if struct.unpack_from("<H", spell, offset)[0] == 251:
            struct.pack_into("<H", spell, offset, 177)
            struct.pack_into("<II", spell, offset + 4, 5, 5)
            spell[offset + 0x14:offset + 0x1C] = b"XQCHOOSE"
    # Use a valid EFF V2 envelope and an opcode-251 song selection.
    choose = bytearray((MOD / "bardsong/c0bardso.eff").read_bytes())
    struct.pack_into("<IIIII", choose, 0x10, 251, 2, 0, 0, 0)
    choose[0x30:0x38] = b"XQSONG\0\0"
    return bytes(spell), bytes(choose)


def malformed_spell_inputs(source: bytes) -> tuple[dict[str, bytes], dict[str, bytes]]:
    def replace(offset: int, layout: str, value: int) -> bytes:
        damaged = bytearray(source)
        struct.pack_into(layout, damaged, offset, value)
        return bytes(damaged)

    ability, = struct.unpack_from("<I", source, 0x64)
    return (
        {
            "XQZERO.SPL": b"",
            "XQTRUNC.SPL": b"SPL V1  ",
            "XQSHORT.SPL": source[:0x71],
            "XQFORMAT.SPL": b"SPL V2  " + source[8:],
        },
        {
            "XQABIL.SPL": replace(0x64, "<I", len(source)),
            "XQABFX.SPL": replace(ability + 0x20, "<H", 0xFFFF),
            "XQGLFX.SPL": replace(0x70, "<H", 0xFFFF),
            "XQOVRFL.SPL": replace(0x64, "<I", 0x7FFFFFFF),
            "XQNEG.SPL": replace(0x6A, "<i", -1),
        },
    )


def song_loader_with_layout(ability_offset: int, effect_offset: int, effect_count: int = 0,
                            first_effect: int = 0) -> bytes:
    source = (MOD / "bardsong/c0bardx.spl").read_bytes()
    original = struct.unpack_from("<I", source, 0x64)[0]
    loader = bytearray(source[:0x72])
    loader.extend(bytes(ability_offset - len(loader)))
    loader.extend(source[original:original + 0x28])
    if effect_count:
        loader.extend(bytes(effect_count * 0x30))
    struct.pack_into("<IHIHH", loader, 0x64, ability_offset, 1, effect_offset, 0, 0)
    struct.pack_into("<HH", loader, ability_offset + 0x1E, effect_count, first_effect)
    return bytes(loader)


def empty_song_loader_with_casting_effect() -> bytes:
    loader = bytearray(song_loader_with_layout(0x72, 0x9A, effect_count=1, first_effect=0xFFFF))
    struct.pack_into("<H", loader, 0x70, 1)
    struct.pack_into("<H", loader, 0x72 + 0x1E, 0)
    struct.pack_into("<H", loader, 0x9A, 139)
    return bytes(loader)


def song_loader_with_shared_effect_table(empty_index: int, *, multiple: bool = False,
                                         overlap: str = "", casting_last: bool = False) -> bytes:
    source = empty_song_loader_with_casting_effect()
    ability_count = 2 if multiple else 1
    effect_offset = 0x72 + 0x28 * ability_count
    casting_first = 2 if casting_last else 0
    loader = bytearray(source[:0x72] + source[0x72:0x9A] * ability_count)
    struct.pack_into("<IHIHH", loader, 0x64, 0x72, ability_count, effect_offset, casting_first, 1)
    casting = source[0x9A:]
    if multiple:
        first = 0 if casting_last or overlap == "casting" else 1
        struct.pack_into("<HH", loader, 0x72 + 0x1E, 2, first)
        final_count = 1 if overlap == "abilities" else 0
        struct.pack_into("<HH", loader, 0x9A + 0x1E, final_count, empty_index)
        ability_effects = (struct.pack("<H", 101) + bytes(0x2E)) + (struct.pack("<H", 142) + bytes(0x2E))
        loader.extend(ability_effects + casting if casting_last else casting + ability_effects)
    else:
        struct.pack_into("<H", loader, 0x72 + 0x20, empty_index)
        loader.extend(casting)
    return bytes(loader)


def duplicate_first_ability(spell: bytearray) -> None:
    headers, count, effects = struct.unpack_from("<IHI", spell, 0x64)
    added_header = spell[headers:headers + 0x28]
    effect_count, first = struct.unpack_from("<HH", added_header, 0x1E)
    records = spell[effects + first * 0x30:effects + (first + effect_count) * 0x30]
    # Keep identical effect bytes in disjoint slots.
    struct.pack_into("<H", added_header, 0x20, (len(spell) - effects) // 0x30)
    spell[effects:effects] = added_header
    struct.pack_into("<HI", spell, 0x68, count + 1, effects + 0x28)
    spell.extend(records)


def external_assignment_with_late_casting(*, multiple: bool = False, capacity: int = 0) -> bytes:
    source = (MOD / "abettor/c0abethl.spl").read_bytes()
    header, _, effects = struct.unpack_from("<IHI", source, 0x64)
    ability = source[header:header + 0x28]
    record = source[effects:effects + 0x30].replace(b"C0ABETS2", b"XQSONG\0\0")
    assert struct.unpack_from("<H", record)[0] == 251
    casting = struct.pack("<HBB", 139, 1, 9) + bytes(range(4, 0x30))
    unrelated = struct.pack("<HBB", 101, 2, 5) + bytes(range(4, 0x30))
    count = 3 if multiple else 1
    offset = 0x72 + count * 0x28
    caller = bytearray(source[:0x72] + ability * count)
    if capacity:
        struct.pack_into("<IHIHH", caller, 0x64, 0x72, 1, offset, 0, 0)
        struct.pack_into("<HH", caller, 0x72 + 0x1E, capacity, 0)
        caller.extend(record + bytes((capacity - 1) * 0x30))
    elif multiple:
        struct.pack_into("<IHIHH", caller, 0x64, 0x72, count, offset, 2, 1)
        struct.pack_into("<HH", caller, 0x72 + 0x1E, 1, 1)
        struct.pack_into("<HH", caller, 0x9A + 0x1E, 1, 0)
        struct.pack_into("<HH", caller, 0xC2 + 0x1E, 0, 0xFFFF)
        caller.extend(unrelated + record + casting)
    else:
        struct.pack_into("<IHIHH", caller, 0x64, 0x72, 1, offset, 1, 1)
        struct.pack_into("<HH", caller, 0x72 + 0x1E, 1, 0)
        caller.extend(record + casting)
    return bytes(caller)


def assignment_parity_fixtures() -> dict[str, bytes]:
    canonical = (MOD / "abettor/c0abethl.spl").read_bytes()
    header, _, table = struct.unpack_from("<IHI", canonical, 0x64)
    match = canonical[table:table + 48].replace(b"C0ABETS2", b"XQSONG\0\0")
    other = match.replace(b"XQSONG", b"XQELSE")
    neutral = struct.pack("<H", 101) + bytes(46)
    casting = bytearray(struct.pack("<H", 139) + bytes(range(2, 48)))
    casting[4:15] = b"%song_name%"
    casting[29:44] = b"%bardsong_name%"
    casting[44] = 0

    def packed(abilities, globals_=(), trailer=b""):
        data = bytearray(canonical[:0x72] + canonical[header:header + 40] * len(abilities))
        struct.pack_into("<IHIHH", data, 0x64, 0x72, len(abilities), len(data), 0, len(globals_))
        data.extend(b"".join(globals_))
        first = len(globals_)
        for index, records in enumerate(abilities):
            struct.pack_into("<HH", data, 0x72 + index * 40 + 0x1E, len(records), first)
            data.extend(b"".join(records))
            first += len(records)
        return bytes(data) + trailer

    return {
        "XQMULTI": packed(((other, match), (match, neutral, other), (match,))),
        "XQGL": packed(((other, match, neutral), (match,)), (match,)),
        "XQCROSS": packed(((match,), (other, match))),
        "XQOPAQUE": packed(((match, neutral),), (bytes(casting),), b"TRAILER\0%SOURCE_RES%"),
    }


def retarget_controller_fixture(source: bytes, replacement: bytes) -> bytes:
    data = bytearray(source)
    effect_table, = struct.unpack_from("<I", data, 0x6A)
    for offset in range(effect_table, len(data) - 47, 48):
        if data[offset + 0x14:offset + 0x1C] == b"C0BARDSO":
            data[offset + 0x14:offset + 0x1C] = replacement
    return bytes(data)


def add_controller_cue(source: bytes, name: bytes) -> tuple[bytes, tuple[bytes, ...]]:
    data = bytearray(source)
    abilities, count, table = struct.unpack_from("<IHI", data, 0x64)
    field = abilities + 40 * (count - 1) + 0x1E
    length, first = struct.unpack_from("<HH", data, field)
    end = table + 48 * (first + length)
    assert end == len(data)
    cue_records = []
    for opcode in (177, 272):
        donor = next(bytes(data[offset:offset + 48]) for offset in range(table + 48 * first, end, 48)
                     if struct.unpack_from("<H", data, offset)[0] == opcode)
        cue = donor[:0x14] + name + donor[0x1C:]
        cue_records.append(cue)
        data.extend(cue)
    struct.pack_into("<H", data, field, length + len(cue_records))
    return bytes(data), tuple(cue_records)


class Component2004ProducerTests(unittest.TestCase):
    def make_fixture(self, root: Path, *, existing_projectile: int, reserve_payload_name: bool = False, snapshot: bool = True) -> None:
        override = root / "override"
        override.mkdir()
        library = root / "testmod" / "lib"
        library.mkdir(parents=True)
        shutil.copytree(MOD / "bardsong", root / "testmod" / "bardsong")
        for name in ("bardsongtweaks.tpa", "functions.tph", "hla_actions.tpa", "song_projectile.tpa",
                     "bardsong_registration.tpa", "bardsong_description.tpa", "abettor_symphony.tpa"):
            shutil.copy2(MOD / "lib" / name, library / name)
        shutil.copy2(MOD / "lib" / "abettor_hla_finite.tpa", library / "finite_actual.tpa")
        # Capture what the unchanged producer actually emits immediately before
        # its existing finite-integration INCLUDE. No producer code is replaced.
        (library / "abettor_hla_finite.tpa").write_text(
            ("COPY ~override~ ~producer-snapshot~\n" if snapshot else "")
            + "INCLUDE ~testmod/lib/finite_actual.tpa~\n",
            encoding="ascii",
        )
        canonical = root / "testmod" / "abettor"
        canonical.mkdir()
        shutil.copy2(MOD / "abettor/c0abethl.spl", canonical)
        for name in ("c0abets2.spl", "c0abethl.spl"):
            shutil.copy2(MOD / "abettor" / name, override / name)
        (override / "LUC0ABET.2DA").write_text(HLA_TABLE, encoding="ascii")
        (override / "KITLIST.2DA").write_text(
            "2DA V1.0\n*\n LABEL NAME LOWER MIXED HELP CLAB PROF UNUSABLE CLASS KITIDS\n"
            "0 MAGE 0 0 0 0 CLABMA01 0 0 1 0\n",
            encoding="ascii",
        )
        (override / "PROJECTL.IDS").write_text(f"IDS V1.0\n157 INAREAPA\n{existing_projectile} EXISTING\n", encoding="ascii")
        (override / "MISSILE.IDS").write_text("IDS V1.0\n0 NONE\n", encoding="ascii")
        (override / "ENGINEST.2DA").write_text(
            "2DA V1.0\n0\n STRREF\nSTRREF_FEEDBACK_BATTLESONGBEGIN 0\nSTRREF_FEEDBACK_BATTLESONGEND 0\n",
            encoding="ascii",
        )
        shared_projectile = bytearray((MOD / "bardsong/c0bardso.PRO").read_bytes())
        shared_projectile[0x0C] &= ~0x40
        shared_projectile[0x21A] = 0x4F
        for name in ("INAREANP", "INAREA", "INAREASM", "BIGNAREA", "INAREAPA"):
            (override / f"{name}.PRO").write_bytes(shared_projectile)
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
            # As in the main TP2, functions.tph replaces WeiDU's ADD_SPELL_EFFECT.
            "ALWAYS\n INCLUDE ~testmod/lib/functions.tph~\n INCLUDE ~testmod/lib/hla_actions.tpa~\nEND\n"
            "LANGUAGE ~English~ ~english~\n"
            "BEGIN ~Bard Song Mechanics Tweak producer regression~ DESIGNATED 2004\n"
            + allocator_seed +
            "INCLUDE ~testmod/lib/bardsongtweaks.tpa~\n",
            encoding="ascii",
        )

    def test_a_preexisting_controller_keeps_its_id_and_is_restored_on_uninstall(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=558, snapshot=False)
            override = root / "override"
            (override / "GET_UNIQUE_FILENAME_SPL.IDS").write_text("IDS V1.0\n", encoding="ascii")
            ids = resource(override, "PROJECTL.IDS")
            with ids.open("a", encoding="ascii") as out:
                out.write("518 C0BARDSO\n")
            old = bytearray((MOD / "bardsong/c0bardso.PRO").read_bytes())
            old[0x0C] &= ~0x40
            old[0x2C] |= 0x40
            old[0x206] ^= 0x3F
            (override / "C0BARDSO.PRO").write_bytes(old)
            before = {p.name.upper(): p.read_bytes() for p in override.iterdir()}
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual((MOD / "bardsong/c0bardso.PRO").read_bytes(),
                             resource(override, "C0BARDSO.PRO").read_bytes())
            self.assertEqual(519, parse_spl(resource(override, "C0ABETS2.SPL")).abilities[0].projectile)
            result = subprocess.run(
                [str(WEIDU), "testmod/setup-test.tp2", "--no-auto-tp2", "--game", str(root),
                 "--no-exit-pause", "--language", "0", "--force-uninstall-list", "2004"],
                cwd=root, text=True, capture_output=True, check=False, timeout=60,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            after = {p.name.upper(): p.read_bytes() for p in override.iterdir()}
            self.assertEqual(set(before), set(after), result.stdout + result.stderr)
            # WeiDU keeps the reserved payload name across uninstall.
            allocator = "GET_UNIQUE_FILENAME_SPL.IDS"
            self.assertIn(b"C0ABETS2", after.pop(allocator))
            del before[allocator]
            for name, data in before.items():
                self.assertEqual(data, after[name], name)

    def test_missing_symphony_hla_is_restored_and_linked(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            resource(override, "C0ABETHL.SPL").unlink()

            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn("Symphony of the Dark Children enabled", result.stdout)
            hla_path = resource(override, "C0ABETHL.SPL")
            name = struct.unpack_from("<I", hla_path.read_bytes(), 0x08)[0]
            self.assertEqual("Symphony of the Dark Children", tlk_string(root / "dialog.tlk", name))
            hla = parse_spl(hla_path)
            controller = parse_spl(resource(override, "C0ABETS2.SPL"))
            pulse = next(e.resource for e in controller.abilities[0].effects if e.opcode == 272)
            self.assertEqual(1, len(hla.find_effects(opcode=251, resource="C0ABETS2")))
            self.assertEqual(1, len(hla.find_effects(opcode=326, resource="C0BARDX")))
            self.assertEqual(1, len(hla.find_effects(opcode=309, resource=pulse)))
            hla_table = resource(override, "LUC0ABET.2DA").read_text().splitlines()
            rows = [line.split() for line in hla_table if "AP_C0ABETHL" in line.split()]
            self.assertEqual(1, len(rows))
            self.assertIn("AP_C0ABETT5", rows[0])

    def test_external_assignment_wraps_song_with_private_projectiles(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            with resource(override, "PROJECTL.IDS").open("a", encoding="ascii") as ids:
                ids.write("480 INAREAPA\n481 INAREANP\n")
                # Reserve the first private name in IDS alone to exercise allocation.
                ids.write("482 C0P0\n")
            enemy = resource(override, "INAREANP.PRO")
            distinct_profile = bytearray(enemy.read_bytes())
            struct.pack_into("<HH", distinct_profile, 0x204, 320, 320)
            enemy.write_bytes(distinct_profile)
            assignment = bytearray((MOD / "abettor/c0abethl.spl").read_bytes())
            assignment = assignment.replace(b"C0ABETS2", b"xqsong\0\0")
            (override / "XQASSIGN.SPL").write_bytes(assignment)
            (override / "XQSONG.SPL").write_bytes((MOD / "abettor/c0abets2.spl").read_bytes())
            original = resource(override, "XQSONG.SPL")
            song = bytearray(original.read_bytes())
            headers, count = struct.unpack_from("<IH", song, 0x64)
            # The two projectile variants must keep their original profiles.
            self.assertGreater(count, 0)
            duplicate_first_ability(song)
            for i in range(count + 1):
                struct.pack_into("<H", song, headers + i * 40 + 0x26, 481 if i == 0 else 482)
            original.write_bytes(song)
            combat = {path.name.upper(): path.read_bytes() for path in override.glob("*.PRO")}
            before_effects = effect_records(original)

            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            wrapper = parse_spl(original)
            pulse = next(e.resource for e in wrapper.abilities[0].effects if e.opcode == 272)
            payload = resource(override, pulse + ".SPL")
            assign = parse_spl(resource(override, "XQASSIGN.SPL"))
            self.assertEqual(1, len(assign.find_effects(opcode=251, resource="XQSONG")))
            # The legacy in-place traversal encounters the moved opcode 251
            # again after cloning. WeiDU emits three pairs for this fixture.
            self.assertEqual(3, len(assign.find_effects(opcode=326, resource="C0BARDX")))
            self.assertEqual(3, len(assign.find_effects(opcode=309, resource=pulse)))
            self.assertEqual(before_effects, effect_records(payload))
            self.assertEqual(pulse, read_eff_resource(resource(override, pulse + ".EFF")))
            projectiles = {}
            for line in resource(override, "PROJECTL.IDS").read_text().splitlines():
                columns = line.split()
                if len(columns) >= 2 and columns[0].isdigit():
                    projectiles[int(columns[0]) + 1] = columns[1].upper()
            self.assertTrue(resource(override, projectiles[wrapper.abilities[0].projectile] + ".PRO").read_bytes()[0x0C] & 0x40)
            for ability, donor in zip(parse_spl(payload).abilities, ["INAREAPA"] + ["INAREANP"] * count, strict=True):
                private = projectiles[ability.projectile]
                self.assertNotIn(private, {"INAREAPA", "INAREANP", "C0P0"})
                expected = bytearray(combat[donor + ".PRO"])
                expected[0x0C] |= 0x40
                self.assertEqual(expected, resource(override, private + ".PRO").read_bytes())
            for file, data in combat.items():
                self.assertEqual(data, resource(override, file).read_bytes())
            undo = subprocess.run(
                [str(WEIDU), "testmod/setup-test.tp2", "--no-auto-tp2", "--game", str(root),
                 "--no-exit-pause", "--language", "0", "--force-uninstall-list", "2004"],
                cwd=root, text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(0, undo.returncode, undo.stdout + undo.stderr)
            self.assertEqual(song, original.read_bytes())
            self.assertEqual(assignment, resource(override, "XQASSIGN.SPL").read_bytes())
            self.assertFalse(any(path.name.upper() in {"C0P1.PRO", "C0P2.PRO"} for path in override.iterdir()))

    def test_external_song_discovery_reads_the_low_word_of_the_icon(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song = song_with_wide_icon_parameter((MOD / "abettor/c0abets2.spl").read_bytes())
            source = override / "XQSONG.SPL"
            source.write_bytes(song)
            assignment = override / "XQASSIGN.SPL"
            assignment.write_bytes((MOD / "abettor/c0abethl.spl").read_bytes().replace(b"C0ABETS2", b"XQSONG\0\0"))

            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            pulse = next(e.resource for e in parse_spl(source).abilities[0].effects if e.opcode == 272)
            assigned = parse_spl(assignment)
            self.assertEqual(1, len(assigned.find_effects(opcode=251, resource="XQSONG")))
            self.assertEqual(3, len(assigned.find_effects(opcode=326, resource="C0BARDX")))
            self.assertEqual(3, len(assigned.find_effects(opcode=309, resource=pulse)))
            payload = parse_spl(resource(override, pulse + ".SPL"))
            self.assertEqual(1, len(payload.find_effects(opcode=142, parameter2=0x00010028)))

    def assert_damaged_inputs_are_isolated(self, damaged: dict[str, bytes], *, bad_donor: bool = False) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song = bytearray((MOD / "abettor/c0abets2.spl").read_bytes())
            ability, = struct.unpack_from("<I", song, 0x64)
            struct.pack_into("<H", song, ability + 0x26, 481)
            (override / "XQSONG.SPL").write_bytes(song)
            assignment = (MOD / "abettor/c0abethl.spl").read_bytes().replace(b"C0ABETS2", b"XQSONG\0\0")
            (override / "XQASSIGN.SPL").write_bytes(assignment)
            ids_file = resource(override, "PROJECTL.IDS")
            with ids_file.open("a", encoding="ascii") as ids:
                ids.write("480 INAREAPA\n481 XQBADPRO\n")
            if bad_donor:
                struct.pack_into("<H", song, ability + 0x26, 482)
                for name in ("XQBAD1.SPL", "XQBAD2.SPL"):
                    (override / name).write_bytes(song)
            for name, data in damaged.items():
                (override / name).write_bytes(data)

            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            messages = [line.upper() for line in result.stdout.splitlines() if "skipping damaged" in line.lower()]
            for name, data in damaged.items():
                self.assertEqual(1, sum(name in line for line in messages), messages)
                self.assertEqual(data, resource(override, name).read_bytes())
            wrapper = parse_spl(resource(override, "XQSONG.SPL"))
            pulse = next(e.resource for e in wrapper.abilities[0].effects if e.opcode == 272)
            assigned = parse_spl(resource(override, "XQASSIGN.SPL"))
            self.assertEqual(3, len(assigned.find_effects(opcode=309, resource=pulse)))
            ids = {int(index) + 1: name.upper()
                   for index, name, *_ in (line.split() for line in ids_file.read_text().splitlines())
                   if index.isdigit()}
            payload = parse_spl(resource(override, pulse + ".SPL"))
            projectile = ids[payload.abilities[0].projectile]
            self.assertNotEqual("INAREAPA", projectile)
            self.assertTrue(resource(override, projectile + ".PRO").read_bytes()[0x0C] & 0x40)
            if bad_donor:
                for name in ("XQBAD1.SPL", "XQBAD2.SPL"):
                    unchanged = resource(override, name)
                    self.assertEqual(bytes(song), unchanged.read_bytes())
                    self.assertEqual(482, parse_spl(unchanged).abilities[0].projectile)
                    self.assertFalse(parse_spl(unchanged).find_effects(opcode=272))
                self.assertEqual(1, sum(name.startswith("C0P") for name in ids.values()))

    def test_short_and_wrong_signature_spells_are_skipped_once(self) -> None:
        headers, _ = malformed_spell_inputs((MOD / "abettor/c0abets2.spl").read_bytes())
        headers["SPCL542A.SPL"] = b"SPL V1  "
        self.assert_damaged_inputs_are_isolated(headers)

    def test_out_of_bounds_spell_tables_are_skipped_once(self) -> None:
        _, tables = malformed_spell_inputs((MOD / "abettor/c0abets2.spl").read_bytes())
        self.assert_damaged_inputs_are_isolated(tables)

    def test_truncated_projectile_donor_is_skipped_once_across_songs(self) -> None:
        self.assert_damaged_inputs_are_isolated({"XQBADPRO.PRO": b"PRO V1.0"}, bad_donor=True)

    def test_truncated_symphony_eff_skips_finale_without_rolling_back_song_wrapping(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            (root / "testmod/bardsong/c0singin.eff").write_bytes(b"EFF V2.0")
            override = root / "override"
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.upper().count("SKIPPING DAMAGED C0SINGIN.EFF"))
            self.assertFalse(any(path.name.upper() in {"C0SINGIN.EFF", "C0ABIVS.EFF", "C0ABIVI.SPL"}
                                 for path in override.iterdir()))
            symphony = parse_spl(resource(override, "C0ABETS2.SPL"))
            pulse = next(e.resource for e in symphony.abilities[0].effects if e.opcode == 272)
            self.assertEqual(pulse, read_eff_resource(resource(override, pulse + ".EFF")))

    def test_external_song_is_discovered_when_assigned_only_through_an_eff(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song = bytearray((MOD / "abettor/c0abets2.spl").read_bytes())
            header = struct.unpack_from("<I", song, 0x64)[0]
            struct.pack_into("<H", song, header + 0x26, 481)
            song_file = override / "XQSONG.SPL"
            song_file.write_bytes(song)
            (override / "XQNOLINK.SPL").write_bytes(song)
            with resource(override, "PROJECTL.IDS").open("a", encoding="ascii") as ids:
                ids.write("480 INAREAPA\n")
            shared = (override / "INAREAPA.PRO").read_bytes()
            spell, effect = effect_assigned_song()
            assignment = override / "XQASSIGN.SPL"
            choose = override / "XQCHOOSE.EFF"
            assignment.write_bytes(spell)
            choose.write_bytes(effect)

            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(spell, assignment.read_bytes())
            self.assertEqual(effect, choose.read_bytes())
            self.assertEqual(shared, (override / "INAREAPA.PRO").read_bytes())
            ids = {int(index) + 1: name.upper()
                   for index, name, *_ in (line.split() for line in resource(override, "PROJECTL.IDS").read_text().splitlines())
                   if index.isdigit()}
            expected = bytearray(shared)
            expected[0x0C] |= 0x40
            for source in (song_file, override / "XQNOLINK.SPL"):
                wrapper = parse_spl(source)
                self.assertEqual({"C0BARDSO"}, {ids[a.projectile] for a in wrapper.abilities})
                pulse = next(e.resource for e in wrapper.abilities[0].effects if e.opcode == 272)
                self.assertEqual(pulse, read_eff_resource(resource(override, pulse + ".EFF")))
                payload = parse_spl(resource(override, pulse + ".SPL"))
                for ability in payload.abilities:
                    private = ids[ability.projectile]
                    self.assertNotEqual("INAREAPA", private)
                    self.assertEqual(expected, resource(override, private + ".PRO").read_bytes())

    def test_song_loader_rejects_bad_empty_pointers_and_overlapping_tables(self) -> None:
        for name, data in (
            ("empty invalid pointer", song_loader_with_layout(0x72, 0xFFFFFFFF)),
            ("effect pointer in header", song_loader_with_layout(0x80, 0x70)),
            ("empty effect table before ability", song_loader_with_layout(0x80, 0x72)),
            ("overlapping tables", song_loader_with_layout(0x72, 0x72, 1)),
        ):
            with self.subTest(name=name), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                packaged = root / "testmod/bardsong/c0bardx.spl"
                override = root / "override"
                prior = song_loader_with_layout(0x72, 0xFFFFFFFF)
                (override / "C0BARDX.SPL").write_bytes(prior)
                packaged.write_bytes(data)
                song = resource(override, "C0ABETS2.SPL")
                original_song = song.read_bytes()
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(1, result.stdout.upper().count("SKIPPING DAMAGED C0BARDX.SPL"))
                self.assertEqual(data, packaged.read_bytes())
                self.assertEqual(prior, resource(override, "C0BARDX.SPL").read_bytes())
                self.assertEqual(original_song, song.read_bytes())
                self.assertFalse(any(path.name.upper() == "C0ABIVS.EFF" for path in override.iterdir()))

    def test_song_loader_inserts_into_an_empty_effect_table_at_eof(self) -> None:
        for label, data in (
            ("empty at EOF", song_loader_with_layout(0x72, 0x9A)),
            ("unused index", song_loader_with_layout(0x72, 0x9A, first_effect=0xFFFF)),
            ("preserve casting effect", empty_song_loader_with_casting_effect()),
        ):
            with self.subTest(label=label), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                packaged = root / "testmod/bardsong/c0bardx.spl"
                packaged.write_bytes(data)
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertNotIn("SKIPPING DAMAGED C0BARDX.SPL", result.stdout.upper())
                override = root / "override"
                song = parse_spl(resource(override, "C0ABETS2.SPL"))
                pulse = next(e.resource for e in song.abilities[0].effects if e.opcode == 272)
                installed = resource(override, "C0BARDX.SPL")
                self.assertTrue(parse_spl(installed).find_effects(opcode=309, resource=pulse))
                self.assertEqual(effect_records(packaged)[0], effect_records(installed)[0])

    def seed_bard_clabs(self, override: Path, grant: str = "****") -> None:
        resource(override, "KITLIST.2DA").write_text(
            "2DA V1.0\n*\n LABEL NAME LOWER MIXED HELP CLAB PROF UNUSABLE CLASS KITIDS\n"
            "0 MAGE 0 0 0 CLABMA01 0 0 1 0\n1 FORKBARD 0 0 0 XQCLAB 0 0 5 0\n",
            encoding="ascii",
        )
        for name in ("CLABBA01", "XQCLAB"):
            (override / f"{name}.2DA").write_text(
                f"2DA V1.0\n****\n  1 2\nABILITY1 {grant} AP_KEEP\n", encoding="ascii",
            )

    def test_damaged_or_missing_package_without_usable_loader_clears_bard_grants(self) -> None:
        for mode in ("damaged", "missing", "damaged installed"):
            with self.subTest(mode=mode), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                packaged = root / "testmod/bardsong/c0bardx.spl"
                override = root / "override"
                self.seed_bard_clabs(override, "AP_C0BARDX" if mode != "damaged" else "****")
                invalid = song_loader_with_layout(0x72, 0xFFFFFFFF)
                if mode == "missing":
                    packaged.unlink()
                else:
                    packaged.write_bytes(invalid)
                if mode == "damaged installed":
                    (override / "C0BARDX.SPL").write_bytes(invalid)
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                message = "MISSING PACKAGED" if mode == "missing" else "SKIPPING DAMAGED"
                self.assertEqual(1, result.stdout.upper().count(f"{message} C0BARDX.SPL"))
                for name in ("CLABBA01.2DA", "XQCLAB.2DA"):
                    fields = resource(override, name).read_text().split()
                    self.assertNotIn("AP_C0BARDX", fields)
                    self.assertIn("AP_KEEP", fields)

    def test_installed_loader_fallback_grants_and_wraps_valid_external_song(self) -> None:
        for mode in ("damaged", "missing"):
            with self.subTest(mode=mode), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                packaged = root / "testmod/bardsong/c0bardx.spl"
                override = root / "override"
                self.seed_bard_clabs(override, "AP_C0BARDX")
                loader = override / "C0BARDX.SPL"
                loader.write_bytes(song_loader_with_shared_effect_table(0))
                original_casting, original_abilities = effect_records(loader)
                if mode == "damaged":
                    packaged.write_bytes(song_loader_with_layout(0x72, 0xFFFFFFFF))
                else:
                    packaged.unlink()
                song = bytearray((MOD / "abettor/c0abets2.spl").read_bytes())
                ability, = struct.unpack_from("<I", song, 0x64)
                struct.pack_into("<H", song, ability + 0x26, 481)
                (override / "XQSONG.SPL").write_bytes(song)
                ids = resource(override, "PROJECTL.IDS")
                with ids.open("a", encoding="ascii") as out:
                    out.write("480 INAREAPA\n")
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                message = "MISSING PACKAGED" if mode == "missing" else "SKIPPING DAMAGED"
                self.assertEqual(1, result.stdout.upper().count(f"{message} C0BARDX.SPL"))
                for name in ("CLABBA01.2DA", "XQCLAB.2DA"):
                    fields = resource(override, name).read_text().split()
                    self.assertEqual(1, fields.count("AP_C0BARDX"))
                    self.assertIn("AP_KEEP", fields)
                wrapper = parse_spl(resource(override, "XQSONG.SPL"))
                pulse = next(e.resource for e in wrapper.abilities[0].effects if e.opcode == 272)
                self.assertEqual(original_casting, effect_records(loader)[0])
                self.assertEqual(original_abilities[0], effect_records(loader)[1][0][:len(original_abilities[0])])
                self.assertTrue(parse_spl(loader).find_effects(opcode=309, resource=pulse))
                projectile = parse_spl(resource(override, pulse + ".SPL")).abilities[0].projectile
                private = next(parts[1] for parts in map(str.split, ids.read_text().splitlines())
                               if len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) + 1 == projectile)
                self.assertNotEqual("INAREAPA", private.upper())
                self.assertTrue(resource(override, private + ".PRO").read_bytes()[0x0C] & 0x40)

    def test_empty_ability_inserts_after_all_referenced_effects(self) -> None:
        for multiple, index, casting_last in ((False, 0, False), (True, 0, False), (True, 1, False), (True, 0, True)):
            with self.subTest(multiple=multiple, index=index, casting_last=casting_last), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                packaged = root / "testmod/bardsong/c0bardx.spl"
                packaged.write_bytes(song_loader_with_shared_effect_table(index, multiple=multiple, casting_last=casting_last))
                casting, abilities = effect_records(packaged)
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                loader = resource(root / "override", "C0BARDX.SPL")
                added = parse_spl(loader)
                after_casting, after_abilities = effect_records(loader)
                self.assertEqual(casting, after_casting)
                for before, after, ability in zip(abilities, after_abilities, added.abilities, strict=True):
                    self.assertEqual(before, after[:len(before)])
                    self.assertTrue(any(e.opcode == 309 for e in ability.effects[len(before):]))

    def test_overlapping_nonempty_casting_or_ability_spans_are_skipped(self) -> None:
        self.assert_damaged_inputs_are_isolated({
            "XQOVG.SPL": song_loader_with_shared_effect_table(0, multiple=True, overlap="casting"),
            "XQOVA.SPL": song_loader_with_shared_effect_table(1, multiple=True, overlap="abilities"),
        })

    def seed_external_song_and_bard_text(self, override: Path) -> tuple[Path, Path]:
        song = override / "XQSONG.SPL"
        song.write_bytes((MOD / "abettor/c0abets2.spl").read_bytes())
        text = override / "CLASTEXT.2DA"
        text.write_bytes(b"2DA V1.0\n0\nCLASS MASK NAME DESC\nBARD 5 0 0 0\n")
        return song, text

    def test_assignment_write_preserves_casting_and_out_of_order_ability_slices(self) -> None:
        for multiple in (False, True):
            with self.subTest(multiple=multiple), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                override = root / "override"
                song, _ = self.seed_external_song_and_bard_text(override)
                caller = override / "XQASSIGN.SPL"
                caller.write_bytes(external_assignment_with_late_casting(multiple=multiple))
                casting, abilities = effect_records(caller)
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                pulse = next(e.resource for e in parse_spl(song).abilities[0].effects if e.opcode == 272)
                parsed = parse_spl(caller)
                self.assertEqual([326, 309, 251], [e.opcode for e in parsed.abilities[0].effects])
                self.assertEqual(pulse, parsed.abilities[0].effects[1].resource)
                after_casting, after_abilities = effect_records(caller)
                self.assertEqual(casting, after_casting)
                self.assertEqual(abilities[0], after_abilities[0][2:])
                self.assertEqual(abilities[1:], after_abilities[1:])
                self.assertEqual(0, struct.unpack_from("<H", caller.read_bytes(), 0x6E)[0])

    def test_full_loader_preserves_unwrapped_songs_and_does_not_publish_finite_state(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            self.seed_bard_clabs(override)
            song, text = self.seed_external_song_and_bard_text(override)
            baseline_song, baseline_text = song.read_bytes(), text.read_bytes()
            full = song_loader_with_layout(0x72, 0x9A, effect_count=0xFFFF)
            (root / "testmod/bardsong/c0bardx.spl").write_bytes(full)
            installed = override / "C0BARDX.SPL"
            installed.write_bytes(full)
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.count("skipping C0BARDX.SPL at the 65535-effect capacity limit"))
            self.assertEqual(full, installed.read_bytes())
            self.assertEqual(0xFFFF, struct.unpack_from("<H", installed.read_bytes(), 0x90)[0])
            self.assertEqual(baseline_song, song.read_bytes())
            self.assertEqual(baseline_text, text.read_bytes())
            self.assertNotIn("AP_C0BARDX", resource(override, "CLABBA01.2DA").read_text().split())
            self.assertFalse((override / "C0BWSYS.2DA").exists())

    def test_assignment_overflow_leaves_near_full_caller_unchanged(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song, _ = self.seed_external_song_and_bard_text(override)
            caller = override / "XQASSIGN.SPL"
            baseline = external_assignment_with_late_casting(capacity=0xFFFE)
            caller.write_bytes(baseline)
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.count("skipping XQASSIGN.SPL at the 65535-effect capacity limit"))
            self.assertEqual(baseline, caller.read_bytes())
            self.assertTrue(parse_spl(song).find_effects(opcode=272))

    def test_unusable_loader_preserves_preinstallation_bard_description(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            self.seed_bard_clabs(override, "AP_C0BARDX")
            song, text = self.seed_external_song_and_bard_text(override)
            baseline_song, baseline_text = song.read_bytes(), text.read_bytes()
            (root / "testmod/bardsong/c0bardx.spl").write_bytes(song_loader_with_layout(0x72, 0xFFFFFFFF))
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(baseline_text, text.read_bytes())
            self.assertEqual(baseline_song, song.read_bytes())
            self.assertNotIn("AP_C0BARDX", resource(override, "CLABBA01.2DA").read_text().split())

    def test_loader_uses_last_slot_only_once_and_preserves_the_remaining_song(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            resource(override, "C0ABETS2.SPL").unlink()
            song, _ = self.seed_external_song_and_bard_text(override)
            alternate = override / "XQOTHER.SPL"
            original = song.read_bytes()
            alternate.write_bytes(original)
            (root / "testmod/bardsong/c0bardx.spl").write_bytes(
                song_loader_with_layout(0x72, 0x9A, effect_count=0xFFFE)
            )
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.count("skipping C0BARDX.SPL at the 65535-effect capacity limit"))
            outputs = (song, alternate)
            changed, = [path for path in outputs if path.read_bytes() != original]
            pulse = next(e.resource for e in parse_spl(changed).abilities[0].effects if e.opcode == 272)
            loader = resource(override, "C0BARDX.SPL")
            self.assertEqual(0xFFFF, struct.unpack_from("<H", loader.read_bytes(), 0x90)[0])
            self.assertEqual(pulse, parse_spl(loader).abilities[0].effects[-1].resource)

    def test_compound_assignments_match_legacy_global_and_ability_traversal(self) -> None:
        def opcodes(records):
            return tuple(struct.unpack_from("<H", record)[0] for record in records)

        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song, _ = self.seed_external_song_and_bard_text(override)
            fixtures = assignment_parity_fixtures()
            for name in ("XQMULTI", "XQGL"):
                (override / f"{name}.SPL").write_bytes(fixtures[name])
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            pulse = next(e.resource for e in parse_spl(song).abilities[0].effects if e.opcode == 272)
            pairs = (326, 309) * 3
            patterns = {
                "XQMULTI": ((), ((251,) + pairs + (251,), pairs + (251, 101, 251), pairs + (251,))),
                "XQGL": (pairs + (251,), ((251,) + pairs + (251, 101), pairs + (251,))),
            }
            for name, pattern in patterns.items():
                with self.subTest(name=name):
                    path = override / f"{name}.SPL"
                    casting, abilities = effect_records(path)
                    self.assertEqual(pattern, (opcodes(casting), tuple(map(opcodes, abilities))))
                    records = casting + tuple(record for ability in abilities for record in ability)
                    for opcode, target in ((326, "C0BARDX"), (309, pulse)):
                        self.assertEqual(9, sum(
                            struct.unpack_from("<H", record)[0] == opcode
                            and record[0x14:0x1C].split(b"\0", 1)[0].decode("ascii") == target
                            for record in records
                        ))

    def test_prior_ability_trigger_can_shift_into_the_current_loop(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            self.seed_external_song_and_bard_text(override)
            caller = override / "XQCROSS.SPL"
            caller.write_bytes(assignment_parity_fixtures()["XQCROSS"])
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            spell = parse_spl(caller)
            pairs = [326, 309] * 4
            self.assertEqual(pairs + [251], [e.opcode for e in spell.abilities[0].effects])
            self.assertEqual([251] + pairs + [251], [e.opcode for e in spell.abilities[1].effects])

    def test_assignment_writer_preserves_binary_casting_and_trailing_bytes(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            self.seed_external_song_and_bard_text(override)
            caller = override / "XQOPAQUE.SPL"
            caller.write_bytes(assignment_parity_fixtures()["XQOPAQUE"])
            casting, abilities = effect_records(caller)
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            after_casting, after_abilities = effect_records(caller)
            self.assertEqual(casting, after_casting)
            self.assertEqual(abilities[0], after_abilities[0][2:])
            self.assertTrue(caller.read_bytes().endswith(b"TRAILER\0%SOURCE_RES%"))
            self.assertEqual([326, 309, 251, 101], [e.opcode for e in parse_spl(caller).abilities[0].effects])

    def test_stale_state_is_deactivated_before_a_later_description_pass(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song, text = self.seed_external_song_and_bard_text(override)
            baseline_song, baseline_text = song.read_bytes(), text.read_bytes()
            self.seed_bard_clabs(override, "AP_C0BARDX")
            baseline_state = b"2DA V1.0\n0\n FINITE\nACTIVE 1\n"
            marker = override / "C0BWSYS.2DA"
            marker.write_bytes(baseline_state)
            (root / "testmod/bardsong/c0bardx.spl").write_bytes(b"SPL V1  ")

            # Use the real component identity so the later description pass
            # sees #2004 as installed, independently of its state marker.
            source = (root / "testmod/setup-test.tp2").read_text(encoding="ascii")
            tp2 = root / "testmod/Setup-BardicWonders.tp2"
            tp2.write_text(
                source.replace("ALWAYS\n", "ALWAYS\nINCLUDE ~testmod/lib/bardsong_description.tpa~\n")
                + "\nBEGIN ~Later Bard description pass~ DESIGNATED 2012\n"
                "ACTION_IF NOT MOD_IS_INSTALLED ~Setup-BardicWonders.tp2~ ~2004~ BEGIN "
                "FAIL ~Missing song component in fixture~ END\n"
                "LAF c0bw_write_song_description INT_VAR current_component = 2012 END\n",
                encoding="ascii",
            )
            args = [str(WEIDU), str(tp2), "--no-auto-tp2", "--noautoupdate", "--no-exit-pause",
                    "--game", str(root), "--language", "0"]
            result = subprocess.run(args + ["--force-install-list", "2004"], cwd=root, text=True,
                                    capture_output=True, timeout=60)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(["ACTIVE", "0"], marker.read_text().split()[-2:])
            self.assertEqual(baseline_song, song.read_bytes())
            self.assertEqual(baseline_text, text.read_bytes())
            self.assertNotIn("AP_C0BARDX", resource(override, "CLABBA01.2DA").read_text().split())
            result = subprocess.run(args + ["--force-install-list", "2012"], cwd=root, text=True,
                                    capture_output=True, timeout=60)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(baseline_text, text.read_bytes())

    def test_missing_core_pulse_template_prevents_publication(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song, text = self.seed_external_song_and_bard_text(override)
            self.seed_bard_clabs(override)
            baseline_song, baseline_text = song.read_bytes(), text.read_bytes()
            (root / "testmod/bardsong/c0bardso.EFF").write_bytes(b"EFF V2.0")
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.count("skipping damaged C0BARDSO.EFF"))
            self.assertEqual(baseline_song, song.read_bytes())
            self.assertEqual(baseline_text, text.read_bytes())
            self.assertFalse((override / "C0BWSYS.2DA").exists())
            self.assertNotIn("AP_C0BARDX", resource(override, "CLABBA01.2DA").read_text().split())

    def test_installed_core_pulse_template_fallback_activates_the_song_runtime(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song, text = self.seed_external_song_and_bard_text(override)
            self.seed_bard_clabs(override)
            packaged = root / "testmod/bardsong/c0bardso.EFF"
            installed = override / "C0BARDSO.EFF"
            canonical = packaged.read_bytes()
            installed.write_bytes(canonical)
            packaged.write_bytes(b"EFF V2.0")
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.count("skipping damaged C0BARDSO.EFF"))
            self.assertEqual(canonical, installed.read_bytes())
            pulse = next(effect.resource for effect in parse_spl(song).abilities[0].effects if effect.opcode == 272)
            self.assertEqual(pulse, read_eff_resource(resource(override, f"{pulse}.EFF")))
            self.assertEqual(["ACTIVE", "1"], resource(override, "C0BWSYS.2DA").read_text().split()[-2:])
            self.assertIn("AP_C0BARDX", resource(override, "CLABBA01.2DA").read_text().split())
            self.assertIn("six rounds", tlk_string(root / "dialog.tlk", int(text.read_text().split()[-1])))

    def assert_rejected_delivery_fallback(self, root: Path, name: str) -> None:
        override = root / "override"
        self.seed_bard_clabs(override, "AP_C0BARDX")
        song, text = self.seed_external_song_and_bard_text(override)
        original_song, original_text = song.read_bytes(), text.read_bytes()
        result = self.install(root)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(1, result.stdout.upper().count(f"SKIPPING DAMAGED {name}"))
        self.assertEqual(original_song, song.read_bytes())
        self.assertEqual(original_text, text.read_bytes())
        self.assertFalse(any(path.name.upper().startswith("C0BW00") for path in override.iterdir()))
        self.assertNotIn("AP_C0BARDX", resource(override, "CLABBA01.2DA").read_text().split())
        self.assertEqual(["ACTIVE", "0"], resource(override, "C0BWSYS.2DA").read_text().split()[-2:])

    def test_valid_eff_header_with_display_opcode_is_not_a_usable_pulse_fallback(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            packaged = root / "testmod/bardsong/c0bardso.EFF"
            fallback = bytearray(packaged.read_bytes())
            struct.pack_into("<I", fallback, 0x10, 139)
            (root / "override/C0BARDSO.EFF").write_bytes(fallback)
            packaged.write_bytes(b"EFF V2.0")
            self.assert_rejected_delivery_fallback(root, "C0BARDSO.EFF")

    def test_installed_controller_pulse_slots_retarget_an_old_payload(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            song, _ = self.seed_external_song_and_bard_text(override)
            self.seed_bard_clabs(override)
            packaged = root / "testmod/bardsong/c0bardso.spl"
            fallback = retarget_controller_fixture(packaged.read_bytes(), b"PREVPULS")
            (override / "C0BARDSO.SPL").write_bytes(fallback)
            packaged.write_bytes(b"SPL V1  ")
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.upper().count("SKIPPING DAMAGED C0BARDSO.SPL"))
            self.assertEqual(fallback, resource(override, "C0BARDSO.SPL").read_bytes())
            controller = parse_spl(song)
            pulse = next(effect.resource for effect in controller.abilities[0].effects if effect.opcode == 272)
            self.assertNotEqual("PREVPULS", pulse)
            for ability in controller.abilities:
                self.assertEqual({pulse, "C0SINGIN"}, {e.resource for e in ability.effects if e.opcode == 177})
                self.assertEqual({pulse, "C0SINGIN", "C0SINGI2"},
                                 {e.resource for e in ability.effects if e.opcode == 272})
                self.assertEqual({pulse}, {e.resource for e in ability.effects if e.opcode == 328})
            effect = resource(override, f"{pulse}.EFF")
            self.assertEqual(146, struct.unpack_from("<I", effect.read_bytes(), 0x10)[0])
            self.assertEqual(pulse, read_eff_resource(effect))
            payload = parse_spl(resource(override, f"{pulse}.SPL"))
            ids = {int(index) + 1: name.upper()
                   for index, name, *_ in (line.split() for line in resource(override, "PROJECTL.IDS").read_text().splitlines())
                   if index.isdigit()}
            for ability in payload.abilities:
                projectile = ids[ability.projectile]
                self.assertNotEqual("INAREAPA", projectile)
                self.assertTrue(resource(override, projectile + ".PRO").read_bytes()[0x0C] & 0x40)
            self.assertIn("AP_C0BARDX", resource(override, "CLABBA01.2DA").read_text().split())
            self.assertEqual(["ACTIVE", "1"], resource(override, "C0BWSYS.2DA").read_text().split()[-2:])

    def test_spell_without_pulse_delivery_is_not_a_usable_controller_fallback(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            packaged = root / "testmod/bardsong/c0bardso.spl"
            source = root / "testmod/bardsong/c0bardsx.spl"
            shutil.copy2(source, root / "override/C0BARDSO.SPL")
            packaged.write_bytes(b"SPL V1  ")
            self.assert_rejected_delivery_fallback(root, "C0BARDSO.SPL")

    def test_symphony_uses_installed_cue_and_restores_missing_hla(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            packaged = root / "testmod/bardsong/c0singin.EFF"
            canonical = packaged.read_bytes()
            (override / "C0SINGIN.EFF").write_bytes(canonical)
            packaged.write_bytes(b"EFF V2.0")
            resource(override, "C0ABETHL.SPL").unlink()
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.upper().count("SKIPPING DAMAGED C0SINGIN.EFF"))
            self.assertEqual(canonical, resource(override, "C0SINGIN.EFF").read_bytes())
            finale = resource(override, "C0ABIVS.EFF").read_bytes()
            self.assertEqual(canonical[:0x30] + b"C0ABIVI\0" + canonical[0x38:], finale)
            self.assertTrue(parse_spl(resource(override, "C0ABIVI.SPL")).find_effects(opcode=20))
            controller = parse_spl(resource(override, "C0ABETS2.SPL"))
            self.assertTrue(controller.find_effects(opcode=177, resource="C0ABIVS"))
            pulse = next(e.resource for e in controller.abilities[0].effects if e.opcode == 272)
            hla = parse_spl(resource(override, "C0ABETHL.SPL"))
            self.assertEqual(1, len(hla.find_effects(opcode=326, resource="C0BARDX")))
            self.assertEqual(1, len(hla.find_effects(opcode=309, resource=pulse)))
            rows = resource(override, "LUC0ABET.2DA").read_text().splitlines()
            self.assertEqual(1, sum("AP_C0ABETHL" in row.split() for row in rows))

    def test_symphony_scrubs_dangling_hla_if_both_sources_are_missing(self) -> None:
        for runtime_available in (True, False):
            with self.subTest(runtime_available=runtime_available), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                override = root / "override"
                table = resource(override, "LUC0ABET.2DA")
                with table.open("a", encoding="ascii") as stream:
                    stream.write("C0ABET2 AP_C0ABETHL * * 1 99 1 AP_C0ABETT5 *\n")
                resource(override, "C0ABETHL.SPL").unlink()
                (root / "testmod/abettor/c0abethl.spl").unlink()
                if not runtime_available:
                    (root / "testmod/bardsong/c0bardx.spl").write_bytes(b"SPL V1  ")
                self.assertIn("AP_C0ABETHL", table.read_text().split())
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertNotIn("AP_C0ABETHL", table.read_text().split())
                self.assertIn("AP_C0ABETT5", table.read_text().split())
                self.assertFalse(any(path.name.upper() in {"C0ABETHL.SPL", "C0ABIVS.EFF", "C0ABIVI.SPL"}
                                     for path in override.iterdir()))

    def test_fallback_preserves_an_existing_non_cast_cue(self) -> None:
        for label, cue_present in (("installed fallback", True), ("packaged controller", False)):
            with self.subTest(label=label), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                override = root / "override"
                song, _ = self.seed_external_song_and_bard_text(override)
                self.seed_bard_clabs(override)
                packaged = root / "testmod/bardsong/c0bardso.spl"
                controller = packaged.read_bytes()
                if cue_present:
                    controller = retarget_controller_fixture(controller, b"PREVPULS")
                controller, cue = add_controller_cue(controller, b"XQCUEREF")
                if cue_present:
                    (override / "C0BARDSO.SPL").write_bytes(controller)
                    shutil.copy2(root / "testmod/bardsong/c0singin.EFF", override / "XQCUEREF.EFF")
                    packaged.write_bytes(b"SPL V1  ")
                else:
                    # A packaged controller may have an additional unresolved
                    # cue. The explicit template marker is still unique.
                    packaged.write_bytes(controller)
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(cue, effect_records(song)[1][-1][-2:])
                self.assertNotIn(b"PREVPULS", song.read_bytes())
                pulse = parse_spl(song).find_effects(opcode=272)[0].resource
                pulse_eff = resource(override, f"{pulse}.EFF")
                self.assertEqual(146, struct.unpack_from("<I", pulse_eff.read_bytes(), 0x10)[0])
                self.assertEqual(pulse, read_eff_resource(pulse_eff))
                payload = parse_spl(resource(override, f"{pulse}.SPL"))
                ids = {int(index) + 1: name.upper() for index, name, *_ in
                       (line.split() for line in resource(override, "PROJECTL.IDS").read_text().splitlines())
                       if index.isdigit()}
                private_projectile = ids[payload.abilities[0].projectile]
                self.assertTrue(private_projectile.startswith("C0P"))
                self.assertTrue(resource(override, private_projectile + ".PRO").read_bytes()[0x0C] & 0x40)
                self.assertEqual(["ACTIVE", "1"], resource(override, "C0BWSYS.2DA").read_text().split()[-2:])

    def test_fallback_with_two_pulse_candidates_is_rejected(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            packaged = root / "testmod/bardsong/c0bardso.spl"
            controller = retarget_controller_fixture(packaged.read_bytes(), b"PREVPULS")
            controller, _ = add_controller_cue(controller, b"OTHERPUL")
            (override / "C0BARDSO.SPL").write_bytes(controller)
            shutil.copy2(root / "testmod/bardsong/c0bardso.EFF", override / "OTHERPUL.EFF")
            packaged.write_bytes(b"SPL V1  ")
            self.assert_rejected_delivery_fallback(root, "C0BARDSO.SPL")

    def test_missing_optional_finale_keeps_the_finite_symphony_grant(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            (root / "testmod/bardsong/c0singin.EFF").write_bytes(b"EFF V2.0")
            table = resource(override, "LUC0ABET.2DA")
            with table.open("a", encoding="ascii") as stream:
                stream.write("C0ABET2 AP_C0ABETHL * * 1 99 1 AP_C0ABETT5 *\n")
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.upper().count("SKIPPING DAMAGED C0SINGIN.EFF"))
            self.assertEqual(1, table.read_text().split().count("AP_C0ABETHL"))
            self.assertFalse(any(path.name.upper() in {"C0ABIVS.EFF", "C0ABIVI.SPL"} for path in override.iterdir()))
            controller = parse_spl(resource(override, "C0ABETS2.SPL"))
            self.assertFalse(controller.find_effects(resource="C0ABIVS"))
            pulse = next(e.resource for e in controller.abilities[0].effects if e.opcode == 272)
            self.assertEqual(pulse, read_eff_resource(resource(override, f"{pulse}.EFF")))
            hla_path = resource(override, "C0ABETHL.SPL")
            hla = parse_spl(hla_path)
            self.assertEqual(1, len(hla.find_effects(opcode=251, resource="C0ABETS2")))
            self.assertEqual(1, len(hla.find_effects(opcode=326, resource="C0BARDX")))
            self.assertEqual(1, len(hla.find_effects(opcode=309, resource=pulse)))
            desc, = struct.unpack_from("<I", hla_path.read_bytes(), 0x50)
            self.assertNotIn("when the song ends", tlk_string(root / "dialog.tlk", desc))

    def test_invalid_later_donor_leaves_all_projectile_registrations_untouched(self) -> None:
        self.assert_projectiles_unchanged_for_rejected_external_song(
            last_id=523, second_donor=b"PRO V1.0", diagnostic="SKIPPING DAMAGED XQBADPRO.PRO",
        )

    def test_projectile_word_capacity_is_checked_for_the_whole_song(self) -> None:
        self.assert_projectiles_unchanged_for_rejected_external_song(
            last_id=65533, second_donor=(MOD / "bardsong/c0bardso.PRO").read_bytes(),
            diagnostic="NO PROJECTILE IDS AVAILABLE FOR XQSONG.SPL",
        )

    def assert_projectiles_unchanged_for_rejected_external_song(self, *, last_id, second_donor, diagnostic) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            ids = (b"IDS V1.0\r\n157 INAREAPA\r\n481 XQBADPRO\r\n521 C0BARDSO\r\n522 C0BWSPA\r\n"
                   + f"{last_id} C0BWSNP\r\n".encode("ascii"))
            index = resource(override, "PROJECTL.IDS")
            index.write_bytes(ids)
            (override / "XQBADPRO.PRO").write_bytes(second_donor)
            song = bytearray((MOD / "abettor/c0abets2.spl").read_bytes())
            duplicate_first_ability(song)
            ability_table, = struct.unpack_from("<I", song, 0x64)
            struct.pack_into("<H", song, ability_table + 40 + 0x26, 482)
            source = override / "XQSONG.SPL"
            source.write_bytes(song)
            assignment = override / "XQASSIGN.SPL"
            caller = (MOD / "abettor/c0abethl.spl").read_bytes().replace(b"C0ABETS2", b"XQSONG\0\0")
            assignment.write_bytes(caller)
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(1, result.stdout.upper().count(diagnostic))
            self.assertEqual(song, source.read_bytes())
            self.assertEqual(caller, assignment.read_bytes())
            self.assertEqual(ids, index.read_bytes())
            self.assertFalse(any(path.name.upper().startswith("C0P") and path.suffix.upper() == ".PRO"
                                 for path in override.iterdir()))
            self.assertEqual(second_donor, (override / "XQBADPRO.PRO").read_bytes())

    def test_projectile_donor_requires_all_type_specific_blocks(self) -> None:
        source = (MOD / "bardsong/c0bardso.PRO").read_bytes()
        for kind, size in ((3, 0x100), (3, 0x200), (2, 0x100), (0, 0x300), (99, 0x300)):
            with self.subTest(kind=kind, size=size):
                donor = bytearray(source[:size])
                struct.pack_into("<H", donor, 0x08, kind)
                self.assert_damaged_inputs_are_isolated({"XQBADPRO.PRO": bytes(donor)}, bad_donor=True)

    def test_symphony_finale_rejects_bad_inner_eff_header_or_one_byte_truncation(self) -> None:
        source = (MOD / "bardsong/c0singin.eff").read_bytes()
        self.assertEqual(0x110, len(source))
        for data in (source[:8] + b"NOT EFF!" + source[16:], source[:0x10F]):
            with self.subTest(size=len(data)), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                (root / "testmod/bardsong/c0singin.eff").write_bytes(data)
                override = root / "override"
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(1, result.stdout.upper().count("SKIPPING DAMAGED C0SINGIN.EFF"))
                self.assertFalse(any(path.name.upper() in {"C0SINGIN.EFF", "C0ABIVS.EFF", "C0ABIVI.SPL"}
                                     for path in override.iterdir()))
                symphony = parse_spl(resource(override, "C0ABETS2.SPL"))
                pulse = next(e.resource for e in symphony.abilities[0].effects if e.opcode == 272)
                self.assertEqual(pulse, read_eff_resource(resource(override, pulse + ".EFF")))

    def test_owned_eff_and_projectile_are_restored_from_valid_packaged_assets(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            for name, data in (
                ("C0SINGIN.EFF", b"EFF V2.0NOT EFF!" + bytes(0x100)),
                ("C0ABIVS.EFF", b"EFF V2.0NOT EFF!" + bytes(0x100)),
                ("C0BARDSO.PRO", b"PRO V1.0"),
                ("C0BWSPA.PRO", b"PRO V1.0"),
            ):
                (override / name).write_bytes(data)
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            canonical = (MOD / "bardsong/c0singin.eff").read_bytes()
            self.assertEqual(canonical, resource(override, "C0SINGIN.EFF").read_bytes())
            expected = canonical[:0x30] + b"C0ABIVI\0" + canonical[0x38:]
            self.assertEqual(expected, resource(override, "C0ABIVS.EFF").read_bytes())
            self.assertEqual((MOD / "bardsong/c0bardso.PRO").read_bytes(),
                             resource(override, "C0BARDSO.PRO").read_bytes())
            self.assertEqual((MOD / "bardsong/projectiles/C0BWSPA.PRO").read_bytes(),
                             resource(override, "C0BWSPA.PRO").read_bytes())

    def test_external_assignment_preserves_legacy_exemptions(self) -> None:
        source = (MOD / "abettor/c0abets2.spl").read_bytes()
        different_type = bytearray(source)
        different_type[0x1C] = 4
        without_icon = bytearray(source)
        effects = struct.unpack_from("<I", source, 0x6A)[0]
        for offset in range(effects, len(source), 48):
            if struct.unpack_from("<H", source, offset)[0] == 142:
                struct.pack_into("<I", without_icon, offset + 8, 0)
        assignment = (MOD / "abettor/c0abethl.spl").read_bytes().replace(b"C0ABETS2", b"XQSONG\0\0")

        for label, song in (
            ("self-targeted opcode 126", song_with_self_targeted_movement(source)),
            ("not a type-5 song", bytes(different_type)),
            ("no ability effect with opcode 142 and icon 40", bytes(without_icon)),
        ):
            with self.subTest(label=label), disposable_game() as root:
                self.make_fixture(root, existing_projectile=520, snapshot=False)
                override = root / "override"
                song_file = override / "XQSONG.SPL"
                assignment_file = override / "XQASSIGN.SPL"
                song_file.write_bytes(song)
                assignment_file.write_bytes(assignment)
                result = self.install(root)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(song, song_file.read_bytes())
                self.assertEqual(assignment, assignment_file.read_bytes())

    def test_owned_stock_song_with_self_targeted_movement_is_still_wrapped(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            override = root / "override"
            source = (MOD / "abettor/c0abets2.spl").read_bytes()
            stock = override / "SPCL542A.SPL"
            stock.write_bytes(song_with_self_targeted_movement(source))
            self.assertEqual(1, len(parse_spl(stock).find_effects(opcode=126, target=1)))
            assignment = (MOD / "abettor/c0abethl.spl").read_bytes().replace(b"C0ABETS2", b"SPCL542A")
            assignment_file = override / "XQASSIGN.SPL"
            assignment_file.write_bytes(assignment)

            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            wrapper = parse_spl(stock)
            self.assertEqual(0, len(wrapper.find_effects(opcode=126)))
            pulse = next(e.resource for e in wrapper.abilities[0].effects if e.opcode == 272)
            self.assertEqual(pulse, read_eff_resource(resource(override, pulse + ".EFF")))
            self.assertEqual(1, len(parse_spl(assignment_file).find_effects(opcode=309, resource=pulse)))
            ids = {
                int(index) + 1: name.upper()
                for index, name, *_ in (line.split() for line in resource(override, "PROJECTL.IDS").read_text().splitlines())
                if index.isdigit()
            }
            self.assertEqual({"C0BARDSO"}, {ids[a.projectile] for a in wrapper.abilities})
            payload = parse_spl(resource(override, pulse + ".SPL"))
            self.assertEqual({"C0BWSPA"}, {ids[a.projectile] for a in payload.abilities})
            for name in ("C0BARDSO", "C0BWSPA"):
                self.assertTrue(resource(override, name + ".PRO").read_bytes()[0x0C] & 0x40, name)

    def test_edited_stock_and_symphony_inputs_are_rewritten(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=1720, snapshot=False)
            override = root / "override"
            old_song = bytearray((MOD / "abettor/c0abets2.spl").read_bytes())
            ability = struct.unpack_from("<I", old_song, 0x64)[0]
            effect = struct.unpack_from("<I", old_song, 0x6A)[0]
            old_song[0x1C] = 4
            old_song[ability + 4:ability + 12] = b"EDITICON"
            struct.pack_into("<H", old_song, ability + 0x0E, 73)
            struct.pack_into("<H", old_song, ability + 0x26, 1)
            struct.pack_into("<H", old_song, effect, 126)
            # Add a valid second ability and a global effect. Legacy layouts
            # and counts must not veto rebuilding the owned controller.
            count = struct.unpack_from("<H", old_song, 0x68)[0]
            duplicate_first_ability(old_song)
            global_first = (len(old_song) - (effect + 40)) // 48
            struct.pack_into("<HH", old_song, 0x6E, global_first, 1)
            old_song.extend(struct.pack("<H", 142) + bytes(46))
            (override / "SPCL542A.SPL").write_bytes(old_song)
            resource(override, "C0ABETS2.SPL").write_bytes(old_song)
            (override / "C0ABIVI.SPL").write_bytes(old_song)
            (override / "CLASTEXT.2DA").write_text(
                "2DA V1.0\n0\nCLASS MASK NAME DESC\nBARD 5 0 0 0\n"
            )
            result = self.install(root)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertNotIn("skipping Symphony", result.stdout)
            ids = resource(override, "PROJECTL.IDS").read_text().splitlines()
            party = next(int(l.split()[0]) + 1 for l in ids if l.split()[-1:] == ["C0BWSPA"])
            controller = next(int(l.split()[0]) + 1 for l in ids if
                              [x.upper() for x in l.split()[-1:]] == ["C0BARDSO"])
            for spell in ("SPCL542A", "C0ABETS2"):
                song = parse_spl(resource(override, spell + ".SPL"))
                self.assertEqual({controller}, {ability.projectile for ability in song.abilities})
                payload = next(e.resource for e in song.abilities[0].effects if e.opcode == 272)
                payload_path = resource(override, payload + ".SPL")
                abilities = parse_spl(payload_path).abilities
                self.assertEqual(count + 1, len(abilities))
                self.assertEqual({party}, {a.projectile for a in abilities})
                self.assertEqual(142, struct.unpack_from("<H", effect_records(payload_path)[0][0])[0])
            invisibility = parse_spl(resource(override, "C0ABIVI.SPL"))
            self.assertEqual(party, invisibility.abilities[0].projectile)
            self.assertEqual(50, invisibility.abilities[0].range)
            table = resource(override, "CLASTEXT.2DA").read_text().splitlines()
            description = int(next(l for l in table if l.startswith("BARD")).split()[4])
            self.assertIn("Class features", tlk_string(root / "dialog.tlk", description))
            self.assertIn("six rounds", tlk_string(root / "dialog.tlk", description))
            self.assertIn("cannot be cast while wearing armor", tlk_string(root / "dialog.tlk", description))

    def test_iwd_stock_profiles_are_written_without_kit_components(self) -> None:
        with disposable_game() as root:
            self.make_fixture(root, existing_projectile=520, snapshot=False)
            # WeiDU selects the IWD:EE branch via HOWPARTY.2DA in chitin.key.
            howparty = struct.pack("<8sHI", b"HOWPARTY", 0x3F4, 0)
            (root / "chitin.key").write_bytes(b"KEY V1  " + struct.pack("<IIII", 0, 1, 24, 24) + howparty)
            language = root / "lang/en_US"
            language.mkdir(parents=True)
            (root / "dialog.tlk").rename(language / "dialog.tlk")
            override = root / "override"
            profiles = {
                "SPCL115": "C0BWSIA", "SPCL116": "C0BWSIA", "SPCL117": "C0BWSIA",
                "SPCL118": "C0BWSIW", "SPCL119": "C0BWSIA", "SPCL120": "C0BWSIA",
                "SPCL542A": "C0BWSIA", "SPCL751A": "C0BWSIW", "SPCL920A": "C0BWSPA",
            }
            for spell in profiles:
                shutil.copy2(MOD / "abettor/c0abets2.spl", override / f"{spell}.SPL")
            stock = {spell: effect_records(override / f"{spell}.SPL") for spell in profiles}
            result = self.install(root, "--use-lang", "en_US")
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            ids = {}
            for line in resource(override, "PROJECTL.IDS").read_text().splitlines():
                columns = line.split()
                if len(columns) == 2 and columns[0].isdigit():
                    ids[columns[1].upper()] = int(columns[0]) + 1
            for spell, name in profiles.items():
                path = resource(override, spell + ".SPL")
                self.assertEqual(stock[spell], effect_records(path))
                self.assertEqual({ids[name]}, {a.projectile for a in parse_spl(path).abilities})
            for name, radius in (("C0BWSIA", 512), ("C0BWSIW", 426), ("C0BWSPA", 256)):
                data = resource(override, name + ".PRO").read_bytes()
                self.assertTrue(data[0x0C] & 0x40, name)
                self.assertEqual(radius, struct.unpack_from("<H", data, 0x204)[0], name)

    def install(self, root: Path, *game_args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(WEIDU), "testmod/setup-test.tp2", "--no-auto-tp2", "--game", str(root), "--no-exit-pause",
             "--language", "0", *game_args, "--force-install-list", "2004"],
            cwd=root, text=True, capture_output=True, check=False, timeout=60,
        )

    def test_real_producer_accepts_dynamic_ids_without_phantom_base_eff(self) -> None:
        payloads: list[str] = []
        projectile_ids: list[int] = []
        for projectile_seed in (558, 1200):
            with self.subTest(projectile_seed=projectile_seed), disposable_game() as root:
                self.make_fixture(root, existing_projectile=projectile_seed, reserve_payload_name=bool(payloads))
                result = self.install(root)
                output = result.stdout + result.stderr
                before = root / "producer-snapshot"
                self.assertTrue(before.is_dir(), output)
                original = parse_spl(resource(before, "C0ABETS2.SPL"))
                payload = next(effect.resource for effect in original.abilities[0].effects if effect.opcode == 177 and effect.timing == 10)
                payloads.append(payload)
                projectile_ids.append(original.abilities[0].projectile)
                for name in ("C0BARDSO", "C0BWSPA", "C0BWSNP"):
                    projectile = resource(before, f"{name}.PRO").read_bytes()
                    self.assertTrue(projectile[0x0C] & 0x40, name)
                for name in ("INAREA", "INAREANP", "INAREAPA", "INAREASM", "BIGNAREA"):
                    projectile = resource(root / "override", f"{name}.PRO").read_bytes()
                    self.assertFalse(projectile[0x0C] & 0x40, name)
                    self.assertEqual(0x4F, projectile[0x21A], name)
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
                    ends = [effect for effect in new.effects if effect.resource == "C0ABIVI"]
                    self.assertEqual(1, len(starts))
                    self.assertEqual(1, len(ends))
                    self.assertTrue(starts[0].matches(opcode=177, target=9, timing=1, duration=0))
                    duration = song_ticks(old, payload)
                    self.assertEqual(600 + index * 100, duration)
                    self.assertEqual(1 if index == 0 else index * 5, new.required_level)
                    self.assertTrue(is_finale(ends[0], duration), ends[0])
                    retained = tuple(record for record in after_headers[index] if record[0x14:0x1C].split(b"\0", 1)[0] not in (b"C0ABIVS", b"C0ABIVI"))
                    self.assertEqual(before_headers[index], retained)
                # Each finale waits for its own song: 40 seconds at the first
                # level, 107 at the last.
                self.assertEqual(
                    [40, 47, 54, 60, 67, 74, 80, 87, 94, 100, 107],
                    [effect.duration for effect in patched.find_effects(resource="C0ABIVI")],
                )
                self.assertEqual((), patched.find_effects(resource="C0ABIVE"))
                self.assertFalse((after / "C0ABIVE.EFF").exists())
                party_projectile = next(
                    int(line.split()[0]) + 1 for line in resource(after, "PROJECTL.IDS").read_text().splitlines()
                    if line.split() and line.split()[-1].upper() == "C0BWSPA"
                )
                expected_payload = bytearray(resource(before, f"{payload}.SPL").read_bytes())
                payload_header = struct.unpack_from("<I", expected_payload, 0x64)[0]
                struct.pack_into("<H", expected_payload, payload_header + 0x26, party_projectile)
                self.assertEqual(expected_payload, resource(after, f"{payload}.SPL").read_bytes())
                self.assertEqual(resource(before, "C0BARDSX.SPL").read_bytes(), resource(after, "C0BARDSX.SPL").read_bytes())
                cooldown = parse_spl(resource(after, "C0BARDSX.SPL"))
                self.assertEqual(1, len(cooldown.find_effects(opcode=144, target=9, parameter2=10, timing=10, duration=1000)))
                self.assertEqual(1, len(cooldown.find_effects(opcode=139, target=9, timing=3, duration=66)))
                self.assertFalse((after / "C0ABETS2.EFF").exists())
                self.assertEqual(1, resource(after, "LUC0ABET.2DA").read_text().count("AP_C0ABETHL"))
                invisibility = parse_spl(resource(after, "C0ABIVI.SPL"))
                self.assertEqual(party_projectile, invisibility.abilities[0].projectile)
                self.assertEqual(5, invisibility.abilities[0].target)
                self.assertEqual(1, len(invisibility.effects))
                self.assertTrue(invisibility.effects[0].matches(opcode=20, target=2, parameter2=0, timing=0, duration=6))
        self.assertEqual(2, len(set(projectile_ids)))
        self.assertEqual(2, len(set(payloads)))


if __name__ == "__main__":
    unittest.main()
