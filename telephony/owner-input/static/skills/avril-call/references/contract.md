# Avril call contract

## Tool order

```text
isla.telephony.plan_call
  -> isla.telephony.run_call
  -> isla.telephony.get_call_run
  -> optional isla.telephony.get_call_recording
  -> optional isla.telephony.transcript_refinement_set
  -> isla.telephony.get_call_run
```

`plan_call` has no external calling side effect. `run_call` consumes one
short-lived confirmation token and may place exactly one call. `get_call_run`
and `get_call_recording` are read-only. Recording reads are hash-bound,
base64-encoded chunks of at most 512 KiB and never accept a caller-supplied
path. `transcript_refinement_set` may attach evidence but cannot alter PBX
disposition.

## Planning input

Required:

- `user_input`: latest user call instruction.

Optional only when explicit:

- `to_phone`: E.164 destination.
- `goal`: bounded call instruction and success criterion.
- `language`: requested call language.
- `execution_authorized`: true only when the user requested execution.
- `refine_transcript`: true only when post-call external transcription is
  permitted.

## Run input

- `plan_id`: exact planning output.
- `confirm_token`: exact planning output; secret and single-use.

## Status input

- `run_id`: exact execution output.
- `cursor` and `limit`: optional activity pagination.

## Refinement input

- `run_id`: known run identifier.
- `audio_sha256`: hash returned with the recording artifact.
- `model`: transcription model actually used.
- `transcript`: returned transcript object; never reconstructed from prose.

## Evidence sources

Keep independent evidence sources distinguishable:

- `asterisk`: authoritative call/channel and disposition events.
- `avr_vosk_live`: immediate local ASR transcript.
- `crustacea_transcribe_skill`: optional post-call refined transcript.
- `fake_executor`: Sonyhal-only contract fixture; proves no call occurred.

Refinement may improve words and speaker labels. It must not rewrite call
status, Asterisk identifiers, timing, or disposition.

## Staging

The Sonyhal executor accepts only `AVRIL_CALL_EXECUTOR=fake`. It must refuse
any other executor value. Use fixture audio and an isolated state file. A
production executor and recording materialization path require a separate,
explicit promotion with controlled FreePBX and Avril validation.
