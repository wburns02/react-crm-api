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

Tool dispatch (Phase 6.1-fix-2): we register every tool name in
``get_tools_schema().standard_tools`` against the AnthropicLLMService here
so that when the model emits a ``tool_use`` block the pipeline routes it
back to ``session._handle_tool_call``. Without this registration Pipecat
would sit waiting for a FunctionCallResultFrame that never arrives.

API discovery against pipecat 0.0.108 (recorded 2026-04-28):
  - ``AnthropicLLMService.register_function(function_name, handler, ...)``
    accepts ``None`` as ``function_name`` for a catch-all handler. We register
    each tool by name explicitly so ``has_function`` works for telemetry.
  - The handler receives a ``FunctionCallParams`` dataclass exposing
    ``function_name: str``, ``tool_call_id: str``, ``arguments: Mapping``,
    ``llm``, ``context``, ``result_callback``.
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
        Tool dispatch is wired here against ``session._handle_tool_call``.
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
            serializer=TwilioFrameSerializer(
                stream_sid=session.stream_sid,
                call_sid=session.call_sid,
                account_sid=settings.TWILIO_ACCOUNT_SID,
                auth_token=settings.TWILIO_AUTH_TOKEN,
            ),
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

    # Wire tool dispatch BEFORE the pipeline runs — Pipecat invokes the
    # handler synchronously when the model emits a tool_use block.
    _register_tools(llm, session)

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


def _register_tools(llm, session) -> None:
    """Register every tool in ``get_tools_schema()`` with the LLM service.

    Each handler forwards to ``session._handle_tool_call`` (which delegates
    to the legacy helper for actual side effects: Twilio SMS, work order
    creation, transfer flagging) and then invokes ``result_callback`` with
    the tool result so Pipecat can splice a ``FunctionCallResultFrame``
    into the conversation.
    """
    from app.services.voice_agent.tools import get_tools_schema

    schema = get_tools_schema()
    tool_names = [fs.name for fs in schema.standard_tools]

    async def _handler(params):
        # ``params`` is a ``pipecat.services.llm_service.FunctionCallParams``
        # dataclass — fields verified against 0.0.108. ``arguments`` is a
        # ``Mapping`` so we coerce to dict for the legacy helper.
        try:
            args = dict(params.arguments or {})
        except Exception:
            args = {}
        result = await session._handle_tool_call(
            params.function_name,
            params.tool_call_id,
            args,
        )
        await params.result_callback(result)

    for name in tool_names:
        llm.register_function(name, _handler)
