#!/usr/bin/env python3
"""CLI tool to chat with the bot via HTTP API."""

import argparse
import json
import sys

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with Claude Code Bot")
    parser.add_argument("message", nargs="?", help="Message to send (or use interactive mode)")
    parser.add_argument("--url", default="http://localhost:8010", help="Bot URL (default: http://localhost:8010)")
    parser.add_argument("--user", default="cli-user", help="User ID (default: cli-user)")
    parser.add_argument("--debug", action="store_true", help="Show full JSON response")
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
        print("Type 'quit' or Ctrl+C to exit.\n")
        try:
            while True:
                try:
                    msg = input("You: ").strip()
                except EOFError:
                    break
                if not msg or msg.lower() in ("quit", "exit"):
                    break
                send(base_url, args.user, msg, args.debug)
        except KeyboardInterrupt:
            print("\nBye!")
    else:
        send(base_url, args.user, args.message, args.debug)


def send(base_url: str, user_id: str, message: str, debug: bool) -> None:
    payload = {"user_id": user_id, "message": message}

    if debug:
        print(f"[request] POST {base_url}/chat")
        print(f"[payload] {json.dumps(payload)}")

    try:
        r = httpx.post(
            f"{base_url}/chat",
            json=payload,
            timeout=120,
        )
    except httpx.ConnectError:
        print("Error: Connection lost")
        return

    if debug:
        print(f"[status] {r.status_code}")
        print(f"[response] {json.dumps(r.json(), indent=2)}")
        print()

    if r.status_code == 200:
        data = r.json()
        print(f"Bot: {data['response']}\n")
    else:
        print(f"Error ({r.status_code}): {r.text}\n")


if __name__ == "__main__":
    main()
