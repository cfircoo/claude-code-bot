#!/usr/bin/env python3
"""CLI tool to chat with the bot via SSE streaming HTTP API."""

from __future__ import annotations

import argparse
import json
import sys

import httpx

# ANSI color codes (disabled when stdout is not a TTY)
_USE_COLOR = sys.stdout.isatty()
DIM = "\033[2m" if _USE_COLOR else ""
RED = "\033[31m" if _USE_COLOR else ""
CYAN = "\033[36m" if _USE_COLOR else ""
BOLD = "\033[1m" if _USE_COLOR else ""
RESET = "\033[0m" if _USE_COLOR else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with Claude Code Bot")
    parser.add_argument("message", nargs="?", help="Message to send (or use interactive mode)")
    parser.add_argument("--url", default="http://localhost:8010", help="Bot URL (default: http://localhost:8010)")
    parser.add_argument("--user", default="cli-user", help="User ID (default: cli-user)")
    parser.add_argument("--conversation", default=None, help="Conversation ID to target")
    parser.add_argument("--debug", action="store_true", help="Show raw SSE events")
    parser.add_argument("--api-key", default=None, help="API key for X-API-Key header authentication")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactive chat mode")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    headers: dict[str, str] = {}
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    # Check health first
    try:
        r = httpx.get(f"{base_url}/health", timeout=5, headers=headers)
        if args.debug:
            print(f"[health] {r.json()}")
    except httpx.ConnectError:
        print(f"Error: Cannot connect to {base_url}")
        sys.exit(1)

    if args.interactive or args.message is None:
        print(f"Connected to {base_url} as '{args.user}'")
        conversation_id = args.conversation
        if conversation_id:
            print(f"Conversation: {conversation_id}")
        print("Type 'quit' or Ctrl+C to exit.\n")
        try:
            while True:
                try:
                    msg = input("You: ").strip()
                except EOFError:
                    break
                if not msg or msg.lower() in ("quit", "exit"):
                    break
                cid = send_streaming(base_url, args.user, msg, conversation_id, args.debug, headers)
                if cid and not conversation_id:
                    conversation_id = cid
                    print(f"{DIM}[Conversation: {conversation_id}]{RESET}")
        except KeyboardInterrupt:
            print("\nBye!")
    else:
        send_streaming(base_url, args.user, args.message, args.conversation, args.debug, headers)


def send_streaming(
    base_url: str,
    user_id: str,
    message: str,
    conversation_id: str | None,
    debug: bool,
    headers: dict[str, str] | None = None,
) -> str | None:
    """Send a message via POST /chat/stream and display SSE events in real-time.

    Returns the conversation_id from the result event, if present.
    """
    payload: dict[str, str | None] = {
        "user_id": user_id,
        "message": message,
        "conversation_id": conversation_id,
    }

    max_retries = 2
    received_conversation_id: str | None = None

    for attempt in range(max_retries + 1):
        if debug:
            print(f"[request] POST {base_url}/chat/stream (attempt {attempt + 1})")
            print(f"[payload] {json.dumps(payload)}")
        elif attempt == 0 and not debug:
            pass  # normal first attempt, no extra output
        # else: reconnect message already printed below

        try:
            with httpx.stream(
                "POST",
                f"{base_url}/chat/stream",
                json=payload,
                headers=headers or {},
                timeout=httpx.Timeout(connect=10, read=300, write=10, pool=10),
            ) as response:
                if response.status_code != 200:
                    response.read()
                    print(f"Error ({response.status_code}): {response.text}\n")
                    return None

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
                        sys.stdout.write(event.get("content", ""))
                        sys.stdout.flush()
                        in_text = True

                    elif event_type == "tool_start":
                        if in_text:
                            print()
                            in_text = False
                        tool = event.get("tool", "unknown")
                        parent = event.get("parent_tool_use_id")
                        prefix = "  ↳ " if parent else ""
                        print(f"{DIM}{prefix}[Using {tool}...]{RESET}", end="", flush=True)

                    elif event_type == "tool_done":
                        print(f"{DIM} done{RESET}")

                    elif event_type == "result":
                        if in_text:
                            print()
                            in_text = False
                        received_conversation_id = event.get("conversation_id")
                        print()

                    elif event_type == "error":
                        if in_text:
                            print()
                            in_text = False
                        print(f"{RED}Error: {event.get('content', 'unknown error')}{RESET}\n")

                    elif event_type == "conversation_switched":
                        if in_text:
                            print()
                            in_text = False
                        cid = event.get("conversation_id", "")
                        print(f"{CYAN}[Switched to conversation {cid}]{RESET}")

                # End of stream — success
                if in_text:
                    print()
                return received_conversation_id

        except httpx.ConnectError:
            print(f"{RED}Error: Connection lost{RESET}")
            return None
        except (httpx.ReadError, httpx.RemoteProtocolError):
            if attempt < max_retries:
                print(f"\n{CYAN}[Reconnecting...]{RESET}")
            else:
                print(f"\n{RED}Error: Connection lost after {max_retries + 1} attempts{RESET}")

    return None


if __name__ == "__main__":
    main()
