import json
import os
import subprocess
import threading
from pathlib import Path

import pytest

from app.infrastructure.host_agent import HostAgentClient, HostAgentError
from host_agent.server import AgentConfig, AgentError, AgentServer, HostController


def config(tmp_path: Path, token: str = "a" * 64) -> AgentConfig:
    project = tmp_path / "project"
    project.mkdir()
    (project / "compose.web.yml").write_text("services: {}\n", encoding="utf-8")
    (project / "compose.host-agent.yml").write_text("services: {}\n", encoding="utf-8")
    (project / ".env.web").write_text(
        "POSTGRES_PASSWORD=do-not-touch\nWOLT_UDP_PUBLISHED_START=40000\nWOLT_UDP_PUBLISHED_END=40099\n",
        encoding="utf-8",
    )
    return AgentConfig(
        token=token, socket_path=tmp_path / "agent.sock",
        state_file=tmp_path / "state.json", project_dir=project,
        compose_file=project / "compose.web.yml",
        host_agent_compose_file=project / "compose.host-agent.yml",
        env_file=project / ".env.web", docker_binary="/usr/bin/docker",
        ufw_binary="/usr/sbin/ufw",
        runtime_dir=project / "runtime",
        agent_install_dir=tmp_path / "installed-agent",
        systemd_run_binary=str(tmp_path / "missing-systemd-run"),
    )


def runtime_bundle(root: Path, version: str = "v1.1.1") -> Path:
    root.mkdir()
    (root / "scripts").mkdir()
    (root / "host_agent").mkdir()
    (root / "VERSION").write_text(version, encoding="utf-8")
    (root / "compose.web.yml").write_text("services:\n  app: {}\n", encoding="utf-8")
    (root / "compose.host-agent.yml").write_text("services:\n  app: {}\n", encoding="utf-8")
    for name in ("init-web-env.sh", "install-cosign.sh", "install-host-agent.sh"):
        (root / "scripts" / name).write_text("#!/bin/bash\n", encoding="utf-8")
    (root / "host_agent" / "__init__.py").write_text("", encoding="utf-8")
    (root / "host_agent" / "server.py").write_text("VERSION = 'new'\n", encoding="utf-8")
    return root


def test_firewall_validation_rejects_command_injection(tmp_path: Path) -> None:
    controller = HostController(config(tmp_path))
    with pytest.raises(AgentError, match="invalid_firewall_source_ip"):
        controller.firewall_preview("192.0.2.1; rm -rf /", 40000, 40099)
    with pytest.raises(AgentError, match="published_udp_range_too_wide"):
        controller.firewall_preview("192.0.2.1", 40000, 40100)


def test_firewall_uses_argument_allowlist_and_persists_only_managed_rule(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict]] = []

    def runner(arguments: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0, "", "")

    controller = HostController(config(tmp_path), runner=runner)
    result = controller.apply_firewall("192.0.2.10", 40000, 40099)

    assert result == {"source_ip": "192.0.2.10", "udp_start": 40000, "udp_end": 40099}
    assert calls[0][0] == [
        "/usr/sbin/ufw", "--force", "allow", "proto", "udp", "from",
        "192.0.2.10", "to", "any", "port", "40000:40099", "comment", "WOLT-managed",
    ]
    assert "shell" not in calls[0][1]
    assert json.loads((tmp_path / "state.json").read_text())["firewall"] == result


def test_environment_update_preserves_secrets_and_is_owner_only(tmp_path: Path) -> None:
    controller = HostController(config(tmp_path))
    controller._update_env({"WOLT_UDP_PUBLISHED_START": "41000", "WOLT_UDP_PUBLISHED_END": "41009"})
    content = controller.config.env_file.read_text()

    assert "POSTGRES_PASSWORD=do-not-touch" in content
    assert "WOLT_UDP_PUBLISHED_START=41000" in content
    assert "WOLT_UDP_PUBLISHED_END=41009" in content
    assert os.stat(controller.config.env_file).st_mode & 0o777 == 0o600
    assert controller.config.env_file.with_suffix(".web.host-agent-backup").exists()


def test_upgrade_rejects_non_semantic_or_injected_tag(tmp_path: Path) -> None:
    controller = HostController(config(tmp_path))
    controller.jobs["job"] = {"id": "job", "operation": "upgrade", "status": "running", "error": None}
    controller._execute_job("job", "upgrade", {"version": "latest;shutdown"})

    assert controller.jobs["job"]["status"] == "failed"
    assert controller.jobs["job"]["error"] == "invalid_release_version"


def test_signed_image_is_pinned_to_verified_digest(tmp_path: Path) -> None:
    agent_config = config(tmp_path)
    cosign = tmp_path / "cosign"
    cosign.write_text("binary", encoding="utf-8")
    agent_config = AgentConfig(**{**agent_config.__dict__, "cosign_binary": str(cosign)})
    digest = "sha256:" + "b" * 64
    calls: list[list[str]] = []

    def runner(arguments: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        output = json.dumps([{"critical": {"image": {"docker-manifest-digest": digest}}}])
        return subprocess.CompletedProcess(arguments, 0, output, "")

    controller = HostController(agent_config, runner=runner)
    image = controller._verified_image("0.3.0")

    assert image == f"alirezasayyari/wolt@{digest}"
    assert calls[0][0:3] == [str(cosign), "verify", "--output"]
    assert calls[0][-1] == "alirezasayyari/wolt:0.3.0"


def test_pre_upgrade_database_backup_is_private_and_allowlisted(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def runner(arguments: list[str], **kwargs) -> subprocess.CompletedProcess:
        calls.append(arguments)
        kwargs["stdout"].write(b"PGDMP-test")
        return subprocess.CompletedProcess(arguments, 0, b"", b"")

    controller = HostController(config(tmp_path), runner=runner)
    backup = controller._database_backup()

    assert backup.read_bytes() == b"PGDMP-test"
    assert os.stat(backup).st_mode & 0o777 == 0o600
    assert calls[0][-8:] == [
        "postgres", "pg_dump", "--format=custom", "--no-owner", "-U", "wolt", "-d", "wolt",
    ]


def test_database_restore_rejects_backup_outside_agent_state(tmp_path: Path) -> None:
    controller = HostController(config(tmp_path))
    external = tmp_path / "external.dump"
    external.write_bytes(b"PGDMP")
    with pytest.raises(AgentError, match="database_backup_unavailable"):
        controller._database_restore(external)


def test_runtime_deployment_preserves_user_state_and_can_restore(tmp_path: Path) -> None:
    agent_config = config(tmp_path)
    agent_config.runtime_dir.mkdir()
    (agent_config.runtime_dir / "local.txt").write_text("old runtime", encoding="utf-8")
    agent_config.agent_install_dir.mkdir()
    (agent_config.agent_install_dir / "server.py").write_text("old agent", encoding="utf-8")
    (agent_config.project_dir / "VERSION").write_text("v1.0.1", encoding="utf-8")
    certs = agent_config.project_dir / "certs"
    certs.mkdir()
    (certs / "smtp-ca.pem").write_text("private ca", encoding="utf-8")
    source = runtime_bundle(tmp_path / "bundle")
    controller = HostController(agent_config)

    controller._validate_runtime(source, "v1.1.1")
    backup = controller._deploy_runtime(source)

    assert (agent_config.project_dir / ".env.web").read_text().startswith("POSTGRES_PASSWORD=do-not-touch")
    assert (certs / "smtp-ca.pem").read_text() == "private ca"
    assert (agent_config.project_dir / "VERSION").read_text() == "v1.1.1"
    assert (agent_config.runtime_dir / "scripts" / "install-host-agent.sh").stat().st_mode & 0o777 == 0o755
    assert (agent_config.agent_install_dir / "server.py").read_text() == "VERSION = 'new'\n"

    controller._restore_runtime(backup)

    assert (agent_config.project_dir / "VERSION").read_text() == "v1.0.1"
    assert (agent_config.runtime_dir / "local.txt").read_text() == "old runtime"
    assert (agent_config.agent_install_dir / "server.py").read_text() == "old agent"
    assert (certs / "smtp-ca.pem").read_text() == "private ca"


def test_runtime_validation_rejects_mismatch_and_symlink(tmp_path: Path) -> None:
    controller = HostController(config(tmp_path))
    source = runtime_bundle(tmp_path / "bundle", version="v9.9.9")
    with pytest.raises(AgentError, match="runtime_bundle_version_mismatch"):
        controller._validate_runtime(source, "v1.1.1")
    (source / "VERSION").unlink()
    (source / "VERSION").symlink_to(source / "compose.web.yml")
    with pytest.raises(AgentError, match="runtime_bundle_invalid"):
        controller._validate_runtime(source, "v1.1.1")


def test_completed_job_survives_agent_restart(tmp_path: Path) -> None:
    agent_config = config(tmp_path)
    first = HostController(agent_config)
    completed = {"id": "job-1", "operation": "upgrade", "status": "succeeded", "error": None}
    first._save_job(completed)

    restarted = HostController(agent_config)
    assert restarted.job("job-1") == completed


def test_upgrade_compose_failure_restores_runtime_environment_and_database(
    tmp_path: Path,
) -> None:
    agent_config = config(tmp_path)
    (agent_config.project_dir / "VERSION").write_text("v1.0.1", encoding="utf-8")
    agent_config.runtime_dir.mkdir()
    (agent_config.runtime_dir / "old.txt").write_text("old runtime", encoding="utf-8")
    agent_config.agent_install_dir.mkdir()
    (agent_config.agent_install_dir / "server.py").write_text("old agent", encoding="utf-8")
    with agent_config.env_file.open("a", encoding="utf-8") as stream:
        stream.write("WOLT_IMAGE=alirezasayyari/wolt@sha256:" + "a" * 64 + "\n")
        stream.write("WOLT_VERSION=v1.0.1\n")
    controller = HostController(agent_config)
    source = runtime_bundle(tmp_path / "bundle")
    database_backup = tmp_path / "backups" / "before.dump"
    database_backup.parent.mkdir()
    database_backup.write_bytes(b"PGDMP")
    restored_database: list[Path] = []

    controller._verified_image = lambda _version: "alirezasayyari/wolt@sha256:" + "b" * 64  # type: ignore[method-assign]
    controller._extract_runtime = lambda _image, _version: source  # type: ignore[method-assign]
    controller._database_backup = lambda: database_backup  # type: ignore[method-assign]
    controller._database_restore = lambda path: restored_database.append(path)  # type: ignore[method-assign]
    controller._healthy = lambda _timeout=120: True  # type: ignore[method-assign]
    controller._run = lambda _arguments, timeout=120: subprocess.CompletedProcess([], 0, "", "")  # type: ignore[method-assign]
    controller._compose = lambda *_args, **_kwargs: (_ for _ in ()).throw(AgentError("host_command_failed", 502))  # type: ignore[method-assign]

    controller._execute_job("upgrade-job", "upgrade", {"version": "v1.1.1"})

    assert controller.job("upgrade-job")["status"] == "failed"
    assert controller.job("upgrade-job")["error"] == "host_command_failed"
    assert (agent_config.project_dir / "VERSION").read_text() == "v1.0.1"
    assert (agent_config.runtime_dir / "old.txt").read_text() == "old runtime"
    assert "WOLT_VERSION=v1.0.1" in agent_config.env_file.read_text()
    assert restored_database == [database_backup]


def test_unix_socket_requires_bearer_token(tmp_path: Path) -> None:
    agent_config = config(tmp_path)
    controller = HostController(agent_config)
    server = AgentServer(agent_config, controller)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert HostAgentClient(agent_config.socket_path, agent_config.token).request("GET", "/v1/status")["agent_version"] == "1.1.1"
        with pytest.raises(HostAgentError) as error:
            HostAgentClient(agent_config.socket_path, "wrong" * 10).request("GET", "/v1/status")
        assert error.value.status == 401
        assert error.value.detail == "host_agent_unauthorized"
    finally:
        server.shutdown()
        server.server_close()
