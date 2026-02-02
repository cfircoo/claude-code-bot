#!/bin/sh
# Fix ownership of mounted .claude directory
if [ -d /home/botuser/.claude ]; then
    chown -R botuser:botuser /home/botuser/.claude
fi
exec gosu botuser "$@"
