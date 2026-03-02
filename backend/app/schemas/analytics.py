"""Pydantic schemas for analytics and reporting endpoints."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class DailyCount(BaseModel):
    date: str  # ISO date string: "2026-03-01"
    count: int


class DashboardResponse(BaseModel):
    calls_today: int
    calls_this_week: int
    calls_this_month: int
    active_campaigns: int
    webrtc_count: int
    phone_count: int
    # Last 7 calendar days (today inclusive), oldest first
    calls_last_7_days: list[DailyCount]


class TargetStats(BaseModel):
    target_id: uuid.UUID
    name: str
    total_calls: int
    completed_calls: int
    avg_duration_seconds: float | None


class CampaignStatsResponse(BaseModel):
    total_sessions: int
    completed_sessions: int
    completion_rate: float  # 0.0–1.0
    avg_calls_per_session: float
    connection_type_breakdown: dict[str, int]  # {"webrtc": N, "outbound_phone": N, ...}
    per_target: list[TargetStats]


class CallSessionRow(BaseModel):
    id: uuid.UUID
    created_at: str  # ISO datetime
    connection_type: str
    status: str
    call_count: int
    duration: int | None

    model_config = {"from_attributes": True}


class CallSessionPage(BaseModel):
    total: int
    items: list[CallSessionRow]


class QualityResponse(BaseModel):
    total_calls: int
    calls_with_quality: int
    avg_quality_score: float | None  # 1–5 MOS-like score; None if no data
    connection_rate: float  # completed / total sessions
    failure_breakdown: dict[str, int]  # {"failed": N, "busy": N, "no_answer": N, ...}


class FailureBreakdown(BaseModel):
    status: str
    count: int


class InsightsDetail(BaseModel):
    """Subset of Twilio Voice Insights summary stored in quality_details."""
    processing_state: str | None = None
    carrier_edge: Any | None = None
    client_edge: Any | None = None
    sdk_edge: Any | None = None
