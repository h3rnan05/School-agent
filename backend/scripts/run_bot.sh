#!/bin/bash
# Wrapper so launchd (which doesn't source shell profiles or .env files on
# its own) can run the bot with the same environment you use manually.
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source .venv/bin/activate
set -a
source .env
set +a
exec python -m app.telegram_bot run
