# FreePBX VM shutdown integration

This is the VM-native successor to the historical LXC shutdown workaround.
It deliberately does **not** copy the LXC `pkill -9` fallback.

The supported chain is:

1. Proxmox asks the already-enabled QEMU guest agent to shut down the VM.
2. systemd stops `freepbx.service` through its packaged
   `ExecStop=/usr/sbin/fwconsole stop` while MariaDB and the writable root
   filesystem remain available through the packaged ordering.
3. This drop-in gives FreePBX 45 seconds to stop. The Proxmox VM shutdown
   budget is 60 seconds, making one minute the hard host-side ceiling.

The installer is fail-closed: it requires KVM, an active guest agent, a
writable root, the exact packaged FreePBX unit preimage, zero calls/channels,
and either an absent or byte-identical drop-in. It performs only an atomic
drop-in write and `systemctl daemon-reload`; it does not stop or restart any
service and does not shut down the VM.

Current VIP packaged-unit preimage (Debian 12 / FreePBX 17):

```text
b82a52ad0d9852f355567bad25064641a5bf6260bbf29ccbb2db8a4c754becd3
```

Check and install:

```sh
sudo ./install-freepbx-vm-shutdown.sh --check \
  --expected-unit-sha256 b82a52ad0d9852f355567bad25064641a5bf6260bbf29ccbb2db8a4c754becd3
sudo ./install-freepbx-vm-shutdown.sh --install \
  --expected-unit-sha256 b82a52ad0d9852f355567bad25064641a5bf6260bbf29ccbb2db8a4c754becd3
```

On Garden, the matching host-side setting is VM 125 `startup: down=60`.
The existing `agent: 1` setting is retained.

An actual poweroff remains a separately scheduled acceptance test. A previous
VIP shutdown failure was caused by an already-aborted ext4 journal and is not
evidence that QEMU guest-agent shutdown failed.
