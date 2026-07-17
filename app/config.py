import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


INTERFACE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class ConfigError(ValueError):
    """Raised when environment or mapping configuration is invalid."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass(frozen=True)
class InterfaceMapping:
    interface: str
    gateway_ip: str


@dataclass(frozen=True)
class Settings:
    fortigate_host: str
    fortigate_ssh_port: int
    fortigate_username: str
    fortigate_password: str
    guacamole_allowed_ip: str
    ssh_connect_timeout: float
    ssh_command_timeout: float
    wol_rate_limit_seconds: float
    log_level: str
    mapping_file: str
    known_hosts_file: str


def _required(env: dict[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"required environment variable is missing: {name}")
    return value


def _integer(value: str, name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _number(value: str, name: str, minimum: float = 0) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if parsed < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return parsed


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if environ is None else environ)
    host = _required(env, "FORTIGATE_HOST")
    allowed_ip = _required(env, "GUACAMOLE_ALLOWED_IP")
    try:
        ipaddress.ip_address(host)
    except ValueError as exc:
        raise ConfigError("FORTIGATE_HOST must be an IP address") from exc
    try:
        ipaddress.ip_address(allowed_ip)
    except ValueError as exc:
        raise ConfigError("GUACAMOLE_ALLOWED_IP must be an IP address") from exc

    log_level = env.get("LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("LOG_LEVEL is invalid")

    return Settings(
        fortigate_host=host,
        fortigate_ssh_port=_integer(env.get("FORTIGATE_SSH_PORT", "22"), "FORTIGATE_SSH_PORT", 1, 65535),
        fortigate_username=_required(env, "FORTIGATE_USERNAME"),
        fortigate_password=_required(env, "FORTIGATE_PASSWORD"),
        guacamole_allowed_ip=allowed_ip,
        ssh_connect_timeout=_number(env.get("SSH_CONNECT_TIMEOUT", "5"), "SSH_CONNECT_TIMEOUT", 0.1),
        ssh_command_timeout=_number(env.get("SSH_COMMAND_TIMEOUT", "10"), "SSH_COMMAND_TIMEOUT", 0.1),
        wol_rate_limit_seconds=_number(env.get("WOL_RATE_LIMIT_SECONDS", "30"), "WOL_RATE_LIMIT_SECONDS"),
        log_level=log_level,
        mapping_file=env.get("MAPPING_FILE", "/app/config/interfaces.yaml"),
        known_hosts_file=env.get("KNOWN_HOSTS_FILE", "/home/wolt/.ssh/known_hosts"),
    )


def load_mappings(path: str | Path) -> dict[int, InterfaceMapping]:
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            document = yaml.load(stream, Loader=_UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot load mapping file: {exc}") from exc

    if not isinstance(document, dict) or not isinstance(document.get("listeners"), dict):
        raise ConfigError("mapping must contain a listeners object")
    listeners = document["listeners"]
    if not listeners:
        raise ConfigError("mapping must define at least one listener")

    mappings: dict[int, InterfaceMapping] = {}
    for raw_port, raw_mapping in listeners.items():
        port = _integer(str(raw_port), "listener port", 1024, 65535)
        if port in mappings:
            raise ConfigError(f"duplicate listener port: {port}")
        if not isinstance(raw_mapping, dict):
            raise ConfigError(f"mapping for port {port} must be an object")
        if set(raw_mapping) != {"interface", "gateway_ip"}:
            raise ConfigError(f"mapping for port {port} must contain only interface and gateway_ip")
        interface = raw_mapping.get("interface")
        gateway_ip = raw_mapping.get("gateway_ip")
        if not isinstance(interface, str) or not INTERFACE_PATTERN.fullmatch(interface):
            raise ConfigError(f"invalid interface for port {port}")
        if not isinstance(gateway_ip, str):
            raise ConfigError(f"invalid gateway_ip for port {port}")
        try:
            normalized_ip = str(ipaddress.ip_address(gateway_ip))
        except ValueError as exc:
            raise ConfigError(f"invalid gateway_ip for port {port}") from exc
        mappings[port] = InterfaceMapping(interface=interface, gateway_ip=normalized_ip)
    return mappings
