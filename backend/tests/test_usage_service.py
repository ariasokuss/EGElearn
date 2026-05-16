from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.activity import service as activity_service_module
from src.config import get_settings
from src.core.llm_usage import UsageInfo
from src.usage.schemas import AdminUserUsageDetailResponse
from src.usage.service import UsageService, calculate_cost, resolve_period_start


class _ResultStub:
    def __init__(self, *, one_value=None, all_value=None):
        self._one_value = one_value
        self._all_value = all_value or []

    def one(self):
        return self._one_value

    def one_or_none(self):
        return self._one_value

    def all(self):
        return self._all_value


def _svc() -> UsageService:
    return UsageService(session_factory=object())


def test_yandexgpt_is_the_only_configured_chat_model():
    settings = get_settings()
    legacy_chatgpt = "Chat" + "GPT 5.4"
    legacy_sonnet = "Clau" + "de Son" + "net 4.6"
    legacy_opus = "Clau" + "de O" + "pus 4.6"

    assert settings.llm.model_id_map == {"YandexGPT": "yandexgpt/latest"}
    assert legacy_chatgpt not in settings.llm.model_id_map
    assert legacy_sonnet not in settings.llm.model_id_map
    assert legacy_opus not in settings.llm.model_id_map
    assert calculate_cost("yandexgpt/latest", 1_000_000, 1_000_000) == 0.0


class _RecordingSession:
    def __init__(self, records):
        self._records = records

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def add(self, record):
        self._records.append(record)

    async def commit(self):
        return None


def _recording_session_factory(records):
    def session_factory():
        return _RecordingSession(records)

    return session_factory


@pytest.mark.asyncio
async def test_log_usage_persists_exact_cost_when_present():
    records = []
    usage = UsageInfo(
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        total_tokens=2_000_000,
        model="openai/gpt-5.4",
        cost_usd=0.123456789,
    )

    await UsageService(
        session_factory=_recording_session_factory(records)
    ).log_usage(
        user_id=uuid.uuid4(),
        feature="chat",
        usage=usage,
    )

    assert len(records) == 1
    assert records[0].cost_usd == 0.12345679


@pytest.mark.asyncio
async def test_log_usage_falls_back_to_yandex_pricing_table_when_exact_cost_missing():
    records = []
    usage = UsageInfo(
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        total_tokens=2_000_000,
        model="yandexgpt/latest",
    )

    await UsageService(
        session_factory=_recording_session_factory(records)
    ).log_usage(
        user_id=uuid.uuid4(),
        feature="chat",
        usage=usage,
    )

    assert len(records) == 1
    assert records[0].cost_usd == 0.0


def test_resolve_period_start_falls_back_to_month_for_unknown_period():
    now = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)

    period, since = resolve_period_start("unexpected", now=now)

    assert period == "month"
    assert since == now - timedelta(days=30)


@pytest.mark.asyncio
async def test_get_admin_usage_overview_uses_selected_calendar_month_for_chart():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(
                one_value=SimpleNamespace(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    total_cost_usd=0.0,
                    request_count=0,
                    active_users=0,
                )
            ),
            _ResultStub(all_value=[]),
            _ResultStub(one_value=SimpleNamespace(total_users=0)),
            _ResultStub(all_value=[]),
            _ResultStub(all_value=[]),
        ]
    )

    result = await _svc().get_admin_usage_overview(
        db,
        period="month",
        limit=50,
        month="2026-04",
        now=datetime(2026, 5, 6, 13, 45, tzinfo=timezone.utc),
    )

    chart = result["activity_chart"]
    assert chart["enabled"] is True
    assert chart["period_label"] == "April 2026"
    assert chart["selected_month"] == "2026-04"
    assert chart["previous_month"] == "2026-03"
    assert chart["previous_month_label"] == "March 2026"
    assert chart["next_month"] == "2026-05"
    assert chart["next_month_label"] == "May 2026"
    assert len(chart["buckets"]) == 30
    assert chart["buckets"][0]["bucket_start"] == datetime(
        2026, 4, 1, tzinfo=timezone.utc
    )
    assert chart["buckets"][0]["label"] == "1"
    assert chart["buckets"][-1]["bucket_start"] == datetime(
        2026, 4, 30, tzinfo=timezone.utc
    )
    assert chart["buckets"][-1]["label"] == "30"


@pytest.mark.asyncio
async def test_get_admin_usage_overview_builds_rows_and_totals():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    totals_row = SimpleNamespace(
        prompt_tokens=130,
        completion_tokens=70,
        total_tokens=200,
        total_cost_usd=0.42,
        request_count=6,
        active_users=2,
    )

    users_rows = [
        SimpleNamespace(
            user_id=user_a,
            email="alice@example.com",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            total_cost_usd=0.33,
            request_count=4,
            last_used_at=datetime(2026, 4, 2, 11, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            user_id=user_b,
            email="bob@example.com",
            prompt_tokens=30,
            completion_tokens=20,
            total_tokens=50,
            total_cost_usd=0.09,
            request_count=2,
            last_used_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
        ),
    ]

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(one_value=totals_row),
            _ResultStub(all_value=users_rows),
            _ResultStub(one_value=SimpleNamespace(total_users=14)),
            _ResultStub(all_value=[]),
            _ResultStub(all_value=[]),
        ]
    )

    result = await _svc().get_admin_usage_overview(
        db,
        period="week",
        limit=50,
    )

    assert result["period"] == "week"
    assert result["prompt_tokens"] == 130
    assert result["completion_tokens"] == 70
    assert result["total_tokens"] == 200
    assert result["total_cost_usd"] == 0.42
    assert result["request_count"] == 6
    assert result["active_users"] == 2
    assert result["total_users"] == 14
    assert result["activity_chart"]["enabled"] is True
    assert result["activity_chart"]["period"] == "week"
    assert len(result["activity_chart"]["buckets"]) == 7

    assert len(result["users"]) == 2
    assert result["users"][0]["email"] == "alice@example.com"
    assert result["users"][0]["total_cost_usd"] == 0.33
    assert result["users"][1]["email"] == "bob@example.com"
    assert result["users"][1]["request_count"] == 2


@pytest.mark.asyncio
async def test_get_admin_usage_overview_sorts_users_by_activity_even_if_db_rows_are_unordered():
    high_activity = uuid.uuid4()
    low_activity = uuid.uuid4()
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(
                one_value=SimpleNamespace(
                    prompt_tokens=130,
                    completion_tokens=70,
                    total_tokens=200,
                    total_cost_usd=0.42,
                    request_count=6,
                    active_users=2,
                )
            ),
            _ResultStub(
                all_value=[
                    SimpleNamespace(
                        user_id=low_activity,
                        email="low@example.com",
                        prompt_tokens=10,
                        completion_tokens=5,
                        total_tokens=15,
                        total_cost_usd=0.01,
                        request_count=1,
                        last_used_at=datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                    ),
                    SimpleNamespace(
                        user_id=high_activity,
                        email="high@example.com",
                        prompt_tokens=90,
                        completion_tokens=40,
                        total_tokens=130,
                        total_cost_usd=0.2,
                        request_count=5,
                        last_used_at=datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc),
                    ),
                ]
            ),
            _ResultStub(one_value=SimpleNamespace(total_users=2)),
            _ResultStub(all_value=[]),
            _ResultStub(all_value=[]),
        ]
    )

    result = await _svc().get_admin_usage_overview(db, period="week", limit=50)

    assert [row["email"] for row in result["users"]] == [
        "high@example.com",
        "low@example.com",
    ]


@pytest.mark.asyncio
async def test_get_admin_usage_overview_includes_activity_chart_with_latest_actions():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    now = datetime(2026, 5, 6, 13, 45, tzinfo=timezone.utc)
    bucket_start = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(
                one_value=SimpleNamespace(
                    prompt_tokens=200,
                    completion_tokens=100,
                    total_tokens=300,
                    total_cost_usd=0.5,
                    request_count=5,
                    active_users=2,
                )
            ),
            _ResultStub(all_value=[]),
            _ResultStub(one_value=SimpleNamespace(total_users=7)),
            _ResultStub(
                all_value=[
                    SimpleNamespace(
                        bucket_start=bucket_start,
                        active_users=2,
                        request_count=5,
                        total_tokens=300,
                        total_cost_usd=0.5,
                    )
                ]
            ),
            _ResultStub(
                all_value=[
                    SimpleNamespace(
                        bucket_start=bucket_start,
                        user_id=user_a,
                        email="alice@example.com",
                        request_count=3,
                        total_tokens=180,
                        total_cost_usd=0.3,
                    ),
                    SimpleNamespace(
                        bucket_start=bucket_start,
                        user_id=user_b,
                        email="bob@example.com",
                        request_count=2,
                        total_tokens=120,
                        total_cost_usd=0.2,
                    ),
                ]
            ),
            _ResultStub(
                all_value=[
                    SimpleNamespace(
                        user_id=user_a,
                        event_type="lesson_opened",
                        event_group="lesson",
                        route_label=None,
                        request_path="/learning/lessons/abc",
                        event_metadata={"lesson_name": "Demand lesson"},
                        created_at=datetime(2026, 5, 6, 12, 30, tzinfo=timezone.utc),
                    )
                ]
            ),
        ]
    )

    result = await _svc().get_admin_usage_overview(
        db,
        period="day",
        limit=50,
        now=now,
    )

    chart = result["activity_chart"]
    assert chart["enabled"] is True
    assert chart["period"] == "day"
    assert chart["bucket_granularity"] == "hour"
    assert chart["timezone"] == "UTC"
    assert len(chart["buckets"]) == 24

    bucket = next(
        item for item in chart["buckets"] if item["bucket_start"] == bucket_start
    )
    assert bucket["label"] == "12:00"
    assert bucket["active_users"] == 2
    assert bucket["request_count"] == 5
    assert bucket["total_tokens"] == 300
    assert bucket["total_cost_usd"] == 0.5

    assert [row["email"] for row in bucket["users"]] == [
        "alice@example.com",
        "bob@example.com",
    ]
    assert bucket["users"][0]["request_count"] == 3
    assert bucket["users"][0]["latest_action"] == "Opened lesson Demand lesson"
    assert bucket["users"][0]["latest_action_at"] == datetime(
        2026, 5, 6, 12, 30, tzinfo=timezone.utc
    )
    assert bucket["users"][1]["latest_action"] is None


@pytest.mark.asyncio
async def test_get_admin_usage_overview_disables_activity_chart_for_all_period():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(
                one_value=SimpleNamespace(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    total_cost_usd=0.0,
                    request_count=0,
                    active_users=0,
                )
            ),
            _ResultStub(all_value=[]),
            _ResultStub(one_value=SimpleNamespace(total_users=0)),
        ]
    )

    result = await _svc().get_admin_usage_overview(
        db,
        period="all",
        limit=50,
        now=datetime(2026, 5, 6, 13, 45, tzinfo=timezone.utc),
    )

    chart = result["activity_chart"]
    assert chart["enabled"] is False
    assert chart["period"] == "all"
    assert chart["bucket_granularity"] is None
    assert chart["timezone"] == "UTC"
    assert chart["period_label"] == "All time"
    assert chart["selected_month"] is None
    assert chart["previous_month"] is None
    assert chart["next_month"] is None
    assert chart["empty_reason"] == "Chart supports day, week, and month periods."
    assert chart["buckets"] == []
    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_get_admin_user_usage_detail_returns_split_by_type_and_requests():
    user_id = uuid.uuid4()

    user_row = SimpleNamespace(id=user_id, email="alice@example.com")
    split_rows = [
        SimpleNamespace(feature="chat", request_count=3, tokens=120, cost_usd=0.21),
        SimpleNamespace(
            feature="feynman", request_count=1, tokens=40, cost_usd=0.08
        ),
    ]
    requests_rows = [
        SimpleNamespace(
            id=uuid.uuid4(),
            feature="chat",
            model="openai/gpt-5.4",
            prompt_tokens=30,
            completion_tokens=20,
            total_tokens=50,
            cost_usd=0.05,
            created_at=datetime(2026, 4, 2, 11, 15, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            feature="feynman",
            model="yandexgpt/latest",
            prompt_tokens=10,
            completion_tokens=30,
            total_tokens=40,
            cost_usd=0.08,
            created_at=datetime(2026, 4, 2, 10, 45, tzinfo=timezone.utc),
        ),
    ]
    total_count_row = SimpleNamespace(total=4)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(one_value=user_row),
            _ResultStub(all_value=split_rows),
            _ResultStub(all_value=requests_rows),
            _ResultStub(one_value=total_count_row),
        ]
    )

    result = await _svc().get_admin_user_usage_detail(
        db,
        user_id=user_id,
        period="month",
        limit=50,
    )

    assert result is not None
    assert result["user_id"] == str(user_id)
    assert result["email"] == "alice@example.com"
    assert result["period"] == "month"
    assert result["request_count_total"] == 4

    assert len(result["split_by_type"]) == 2
    assert result["split_by_type"][0]["type"] == "chat"
    assert result["split_by_type"][0]["type_label"] == "Chat"
    assert result["split_by_type"][0]["request_count"] == 3
    assert result["split_by_type"][1]["type"] == "feynman"
    assert result["split_by_type"][1]["type_label"] == "Feynman"

    assert len(result["requests"]) == 2
    assert result["requests"][0]["feature"] == "chat"
    assert result["requests"][0]["feature_label"] == "Chat"
    assert result["requests"][1]["model"] == "yandexgpt/latest"
    assert result["requests"][1]["feature_label"] == "Feynman"


@pytest.mark.asyncio
async def test_get_admin_user_usage_detail_sorts_request_logs_newest_first():
    user_id = uuid.uuid4()
    older = datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc)
    newer = datetime(2026, 4, 2, 11, 0, tzinfo=timezone.utc)
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(one_value=SimpleNamespace(id=user_id, email="alice@example.com")),
            _ResultStub(all_value=[]),
            _ResultStub(
                all_value=[
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        feature="chat",
                        model="openai/gpt-5.4",
                        prompt_tokens=1,
                        completion_tokens=1,
                        total_tokens=2,
                        cost_usd=0.01,
                        created_at=older,
                    ),
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        feature="feynman",
                        model="openai/gpt-5.4",
                        prompt_tokens=2,
                        completion_tokens=2,
                        total_tokens=4,
                        cost_usd=0.02,
                        created_at=newer,
                    ),
                ]
            ),
            _ResultStub(one_value=SimpleNamespace(total=2)),
        ]
    )

    result = await _svc().get_admin_user_usage_detail(
        db,
        user_id=user_id,
        period="week",
        limit=50,
    )

    assert result is not None
    assert [row["created_at"] for row in result["requests"]] == [newer, older]


@pytest.mark.asyncio
async def test_get_admin_user_usage_detail_labels_chat_title_and_practice_hint():
    user_id = uuid.uuid4()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(one_value=SimpleNamespace(id=user_id, email="alice@example.com")),
            _ResultStub(
                all_value=[
                    SimpleNamespace(
                        feature="chat_title",
                        request_count=2,
                        tokens=18,
                        cost_usd=0.01,
                    ),
                    SimpleNamespace(
                        feature="test_practice_hint",
                        request_count=1,
                        tokens=100,
                        cost_usd=0.05,
                    ),
                ]
            ),
            _ResultStub(
                all_value=[
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        feature="chat_title",
                        model="openai/gpt-5.4",
                        prompt_tokens=10,
                        completion_tokens=8,
                        total_tokens=18,
                        cost_usd=0.01,
                        created_at=datetime(2026, 4, 2, 11, 15, tzinfo=timezone.utc),
                    ),
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        feature="test_practice_hint",
                        model="openai/gpt-5.4",
                        prompt_tokens=80,
                        completion_tokens=20,
                        total_tokens=100,
                        cost_usd=0.05,
                        created_at=datetime(2026, 4, 2, 11, 10, tzinfo=timezone.utc),
                    ),
                ]
            ),
            _ResultStub(one_value=SimpleNamespace(total=3)),
        ]
    )

    result = await _svc().get_admin_user_usage_detail(
        db,
        user_id=user_id,
        period="week",
        limit=50,
    )

    assert result is not None
    assert result["split_by_type"][0]["type_label"] == "Chat Title"
    assert result["split_by_type"][1]["type_label"] == "Practice Hint Chat"
    assert result["requests"][0]["feature_label"] == "Chat Title"
    assert result["requests"][1]["feature_label"] == "Practice Hint Chat"


@pytest.mark.asyncio
async def test_get_admin_user_usage_detail_includes_activity_sessions(monkeypatch):
    user_id = uuid.uuid4()
    session_factory = object()
    activity_sessions = [
        {
            "start_at": datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            "end_at": datetime(2026, 4, 2, 10, 5, tzinfo=timezone.utc),
            "duration_seconds": 330,
            "event_count": 3,
            "summary": "Completed test with 55%",
            "signals": ["low_score", "chat_after_low_score"],
            "events": [
                    {
                        "event_id": str(uuid.uuid4()),
                        "event_type": "test_started",
                        "event_group": "test",
                        "action_label": "Started",
                        "created_at": datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
                        "label": "Started test, 10 questions",
                        "metadata": {"total_questions": 10},
                },
            ],
        }
    ]
    calls = {}

    class FakeActivityService:
        def __init__(self, actual_session_factory):
            calls["session_factory"] = actual_session_factory

        async def get_admin_activity_sessions(
            self,
            actual_db,
            *,
            user_id,
            period,
            limit,
        ):
            calls["db"] = actual_db
            calls["user_id"] = user_id
            calls["period"] = period
            calls["limit"] = limit
            return activity_sessions

    monkeypatch.setattr(activity_service_module, "ActivityService", FakeActivityService)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ResultStub(one_value=SimpleNamespace(id=user_id, email="alice@example.com")),
            _ResultStub(all_value=[]),
            _ResultStub(all_value=[]),
            _ResultStub(one_value=SimpleNamespace(total=0)),
        ]
    )

    result = await UsageService(session_factory=session_factory).get_admin_user_usage_detail(
        db,
        user_id=user_id,
        period="week",
        limit=25,
    )

    assert result is not None
    assert result["activity_sessions"] == activity_sessions
    response = AdminUserUsageDetailResponse(**result)
    assert response.activity_sessions[0].summary == "Completed test with 55%"
    assert calls == {
        "session_factory": session_factory,
        "db": db,
        "user_id": user_id,
        "period": "week",
        "limit": 25,
    }


@pytest.mark.asyncio
async def test_get_admin_user_usage_detail_returns_none_when_user_missing():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ResultStub(one_value=None)])

    result = await _svc().get_admin_user_usage_detail(
        db,
        user_id=uuid.uuid4(),
        period="week",
        limit=20,
    )

    assert result is None
