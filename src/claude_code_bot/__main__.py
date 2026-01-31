"""Entry point for running the bot: python -m claude_code_bot."""

import uvicorn


def main() -> None:
    """Start the bot server."""
    uvicorn.run(
        "claude_code_bot.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
