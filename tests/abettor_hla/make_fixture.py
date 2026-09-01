from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import shutil
import sys

from .ie_resources import read_eff_resource


ROOT = Path(__file__).resolve().parents[2]
TAIL_ROOT = ROOT / "live-patch" / "abettor-hla"
WEIDU = ROOT / "Setup-BardicWonders.exe"
FIXTURE_SENTINEL = ".abettor-hla-disposable-fixture"
FIXTURE_SENTINEL_CONTENT = "abettor-hla-disposable-fixture-v1\n"
RESERVED_OUTPUTS = ("C0ABIVI.SPL", "C0ABIVS.EFF", "C0ABIVE.EFF")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def component_ids(path: Path) -> list[dict[str, int | str]]:
    pattern = re.compile(r"^~([^~]+)~\s+#(\d+)\s+#(\d+)")
    entries: list[dict[str, int | str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            entries.append(
                {
                    "tp2": match.group(1).upper(),
                    "language": int(match.group(2)),
                    "component": int(match.group(3)),
                }
            )
    return entries


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def build_fixture(source: Path, destination: Path) -> dict[str, object]:
    source = source.resolve()
    destination = destination.resolve()
    if destination == source or source in destination.parents:
        raise RuntimeError("destination must be outside the source game directory")
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    override = destination / "override"
    override.mkdir()

    source_override = source / "override"
    collisions = [name for name in RESERVED_OUTPUTS if (source_override / name).exists()]
    if collisions:
        raise RuntimeError(
            "reserved Abettor output already exists in source: " + ", ".join(collisions)
        )
    pointer = require_file(source_override / "C0ABETS2.EFF")
    payload_resref = read_eff_resource(pointer)
    resource_names = (
        "C0ABETS2.SPL",
        "C0ABETS2.EFF",
        f"{payload_resref}.SPL",
        f"{payload_resref}.EFF",
        "C0ABETHL.SPL",
        "C0SINGIN.SPL",
        "C0SINGIN.EFF",
        "C0SINGI2.EFF",
    )

    source_files: list[Path] = []
    for name in resource_names:
        path = require_file(source_override / name)
        source_files.append(path)
        shutil.copy2(path, override / name)

    tlk_candidates = (
        source / "lang" / "en_US" / "dialog.tlk",
        source / "dialog.tlk",
    )
    tlk_source = next((path for path in tlk_candidates if path.is_file()), None)
    if tlk_source is None:
        raise FileNotFoundError("dialog.tlk was not found in lang/en_US or the game root")
    log_source = require_file(source / "WeiDU.log")
    shutil.copy2(tlk_source, destination / "dialog.tlk")
    shutil.copy2(log_source, destination / "WeiDU.log")

    shutil.copy2(require_file(TAIL_ROOT / "Setup-AbettorHLARebalance.tp2"), destination)
    shutil.copytree(
        require_file(TAIL_ROOT / "abettor-hla-rebalance" / "lib" / "patch.tpa").parents[1],
        destination / "abettor-hla-rebalance",
    )
    shutil.copy2(require_file(WEIDU), destination / "Setup-AbettorHLARebalance.exe")
    (destination / FIXTURE_SENTINEL).write_text(
        FIXTURE_SENTINEL_CONTENT,
        encoding="ascii",
    )

    fixture_inputs = (
        *(override / name for name in resource_names),
        destination / "dialog.tlk",
        destination / "WeiDU.log",
    )

    manifest: dict[str, object] = {
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "payloadResref": payload_resref,
        "sourceHashes": {
            str(path.relative_to(source)): sha256(path)
            for path in (*source_files, tlk_source, log_source)
        },
        "components": component_ids(log_source),
        "fixtureHashes": {
            str(path.relative_to(destination)): sha256(path) for path in fixture_inputs
        },
    }
    (destination / "fixture-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Copy the Abettor resources into an isolated WeiDU fixture.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = build_fixture(args.source, args.destination)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"FIXTURE_BUILD=FAIL: {error}", file=sys.stderr)
        return 1
    print(f"FIXTURE_BUILD=PASS payload={manifest['payloadResref']} destination={args.destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
