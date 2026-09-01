#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import struct
import sys
import tempfile


ABILITY_SIZE = 0x28
EFFECT_SIZE = 0x30


class PatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Effect:
    raw: bytes
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

    def matches(self, fields: dict[str, int | str]) -> bool:
        return all(getattr(self, name) == value for name, value in fields.items())


SAVE_OPCODES = (33, 34, 35, 36, 37)

ZERO_EFFECT_TAIL = {
    "resist_dispel": 0,
    "dice_count": 0,
    "dice_size": 0,
    "save_type": 0,
    "save_bonus": 0,
    "special": 0,
}

COMMON_SONG_EFFECT = {
    "target": 2,
    "power": 0,
    "parameter2": 0,
    "timing": 0,
    "duration": 6,
    "probability1": 100,
    "probability2": 0,
    "resource": "",
    **ZERO_EFFECT_TAIL,
}

REMOVALS: tuple[tuple[int, dict[str, int | str]], ...] = (
    (
        1,
        {
            "opcode": 22,
            "target": 1,
            "power": 0,
            "parameter1": 6,
            "parameter2": 0,
            "timing": 0,
            "duration": 6,
            "probability1": 100,
            "probability2": 0,
            "resource": "",
        },
    ),
    (
        1,
        {
            "opcode": 250,
            "target": 1,
            "power": 0,
            "parameter1": 6,
            "parameter2": 0,
            "timing": 0,
            "duration": 6,
            "probability1": 100,
            "probability2": 0,
            "resource": "",
        },
    ),
    (
        1,
        {
            "opcode": 0,
            "target": 1,
            "power": 0,
            "parameter1": 4,
            "parameter2": 0,
            "timing": 0,
            "duration": 6,
            "probability1": 100,
            "probability2": 0,
            "resource": "",
        },
    ),
    (
        1,
        {
            "opcode": 0,
            "target": 1,
            "power": 0,
            "parameter1": 4,
            "parameter2": 2,
            "timing": 0,
            "duration": 6,
            "probability1": 100,
            "probability2": 0,
            "resource": "",
        },
    ),
    (
        2,
        {
            "opcode": 219,
            "target": 1,
            "power": 0,
            "parameter1": 1,
            "parameter2": 8,
            "timing": 0,
            "duration": 6,
            "probability1": 100,
            "probability2": 0,
            "resource": "",
        },
    ),
    (
        1,
        {
            "opcode": 292,
            "target": 1,
            "power": 0,
            "parameter1": 0,
            "parameter2": 1,
            "timing": 0,
            "duration": 6,
            "probability1": 100,
            "probability2": 0,
            "resource": "",
        },
    ),
    (
        1,
        {
            "opcode": 20,
            "target": 1,
            "power": 0,
            "parameter1": 0,
            "parameter2": 0,
            "timing": 0,
            "duration": 12,
            "probability1": 20,
            "probability2": 0,
            "resource": "",
        },
    ),
    (
        1,
        {
            "opcode": 146,
            "target": 1,
            "power": 0,
            "parameter1": 0,
            "parameter2": 1,
            "timing": 1,
            "duration": 0,
            "probability1": 5,
            "probability2": 0,
            "resource": "SPSD02",
        },
    ),
)
REMOVALS = tuple(
    (expected, {**fields, **ZERO_EFFECT_TAIL}) for expected, fields in REMOVALS
)

RETAINED: tuple[tuple[int, dict[str, int | str]], ...] = (
    (
        1,
        {
            "opcode": 321,
            "target": 2,
            "power": 0,
            "parameter1": 0,
            "parameter2": 0,
            "timing": 1,
            "duration": 0,
            "probability1": 100,
            "probability2": 0,
            "resource": "C0ABETS2",
        },
    ),
    (
        1,
        {
            "opcode": 215,
            "target": 2,
            "power": 0,
            "parameter1": 0,
            "parameter2": 1,
            "timing": 0,
            "duration": 8,
            "probability1": 100,
            "probability2": 0,
            "resource": "C0ABETT1",
        },
    ),
    *(
        (
            1,
            {
                "opcode": opcode,
                "parameter1": 70,
                **COMMON_SONG_EFFECT,
            },
        )
        for opcode in (92, 91, 90, 275, 59, 276, 277)
    ),
    *(
        (
            1,
            {
                "opcode": opcode,
                "parameter1": parameter1,
                **COMMON_SONG_EFFECT,
            },
        )
        for opcode, parameter1 in ((150, 0), (65, 0), (69, 0))
    ),
    (
        1,
        {
            "opcode": 0,
            "parameter1": 3,
            **COMMON_SONG_EFFECT,
        },
    ),
    (
        1,
        {
            "opcode": 20,
            "target": 1,
            "power": 0,
            "parameter1": 0,
            "parameter2": 1,
            "timing": 0,
            "duration": 6,
            "probability1": 100,
            "probability2": 0,
            "resource": "",
        },
    ),
    *(
        (
            1,
            {
                "opcode": 142,
                "target": 2,
                "power": 0,
                "parameter1": 0,
                "parameter2": icon,
                "timing": 0,
                "duration": 6,
                "probability1": 100,
                "probability2": 0,
                "resource": "",
            },
        )
        for icon in (40, 58, 31)
    ),
)
RETAINED = tuple(
    (expected, {**fields, **ZERO_EFFECT_TAIL}) for expected, fields in RETAINED
)


def _resref(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode("ascii").upper()


def _parse_effect(raw: bytes) -> Effect:
    return Effect(
        raw=raw,
        opcode=struct.unpack_from("<H", raw, 0x00)[0],
        target=raw[0x02],
        power=raw[0x03],
        parameter1=struct.unpack_from("<i", raw, 0x04)[0],
        parameter2=struct.unpack_from("<i", raw, 0x08)[0],
        timing=raw[0x0C],
        resist_dispel=raw[0x0D],
        duration=struct.unpack_from("<I", raw, 0x0E)[0],
        probability1=raw[0x12],
        probability2=raw[0x13],
        resource=_resref(raw[0x14:0x1C]),
        dice_count=struct.unpack_from("<I", raw, 0x1C)[0],
        dice_size=struct.unpack_from("<I", raw, 0x20)[0],
        save_type=struct.unpack_from("<I", raw, 0x24)[0],
        save_bonus=struct.unpack_from("<i", raw, 0x28)[0],
        special=struct.unpack_from("<I", raw, 0x2C)[0],
    )


def _save_fields(opcode: int, value: int) -> dict[str, int | str]:
    return {"opcode": opcode, "parameter1": value, **COMMON_SONG_EFFECT}


def _count(effects: list[Effect], fields: dict[str, int | str]) -> int:
    return sum(effect.matches(fields) for effect in effects)


def _retained_contract_is_valid(effects: list[Effect]) -> bool:
    return all(_count(effects, fields) == expected for expected, fields in RETAINED)


def _save_contract_is_valid(effects: list[Effect], value: int) -> bool:
    return all(
        _count(effects, _save_fields(opcode, value)) == 1
        and sum(
            effect.matches(
                {
                    "opcode": opcode,
                    "target": 2,
                    "power": 0,
                    "parameter2": 0,
                    "timing": 0,
                    "duration": 6,
                    "probability1": 100,
                    "probability2": 0,
                    "resource": "",
                }
            )
            for effect in effects
        )
        == 1
        for opcode in SAVE_OPCODES
    )


def _removed_families_are_valid(effects: list[Effect], *, old: bool) -> bool:
    expected_one = 1 if old else 0
    expected_good = 2 if old else 0
    return (
        sum(
            effect.matches(
                {
                    "opcode": 22,
                    "target": 1,
                    "power": 0,
                    "parameter2": 0,
                    "timing": 0,
                    "duration": 6,
                    "probability1": 100,
                    "probability2": 0,
                    "resource": "",
                }
            )
            for effect in effects
        )
        == expected_one
        and sum(
            effect.matches(
                {
                    "opcode": 250,
                    "target": 1,
                    "power": 0,
                    "parameter2": 0,
                    "timing": 0,
                    "duration": 6,
                    "probability1": 100,
                    "probability2": 0,
                    "resource": "",
                }
            )
            for effect in effects
        )
        == expected_one
        and sum(
            effect.matches(
                {
                    "opcode": 219,
                    "target": 1,
                    "power": 0,
                    "parameter2": 8,
                    "timing": 0,
                    "duration": 6,
                    "probability1": 100,
                    "probability2": 0,
                    "resource": "",
                }
            )
            for effect in effects
        )
        == expected_good
        and sum(
            effect.matches(
                {
                    "opcode": 292,
                    "target": 1,
                    "power": 0,
                    "parameter1": 0,
                    "timing": 0,
                    "duration": 6,
                    "probability1": 100,
                    "probability2": 0,
                    "resource": "",
                }
            )
            for effect in effects
        )
        == expected_one
        and sum(
            effect.matches({"opcode": 146, "target": 1, "resource": "SPSD02"})
            for effect in effects
        )
        == expected_one
    )


def _is_old_state(effects: list[Effect]) -> bool:
    return (
        _retained_contract_is_valid(effects)
        and _save_contract_is_valid(effects, 5)
        and _removed_families_are_valid(effects, old=True)
        and all(_count(effects, fields) == expected for expected, fields in REMOVALS)
    )


def _is_balanced_state(effects: list[Effect]) -> bool:
    return (
        _retained_contract_is_valid(effects)
        and _save_contract_is_valid(effects, 1)
        and _removed_families_are_valid(effects, old=False)
        and all(_count(effects, fields) == 0 for _, fields in REMOVALS)
    )


def patch_bytes(data: bytes) -> tuple[bytes, bool]:
    if len(data) < 0x72 or data[:8] != b"SPL V1  ":
        raise PatchError("resource is not SPL V1")

    ability_offset = struct.unpack_from("<I", data, 0x64)[0]
    ability_count = struct.unpack_from("<H", data, 0x68)[0]
    effect_offset = struct.unpack_from("<I", data, 0x6A)[0]
    global_effect_count = struct.unpack_from("<H", data, 0x70)[0]

    if ability_count != 1 or global_effect_count != 0:
        raise PatchError(
            f"expected one ability and no global effects, got {ability_count} abilities and "
            f"{global_effect_count} global effects"
        )
    if ability_offset + ABILITY_SIZE > len(data):
        raise PatchError("ability header exceeds file")

    first_effect = struct.unpack_from("<H", data, ability_offset + 0x20)[0]
    effect_count = struct.unpack_from("<H", data, ability_offset + 0x1E)[0]
    if first_effect != 0:
        raise PatchError(f"expected first ability effect index 0, got {first_effect}")

    effect_end = effect_offset + effect_count * EFFECT_SIZE
    if effect_end != len(data):
        raise PatchError("expected the ability effect table to end at end-of-file")

    effects = [
        _parse_effect(data[offset : offset + EFFECT_SIZE])
        for offset in range(effect_offset, effect_end, EFFECT_SIZE)
    ]

    old_state = _is_old_state(effects)
    balanced_state = _is_balanced_state(effects)
    if balanced_state and not old_state:
        return data, False
    if not old_state or balanced_state:
        raise PatchError("semantic effect contract is partial, ambiguous, or has drifted")

    rebuilt: list[bytes] = []
    for effect in effects:
        if any(effect.matches(fields) for _, fields in REMOVALS):
            continue

        raw = bytearray(effect.raw)
        if any(effect.matches(_save_fields(opcode, 5)) for opcode in SAVE_OPCODES):
            struct.pack_into("<i", raw, 0x04, 1)
        rebuilt.append(bytes(raw))

    output = bytearray(data[:effect_offset])
    output.extend(b"".join(rebuilt))
    struct.pack_into("<H", output, ability_offset + 0x1E, len(rebuilt))

    parsed_output = [
        _parse_effect(output[offset : offset + EFFECT_SIZE])
        for offset in range(effect_offset, len(output), EFFECT_SIZE)
    ]
    if not _is_balanced_state(parsed_output):
        raise PatchError("post-patch semantic contract did not validate")
    return bytes(output), True


def patch_file(path: Path) -> bool:
    original = path.read_bytes()
    patched, changed = patch_bytes(original)
    if not changed:
        return False

    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(patched)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} PATH_TO_C0ABETS2.SPL", file=sys.stderr)
        return 2

    path = Path(argv[1])
    try:
        changed = patch_file(path)
    except (OSError, UnicodeError, PatchError) as error:
        print(f"refusing to patch {path}: {error}", file=sys.stderr)
        return 1

    if changed:
        print(f"patched {path}")
    else:
        print(f"already balanced: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
