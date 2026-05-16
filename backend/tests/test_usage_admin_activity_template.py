from __future__ import annotations

import inspect
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.usage.admin import (
    templates,
    usage_admin_style,
    usage_admin_user_data,
    usage_admin_user_page,
)


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src" / "usage" / "templates"


def _query_default(fn, name: str):
    return inspect.signature(fn).parameters[name].default.default


def _render_user_detail(detail):
    return templates.env.get_template("usage_user_detail.html").render(
        title="User Usage",
        request=SimpleNamespace(
            url=SimpleNamespace(path=f"/admin/usage/users/{detail['user_id']}")
        ),
        detail=detail,
        current_period="week",
        current_limit=200,
        period_options=["day", "week", "month", "all"],
        generated_at=datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc),
    )


def _render_dashboard(overview, *, current_period="month"):
    return templates.env.get_template("usage_dashboard.html").render(
        title="Admin Usage",
        request=SimpleNamespace(url=SimpleNamespace(path="/admin/usage")),
        overview=overview,
        current_period=current_period,
        current_limit=50,
        current_email="",
        current_month=(overview.get("activity_chart") or {}).get("selected_month"),
        period_options=["day", "week", "month", "all"],
        generated_at=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
    )


def _overview(activity_chart):
    return {
        "period": "month",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "total_cost_usd": 0.42,
        "request_count": 3,
        "active_users": 2,
        "total_users": 64,
        "activity_chart": activity_chart,
        "users": [],
    }


def _detail(activity_sessions):
    return {
        "user_id": str(uuid.uuid4()),
        "email": "alice@example.com",
        "period": "week",
        "request_count_total": 0,
        "request_count_returned": 0,
        "activity_sessions": activity_sessions,
        "split_by_type": [],
        "requests": [],
    }


def test_admin_user_usage_routes_default_to_week_period():
    assert _query_default(usage_admin_user_data, "period") == "week"
    assert _query_default(usage_admin_user_page, "period") == "week"


def test_user_detail_template_uses_versioned_usage_css():
    html = _render_user_detail(_detail([]))

    assert '/admin/usage/static/style.css?v=' in html


def test_dashboard_template_renders_activity_chart_drilldown():
    user_id = uuid.uuid4()
    bucket_start = datetime(2026, 5, 5, 0, 0, tzinfo=timezone.utc)
    html = _render_dashboard(
        _overview(
            {
                "enabled": True,
                "period": "month",
                "bucket_granularity": "day",
                "timezone": "UTC",
                "period_label": "May 2026",
                "selected_month": "2026-05",
                "previous_month": "2026-04",
                "previous_month_label": "April 2026",
                "next_month": "2026-06",
                "next_month_label": "June 2026",
                "empty_reason": None,
                "buckets": [
                    {
                        "bucket_start": bucket_start,
                        "bucket_end": datetime(2026, 5, 6, 0, 0, tzinfo=timezone.utc),
                        "label": "2026-05-05",
                        "active_users": 2,
                        "request_count": 3,
                        "total_tokens": 150,
                        "total_cost_usd": 0.42,
                        "height_percent": 100,
                        "users": [
                            {
                                "user_id": str(user_id),
                                "email": "alice@example.com",
                                "request_count": 3,
                                "total_tokens": 150,
                                "total_cost_usd": 0.42,
                                "latest_action": "Submitted test: 4/5 answered, 78%",
                                "latest_action_at": datetime(
                                    2026, 5, 5, 12, 30, tzinfo=timezone.utc
                                ),
                            }
                        ],
                    }
                ],
            }
        )
    )

    assert "Activity" in html
    assert "Active users by day" in html
    assert "UTC" in html
    assert "May 2026" in html
    assert '--activity-bucket-count: 1' in html
    assert 'data-activity-bucket-trigger="activity-bucket-0"' in html
    assert "--activity-bar-height: 100%" in html
    assert "2 users" in html
    assert "3 requests" in html
    assert "alice@example.com" in html
    assert "150 tokens" in html
    assert "$0.420000" in html
    assert "Submitted test: 4/5 answered, 78%" in html
    assert f"/admin/usage/users/{user_id}" in html
    assert "period=month" in html
    assert "limit=50" in html


def test_dashboard_template_renders_total_users_stat_card():
    html = _render_dashboard(
        _overview(
            {
                "enabled": False,
                "period": "all",
                "bucket_granularity": None,
                "timezone": "UTC",
                "period_label": "All time",
                "selected_month": None,
                "previous_month": None,
                "previous_month_label": None,
                "next_month": None,
                "next_month_label": None,
                "empty_reason": "Chart supports day, week, and month periods.",
                "buckets": [],
            }
        )
    )

    assert "<h2>Total Users</h2>" in html
    assert '<div class="value">64</div>' in html
    assert "<h2>Requests</h2>" not in html


def test_dashboard_template_renders_month_navigation_labels_and_links():
    html = _render_dashboard(
        _overview(
            {
                "enabled": True,
                "period": "month",
                "bucket_granularity": "day",
                "timezone": "UTC",
                "period_label": "April 2026",
                "selected_month": "2026-04",
                "previous_month": "2026-03",
                "previous_month_label": "March 2026",
                "next_month": "2026-05",
                "next_month_label": "May 2026",
                "empty_reason": None,
                "buckets": [],
            }
        )
    )

    assert "April 2026" in html
    assert "March 2026" in html
    assert "May 2026" in html
    assert "month=2026-03" in html
    assert 'name="month" value="2026-04"' in html
    assert "month=2026-05" in html


def test_activity_chart_css_fits_buckets_without_internal_scroll():
    css = (TEMPLATES_DIR / "usage.css").read_text()
    chart_block = css[
        css.index(".activity-chart-bars {") : css.index(".activity-chart-bar {")
    ]
    bar_block = css[
        css.index(".activity-chart-bar {") : css.index(".activity-chart-bar-track {")
    ]
    label_block = css[
        css.index(".activity-chart-bar-label {") : css.index(
            ".activity-chart-bar.is-selected .activity-chart-bar-label {"
        )
    ]

    assert "grid-template-columns: repeat(var(--activity-bucket-count), minmax(0, 1fr));" in chart_block
    assert "overflow-x: auto" not in chart_block
    assert "gap: 3px;" in bar_block
    assert "writing-mode" not in label_block
    assert "rotate(" not in label_block


def test_dashboard_template_renders_activity_chart_unsupported_all_state():
    html = _render_dashboard(
        _overview(
            {
                "enabled": False,
                "period": "all",
                "bucket_granularity": None,
                "timezone": "UTC",
                "period_label": "All time",
                "selected_month": None,
                "previous_month": None,
                "previous_month_label": None,
                "next_month": None,
                "next_month_label": None,
                "empty_reason": "Chart supports day, week, and month periods.",
                "buckets": [],
            }
        ),
        current_period="all",
    )

    assert "Activity" in html
    assert "Chart supports day, week, and month periods." in html
    assert "data-activity-bucket-trigger" not in html


@pytest.mark.asyncio
async def test_usage_admin_style_disables_browser_cache():
    response = await usage_admin_style()

    assert response.headers["cache-control"] == "no-store"


def test_user_detail_template_renders_activity_session_timeline():
    activity_sessions = [
        {
            "start_at": datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            "end_at": datetime(2026, 4, 2, 10, 5, 30, tzinfo=timezone.utc),
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
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "test_graded",
                    "event_group": "test",
                    "action_label": "Graded",
                    "created_at": datetime(2026, 4, 2, 10, 5, tzinfo=timezone.utc),
                    "label": "Test graded: 8/10 answered, 55%",
                    "metadata": {"answered_count": 8, "total_questions": 10},
                },
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "lesson_question_answered",
                    "event_group": "lesson",
                    "action_label": "Question Answered",
                    "created_at": datetime(2026, 4, 2, 10, 6, tzinfo=timezone.utc),
                    "label": "Answered lesson question correctly",
                    "metadata": {
                        "is_correct": True,
                        "earned_marks": 1,
                        "total_marks": 1,
                    },
                },
            ],
        }
    ]

    html = _render_user_detail(_detail(activity_sessions))

    assert "Activity Sessions" in html
    assert 'class="panel activity-panel"' in html
    assert 'class="activity-session-toggle"' in html
    assert 'class="event-type-chip"' in html
    assert "<details" in html
    assert "<summary" in html
    assert "Completed test with 55%" in html
    assert "2026-04-02 10:00" in html
    assert "2026-04-02 10:05" in html
    assert "330s" in html
    assert "3 events" in html
    assert "Low Score" in html
    assert "Chat After Low Score" in html
    assert "Test Started" not in html
    assert "Test Graded" not in html
    assert "Lesson Question Answered" not in html
    assert "Test" in html
    assert "Started" in html
    assert "Graded" in html
    assert "Lesson" in html
    assert "Question Answered" in html
    assert "Correct" in html
    assert "1/1" in html
    assert html.index(">Test<") < html.index(">Started<")
    assert html.index(">Lesson<") < html.index(">Question Answered<")
    assert html.index(">Question Answered<") < html.index(">Correct<")
    assert html.index(">Correct<") < html.index(">1/1<")
    assert "Started test, 10 questions" not in html
    assert "Test graded: 8/10 answered, 55%" not in html
    assert "Answered lesson question correctly" not in html


def test_user_detail_template_renders_activity_replay_payload_items():
    activity_sessions = [
        {
            "start_at": datetime(2026, 5, 5, 11, 0, tzinfo=timezone.utc),
            "end_at": datetime(2026, 5, 5, 11, 2, tzinfo=timezone.utc),
            "duration_seconds": 120,
            "event_count": 2,
            "summary": "Answered lesson question",
            "signals": [],
            "events": [
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "lesson_question_answered",
                    "event_group": "lesson",
                    "action_label": "Question Answered",
                    "created_at": datetime(2026, 5, 5, 11, 0, tzinfo=timezone.utc),
                    "label": "Answered private inline question",
                    "metadata": {
                        "is_correct": False,
                        "earned_marks": 1,
                        "total_marks": 3,
                    },
                    "replay_payload": {
                        "schema_version": 1,
                        "refs": {"question_id": "q-1"},
                        "items": [
                            {
                                "kind": "question",
                                "title": "Question",
                                "text": "Explain <script>alert('x')</script>",
                                "options": ["Option <b>A</b>", "Option B"],
                            },
                            {
                                "kind": "user_answer",
                                "title": "Answer",
                                "text": "First line\nSecond line",
                                "score": "1/3",
                                "earned_marks": 1,
                                "total_marks": 3,
                                "score_percent": 33.3,
                                "correctness": "partial",
                            },
                            {
                                "kind": "mark",
                                "title": "Awarded",
                                "value": "1 mark",
                            },
                        ],
                    },
                },
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "chat_opened",
                    "event_group": "chat",
                    "action_label": "Opened",
                    "created_at": datetime(2026, 5, 5, 11, 1, tzinfo=timezone.utc),
                    "label": "Opened chat panel",
                    "metadata": {},
                    "replay_payload": {"schema_version": 1, "items": []},
                },
            ],
        }
    ]

    html = _render_user_detail(_detail(activity_sessions))

    assert html.count('class="activity-replay"') == 1
    assert 'class="activity-replay-item"' in html
    assert "Question" in html
    assert "Answer" in html
    assert "Awarded" in html
    assert "1 mark" in html
    assert "Score 1/3" not in html
    assert ">1/3<" in html
    assert ">33%<" in html
    assert "Partial" in html
    assert "Option &lt;b&gt;A&lt;/b&gt;" in html
    assert "Option B" in html
    assert "First line\nSecond line" in html
    assert "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;" in html
    assert "<script>alert('x')</script>" not in html
    assert "Answered private inline question" not in html
    assert "Opened chat panel" not in html


def test_user_detail_template_renders_structured_mcq_options_without_noise():
    activity_sessions = [
        {
            "start_at": datetime(2026, 5, 5, 11, 0, tzinfo=timezone.utc),
            "end_at": datetime(2026, 5, 5, 11, 0, tzinfo=timezone.utc),
            "duration_seconds": 0,
            "event_count": 1,
            "summary": "Answered lesson question",
            "signals": [],
            "events": [
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": "lesson_question_answered",
                    "event_group": "lesson",
                    "action_label": "Question Answered",
                    "created_at": datetime(2026, 5, 5, 11, 0, tzinfo=timezone.utc),
                    "label": "Answered lesson question incorrectly",
                    "metadata": {
                        "is_correct": False,
                        "earned_marks": 0,
                        "total_marks": 1,
                    },
                    "replay_payload": {
                        "schema_version": 1,
                        "items": [
                            {
                                "kind": "question",
                                "title": "Question 1",
                                "text": "Which statement best describes rational choice?",
                                "options": [
                                    {
                                        "label": "A",
                                        "text": "It is always cheapest",
                                        "value": "A. It is always cheapest",
                                        "is_selected": False,
                                        "is_correct": False,
                                    },
                                    {
                                        "label": "B",
                                        "text": "It always turns out best in hindsight",
                                        "value": "B. It always turns out best in hindsight",
                                        "is_selected": False,
                                        "is_correct": False,
                                    },
                                    {
                                        "label": "C",
                                        "text": "It uses the information available to pursue the decision-maker's objective",
                                        "value": "C. It uses the information available to pursue the decision-maker's objective",
                                        "is_selected": False,
                                        "is_correct": True,
                                    },
                                    {
                                        "label": "D",
                                        "text": "It is always morally correct",
                                        "value": "D. It is always morally correct",
                                        "is_selected": True,
                                        "is_correct": False,
                                    },
                                ],
                            },
                            {
                                "kind": "user_answer",
                                "title": "User answer",
                                "text": "D. It is always morally correct",
                                "absorbed_into_options": True,
                            },
                            {
                                "kind": "answer_key",
                                "title": "Correct option",
                                "value": "C. It uses the information available to pursue the decision-maker's objective",
                                "absorbed_into_options": True,
                            },
                        ],
                    },
                },
            ],
        }
    ]

    html = _render_user_detail(_detail(activity_sessions))

    assert 'class="activity-mcq-options"' in html
    assert 'class="activity-mcq-option is-selected"' in html
    assert 'class="activity-mcq-option is-correct"' in html
    assert "<ol class=\"activity-replay-options\">" not in html
    assert ">Selected<" in html
    assert ">Correct<" in html
    assert ">User answer<" not in html
    assert ">Correct option<" not in html
    assert "D. It is always morally correct" not in html


def test_user_detail_template_renders_activity_empty_state():
    detail = _detail([])
    html = _render_user_detail(deepcopy(detail))

    assert "Activity Sessions" in html
    assert "No activity sessions found for this period." in html
