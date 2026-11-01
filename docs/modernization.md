# Component and kernel modernization

Assessment of what can be updated in the 4.38.23852 firmware and at what cost.

## Constraint

Device runs glibc 2.11.1 (armv7 hard-float). Anything rebuilt must link against
glibc ≤ 2.11 or be static; a newer symbol requirement will not resolve on the
device. `nickel` itself needs only `GLIBC_2.4`, so a cross-toolchain targeting
the old glibc is enough. BusyBox needs `GLIBC_2.14`.

## Userland

| Component | Shipped | Difficulty | Notes |
|-----------|---------|------------|-------|
| zlib | 1.2.8 | easy | soname `libz.so.1` stable; parses untrusted zip/epub |
| FreeType | 2.6.2 | easy | soname `libfreetype.so.6` stable; parses untrusted fonts |
| libpng | 1.6 (`.so.16`) | easy | soname stable |
| libjpeg | (`.so.62`) | easy | soname stable |
| libxml2 | 2.7.6 | easy | soname `libxml2.so.2` stable |
| BusyBox | 1.31.1 | easy | standalone binary; low security value |
| OpenSSH | 8.9p1 | medium | only `sshd` uses it; a newer build must bundle a modern OpenSSL statically |
| wpa_supplicant | — | medium | links OpenSSL 1.0.0; same bundling problem |
| OpenSSL | 1.0.1u | hard | ABI-locked into closed `nickel`, `librmsdk` (Adobe DRM), `libadobe`; cannot move to 1.1/3.x without rebuilding those |
| Qt / QtWebKit | 5.2.1 | hard | `nickel` is built against it |

Easiest high-value work: the media/parsing libraries (zlib, FreeType, libpng,
libjpeg, libxml2). Stable sonames mean a newer release is a drop-in; they
process untrusted epub content, so they carry the most exposure. Build each
against glibc 2.11, replace the file, confirm `nickel` still loads and renders.

OpenSSL cannot be updated in place: closed binaries are linked to soname
`.1.0.0`, and 1.1/3.x are a different ABI.

### Building the updated libraries

`tools/libs/run.sh` (Docker) builds the koxtoolchain, cross-compiles the five
libraries, and fails if any result needs a newer glibc than the device has or
gains an unresolvable dependency. Output:

- `out/libs/lib/` — the built shared objects.
- `out/libs/overlay/` — the same objects named by soname at their device paths
  (`lib/`, `usr/lib/`), ready for `--overlay`.

Current versions and measured glibc floor:

| Library | Version | soname | glibc floor |
|---------|---------|--------|-------------|
| zlib | 1.3.1 | `libz.so.1` | 2.4 |
| libpng | 1.6.44 | `libpng16.so.16` | 2.4 |
| libjpeg-turbo | 3.0.4 | `libjpeg.so.62` | 2.7 |
| FreeType | 2.13.3 | `libfreetype.so.6` | 2.4 |
| libxml2 | 2.13.5 | `libxml2.so.2` | 2.7 |

FreeType and libxml2 are built with optional dependencies disabled so their
`NEEDED` list stays within what the stock libraries linked.

## Kernel

Nia is i.MX6ULL, kernel 4.1.15 (NXP BSP plus Netronix/NTX board patches).

- Built into `zImage`: SoC, EPDC (e-ink controller), touch, frontlight, MMC.
- Loadable modules: Realtek 8189fs Wi-Fi, SDIO power helpers, USB gadget.
- Vendor `.ko` files are locked to 4.1.15 by vermagic and the kernel's unstable
  module ABI; they cannot be loaded on another kernel. Porting means rebuilding
  driver *source* against the target kernel.

Source availability for a port:

- i.MX6ULL SoC support is mainlined.
- NTX board support (device tree, frontlight PWM, battery, keys) comes from
  Kobo's published GPL kernel source.
- EPDC is the blocker: the e-ink driver is out-of-tree (`mxc_epdc_fb`); there is
  no clean mainline panel driver for this path as of writing — verify current
  status before committing to a port.
- Realtek 8189fs is an out-of-tree/community driver.

A full port to current mainline is a large, high-risk effort and needs SD-card
or serial recovery before it is attempted. It is also lower security value than
the userland work above: the network-facing and untrusted-content code is in
userland, not the kernel. Interim option: stay on 4.1.15 and patch in place.
