# SSH hardening

The stock firmware has two SSH weaknesses:

- **Shared host keys.** Every Kobo ships the same `/etc/ssh/ssh_host_*` private
  keys, so anyone who has them (they are in the public firmware) can
  impersonate your device or sit in the middle of the connection.
- **Empty-password root.** When SSH is enabled, `/etc/init.d/ssh` blanks the
  root password and `sshd_config` sets `PermitRootLogin yes` /
  `PermitEmptyPasswords yes`, so there is a window where root is reachable with
  no password.

The `overlay/` files replace both:

- `overlay/etc/ssh/sshd_config` — key-only root login, passwords and empty
  passwords refused.
- `overlay/etc/init.d/ssh` — generates a device-unique host key on first
  enable (kept on the user partition, so it survives firmware updates), and
  refuses to start `sshd` until you have installed a public key, so root is
  never reachable without a key.

## Build it into a package

```bash
python3 -I tools/openkobo.py build --zip kobo-update-4.38.23852.zip \
        --profile offline --overlay overlay/ --out out/
```

The overlay files are added to the same `KoboRoot.tgz` as the patched library.
Install it the usual way: copy `out/KoboRoot.tgz` into the `.kobo` folder over
USB, eject, reboot.

## Enable SSH on the device

1. Over USB, create the folder `.kobo/openkobo/` on the eReader and copy your
   **public** key (e.g. `~/.ssh/id_ed25519.pub`) to
   `.kobo/openkobo/authorized_keys`.
2. Create an empty file `.kobo/ssh-enabled`.
3. Eject and reboot. Then:

   ```bash
   ssh root@<device_ip>
   ```

The first boot generates the host key, so the very first connection may take a
few extra seconds. If `authorized_keys` is missing or empty, `sshd` does not
start — that is intentional.

To disable SSH again, delete `.kobo/ssh-enabled` and reboot.

> Host keys live at `.kobo/openkobo/ssh/` on the (FAT) user partition, so
> someone with physical USB access could read them. That is a weaker threat
> than keys shared across every device and reachable over the network; protect
> the device physically if that matters to you.
