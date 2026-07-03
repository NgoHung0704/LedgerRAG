"""Phase 1 DoD integration test — needs the full docker-compose stack plus a
model server for embedder+chat.

Run:  RUN_INTEGRATION=1 pytest tests/integration -q -m integration
"""

import json
import os
import time

import pytest

pytestmark = pytest.mark.integration

if not os.environ.get("RUN_INTEGRATION"):
    pytest.skip("set RUN_INTEGRATION=1 with the stack running",
                allow_module_level=True)

import fitz  # noqa: E402
import httpx  # noqa: E402

API = os.environ.get("LEDGERRAG_API_URL", "http://localhost:8000")

FRENCH_POLICY = (
    "Règlement intérieur — Congés payés.\n\n"
    "Article 12 : Les cadres bénéficient de vingt-cinq (25) jours ouvrés de "
    "congés payés par an. Les demandes doivent être déposées au moins deux "
    "semaines à l'avance auprès du service des ressources humaines.\n\n"
    "Article 13 : Le télétravail est autorisé deux jours par semaine après "
    "accord du manager."
)


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 545, 780), text, fontsize=12)
    return doc.tobytes()


def test_upload_ingest_and_ask():
    with httpx.Client(base_url=API, timeout=30) as client:
        kb = client.post("/api/kbs", json={
            "name": "HR intégration",
            "description": "Règlement intérieur de test"}).raise_for_status().json()

        pdf = make_pdf(FRENCH_POLICY)
        doc = client.post(
            f"/api/kbs/{kb['id']}/documents",
            files={"file": ("reglement.pdf", pdf, "application/pdf")},
        ).raise_for_status().json()
        assert doc["status"] == "queued"

        # queued -> parsing -> indexing -> done
        deadline = time.monotonic() + 180
        status = doc["status"]
        while time.monotonic() < deadline and status not in ("done", "failed"):
            time.sleep(2)
            status = client.get(
                f"/api/documents/{doc['id']}").raise_for_status().json()["status"]
        assert status == "done", f"ingestion ended in {status!r}"

        # streamed answer with a citation pointing at the right page
        answer = ""
        citations = []
        with client.stream(
            "POST", f"/api/kbs/{kb['id']}/chat",
            json={"question": "Combien de jours de congés payés pour les cadres ?"},
            timeout=120,
        ) as response:
            response.raise_for_status()
            assert response.headers["content-type"].startswith("text/event-stream")
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if event["type"] == "token":
                    answer += event["content"]
                elif event["type"] == "citations":
                    citations = event["citations"]
                elif event["type"] == "error":
                    pytest.fail(f"pipeline error: {event['message']}")

        assert "25" in answer or "vingt-cinq" in answer.lower()
        assert citations, "expected at least one citation"
        assert citations[0]["filename"] == "reglement.pdf"
        assert citations[0]["page"] == 1
