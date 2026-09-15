# Rita Current Recovery Kit

This is recovery revision `current-20260914-r2` of source
`6b0efd9a6ed9d702fcc5eb8901b76fbae74fa6d4`. It does not change Rita software.
The binary is SHA-256
`eeb7bc0265b51be0531ab504640876beaa248a4f8864a1f5bdb731cbe804318f`.
The skeleton and inspectable kit contain the same files, including private
configuration. Never publish either publicly.

## Existing Deployment

Rita is already installed on VIP. Do not reinstall it for packaging alone.
Its current configuration selects standalone Tessa on Ava at
`http://ava.bajaj.com:6013/text-to-speech-stream`; Avril is optional standby.
The Rita service, binary, FreePBX routing and reservation ledger are unchanged.

Before a later live change, confirm zero Asterisk/Ava calls and take a named
PVE snapshot of the affected guest. Preserve newer messages, reservations and
other accrued state before any snapshot restore. Historical file-level rollback
helpers and `install.sh` are source references, not the current deployment route.

## Replacement Host

Use the Rita and FreePBX Legible setup guides to prepare the supported Debian 12
base, FreePBX, hostname/TLS ingress and service identities. The native executable
requires GLIBC no newer than 2.36; do not substitute a Trixie-built executable.
Build from the canonical source using the retained Bookworm recipe when the
binary is unavailable. `RITA-DEPLOY.md` documents that recipe and native helper.

The protected `private/private-native-current.tar.gz` contains the current
environment, route aliases, voicemail-helper settings and systemd unit.
`private/native-config-metadata.json` records exact target paths, hashes and
numeric ownership. Reconcile the named service groups on replacement hardware;
numeric group IDs are not portable. Reissue secrets at the owning services if
this private recovery material is lost. The plain equivalents are present in
`config/` and `private/native/` for inspection.

Restore native FreePBX settings through its web UI or Config Edit, never by
replacing generated dialplans. Native routing and mailbox semantics remain
FreePBX-owned. Restore current credentials/configuration before starting Rita;
do not import old reservations over a newer live ledger. Provision HTTPS ingress
and certificates through their owner because this four-file capture is not a
whole-VIP backup. Start Tessa's Kokoro dependency before Tessa, then Rita.

Verify the recorded binary and private-file hashes, `systemctl is-active
aimee-pbx-router`, authenticated native status, and zero active channels. Then
test the complete authorised call path. HTTP acceptance is not proof of ringing,
audible speech, successful message deposit or IMAP delivery. This packaging
revision does not assert that the outstanding human-call gates passed.
