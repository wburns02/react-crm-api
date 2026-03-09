"""
WebSocket connection manager for real-time call transcription.
Routes transcript data from Google STT to connected frontend clients.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TranscriptWSManager:
    """
    Manages WebSocket connections keyed by call_sid.
    Multiple frontend tabs can subscribe to the same call's transcript.
    """

    def __init__(self):
        # call_sid -> set of connected WebSockets
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, call_sid: str, ws: WebSocket):
        """Register a frontend WebSocket for a specific call."""
        async with self._lock:
            if call_sid not in self._connections:
                self._connections[call_sid] = set()
            self._connections[call_sid].add(ws)
        logger.info(f"Transcript WS connected for call {call_sid} (total: {len(self._connections.get(call_sid, set()))})")

    async def disconnect(self, call_sid: str, ws: WebSocket):
        """Remove a frontend WebSocket."""
        async with self._lock:
            conns = self._connections.get(call_sid)
            if conns:
                conns.discard(ws)
                if not conns:
                    del self._connections[call_sid]
        logger.info(f"Transcript WS disconnected for call {call_sid}")

    async def broadcast_transcript(
        self,
        call_sid: str,
        text: str,
        is_final: bool,
        speaker: str = "customer",
    ):
        """
        Send a transcript entry to all connected frontends for a call.
        Message format matches TranscriptEntry in useCustomerTranscript.ts:
          { speaker, text, isFinal, timestamp }
        """
        message = json.dumps({
            "speaker": speaker,
            "text": text,
            "isFinal": is_final,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        async with self._lock:
            conns = self._connections.get(call_sid)
            if not conns:
                return
            # Copy so we can release lock before I/O
            conns_snapshot = list(conns)

        dead: list[WebSocket] = []
        for ws in conns_snapshot:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                conns = self._connections.get(call_sid)
                if conns:
                    for ws in dead:
                        conns.discard(ws)
                    if not conns:
                        del self._connections[call_sid]

    def has_listeners(self, call_sid: str) -> bool:
        return bool(self._connections.get(call_sid))

    def active_calls(self) -> list[str]:
        return list(self._connections.keys())


# Singleton instance
transcript_manager = TranscriptWSManager()
