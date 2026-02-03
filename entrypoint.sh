#!/bin/bash
# Filter out SDK MCP/hook noise from stderr
exec uv run python -m claude_code_bot 2>&1 | grep -v -E "(Error in hook callback|No servers were imported|error: Stream closed|at sendRequest|at f91|at gm|at zF|createElement|MCP server)"
