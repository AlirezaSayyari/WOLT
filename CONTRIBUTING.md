# Contributing

1. Create a focused branch from `main`.
2. Do not commit `.env`, `config/interfaces.yaml`, `ssh/known_hosts`, or credentials.
3. Run `docker build --target test -t wolt:test .` and `docker run --rm wolt:test`.
4. Keep device-specific behavior behind a driver boundary as the web architecture evolves.
5. Open a pull request describing behavior, tests, and security impact.
