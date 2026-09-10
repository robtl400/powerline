"""Voice token endpoint — issues Twilio Access Tokens for WebRTC calling.

No authentication required; this is called from the embedded widget running
on org websites on behalf of supporters.
"""
from __future__ import annotations

import asyncio
import random
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from app.api.deps import DB
from app.api.v1.helpers import resolve_rep_or_422, resolve_target_ids
from app.config import settings
from app.dependencies import get_client_ip
from app.models.blocklist import BlocklistEntry
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.redis_client import get_redis
from app.schemas.tokens import VoiceTokenRequest, VoiceTokenResponse
from app.services.call_state import save_call_state
from app.services.rate_limiter import check_rate_limit

log = structlog.get_logger()

router = APIRouter(tags=["tokens"])

_TOKEN_RATE_LIMIT = 5  # max AccessTokens per IP per hour
_TOKEN_CAMPAIGN_LIMIT = 500  # max AccessTokens per campaign per hour


@router.post("/tokens/voice", response_model=VoiceTokenResponse)
async def create_voice_token(
    body: VoiceTokenRequest, request: Request, db: DB
) -> VoiceTokenResponse:
    """Issue a Twilio Access Token for WebRTC browser calling.

    Creates a CallSession and stores Redis call state so the voice-app webhook
    can look up the campaign and targets when the browser connects.

    Flow:
      widget → POST /tokens/voice → {token, session_id}
            → device.connect({ params: { session_id } })
            → Twilio calls voice-app with session_id in form body
            → same webhook chain as phone callback path

    No auth required — the blocklist and both rate limits are applied before
    any session is created or any Twilio credential is used.
    """
    # 1. Blocklist check by client IP — silent 403
    ip = get_client_ip(request)
    bl_result = await db.execute(
        select(BlocklistEntry).where(BlocklistEntry.ip_address == ip).limit(1)
    )
    if bl_result.scalar_one_or_none():
        log.warning("tokens_voice_blocklist_hit", ip=ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This number is not eligible to participate")

    # 2. Validate campaign
    result = await db.execute(select(Campaign).where(Campaign.id == body.campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign or campaign.status != "live":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or not active")

    if not campaign.allow_webrtc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This campaign does not support browser calling"
        )

    # 3. Rate limit by client IP and by campaign
    redis = get_redis()
    await check_rate_limit(redis, "token", ip, _TOKEN_RATE_LIMIT)
    await check_rate_limit(redis, "token-campaign", str(campaign.id), _TOKEN_CAMPAIGN_LIMIT)

    # 4. Campaign-wide call ceiling
    if campaign.call_maximum is not None:
        count_result = await db.execute(
            select(func.count()).select_from(CallSession).where(CallSession.campaign_id == campaign.id)
        )
        if (count_result.scalar_one() or 0) >= campaign.call_maximum:
            log.warning("tokens_voice_campaign_maximum", campaign_id=str(campaign.id))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="This campaign has reached its call limit"
            )

    # 5. Load targets (DB campaign targets or the rep behind the caller's handle)
    rep = await resolve_rep_or_422(body.rep_token, campaign.id)
    target_ids = await resolve_target_ids(campaign, db, rep=rep)

    if not target_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Campaign has no targets configured")

    if campaign.target_ordering == "shuffle" and rep is None:
        random.shuffle(target_ids)

    # 6. Persist CallSession
    session_id = uuid.uuid4()
    session = CallSession(
        id=session_id,
        campaign_id=campaign.id,
        connection_type="webrtc",
        status="initiated",
    )
    db.add(session)
    await db.commit()

    log.info(
        "webrtc_session_created",
        session_id=str(session_id),
        campaign_id=str(campaign.id),
        target_count=len(target_ids),
    )

    # 7. Store call state in Redis (consumed by webhook chain)
    state = {
        "campaign_id": str(campaign.id),
        "target_ids": target_ids,
        "current_target_index": 0,
        "caller_phone_hash": "",
        "connection_type": "webrtc",
        "client_ip": ip,
    }
    await save_call_state(session_id, state)

    # 8. Generate Twilio Access Token with VoiceGrant (skipped in dev when key absent)
    if settings.TWILIO_API_KEY_SID:
        loop = asyncio.get_running_loop()
        try:
            token_str = await loop.run_in_executor(None, _build_access_token, session_id)
        except Exception:
            log.exception("access_token_build_failed", session_id=str(session_id))
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate calling token")
    else:
        log.info("access_token_skipped_dev_mode", session_id=str(session_id))
        token_str = "dev-token"

    return VoiceTokenResponse(token=token_str, session_id=str(session_id))


def _build_access_token(session_id: uuid.UUID) -> str:
    """Build and sign a Twilio Access Token with a VoiceGrant.

    Sync — callers must use run_in_executor. The Twilio JWT SDK is sync-only.
    """
    from twilio.jwt.access_token import AccessToken  # type: ignore[import]
    from twilio.jwt.access_token.grants import VoiceGrant  # type: ignore[import]

    token = AccessToken(
        account_sid=settings.TWILIO_ACCOUNT_SID,
        signing_key_sid=settings.TWILIO_API_KEY_SID,
        secret=settings.TWILIO_API_KEY_SECRET,
        identity=str(session_id),
        ttl=600,  # 10 minutes — widget must connect before this expires
    )
    grant = VoiceGrant(
        outgoing_application_sid=settings.TWILIO_TWIML_APP_SID,
        incoming_allow=False,
    )
    token.add_grant(grant)
    result = token.to_jwt()
    # to_jwt() returns str in twilio SDK ≥ 8.x
    return result if isinstance(result, str) else result.decode()
