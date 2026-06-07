from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    load_dotenv(backend_root / ".env")
    if not (os.getenv("PIM_DATABASE_URL") or os.getenv("DATABASE_URL")):
        raise SystemExit("DATABASE_URL or PIM_DATABASE_URL is required")
    config = Config(str(backend_root / "alembic.ini"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
