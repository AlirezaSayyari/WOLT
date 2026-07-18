import os
import stat
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "init-web-env.sh"
UPGRADE_SCRIPT = Path(__file__).parents[1] / "scripts" / "upgrade-web-env.sh"


def test_init_web_env_generates_private_unique_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.web"
    environment = {**os.environ, "WOLT_WEB_ENV_FILE": str(env_file)}

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    values = dict(
        line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line
    )
    database_password = values["POSTGRES_PASSWORD"].strip("'")
    bootstrap_token = values["WOLT_BOOTSTRAP_TOKEN"].strip("'")
    master_key = values["WOLT_MASTER_KEY"].strip("'")

    assert len(database_password) == 64
    assert len(bootstrap_token) == 64
    assert database_password != bootstrap_token
    assert len(master_key) == 64
    assert len({database_password, bootstrap_token, master_key}) == 3
    assert values["WOLT_UDP_PUBLISHED_START"] == "40000"
    assert values["WOLT_UDP_PUBLISHED_END"] == "40099"
    assert bootstrap_token in result.stdout
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_init_web_env_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.web"
    env_file.write_text("existing=true\n")

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env={**os.environ, "WOLT_WEB_ENV_FILE": str(env_file)},
    )

    assert result.returncode != 0
    assert env_file.read_text() == "existing=true\n"
    assert "refusing to overwrite" in result.stderr


def test_upgrade_web_env_preserves_existing_values_and_adds_master_key(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env.web"
    env_file.write_text("POSTGRES_PASSWORD='existing-secret'\n")
    environment = {**os.environ, "WOLT_WEB_ENV_FILE": str(env_file)}

    subprocess.run(
        ["bash", str(UPGRADE_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    contents = env_file.read_text()
    assert "POSTGRES_PASSWORD='existing-secret'" in contents
    master_line = next(
        line for line in contents.splitlines() if line.startswith("WOLT_MASTER_KEY=")
    )
    assert len(master_line.split("'", 2)[1]) == 64
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600

    repeated = subprocess.run(
        ["bash", str(UPGRADE_SCRIPT)],
        capture_output=True,
        text=True,
        env=environment,
    )
    assert repeated.returncode != 0
    assert "already up to date" in repeated.stderr


def test_upgrade_web_env_adds_udp_envelope_when_master_key_exists(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.web"
    env_file.write_text("POSTGRES_PASSWORD='existing'\nWOLT_MASTER_KEY='" + "ab" * 32 + "'\n")

    subprocess.run(
        ["bash", str(UPGRADE_SCRIPT)],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "WOLT_WEB_ENV_FILE": str(env_file)},
    )

    contents = env_file.read_text()
    assert contents.count("WOLT_MASTER_KEY=") == 1
    assert "WOLT_UDP_PUBLISHED_START=40000" in contents
    assert "WOLT_UDP_PUBLISHED_END=40099" in contents
