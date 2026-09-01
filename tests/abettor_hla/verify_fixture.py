from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess
import sys

from .ie_resources import parse_spl, read_eff_resource
from .make_fixture import FIXTURE_SENTINEL, FIXTURE_SENTINEL_CONTENT


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def component_ids(path: Path) -> list[tuple[str, int, int]]:
    pattern = re.compile(r"^~([^~]+)~\s+#(\d+)\s+#(\d+)")
    entries: list[tuple[str, int, int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            entries.append((match.group(1).upper(), int(match.group(2)), int(match.group(3))))
    return entries


def tlk_string(path: Path, strref: int) -> str:
    data = path.read_bytes()
    if data[:8] != b"TLK V1  ":
        raise AssertionError("invalid TLK signature")
    count = struct.unpack_from("<I", data, 0x0A)[0]
    data_offset = struct.unpack_from("<I", data, 0x0E)[0]
    if not 0 <= strref < count:
        raise AssertionError(f"invalid description strref {strref}; TLK has {count} entries")
    entry = 0x12 + strref * 0x1A
    offset = struct.unpack_from("<I", data, entry + 0x12)[0]
    length = struct.unpack_from("<I", data, entry + 0x16)[0]
    return data[data_offset + offset : data_offset + offset + length].decode("utf-8")


def tlk_entries(path: Path) -> list[tuple[int, bytes, int, int, str]]:
    data = path.read_bytes()
    if data[:8] != b"TLK V1  ":
        raise AssertionError("invalid TLK signature")
    count = struct.unpack_from("<I", data, 0x0A)[0]
    entries: list[tuple[int, bytes, int, int, str]] = []
    for index in range(count):
        offset = 0x12 + index * 0x1A
        entries.append(
            (
                struct.unpack_from("<H", data, offset)[0],
                data[offset + 0x02 : offset + 0x0A],
                struct.unpack_from("<I", data, offset + 0x0A)[0],
                struct.unpack_from("<I", data, offset + 0x0E)[0],
                tlk_string(path, index),
            )
        )
    return entries


def run_weidu(fixture: Path, operation: str) -> subprocess.CompletedProcess[str]:
    switch = "--force-install" if operation == "install" else "--force-uninstall"
    return subprocess.run(
        [
            str(fixture / "Setup-AbettorHLARebalance.exe"),
            "--no-auto-tp2",
            "--noautoupdate",
            "--nogame",
            "--search",
            "override",
            "--tlkin",
            "dialog.tlk",
            "--tlkout",
            "dialog.tlk",
            "--no-exit-pause",
            "--language",
            "0",
            switch,
            "0",
            "Setup-AbettorHLARebalance.tp2",
        ],
        cwd=fixture,
        text=True,
        capture_output=True,
        check=False,
    )


def exact_effect(
    opcode: int,
    target: int,
    *,
    parameter1: int = 0,
    parameter2: int = 0,
    timing: int = 0,
    duration: int = 6,
    probability1: int = 100,
    resource: str = "",
    special: int = 0,
) -> dict[str, int | str]:
    return {
        "opcode": opcode,
        "target": target,
        "power": 0,
        "parameter1": parameter1,
        "parameter2": parameter2,
        "timing": timing,
        "resist_dispel": 0,
        "duration": duration,
        "probability1": probability1,
        "probability2": 0,
        "resource": resource,
        "dice_count": 0,
        "dice_size": 0,
        "save_type": 0,
        "save_bonus": 0,
        "special": special,
    }


def validate_installed(fixture: Path, payload_resref: str, marker_counts: tuple[int, int]) -> None:
    override = fixture / "override"
    if read_eff_resource(override / "C0ABETS2.EFF") != payload_resref:
        raise AssertionError("dynamic payload pointer changed")

    payload = parse_spl(override / f"{payload_resref}.SPL")
    for opcode in (92, 91, 90, 275, 59, 276, 277):
        if len(payload.find_effects(**exact_effect(opcode, 2, parameter1=70))) != 1:
            raise AssertionError(f"skill opcode {opcode} is not exactly +70")
    retained = (
        exact_effect(150, 2),
        exact_effect(65, 2),
        exact_effect(0, 2, parameter1=3),
        exact_effect(69, 2),
        exact_effect(20, 1, parameter2=1),
        exact_effect(142, 2, parameter2=40),
        exact_effect(142, 2, parameter2=58),
        exact_effect(142, 2, parameter2=31),
        exact_effect(215, 2, parameter2=1, duration=8, resource="C0ABETT1"),
    )
    for fields in retained:
        if len(payload.find_effects(**fields)) != 1:
            raise AssertionError(f"retained payload effect is not exact: {fields}")
    for opcode in (33, 34, 35, 36, 37):
        family = payload.find_effects(
            opcode=opcode,
            target=2,
            power=0,
            parameter2=0,
            timing=0,
            duration=6,
            probability1=100,
            probability2=0,
            resource="",
        )
        if len(family) != 1 or not family[0].matches(**exact_effect(opcode, 2, parameter1=1)):
            raise AssertionError(f"save opcode {opcode} is not exactly +1")
    forbidden_families = (
        {"opcode": 22, "target": 1, "power": 0, "parameter2": 0, "timing": 0,
         "duration": 6, "probability1": 100, "probability2": 0, "resource": ""},
        {"opcode": 250, "target": 1, "power": 0, "parameter2": 0, "timing": 0,
         "duration": 6, "probability1": 100, "probability2": 0, "resource": ""},
        {"opcode": 219, "target": 1, "power": 0, "parameter2": 8, "timing": 0,
         "duration": 6, "probability1": 100, "probability2": 0, "resource": ""},
        {"opcode": 292, "target": 1, "power": 0, "parameter1": 0, "timing": 0,
         "duration": 6, "probability1": 100, "probability2": 0, "resource": ""},
        {"opcode": 146, "target": 1, "resource": "SPSD02"},
    )
    for fields in forbidden_families:
        if payload.find_effects(**fields):
            raise AssertionError(f"forbidden payload effect family remains: {fields}")
    removed_exact = (
        exact_effect(0, 1, parameter1=4),
        exact_effect(0, 1, parameter1=4, parameter2=2),
        exact_effect(20, 1, duration=12, probability1=20),
    )
    for fields in removed_exact:
        if payload.find_effects(**fields):
            raise AssertionError(f"removed payload effect remains: {fields}")
    if len(payload.find_effects(opcode=326, resource="C0BSNGEF")) != marker_counts[0]:
        raise AssertionError("C0BSNGEF count changed")

    hla = parse_spl(override / "C0ABETHL.SPL")
    if len(hla.find_effects(opcode=309, resource="C0BWHLAB")) != marker_counts[1]:
        raise AssertionError("C0BWHLAB count changed")

    controller = parse_spl(override / "C0ABETS2.SPL")
    for index, ability in enumerate(controller.abilities):
        start_hooks = [
            effect
            for effect in ability.effects
            if effect.matches(
                opcode=177,
                target=9,
                power=0,
                parameter1=0,
                parameter2=2,
                timing=1,
                duration=0,
                probability1=100,
                probability2=0,
                resource="C0ABIVS",
                dice_count=0,
                dice_size=0,
                save_type=0,
                save_bonus=0,
                special=0,
            )
        ]
        end_hooks = [
            effect
            for effect in ability.effects
            if effect.matches(
                opcode=272,
                target=9,
                power=0,
                parameter1=6,
                parameter2=3,
                timing=10,
                probability1=100,
                probability2=0,
                resource="C0ABIVE",
                dice_count=0,
                dice_size=0,
                save_type=0,
                save_bonus=0,
                special=40,
            )
            and effect.duration > 0
        ]
        if len(start_hooks) != 1:
            raise AssertionError(f"controller header {index} lacks exactly one start hook")
        if len(end_hooks) != 1:
            raise AssertionError(f"controller header {index} lacks exactly one end hook")

    invisibility = parse_spl(override / "C0ABIVI.SPL")
    invisibility_ability = invisibility.abilities[0]
    payload_projectile = payload.abilities[0].projectile
    if (
        invisibility.spell_type != 5
        or len(invisibility.abilities) != 1
        or invisibility_ability.target != 5
        or invisibility_ability.range != 50
        or invisibility_ability.projectile != 158
        or invisibility_ability.projectile != payload_projectile
    ):
        raise AssertionError("C0ABIVI does not use the validated party delivery header")
    if len(invisibility.effects) != 1 or not invisibility.effects[0].matches(
        opcode=20,
        target=2,
        power=0,
        parameter1=0,
        parameter2=0,
        timing=0,
        resist_dispel=0,
        duration=6,
        probability1=100,
        probability2=0,
        resource="",
        dice_count=0,
        dice_size=0,
        save_type=0,
        save_bonus=0,
        special=0,
    ):
        raise AssertionError("C0ABIVI is not one round of ordinary party Invisibility")

    hla_data = (override / "C0ABETHL.SPL").read_bytes()
    description = tlk_string(fixture / "dialog.tlk", struct.unpack_from("<I", hla_data, 0x50)[0])
    for phrase in ("one round when the song begins", "one round when the song ends"):
        if phrase not in description:
            raise AssertionError(f"description lacks: {phrase}")


def verify(fixture: Path) -> None:
    fixture = fixture.resolve()
    sentinel = fixture / FIXTURE_SENTINEL
    if not sentinel.is_file() or sentinel.read_text(encoding="ascii") != FIXTURE_SENTINEL_CONTENT:
        raise AssertionError("directory is not a generated disposable Abettor fixture")
    for marker in ("chitin.key", "Baldur.exe", "InfinityLoader.exe"):
        if (fixture / marker).exists():
            raise AssertionError(f"refusing game-like fixture directory containing {marker}")
    manifest = json.loads((fixture / "fixture-manifest.json").read_text(encoding="utf-8"))
    if Path(str(manifest["source"])).resolve() == fixture:
        raise AssertionError("fixture path resolves to the recorded source game")
    payload_resref = str(manifest["payloadResref"])
    override = fixture / "override"
    for relative, expected_hash in dict(manifest["fixtureHashes"]).items():
        path = fixture / str(relative)
        if not path.is_file() or sha256(path) != expected_hash:
            raise AssertionError(f"fixture input drifted since creation: {relative}")
    manifest_components = [
        (str(entry["tp2"]), int(entry["language"]), int(entry["component"]))
        for entry in list(manifest["components"])
    ]
    if component_ids(fixture / "WeiDU.log") != manifest_components:
        raise AssertionError("fixture component order drifted since creation")
    tracked = (
        override / "C0ABETS2.SPL",
        override / "C0ABETS2.EFF",
        override / f"{payload_resref}.SPL",
        override / f"{payload_resref}.EFF",
        override / "C0ABETHL.SPL",
    )
    before_hashes = {path: sha256(path) for path in tracked}
    before_components = component_ids(fixture / "WeiDU.log")
    before_tlk_entries = tlk_entries(fixture / "dialog.tlk")
    before_payload = parse_spl(override / f"{payload_resref}.SPL")
    before_hla = parse_spl(override / "C0ABETHL.SPL")
    marker_counts = (
        len(before_payload.find_effects(opcode=326, resource="C0BSNGEF")),
        len(before_hla.find_effects(opcode=309, resource="C0BWHLAB")),
    )

    install = run_weidu(fixture, "install")
    if install.returncode != 0:
        raise AssertionError(f"install failed ({install.returncode})\n{install.stdout}\n{install.stderr}")

    validation_error: BaseException | None = None
    try:
        validate_installed(fixture, payload_resref, marker_counts)
        if tlk_entries(fixture / "dialog.tlk")[: len(before_tlk_entries)] != before_tlk_entries:
            raise AssertionError("install changed a pre-existing TLK entry")
        installed_components = component_ids(fixture / "WeiDU.log")
        if installed_components[:-1] != before_components:
            raise AssertionError("prior WeiDU component order changed during install")
        if "SETUP-ABETTORHLAREBALANCE.TP2" not in installed_components[-1][0]:
            raise AssertionError("tail component was not appended last")
    except BaseException as error:
        validation_error = error

    uninstall = run_weidu(fixture, "uninstall")
    if uninstall.returncode != 0:
        raise AssertionError(
            f"uninstall failed ({uninstall.returncode})\n{uninstall.stdout}\n{uninstall.stderr}"
        )

    for path, expected_hash in before_hashes.items():
        if sha256(path) != expected_hash:
            raise AssertionError(f"uninstall did not restore exact hash: {path.name}")
    if tlk_entries(fixture / "dialog.tlk")[: len(before_tlk_entries)] != before_tlk_entries:
        raise AssertionError("uninstall did not restore all pre-existing TLK entries")
    for name in ("C0ABIVI.SPL", "C0ABIVS.EFF", "C0ABIVE.EFF"):
        if (override / name).exists():
            raise AssertionError(f"uninstall left a generated resource behind: {name}")
    if component_ids(fixture / "WeiDU.log") != before_components:
        raise AssertionError("uninstall did not restore prior WeiDU component order")
    if validation_error is not None:
        raise validation_error


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Install, inspect, and uninstall the tail patch in a fixture.")
    parser.add_argument("--fixture", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        verify(args.fixture)
    except (OSError, ValueError, AssertionError, KeyError, json.JSONDecodeError) as error:
        print(f"DISPOSABLE_FIXTURE_VERIFICATION=FAIL: {error}", file=sys.stderr)
        return 1
    print("DISPOSABLE_FIXTURE_VERIFICATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
