# openkobo

A more private, lighter and more open firmware for Kobo e-readers, built as a
set of patches against Kobo's own firmware rather than a fork of it. Nothing
from Kobo's firmware is stored in this repository: you bring the official
update zip, the tooling patches it.

**Status: research.** The analysis is done, the patches are defined and the
build tool produces a patched `KoboRoot.tgz`, but nothing has been tested on a
device yet.

## Target

| Firmware   | Bundles                    | Devices                                                           |
|------------|----------------------------|-------------------------------------------------------------------|
| 4.38.23852 | kobo3 – kobo11             | Touch, Glo, Aura, Clara HD, Forma, Libra H2O, **Nia**, Sage, Libra 2, Clara 2E, Elipsa (2E), ... |
| 4.46.23852 | kobo12, kobo13             | Clara BW, Clara Colour, Libra Colour (separate branch, not yet looked at) |

Firmware downloads per device: <https://pgaskin.net/KoboStuff/kobofirmware.html>.
The patch sites were checked by hand on the kobo7 bundle (Nia, Clara HD,
Forma, Libra H2O); `libnickel.so.1.0.0` SHA-1 `f41a9da25309160da7cb49bc7db6a9e4cf79aeab`.

## What the stock firmware does that we want gone

Found in `libnickel.so.1.0.0` (the whole UI lives there; `nickel` is a 36 KB
launcher plus embedded resources).

- **Kobo analytics.** Every event goes through `EventEngine::fireAnalyticsEvent`.
  Events flagged *mandatory* skip all privacy checks, so the settings toggles
  cannot stop them. Without an account, `PrivacyPermissionsManager::analyticsEnabled`
  defaults to true.
- **Crash-log upload.** `SubmitAnalyticsEventsCommand::populateQueue` attaches
  crash logs to the analytics upload whatever `crashLoggingEnabled` says.
- **Google Analytics.** Hard-coded `UA-6177406-38` and GA4 `G-HKVPYM8786`,
  sent to `ssl.google-analytics.com`.
- **Third-party geo-IP.** During setup the device's IP goes to `api.ipinfodb.com`
  (hard-coded API key) and `worldtimeapi.org` to guess the time zone.
- **Connectivity probes.** Every Wi-Fi connect hits `captive.apple.com`,
  `api.ereaderupgrade.com` and `api.ereaderupgrades.com`.
- **A/B testing** (Optimizely cookies, test groups attached to events) and
  store **recommendations** throughout the UI.
- **Over-the-air updates**, still checked in sideloaded mode. An update would
  silently replace a patched firmware.
- **SSH.** Kobo now ships `sshd` (OpenSSH 8.9p1), enabled by creating
  `.kobo/ssh-enabled`. Every unit ships the same host private keys, and root is
  reachable with an empty password until the first login sets one.

## What helps

- **Sideloaded mode.** Kobo's own account-less mode
  (`ApplicationSettings::sideloadedMode`). With it on, first-time setup treats
  the account step as complete, and the store, Kobo Plus, account UI, Reading
  Life tracking and periodic auto-sync are off. Kobo itself enters it from
  `ChooseSetupTypeController::onSkipWifiSetup`.
- **Custom sync endpoint.** `[OneStoreServices] api_endpoint` in
  `Kobo eReader.conf` redirects the store/sync API. That is how self-hosted
  servers with Kobo sync (calibre-web, Komga, BookLore, ...) plug in. It needs
  the normal sync path, so it is incompatible with forced sideloaded mode,
  hence two planned profiles: **offline** and **selfhosted**.
- **Unsigned updates.** `rcS` extracts `.kobo/KoboRoot.tgz` onto `/` with no
  signature check, so a repacked update installs like a stock one.

## Patches

[`patches/libnickel.toml`](patches/libnickel.toml) defines 12 patches. Each is
a small Thumb-2 stub written at a function entry (`bx lr`, return 0/1, or a
tail call), keyed by the exported mangled symbol rather than an offset, so the
same file applies across hardware bundles and to later builds where the symbol
still exists. Every entry says why the stub is safe for its callers.

| Group      | Patches |
|------------|---------|
| telemetry  | analytics events, analytics upload, GA queue and send, analytics/crash/A-B/recommendation permissions off |
| geoip      | time-zone lookup fails immediately (manual time-zone selection) |
| ota        | no upgrade check during sync |
| captive    | no connectivity probes (NTP via dhcpcd is unaffected) |
| accounts   | sideloaded mode forced on (offline profile only) |

## Building

You supply the official update zip for your device (see the download table
above). `tools/openkobo.py` needs only Python 3.11+ (standard library).

```bash
# resolve every patch site and print offsets + current prologue bytes
python3 -I tools/openkobo.py inspect --zip kobo-update-4.38.23852.zip

# apply the offline profile and repack
python3 -I tools/openkobo.py build --zip kobo-update-4.38.23852.zip \
        --profile offline --out out/
```

The tool refuses to patch unless the library's SHA-1 matches a
`[[target.verified]]` build in `patches/libnickel.toml` (override with
`--force` after reviewing `inspect` output on the new build). `--only`/`--skip`
select patch groups; `--profile selfhosted` leaves sideloaded mode off.

Output `out/KoboRoot.tgz` holds only the patched `libnickel.so.1.0.0`, with the
stock file's mode and ownership preserved. **Install:** copy it into the
`.kobo` folder on the eReader over USB, eject, and reboot. **Revert:** reinstall
the official update zip for the device.

On 4.38.23852 (offline profile) the result differs from the stock library in
exactly the 12 patch sites (38 bytes) and nothing else; each stub was confirmed
with `objdump` to decode to the intended instruction.

> Patching firmware can brick a device. Back up the `.kobo` folder first, and
> try the telemetry/OTA groups (`--skip accounts`) before forcing sideloaded
> mode. Untested on hardware so far.

## Outdated components (for the roadmap)

| Component | Version | Notes |
|-----------|---------|-------|
| Kernel (Nia, mx6ull) | 4.1.15 NXP BSP | EOL 2018. E-ink and Wi-Fi drivers are vendor-specific, so no drop-in replacement |
| glibc | 2.11.1 | 2009; new binaries for the device should be static |
| OpenSSL | 1.0.1u (+ 0.9.8) | 2016, no TLS 1.3 |
| Qt / QtWebKit | 5.2.1 | 2014; the built-in browser runs on it |
| zlib / libxml2 | 1.2.4 / 2.7.6 | 2010 / 2009 |
| BusyBox | 1.31.1 | 2019 |
| OpenSSH | 8.9p1 | 2022, has internal-sftp |

## Working with Ghidra

The analysis uses a headless Ghidra project (kept out of git). To recreate it,
import `usr/local/Kobo/libnickel.so.1.0.0` from an extracted `KoboRoot.tgz`
with `analyzeHeadless` (about 7 minutes). Then run query batches:

```bash
tools/gq.sh queries.txt out.txt
```

One command per line: `decomp <addr>`, `callers <addr>`, `strref <text>`,
`disasm <addr> <count>`. Set `GHIDRA` to your Ghidra install. Ghidra loads the
library at `0x10000`, so its addresses are the file offset (and `objdump`
address) plus `0x10000`.

## Roadmap

- Test on hardware (a Kobo Nia): telemetry/OTA/geo-IP/captive groups first,
  then sideloaded mode after a factory reset.
- selfhosted profile: work out what the device needs to sync against a custom
  `api_endpoint` (calibre-web / Komga / BookLore) without a real Kobo account.
- SSH: per-device host keys, key-only root login, SFTP.
- Library scanning: skip hidden folders (`ExcludeSyncFolders`) for faster
  imports.
- Look at the 4.46 branch for the colour and Clara BW models.
