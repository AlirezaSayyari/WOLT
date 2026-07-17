import pytest

from app.parser import InvalidMagicPacketError, build_magic_packet, parse_magic_packet


MAC = bytes.fromhex("02AABBCCDD16")


def test_parse_standard_magic_packet() -> None:
    parsed = parse_magic_packet(build_magic_packet(MAC))
    assert parsed.mac_address == "02:AA:BB:CC:DD:16"
    assert parsed.packet_length == 102


@pytest.mark.parametrize("payload", [b"\x00" * 6 + MAC * 16, b"\xff" * 20])
def test_rejects_invalid_header_or_short_packet(payload: bytes) -> None:
    with pytest.raises(InvalidMagicPacketError):
        parse_magic_packet(payload)


def test_rejects_long_secureon_packet() -> None:
    with pytest.raises(InvalidMagicPacketError):
        parse_magic_packet(build_magic_packet(MAC) + b"secret")


def test_rejects_non_repeating_mac() -> None:
    payload = bytearray(build_magic_packet(MAC))
    payload[-1] ^= 1
    with pytest.raises(InvalidMagicPacketError):
        parse_magic_packet(bytes(payload))


@pytest.mark.parametrize(
    ("mac", "expected"),
    [
        (b"\x00" * 6, "00:00:00:00:00:00"),
        (b"\xff" * 6, "FF:FF:FF:FF:FF:FF"),
    ],
)
def test_accepts_zero_and_ff_mac_bytes(mac: bytes, expected: str) -> None:
    assert parse_magic_packet(build_magic_packet(mac)).mac_address == expected


def test_build_helper_requires_six_bytes() -> None:
    with pytest.raises(ValueError):
        build_magic_packet(b"short")
