#!/usr/bin/env python3
"""openkobo build tool.

Applies the symbol-keyed patches in patches/libnickel.toml to the copy of
libnickel.so.1.0.0 inside an official Kobo firmware update, and repacks a
minimal KoboRoot.tgz that installs over the stock firmware.

The device applies the result exactly like a stock update: rcS extracts
.kobo/KoboRoot.tgz onto / with no signature check. Reverting is just
reinstalling the official update zip for the device.

Nothing from Kobo ships in this repository; you supply the official update.

Usage:
    python3 -I tools/openkobo.py build  --zip kobo-update-4.38.23852.zip \\
                                        --profile offline --out out/
    python3 -I tools/openkobo.py inspect --zip kobo-update-4.38.23852.zip

`inspect` resolves every patch symbol and prints its offset and current
prologue bytes, which is how you port the patch set to a new firmware build.

Run with `-I` so the untrusted firmware directory can never inject a module.
Standard library only (tomllib needs Python 3.11+).
"""

import argparse
import hashlib
import io
import struct
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

# ----------------------------------------------------------------------------
# Thumb-2 stub encodings
# ----------------------------------------------------------------------------

STATIC_STUBS = {
    # mnemonic           bytes (little-endian)   effect
    "return_void":  b"\x70\x47",                 # bx lr
    "return_false": b"\x00\x20\x70\x47",          # movs r0,#0 ; bx lr
    "return_true":  b"\x01\x20\x70\x47",          # movs r0,#1 ; bx lr
}


def encode_b_w(src_vaddr: int, dst_vaddr: int) -> bytes:
    """Encode a Thumb-2 `B.W dst` (T4) placed at src_vaddr.

    A plain branch (not BL/BLX) stays in Thumb state and leaves lr and the
    argument registers untouched, so it tail-calls dst with the same `this`
    pointer and returns straight to the original caller.
    """
    off = dst_vaddr - (src_vaddr + 4)
    if off & 1:
        raise ValueError("branch offset is odd")
    if not -(1 << 24) <= off < (1 << 24):
        raise ValueError(f"B.W target out of range ({off:#x})")
    s = (off >> 24) & 1
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    imm10 = (off >> 12) & 0x3FF
    imm11 = (off >> 1) & 0x7FF
    j1 = 1 ^ i1 ^ s               # I1 = NOT(J1 EOR S)
    j2 = 1 ^ i2 ^ s
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


# ----------------------------------------------------------------------------
# Minimal ELF32 (little-endian ARM) reader: just the dynamic symbol table
# ----------------------------------------------------------------------------

STT_FUNC = 2


class Sym:
    __slots__ = ("name", "vaddr", "file_off", "size", "is_thumb")

    def __init__(self, name, vaddr, file_off, size, is_thumb):
        self.name = name
        self.vaddr = vaddr          # entry with the Thumb bit cleared
        self.file_off = file_off    # offset of that entry in the file
        self.size = size
        self.is_thumb = is_thumb


class Elf32:
    def __init__(self, data: bytes):
        if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
            raise ValueError("not a little-endian 32-bit ELF")
        self.data = bytearray(data)
        (self.e_type, self.e_machine, _ver, self.e_entry, self.e_phoff,
         self.e_shoff, _flags, _ehsize, self.e_phentsize, self.e_phnum,
         self.e_shentsize, self.e_shnum, _shstrndx) = struct.unpack_from(
            "<HHIIIIIHHHHHH", data, 16)
        if self.e_machine != 40:  # EM_ARM
            raise ValueError("not an ARM ELF")
        self._loads = self._read_loads()
        self.funcs = self._read_dynsyms()

    def _read_loads(self):
        loads = []
        for i in range(self.e_phnum):
            base = self.e_phoff + i * self.e_phentsize
            p_type, p_off, p_vaddr, _pa, p_filesz, _ms, _fl, _al = \
                struct.unpack_from("<IIIIIIII", self.data, base)
            if p_type == 1:  # PT_LOAD
                loads.append((p_vaddr, p_off, p_filesz))
        return loads

    def vaddr_to_off(self, vaddr: int) -> int:
        for p_vaddr, p_off, p_filesz in self._loads:
            if p_vaddr <= vaddr < p_vaddr + p_filesz:
                return vaddr - p_vaddr + p_off
        raise ValueError(f"vaddr {vaddr:#x} is in no PT_LOAD segment")

    def _sections(self):
        for i in range(self.e_shnum):
            base = self.e_shoff + i * self.e_shentsize
            yield struct.unpack_from("<IIIIIIIIII", self.data, base)

    def _read_dynsyms(self):
        secs = list(self._sections())
        dynsym = next((s for s in secs if s[1] == 11), None)  # SHT_DYNSYM
        if dynsym is None:
            raise ValueError("no .dynsym section")
        _n, _t, _f, _a, sym_off, sym_sz, strtab_idx, _i, _al, entsz = dynsym
        str_off, str_sz = secs[strtab_idx][4], secs[strtab_idx][5]
        strtab = self.data[str_off:str_off + str_sz]
        funcs = {}
        for off in range(sym_off, sym_off + sym_sz, entsz or 16):
            st_name, st_value, st_size, st_info, _other, st_shndx = \
                struct.unpack_from("<IIIBBH", self.data, off)
            if st_shndx == 0 or (st_info & 0xF) != STT_FUNC:
                continue
            end = strtab.index(b"\0", st_name)
            name = strtab[st_name:end].decode("latin1")
            is_thumb = bool(st_value & 1)
            vaddr = st_value & ~1
            funcs[name] = Sym(name, vaddr, self.vaddr_to_off(vaddr),
                              st_size, is_thumb)
        return funcs


# ----------------------------------------------------------------------------
# Patch application
# ----------------------------------------------------------------------------

class PatchError(Exception):
    pass


def build_stub(patch, elf: Elf32, site: Sym) -> bytes:
    kind = patch["stub"]
    if kind in STATIC_STUBS:
        return STATIC_STUBS[kind]
    if kind.startswith("tailcall:"):
        target_name = kind.split(":", 1)[1]
        target = elf.funcs.get(target_name)
        if target is None:
            raise PatchError(f"tail-call target {target_name} not found")
        return encode_b_w(site.vaddr, target.vaddr)
    raise PatchError(f"unknown stub kind {kind!r}")


def apply_patches(elf: Elf32, spec: dict, profile: str, only, skip):
    """Patch elf.data in place. Returns a list of per-patch result rows."""
    rows = []
    for patch in spec["patch"]:
        pid, group = patch["id"], patch["group"]
        if profile not in patch.get("profiles", []):
            rows.append((pid, group, "skip", "not in profile"))
            continue
        if only and group not in only:
            rows.append((pid, group, "skip", "not in --only"))
            continue
        if skip and group in skip:
            rows.append((pid, group, "skip", "in --skip"))
            continue

        site = elf.funcs.get(patch["symbol"])
        if site is None:
            raise PatchError(f"{pid}: symbol not found: {patch['symbol']}")
        if not site.is_thumb:
            raise PatchError(f"{pid}: {patch['symbol']} is not a Thumb function")

        stub = build_stub(patch, elf, site)
        if site.size and site.size < len(stub):
            raise PatchError(f"{pid}: function too small for stub")

        here = elf.data[site.file_off:site.file_off + len(stub)]
        if here == stub:
            rows.append((pid, group, "ok", "already patched"))
            continue
        elf.data[site.file_off:site.file_off + len(stub)] = stub
        rows.append((pid, group, "patched",
                     f"@{site.file_off:#x} {here.hex()} -> {stub.hex()}"))
    return rows


# ----------------------------------------------------------------------------
# Firmware container handling
# ----------------------------------------------------------------------------

def read_member(zip_path: Path, member: str):
    """Return (bytes, TarInfo) for `member` inside the zip's KoboRoot.tgz."""
    with zipfile.ZipFile(zip_path) as zf:
        if "KoboRoot.tgz" not in zf.namelist():
            raise PatchError("KoboRoot.tgz not found in the update zip")
        blob = zf.read("KoboRoot.tgz")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        wanted = {member, "./" + member}
        ti = next((m for m in tf.getmembers() if m.name in wanted), None)
        if ti is None:
            raise PatchError(f"{member} not found in KoboRoot.tgz")
        return tf.extractfile(ti).read(), ti


def collect_overlay(overlay_dir: Path):
    """Return (arcname, bytes, mode) for every file under overlay_dir.

    Scripts (under an init.d directory, or ending in .sh) get mode 0755;
    everything else 0644. Paths are mapped to ./<relative path> so they land
    at the matching absolute path when the device runs `tar zxf -C /`.
    """
    members = []
    root = Path(overlay_dir)
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        executable = rel.endswith(".sh") or "/init.d/" in "/" + rel
        members.append(("./" + rel, p.read_bytes(), 0o755 if executable else 0o644))
    return members


def write_koboroot(out_path: Path, data: bytes, template: tarfile.TarInfo,
                   extra=None):
    """Write a KoboRoot.tgz with the patched library (keeping the stock file's
    name, mode, ownership and mtime) plus any overlay files, so it installs
    like a stock update."""
    with tarfile.open(out_path, "w:gz") as tf:
        ti = tarfile.TarInfo(template.name)
        ti.size = len(data)
        ti.mode, ti.mtime, ti.type = template.mode, template.mtime, tarfile.REGTYPE
        ti.uid, ti.gid = template.uid, template.gid
        ti.uname, ti.gname = template.uname, template.gname
        tf.addfile(ti, io.BytesIO(data))
        for arcname, blob, mode in (extra or []):
            ei = tarfile.TarInfo(arcname)
            ei.size = len(blob)
            ei.mode = mode
            ei.mtime = template.mtime
            ei.type = tarfile.REGTYPE
            ei.uid = ei.gid = 0
            ei.uname = ei.gname = "root"
            tf.addfile(ei, io.BytesIO(blob))


# ----------------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------------

def load_spec(patches_path: Path):
    with open(patches_path, "rb") as fh:
        return tomllib.load(fh)


def verified_sha1s(spec):
    return {v["sha1"] for v in spec.get("target", {}).get("verified", [])}


def cmd_inspect(args):
    spec = load_spec(args.patches)
    member = spec["target"]["path"]
    blob, _ti = read_member(args.zip, member)
    print(f"{member}  sha1 {hashlib.sha1(blob).hexdigest()}  ({len(blob)} bytes)")
    elf = Elf32(blob)
    seen = set()
    for patch in spec["patch"]:
        sym = patch["symbol"]
        if sym in seen:
            continue
        seen.add(sym)
        site = elf.funcs.get(sym)
        if site is None:
            print(f"  MISSING  {patch['id']:<28} {sym}")
            continue
        head = bytes(elf.data[site.file_off:site.file_off + 8]).hex()
        print(f"  {patch['id']:<28} @{site.file_off:#010x} "
              f"size={site.size:<5} {head}")
    return 0


def cmd_build(args):
    spec = load_spec(args.patches)
    member = spec["target"]["path"]
    blob, template = read_member(args.zip, member)
    sha1 = hashlib.sha1(blob).hexdigest()
    verified = verified_sha1s(spec)

    print(f"target {member}")
    print(f"  sha1 {sha1}")
    if sha1 in verified:
        print("  verified build")
    else:
        print("  WARNING: unverified build; patch sites checked only on:")
        for v in spec.get("target", {}).get("verified", []):
            print(f"    {v['version']}  {v['sha1']}")
        if not args.force:
            print("  refusing without --force (run `inspect` and review first)")
            return 2

    elf = Elf32(blob)
    only = set(args.only) if args.only else None
    skip = set(args.skip) if args.skip else None
    rows = apply_patches(elf, spec, args.profile, only, skip)

    print(f"\nprofile {args.profile}:")
    applied = 0
    for pid, group, status, detail in rows:
        mark = {"patched": "+", "ok": "=", "skip": "-"}[status]
        print(f"  {mark} {group:<10} {pid:<28} {detail}")
        if status == "patched":
            applied += 1

    extra = collect_overlay(args.overlay) if args.overlay else []

    args.out.mkdir(parents=True, exist_ok=True)
    so_path = args.out / Path(member).name
    so_path.write_bytes(elf.data)
    kr_path = args.out / "KoboRoot.tgz"
    write_koboroot(kr_path, bytes(elf.data), template, extra)

    print(f"\n{applied} patch(es) applied")
    for arcname, _blob, mode in extra:
        print(f"  overlay {oct(mode)[2:]} {arcname}")
    print(f"  {so_path}")
    print(f"  {kr_path}")
    print("\nInstall: copy KoboRoot.tgz into the .kobo folder on the eReader "
          "over USB, eject, and reboot.")
    return 0


def main(argv=None):
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="openkobo firmware patch tool")
    ap.add_argument("--patches", type=Path,
                    default=here / "patches" / "libnickel.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="apply patches and repack KoboRoot.tgz")
    b.add_argument("--zip", type=Path, required=True,
                   help="official Kobo update zip for this device")
    b.add_argument("--profile", default="offline",
                   choices=["offline", "selfhosted"])
    b.add_argument("--out", type=Path, default=here / "out")
    b.add_argument("--overlay", type=Path,
                   help="directory of extra files to add to KoboRoot.tgz "
                        "(e.g. overlay/ for the SSH hardening)")
    b.add_argument("--only", nargs="+", metavar="GROUP",
                   help="only these patch groups")
    b.add_argument("--skip", nargs="+", metavar="GROUP",
                   help="skip these patch groups")
    b.add_argument("--force", action="store_true",
                   help="patch even an unverified build")
    b.set_defaults(func=cmd_build)

    i = sub.add_parser("inspect", help="resolve patch sites, patch nothing")
    i.add_argument("--zip", type=Path, required=True)
    i.set_defaults(func=cmd_inspect)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (PatchError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
