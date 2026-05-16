"""Service for recording and querying per-user LLM usage."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth.models import User
from src.config import get_settings
from src.core.llm_usage import UsageInfo
from src.usage.models import LLMUsageLog

logger = logging.getLogger(__name__)


USAGE_FEATURE_LABELS = {
    "chat": "Chat",
    "chat_title": "Chat Title",
    "test_practice_hint": "Practice Hint Chat",
    "feynman": "Feynman",
    "mini_feynman": "Mini Feynman",
    "feynman_feedback": "Feynman Feedback",
    "results": "Results",
    "test_gen": "Test Generation",
    "test_grading": "Test Grading",
    "past_paper": "Past Paper",
    "past_paper_parse": "Past Paper Parse",
    "past_paper_chat": "Past Paper Chat",
}


def usage_feature_label(feature: str) -> str:
    return USAGE_FEATURE_LABELS.get(feature, feature.replace("_", " ").title())


def calculate_cost(
    model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Calculate estimated cost in USD based on config pricing."""
    pricing = get_settings().llm.model_pricing.get(model)
    if pricing is None:
        return 0.0
    prompt_cost = (prompt_tokens / 1_000_000) * pricing.get("prompt", 0)
    completion_cost = (completion_tokens / 1_000_000) * pricing.get("completion", 0)
    return round(prompt_cost + completion_cost, 8)


def resolve_period_start(
    period: str,
    *,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    current = now or datetime.now(timezone.utc)
    if period == "day":
        return "day", current - timedelta(days=1)
    if period == "week":
        return "week", current - timedelta(weeks=1)
    if period == "all":
        return "all", datetime.min.replace(tzinfo=timezone.utc)
    # Fallback to month for unknown values.
    return "month", current - timedelta(days=30)


def _month_start_for(value: datetime) -> datetime:
    value = _as_utc(value)
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(value: datetime, count: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + count
    year, month_zero_based = divmod(month_index, 12)
    return datetime(year, month_zero_based + 1, 1, tzinfo=timezone.utc)


def _month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


def _month_label(value: datetime) -> str:
    return value.strftime("%B %Y")


def _selected_month_start(
    month: str | None,
    *,
    now: datetime | None = None,
) -> datetime:
    if month:
        try:
            year, month_number = month.split("-", 1)
            parsed = datetime(int(year), int(month_number), 1, tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            pass
    return _month_start_for(now or datetime.now(timezone.utc))


def resolve_admin_period_window(
    period: str,
    *,
    now: datetime | None = None,
    month: str | None = None,
) -> tuple[str, datetime, datetime | None]:
    period, since = resolve_period_start(period, now=now)
    if period == "month":
        start = _selected_month_start(month, now=now)
        return "month", start, _add_months(start, 1)
    return period, since, None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _floor_utc_hour(value: datetime) -> datetime:
    value = _as_utc(value)
    return value.replace(minute=0, second=0, microsecond=0)


def _floor_utc_day(value: datetime) -> datetime:
    value = _as_utc(value)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _activity_chart_disabled(period: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "period": period,
        "bucket_granularity": None,
        "timezone": "UTC",
        "period_label": "All time" if period == "all" else period.title(),
        "selected_month": None,
        "previous_month": None,
        "previous_month_label": None,
        "next_month": None,
        "next_month_label": None,
        "empty_reason": "Chart supports day, week, and month periods.",
        "buckets": [],
    }


def _activity_chart_window(
    period: str,
    *,
    now: datetime | None = None,
    month: str | None = None,
) -> tuple[str, datetime, datetime, timedelta, int] | None:
    current = _as_utc(now or datetime.now(timezone.utc))
    if period == "day":
        end = _floor_utc_hour(current) + timedelta(hours=1)
        return "hour", end - timedelta(hours=24), end, timedelta(hours=1), 24
    if period == "week":
        end = _floor_utc_day(current) + timedelta(days=1)
        return "day", end - timedelta(days=7), end, timedelta(days=1), 7
    if period == "month":
        start = _selected_month_start(month, now=current)
        end = _add_months(start, 1)
        return "day", start, end, timedelta(days=1), (end - start).days
    return None


def _bucket_label(bucket_start: datetime, granularity: str) -> str:
    bucket_start = _as_utc(bucket_start)
    if granularity == "hour":
        return bucket_start.strftime("%H:00")
    return str(bucket_start.day)


def _bucket_for_timestamp(value: datetime, granularity: str) -> datetime:
    return _floor_utc_hour(value) if granularity == "hour" else _floor_utc_day(value)


def _bucket_sql_expression(granularity: str):
    return func.date_trunc(granularity, LLMUsageLog.created_at).label("bucket_start")


def _row_entity(row: Any) -> Any:
    try:
        return row[0]
    except (TypeError, KeyError, IndexError):
        return row


class UsageService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def log_usage(
        self,
        *,
        user_id: uuid.UUID | str,
        feature: str,
        usage: UsageInfo | None,
    ) -> None:
        """Insert a usage record. Safe to call fire-and-forget."""
        if usage is None:
            return
        uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
        cost = (
            round(float(usage.cost_usd), 8)
            if usage.cost_usd is not None
            else calculate_cost(
                usage.model, usage.prompt_tokens, usage.completion_tokens
            )
        )
        try:
            async with self._session_factory() as db:
                record = LLMUsageLog(
                    user_id=uid,
                    model=usage.model,
                    feature=feature,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    cost_usd=cost,
                )
                db.add(record)
                await db.commit()
        except Exception:
            logger.exception("Failed to log LLM usage for user %s", uid)

    def log_usage_fire_and_forget(
        self,
        *,
        user_id: uuid.UUID | str,
        feature: str,
        usage: UsageInfo | None,
    ) -> None:
        """Schedule usage logging without awaiting (non-blocking)."""
        if usage is None:
            return
        asyncio.create_task(
            self.log_usage(user_id=user_id, feature=feature, usage=usage)
        )

    async def get_user_stats(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        period: str = "month",
    ) -> dict[str, Any]:
        """Aggregate usage stats for a user within a time period."""
        period, since = resolve_period_start(period)

        base_filter = (
            LLMUsageLog.user_id == user_id,
            LLMUsageLog.created_at >= since,
        )

        # Totals
        totals_q = select(
            func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0).label(
                "completion_tokens"
            ),
            func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LLMUsageLog.cost_usd), 0.0).label("total_cost_usd"),
        ).where(*base_filter)
        totals_row = (await db.execute(totals_q)).one()

        # By model
        by_model_q = (
            select(
                LLMUsageLog.model,
                func.sum(LLMUsageLog.total_tokens).label("tokens"),
                func.sum(LLMUsageLog.cost_usd).label("cost_usd"),
            )
            .where(*base_filter)
            .group_by(LLMUsageLog.model)
        )
        by_model_rows = (await db.execute(by_model_q)).all()
        by_model = {
            row.model: {"tokens": int(row.tokens), "cost_usd": round(float(row.cost_usd), 6)}
            for row in by_model_rows
        }

        # By feature
        by_feature_q = (
            select(
                LLMUsageLog.feature,
                func.sum(LLMUsageLog.total_tokens).label("tokens"),
                func.sum(LLMUsageLog.cost_usd).label("cost_usd"),
            )
            .where(*base_filter)
            .group_by(LLMUsageLog.feature)
        )
        by_feature_rows = (await db.execute(by_feature_q)).all()
        by_feature = {
            row.feature: {"tokens": int(row.tokens), "cost_usd": round(float(row.cost_usd), 6)}
            for row in by_feature_rows
        }

        return {
            "prompt_tokens": int(totals_row.prompt_tokens),
            "completion_tokens": int(totals_row.completion_tokens),
            "total_tokens": int(totals_row.total_tokens),
            "total_cost_usd": round(float(totals_row.total_cost_usd), 6),
            "by_model": by_model,
            "by_feature": by_feature,
            "period": period,
        }

    async def get_admin_usage_overview(
        self,
        db: AsyncSession,
        *,
        period: str = "month",
        limit: int = 100,
        email: str | None = None,
        now: datetime | None = None,
        month: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate usage stats across all users for admin reporting."""
        period, since, until = resolve_admin_period_window(
            period,
            now=now,
            month=month,
        )
        email_filter = email.strip() if email else None
        filters = [LLMUsageLog.created_at >= since]
        if until is not None:
            filters.append(LLMUsageLog.created_at < until)
        if email_filter:
            filters.append(User.email.ilike(f"%{email_filter}%"))

        totals_q = (
            select(
                func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0).label(
                    "prompt_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0).label(
                    "completion_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label(
                    "total_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.cost_usd), 0.0).label(
                    "total_cost_usd"
                ),
                func.count(LLMUsageLog.id).label("request_count"),
                func.count(func.distinct(LLMUsageLog.user_id)).label("active_users"),
            )
            .join(User, User.id == LLMUsageLog.user_id)
            .where(*filters)
        )
        totals_row = (await db.execute(totals_q)).one()

        users_q = (
            select(
                LLMUsageLog.user_id.label("user_id"),
                User.email.label("email"),
                func.coalesce(func.sum(LLMUsageLog.prompt_tokens), 0).label(
                    "prompt_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.completion_tokens), 0).label(
                    "completion_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label(
                    "total_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.cost_usd), 0.0).label(
                    "total_cost_usd"
                ),
                func.count(LLMUsageLog.id).label("request_count"),
                func.max(LLMUsageLog.created_at).label("last_used_at"),
            )
            .join(User, User.id == LLMUsageLog.user_id)
            .where(*filters)
            .group_by(LLMUsageLog.user_id, User.email)
            .order_by(
                func.count(LLMUsageLog.id).desc(),
                func.sum(LLMUsageLog.total_tokens).desc(),
                func.max(LLMUsageLog.created_at).desc(),
            )
            .limit(limit)
        )
        user_rows = (await db.execute(users_q)).all()

        total_users_q = select(func.count(User.id).label("total_users"))
        if email_filter:
            total_users_q = total_users_q.where(User.email.ilike(f"%{email_filter}%"))
        total_users_row = (await db.execute(total_users_q)).one()

        users = [
            {
                "user_id": str(row.user_id),
                "email": row.email,
                "prompt_tokens": int(row.prompt_tokens),
                "completion_tokens": int(row.completion_tokens),
                "total_tokens": int(row.total_tokens),
                "total_cost_usd": round(float(row.total_cost_usd), 6),
                "request_count": int(row.request_count),
                "last_used_at": row.last_used_at,
            }
            for row in user_rows
        ]
        users.sort(
            key=lambda row: (
                -row["request_count"],
                -row["total_tokens"],
                -(row["last_used_at"].timestamp() if row["last_used_at"] else 0),
                row["email"],
            )
        )

        activity_chart = await self._get_admin_activity_chart(
            db,
            period=period,
            email=email,
            now=now,
            month=month,
        )

        return {
            "period": period,
            "prompt_tokens": int(totals_row.prompt_tokens),
            "completion_tokens": int(totals_row.completion_tokens),
            "total_tokens": int(totals_row.total_tokens),
            "total_cost_usd": round(float(totals_row.total_cost_usd), 6),
            "request_count": int(totals_row.request_count),
            "active_users": int(totals_row.active_users),
            "total_users": int(total_users_row.total_users),
            "activity_chart": activity_chart,
            "users": users,
        }

    async def _get_admin_activity_chart(
        self,
        db: AsyncSession,
        *,
        period: str,
        email: str | None,
        now: datetime | None,
        month: str | None,
    ) -> dict[str, Any]:
        window = _activity_chart_window(period, now=now, month=month)
        if window is None:
            return _activity_chart_disabled(period)

        granularity, start, end, step, bucket_count = window
        bucket_starts = [start + step * index for index in range(bucket_count)]
        buckets: dict[datetime, dict[str, Any]] = {
            bucket_start: {
                "bucket_start": bucket_start,
                "bucket_end": bucket_start + step,
                "label": _bucket_label(bucket_start, granularity),
                "active_users": 0,
                "request_count": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "height_percent": 0,
                "users": [],
            }
            for bucket_start in bucket_starts
        }

        filters = [
            LLMUsageLog.created_at >= start,
            LLMUsageLog.created_at < end,
        ]
        if email:
            filters.append(User.email.ilike(f"%{email.strip()}%"))

        bucket_expr = _bucket_sql_expression(granularity)
        bucket_totals_q = (
            select(
                bucket_expr,
                func.count(func.distinct(LLMUsageLog.user_id)).label("active_users"),
                func.count(LLMUsageLog.id).label("request_count"),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label(
                    "total_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.cost_usd), 0.0).label(
                    "total_cost_usd"
                ),
            )
            .join(User, User.id == LLMUsageLog.user_id)
            .where(*filters)
            .group_by(bucket_expr)
        )
        bucket_total_rows = (await db.execute(bucket_totals_q)).all()
        for row in bucket_total_rows:
            bucket_start = _as_utc(row.bucket_start)
            bucket = buckets.get(bucket_start)
            if bucket is None:
                continue
            bucket["active_users"] = int(row.active_users)
            bucket["request_count"] = int(row.request_count)
            bucket["total_tokens"] = int(row.total_tokens)
            bucket["total_cost_usd"] = round(float(row.total_cost_usd), 6)

        bucket_user_expr = _bucket_sql_expression(granularity)
        bucket_users_q = (
            select(
                bucket_user_expr,
                LLMUsageLog.user_id.label("user_id"),
                User.email.label("email"),
                func.count(LLMUsageLog.id).label("request_count"),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label(
                    "total_tokens"
                ),
                func.coalesce(func.sum(LLMUsageLog.cost_usd), 0.0).label(
                    "total_cost_usd"
                ),
            )
            .join(User, User.id == LLMUsageLog.user_id)
            .where(*filters)
            .group_by(bucket_user_expr, LLMUsageLog.user_id, User.email)
            .order_by(
                bucket_user_expr,
                desc(func.count(LLMUsageLog.id)),
                desc(func.sum(LLMUsageLog.total_tokens)),
            )
        )
        bucket_user_rows = (await db.execute(bucket_users_q)).all()
        active_user_ids = {row.user_id for row in bucket_user_rows}
        latest_actions = await self._latest_activity_actions_for_chart(
            db,
            user_ids=active_user_ids,
            start=start,
            end=end,
            granularity=granularity,
        )

        for row in bucket_user_rows:
            bucket_start = _as_utc(row.bucket_start)
            bucket = buckets.get(bucket_start)
            if bucket is None:
                continue
            latest = latest_actions.get((bucket_start, row.user_id))
            bucket["users"].append(
                {
                    "user_id": str(row.user_id),
                    "email": row.email,
                    "request_count": int(row.request_count),
                    "total_tokens": int(row.total_tokens),
                    "total_cost_usd": round(float(row.total_cost_usd), 6),
                    "latest_action": latest["label"] if latest else None,
                    "latest_action_at": latest["created_at"] if latest else None,
                }
            )

        max_active_users = max(
            (bucket["active_users"] for bucket in buckets.values()),
            default=0,
        )
        for bucket in buckets.values():
            if max_active_users:
                bucket["height_percent"] = max(
                    6,
                    round((bucket["active_users"] / max_active_users) * 100),
                )
            bucket["users"].sort(
                key=lambda row: (
                    -row["request_count"],
                    -row["total_tokens"],
                    row["email"],
                )
            )

        return {
            "enabled": True,
            "period": period,
            "bucket_granularity": granularity,
            "timezone": "UTC",
            "period_label": _month_label(start)
            if period == "month"
            else ("Last 24 hours" if period == "day" else "Last 7 days"),
            "selected_month": _month_key(start) if period == "month" else None,
            "previous_month": _month_key(_add_months(start, -1))
            if period == "month"
            else None,
            "previous_month_label": _month_label(_add_months(start, -1))
            if period == "month"
            else None,
            "next_month": _month_key(_add_months(start, 1))
            if period == "month"
            else None,
            "next_month_label": _month_label(_add_months(start, 1))
            if period == "month"
            else None,
            "empty_reason": None,
            "buckets": [buckets[bucket_start] for bucket_start in bucket_starts],
        }

    async def _latest_activity_actions_for_chart(
        self,
        db: AsyncSession,
        *,
        user_ids: set[uuid.UUID],
        start: datetime,
        end: datetime,
        granularity: str,
    ) -> dict[tuple[datetime, uuid.UUID], dict[str, Any]]:
        if not user_ids:
            return {}

        from src.activity.models import UserActivityEvent
        from src.activity.service import _human_event_label

        activity_q = (
            select(UserActivityEvent)
            .where(
                UserActivityEvent.user_id.in_(user_ids),
                UserActivityEvent.created_at >= start,
                UserActivityEvent.created_at < end,
            )
            .order_by(UserActivityEvent.created_at.desc())
        )
        activity_rows = (await db.execute(activity_q)).all()
        latest: dict[tuple[datetime, uuid.UUID], dict[str, Any]] = {}
        for row in activity_rows:
            event = _row_entity(row)
            event_user_id = getattr(event, "user_id", None)
            created_at = getattr(event, "created_at", None)
            if event_user_id is None or not isinstance(created_at, datetime):
                continue
            key = (_bucket_for_timestamp(created_at, granularity), event_user_id)
            if key in latest:
                continue
            latest[key] = {
                "label": _human_event_label(event),
                "created_at": _as_utc(created_at),
            }
        return latest

    async def get_admin_user_usage_detail(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        period: str = "month",
        limit: int = 200,
    ) -> dict[str, Any] | None:
        """Return request-level usage detail for one user, split by type."""
        period, since = resolve_period_start(period)

        user_q = select(User.id, User.email).where(User.id == user_id)
        user_row = (await db.execute(user_q)).one_or_none()
        if user_row is None:
            return None

        base_filters = (
            LLMUsageLog.user_id == user_id,
            LLMUsageLog.created_at >= since,
        )

        split_q = (
            select(
                LLMUsageLog.feature.label("feature"),
                func.count(LLMUsageLog.id).label("request_count"),
                func.coalesce(func.sum(LLMUsageLog.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LLMUsageLog.cost_usd), 0.0).label("cost_usd"),
            )
            .where(*base_filters)
            .group_by(LLMUsageLog.feature)
            .order_by(
                func.count(LLMUsageLog.id).desc(),
                func.sum(LLMUsageLog.total_tokens).desc(),
            )
        )
        split_rows = (await db.execute(split_q)).all()
        split_by_type = [
            {
                "type": row.feature,
                "type_label": usage_feature_label(row.feature),
                "request_count": int(row.request_count),
                "tokens": int(row.tokens),
                "cost_usd": round(float(row.cost_usd), 6),
            }
            for row in split_rows
        ]

        requests_q = (
            select(
                LLMUsageLog.id,
                LLMUsageLog.feature,
                LLMUsageLog.model,
                LLMUsageLog.prompt_tokens,
                LLMUsageLog.completion_tokens,
                LLMUsageLog.total_tokens,
                LLMUsageLog.cost_usd,
                LLMUsageLog.created_at,
            )
            .where(*base_filters)
            .order_by(LLMUsageLog.created_at.desc())
            .limit(limit)
        )
        request_rows = (await db.execute(requests_q)).all()
        requests = [
            {
                "request_id": str(row.id),
                "feature": row.feature,
                "feature_label": usage_feature_label(row.feature),
                "model": row.model,
                "prompt_tokens": int(row.prompt_tokens),
                "completion_tokens": int(row.completion_tokens),
                "total_tokens": int(row.total_tokens),
                "cost_usd": round(float(row.cost_usd), 6),
                "created_at": row.created_at,
            }
            for row in request_rows
        ]
        requests.sort(key=lambda row: row["created_at"], reverse=True)

        total_count_q = select(func.count(LLMUsageLog.id).label("total")).where(
            *base_filters
        )
        total_count_row = (await db.execute(total_count_q)).one()

        # Local import avoids a module cycle: activity service reuses usage periods.
        from src.activity.service import ActivityService

        activity_sessions = await ActivityService(
            self._session_factory
        ).get_admin_activity_sessions(
            db,
            user_id=user_id,
            period=period,
            limit=limit,
        )

        return {
            "user_id": str(user_row.id),
            "email": user_row.email,
            "period": period,
            "request_count_total": int(total_count_row.total),
            "request_count_returned": len(requests),
            "activity_sessions": activity_sessions,
            "split_by_type": split_by_type,
            "requests": requests,
        }
