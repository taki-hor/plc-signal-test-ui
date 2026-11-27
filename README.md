# Anodizing PLC Communication & Signal Test Console

Monitor tank signals, test commands against PLC feedback, and record operator results before AGV or robot integration.

## Quick start

Requires Python 3.11 or newer. From the repository root, run:

```bash
./start
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). On first run, the launcher creates a virtual environment, installs dependencies, and creates `.env` with mock mode enabled. If your checkout has `start.sh`, it runs the same launcher.

## Connect to a live PLC

Set `PLC_API_BASE_URL` and `PLC_API_KEY` in `.env`, set `PLC_MOCK_MODE=false`, then restart the console. Start with read-only checks. Before sending commands, confirm the target, reset procedure, and operator readiness.

## Documentation

- [User guide](docs/user-guide.md)
- [Commissioning and signal test plan](docs/signal-test-plan.md)
- [Field test results](docs/swagger-second-run-2026-10-26.txt)
- [Supplier manual, Swagger schema, and tag catalog](docs/source/README.md)
- [Supplier documentation discrepancies](docs/swagger-alignment-2026-10-23.md)
- [Architecture](docs/architecture.md)

To run the automated tests after setup, use `.venv/bin/python -m pytest -q`.
