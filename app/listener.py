import logging
import socket
import threading
from dataclasses import dataclass, field

from app.config import InterfaceMapping
from app.fortigate import FortiGateClient, FortiGateError
from app.parser import InvalidMagicPacketError, parse_magic_packet
from app.rate_limit import RateLimiter


LOGGER = logging.getLogger("wolt.listener")


@dataclass
class UDPListener:
    port: int
    mapping: InterfaceMapping
    allowed_ip: str
    rate_limiter: RateLimiter
    fortigate: FortiGateClient
    stop_event: threading.Event
    _socket: socket.socket | None = field(default=None, init=False)

    def run(self) -> None:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket = sock
            sock.settimeout(0.5)
            sock.bind(("0.0.0.0", self.port))
            LOGGER.info("event=listener_started listen_port=%s", self.port)
            while not self.stop_event.is_set():
                try:
                    data, (source_ip, source_port) = sock.recvfrom(2048)
                    self._handle(data, source_ip, source_port)
                except socket.timeout:
                    continue
                except OSError:
                    if not self.stop_event.is_set():
                        LOGGER.error("event=listener_socket_error listen_port=%s", self.port)
                except Exception as exc:
                    LOGGER.error(
                        "event=listener_request_error listen_port=%s reason=%s",
                        self.port,
                        type(exc).__name__,
                    )
        except OSError as exc:
            LOGGER.error(
                "event=listener_bind_failed listen_port=%s reason=%s",
                self.port,
                type(exc).__name__,
            )
        finally:
            if sock is not None:
                sock.close()
            LOGGER.info("event=listener_stopped listen_port=%s", self.port)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()

    def _handle(self, data: bytes, source_ip: str, source_port: int) -> None:
        if source_ip != self.allowed_ip:
            LOGGER.warning(
                "event=wol_request_rejected source_ip=%s listen_port=%s reason=source_not_allowed",
                source_ip,
                self.port,
            )
            return
        try:
            packet = parse_magic_packet(data)
        except InvalidMagicPacketError:
            LOGGER.warning(
                "event=wol_request_rejected source_ip=%s listen_port=%s "
                "reason=invalid_magic_packet packet_length=%s",
                source_ip,
                self.port,
                len(data),
            )
            return

        LOGGER.info(
            "event=wol_request_received source_ip=%s source_port=%s listen_port=%s "
            "destination_mac=%s fortigate_interface=%s gateway_ip=%s",
            source_ip,
            source_port,
            self.port,
            packet.mac_address,
            self.mapping.interface,
            self.mapping.gateway_ip,
        )
        if not self.rate_limiter.allow(self.port, packet.mac_address):
            LOGGER.info(
                "event=wol_request_rate_limited mac=%s listen_port=%s",
                packet.mac_address,
                self.port,
            )
            return
        try:
            self.fortigate.execute_wol(
                self.mapping.interface, packet.mac_address, self.mapping.gateway_ip
            )
            LOGGER.info(
                "event=fortigate_wol_success destination_mac=%s fortigate_interface=%s",
                packet.mac_address,
                self.mapping.interface,
            )
        except FortiGateError as exc:
            LOGGER.error(
                "event=fortigate_wol_failed destination_mac=%s fortigate_interface=%s reason=%s",
                packet.mac_address,
                self.mapping.interface,
                exc,
            )
