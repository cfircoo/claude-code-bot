#!/usr/bin/env python3
"""CLI tool to chat with the bot via SSE streaming HTTP API."""

from __future__ import annotations

import argparse
import json
import sys

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with Claude Code Bot")
    parser.add_argument("message", nargs="?", help="Message to send (or use interactive mode)")
    parser.add_argument("--url", default="http://localhost:8010", help="Bot URL (default: http://localhost:8010)")
    parser.add_argument("--user", default="cli-user", help="User ID (default: cli-user)")
    parser.add_argument("--conversation", default=None, help="Conversation ID to target")
    parser.add_argument("--debug", action="store_true", help="Show raw SSE events")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactive chat mode")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    # Check health first
    try:
        r = httpx.get(f"{base_url}/health", timeout=5)
        if args.debug:
            print(f"[health] {r.json()}")
    except httpx.ConnectError:
        print(f"Error: Cannot connect to {base_url}")
        sys.exit(1)

    if args.interactive or args.message is None:
        print(f"Connected to {base_url} as '{args.user}'")
        if args.conversation:
            print(f"Conversation: {args.conversation}")
        print("Type 'quit' or Ctrl+C to exit.\n")
        try:
            while True:
                try:
                    msg = input("You: ").strip()
                except EOFError:
                    break
                if not msg or msg.lower() in ("quit", "exit"):
                    break
                send_streaming(base_url, args.user, msg, args.conversation, args.debug)
        except KeyboardInterrupt:
            print("\nBye!")
    else:
        send_streaming(base_url, args.user, args.message, args.conversation, args.debug)


def send_streaming(
    base_url: str,
    user_id: str,
    message: str,
    conversation_id: str | None,
    debug: bool,
) -> None:
    """Send a message via POST /chat/stream and display SSE events in real-time."""
    payload: dict[str, str | None] = {
        "user_id": user_id,
        "message": message,
        "conversation_id": conversation_id,
    }

    if debug:
        print(f"[request] POST {base_url}/chat/stream")
        print(f"[payload] {json.dumps(payload)}")

    try:
        with httpx.stream(
            "POST",
            f"{base_url}/chat/stream",
            json=payload,
            timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
        ) as response:
            if response.status_code != 200:
                response.read()
                print(f"Error ({response.status_code}): {response.text}\n")
                return

            in_text = False
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue

                raw = line[6:]
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    if debug:
                        print(f"[bad-json] {raw}")
                    continue

                if debug:
                    print(f"[event] {json.dumps(event)}")

                event_type = event.get("type", "")

                if event_type == "text":
                    # Print text tokens as they arrive, no newline
                    sys.stdout.write(event.get("content", ""))
                    sys.stdout.flush()
                    in_text = True

                elif event_type == "tool_start":
                    if in_text:
                        print()  # newline after text
                        in_text = False
                    tool = event.get("tool", "unknown")
                    parent = event.get("parent_tool_use_id")
                    prefix = "  ↳ " if parent else ""
                    print(f"{prefix}[Using {tool}...]", end="", flush=True)

                elif event_type == "tool_done":
                    print(" done")

                elif event_type == "result":
                    if in_text:
                        print()  # newline after text
                        in_text = False
                    content = event.get("content", "")
                    print(f"\n{'─' * 40}")
                    print(f"Bot: {content}\n")

                elif event_type == "error":
                    if in_text:
                        print()
                        in_text = False
                    print(f"Error: {event.get('content', 'unknown error')}\n")

                elif event_type == "conversation_switched":
                    if in_text:
                        print()
                        in_text = False
                    cid = event.get("conversation_id", "")
                    print(f"[Switched to conversation {cid}]")

            # End of stream
            if in_text:
                print()

    except httpx.ConnectError:
        print("Error: Connection lost")


if __name__ == "__main__":
    main()
