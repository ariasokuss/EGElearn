#!/usr/bin/env python3
"""One-shot AMQP connectivity check (same stack as the app: aio-pika).

Do not commit real URLs/passwords. Examples:

  AMQP_URL="amqp://user:pass@host:port/" uv run python scripts/check_amqp.py
  RABBITMQ__URL="amqp://..." uv run python scripts/check_amqp.py
  uv run python scripts/check_amqp.py "amqp://user:pass@host:port/"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def _check(url: str, *, timeout_s: float) -> None:
    import aio_pika

    conn = await asyncio.wait_for(aio_pika.connect(url), timeout=timeout_s)
    try:
        ch = await conn.channel()
        await ch.close()
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test RabbitMQ / AMQP connection")
    parser.add_argument(
        "url",
        nargs="?",
        default=(
            os.environ.get("AMQP_URL")
            or os.environ.get("RABBITMQ__URL")
            or os.environ.get("RABBITMQ_URL")
            or os.environ.get("CLOUDAMQP_URL")
        ),
        help="AMQP URL (or env AMQP_URL, RABBITMQ__URL, RABBITMQ_URL, CLOUDAMQP_URL)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Connection timeout in seconds (default: 20)",
    )
    args = parser.parse_args()
    if not args.url:
        print(
            "Missing URL. Set AMQP_URL or RABBITMQ__URL, or pass URL as first argument.",
            file=sys.stderr,
        )
        return 2

    # Redacted log line
    from urllib.parse import urlparse

    p = urlparse(args.url)
    safe = f"{p.scheme}://{p.username or ''}:***@{p.hostname or ''}:{p.port or ''}{p.path or ''}"
    print(f"Connecting to {safe} (timeout {args.timeout}s)...")

    try:
        asyncio.run(_check(args.url, timeout_s=args.timeout))
    except TimeoutError:
        print("FAIL: timeout", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print("OK: connected, opened channel, closed cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
