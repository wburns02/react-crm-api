"""Constructs the Pipecat pipeline from a session + websocket.

Service import paths are verified against installed pipecat-ai 0.0.108. See
``app/services/voice_agent/_pipecat_imports.md`` for the discovery log.

The factory builds the full processor graph including the user/assistant
context aggregators that bracket the LLM. The caller (``voice_agent_ws``)
owns the ``LLMContext`` + ``LLMContextAggregatorPair`` — that lets the same
factory be reused with a non-WebSocket transport in tests / eval rigs.

Pipeline order (Pipecat 0.0.108 standard for STT → LLM → TTS over Twilio):

    transport.input()
        → stt
        → context_aggregator_pair.user()
        → llm
        → tts
        → transport.output()
        → context_aggregator_pair.assistant()

The user aggregator accumulates the user's spoken turn into the context
*before* the LLM runs; the assistant aggregator captures the LLM response
back into the context *after* TTS, so the next turn sees the full history.
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


def build_pipeline(*, session, websocket, context_aggregator_pair) -> Pipeline:
    """Build a Pipecat Pipeline for an outbound MAC Septic agent call.

    Args:
      session: ``OutboundAgentSession`` (see ``voice_agent.session``). Must
        expose ``stream_sid``, ``system_prompt``, and ``tools``. The system
        prompt + tools are owned by the caller via ``context_aggregator_pair``.
      websocket: live FastAPI WebSocket from Twilio Media Streams.
      context_aggregator_pair: ``LLMContextAggregatorPair`` built in
        ``voice_agent_ws`` from a seeded ``LLMContext`` (system prompt +
        tools). Its ``.user()`` and ``.assistant()`` processors bracket the
        LLM in the pipeline so multi-turn history is preserved.
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
            context_aggregator_pair.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator_pair.assistant(),
        ]
    )
    return pipeline
