"""Smoke test: pipeline_factory.build_pipeline assembles without exploding."""
import pytest


@pytest.mark.asyncio
async def test_build_pipeline_returns_pipecat_pipeline(mocker):
    # Mock all external service constructors so we don't need real API keys
    mocker.patch("app.services.voice_agent.pipeline_factory.CartesiaTTSService")
    mocker.patch("app.services.voice_agent.pipeline_factory.DeepgramSTTService")
    mocker.patch("app.services.voice_agent.pipeline_factory.AnthropicLLMService")
    mocker.patch("app.services.voice_agent.pipeline_factory.SileroVADAnalyzer")
    mocker.patch("app.services.voice_agent.pipeline_factory.FastAPIWebsocketTransport")
    mocker.patch("app.services.voice_agent.pipeline_factory.FastAPIWebsocketParams")
    mocker.patch("app.services.voice_agent.pipeline_factory.TwilioFrameSerializer")

    from app.services.voice_agent import pipeline_factory

    fake_session = mocker.MagicMock()
    fake_session.system_prompt = "system"
    fake_session.tools = []
    fake_session.stream_sid = "MZxxxx"

    pipeline = pipeline_factory.build_pipeline(
        session=fake_session,
        websocket=mocker.MagicMock(),
    )
    assert pipeline is not None
