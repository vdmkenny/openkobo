# Components

Versions in 4.38.23852 (kobo7 bundle), read from the binaries. Several file
names do not match the version inside.

| Component | Stock | openkobo |
|-----------|-------|----------|
| glibc | 2.19 (file `libc-2.11.1.so`) | stock |
| zlib | 1.2.8 (reports `1.2.8-motley`; file `libz.so.1.2.4`) | 1.3.1 |
| libpng | 1.6.x (`libpng16.so.16` → `libpng.so`, base image) | 1.6.44 |
| libjpeg-turbo | 1.5.2 | 3.0.4 |
| FreeType | 2.5.0 (file `libfreetype.so.6.6.2`) | 2.13.3 |
| libxml2 | 2.7.6 | 2.13.5 |
| OpenSSH `sshd` | 8.9p1, static | stock, new config |
| BusyBox | 1.31.1 | stock |
| OpenSSL | 1.0.1u | stock |
| Qt | 5.2.1 | stock |
| Kernel | 4.1.15 (NXP BSP + Netronix patches) | stock |

## Replaced libraries

`tools/libs/` (Docker) builds the koreader koxtoolchain and cross-compiles the
five libraries. `build-libs.sh` rejects a build that changes a soname, adds a
`NEEDED` entry the device lacks, or needs a glibc symbol version newer than
`GLIBC_2.18`. The results need at most `GLIBC_2.7`, are stripped, and are
installed under their soname at the stock path (`lib/`, `usr/lib/`).

Checked against the 59 stock binaries that link them (nickel, Qt, Adobe
RMSDK, plugins): every symbol and symbol version they import is defined.
FreeType and libxml2 are built with optional dependencies off, so their
`NEEDED` lists match the stock libraries.

The official update has no entry for the soname links `lib/libz.so.1`,
`lib/libjpeg.so.62`, `usr/lib/libfreetype.so.6` and `usr/lib/libxml2.so.2`; the
base image provides them as symlinks. Reinstalling the official update
therefore does not undo the libraries; `openkobo.py revert` does.

## Not replaced

- OpenSSL: the closed `nickel`, `librmsdk` and `libadobe` link `.so.1.0.0`;
  1.1 and 3.x have a different ABI.
- Qt: `nickel` is built against 5.2.1.
- Kernel: vendor modules (Wi-Fi, USB gadget) are tied to 4.1.15 by vermagic.
  The e-ink controller driver (`mxc_epdc_fb`) is out of tree, so a newer kernel
  needs that driver ported.
