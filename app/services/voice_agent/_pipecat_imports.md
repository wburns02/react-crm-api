# Pipecat Import Paths (verified for installed version)

Verified during Phase 0.1 against the actual installed Pipecat package. Later
phases should use these paths exactly. If the version is bumped, re-verify.

## Installed version

- `pipecat-ai==0.0.108`
- Python 3.12.12 (matches Dockerfile `python:3.12-slim`)

## Verification table

| Component                   | Plan-expected path                                       | Verified path                                            | Status |
|-----------------------------|----------------------------------------------------------|----------------------------------------------------------|--------|
| Pipeline                    | `pipecat.pipeline.pipeline.Pipeline`                     | `pipecat.pipeline.pipeline.Pipeline`                     | OK     |
| Cartesia TTS                | `pipecat.services.cartesia.tts.CartesiaTTSService`       | `pipecat.services.cartesia.tts.CartesiaTTSService`       | OK     |
| Deepgram STT                | `pipecat.services.deepgram.stt.DeepgramSTTService`       | `pipecat.services.deepgram.stt.DeepgramSTTService`       | OK     |
| Anthropic LLM               | `pipecat.services.anthropic.llm.AnthropicLLMService`     | `pipecat.services.anthropic.llm.AnthropicLLMService`     | OK     |
| Silero VAD                  | `pipecat.audio.vad.silero.SileroVADAnalyzer`             | `pipecat.audio.vad.silero.SileroVADAnalyzer`             | OK     |
| Twilio frame serializer     | `pipecat.serializers.twilio.TwilioFrameSerializer`       | `pipecat.serializers.twilio.TwilioFrameSerializer`       | OK     |
| FastAPI WebSocket transport | `pipecat.transports.network.fastapi_websocket.*`         | `pipecat.transports.websocket.fastapi.*` (see note)      | MOVED  |
| Pipeline runner             | `pipecat.pipeline.runner.PipelineRunner`                 | `pipecat.pipeline.runner.PipelineRunner`                 | OK     |
| Pipeline task / params      | `pipecat.pipeline.task.PipelineTask, PipelineParams`     | `pipecat.pipeline.task.PipelineTask, PipelineParams`     | OK     |

## Note on the WebSocket transport rename

The plan-expected path `pipecat.transports.network.fastapi_websocket` still
imports successfully on 0.0.108 but emits:

> DeprecationWarning: Module `pipecat.transports.network.fastapi_websocket` is
> deprecated, use `pipecat.transports.websocket.fastapi` instead.

The new canonical path also imports cleanly:

```python
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
```

**Use the new path** (`pipecat.transports.websocket.fastapi`) in all new code
written by later phases. The old path will be removed in a future Pipecat
release.

## Reproducing the verification

```bash
source venv/bin/activate
python -c "import pipecat; print(pipecat.__version__)"
python -c "from pipecat.pipeline.pipeline import Pipeline"
python -c "from pipecat.services.cartesia.tts import CartesiaTTSService"
python -c "from pipecat.services.deepgram.stt import DeepgramSTTService"
python -c "from pipecat.services.anthropic.llm import AnthropicLLMService"
python -c "from pipecat.audio.vad.silero import SileroVADAnalyzer"
python -c "from pipecat.serializers.twilio import TwilioFrameSerializer"
python -c "from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams"
python -c "from pipecat.pipeline.runner import PipelineRunner"
python -c "from pipecat.pipeline.task import PipelineTask, PipelineParams"
```

All ten lines should print without error (Pipecat's banner log line is normal).
