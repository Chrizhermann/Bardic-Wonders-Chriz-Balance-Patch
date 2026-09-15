"""Validate release versions and parse every shipped installer library."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAIN_VERSION = "v2.9c-balance.5"
TAIL_VERSION = "1.1.0"


def main() -> None:
    main_tp2 = ROOT / "BardicWonders/Setup-BardicWonders.tp2"
    tail_tp2 = ROOT / "live-patch/abettor-hla/Setup-AbettorHLARebalance.tp2"
    for path, expected in ((main_tp2, MAIN_VERSION), (tail_tp2, TAIL_VERSION)):
        match = re.search(r"^VERSION ~([^~]+)~", path.read_text(), re.MULTILINE)
        if match is None or match[1] != expected:
            raise SystemExit(f"Version mismatch in {path.relative_to(ROOT)}")
    if os.environ.get("GITHUB_REF_TYPE") == "tag":
        if os.environ.get("GITHUB_REF_NAME") != MAIN_VERSION:
            raise SystemExit("Main TP2 version does not match the release tag")
    files = [main_tp2, tail_tp2]
    files += sorted((ROOT / "BardicWonders/lib").glob("*.tpa"))
    files += sorted((ROOT / "live-patch/abettor-hla/abettor-hla-rebalance/lib").glob("*.tpa"))
    with tempfile.TemporaryDirectory(prefix="bardic-parse-") as directory:
        for path in files:
            result = subprocess.run(
                [str(ROOT / "Setup-BardicWonders.exe"), "--no-auto-tp2", "--noautoupdate",
                 "--no-exit-pause", "--nogame", "--parse-check", path.suffix[1:].upper(),
                 str(path), "--log", str(Path(directory) / "parse.log")],
                cwd=directory, text=True, capture_output=True, check=False, timeout=30,
            )
            if result.returncode:
                raise SystemExit(f"Parse failed: {path.relative_to(ROOT)}\n{result.stdout}\n{result.stderr}")
    print(f"INSTALLER_VERIFICATION=PASS versions={MAIN_VERSION}/{TAIL_VERSION} syntax_checks={len(files)}")


if __name__ == "__main__":
    main()
