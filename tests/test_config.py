from pathlib import Path

import pytest

from app.config import ConfigError, load_mappings, load_settings


def write_mapping(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "interfaces.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_valid_mapping(tmp_path: Path) -> None:
    path = write_mapping(
        tmp_path,
        'listeners:\n  "40016":\n    interface: "demo-vlan-16"\n    gateway_ip: "198.51.100.94"\n',
    )
    mapping = load_mappings(path)
    assert mapping[40016].interface == "demo-vlan-16"
    assert mapping[40016].gateway_ip == "198.51.100.94"


@pytest.mark.parametrize(
    "body",
    [
        "listeners: {}\n",
        'listeners:\n  "80":\n    interface: vlan\n    gateway_ip: 192.0.2.1\n',
        'listeners:\n  nope:\n    interface: vlan\n    gateway_ip: 192.0.2.1\n',
        'listeners:\n  "40016":\n    interface: "bad interface"\n    gateway_ip: 192.0.2.1\n',
        'listeners:\n  "40016":\n    interface: vlan\n    gateway_ip: nope\n',
        'listeners:\n  "40016":\n    interface: vlan\n',
        'listeners:\n  "40016":\n    interface: vlan\n    gateway_ip: 192.0.2.1\n  "40016":\n    interface: vlan2\n    gateway_ip: 192.0.2.2\n',
    ],
)
def test_rejects_invalid_mapping(tmp_path: Path, body: str) -> None:
    with pytest.raises(ConfigError):
        load_mappings(write_mapping(tmp_path, body))


def valid_environment() -> dict[str, str]:
    return {
        "FORTIGATE_HOST": "192.0.2.10",
        "FORTIGATE_USERNAME": "wolt",
        "FORTIGATE_PASSWORD": "not-real",
        "GUACAMOLE_ALLOWED_IP": "192.0.2.20",
    }


def test_load_settings_defaults() -> None:
    settings = load_settings(valid_environment())
    assert settings.fortigate_ssh_port == 22


def test_rejects_missing_required_environment() -> None:
    env = valid_environment()
    del env["FORTIGATE_PASSWORD"]
    with pytest.raises(ConfigError):
        load_settings(env)
