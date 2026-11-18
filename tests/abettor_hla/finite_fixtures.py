from __future__ import annotations

import struct

from .ie_resources import Ability, Effect
from .test_patcher import effect_bytes


def finale_delay(song_ticks: int) -> int:
    """Delayed effects count whole seconds and a song lasts ticks (15 per
    second); the finale waits for the song's last tick."""
    return -(-song_ticks // 15)


def song_ticks(ability: Ability, payload: str) -> int:
    return next(
        effect.duration
        for effect in ability.effects
        if effect.matches(opcode=272, timing=10, resource=payload)
    )


def is_finale(effect: Effect, song: int) -> bool:
    return effect.matches(
        opcode=326,
        target=9,
        power=0,
        parameter1=0,
        parameter2=0,
        timing=4,
        resist_dispel=0,
        duration=finale_delay(song),
        probability1=100,
        probability2=0,
        resource="C0ABIVI",
        dice_count=0,
        dice_size=0,
        save_type=0,
        save_bonus=0,
        special=0,
    )


def opening_effect() -> bytes:
    return effect_bytes(177, target=9, parameter2=2, timing=1, duration=0, resource="C0ABIVS")


def finale_effect(delay: int) -> bytes:
    return effect_bytes(326, target=9, timing=4, duration=delay, resource="C0ABIVI")


def controller_bytes(
    durations: tuple[int, ...] = (600, 700),
    *,
    payload_resource: str = "C0ABETS2",
    start_duration: int = 0,
    start_power: int = 0,
    start_special: int = 0,
    end_special: int = 40,
    first_global_opcode: int = 136,
    header_projectile: int = 559,
    start_probability: int = 100,
    extra_start_probability: int | None = None,
    extra_start_resist_dispel: int = 0,
    extra_start_dice_count: int = 0,
    extra_start_dice_size: int = 0,
    extra_start_save_type: int = 0,
    extra_start_resource: str = "C0SINGIN",
    extra_end_duration: int | None = None,
    extra_end_resist_dispel: int = 0,
    extra_end_resource: str = "C0SINGI2",
    extra_effects: tuple[bytes, ...] = (),
) -> bytes:
    ability_offset = 0x72
    global_effects = [
        effect_bytes(first_global_opcode, target=9, timing=1, duration=0),
        effect_bytes(
            146,
            target=9,
            parameter2=1,
            timing=1,
            duration=0,
            resource="C0BARDSX",
        ),
    ]
    effect_groups: list[list[bytes]] = []
    for duration in durations:
        effect_groups.append(
            [
                effect_bytes(138, target=9, parameter2=2, timing=1, duration=0),
                effect_bytes(
                    146,
                    target=9,
                    parameter2=0,
                    timing=1,
                    duration=0,
                    resource="C0BARDSX",
                ),
                effect_bytes(
                    177,
                    target=9,
                    power=start_power,
                    parameter2=2,
                    timing=10,
                    duration=duration,
                    resource=payload_resource,
                ),
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=duration,
                    resource=payload_resource,
                    special=end_special,
                ),
                effect_bytes(
                    177,
                    target=9,
                    parameter2=2,
                    timing=1,
                    duration=start_duration,
                    probability1=start_probability,
                    resource="C0SINGIN",
                    special=start_special,
                ),
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=duration,
                    resource="C0SINGIN",
                    special=end_special,
                ),
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=duration,
                    resource="C0SINGI2",
                    special=end_special,
                ),
                effect_bytes(
                    328,
                    target=9,
                    parameter2=85,
                    timing=10,
                    duration=duration,
                    resource=payload_resource,
                    special=1,
                ),
            ]
        )
        if extra_start_probability is not None:
            effect_groups[-1].append(
                effect_bytes(
                    177,
                    target=9,
                    parameter2=2,
                    timing=1,
                    duration=0,
                    probability1=extra_start_probability,
                    resource=extra_start_resource,
                    resist_dispel=extra_start_resist_dispel,
                    dice_count=extra_start_dice_count,
                    dice_size=extra_start_dice_size,
                    save_type=extra_start_save_type,
                )
            )
        if extra_end_duration is not None:
            effect_groups[-1].append(
                effect_bytes(
                    272,
                    target=9,
                    parameter1=6,
                    parameter2=3,
                    timing=10,
                    duration=extra_end_duration,
                    probability1=100,
                    resource=extra_end_resource,
                    resist_dispel=extra_end_resist_dispel,
                    special=40,
                )
            )
        effect_groups[-1].extend(extra_effects)

    effect_offset = ability_offset + len(effect_groups) * 0x28
    data = bytearray(effect_offset)
    data[:8] = b"SPL V1  "
    struct.pack_into("<H", data, 0x1C, 5)
    struct.pack_into("<I", data, 0x64, ability_offset)
    struct.pack_into("<H", data, 0x68, len(effect_groups))
    struct.pack_into("<I", data, 0x6A, effect_offset)
    struct.pack_into("<H", data, 0x6E, 0)
    struct.pack_into("<H", data, 0x70, len(global_effects))

    first_effect = len(global_effects)
    for index, effects in enumerate(effect_groups):
        offset = ability_offset + index * 0x28
        data[offset] = 1
        data[offset + 0x02] = 4
        data[offset + 0x0C] = 1
        struct.pack_into("<H", data, offset + 0x0E, 1)
        struct.pack_into("<H", data, offset + 0x10, index + 1)
        struct.pack_into("<H", data, offset + 0x1C, 1)
        struct.pack_into("<H", data, offset + 0x1E, len(effects))
        struct.pack_into("<H", data, offset + 0x20, first_effect)
        struct.pack_into("<H", data, offset + 0x22, 1)
        struct.pack_into("<H", data, offset + 0x24, 1)
        struct.pack_into("<H", data, offset + 0x26, header_projectile)
        first_effect += len(effects)

    return (
        bytes(data)
        + b"".join(global_effects)
        + b"".join(effect for group in effect_groups for effect in group)
    )


HLA_TABLE = """2DA V1.0
*
           ABILITY       ICON  STRREF  MIN_LEV  MAX_LEVEL  NUM_ALLOWED  PREREQUISITE  EXCLUDED_BY
C0ABET1    AP_C0ABETT5    *     *       1        99         1            *             *
C0ABET2    AP_C0ABETHL    *     *       1        99         1            AP_C0ABETT5   *
"""
