from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct


SPL_HEADER_SIZE = 0x72
SPL_ABILITY_SIZE = 0x28
SPL_EFFECT_SIZE = 0x30


@dataclass(frozen=True)
class Effect:
    opcode: int
    target: int
    power: int
    parameter1: int
    parameter2: int
    timing: int
    resist_dispel: int
    duration: int
    probability1: int
    probability2: int
    resource: str
    dice_count: int
    dice_size: int
    save_type: int
    save_bonus: int
    special: int

    def matches(self, **fields: int | str) -> bool:
        return all(getattr(self, name) == value for name, value in fields.items())


@dataclass(frozen=True)
class Ability:
    target: int
    range: int
    required_level: int
    projectile: int
    effects: tuple[Effect, ...]


@dataclass(frozen=True)
class Spell:
    spell_type: int
    abilities: tuple[Ability, ...]

    @property
    def effects(self) -> tuple[Effect, ...]:
        return tuple(effect for ability in self.abilities for effect in ability.effects)

    def find_effects(self, **fields: int | str) -> tuple[Effect, ...]:
        return tuple(effect for effect in self.effects if effect.matches(**fields))


def _resref(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii").upper()


def _effect(data: bytes, offset: int) -> Effect:
    return Effect(
        opcode=struct.unpack_from("<H", data, offset)[0],
        target=data[offset + 0x02],
        power=data[offset + 0x03],
        parameter1=struct.unpack_from("<i", data, offset + 0x04)[0],
        parameter2=struct.unpack_from("<i", data, offset + 0x08)[0],
        timing=data[offset + 0x0C],
        resist_dispel=data[offset + 0x0D],
        duration=struct.unpack_from("<I", data, offset + 0x0E)[0],
        probability1=data[offset + 0x12],
        probability2=data[offset + 0x13],
        resource=_resref(data[offset + 0x14 : offset + 0x1C]),
        dice_count=struct.unpack_from("<I", data, offset + 0x1C)[0],
        dice_size=struct.unpack_from("<I", data, offset + 0x20)[0],
        save_type=struct.unpack_from("<I", data, offset + 0x24)[0],
        save_bonus=struct.unpack_from("<i", data, offset + 0x28)[0],
        special=struct.unpack_from("<I", data, offset + 0x2C)[0],
    )


def parse_spl(path: Path) -> Spell:
    data = path.read_bytes()
    if len(data) < SPL_HEADER_SIZE or data[:8] != b"SPL V1  ":
        raise ValueError(f"not an SPL V1 resource: {path}")

    ability_offset = struct.unpack_from("<I", data, 0x64)[0]
    ability_count = struct.unpack_from("<H", data, 0x68)[0]
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]

    if ability_offset + ability_count * SPL_ABILITY_SIZE > len(data):
        raise ValueError(f"ability table exceeds file: {path}")

    abilities: list[Ability] = []
    for index in range(ability_count):
        offset = ability_offset + index * SPL_ABILITY_SIZE
        effect_count = struct.unpack_from("<H", data, offset + 0x1E)[0]
        first_effect = struct.unpack_from("<H", data, offset + 0x20)[0]
        end = effect_offset + (first_effect + effect_count) * SPL_EFFECT_SIZE
        if end > len(data):
            raise ValueError(f"effect table exceeds file: {path}")

        effects = tuple(
            _effect(data, effect_offset + effect_index * SPL_EFFECT_SIZE)
            for effect_index in range(first_effect, first_effect + effect_count)
        )
        abilities.append(
            Ability(
                target=data[offset + 0x0C],
                range=struct.unpack_from("<H", data, offset + 0x0E)[0],
                required_level=struct.unpack_from("<H", data, offset + 0x10)[0],
                projectile=struct.unpack_from("<H", data, offset + 0x26)[0],
                effects=effects,
            )
        )

    return Spell(
        spell_type=struct.unpack_from("<H", data, 0x1C)[0],
        abilities=tuple(abilities),
    )


def read_eff_resource(path: Path) -> str:
    data = path.read_bytes()
    if (
        len(data) < 0x38
        or data[:8] != b"EFF V2.0"
        or data[0x08:0x10] != b"EFF V2.0"
    ):
        raise ValueError(f"not an EFF V2 resource: {path}")
    raw_resource = data[0x30:0x38]
    prefix, separator, padding = raw_resource.partition(b"\0")
    if separator and any(padding):
        raise ValueError(f"EFF has non-NUL resource padding: {path}")
    try:
        resource = prefix.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError(f"EFF has a non-ASCII resource field: {path}") from error
    if re.fullmatch(r"[A-Za-z0-9_#@-]{1,8}", resource) is None:
        raise ValueError(f"EFF has an invalid resource field: {path}")
    return resource.upper()
