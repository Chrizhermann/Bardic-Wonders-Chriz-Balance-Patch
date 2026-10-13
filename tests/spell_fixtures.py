"""Synthetic SPL, TLK and game fixtures for real-WeiDU installer tests.

The fixtures are built from scratch: no game resource is read or bundled.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
import shutil
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "BardicWonders"
WEIDU = ROOT / "Setup-BardicWonders.exe"
EMPTY_KEY = b"KEY V1  " + struct.pack("<IIII", 0, 0, 0x18, 0x18)
NONE = 0xFFFFFFFF
IDENTITY_OPCODES = (206, 318, 321, 324)


def resref(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii").upper()


@dataclass(frozen=True)
class Fx:
    opcode: int
    target: int = 2
    power: int = 1
    parameter1: int = 0
    parameter2: int = 0
    timing: int = 0
    resist_dispel: int = 1
    duration: int = 0
    probability1: int = 100
    probability2: int = 0
    resource: str = ""
    dice_count: int = 0
    dice_size: int = 0
    save_type: int = 0
    save_bonus: int = 0
    special: int = 0

    def pack(self) -> bytes:
        data = bytearray(0x30)
        struct.pack_into(
            "<HBBiiBBIBB", data, 0, self.opcode, self.target, self.power,
            self.parameter1, self.parameter2, self.timing, self.resist_dispel,
            self.duration, self.probability1, self.probability2,
        )
        data[0x14:0x1C] = self.resource.encode("ascii").ljust(8, b"\0")
        struct.pack_into(
            "<IIIiI", data, 0x1C, self.dice_count, self.dice_size,
            self.save_type, self.save_bonus, self.special,
        )
        return bytes(data)

    @classmethod
    def unpack(cls, data: bytes, offset: int) -> "Fx":
        values = struct.unpack_from("<HBBiiBBIBB", data, offset)
        tail = struct.unpack_from("<IIIiI", data, offset + 0x1C)
        return cls(*values, resref(data[offset + 0x14:offset + 0x1C]), *tail)


@dataclass(frozen=True)
class Ability:
    effects: tuple[Fx, ...]
    icon: str = ""
    target: int = 1
    range: int = 30
    level: int = 1
    projectile: int = 1


@dataclass(frozen=True)
class Spell:
    abilities: tuple[Ability, ...]
    name: int = NONE
    description: int = NONE
    spell_type: int = 2
    level: int = 1
    icon: str = ""
    casting: tuple[Fx, ...] = ()
    flags: int = 0
    exclusion: int = 0

    def pack(self) -> bytes:
        header = bytearray(0x72)
        header[0:8] = b"SPL V1  "
        struct.pack_into("<II", header, 0x08, self.name, NONE)
        struct.pack_into("<I", header, 0x18, self.flags)
        struct.pack_into("<H", header, 0x1C, self.spell_type)
        struct.pack_into("<I", header, 0x1E, self.exclusion)
        struct.pack_into("<I", header, 0x34, self.level)
        header[0x3A:0x42] = self.icon.encode("ascii").ljust(8, b"\0")
        struct.pack_into("<II", header, 0x50, self.description, NONE)
        effects = list(self.casting)
        abilities = b""
        for ability in self.abilities:
            raw = bytearray(0x28)
            raw[0] = 1
            raw[2] = 2
            raw[4:12] = ability.icon.encode("ascii").ljust(8, b"\0")
            raw[0x0C] = ability.target
            struct.pack_into("<HHH", raw, 0x0E, ability.range, ability.level, 1)
            struct.pack_into("<HHH", raw, 0x1E, len(ability.effects), len(effects), 1)
            struct.pack_into("<H", raw, 0x26, ability.projectile)
            effects.extend(ability.effects)
            abilities += bytes(raw)
        struct.pack_into(
            "<IHIHH", header, 0x64, 0x72, len(self.abilities),
            0x72 + len(abilities), 0, len(self.casting),
        )
        return bytes(header) + abilities + b"".join(effect.pack() for effect in effects)

    @classmethod
    def read(cls, path: Path) -> "Spell":
        data = path.read_bytes()
        if data[:8] != b"SPL V1  ":
            raise AssertionError(f"not an SPL V1 file: {path}")
        ability_offset, ability_count, effect_offset, cast_first, cast_count = (
            struct.unpack_from("<IHIHH", data, 0x64))

        def effects(first: int, count: int) -> tuple[Fx, ...]:
            return tuple(Fx.unpack(data, effect_offset + 0x30 * index)
                         for index in range(first, first + count))

        abilities = []
        for index in range(ability_count):
            offset = ability_offset + 0x28 * index
            count, first = struct.unpack_from("<HH", data, offset + 0x1E)
            abilities.append(Ability(
                effects=effects(first, count),
                icon=resref(data[offset + 4:offset + 12]),
                target=data[offset + 0x0C],
                range=struct.unpack_from("<H", data, offset + 0x0E)[0],
                level=struct.unpack_from("<H", data, offset + 0x10)[0],
                projectile=struct.unpack_from("<H", data, offset + 0x26)[0],
            ))
        return cls(
            abilities=tuple(abilities),
            name=struct.unpack_from("<I", data, 0x08)[0],
            description=struct.unpack_from("<I", data, 0x50)[0],
            spell_type=struct.unpack_from("<H", data, 0x1C)[0],
            level=struct.unpack_from("<I", data, 0x34)[0],
            icon=resref(data[0x3A:0x42]),
            casting=effects(cast_first, cast_count),
            flags=struct.unpack_from("<I", data, 0x18)[0],
            exclusion=struct.unpack_from("<I", data, 0x1E)[0],
        )

    @property
    def effects(self) -> tuple[Fx, ...]:
        return self.casting + tuple(fx for ability in self.abilities for fx in ability.effects)


def imported(source: Spell, source_resref: str, destination: str, spell_type: int, level: int) -> Spell:
    """The documented import: type/level set, identity references duplicated
    for the copy (each copy placed above its original), Mold Touch named."""

    def convert(effects: tuple[Fx, ...]) -> tuple[Fx, ...]:
        result = []
        for fx in effects:
            if fx.opcode == 78 and fx.parameter2 in (11, 12) and not fx.resource:
                fx = replace(fx, resource=f"{source_resref}B")
            if fx.opcode in IDENTITY_OPCODES and fx.resource.upper() == source_resref.upper():
                result.append(replace(fx, resource=destination.upper()))
            result.append(fx)
        return tuple(result)

    return replace(
        source,
        spell_type=spell_type,
        level=level,
        casting=convert(source.casting),
        abilities=tuple(replace(a, effects=convert(a.effects)) for a in source.abilities),
    )


def tlk(strings: list[str]) -> bytes:
    entries, text = b"", b""
    for string in strings:
        raw = string.encode("utf-8")
        entry = bytearray(0x1A)
        struct.pack_into("<H", entry, 0, 1 if raw else 0)
        struct.pack_into("<II", entry, 0x12, len(text), len(raw))
        entries += bytes(entry)
        text += raw
    return (b"TLK V1  " + struct.pack("<HII", 0, len(strings), 0x12 + 0x1A * len(strings))
            + entries + text)


def tlk_string(path: Path, strref: int) -> str:
    data = path.read_bytes()
    count, base = struct.unpack_from("<II", data, 0x0A)
    if not 0 <= strref < count:
        raise AssertionError(f"strref {strref} outside TLK with {count} entries")
    offset, length = struct.unpack_from("<II", data, 0x12 + 0x1A * strref + 0x12)
    return data[base + offset:base + offset + length].decode("utf-8")


def spell_ids(entries: dict[str, int]) -> str:
    return "IDS V1.0\n" + "".join(f"{number} {symbol}\n" for symbol, number in entries.items())


def file_snapshot(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix().lower(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def resource(directory: Path, name: str) -> Path:
    matches = [path for path in directory.iterdir() if path.name.upper() == name.upper()]
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} in {directory}, found {matches}")
    return matches[0]


def make_game(root: Path, strings: list[str]) -> Path:
    """An empty-key EE game: every resource comes from override."""
    override = root / "override"
    override.mkdir(parents=True)
    (root / "chitin.key").write_bytes(EMPTY_KEY)
    (root / "dialog.tlk").write_bytes(tlk(strings))
    return override


def copy_libraries(mod: Path, *names: str) -> None:
    (mod / "lib").mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy2(MOD / "lib" / name, mod / "lib" / name)


def section(path: Path, start: str, end: str | None = None) -> str:
    """Production source between two markers (start included, end excluded)."""
    text = path.read_text(encoding="utf-8")
    first = text.index(start)
    if text.count(start) != 1:
        raise AssertionError(f"marker is not unique in {path.name}: {start!r}")
    if end is None:
        return text[first:]
    return text[first:text.index(end, first)]


def run_weidu(root: Path, tp2: str, *, install=(), uninstall=()) -> str:
    options = []
    if uninstall:
        options += ["--force-uninstall-list", *(str(n) for n in uninstall)]
    if install:
        options += ["--force-install-list", *(str(n) for n in install)]
    result = subprocess.run(
        [str(WEIDU), "--no-auto-tp2", "--noautoupdate", "--game", str(root),
         "--tlkin", "dialog.tlk", "--tlkout", "dialog.tlk", "--no-exit-pause",
         "--language", "0", tp2, *options],
        cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, check=False,
    )
    return result.stdout + result.stderr


def active_components(root: Path) -> list[tuple[str, int]]:
    log = root / "WeiDU.log"
    if not log.exists():
        return []
    rows = []
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"~([^~]+)~\s+#\d+\s+#(\d+)", line)
        if match and not line.startswith("//"):
            rows.append((match[1].upper().replace("\\", "/"), int(match[2])))
    return rows
