import argparse
import hmac
import ipaddress
import json
import os
import re
import shutil
import socketserver
import subprocess
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable


VERSION_PATTERN = re.compile(r"^v?\d+\.\d+\.\d+(?:[-.][A-Za-z0-9.-]+)?$")
REPOSITORY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$")
DATABASE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
IMAGE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,299}$")


class AgentError(RuntimeError):
    def __init__(self, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class AgentConfig:
    token: str
    socket_path: Path = Path("/run/wolt-agent/agent.sock")
    socket_group_gid: int = -1
    state_file: Path = Path("/var/lib/wolt-agent/state.json")
    project_dir: Path = Path("/data/WOLT")
    compose_file: Path = Path("/data/WOLT/compose.web.yml")
    host_agent_compose_file: Path = Path("/data/WOLT/compose.host-agent.yml")
    env_file: Path = Path("/data/WOLT/.env.web")
    image_repository: str = "alirezasayyari/wolt"
    health_url: str = "http://127.0.0.1:8080/api/v1/health/ready"
    docker_binary: str = "/usr/bin/docker"
    ufw_binary: str = "/usr/sbin/ufw"
    cosign_binary: str = "/usr/local/bin/cosign"
    signing_identity: str = r"^https://github.com/AlirezaSayyari/WOLT/.github/workflows/release.yml@refs/tags/v[0-9]+\.[0-9]+\.[0-9]+.*$"
    signing_issuer: str = "https://token.actions.githubusercontent.com"

    @classmethod
    def from_env(cls) -> "AgentConfig":
        token = os.environ.get("WOLT_HOST_AGENT_TOKEN", "")
        if len(token) < 32:
            raise AgentError("host_agent_token_too_short")
        project = Path(os.environ.get("WOLT_PROJECT_DIR", "/data/WOLT")).resolve()
        compose = Path(os.environ.get("WOLT_COMPOSE_FILE", str(project / "compose.web.yml"))).resolve()
        host_compose = Path(os.environ.get("WOLT_HOST_AGENT_COMPOSE_FILE", str(project / "compose.host-agent.yml"))).resolve()
        env_file = Path(os.environ.get("WOLT_ENV_FILE", str(project / ".env.web"))).resolve()
        for candidate in (compose, host_compose, env_file):
            try:
                candidate.relative_to(project)
            except ValueError as exc:
                raise AgentError("host_agent_path_outside_project") from exc
        repository = os.environ.get("WOLT_IMAGE_REPOSITORY", "alirezasayyari/wolt").strip().lower()
        if not REPOSITORY_PATTERN.fullmatch(repository):
            raise AgentError("invalid_image_repository")
        return cls(
            token=token,
            socket_path=Path(os.environ.get("WOLT_HOST_AGENT_SOCKET", "/run/wolt-agent/agent.sock")),
            socket_group_gid=int(os.environ.get("WOLT_HOST_AGENT_GID", "-1")),
            state_file=Path(os.environ.get("WOLT_HOST_AGENT_STATE", "/var/lib/wolt-agent/state.json")),
            project_dir=project, compose_file=compose,
            host_agent_compose_file=host_compose, env_file=env_file,
            image_repository=repository,
            health_url=os.environ.get("WOLT_HEALTH_URL", "http://127.0.0.1:8080/api/v1/health/ready"),
            docker_binary=os.environ.get("WOLT_DOCKER_BINARY", "/usr/bin/docker"),
            ufw_binary=os.environ.get("WOLT_UFW_BINARY", "/usr/sbin/ufw"),
            cosign_binary=os.environ.get("WOLT_COSIGN_BINARY", "/usr/local/bin/cosign"),
        )


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def read(self) -> dict[str, Any]:
        with self.lock:
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                return {}

    def write(self, state: dict[str, Any]) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)


class HostController:
    def __init__(
        self,
        config: AgentConfig,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.config = config
        self.runner = runner
        self.opener = opener
        self.store = StateStore(config.state_file)
        self.jobs: dict[str, dict[str, Any]] = {}
        self.jobs_lock = threading.Lock()

    def _run(self, arguments: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
        try:
            result = self.runner(
                arguments, check=False, capture_output=True, text=True, timeout=timeout,
                cwd=self.config.project_dir,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentError("host_command_failed", 502) from exc
        if result.returncode != 0:
            raise AgentError("host_command_failed", 502)
        return result

    @staticmethod
    def _network_values(source_ip: str, start: int, end: int) -> tuple[str, int, int]:
        try:
            source = str(ipaddress.ip_address(source_ip))
        except ValueError as exc:
            raise AgentError("invalid_firewall_source_ip") from exc
        if not 1024 <= start <= end <= 65535:
            raise AgentError("invalid_published_udp_range")
        if end - start + 1 > 100:
            raise AgentError("published_udp_range_too_wide")
        return source, start, end

    def _ufw_rule(self, source: str, start: int, end: int, *, delete: bool = False) -> list[str]:
        arguments = [self.config.ufw_binary, "--force"]
        if delete:
            arguments.append("delete")
        arguments.extend([
            "allow", "proto", "udp", "from", source, "to", "any", "port",
            f"{start}:{end}", "comment", "WOLT-managed",
        ])
        return arguments

    def status(self) -> dict[str, Any]:
        state = self.store.read()
        ufw_available = Path(self.config.ufw_binary).is_file()
        docker_available = Path(self.config.docker_binary).is_file()
        cosign_available = Path(self.config.cosign_binary).is_file()
        ufw_active = False
        if ufw_available:
            try:
                output = self._run([self.config.ufw_binary, "status"], timeout=10).stdout
                ufw_active = "Status: active" in output
            except AgentError:
                pass
        return {
            "agent_version": "1.0.0", "ufw_available": ufw_available,
            "ufw_active": ufw_active, "docker_available": docker_available,
            "cosign_available": cosign_available,
            "image_repository": self.config.image_repository,
            "managed_firewall": state.get("firewall"),
            "deployment": state.get("deployment"),
            "last_successful": state.get("last_successful"),
            "capabilities": ["ufw", "published_udp_range", "upgrade", "rollback"],
        }

    def firewall_preview(self, source_ip: str, start: int, end: int) -> dict[str, Any]:
        source, start, end = self._network_values(source_ip, start, end)
        previous = self.store.read().get("firewall")
        return {
            "source_ip": source, "udp_start": start, "udp_end": end,
            "previous": previous,
            "actions": ["remove_previous_wolt_rule"] if previous and previous != {
                "source_ip": source, "udp_start": start, "udp_end": end
            } else [],
            "rule": f"allow UDP {start}:{end} from {source}",
        }

    def apply_firewall(self, source_ip: str, start: int, end: int) -> dict[str, Any]:
        preview = self.firewall_preview(source_ip, start, end)
        previous = preview["previous"]
        current = {
            "source_ip": preview["source_ip"],
            "udp_start": preview["udp_start"], "udp_end": preview["udp_end"],
        }
        if previous and previous != current:
            self._run(self._ufw_rule(
                previous["source_ip"], int(previous["udp_start"]),
                int(previous["udp_end"]), delete=True,
            ), timeout=20)
        self._run(self._ufw_rule(
            current["source_ip"], current["udp_start"], current["udp_end"]
        ), timeout=20)
        state = self.store.read()
        state["firewall"] = current
        self.store.write(state)
        return current

    def remove_firewall(self) -> None:
        state = self.store.read()
        current = state.get("firewall")
        if current:
            self._run(self._ufw_rule(
                current["source_ip"], int(current["udp_start"]),
                int(current["udp_end"]), delete=True,
            ), timeout=20)
            state.pop("firewall", None)
            self.store.write(state)

    def releases(self) -> dict[str, Any]:
        namespace, repository = self.config.image_repository.split("/", 1)
        url = f"https://hub.docker.com/v2/repositories/{namespace}/{repository}/tags?page_size=50&ordering=last_updated"
        try:
            with self.opener(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise AgentError("release_discovery_failed", 502) from exc
        results = [
            {"name": row["name"], "digest": row.get("digest"), "updated_at": row.get("last_updated")}
            for row in payload.get("results", []) if VERSION_PATTERN.fullmatch(str(row.get("name", "")))
        ]
        return {"repository": self.config.image_repository, "releases": results}

    def _compose(self, *arguments: str, timeout: int = 300) -> None:
        self._run([
            self.config.docker_binary, "compose", "--project-directory", str(self.config.project_dir),
            "--env-file", str(self.config.env_file), "-f", str(self.config.compose_file),
            "-f", str(self.config.host_agent_compose_file),
            *arguments,
        ], timeout=timeout)

    def _current_image(self) -> str:
        container = self._run([
            self.config.docker_binary, "compose", "--project-directory", str(self.config.project_dir),
            "--env-file", str(self.config.env_file), "-f", str(self.config.compose_file),
            "-f", str(self.config.host_agent_compose_file), "ps", "-q", "app",
        ], timeout=30).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{12,64}", container):
            raise AgentError("current_image_unavailable", 502)
        image = self._run([
            self.config.docker_binary, "inspect", "--format={{.Config.Image}}", container,
        ], timeout=30).stdout.strip()
        if not IMAGE_REFERENCE_PATTERN.fullmatch(image):
            raise AgentError("current_image_unavailable", 502)
        return image

    def _env_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in self.config.env_file.read_text(encoding="utf-8").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
        return values

    def _update_env(self, changes: dict[str, str]) -> None:
        path = self.config.env_file
        if path.is_symlink() or not path.is_file():
            raise AgentError("unsafe_environment_file")
        lines = path.read_text(encoding="utf-8").splitlines()
        remaining = dict(changes)
        output: list[str] = []
        for line in lines:
            if line and not line.lstrip().startswith("#") and "=" in line:
                key = line.split("=", 1)[0]
                if key in remaining:
                    output.append(f"{key}={remaining.pop(key)}")
                    continue
            output.append(line)
        output.extend(f"{key}={value}" for key, value in remaining.items())
        backup = path.with_suffix(path.suffix + ".host-agent-backup")
        shutil.copy2(path, backup)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    def _healthy(self, timeout: int = 120) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with self.opener(self.config.health_url, timeout=3) as response:
                    if response.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def _database_identity(self) -> tuple[str, str]:
        values = self._env_values()
        user = values.get("WOLT_DB_USER", "wolt").strip("'\"")
        database = values.get("WOLT_DB_NAME", "wolt").strip("'\"")
        if not DATABASE_IDENTIFIER_PATTERN.fullmatch(user) or not DATABASE_IDENTIFIER_PATTERN.fullmatch(database):
            raise AgentError("invalid_database_identity")
        return user, database

    def _database_backup(self) -> Path:
        user, database = self._database_identity()
        backup_dir = self.config.state_file.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        path = backup_dir / f"pre-upgrade-{uuid.uuid4()}.dump"
        arguments = [
            self.config.docker_binary, "compose", "--project-directory", str(self.config.project_dir),
            "--env-file", str(self.config.env_file), "-f", str(self.config.compose_file),
            "-f", str(self.config.host_agent_compose_file), "exec", "-T", "postgres",
            "pg_dump", "--format=custom", "--no-owner", "-U", user, "-d", database,
        ]
        try:
            with path.open("wb") as output:
                result = self.runner(
                    arguments, check=False, stdout=output, stderr=subprocess.PIPE,
                    timeout=600, cwd=self.config.project_dir,
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            path.unlink(missing_ok=True)
            raise AgentError("database_backup_failed", 502) from exc
        if result.returncode != 0 or not path.is_file() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            raise AgentError("database_backup_failed", 502)
        os.chmod(path, 0o600)
        return path

    def _database_restore(self, backup: Path) -> None:
        try:
            backup = backup.resolve(strict=True)
            backup.relative_to((self.config.state_file.parent / "backups").resolve())
        except (FileNotFoundError, ValueError) as exc:
            raise AgentError("database_backup_unavailable") from exc
        user, database = self._database_identity()
        self._compose("stop", "app", timeout=120)
        prefix = [
            self.config.docker_binary, "compose", "--project-directory", str(self.config.project_dir),
            "--env-file", str(self.config.env_file), "-f", str(self.config.compose_file),
            "-f", str(self.config.host_agent_compose_file), "exec", "-T", "postgres",
        ]
        self._run(prefix + ["dropdb", "--force", "-U", user, database], timeout=120)
        self._run(prefix + ["createdb", "-U", user, database], timeout=120)
        try:
            with backup.open("rb") as source:
                result = self.runner(
                    prefix + ["pg_restore", "--no-owner", "--no-privileges", "-U", user, "-d", database],
                    check=False, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=600, cwd=self.config.project_dir,
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentError("database_restore_failed", 502) from exc
        if result.returncode != 0:
            raise AgentError("database_restore_failed", 502)

    def _verified_image(self, version: str) -> str:
        if not Path(self.config.cosign_binary).is_file():
            raise AgentError("signature_verification_unavailable", 503)
        tagged_image = f"{self.config.image_repository}:{version}"
        result = self._run([
            self.config.cosign_binary, "verify", "--output", "json",
            "--certificate-identity-regexp", self.config.signing_identity,
            "--certificate-oidc-issuer", self.config.signing_issuer,
            tagged_image,
        ], timeout=120)
        try:
            entries = json.loads(result.stdout)
            digest = entries[0]["critical"]["image"]["docker-manifest-digest"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise AgentError("signature_verification_failed", 502) from exc
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(digest)):
            raise AgentError("signature_verification_failed", 502)
        return f"{self.config.image_repository}@{digest}"

    def start_job(self, operation: str, payload: dict[str, Any]) -> dict[str, str]:
        if operation not in {"deployment", "upgrade", "rollback"}:
            raise AgentError("unsupported_host_operation")
        with self.jobs_lock:
            if any(job["status"] == "running" for job in self.jobs.values()):
                raise AgentError("host_operation_in_progress", 409)
            job_id = str(uuid.uuid4())
            self.jobs[job_id] = {"id": job_id, "operation": operation, "status": "running", "error": None}
        threading.Thread(target=self._execute_job, args=(job_id, operation, payload), daemon=True).start()
        return {"job_id": job_id}

    def job(self, job_id: str) -> dict[str, Any]:
        with self.jobs_lock:
            if job_id not in self.jobs:
                raise AgentError("host_job_not_found", 404)
            return dict(self.jobs[job_id])

    def _execute_job(self, job_id: str, operation: str, payload: dict[str, Any]) -> None:
        try:
            if operation == "deployment":
                source, start, end = self._network_values(
                    str(payload.get("source_ip", "")), int(payload.get("udp_start", 0)), int(payload.get("udp_end", 0))
                )
                old = self._env_values()
                rollback_env = {
                    "WOLT_UDP_PUBLISHED_START": old.get("WOLT_UDP_PUBLISHED_START", "40000"),
                    "WOLT_UDP_PUBLISHED_END": old.get("WOLT_UDP_PUBLISHED_END", "40099"),
                }
                previous_firewall = self.store.read().get("firewall")
                self._update_env({"WOLT_UDP_PUBLISHED_START": str(start), "WOLT_UDP_PUBLISHED_END": str(end)})
                self.apply_firewall(source, start, end)
                self._compose("up", "-d", "--no-build", "app")
                if not self._healthy():
                    self._update_env(rollback_env)
                    if previous_firewall:
                        self.apply_firewall(previous_firewall["source_ip"], int(previous_firewall["udp_start"]), int(previous_firewall["udp_end"]))
                    else:
                        self.remove_firewall()
                    self._compose("up", "-d", "--no-build", "app")
                    raise AgentError("deployment_health_check_failed", 502)
                state = self.store.read(); state["deployment"] = {"udp_start": start, "udp_end": end}; state["rollback"] = {"env": rollback_env, "firewall": previous_firewall}; self.store.write(state)
            elif operation == "upgrade":
                version = str(payload.get("version", ""))
                if not VERSION_PATTERN.fullmatch(version):
                    raise AgentError("invalid_release_version")
                old = self._env_values()
                old_image = old.get("WOLT_IMAGE") or self._current_image()
                new_image = self._verified_image(version)
                backup = self._database_backup()
                self._run([self.config.docker_binary, "pull", new_image], timeout=600)
                self._update_env({"WOLT_IMAGE": new_image})
                self._compose("up", "-d", "--no-build", "app", timeout=600)
                if not self._healthy():
                    self._update_env({"WOLT_IMAGE": old_image})
                    self._database_restore(backup)
                    self._compose("up", "-d", "--no-build", "app", timeout=600)
                    raise AgentError("upgrade_health_check_failed", 502)
                state = self.store.read()
                previous_backup = state.get("rollback", {}).get("database_backup")
                if previous_backup:
                    Path(previous_backup).unlink(missing_ok=True)
                state["rollback"] = {"env": {"WOLT_IMAGE": old_image}, "database_backup": str(backup)}
                state["last_successful"] = {"image": new_image, "at": int(time.time())}
                self.store.write(state)
            else:
                state = self.store.read(); rollback = state.get("rollback")
                if not rollback:
                    raise AgentError("rollback_not_available")
                rollback_env = rollback.get("env", {})
                if not rollback_env:
                    raise AgentError("rollback_not_available")
                self._update_env({key: str(value) for key, value in rollback_env.items()})
                if rollback.get("database_backup"):
                    self._database_restore(Path(rollback["database_backup"]))
                if "firewall" in rollback:
                    previous_firewall = rollback["firewall"]
                    if previous_firewall:
                        self.apply_firewall(previous_firewall["source_ip"], int(previous_firewall["udp_start"]), int(previous_firewall["udp_end"]))
                    else:
                        self.remove_firewall()
                self._compose("up", "-d", "--no-build", "app", timeout=600)
                if not self._healthy():
                    raise AgentError("rollback_health_check_failed", 502)
            with self.jobs_lock:
                self.jobs[job_id]["status"] = "succeeded"
        except Exception as exc:
            detail = exc.detail if isinstance(exc, AgentError) else "host_operation_failed"
            with self.jobs_lock:
                self.jobs[job_id]["status"] = "failed"
                self.jobs[job_id]["error"] = detail


class AgentRequestHandler(BaseHTTPRequestHandler):
    server: "AgentServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _response(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.config.token}"
        return hmac.compare_digest(header, expected)

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 16384:
            raise AgentError("request_too_large", 413)
        try:
            value = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError as exc:
            raise AgentError("invalid_json") from exc
        if not isinstance(value, dict):
            raise AgentError("invalid_json")
        return value

    def _dispatch(self) -> dict[str, Any]:
        controller = self.server.controller
        if self.command == "GET" and self.path == "/v1/status":
            return controller.status()
        if self.command == "GET" and self.path == "/v1/releases":
            return controller.releases()
        if self.command == "GET" and self.path.startswith("/v1/jobs/"):
            return controller.job(self.path.rsplit("/", 1)[-1])
        payload = self._payload()
        if self.command == "POST" and self.path == "/v1/firewall/preview":
            return controller.firewall_preview(str(payload.get("source_ip", "")), int(payload.get("udp_start", 0)), int(payload.get("udp_end", 0)))
        if self.command == "POST" and self.path == "/v1/firewall/apply":
            return controller.apply_firewall(str(payload.get("source_ip", "")), int(payload.get("udp_start", 0)), int(payload.get("udp_end", 0)))
        if self.command == "POST" and self.path in {"/v1/deployment", "/v1/upgrade", "/v1/rollback"}:
            return controller.start_job(self.path.rsplit("/", 1)[-1], payload)
        raise AgentError("not_found", 404)

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def _handle(self) -> None:
        if not self._authorized():
            self._response(401, {"detail": "unauthorized"})
            return
        try:
            self._response(200, self._dispatch())
        except AgentError as exc:
            self._response(exc.status, {"detail": exc.detail})
        except (TypeError, ValueError):
            self._response(422, {"detail": "invalid_request"})


class AgentServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, config: AgentConfig, controller: HostController) -> None:
        config.socket_path.parent.mkdir(parents=True, exist_ok=True)
        config.socket_path.unlink(missing_ok=True)
        self.config = config
        self.controller = controller
        super().__init__(str(config.socket_path), AgentRequestHandler)
        os.chmod(config.socket_path, 0o660)
        if config.socket_group_gid >= 0:
            os.chown(config.socket_path, 0, config.socket_group_gid)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restricted WOLT host agent")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = AgentConfig.from_env()
    if args.check:
        print(json.dumps(HostController(config).status()))
        return 0
    with AgentServer(config, HostController(config)) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
