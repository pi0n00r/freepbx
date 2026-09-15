# Current Telephony Deployment

Use `PACKAGE-IDENTITY.json` in the private kit for its exact coordinator commit.
`component-bindings-20260914.json` identifies each component's retained owner
packet. This successor retains Ava and the relay and adds the accepted native
FreePBX RTP keepalive amendment. No component binary is rebuilt or restarted.

## Already Installed

Extn 7 is the narrow local Ministral receptionist. Extn 6 is full Crustacea
AImèe through the authenticated relay. FreePBX owns routing, mailbox-1 PIN
authentication, Follow-Me and Voicemail. Rita performs native PBX operations;
standalone Tessa on Ava uses Ava's Kokoro. Avril remains optional standby.
Voice Organ/Isla retains its own outbound executor. AIgis consumes attention
and presence surfaces; it does not replace PBX semantics or the future
Incident Controller.

Do not restart or reinstall working services because packaging changed.
Ava runtime `27b936e` and relay `71794f4` are installed. Ava's packaging source
`92e848b` adds recovery tooling and instructions without changing its runtime
source tree. Both changed Ava files are a paired installation unit.

Preserve Extn 7, the two-second pre-PIN wait, female prompt assets, current
opening contract, full main-agent tools and model selector. Do not restore an
old agents database or configuration during an ordinary source update.

## Retained Inputs

### Native FreePBX RTP Amendment

In FreePBX Admin -> Config Edit, open the existing
`pjsip.endpoint_custom_post.conf`. Preserve other sections and retain:

```ini
[1](+)
rtp_keepalive=1
```

The exact snippet is `deployment/native/pjsip.endpoint_custom_post.conf`.
Save and Apply Config with zero active calls. Do not edit generated files.
Verify with `asterisk -rx 'pjsip show endpoint 1'`: keepalive 1, Direct Media
true, media encryption sdes, RTP timeout 180, hold timeout 300. Retain existing
dual-stack transports, codecs, Follow-Me and both extension routes. No Ava,
Rita or Crustacea restart accompanies this setting. An earlier VIP restore
must include this amendment. An authorised baseline reversal removes only
these added lines through Config Edit, followed by Save/Apply and readback 0.

The brief outgoing human call passed with this setting, but its root-cause
mechanism and long-term reliability are not inferred from one observation.

Current Ava: `Projects/Ava/staging/ava-accepted-four-payload-92e848b-20260914`.
Its `ava/DEPLOY.md` covers clean Debian/NVIDIA/Docker setup, private current
configuration, consistent database bootstraps, models and image reconstruction.
Its installer has a read-only `--verify-installed` mode. `--check-only` checks
the former activation preimage and is not the current runtime health check.

Current relay: `Projects/openclaw/staging/aimee-main-voice-71794f4-20260914-r1`.
Follow its `deploy-kit/DEPLOY.md`; the private kit contains the real unit and
protected environment. The same current packet is included in this skeleton
under `current-relay/`.

Rita, Tessa, Voice Organ, AIgis, model/MCP and current captured-Core owner
packets retain the acquisition paths in the component index. They were not
rebuilt or redeployed for this packaging successor. Captured Core is separate
from the newer relay; do not replay its historical protected-file preimages
over the accepted relay. Current-owner preflight is required for any future
Core restoration. No live Core restoration is certified by this package.

For offline Core verification, `--projects-root` now delegates to the retained
owner's `fa3323b` verifier, including its existing `--closure-root` option. It
validates the complete captured Core without executing the obsolete four
patchers or requiring a disposable Sonyhal directory. The owner packet at
`Projects/openclaw/staging/current-telephony-recovery-fa3323b-20260914-r4/package`
includes an older relay. It is not permission to restore that relay over the
current `71794f4` packet. The historical explicit `--roots` interface and its
native recovery prerequisites are unchanged; do not confuse an offline pass
with permission or qualification for a native Core restoration.

On Linux, extract private skeletons with Unix modes preserved. Run the existing
read-only coordinator for each relevant retained packet:

```sh
python3 -B deployment/recovery-coordinator.py verify --projects-root /absolute/path/to/Projects --component ava
python3 -B deployment/recovery-coordinator.py verify --projects-root /absolute/path/to/Projects --component crustacea
```

`--component` verification covers that packet, not every external dependency.
Do not recreate disposable Sonyhal work directories. Use the retained Projects
paths. The canonical source is secret-free; skeletons and inspectable kits
contain live credentials and must remain private.

## Later Deployment Or Recovery

Start from the current Legible component guides and assembly note
`qJaJNvzogj4a`. Establish native FreePBX through its UI/Config Edit, then the
owner-managed media, Tessa, Rita, Voice Organ/Isla and Crustacea foundations.
Preserve dual-stack listeners, hostname URLs, credentials and native ownership.

Before a later live change, prove zero calls on Ava and Asterisk and take a
named PVE snapshot on the actual owning host. Use the owning component's
procedure. Do not combine independently selected historical component files.
A VM restoration may rewind messages, sessions and reservations; preserve
accrued state first. Private configuration captures are for total-loss recovery,
not permission to overwrite newer live configuration or ledgers.

## Acceptance

Call `1789439347.39` passed confirmed memo delivery (native Voicemail UID 21),
spoken Goodbye and clean hangup. Independent IMAP receipt is retained under
`Projects/VIP/receipts/ext6-native-imap-deposit-1789439347.39-20260914.md`.
The WAV is synthesis of confirmed text, not original caller audio.

The September 15 keepalive experiment passed three recognised human turns on
the actual Rita -> Extn 1 -> mailbox-1 PIN -> Extn 6 route. Gary accepted the
farewell-and-hangup gate and authorised production retention. No new deposit
was exercised on that call. Ava drained farewell audio and used its existing
terminal fallback, not a model-issued hangup tool.

The missed first Yes, long first response and turn-taking remain follow-ups.
Extended human nine-turn recall, barge-in, cross-call isolation, original-audio
recording and fresh-host recovery are not implied. Extn 7 alone may end its
narrow receptionist task without continued open-ended conversation; Extn 6
retains the full contextual multi-turn contract. Calendar answering, response
tuning and the Incident Controller remain outside this production release.
