# Home Assistant Custom Component: Mazda Connected Services v2 (EU/MME)

This package contains a full **custom component** and a **test suite** for Mazda Connected Services v2 (OAuth2 + PKCE).
The client implements:
- OAuth 2.0 Authorization Code + PKCE (B2C SelfAsserted + Confirm)
- Token exchange, refresh + retry on 401
- Vehicles list + vehicle status
- Start/Stop charging (mocked in tests)

## Quickstart (local tests)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install pytest pytest-asyncio aiohttp pytest-aiohttp pytest-cov homeassistant

# Run tests
PYTHONPATH=. pytest -vv -s
```
