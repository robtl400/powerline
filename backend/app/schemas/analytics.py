"""Pydantic schemas for analytics and reporting endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.common import Page


class DailyCount(BaseModel):
    date: str  # ISO date string: "2026-03-01"
    count: int


class DashboardResponse(BaseModel):
    calls_today: int
    calls_this_week: int
    calls_this_month: int
    active_campaigns: int
    # Connection-type split over the same trailing 30 days as calls_this_month
    webrtc_count: int
    phone_count: int
    # Last 7 calendar days (today inclusive), oldest first
    calls_last_7_days: list[DailyCount]


class TargetStats(BaseModel):
    target_id: uuid.UUID
    name: str
    # Calls actually dialed: a skipped target is counted in skipped_calls only
    total_calls: int
    completed_calls: int
    skipped_calls: int = 0
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
    created_at: datetime
    connection_type: str
    status: str
    call_count: int
    duration: int | None

    model_config = {"from_attributes": True}


CallSessionPage = Page[CallSessionRow]


class QualityResponse(BaseModel):
    total_calls: int  # calls dialed; skipped targets are excluded
    calls_with_quality: int
    avg_quality_score: float | None  # 1–5 MOS-like score; None if no data
    connection_rate: float  # completed / total sessions
    # Every call status that is not a connected call:
    # {"failed": N, "busy": N, "no_answer": N, "canceled": N, "skipped": N}
    failure_breakdown: dict[str, int]


class FailureBreakdown(BaseModel):
    status: str
    count: int


class InsightsDetail(BaseModel):
    """Subset of Twilio Voice Insights summary stored in quality_details."""
    processing_state: str | None = None
    carrier_edge: Any | None = None
    client_edge: Any | None = None
    sdk_edge: Any | None = None
