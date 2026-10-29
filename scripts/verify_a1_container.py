"""A1 smoke against a built image: isolated volumes, no external runtime network.

Build the repository Dockerfile first, then run this script on the Docker host.
No .env, real reports, model credentials or existing deployment resources are used.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4


DATA = "/usr/src/app/data"
ENVIRONMENT = ["-e", f"TDR_DATABASE_URL=sqlite:///{DATA}/tdr.db",
               "-e", f"REPORT_STORE_PATH={DATA}/reports.json",
               "-e", "TDR_BLOCK_NETWORK=1", "-e", "LANGSMITH_TRACING=false",
               "-e", "LANGCHAIN_TRACING_V2=false"]
REQUEST = """
import json, sys, urllib.request, urllib.error
command = json.load(sys.stdin)
body = command.get('data')
request = urllib.request.Request('http://127.0.0.1:8000' + command['path'],
    method=command['method'], data=None if body is None else json.dumps(body).encode(),
    headers={'Content-Type': 'application/json'})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    response = opener.open(request, timeout=3)
except urllib.error.HTTPError as error:
    response = error
print(json.dumps({'status': response.code, 'body': json.loads(response.read())}))
"""


def docker(*args, stdin=None, check=True, timeout=120):
    result = subprocess.run(["docker", *args], input=stdin, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {(result.stderr or result.stdout)[-6000:]}")
    return result


class Smoke:
    def __init__(self, image):
        self.image = image
        self.prefix = "tdr-a1-" + uuid4().hex[:12]
        self.volumes = []
        self.containers = set()
        self.helper_number = 0
        self.checks = []

    def passed(self, name):
        self.checks.append(name)
        print("PASS " + name, flush=True)

    def volume(self, suffix):
        name = self.prefix + "-" + suffix
        self.volumes.append(name)
        docker("volume", "create", "--label", "tdr.validation=a1",
               "--label", "tdr.validation.run=" + self.prefix, name)
        return name

    def helper(self, volume, *command, stdin=None, extra_mounts=(), timeout=120):
        self.helper_number += 1
        name = self.prefix + f"-helper-{self.helper_number}"
        self.containers.add(name)
        try:
            return docker("run", "--rm", "--name", name,
                          "--label", "tdr.validation.run=" + self.prefix,
                          "--network", "none", "-i", *ENVIRONMENT,
                          "--mount", f"type=volume,src={volume},dst={DATA}", *extra_mounts,
                          self.image, *command, stdin=stdin, timeout=timeout).stdout.strip()
        finally:
            self.remove_owned_container(name)

    def python(self, volume, code, *, extra_mounts=()):
        return self.helper(volume, "python", "-c", code, extra_mounts=extra_mounts)

    def migrate(self, volume, *flags):
        return json.loads(self.helper(volume, "python", "scripts/migrate_report_store.py", *flags))

    def start(self, volume, suffix):
        name = self.prefix + "-" + suffix
        self.containers.add(name)
        docker("run", "-d", "--name", name, "--label", "tdr.validation=a1",
               "--label", "tdr.validation.run=" + self.prefix,
               "--network", "none", *ENVIRONMENT,
               "--mount", f"type=volume,src={volume},dst={DATA}", self.image)
        return name

    def request(self, container, path, method="GET", data=None):
        result = docker("exec", "-i", container, "python", "-c", REQUEST,
                        stdin=json.dumps({"method": method, "path": path, "data": data}), timeout=15)
        return json.loads(result.stdout)

    def ready(self, container):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if self.request(container, "/api/reports")["status"] == 200:
                    return
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                pass
            running = docker("inspect", "--format", "{{.State.Running}}", container).stdout.strip()
            if running != "true":
                break
            time.sleep(1)
        raise RuntimeError("API did not become ready: " + docker("logs", "--tail", "60", container).stderr[-6000:])

    def remove(self, container):
        docker("stop", "--time", "15", container)
        self.remove_owned_container(container)

    def remove_owned_container(self, container):
        inspected = docker("inspect", container, check=False)
        if inspected.returncode:
            if "no such" in inspected.stderr.lower():
                self.containers.discard(container)
                return
            raise RuntimeError(inspected.stderr)
        labels = json.loads(inspected.stdout)[0]["Config"].get("Labels") or {}
        if labels.get("tdr.validation.run") != self.prefix:
            raise RuntimeError("Refusing to remove a container owned by another run: " + container)
        docker("rm", "-f", container)
        self.containers.discard(container)

    def refused(self, volume, suffix, expected):
        container = self.start(volume, suffix)
        exit_code = docker("wait", container, timeout=120).stdout.strip()
        logs = docker("logs", container)
        assert exit_code != "0" and expected in logs.stdout + logs.stderr, (exit_code, logs.stderr[-6000:])
        self.remove_owned_container(container)

    def cleanup(self):
        failures = []
        for name in list(self.containers):
            try:
                self.remove_owned_container(name)
            except Exception as exc:
                failures.append(str(exc))
        for name in reversed(self.volumes):
            try:
                inspected = docker("volume", "inspect", name, check=False)
                if inspected.returncode:
                    if "no such" in inspected.stderr.lower():
                        continue
                    raise RuntimeError(inspected.stderr)
                labels = json.loads(inspected.stdout)[0].get("Labels") or {}
                if labels.get("tdr.validation.run") != self.prefix:
                    raise RuntimeError("Refusing to remove a volume owned by another run: " + name)
                docker("volume", "rm", name)
            except Exception as exc:
                failures.append(str(exc))
        return failures

    def run(self):
        inspection = json.loads(docker("image", "inspect", self.image).stdout)[0]
        assert inspection["Os"] == "linux" and inspection["Config"]["User"] not in {None, "", "root", "0"}
        self.image_id = inspection["Id"]
        volume = self.volume("data")
        self.versions = json.loads(self.python(volume, "import json, sys, sqlite3, sqlalchemy, fastapi; print(json.dumps({'python': sys.version.split()[0], 'sqlite': sqlite3.sqlite_version, 'sqlalchemy': sqlalchemy.__version__, 'fastapi': fastapi.__version__}))"))
        self.python(volume, "from pathlib import Path; assert not Path('/usr/src/app/.env').exists(); assert not Path('/usr/src/app/evals/results').exists()")
        self.passed("image excludes real .env and local evaluation output")
        assert int(self.python(volume, "import os; print(os.getuid())")) != 0

        records = {"legacy": {"id": "legacy", "question": "中文问题😀", "answer": "原始正文",
                   "timestamp": 1000, "orderedData": [],
                   "chatMessages": [{"role": "user", "content": "历史追问😀", "timestamp": 1001}]},
                   "other": {"id": "other", "answer": "另一个报告", "timestamp": 500}}
        source = json.dumps(records, ensure_ascii=False).encode("utf-8")
        code = f"from pathlib import Path; Path('{DATA}/reports.json').write_bytes(bytes.fromhex('{source.hex()}'))"
        self.python(volume, code)
        self.passed("Linux image and default non-root volume writes")
        try:
            self.helper(volume, "python", "-u", "-c",
                        "import time; print('helper-started', flush=True); time.sleep(20)", timeout=5)
        except subprocess.TimeoutExpired as exc:
            captured = exc.stdout or b""
            if isinstance(captured, bytes):
                captured = captured.decode("utf-8", errors="replace")
            assert "helper-started" in captured, "timeout probe did not reach the daemon-side process"
        else:
            raise AssertionError("helper timeout probe unexpectedly completed")
        assert not docker("ps", "-a", "--filter", "label=tdr.validation.run=" + self.prefix,
                          "--format", "{{.Names}}").stdout.strip()
        self.passed("helper client timeout removes its daemon-side container")
        preview = self.migrate(volume)
        assert preview["valid"] and preview["records"] == 2
        assert self.python(volume, f"from pathlib import Path; print(Path('{DATA}/tdr.db').exists())") == "False"
        self.passed("dry-run preserves source and does not initialize database")
        imported = self.migrate(volume, "--apply")
        assert imported["imported"] == 2 and imported["source_sha256"] == sha256(source).hexdigest()
        backup = repr(imported["backup"])
        check = self.python(volume, f"from pathlib import Path; from hashlib import sha256; print(sha256(Path({backup}).read_bytes()).hexdigest()); print(sha256(Path('{DATA}/reports.json').read_bytes()).hexdigest())")
        assert check.splitlines() == [sha256(source).hexdigest()] * 2
        self.passed("legacy import and exact-byte backup/source SHA-256")
        repeat = self.migrate(volume, "--apply")
        assert repeat["imported"] == 0 and repeat["skipped"] == 2
        self.passed("repeat migration is idempotent")

        api = self.start(volume, "api-first")
        self.ready(api)
        report = self.request(api, "/api/reports/legacy")["body"]["report"]
        assert report["question"] == "中文问题😀" and report["chatMessages"] == records["legacy"]["chatMessages"]
        assert report["origin"] == "legacy_import" and report["lineage_status"] == "unavailable"
        self.passed("real ASGI startup and imported Chinese/chat metadata")
        created = self.request(api, "/api/reports", "POST", {"id": "created", "question": "容器创建", "answer": "新正文", "timestamp": 2000})
        assert created["status"] == 200
        assert self.request(api, "/api/reports/legacy", "PUT", {"question": "更新的问题"})["status"] == 200
        page = self.request(api, "/api/reports?limit=1&offset=1")["body"]["reports"]
        assert [r["id"] for r in page] == ["created"]
        assert self.request(api, "/api/reports?limit=0")["status"] == 422
        assert self.request(api, "/api/reports/other", "DELETE")["status"] == 200
        assert self.request(api, "/api/reports/other")["status"] == 404
        self.passed("real HTTP CRUD, pagination and request validation")
        self.remove(api)
        api = self.start(volume, "api-replaced")
        self.ready(api)
        saved = self.request(api, "/api/reports/legacy")["body"]["report"]
        assert saved["question"] == "更新的问题" and saved["chatMessages"] == records["legacy"]["chatMessages"]
        assert self.request(api, "/api/reports/created")["body"]["report"]["answer"] == "新正文"
        assert len(self.request(api, "/api/reports")["body"]["reports"]) == 2
        self.passed("container replacement preserves reports, chats and deletion")
        self.remove(api)

        restored = self.volume("restored")
        self.python(restored, f"import shutil; shutil.copytree('/source', '{DATA}', dirs_exist_ok=True)",
                    extra_mounts=("--mount", f"type=volume,src={volume},dst=/source,readonly"))
        api = self.start(restored, "api-restored")
        self.ready(api)
        assert self.request(api, "/api/reports/legacy")["body"]["report"]["question"] == "更新的问题"
        assert self.request(api, "/api/reports/created")["body"]["report"]["answer"] == "新正文"
        assert len(self.request(api, "/api/reports")["body"]["reports"]) == 2
        self.passed("stopped-volume backup restores into independent volume")
        self.remove(api)

        negative = self.volume("negative")
        self.refused(negative, "missing-schema", "Storage is not initialized")
        self.passed("uninitialized schema refuses API startup")
        self.migrate(negative, "--init-only")
        self.python(negative, f"import sqlite3; c=sqlite3.connect('{DATA}/tdr.db'); c.execute('UPDATE schema_migrations SET version=999'); c.commit()")
        self.refused(negative, "unknown-schema", "Unsupported or modified storage schema")
        self.passed("unknown schema version refuses API startup")
        self.python(negative, f"import sqlite3; from pathlib import Path; c=sqlite3.connect('{DATA}/tdr.db'); c.execute('UPDATE schema_migrations SET version=1'); c.commit(); Path('{DATA}/reports.json').write_text('{{\"old\":{{\"id\":\"old\"}}}}')")
        self.refused(negative, "unimported-history", "Unmigrated or changed legacy history")
        self.passed("unimported legacy file refuses API startup")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="tdr-a1-validation:20261029")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    smoke = Smoke(args.image)
    summary = {"image": args.image, "status": "failed", "runtime_network": "none"}
    started = time.monotonic()
    try:
        smoke.run()
        summary["status"] = "passed"
    except Exception as exc:
        summary["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        failures = smoke.cleanup()
        summary.update(checks=smoke.checks, check_count=len(smoke.checks),
                       image_id=getattr(smoke, "image_id", None), versions=getattr(smoke, "versions", None),
                       elapsed_seconds=round(time.monotonic() - started, 2),
                       cleanup_errors=failures)
        if failures:
            summary["status"] = "failed"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=True), flush=True)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
