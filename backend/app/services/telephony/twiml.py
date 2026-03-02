"""TwiML generation functions for each call flow step.

These functions return XML strings ready to serve as TwiML responses.
They do not define any webhook endpoints — those live in the call flow
router (Session 5).
"""
from __future__ import annotations

import dataclasses
import re

from twilio.twiml.voice_response import Dial, VoiceResponse


@dataclasses.dataclass
class AudioConfig:
    file_url: str | None = None   # served from S3; if set, use <Play>
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


def _add_audio(response: VoiceResponse, audio: AudioConfig, context: dict) -> None:
    """Append a <Play> or <Say> verb to the response.

    <Play> takes priority over <Say> when both file_url and tts_text are set.
    If neither is set, nothing is appended (silent step).
    """
    if audio.file_url:
        response.play(audio.file_url)
    elif audio.tts_text:
        rendered = _render_text(audio.tts_text, context)
        response.say(rendered, voice=audio.voice)


def build_greeting(audio: AudioConfig, context: dict) -> str:
    """TwiML for the campaign intro greeting played to the caller before connecting."""
    r = VoiceResponse()
    _add_audio(r, audio, context)
    return str(r)


def build_hold_music(audio: AudioConfig) -> str:
    """TwiML for hold music played while Powerline dials the target."""
    r = VoiceResponse()
    _add_audio(r, audio, {})
    return str(r)


def build_dial_target(target_phone: str, caller_id: str, timeout: int = 30) -> str:
    """TwiML to <Dial> a target legislator or official.

    caller_id must be a Twilio-verified number — using an unverified number
    causes Twilio error 21214 and the call will not connect.
    """
    r = VoiceResponse()
    dial = Dial(caller_id=caller_id, timeout=timeout)
    dial.number(target_phone)
    r.append(dial)
    return str(r)


def build_voicemail(audio: AudioConfig, context: dict) -> str:
    """TwiML for a voicemail drop when the target does not answer."""
    r = VoiceResponse()
    _add_audio(r, audio, context)
    return str(r)


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
    """
    r = VoiceResponse()
    gather = r.gather(action=action_url, num_digits=1, method="POST", timeout=10)
    if audio.file_url:
        gather.play(audio.file_url)
    elif audio.tts_text:
        gather.say(_render_text(audio.tts_text, context), voice=audio.voice)
    if confirm_audio is not None:
        if confirm_audio.file_url:
            gather.play(confirm_audio.file_url)
        elif confirm_audio.tts_text:
            gather.say(
                _render_text(confirm_audio.tts_text, context), voice=confirm_audio.voice
            )
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
    """
    r = VoiceResponse()
    _add_audio(r, intro_audio, context)
    dial = Dial(caller_id=caller_id, timeout=timeout, action=action_url, method="POST")
    dial.number(target_phone)
    r.append(dial)
    return str(r)


def build_between_targets(audio: AudioConfig, context: dict, redirect_url: str) -> str:
    """TwiML for the transition between targets: play bridging message then redirect.

    Used both as the make-calls response (block intro → first target) and
    as the call-complete response when more targets remain.
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
