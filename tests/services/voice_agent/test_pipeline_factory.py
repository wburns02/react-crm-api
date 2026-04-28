"""Smoke test: pipeline_factory.build_pipeline assembles without exploding."""
import pytest


@pytest.mark.asyncio
async def test_build_pipeline_returns_pipecat_pipeline(mocker):
    # Mock all external service constructors so we don't need real API keys
    mocker.patch("app.services.voice_agent.pipeline_factory.CartesiaTTSService")
    mocker.patch("app.services.voice_agent.pipeline_factory.DeepgramSTTService")
    mock_llm_cls = mocker.patch(
        "app.services.voice_agent.pipeline_factory.AnthropicLLMService"
    )
    mocker.patch("app.services.voice_agent.pipeline_factory.SileroVADAnalyzer")
    mocker.patch("app.services.voice_agent.pipeline_factory.FastAPIWebsocketTransport")
    mocker.patch("app.services.voice_agent.pipeline_factory.FastAPIWebsocketParams")
    mocker.patch("app.services.voice_agent.pipeline_factory.TwilioFrameSerializer")

    from app.services.voice_agent import pipeline_factory
    from app.services.voice_agent.tools import get_tools_schema

    fake_session = mocker.MagicMock()
    fake_session.system_prompt = "system"
    fake_session.tools = []
    fake_session.stream_sid = "MZxxxx"

    fake_pair = mocker.MagicMock()
    fake_pair.user.return_value = mocker.MagicMock()
    fake_pair.assistant.return_value = mocker.MagicMock()

    pipeline = pipeline_factory.build_pipeline(
        session=fake_session,
        websocket=mocker.MagicMock(),
        context_aggregator_pair=fake_pair,
    )
    assert pipeline is not None
    # Both aggregators must be spliced into the processor list — that's the
    # whole point of the Phase 6.1-fix change.
    fake_pair.user.assert_called_once()
    fake_pair.assistant.assert_called_once()

    # Phase 6.1-fix-2: every tool in the schema must be registered with the LLM
    # service so Pipecat can dispatch tool_use blocks back to the session.
    expected_tool_count = len(get_tools_schema().standard_tools)
    mock_llm_instance = mock_llm_cls.return_value
    assert mock_llm_instance.register_function.call_count == expected_tool_count
    registered_names = {
        call.args[0] for call in mock_llm_instance.register_function.call_args_list
    }
    expected_names = {fs.name for fs in get_tools_schema().standard_tools}
    assert registered_names == expected_names


def test_get_tools_schema_returns_native_pipecat_schema():
    """``get_tools_schema()`` must return a real ``ToolsSchema`` populated with
    one ``FunctionSchema`` per AGENT_TOOLS entry. Pipecat 0.0.108's
    ``LLMContext`` rejects raw dict tools — this is the single source of truth
    that keeps that contract honored."""
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    from app.services.voice_agent.tools import AGENT_TOOLS, get_tools_schema

    schema = get_tools_schema()
    assert isinstance(schema, ToolsSchema)
    assert len(schema.standard_tools) == len(AGENT_TOOLS)
    for fn in schema.standard_tools:
        assert isinstance(fn, FunctionSchema)
        assert fn.name
        assert fn.description
        assert isinstance(fn.properties, dict)
        assert isinstance(fn.required, list)

    # Round-trip check: each declared tool name appears in the schema.
    expected_names = {t["name"] for t in AGENT_TOOLS}
    actual_names = {fn.name for fn in schema.standard_tools}
    assert expected_names == actual_names
