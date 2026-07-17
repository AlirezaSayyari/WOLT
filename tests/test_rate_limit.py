from app.rate_limit import RateLimiter


def test_rate_limit_is_per_port_and_mac() -> None:
    now = [100.0]
    limiter = RateLimiter(30, clock=lambda: now[0])

    assert limiter.allow(40016, "AA:BB:CC:DD:EE:FF")
    assert not limiter.allow(40016, "AA:BB:CC:DD:EE:FF")
    assert limiter.allow(40017, "AA:BB:CC:DD:EE:FF")
    assert limiter.allow(40016, "00:11:22:33:44:55")

    now[0] += 30
    assert limiter.allow(40016, "AA:BB:CC:DD:EE:FF")
