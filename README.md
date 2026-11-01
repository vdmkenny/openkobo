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

`patches/libnickel.toml` defines 12 patches to `libnickel.so.1.0.0`. Each is a
Thumb-2 stub at a function entry (`bx lr`, return 0/1, or a tail call), keyed by
exported symbol so it applies across bundles and later builds.

| Group     | Effect |
|-----------|--------|
| telemetry | No Kobo analytics events, no analytics/crash-log upload, no Google Analytics, analytics/crash/A-B/recommendation permissions forced off |
| geoip     | Time-zone lookup to `api.ipinfodb.com` / `worldtimeapi.org` removed; time zone set manually |
| ota       | No firmware update check during sync |
| captive   | No connectivity probe to `captive.apple.com` / Kobo hosts (NTP unaffected) |
| accounts  | Sideloaded mode forced on — no account, no store (offline profile only) |

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

# offline profile, with the SSH hardening overlay
python3 -I tools/openkobo.py build --zip kobo-update-4.38.23852.zip \
        --profile offline --overlay overlay/ --out out/
```

Refuses to patch unless the library SHA-1 matches a `[[target.verified]]` entry
(override with `--force`). `--only`/`--skip` select patch groups by name.
`--overlay DIR` adds extra files (e.g. the SSH hardening) to the package.

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

`docs/modernization.md`. Summary: the media/parsing libraries (zlib, FreeType,
libpng, libjpeg, libxml2) are the easiest and highest-value updates. OpenSSL,
Qt and the kernel are ABI-locked to closed or vendor code and are hard.

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

- Update the media/parsing libraries (`docs/modernization.md`).
- Library scanning: skip hidden folders (`ExcludeSyncFolders`).
- Support the 4.46 bundles (Clara BW/Colour, Libra Colour).
- selfhosted profile: sync against a custom `api_endpoint` without a Kobo account.
