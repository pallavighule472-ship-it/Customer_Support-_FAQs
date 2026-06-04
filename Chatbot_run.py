from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from Chatbot_Backend import app_ingestion, app_support
import subprocess
import sys
import os
import uuid

app = FastAPI(
    title="SwiftHelp API",
    description="Customer Support FAQ chatbot powered by LangGraph + ChromaDB",
    version="1.0.0"
)


# ─── Request / Response Models ─────────────────────────────────────────────────

class IngestRequest(BaseModel):
    urls: list[str] = Field(..., description="One or more website URLs to ingest")

class IngestResponse(BaseModel):
    success:        bool
    entity_name:    str
    total_faqs:     int
    urls_processed: int
    errors:         list[str]


class ChatRequest(BaseModel):
    query:      str = Field(..., description="User's question")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])

class ChatResponse(BaseModel):
    answer:    str
    intent:    str
    escalated: bool
    ticket_id: str
    sources:   list[str]


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "SwiftHelp API is running", "docs": "/docs"}


@app.post("/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest):
    if not request.urls:
        raise HTTPException(status_code=400, detail="At least one URL is required")

    total_faqs     = 0
    entity_name    = ""
    errors         = []
    urls_processed = 0

    for url in request.urls:
        result = app_ingestion.invoke({"url": url.strip()})
        if result.get("error"):
            errors.append(f"{url}: {result['error']}")
        else:
            total_faqs     += result.get("embedded_count", 0)
            urls_processed += 1
            if not entity_name:
                entity_name = result.get("entity_name", "")

    return IngestResponse(
        success        = total_faqs > 0,
        entity_name    = entity_name,
        total_faqs     = total_faqs,
        urls_processed = urls_processed,
        errors         = errors
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    result = app_support.invoke({
        "session_id":      request.session_id,
        "user_id":         "api_user",
        "user_query":      request.query,
        "intent":          "",
        "chat_history":    [],
        "retrieved_docs":  [],
        "answer":          "",
        "escalate":        False,
        "escalate_reason": "",
        "ticket_id":       "",
        "sources":         [],
        "final_response":  "",
        "error":           None
    })

    return ChatResponse(
        answer    = result.get("final_response") or result.get("answer", ""),
        intent    = result.get("intent", ""),
        escalated = result.get("escalate", False),
        ticket_id = result.get("ticket_id", ""),
        sources   = result.get("sources", [])
    )


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))

    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "Chatbot_run:app", "--port", "8000"],
        cwd=base
    )
    ui_process = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "Chatbot_Frontend.py"],
        cwd=base
    )

    print("SwiftHelp is running!")
    print("Streamlit UI  → http://localhost:8501")
    print("FastAPI docs  → http://localhost:8000/docs")

    try:
        api_process.wait()
        ui_process.wait()
    except KeyboardInterrupt:
        api_process.terminate()
        ui_process.terminate()
