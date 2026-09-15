---
name: avril-call
description: Plan, confirm, run, monitor, and collect evidence for authenticated calls through the fleet-owned Avril and Isla stack, including opt-in Google Voice PSTN acceptance smokes. Use when the user asks Codex to place or schedule a call, check an Avril call run, run the external DID to Avril acceptance path, or refine an authorized call recording. Also covers the installed Rita internal-call process adapter for health, originate and status. Native server/client smoke passed; recipient audio and human-call qualification remain open.
---

# Avril Call

Prefer authenticated Isla MCP tools for ordinary calls. Existing authenticated
Avril, FreePBX, Asterisk, AMI, ARI, SIP or carrier controls are valid alternatives
within Gary's authorised scope; Isla is not an exclusive permitted route.
Preserve the exact destination and purpose, prevent duplicate originations, and
obtain authoritative call readback whichever route is used. Do not introduce a
destination allowlist or a redundant approval gate.

The workflow below describes Isla's plan/run contract, not a restriction on
other authenticated routes. The authorised Google Voice acceptance harness is
described in [references/google-voice-acceptance.md](references/google-voice-acceptance.md).

## Rita internal-call process adapter

The installed adapter passed authenticated native server/client health and
readback smoke. A real originate returned a PBX receipt and terminal status;
recipient audio and human-call qualification remain open. These checks do not
prove that Gary answered or passed the Extn 6 gate. This is an adapter in this
existing skill, not a new skill or tool catalogue. Existing authorised direct
native PBX routes remain permitted; the Isla plan/run workflow below is not
an exclusive route or an extra approval requirement for this adapter.

Run the reviewed client through the trusted skill process, with one JSON
object on stdin followed by EOF and one machine-coded JSON result on stdout:

```bash
node "<avril-call-skill>/scripts/rita_internal_calls.js" < "<protected-request-json>"
```

These are illustrative input shapes, not call authorisations:

```json
{"operation":"health"}
{"operation":"originate","request_id":"caller-retained-0001","target":"Exact authorised target","purpose":"Exact caller-provided purpose"}
{"operation":"originate","request_id":"caller-retained-0002","target":"Exact authorised target","purpose":"Exact caller-provided purpose","opening_kind":"notification","opening_text":"Hi native recipient, this is your assistant. Exact caller-provided purpose."}
{"operation":"status","request_id":"caller-retained-0001"}
```

- Require existing clear user intent for originate; health/status do not originate.
- Retain the stable caller-provided request_id with the exact target and purpose
  before originate. The client does not create identity or keep a request ledger.
- Optional opening_kind/opening_text are presentation only: at most 64/1024 UTF-8
  bytes respectively, excluding Unicode Cc/Cf/Zl/Zp controls. Missing/null/empty
  values remain valid; unknown kind is generic, not a call refusal. Retain every
  present optional value exactly with the request before dispatch and for replay.
- The main agent prepares complete opening_text in the existing authorised intent
  turn before originate, not with extra inference after answer. The client passes
  it unchanged; it does not compose speech, create a directory or infer identity,
  PIN proof or acknowledgement. Use trusted native FreePBX recipient/call-kind
  context; unavailable names remain generic. No additional call gate is introduced.
- Greeting is `Hi {Name},`; Introduction contains no Hi. Incoming is
  `Hi {Introduction}`; outgoing is `{Greeting} {Introduction}`; notification is
  `{Greeting} {Introduction} {Purpose}`. Include exactly one Hi and no duplicate
  comma. Purpose is not automatically appended to ordinary outgoing speech.
- Each invocation makes at most one request. On timeout, transport failure or
  unknown outcome, do not retry/redial or mint a replacement ID. Reconcile with
  explicit status using the retained ID or authoritative native PBX readback;
  no automatic polling. Existing authorised native PBX routes remain permitted.
- A nonzero exit may include a valid 502 receipt. Preserve cached state/time and
  readback_available; do not interpret unavailable readback as call rejection.
- PBX acceptance/ringing/native answer are not Gary acknowledgement. Both delivery
  and human_acknowledgement remain unproven; report only returned PBX receipt facts.
- PBX_ROUTER_URL keeps its configured HTTPS hostname and proxy prefix. The existing
  PBX_ROUTER_TOKEN pair stays in the trusted process environment or protected
  /etc/aimee-main-voice-relay.env (root:aimee 0640); process values override.
  Never put secrets, credentials, raw headers or config overrides in skill/model input.
- Current-call handoff remains separate: use the existing authoritative raw-call-ID
  binding for that same live call. The originate request_id is not its call_id.
  Ava-specific header validation stays at its existing edge, not in Rita or these ops.
  Opening fields belong only to originate, not the separate current-call tool.

## Safety contract

- Require clear user intent before any real outbound call.
- When using Isla, call `isla.telephony.plan_call` before `isla.telephony.run_call`.
- Treat `plan_id`, `confirm_token`, and `run_id` as opaque.
- Preserve opaque values exactly; never synthesize, modify, reuse, or display
  `confirm_token`.
- Never guess a phone number, country code, goal, language, or schedule.
- Never use `run_call` for setup or connectivity checks.
- Never configure `run_call` for automatic approval.
- If the user asked only to plan, stop after planning.
- If the user already clearly asked to place the call and planning returns
  `ready_to_run=true`, run the exact plan without asking a redundant second
  confirmation.
- Re-plan after any destination, goal, language, schedule, or recording-policy
  change.

## Workflow

1. Call `isla.telephony.plan_call` with the latest user instruction in
   `user_input`. Include structured fields only when explicit.
2. If `ready_to_run=false`, ask only for the returned missing fields and refine
   the plan.
3. If execution is authorized, call `isla.telephony.run_call` once with the
   exact `plan_id` and `confirm_token`.
4. Read the returned `run_id`; show non-terminal activity without exposing
   credentials.
5. Poll `isla.telephony.get_call_run` with the known `run_id` until a terminal
   state or until the user asks to stop.
6. Report only returned PBX outcome, activity, transcript, and evidence.
   Never invent missing transcript text.

Terminal states are `COMPLETED`, `FAILED`, `NO_ANSWER`, `BUSY`, `VOICEMAIL`,
`DECLINED`, `CANCELLED`, `BLOCKED`, and `EXPIRED`.

## Transcript refinement

Treat AVR/Vosk output as the immediate live transcript. Refine it only when all
of these are true:

- the plan requested refinement;
- `get_call_run` returns `transcript_refinement.status=pending`;
- policy permits sending that recording to the configured transcription
  provider.

Materialize the hash-bound recording through Isla into a protected Crustacea
path:

```bash
python3 "<avril-call-skill>/scripts/materialize_call_recording.py" \
  "<run_id>" \
  --out "$HOME/.local/share/avril-call/recordings/<run_id>.wav"
```

The helper reads `ISLA_AUTH_TOKEN` and optional `ISLA_MCP_URL`, fetches bounded
chunks only through `isla.telephony.get_call_recording`, verifies the final
SHA-256, writes mode `0600`, and refuses to overwrite an existing file.

Then use the existing Crustacea transcribe skill; do not duplicate its client:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/transcribe/scripts/transcribe_diarize.py" \
  "<protected-recording-path>" \
  --model gpt-4o-transcribe-diarize \
  --response-format diarized_json \
  --out "<protected-output-path>"
```

Hash the input recording with `sha256sum`. Call
`isla.telephony.transcript_refinement_set` with the `run_id`, exact recording
hash, model name, and returned transcript object. Then fetch
`isla.telephony.get_call_run` again and require:

- `transcript_refinement.status=complete`;
- `transcript_refinement.source=crustacea_transcribe_skill`;
- the same recording hash;
- preserved immediate AVR transcript and PBX outcome.

Do not make call completion depend on optional refinement. If refinement fails,
retain the live transcript, report the refinement failure separately, and do
not change the PBX result.

Read [references/contract.md](references/contract.md) when implementing or
debugging the tool schemas, state transitions, evidence envelope, or Sonyhal
fixture flow.

## External acceptance

For an end-to-end production ingress smoke, read
[references/google-voice-acceptance.md](references/google-voice-acceptance.md).
Keep setup/no-call proof distinct from PSTN authorization and never use the
Google Messages CDP profile.
