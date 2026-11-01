# openkobo

Builds a `KoboRoot.tgz` from an official Kobo firmware update. Installed on
the eReader, it:

- disables Kobo analytics, crash-log upload, Google Analytics, the geo-IP
  time-zone lookup, the captive-portal probe and OTA update checks;
- removes the Kobo account requirement (sideloaded mode: no store, no sync);
- makes the library import skip hidden directories;
- replaces SSH with key-only root login and a per-device host key;
- replaces zlib, libpng, libjpeg-turbo, FreeType and libxml2 with current
  releases.

No Kobo firmware is stored here. You supply the update zip.

## Supported

Firmware 4.38.23852, bundles kobo3–kobo11: Touch, Glo, Aura, Clara HD, Forma,
Libra H2O, Nia, Sage, Libra 2, Clara 2E, Elipsa, Elipsa 2E. The device must
already run 4.38.23852; the package holds only the files it changes.

Patch sites and library compatibility are checked on the kobo7 bundle
(`libnickel.so.1.0.0` SHA-1 `f41a9da25309160da7cb49bc7db6a9e4cf79aeab`). The
build refuses any other `libnickel` unless given `--force`.

The 4.46 bundles (kobo12, kobo13: Clara BW, Clara Colour, Libra Colour) are not
supported.

Run on hardware (Kobo Nia): the libnickel patches. The SSH and library changes
are verified off-device only (see `docs/`).

## Build

Requires Python 3.11+ and, for the libraries, Docker.

```bash
make ZIP=~/Downloads/kobo-update-4.38.23852.zip
```

Output: `out/full/KoboRoot.tgz`. The first run builds the cross-toolchain,
which is slow; later runs reuse it.

| Command | Result |
|---------|--------|
| `make` | full package: patches, SSH, libraries |
| `make OVERLAYS=overlay` | patches and SSH, no libraries, no Docker |
| `make PROFILE=selfhosted` | every patch except `accounts`; keeps the Kobo account and sync |
| `make revert` | `out/revert/KoboRoot.tgz`, restores the stock files |
| `make inspect` | resolves each patch symbol, prints offsets, patches nothing |
| `make libs` | rebuilds the libraries only |
| `make clean` | removes `out/full`, `out/revert` |

`ZIP` defaults to the first `kobo-update-*.zip` in this directory.

## Install

Back up the `.kobo` folder. Copy `KoboRoot.tgz` into `.kobo/` on the eReader
over USB and eject. The device installs it on the next boot.

## Revert

Install `out/revert/KoboRoot.tgz` the same way. It restores the stock
`libnickel`, SSH files and library links. Reinstalling the official update
alone does not restore the library links.

## Patches

`patches/libnickel.toml`: 13 patches to `libnickel.so.1.0.0`, keyed by exported
symbol, each with its rationale. Most replace a function entry with a Thumb-2
stub (`bx lr`, return 0/1, or a tail call); one replaces bytes inside a
function. The patched library differs from stock in 39 bytes.

| Group | Effect |
|-------|--------|
| telemetry | No analytics events or upload, no crash-log upload, no Google Analytics; analytics, crash-log, A/B and recommendation permissions off |
| geoip | No time-zone lookup via `api.ipinfodb.com` / `worldtimeapi.org`; time zone set by hand |
| ota | No firmware update check |
| captive | No connectivity probe to `captive.apple.com` / Kobo hosts; hotel-style login pages are not detected; NTP unaffected |
| accounts | Sideloaded mode on: no account, store, Kobo Plus, Dropbox, Google Drive or OverDrive |
| scan | Import skips hidden directories (`.git`, calibre metadata, macOS `.Spotlight-V100`, …) |

## SSH

Off by default. Setup: `docs/ssh.md`.

## Libraries

| Library | Stock | openkobo |
|---------|-------|----------|
| zlib | 1.2.8 | 1.3.1 |
| libpng | 1.6.x | 1.6.44 |
| libjpeg-turbo | 1.5.2 | 3.0.4 |
| FreeType | 2.4.4 | 2.13.3 |
| libxml2 | 2.7.6 | 2.13.5 |

Built by `tools/libs/` in Docker against the device's glibc. Compatibility
checks and other component versions: `docs/components.md`.

## Ghidra

Helpers for finding patch sites, using a local headless project (not in git).
Ghidra loads `libnickel.so.1.0.0` at `0x10000`, so its addresses are the file
offset plus `0x10000`.

```bash
GHIDRA=/path/to/ghidra tools/gq.sh queries.txt out.txt
```

Commands, one per line: `decomp <addr>`, `callers <addr>`, `strref <text>`,
`disasm <addr> <count>`.

## Layout

```
Makefile                  build entry point
patches/libnickel.toml    patch definitions
overlay/                  SSH files added to the package
tools/openkobo.py         patch, package and revert tool
tools/libs/               library cross-build (Docker)
tools/gq.sh, tools/ghidra_scripts/   Ghidra helpers
docs/                     ssh.md, components.md
```
