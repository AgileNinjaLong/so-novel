"""启动入口：python serve.py"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402


def main() -> None:
    s = settings
    uvicorn.run(
        "app.main:app",
        host=s.host,
        port=s.port,
        log_level=os.environ.get("WEBAPP_LOG_LEVEL", "info"),
        reload=False,
    )


if __name__ == "__main__":
    main()
