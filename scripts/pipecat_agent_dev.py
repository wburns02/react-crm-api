"""Local dev runner for the Pipecat outbound voice agent.

Setup checklist (one-time):
  1. .env: set
       VOICE_AGENT_ENGINE=pipecat
       CARTESIA_API_KEY=<your-key>
       CARTESIA_VOICE_ID=<picked-voice>
       OUTBOUND_AGENT_AMD_CALLBACK=https://<ngrok-id>.ngrok.io/api/v2/outbound-agent/amd
  2. Run the alembic migration to add is_test_prospect / hallucinations / amd_result columns:
       source venv/bin/activate && alembic upgrade head
  3. Seed test prospects (mark Will's cell as test):
       psql "$DATABASE_URL" -c "UPDATE customers SET is_test_prospect=true WHERE phone='+19792361958';"

Per-session loop:
  1. Start the FastAPI app in this script:
       python scripts/pipecat_agent_dev.py
     Listens on 0.0.0.0:8000, reload=True so code edits hot-reload.
  2. In a second terminal, start ngrok:
       ngrok http 8000
     Note the public https URL (e.g., https://abc123.ngrok.io).
  3. In Twilio console (phone-numbers > active numbers > pick a TEST DID, NOT a prod one):
     - Voice webhook (when a call comes in): set to (NOT used for outbound, but
       set anyway): https://<ngrok-id>.ngrok.io/api/v2/outbound-agent/voice
     - Voice URL (more likely the outbound-agent flow): the voice_webhook is
       hit by Twilio after the call connects, configured by the call create's
       `url` argument. For dev, the campaign_dialer's callback_url constant in
       app/services/campaign_dialer.py needs to point to your ngrok URL.
     - AMD callback: set OUTBOUND_AGENT_AMD_CALLBACK env var to the ngrok URL +
       /api/v2/outbound-agent/amd path.
  4. Trigger a 1-call test campaign:
       curl -X POST localhost:8000/api/v2/outbound-agent/campaign/start \\
            -H "Content-Type: application/json" \\
            -d '{"is_test": true, "max_calls": 1}'
     (If the campaign endpoint doesn't accept is_test yet — Phase 6.3 added the
     filter to get_prospect_queue but the campaign endpoint may need a follow-up
     to plumb it through. Check.)
  5. Will's cell should ring within ~5s. Pick up, talk to Sarah.
  6. After the call, run the eval rig (Phase 7):
       python scripts/voice_eval.py --call-sid <CA...> --out voice_eval_runs/

Iteration cycle: edit code -> uvicorn auto-reloads -> redial -> review eval.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
