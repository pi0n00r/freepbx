# Google Voice acceptance origin

Use this only for an explicitly authorized end-to-end ingress smoke. It is not
the ordinary outbound-call executor.

## Fixed topology

`Google Voice PSTN -> public DID -> VoIP.ms IVR -> DTMF 0 -> Amici/ext 7 ->
explicit request for AImèe -> production Avril -> FreePBX native routing`.

Do not shorten this into an AI-first path. Direct Gary/Sat routes bypass AImèe.

## Owned local surface

- Browser profile: `~/.local/state/aimee-browser/google-voice`, mode 0700.
- Browser service: `google-voice-browser.service`; loopback CDP 9224 only.
- Audio service: `google-voice-audio.service`.
- Input: `gv_tx_mic`, remapped from the isolated `gv_tx.monitor`.
- Output: `gv_rx`; capture from `gv_rx.monitor`.
- Google Messages owns CDP 9223 and must remain untouched.
- Correct Voice owner: `ssgbajaj@gmail.com`; require the Calls page to show
  `Call as (919) 926-9860`.
- Prepared prompts and proof artifacts live under
  `~/.local/state/google-voice-harness/`.

## Gate order

1. Require both user services active, 9224 loopback-only, `gv_tx_mic` present,
   no PipeWire loopback, and Voice microphone permission set to Allow.
2. Require local MediaRecorder capture of injected Kokoro speech and a separate
   non-silent `gv_rx.monitor` browser-output capture.
3. Require three separate mono 48 kHz PCM WAVs from Avril Kokoro `:6013`,
   `af_bella`: transfer request, AImèe voicemail request, and unique marker.
   Preserve JSON, HTTP `audio/l16`, raw, WAV, hashes, and durations.
4. Require the signed-in Calls page and inspect the number entry, call control,
   dialpad, and state-dependent in-call keypad without originating a call.
   Require Google Voice Settings to read back `Always use my phone to make
calls = false` and `Forward calls to Web = true`; otherwise the call control
   either opens the callback flow or cannot establish the owned browser as the
   WebRTC device.
5. Stop unless the current user request explicitly authorizes the PSTN call.
6. During an authorized call, inject one prepared segment only after each
   observed cue: IVR/DTMF 0, Amici/AImèe answer, then native voicemail.
7. Accept only one correlated Cowlet native artifact, exact marker evidence,
   successful native route outcome, and replay/conflict rejection without a
   second artifact. Preserve call IDs and independent PBX/mail evidence.

Do not use `openclaw agent --deliver` or `messages.tts.auto` for prompt audio.
Use explicit `tts.convert` only if Avril Kokoro fails.

## Trusted browser actions

- Activate the exact Calls tab before a physical CDP click. A correctly
  located control on an inactive target can absorb `mouse_click` without a DOM
  event. Require a trusted click trace or the expected in-call controls before
  claiming origination.
- Do not treat DOM `element.click()` as live-call proof. Require the signed-in
  line, exact E.164 call-control label, then `Hang up call`, `Mute call`, and
  `Open keypad` readback.
- Avoid prolonged zero-valued microphone input after connection. Google Voice
  raises its microphone watchdog and may terminate the test before DTMF. Keep
  the isolated TX endpoint valid and begin the first authorized segment
  promptly after the observed cue; do not add an RX-to-TX loop.
- A call is RED if the returned audio becomes silent and the call ends without
  one correlated native artifact. Preserve the RX recording and inspect
  router/native state before any retry.
