# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=rita
"""Promote the retained producer without unit edits or incompatible rollback."""

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile

HELPER_SHA = "52c9182469c86c94f1406bfff8d495a9c29e78c5230711a5d5fe2bb4a93ed7f4"
TESSA_URL = "http://ava.bajaj.com:6013/text-to-speech-stream"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def selector(raw):
    lines = raw.decode("utf-8").splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines)
               if line.strip().startswith("AVRIL_AIMEE_TTS_URL=")]
    if len(matches) != 1:
        raise ValueError("exactly one existing TTS selector required")
    old = lines[matches[0]]
    ending = "\r\n" if old.endswith("\r\n") else "\n"
    lines[matches[0]] = "AVRIL_AIMEE_TTS_URL=" + TESSA_URL + ending
    return "".join(lines).encode("utf-8")


def load_helper(kit):
    path = kit / "deploy-rita-canonical.py"
    if sha(path.read_bytes()) != HELPER_SHA:
        raise ValueError("retained helper identity mismatch")
    spec = importlib.util.spec_from_file_location("retained_rita", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def promote(module, data, binary, unit, env, root, expected, unit_sha, env_sha,
            runtime, smoke):
    binary_info, unit_info, old_unit, new_unit = module.check_site(binary, unit, expected)
    env_info = module.regular(env)
    old_env = env.read_bytes()
    if old_unit != new_unit or sha(old_unit) != unit_sha or sha(old_env) != env_sha:
        raise ValueError("exact current configuration baseline required")
    if env_info.st_uid != 0 or stat.S_IMODE(env_info.st_mode) != 0o600:
        raise ValueError("protected environment ownership required")
    new_env = selector(old_env)

    def unchanged():
        module.recheck_site(binary, unit, expected, binary_info, unit_info, old_unit)
        now = module.regular(env)
        if env.read_bytes() != old_env or (now.st_uid, now.st_gid, stat.S_IMODE(now.st_mode)) != (
                env_info.st_uid, env_info.st_gid, stat.S_IMODE(env_info.st_mode)):
            raise ValueError("environment changed before promotion")

    runtime.zero()
    unchanged()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private backup directory required")
    backup = Path(tempfile.mkdtemp(prefix="producer-", dir=root))
    for name, raw in (("binary.before", binary.read_bytes()), ("unit.before", old_unit),
                      ("environment.before", old_env)):
        fd = os.open(backup / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    module.sync_directory(backup)
    module.sync_directory(root)
    phase = "stop"
    try:
        runtime.zero()
        unchanged()
        runtime.stop()
        unchanged()
        phase = "binary"
        module.atomic(binary, data, binary_info)
        phase = "selector"
        module.atomic(env, new_env, env_info)
        phase = "start"
        runtime.start()
        phase = "health"
        smoke()
        if binary.read_bytes() != data or unit.read_bytes() != old_unit or env.read_bytes() != new_env:
            raise ValueError("postimage changed")
    except Exception:
        # New reservations can be unreadable by the former producer. Never rewind them.
        print(json.dumps({"ok": False, "phase": phase, "backup": str(backup),
                          "automatic_rollback": False, "reservations_rewound": False}))
        raise
    return {"ok": True, "backup": str(backup), "binary_sha256": sha(data),
            "unit_sha256": sha(old_unit), "environment_sha256": sha(new_env),
            "automatic_rollback": False, "reservations_rewound": False,
            "human_acceptance": "pending"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", required=True, type=Path)
    parser.add_argument("--expected-binary", required=True)
    parser.add_argument("--expected-unit", required=True)
    parser.add_argument("--expected-environment", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    module = load_helper(args.kit.resolve())
    data = module.package(args.kit.resolve())
    binary = Path("/usr/local/libexec/aimee-pbx-router")
    unit = Path("/etc/systemd/system/aimee-pbx-router.service")
    env = Path("/etc/aimee-pbx-router.env")
    _, _, old_unit, new_unit = module.check_site(binary, unit, args.expected_binary)
    raw_env = env.read_bytes()
    if old_unit != new_unit or sha(old_unit) != args.expected_unit or sha(raw_env) != args.expected_environment:
        raise ValueError("configuration baseline mismatch")
    selector(raw_env)
    token = module.token_from_env(env)
    native = module.Native()
    native.zero()
    if not args.apply:
        print(json.dumps({"ok": True, "mode": "check", "mutated": False}))
        return
    if os.geteuid() != 0:
        raise ValueError("root required")
    lock = os.open("/run/lock/jd-rita-producer-promotion.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock, "r+") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = promote(module, data, binary, unit, env,
                         Path("/var/backups/aimee-pbx-router-producer-20260914"),
                         args.expected_binary, args.expected_unit, args.expected_environment,
                         native, lambda: native.smoke("https://vip.bajaj.com/aimee-router", token,
                                                     True, module.BINARY_SHA,
                                                     module.unit_service_type(old_unit)))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
