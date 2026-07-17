from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedMagicPacket:
    mac_address: str
    packet_length: int


class InvalidMagicPacketError(ValueError):
    """Raised when a UDP payload is not a standard 102-byte magic packet."""


def parse_magic_packet(data: bytes) -> ParsedMagicPacket:
    if len(data) != 102:
        raise InvalidMagicPacketError("magic packet must be exactly 102 bytes")
    if data[:6] != b"\xff" * 6:
        raise InvalidMagicPacketError("invalid magic packet header")

    mac = data[6:12]
    if data[6:] != mac * 16:
        raise InvalidMagicPacketError("destination MAC is not repeated 16 times")

    return ParsedMagicPacket(
        mac_address=":".join(f"{byte:02X}" for byte in mac),
        packet_length=len(data),
    )


def build_magic_packet(mac: bytes) -> bytes:
    if len(mac) != 6:
        raise ValueError("MAC must contain exactly 6 bytes")
    return b"\xff" * 6 + mac * 16
