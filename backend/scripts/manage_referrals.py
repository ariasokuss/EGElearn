#!/usr/bin/env python3
"""
Referral management CLI script.

Usage:
    # Create a referral source for a user
    python scripts/manage_referrals.py create --email user@example.com --code roman-yt --label "YouTube"

    # List all referral sources
    python scripts/manage_referrals.py list

    # List sources for a specific user
    python scripts/manage_referrals.py list --email user@example.com

    # View dashboard stats
    python scripts/manage_referrals.py stats

    # View stats for a specific user
    python scripts/manage_referrals.py stats --email user@example.com

    # Deactivate a referral source
    python scripts/manage_referrals.py deactivate --code roman-yt

    # Reactivate a referral source
    python scripts/manage_referrals.py activate --code roman-yt
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add backend src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select, func
from src.config import get_settings
from src.core.db import create_engine, create_session_factory
from src.referral.models import ReferralAttribution, ReferralSource, ReferralVisit
from src.auth.models import User


async def get_session_factory():
    settings = get_settings()
    engine = create_engine(settings.postgres)
    return create_session_factory(engine), engine


async def find_user_by_email(session, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


async def cmd_create(args):
    sf, engine = await get_session_factory()
    async with sf() as session:
        user = await find_user_by_email(session, args.email)
        if not user:
            print(f"Error: User with email '{args.email}' not found")
            return

        existing = await session.scalar(
            select(ReferralSource).where(ReferralSource.code == args.code)
        )
        if existing:
            print(f"Error: Code '{args.code}' is already taken")
            return

        source = ReferralSource(
            user_id=user.id,
            code=args.code,
            label=args.label,
        )
        session.add(source)
        await session.commit()
        print("Created referral source:")
        print(f"  Code:  {source.code}")
        print(f"  Label: {source.label or '—'}")
        print(f"  User:  {args.email}")
        print(f"  ID:    {source.id}")
        print(f"\n  Link:  https://novalearn.ai?ref={source.code}")

    await engine.dispose()


async def cmd_list(args):
    sf, engine = await get_session_factory()
    async with sf() as session:
        query = select(ReferralSource).order_by(ReferralSource.created_at.desc())
        if args.email:
            user = await find_user_by_email(session, args.email)
            if not user:
                print(f"Error: User with email '{args.email}' not found")
                return
            query = query.where(ReferralSource.user_id == user.id)

        sources = (await session.scalars(query)).all()
        if not sources:
            print("No referral sources found")
            return

        print(f"{'Code':<20} {'Label':<25} {'Active':<8} {'Created':<20}")
        print("-" * 73)
        for s in sources:
            print(
                f"{s.code:<20} {(s.label or '—'):<25} "
                f"{'Yes' if s.is_active else 'No':<8} "
                f"{s.created_at.strftime('%Y-%m-%d %H:%M'):<20}"
            )

    await engine.dispose()


async def cmd_stats(args):
    sf, engine = await get_session_factory()
    async with sf() as session:
        query = select(ReferralSource).order_by(ReferralSource.created_at.desc())
        if args.email:
            user = await find_user_by_email(session, args.email)
            if not user:
                print(f"Error: User with email '{args.email}' not found")
                return
            query = query.where(ReferralSource.user_id == user.id)

        sources = (await session.scalars(query)).all()
        if not sources:
            print("No referral sources found")
            return

        print(
            f"{'Code':<20} {'Label':<20} {'Visits':<8} {'Unique':<8} "
            f"{'Signups':<8} {'Purchases':<10}"
        )
        print("-" * 74)

        total_visits = total_unique = total_signups = total_purchases = 0

        for s in sources:
            visits = (
                await session.scalar(
                    select(func.count()).where(ReferralVisit.source_id == s.id)
                )
                or 0
            )
            unique = (
                await session.scalar(
                    select(func.count(func.distinct(ReferralVisit.visitor_id))).where(
                        ReferralVisit.source_id == s.id
                    )
                )
                or 0
            )
            signups = (
                await session.scalar(
                    select(func.count()).where(ReferralAttribution.source_id == s.id)
                )
                or 0
            )
            purchases = (
                await session.scalar(
                    select(func.count()).where(
                        ReferralAttribution.source_id == s.id,
                        ReferralAttribution.purchased_at.is_not(None),
                    )
                )
                or 0
            )

            total_visits += visits
            total_unique += unique
            total_signups += signups
            total_purchases += purchases

            print(
                f"{s.code:<20} {(s.label or '—'):<20} {visits:<8} {unique:<8} "
                f"{signups:<8} {purchases:<10}"
            )

        if len(sources) > 1:
            print("-" * 74)
            print(
                f"{'TOTAL':<20} {'':<20} {total_visits:<8} {total_unique:<8} "
                f"{total_signups:<8} {total_purchases:<10}"
            )

    await engine.dispose()


async def cmd_toggle(args, activate: bool):
    sf, engine = await get_session_factory()
    async with sf() as session:
        source = await session.scalar(
            select(ReferralSource).where(ReferralSource.code == args.code)
        )
        if not source:
            print(f"Error: Source with code '{args.code}' not found")
            return

        source.is_active = activate
        await session.commit()
        status = "activated" if activate else "deactivated"
        print(f"Source '{args.code}' {status}")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Manage referral sources")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a referral source")
    p_create.add_argument("--email", required=True, help="User email (creator)")
    p_create.add_argument("--code", required=True, help="Referral code (URL-safe)")
    p_create.add_argument("--label", default=None, help="Label (e.g. YouTube)")

    # list
    p_list = sub.add_parser("list", help="List referral sources")
    p_list.add_argument("--email", default=None, help="Filter by user email")

    # stats
    p_stats = sub.add_parser("stats", help="View referral stats")
    p_stats.add_argument("--email", default=None, help="Filter by user email")

    # deactivate
    p_deact = sub.add_parser("deactivate", help="Deactivate a source")
    p_deact.add_argument("--code", required=True, help="Referral code")

    # activate
    p_act = sub.add_parser("activate", help="Reactivate a source")
    p_act.add_argument("--code", required=True, help="Referral code")

    args = parser.parse_args()

    if args.command == "create":
        asyncio.run(cmd_create(args))
    elif args.command == "list":
        asyncio.run(cmd_list(args))
    elif args.command == "stats":
        asyncio.run(cmd_stats(args))
    elif args.command == "deactivate":
        asyncio.run(cmd_toggle(args, activate=False))
    elif args.command == "activate":
        asyncio.run(cmd_toggle(args, activate=True))


if __name__ == "__main__":
    main()
