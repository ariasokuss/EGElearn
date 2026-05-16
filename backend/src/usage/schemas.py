from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from src.activity.schemas import AdminActivitySessionRow


class FeatureUsage(BaseModel):
    tokens: int
    cost_usd: float


class UsageStatsResponse(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    by_model: dict[str, FeatureUsage]
    by_feature: dict[str, FeatureUsage]
    period: str


class AdminUserUsageRow(BaseModel):
    user_id: str
    email: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    request_count: int
    last_used_at: datetime | None


class AdminActivityChartUserRow(BaseModel):
    user_id: str
    email: str
    request_count: int
    total_tokens: int
    total_cost_usd: float
    latest_action: str | None
    latest_action_at: datetime | None


class AdminActivityChartBucket(BaseModel):
    bucket_start: datetime
    bucket_end: datetime
    label: str
    active_users: int
    request_count: int
    total_tokens: int
    total_cost_usd: float
    height_percent: int
    users: list[AdminActivityChartUserRow]


class AdminActivityChart(BaseModel):
    enabled: bool
    period: str
    bucket_granularity: str | None
    timezone: str
    period_label: str
    selected_month: str | None
    previous_month: str | None
    previous_month_label: str | None
    next_month: str | None
    next_month_label: str | None
    empty_reason: str | None
    buckets: list[AdminActivityChartBucket]


class AdminUsageOverviewResponse(BaseModel):
    period: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    request_count: int
    active_users: int
    total_users: int
    activity_chart: AdminActivityChart
    users: list[AdminUserUsageRow]


class AdminUsageTypeSplitRow(BaseModel):
    type: str
    type_label: str
    request_count: int
    tokens: int
    cost_usd: float


class AdminUsageRequestRow(BaseModel):
    request_id: str
    feature: str
    feature_label: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    created_at: datetime


class AdminUserUsageDetailResponse(BaseModel):
    user_id: str
    email: str
    period: str
    request_count_total: int
    request_count_returned: int
    activity_sessions: list[AdminActivitySessionRow]
    split_by_type: list[AdminUsageTypeSplitRow]
    requests: list[AdminUsageRequestRow]
