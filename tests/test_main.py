"""Tests for __main__.py entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from claude_code_bot.__main__ import main


def test_main_config_exists(tmp_path: Path) -> None:
    """When config exists, should call uvicorn.run."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("persona:\n  name: Test\n")

    with patch.dict("os.environ", {"CONFIG_PATH": str(config_file)}):
        with patch("claude_code_bot.__main__.uvicorn") as mock_uvicorn:
            main()
            mock_uvicorn.run.assert_called_once_with(
                "claude_code_bot.app:app",
                host="0.0.0.0",
                port=8000,
                reload=False,
            )


def test_main_config_missing(tmp_path: Path) -> None:
    """When config doesn't exist, should exit with error."""
    with patch.dict("os.environ", {"CONFIG_PATH": str(tmp_path / "nonexistent.yaml")}):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
