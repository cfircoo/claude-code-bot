"""Entry point for running the bot: python -m claude_code_bot."""

import os
import sys
from pathlib import Path

import uvicorn


def main() -> None:
    """Start the bot server."""
    config_path = Path(os.environ.get("CONFIG_PATH", "config.yaml"))
    if not config_path.exists():
        print(
            "\n  ERROR: No config.yaml found.\n"
            "  Run 'python install.py' to set up the bot first.\n"
        )
        sys.exit(1)

    uvicorn.run(
        "claude_code_bot.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
