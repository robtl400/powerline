"""TwiML generation functions for each call flow step.

These functions return XML strings ready to serve as TwiML responses.
They do not define any webhook endpoints — those live in the call flow
router (app/api/v1/webhooks.py).
"""
from __future__ import annotations

import dataclasses
import re

from twilio.twiml.voice_response import Dial, Gather, VoiceResponse


@dataclasses.dataclass
class AudioConfig:
    file_url: str | None = None   # served from Cloudinary; if set, use <Play>
    tts_text: str | None = None   # template with {{var}} placeholders; use <Say>
    voice: str = "alice"          # Twilio TTS voice name


def _render_text(template: str, context: dict) -> str:
    """Replace {{var}} placeholders with values from context.

    Unknown placeholders are left as-is rather than raising KeyError.
    Common context keys: name, title, location.
    """
    def replacer(m: re.Match) -> str:
        return str(context.get(m.group(1), m.group(0)))

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


def _add_audio(
    node: VoiceResponse | Gather, audio: AudioConfig, context: dict
) -> None:
    """Append a <Play> or <Say> verb to a response or to a <Gather>.

    <Play> takes priority over <Say> when both file_url and tts_text are set.
    If neither is set, nothing is appended (silent step).
    """
    if audio.file_url:
        node.play(audio.file_url)
    elif audio.tts_text:
        rendered = _render_text(audio.tts_text, context)
        node.say(rendered, voice=audio.voice)


def build_gather_intro(
    audio: AudioConfig,
    context: dict,
    action_url: str,
    confirm_audio: AudioConfig | None = None,
) -> str:
    """TwiML for the call entry point: play intro inside <Gather> and wait for a keypress.

    The <Gather> wraps the audio so Twilio can detect a digit press mid-playback.
    action_url receives the caller's keypress (Digits param) via POST.

    confirm_audio is an optional second audio clip played after the main intro
    (e.g. "Press any key when you're ready to begin."). When omitted, only the
    main intro plays — backward-compatible with callers that don't separate them.

    actionOnEmptyResult keeps a silent caller in the flow: Twilio posts to
    action_url with no Digits instead of falling off the end of the document.

    Only a caller with a keypad can answer this, so it is served to phone
    callers; the WebRTC entry point in webhooks.py plays its intro and moves on
    without waiting for digits the widget cannot send.
    """
    r = VoiceResponse()
    gather = r.gather(
        action=action_url,
        num_digits=1,
        method="POST",
        timeout=10,
        action_on_empty_result=True,
    )
    _add_audio(gather, audio, context)
    if confirm_audio is not None:
        _add_audio(gather, confirm_audio, context)
    return str(r)


def build_target_intro_and_dial(
    intro_audio: AudioConfig,
    context: dict,
    target_phone: str,
    caller_id: str,
    action_url: str,
    timeout: int = 30,
) -> str:
    """TwiML to announce the target then <Dial> them.

    action_url is called when the dialed leg completes (DialCallStatus, etc.)
    so call-complete can log the result and route to the next target or goodbye.

    hangupOnStar lets the caller press * to end the current target's leg and
    move on — Twilio drops the dialed party and posts to action_url.
    """
    r = VoiceResponse()
    _add_audio(r, intro_audio, context)
    dial = Dial(
        caller_id=caller_id,
        timeout=timeout,
        action=action_url,
        method="POST",
        hangup_on_star=True,
    )
    dial.number(target_phone)
    r.append(dial)
    return str(r)


def build_between_targets(audio: AudioConfig, context: dict, redirect_url: str) -> str:
    """TwiML for the transition between targets: play bridging message then redirect.

    Used as the make-calls response (block intro → first target), as the
    call-complete response when more targets remain, and as the WebRTC entry
    response, where the intro leads straight into the first target.
    """
    r = VoiceResponse()
    _add_audio(r, audio, context)
    r.redirect(redirect_url, method="POST")
    return str(r)


def build_goodbye(audio: AudioConfig, context: dict) -> str:
    """TwiML for the end of a session: play goodbye audio then hang up."""
    r = VoiceResponse()
    _add_audio(r, audio, context)
    r.hangup()
    return str(r)


def build_redirect(redirect_url: str) -> str:
    """TwiML that sends the call straight on to another webhook, silently.

    Used when a step has nothing to say to the caller — skipping a target whose
    row is gone, for instance — and only needs the flow to continue.
    """
    r = VoiceResponse()
    r.redirect(redirect_url, method="POST")
    return str(r)


def build_hangup() -> str:
    """TwiML that ends the call without playing anything.

    The answer for every webhook path that cannot continue: an unusable
    session, a blocked caller, an error. Twilio speaks XML, so even failures
    are answered with a valid document.
    """
    r = VoiceResponse()
    r.hangup()
    return str(r)
