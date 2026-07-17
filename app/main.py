import logging
import signal
import threading

from app.config import ConfigError, load_mappings, load_settings
from app.fortigate import FortiGateClient
from app.listener import UDPListener
from app.logging_config import configure_logging
from app.rate_limit import RateLimiter


LOGGER = logging.getLogger("wolt")


def main() -> int:
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        mappings = load_mappings(settings.mapping_file)
    except ConfigError as exc:
        configure_logging("INFO")
        LOGGER.error("event=startup_failed reason=config_error detail=%s", exc)
        return 1

    stop_event = threading.Event()
    limiter = RateLimiter(settings.wol_rate_limit_seconds)
    fortigate = FortiGateClient(settings)
    listeners = [
        UDPListener(port, mapping, settings.guacamole_allowed_ip, limiter, fortigate, stop_event)
        for port, mapping in mappings.items()
    ]
    threads = [
        threading.Thread(target=listener.run, name=f"udp-{listener.port}", daemon=False)
        for listener in listeners
    ]

    def shutdown(signum: int, _frame: object) -> None:
        LOGGER.info("event=shutdown_requested signal=%s", signum)
        stop_event.set()
        for listener in listeners:
            listener.close()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    LOGGER.info("event=wolt_starting listener_count=%s", len(listeners))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    LOGGER.info("event=wolt_stopped")
    return 0 if stop_event.is_set() else 1


if __name__ == "__main__":
    raise SystemExit(main())
