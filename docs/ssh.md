# SSH

`overlay/` replaces `/etc/init.d/ssh` and `/etc/ssh/sshd_config`.

| | Stock | openkobo |
|-|-------|----------|
| Host key | `/etc/ssh/ssh_host_*`, identical on every Kobo | one you generate for the device |
| Root login | password blanked, empty password accepted | public key only |
| Starts when | `.kobo/ssh-enabled` exists | that, plus a host key and an authorized key |

## Enable

On your computer:

```bash
ssh-keygen -t ed25519 -N "" -C kobo -f ssh_host_ed25519_key
```

On the eReader over USB:

| Path | Content |
|------|---------|
| `.kobo/openkobo/ssh/ssh_host_ed25519_key` | the private key generated above |
| `.kobo/openkobo/authorized_keys` | your public key, e.g. `~/.ssh/id_ed25519.pub` |
| `.kobo/ssh-enabled` | empty |

Eject, reboot, then `ssh root@<device_ip>`. To check the host key on first
connect, add `<device_ip>` followed by the contents of
`ssh_host_ed25519_key.pub` to `~/.ssh/known_hosts`.

Disable: delete `.kobo/ssh-enabled` and reboot.

## Notes

- The firmware has no `ssh-keygen`, so the host key is generated off-device.
- Both keys live on the FAT user partition, readable by anyone with USB access.
- At boot, `init.d/ssh` copies them to `/tmp/openkobo` (0700, files 0600):
  sshd needs a 0600 host key, which FAT cannot store, and the partition is
  unmounted while USB is connected.
- `StrictModes` is off. The firmware update sets `/` to 0775 owned by uid
  1000, which fails sshd's parent-directory check for any path.
- Tested with the device's `sshd` (OpenSSH 8.9p1, static ARM) under emulation,
  with `/` and `/tmp` set to the device's modes: key login works, password
  login is refused, and sshd does not start without a host key.
