# openkobo

Patches for Kobo e-reader firmware that remove telemetry, remove the account
requirement, and harden the system. Distributed as patches, not a fork: you
supply the official update zip, the tooling patches it. No Kobo firmware is
stored in this repository.

## Supported

| Firmware   | Bundles        | Devices |
|------------|----------------|---------|
| 4.38.23852 | kobo3–kobo11   | Touch, Glo, Aura, Clara HD, Forma, Libra H2O, Nia, Sage, Libra 2, Clara 2E, Elipsa, Elipsa 2E |
| 4.46.23852 | kobo12, kobo13 | Clara BW, Clara Colour, Libra Colour — not yet supported |

Patch sites verified on the kobo7 bundle; `libnickel.so.1.0.0` SHA-1
`f41a9da25309160da7cb49bc7db6a9e4cf79aeab`. Tested on a Kobo Nia: both profiles
install and run.

Firmware downloads: <https://pgaskin.net/KoboStuff/kobofirmware.html>

## Patches

`patches/libnickel.toml` defines 13 patches to `libnickel.so.1.0.0`, keyed by
exported symbol so they apply across bundles and later builds. Most are a
Thumb-2 stub at a function entry (`bx lr`, return 0/1, or a tail call); one is a
byte replacement anchored inside a function (`find`/`replace`).

| Group     | Effect |
|-----------|--------|
| telemetry | No Kobo analytics events, no analytics/crash-log upload, no Google Analytics, analytics/crash/A-B/recommendation permissions forced off |
| geoip     | Time-zone lookup to `api.ipinfodb.com` / `worldtimeapi.org` removed; time zone set manually |
| ota       | No firmware update check during sync |
| captive   | No connectivity probe to `captive.apple.com` / Kobo hosts (NTP unaffected) |
| accounts  | Sideloaded mode forced on — no account, no store (offline profile only) |
| scan      | Importer skips hidden directories, so it no longer descends into `.git`, calibre metadata or macOS junk |

## Profiles

- `offline` (default): all 12 patches, including forced sideloaded mode.
- `selfhosted`: telemetry/geoip/ota/captive only, leaves the account and sync
  path intact for a custom `[OneStoreServices] api_endpoint`. Not yet
  implemented.

## Build

Requires Python 3.11+ (standard library only).

```bash
# resolve patch sites, print offsets and current prologue bytes
python3 -I tools/openkobo.py inspect --zip kobo-update-4.38.23852.zip

# offline profile, with the SSH hardening and updated-library overlays
python3 -I tools/openkobo.py build --zip kobo-update-4.38.23852.zip \
        --profile offline --overlay overlay/ out/libs/overlay --out out/
```

Refuses to patch unless the library SHA-1 matches a `[[target.verified]]` entry
(override with `--force`). `--only`/`--skip` select patch groups by name.
`--overlay` takes one or more directories whose files are added to the package;
`overlay/` is the SSH hardening and `out/libs/overlay` is produced by the
library build (see below).

Output differs from the stock library only at the 12 patch sites (38 bytes);
each stub is confirmed with `objdump`.

## Install

Copy `out/KoboRoot.tgz` into the `.kobo` folder over USB, eject, reboot.
Revert by reinstalling the official update zip.

Back up `.kobo` first. To test patches without removing the account, build with
`--skip accounts`.

## SSH hardening

`overlay/` replaces the stock SSH config and init script: device-unique host
keys, key-only root login, and `sshd` refuses to start without an installed
public key. Build with `--overlay overlay/`. Setup: `docs/ssh.md`.

## Component and kernel status

`docs/modernization.md`. The media/parsing libraries (zlib, FreeType, libpng,
libjpeg, libxml2) are the easiest and highest-value updates and are built by
`tools/libs/run.sh` (Docker): it cross-compiles them for the device's old glibc
and writes `out/libs/overlay`, which the build above adds with `--overlay`.
OpenSSL, Qt and the kernel are ABI-locked to closed or vendor code and are hard.

## Ghidra

Headless project, kept out of git. Import `libnickel.so.1.0.0` from an extracted
`KoboRoot.tgz` with `analyzeHeadless`, then query:

```bash
tools/gq.sh queries.txt out.txt
```

Commands, one per line: `decomp <addr>`, `callers <addr>`, `strref <text>`,
`disasm <addr> <count>`. Set `GHIDRA` to the Ghidra install. Ghidra loads the
library at `0x10000`; its addresses are the file/objdump offset plus `0x10000`.

## Layout

```
patches/libnickel.toml   patch definitions
overlay/                 files added to KoboRoot.tgz (SSH hardening)
tools/openkobo.py        build tool
tools/gq.sh, ghidra_scripts/   Ghidra query helpers
docs/                    ssh.md, modernization.md
```

## Roadmap

- Media/parsing libraries: built (zlib 1.3.1, libpng 1.6.44, libjpeg-turbo
  3.0.4, FreeType 2.13.3, libxml2 2.13.5) via `tools/libs/`; not yet tested on a
  device.
- Support the 4.46 bundles (Clara BW/Colour, Libra Colour).
- selfhosted profile: sync against a custom `api_endpoint` without a Kobo account.
