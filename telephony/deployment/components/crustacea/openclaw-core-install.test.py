#!/usr/bin/env python3
# AI-NOTICE:Schema-Version=0.1
# AI-NOTICE:License=AGPL-3.0-or-later
# AI-NOTICE:Project=crustacea
# AI-NOTICE:Repository=https://github.com/pi0n00r/crustacea-backup
# AI-NOTICE:Network-Service=AGPL section 13 applies to network-exposed services

import hashlib
import json
import os
import pathlib
import pwd
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest


PHASE = pathlib.Path(__file__).with_name("openclaw-core-install.commands")


class ScopedMaskTests(unittest.TestCase):
    def run_phase(self, exit_code):
        with tempfile.TemporaryDirectory(prefix="core-mask-unit-") as name:
            root = pathlib.Path(name)
            npm = root / "npm"
            npm.write_text("#!/bin/bash\numask > \"$OUT/mask\"\nprintf '%s\\n' \"$@\" > \"$OUT/args\"\nexit " + str(exit_code) + "\n")
            npm.chmod(0o755)
            phase = root / "phase"
            phase.write_text(PHASE.read_text().replace("sudo /bin/bash", "/bin/bash", 1).replace("/usr/bin/npm", str(npm), 1))
            shell = 'set -euo pipefail; umask 077; mkdir "$OUT/checkpoint"; touch "$OUT/checkpoint/before"; trap \'umask > "$OUT/parent-mask"; touch "$OUT/checkpoint/after"\' EXIT; CORE_TGZ="$1"; source "$2"'
            env = dict(os.environ, OUT=str(root))
            result = subprocess.run(["/bin/bash", "-c", shell, "test", "/fixture/package with spaces.tgz", str(phase)], env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, exit_code)
            self.assertEqual((root / "mask").read_text().strip(), "0022")
            self.assertEqual((root / "parent-mask").read_text().strip(), "0077")
            self.assertEqual(stat.S_IMODE((root / "checkpoint").stat().st_mode), 0o700)
            for path in [root / "checkpoint/before", root / "checkpoint/after", root / "parent-mask"]:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual((root / "args").read_text().splitlines(), ["install", "-g", "--prefix", "/usr", "--prefer-offline", "--allow-scripts=openclaw", "/fixture/package with spaces.tgz"])

    def test_success_keeps_private_parent_mask_and_exact_npm_options(self):
        self.run_phase(0)

    def test_failure_propagates_without_changing_private_parent_mask(self):
        self.run_phase(7)

    def test_authoritative_phase_shell_syntax(self):
        self.assertEqual(subprocess.run(["/bin/bash", "-n", str(PHASE)], capture_output=True, timeout=5).returncode, 0)


WALK_AS_SERVICE_USER = r'''
import json, os, pathlib, stat, sys
root = pathlib.Path(sys.argv[1])
errors = []
counts = {"directories": 0, "regular_files": 0, "symlinks": 0}
def failed(error):
    errors.append({"path": error.filename, "errno": error.errno})
for directory, dirs, files in os.walk(root, followlinks=False, onerror=failed):
    counts["directories"] += 1
    if not os.access(directory, os.R_OK | os.X_OK):
        errors.append({"path": directory, "category": "directory_access"})
    for name in dirs + files:
        path = pathlib.Path(directory) / name
        try:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                counts["symlinks"] += 1
                path = path.resolve(strict=True)
                metadata = path.stat()
            if stat.S_ISREG(metadata.st_mode):
                counts["regular_files"] += 1
                with path.open("rb") as stream:
                    stream.read(1)
                if (pathlib.Path(directory) == root / "bin" or pathlib.Path(directory).name == ".bin") and not os.access(path, os.X_OK):
                    errors.append({"path": str(path), "category": "executable_access"})
        except OSError as error:
            failed(error)
print(json.dumps({"uid": os.getuid(), "counts": counts, "errors": errors}))
sys.exit(1 if errors else 0)
'''


def native_root_fixture(root, artifact, retained_cache, validate_only=False):
    """Two offline npm installs in an owned namespace, never a host prefix."""
    root, artifact, retained_cache = [pathlib.Path(p).resolve(strict=True) for p in [root, artifact, retained_cache]]
    if os.getuid() != 0 or root.parent != pathlib.Path("/dev/shm") or not root.name.startswith("jd-crustacea-core-mask-"):
        raise RuntimeError("root fixture requires its resolved owned /dev/shm root")
    if pathlib.Path("/proc/self/ns/net").readlink() == pathlib.Path("/proc/1/ns/net").readlink():
        raise RuntimeError("root fixture requires a private network namespace")
    service = pwd.getpwnam("aimee")
    if service.pw_uid == 0 or root.stat().st_uid != service.pw_uid:
        raise RuntimeError("fixture root must be owned by the non-root service user")
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != "908c809914cd95a7af9cbf84406eab01c96c89ecd8072aec96f04d00e81ed987":
        raise RuntimeError("fixture requires the frozen exact-3a core package")
    os.umask(0o022)
    fixture = root / "native"
    if not validate_only:
        subprocess.run(["/usr/bin/mount", "--make-rprivate", "/"], check=True, timeout=5)
        fixture.mkdir(mode=0o755)
        for name in ["cache-upper", "cache-work", "cache", "root-home", "logs"]:
            (fixture / name).mkdir(mode=0o700)
        subprocess.run(["/usr/bin/mount", "-t", "overlay", "overlay", "-o", f"lowerdir={retained_cache},upperdir={fixture / 'cache-upper'},workdir={fixture / 'cache-work'}", str(fixture / "cache")], check=True, timeout=5)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(fixture / "root-home"), "npm_config_cache": str(fixture / "cache"), "npm_config_offline": "true", "npm_config_audit": "false", "npm_config_fund": "false", "npm_config_update_notifier": "false", "npm_config_logs_dir": str(fixture / "logs")}
    service_home = root / "service-home"
    if not validate_only:
        service_home.mkdir(mode=0o700)
        os.chown(service_home, service.pw_uid, service.pw_gid)
    service_env = ["/usr/bin/env", "HOME=" + str(service_home), "OPENCLAW_STATE_DIR=" + str(service_home / "state"), "OPENCLAW_CONFIG_PATH=" + str(service_home / "missing.json")]
    as_service = ["/usr/bin/sudo", "-n", "-u", "aimee"]
    outcomes = []
    for corrected in [False, True]:
        label = "root-077-original-defect" if not corrected else "root-022-corrected"
        case = fixture / label
        if not validate_only:
            case.mkdir(mode=0o755)
        prefix = case / "prefix"
        phase = case / "phase.commands"
        body = PHASE.read_text().replace("sudo /bin/bash", "/bin/bash", 1).replace("--prefix /usr", "--prefix " + shlex.quote(str(prefix)), 1)
        if not corrected:
            body = body.replace("    umask 022\n", "", 1)
        if validate_only:
            if phase.read_text() != body:
                raise RuntimeError("retained installed fixture command differs from authoritative phase")
        else:
            phase.write_text(body)
            phase.chmod(0o600)
        shell = 'set -euo pipefail; umask 077; mkdir "$3/checkpoint"; touch "$3/checkpoint/before"; CORE_TGZ="$1"; source "$2"; umask > "$3/parent-mask"; touch "$3/checkpoint/after"'
        if validate_only:
            # The after checkpoint is created only after the fail-fast installer.
            if not (case / "checkpoint/after").is_file():
                raise RuntimeError("no successful retained root install checkpoint")
            install = subprocess.CompletedProcess([], 0, (case / "npm.stdout").read_bytes(), (case / "npm.stderr").read_bytes())
        else:
            install = subprocess.run(["/bin/bash", "-c", shell, label, str(artifact), str(phase), str(case)], env=env, capture_output=True, timeout=180)
            (case / "npm.stdout").write_bytes(install.stdout)
            (case / "npm.stderr").write_bytes(install.stderr)
        if install.returncode:
            raise RuntimeError(label + " offline npm install failed: " + str(install.returncode))
        if (case / "parent-mask").read_text().strip() != "0077" or stat.S_IMODE((case / "checkpoint").stat().st_mode) != 0o700 or any(stat.S_IMODE((case / name).stat().st_mode) != 0o600 for name in ["checkpoint/before", "checkpoint/after", "parent-mask"]):
            raise RuntimeError("private checkpoint mask changed")
        walk = subprocess.run(as_service + ["/usr/bin/python3", "-B", "-c", WALK_AS_SERVICE_USER, str(prefix)], capture_output=True, timeout=60)
        closure = json.loads(walk.stdout)
        cli = subprocess.run(as_service + service_env + [str(prefix / "bin/openclaw"), "--help"], capture_output=True, timeout=30)
        plugin_help = None
        imports = None
        inventory = None
        if corrected:
            plugin_help = subprocess.run(as_service + service_env + [str(prefix / "bin/openclaw"), "plugins", "install", "--help"], capture_output=True, timeout=30)
            dist = prefix / "lib/node_modules/openclaw/dist"
            js = 'const w=await import(process.argv[1]);const l=await import(process.argv[2]);if(typeof w.i!=="function"||typeof l.t!=="function")process.exit(41);'
            imports = subprocess.run(as_service + service_env + ["/usr/bin/node", "--input-type=module", "-e", js, (dist / "installed-plugin-index-store-write-BUPxwvHC.mjs").as_uri(), (dist / "plugin-lifecycle-lease-wd6DQWlj.mjs").as_uri()], capture_output=True, timeout=30)
            inventory = subprocess.run(as_service + service_env + ["/usr/bin/npm", "ls", "-g", "--prefix", str(prefix), "--omit=dev", "--json", "--all"], capture_output=True, timeout=30)
            (case / "dependency-inventory.json").write_bytes(inventory.stdout)
            identity = json.loads((dist / "build-info.json").read_text())
            if identity.get("commit") != "3a64756280280bdec52ce892c4c8c6e86b5181e3":
                raise RuntimeError("installed build identity differs from frozen 3a")
            owners = [str(p.relative_to(prefix)) for p in prefix.rglob("*") if p.lstat().st_uid != 0]
            if walk.returncode or cli.returncode or plugin_help.returncode or imports.returncode or inventory.returncode or owners:
                raise RuntimeError("corrected root-to-aimee prefix/entrypoint/import gate failed")
        elif walk.returncode == 0 or cli.returncode != 126:
            raise RuntimeError("original root-077 permission defect was not reproduced")
        result = {"case": label, "npm_exit": install.returncode, "installer_uid": 0, "service_uid": service.pw_uid, "prefix_mode": oct(stat.S_IMODE(prefix.stat().st_mode)), "closure": closure, "entrypoint_help_exit": cli.returncode, "plugin_help_exit": None if plugin_help is None else plugin_help.returncode, "pinned_module_import_exit": None if imports is None else imports.returncode, "dependency_inventory_exit": None if inventory is None else inventory.returncode, "parent_umask": "0077", "checkpoint_directory_mode": "0700", "checkpoint_file_mode": "0600", "npm_stderr_sha256": hashlib.sha256(install.stderr).hexdigest(), "install_scripts_warning_present": b"npm warn install-scripts" in install.stderr}
        outcomes.append(result)
        (case / "RESULT.json").write_text(json.dumps(result, indent=2) + "\n")
    receipt = {"status": "pass", "phase_sha256": hashlib.sha256(PHASE.read_bytes()).hexdigest(), "test_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(), "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(), "npm": subprocess.check_output(["/usr/bin/npm", "--version"], text=True).strip(), "node": subprocess.check_output(["/usr/bin/node", "--version"], text=True).strip(), "namespace": "private mount and network", "offline": True, "retained_cache": "read-only overlay lower; writes owned upper only", "install_evidence": "retained successful root-created prefixes; read-only closure revalidation" if validate_only else "fresh root npm installs", "fixture_only_substitutions": ["prefix /usr replaced by resolved owned case prefix", "outer sudo omitted because installer already root", "original-defect control omits child umask 022"], "production_actions": False, "outcomes": outcomes}
    (root / "ROOT-TO-AIMEE-VALIDATION.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] in {"--native-root-fixture", "--validate-native-root-fixture"}:
        native_root_fixture(*sys.argv[2:], validate_only=sys.argv[1] == "--validate-native-root-fixture")
    else:
        unittest.main()
