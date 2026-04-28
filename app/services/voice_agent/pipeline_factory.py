"""Constructs the Pipecat pipeline from a session + websocket.

Service import paths are verified against installed pipecat-ai 0.0.108. See
``app/services/voice_agent/_pipecat_imports.md`` for the discovery log.

The factory only assembles the core processor list (transport in -> STT -> LLM
-> TTS -> transport out). Anthropic context wiring (system prompt, tools,
prompt-caching) is layered on by the session module in Phase 4.2 and the WS
handler in Phase 6.1; this keeps Phase 4.1 narrowly focused on a smoke-testable
construction path.
"""
from app.config import settings

# Verified imports against pipecat 0.0.108 (see _pipecat_imports.md).
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)


def build_pipeline(*, session, websocket) -> Pipeline:
    """Build a Pipecat Pipeline for an outbound MAC Septic agent call.

    ``session`` is an ``OutboundAgentSession`` (see ``voice_agent.session``).
    It must expose:
        - ``stream_sid: str`` — Twilio Media Stream SID (for the serializer)
        - ``system_prompt: str`` — rendered system prompt (consumed downstream
          by the session/WS handler when wiring the LLM context)
        - ``tools: list[dict]`` — Anthropic tool schemas (likewise wired
          downstream)

    ``websocket`` is the live FastAPI WebSocket connection from Twilio's Media
    Streams.

    The returned ``Pipeline`` has no LLM context yet — that is attached by the
    session/WS handler before the pipeline is started. Phase 4.1's contract is
    only that the processor graph constructs cleanly.
    """
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
            serializer=TwilioFrameSerializer(stream_sid=session.stream_sid),
        ),
    )

    # Deepgram STT. ``LiveOptions`` (endpointing, utterance_end_ms, etc.) live
    # in ``pipecat.services.deepgram.stt`` on 0.0.108 and are passed via the
    # ``live_options`` constructor kwarg. We leave them at defaults here and
    # plan to tune in Phase 7 (voice eval rig).
    stt = DeepgramSTTService(
        api_key=settings.DEEPGRAM_API_KEY,
        model="nova-3",
    )

    llm = AnthropicLLMService(
        api_key=settings.ANTHROPIC_API_KEY,
        model="claude-sonnet-4-6",
    )

    tts = CartesiaTTSService(
        api_key=settings.CARTESIA_API_KEY,
        voice_id=settings.CARTESIA_VOICE_ID or "",
        model="sonic-2",
        sample_rate=24000,
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            llm,
            tts,
            transport.output(),
        ]
    )
    return pipeline
