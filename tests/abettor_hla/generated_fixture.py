"""Generated-song fixtures built from the shipped controller and payload resources."""
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]


def generated_resources(root: Path, payload: str, projectile: int = 444, display_strref: int = 1234) -> None:
    override = root / "override"
    controller = bytearray((ROOT / "BardicWonders/bardsong/c0bardso.spl").read_bytes())
    ability_offset, count, effect_offset = struct.unpack_from("<IHI", controller, 0x64)
    for index in range(count):
        header = ability_offset + 40 * index
        struct.pack_into("<H", controller, header + 0x26, projectile)
    # These are exactly the substitutions made by component 2004 after it
    # obtains a unique song name and registers the C0BARDSO projectile.
    for offset in range(effect_offset, len(controller), 48):
        if controller[offset + 20:offset + 28].rstrip(b"\0").upper() == b"BARDSONG":
            controller[offset + 20:offset + 28] = payload.encode().ljust(8, b"\0")
    (override / "C0ABETS2.SPL").write_bytes(controller)
    song = bytearray((ROOT / "BardicWonders/abettor/c0abets2.spl").read_bytes())
    effect_offset = struct.unpack_from("<I", song, 0x6A)[0]
    for offset in range(effect_offset, len(song), 48):
        if song[offset + 20:offset + 28].rstrip(b"\0").upper() == b"C0ABETS2":
            song[offset + 20:offset + 28] = payload.encode().ljust(8, b"\0")
    (override / f"{payload}.SPL").write_bytes(song)
    template = bytearray((override / "C0SINGIN.SPL").read_bytes())
    effect_offset = struct.unpack_from("<I", template, 0x6A)[0]
    for offset in range(effect_offset, len(template), 48):
        if struct.unpack_from("<H", template, offset)[0] == 139:
            struct.pack_into("<i", template, offset + 4, display_strref)
    (override / "C0SINGIN.SPL").write_bytes(template)
    (override / "C0ABETS2.EFF").unlink()
    (override / "PROJECTL.IDS").write_text(f"IDS V1.0\n{projectile - 1} C0BARDSO\n")
