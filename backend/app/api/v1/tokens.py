"""Voice token endpoint — issues Twilio Access Tokens for WebRTC calling.

No authentication required; this is called from the embedded widget running
on org websites on behalf of supporters.
"""
from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import DB
from app.api.v1.helpers import get_live_campaign_or_404, start_call_session
from app.config import settings
from app.dependencies import get_client_ip
from app.models.blocklist import BlocklistEntry
from app.redis_client import get_redis
from app.schemas.tokens import VoiceTokenRequest, VoiceTokenResponse
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
    any session is created or any Twilio credential is used, and the campaign's
    call ceiling is claimed in the same transaction that opens the session.
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
    campaign = await get_live_campaign_or_404(body.campaign_id, db)

    if not campaign.allow_webrtc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This campaign does not support browser calling"
        )

    # 3. Rate limit by client IP and by campaign
    redis = get_redis()
    await check_rate_limit(redis, "token", ip, _TOKEN_RATE_LIMIT)
    await check_rate_limit(redis, "token-campaign", str(campaign.id), _TOKEN_CAMPAIGN_LIMIT)

    # 4. Claim a slot under the campaign ceiling, open the session, store its state
    session_id = await start_call_session(
        campaign,
        db,
        connection_type="webrtc",
        rep_token=body.rep_token,
        client_ip=ip,
    )

    # 5. Generate Twilio Access Token with VoiceGrant (skipped in dev when key absent)
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
