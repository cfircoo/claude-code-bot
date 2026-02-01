# Ralph Test Log

## US-201: Add extra="ignore" to BotConfig
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_config.py::test_bot_config_extra_fields_ignored` — verifies unknown YAML keys don't raise ValidationError
- **Tests modified:** None
- **Coverage notes:** All 8 config tests pass
