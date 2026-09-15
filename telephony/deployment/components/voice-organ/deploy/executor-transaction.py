#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=Voice-Organ
"""Existing Voice Organ replacement entrypoint's guarded binary-only transaction."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

SHA = re.compile(r"[0-9a-f]{64}\Z")
UNIT = "avril-call-executor.service"
ABI_GATE_SHA = "8e204f2c34940351567b52960867f35b95449996417f664e0a9ccf2b66eec4db"
CONTROL_PATHS = (
    "/etc/voice/voice-organ.env", "/etc/voice/avril-call-executor.env",
    "/etc/systemd/system/voice-organ-calld.service", "/etc/systemd/system/avril-call-executor.service",
    "/opt/voice-organ/calld.py", "/opt/voice-organ/call_recon.py",
    "/opt/voice-organ/isla_adapter.py", "/opt/voice-organ/call-originate.py",
    "/etc/voice/call-allowlist.txt")


class Stop(Exception):
    pass


class IndeterminateOperation(Stop):
    pass


def require(value, code):
    if not value:
        raise Stop(code)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(131072), b""): h.update(b)
    return h.hexdigest()


def fingerprint(path):
    p = Path(path)
    s = p.lstat()
    require(stat.S_ISREG(s.st_mode), "file_not_regular")
    return {"sha256": digest(p), "size": s.st_size, "uid": s.st_uid, "gid": s.st_gid,
            "mode": stat.S_IMODE(s.st_mode)}


def private_path(path, base, prefix):
    p = Path(path)
    require(p.is_absolute() and p.parent == base and p.name.startswith(prefix)
            and p.resolve() == p and not p.is_symlink(), "backup_scope_invalid")
    s = p.stat()
    require(stat.S_IMODE(s.st_mode) == 0o700 and s.st_uid == os.geteuid(), "backup_owner_or_mode_invalid")
    return p


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data); out.flush(); os.fsync(out.fileno())
    fd = os.open(Path(path).parent, os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def physical(path):
    p = Path(path); s = p.stat()
    return {**fingerprint(p), "dev": s.st_dev, "ino": s.st_ino, "mtime_ns": s.st_mtime_ns}


def journal(base, manifest_sha, target, phase, path):
    value = {"schema": "voice-organ-executor-journal-v1", "manifest_sha256": manifest_sha,
             "target": str(target), "phase": phase, "identity": physical(path)}
    write_private(base / ("journal-" + str(time.time_ns()) + "-" + phase + ".json"),
                  (json.dumps(value, sort_keys=True) + "\n").encode())


def journal_owns(base, manifest_sha, target):
    observed = physical(target)
    for p in base.glob("journal-*.json"):
        require(fingerprint(p)["uid"] == os.geteuid() and fingerprint(p)["mode"] == 0o600, "journal_metadata_invalid")
        value = json.loads(p.read_bytes())
        if (value.get("schema") == "voice-organ-executor-journal-v1"
                and value.get("manifest_sha256") == manifest_sha and value.get("target") == str(target)
                and value.get("phase") in ("prepared", "installed", "restore_prepared", "restored")
                and value.get("identity") == observed):
            return True
    return False


def atomic(path, data, identity, record=None):
    fd, name = tempfile.mkstemp(prefix=".executor-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data); out.flush()
            os.fchown(out.fileno(), identity["uid"], identity["gid"])
            os.fchmod(out.fileno(), identity["mode"]); os.fsync(out.fileno())
        if record is not None: record("prepared", Path(name))
        os.replace(name, path)
        d = os.open(path.parent, os.O_DIRECTORY)
        try: os.fsync(d)
        finally: os.close(d)
        if record is not None: record("installed", path)
    finally:
        if os.path.exists(name): os.unlink(name)


def replacement_gate(native, layout, generation, controls):
    native.idle()
    require(native.controls() == controls, "protected_controls_drift_before_replace")
    native.idle()
    require(physical(layout.live) == generation, "physical_executor_drift_before_replace")


def replacement_record(native, layout, generation, controls, base, manifest_sha, restoring):
    def record(phase, path):
        journal(base, manifest_sha, layout.live,
                ("restore_prepared" if phase == "prepared" else "restored") if restoring else phase, path)
        if phase == "prepared":
            # Revalidate after durable preparation, immediately before the rename.
            replacement_gate(native, layout, generation, controls)
    return record


class Layout:
    def __init__(self):
        self.live = Path("/usr/local/sbin/avril-call-executor")
        self.backup_base = Path("/root")
        self.controls = tuple(Path(p) for p in CONTROL_PATHS)
        self.abi_gate = Path(__file__).resolve().with_name("verify-executor-abi.sh")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Stop("http_redirect_rejected")


class Native:
    def __init__(self, layout):
        self.layout = layout

    def run(self, args, timeout=10):
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        require(result.returncode == 0 and len(result.stdout) <= 65536, "native_command_failed")
        return result.stdout

    def abi(self, path):
        require(digest(self.layout.abi_gate) == ABI_GATE_SHA, "ABI_gate_identity_changed")
        # The retained gate checks ELF x86_64 and maximum required GLIBC <= 2.36.
        if stat.S_IMODE(Path(path).stat().st_mode) & 0o111:
            self.run(["/bin/bash", str(self.layout.abi_gate), str(path), "2.36"])
        else:
            # Recovery blobs remain mode0600. Inspect a private executable probe copy.
            with tempfile.TemporaryDirectory(prefix="executor-ABI-probe-", dir=self.layout.backup_base) as tmp:
                probe = Path(tmp) / "executor"
                probe.write_bytes(Path(path).read_bytes()); probe.chmod(0o700)
                require(digest(probe) == digest(path), "ABI_probe_identity_changed")
                self.run(["/bin/bash", str(self.layout.abi_gate), str(probe), "2.36"])

    def controls(self):
        rows = {}
        for p in self.layout.controls:
            rows[str(p)] = fingerprint(p) if p.exists() else None
        data = self.run(["/usr/bin/systemctl", "show", UNIT, "--property=FragmentPath,DropInPaths,User,Group,ExecStart"])
        # Preserve the complete effective control projection as a digest, not argv text.
        rows["effective_unit_sha256"] = hashlib.sha256(data).hexdigest()
        for line in data.decode().splitlines():
            if line.startswith("DropInPaths="):
                for raw in line.split("=", 1)[1].split():
                    p = Path(raw)
                    require(p.is_absolute() and not p.is_symlink(), "unit_dropin_path_invalid")
                    rows[str(p)] = fingerprint(p)
        return rows

    def request(self, port, route, payload=None, token=None):
        wire = json.dumps({"port": port, "route": route, "payload": payload, "token": token}).encode()
        child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--probe-child"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            output, unused = child.communicate(wire, timeout=3)
        except subprocess.TimeoutExpired:
            child.kill(); child.communicate()
            raise Stop("http_total_deadline_exceeded") from None
        require(child.returncode == 0 and len(output) <= 65536, "http_probe_unavailable")
        value = json.loads(output)
        return value["status"], value["value"]

    def request_inline(self, port, route, payload=None, token=None):
        require((port, route) in ((9670, "/status"), (6022, "/healthz"), (6022, "/calls")), "probe_route_invalid")
        require(payload is None or payload == {} or (isinstance(payload, dict)
                and payload.get("op") == "plan_call" and payload.get("args", {}).get("execution_authorized") is False),
                "probe_actuation_rejected")
        headers = {"Content-Type": "application/json"}
        if token is not None: headers["Authorization"] = "Bearer " + token
        req = Request("http://127.0.0.1:" + str(port) + route,
                      data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            with build_opener(NoRedirect()).open(req, timeout=3) as response:
                status, data = response.status, response.read(65537)
        except HTTPError as e:
            status, data = e.code, e.read(65537)
        require(len(data) <= 65536, "http_body_over_budget")
        try: value = json.loads(data)
        except (ValueError, UnicodeError): value = None
        return status, value

    def zero(self):
        self.run(["/usr/bin/systemctl", "is-active", "--quiet", "voice-organ-calld.service"])
        status, p = self.request(9670, "/status")
        require(status == 200 and isinstance(p, dict) and type(p.get("active_calls")) is int
                and p["active_calls"] == 0, "voice_calls_not_zero_or_unreported")
        require("conversation_turn_limit" not in p or p["conversation_turn_limit"] is None,
                "conversation_turn_limit_nonnull")
        data = self.run(["/usr/sbin/asterisk", "-rx", "core show channels concise"])
        require(not data.strip(), "native_channels_not_zero")
        return {"active_calls": 0, "native_channels": 0,
                "conversation_turn_limit": None if "conversation_turn_limit" in p else "unreported"}

    def state(self):
        data = self.run(["/usr/bin/systemctl", "show", UNIT, "--property=MainPID,NRestarts,ActiveState,SubState"])
        rows = dict(line.split("=", 1) for line in data.decode().splitlines() if "=" in line)
        require(rows.get("ActiveState") == "active" and rows.get("SubState") == "running", "executor_not_running")
        require(rows.get("MainPID", "").isdigit() and int(rows["MainPID"]) > 0, "executor_PID_invalid")
        pid = int(rows["MainPID"])
        exe = Path("/proc") / str(pid) / "exe"
        require(os.readlink(exe) == str(self.layout.live), "runtime_executable_path_changed")
        require(digest(exe) == digest(self.layout.live), "runtime_executable_hash_changed")
        owner = (Path("/proc") / str(pid)).stat()
        return {"pid": pid, "restarts": rows["NRestarts"], "sha256": digest(exe),
                "uid": owner.st_uid, "gid": owner.st_gid}

    def health(self):
        status, p = self.request(6022, "/healthz")
        require(status == 200 and isinstance(p, dict) and p.get("ok") is True
                and p.get("executor") == "voice_organ", "executor_health_invalid")
        status, _ = self.request(6022, "/calls", {})
        require(status == 401, "executor_unauthenticated_not_401")
        values = {}
        for line in Path("/etc/voice/avril-call-executor.env").read_text().splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                name, value = line.split("=", 1); values[name] = value
        token = values.get("AVRIL_CALL_AUTH_TOKEN", "")
        require(len(token) >= 24, "managed_executor_token_missing")
        status, p = self.request(6022, "/calls", {"op": "plan_call", "args": {
            "caller_id": "deployment-abi-smoke", "user_input": "Non-actuating deployment verification only.",
            "execution_authorized": False}}, token)
        require(status == 200 and isinstance(p, dict) and p.get("ok") is True
                and p.get("ready_to_run") is False and p.get("confirm_token") is None
                and sorted(p.get("missing_fields", [])) == ["goal", "to_phone"], "nonactuating_plan_invalid")

    def check(self, expected):
        zero = self.zero(); self.health()
        state = self.state()
        require(state["sha256"] == expected, "runtime_expected_hash_rejected")
        return {**state, "voice_status": zero}

    def operation_state(self):
        raw = self.run(["/usr/bin/systemctl", "show", UNIT, "--property=Job,MainPID,ActiveState,SubState"])
        rows = dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line)
        job = rows.get("Job")
        require(job is not None, "systemd_job_observation_unavailable")
        number = job.split()[0] if job else "0"
        require(number.isdigit(), "systemd_job_observation_invalid")
        require(rows.get("MainPID", "").isdigit(), "systemd_PID_observation_invalid")
        return {"job": int(number), "pid": int(rows["MainPID"]),
                "active": rows.get("ActiveState"), "substate": rows.get("SubState")}

    def idle(self):
        require(self.operation_state()["job"] == 0, "systemd_job_pending_no_mutation")

    def service(self, op):
        self.idle()
        try: self.run(["/usr/bin/systemctl", op, UNIT])
        except subprocess.TimeoutExpired:
            raise IndeterminateOperation("systemd_" + op + "_observation_timeout") from None
        self.idle()

    def stop(self): self.service("stop")
    def start(self): self.service("start")

    def post(self, expected):
        deadline = time.monotonic() + 30
        while True:
            try: first = self.check(expected); break
            except (Stop, OSError):
                if time.monotonic() >= deadline: raise Stop("post_start_readiness_failed") from None
                time.sleep(0.25)
        time.sleep(12)
        last = self.check(expected)
        require(first == last, "executor_restart_or_PID_drift")


def load_snapshot(path, expected_manifest, layout, native):
    require(SHA.fullmatch(expected_manifest or "") is not None, "backup_manifest_pin_required")
    base = private_path(path, layout.backup_base, "avril-call-executor-pre-abi-")
    manifest = base / "snapshot.json"
    require(fingerprint(manifest)["mode"] == 0o600 and manifest.stat().st_uid == os.geteuid(), "snapshot_metadata_invalid")
    require(digest(manifest) == expected_manifest, "backup_manifest_hash_changed")
    m = json.loads(manifest.read_bytes())
    require(m.get("schema") == "voice-organ-executor-transaction-v1" and m.get("target") == str(layout.live)
            and m.get("unit") == UNIT and m.get("config_restored") is False
            and m.get("state_restored") is False, "legacy_or_foreign_backup_unsupported")
    blob = base / "executor.before"
    identity = fingerprint(blob)
    require(identity["sha256"] == m["before"]["sha256"] and identity["size"] == m["before"]["size"]
            and identity["mode"] == 0o600 and identity["uid"] == os.geteuid(), "backup_executor_identity_changed")
    native.abi(blob)
    require(native.controls() == m["controls"], "protected_controls_changed")
    return m, blob.read_bytes()


def transaction(mode, native, layout, expected_current, candidate=None, expected_candidate=None,
                backup=None, expected_manifest=None):
    require(SHA.fullmatch(expected_current or "") is not None, "current_live_CAS_required")
    current = fingerprint(layout.live)
    generation = physical(layout.live)
    require(current["sha256"] == expected_current, "current_live_CAS_changed")
    controls = native.controls()
    native.zero()
    try:
        before_state = native.check(expected_current)
    except (Stop, OSError, subprocess.SubprocessError) as error:
        require(mode == "rollback", "preflight_health_unavailable")
        m, unused = load_snapshot(backup, expected_manifest, layout, native)
        require(current in (m["after"], m["before"])
                and journal_owns(Path(backup), expected_manifest, layout.live), "unhealthy_runtime_not_owned_journal_generation")
        # This is explicit crash restoration of our own prepared generation, not health pass.
        before_state = {"status": "unavailable_owned_crash_generation", "error": str(error) if isinstance(error, Stop) else "native_io_failed"}
    if mode == "check":
        if candidate is not None:
            require(SHA.fullmatch(expected_candidate or "") is not None, "candidate_pin_required")
            require(fingerprint(candidate)["sha256"] == expected_candidate, "candidate_hash_changed")
            native.abi(candidate)
        return {"status": "check_only_pass", "runtime": before_state, "sha256": expected_current}
    if mode == "apply":
        require(candidate is not None and SHA.fullmatch(expected_candidate or "") is not None, "candidate_and_pin_required")
        require(fingerprint(candidate)["sha256"] == expected_candidate, "candidate_hash_changed")
        native.abi(candidate); native.abi(layout.live)
        data = Path(candidate).read_bytes()
        require(hashlib.sha256(data).hexdigest() == expected_candidate, "candidate_changed_during_read")
        base = Path(tempfile.mkdtemp(prefix="avril-call-executor-pre-abi-", dir=layout.backup_base))
        base.chmod(0o700)
        old = layout.live.read_bytes()
        require(hashlib.sha256(old).hexdigest() == expected_current, "live_changed_during_capture")
        write_private(base / "executor.before", old)
        after = {**current, "sha256": expected_candidate, "size": len(data)}
        m = {"schema": "voice-organ-executor-transaction-v1", "target": str(layout.live), "unit": UNIT,
             "before": current, "after": after, "controls": controls, "runtime_before": before_state,
             "capture_generation": generation,
             "config_restored": False, "state_restored": False, "capture_authority": "this versioned replacement helper"}
        write_private(base / "snapshot.json", (json.dumps(m, sort_keys=True, indent=2) + "\n").encode())
        manifest_sha = digest(base / "snapshot.json")
        m, old = load_snapshot(base, manifest_sha, layout, native)
        desired = after
    else:
        m, data = load_snapshot(backup, expected_manifest, layout, native)
        base, manifest_sha = Path(backup), expected_manifest
        require(current in (m["after"], m["before"]), "current_not_snapshot_generation")
        require(physical(layout.live) == m["capture_generation"] or journal_owns(base, manifest_sha, layout.live),
                "physical_executor_generation_not_snapshot_owned")
        desired = m["before"]
        old = layout.live.read_bytes()
        if current == desired:
            native.post(desired["sha256"])
            require(fingerprint(layout.live) == desired, "idempotent_rollback_identity_changed")
            return {"status": "already_restored", "backup": str(base), "restored": desired}
    require(native.controls() == controls and physical(layout.live) == generation, "drift_before_stop")
    native.zero()
    require(native.controls() == controls and physical(layout.live) == generation, "drift_before_stop")
    # Only the binary changes. No captured control file, ledger or database is restored.
    changed = False
    result = {"backup": str(base), "backup_manifest_sha256": manifest_sha,
              "preflight_runtime": before_state, "config_restored": False, "state_restored": False}
    try:
        changed = True; native.stop()
        replacement_gate(native, layout, generation, controls)
        atomic(layout.live, data, desired, replacement_record(
            native, layout, generation, controls, base, manifest_sha, mode == "rollback"))
        require(fingerprint(layout.live) == desired, "replacement_identity_rejected")
        native.start(); native.post(desired["sha256"])
        require(fingerprint(layout.live) == desired and native.controls() == controls, "postflight_identity_or_controls_changed")
        native.zero()
        result.update(status=mode + "_passed", restored=fingerprint(layout.live))
    except (Stop, OSError, ValueError, subprocess.SubprocessError) as error:
        result.update(status="transaction_failed_no_retry", phase=type(error).__name__, primary_error=str(error) if isinstance(error, Stop) else "native_io_failed")
        if changed:
            try:
                # A timed-out observation is neither success nor failure of systemd's job.
                observation = native.operation_state()
                result["systemd_operation_observation"] = observation
                require(observation["job"] == 0, "systemd_job_pending_recovery_deferred")
                require(native.controls() == controls, "unrelated_controls_drift_refuse_restore")
                require(fingerprint(layout.live) in (current, desired), "concurrent_executor_drift_refuse_restore")
                require(physical(layout.live) == generation or journal_owns(base, manifest_sha, layout.live),
                        "concurrent_physical_executor_drift_refuse_restore")
                restore_generation = physical(layout.live)
                native.zero(); native.stop()
                replacement_gate(native, layout, restore_generation, controls)
                atomic(layout.live, old, current, replacement_record(
                    native, layout, restore_generation, controls, base, manifest_sha, True))
                require(fingerprint(layout.live) == current, "failure_restore_identity_rejected")
                native.start(); native.post(current["sha256"])
                require(native.controls() == controls and fingerprint(layout.live) == current, "failure_restore_postflight_rejected")
                result["rollback_status"] = "pretransaction_executor_restored"
                result["rollback_restored"] = fingerprint(layout.live)
            except (Stop, OSError, ValueError, subprocess.SubprocessError) as rollback_error:
                result["rollback_status"] = "failed_or_refused_no_retry"
                result["rollback_error"] = str(rollback_error) if isinstance(rollback_error, Stop) else "native_restore_io_failed"
        else: result["rollback_status"] = "no_binary_mutation"
    write_private(base / (mode + "-receipt-" + str(time.time_ns()) + ".json"), (json.dumps(result, sort_keys=True) + "\n").encode())
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true"); mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", type=Path)
    p.add_argument("--expected-current-sha256", required=True)
    p.add_argument("--candidate", type=Path); p.add_argument("--candidate-sha256")
    p.add_argument("--backup-manifest-sha256")
    a = p.parse_args(argv)
    try:
        require(os.geteuid() == 0, "root_required")
        layout = Layout()
        fd = os.open("/root/.avril-call-executor-replacement.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = transaction("rollback" if a.rollback else "apply" if a.apply else "check", Native(layout), layout,
                a.expected_current_sha256, a.candidate, a.candidate_sha256, a.rollback, a.backup_manifest_sha256)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] in ("check_only_pass", "apply_passed", "rollback_passed", "already_restored") else 1
    except (Stop, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "blocked_no_retry", "error": str(error) if isinstance(error, Stop) else "native_or_schema_error"}))
        return 2


if __name__ == "__main__":
    if sys.argv[1:] == ["--probe-child"]:
        try:
            raw = sys.stdin.buffer.read(65537)
            require(len(raw) <= 65536, "probe_input_over_budget")
            status, value = Native(Layout()).request_inline(**json.loads(raw))
            print(json.dumps({"status": status, "value": value}))
        except Exception:
            raise SystemExit(2) from None
        raise SystemExit(0)
    raise SystemExit(main())
