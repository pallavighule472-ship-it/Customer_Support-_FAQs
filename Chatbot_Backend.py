import json
import os
import smtplib
import uuid
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TypedDict, Optional

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import StateGraph, START, END
import chromadb
import requests

load_dotenv()

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH       = os.path.join(BASE_DIR, "chroma_db")
METADATA_PATH     = os.path.join(BASE_DIR, "metadata.json")
CHAT_HISTORY_PATH = os.path.join(BASE_DIR, "chat_history.json")


# ─── Graph 1: Knowledge Ingestion Pipeline ────────────────────────────────────

class IngestionState(TypedDict):
    url:            str
    html:           str
    entity_name:    str
    raw_text:       str
    cleaned_text:   str
    chunks:         list[str]
    generated_faqs: list[dict]
    validated_faqs: list[dict]
    documents:      list[Document]
    embeddings:     list[list[float]]
    embedded_count: int
    success:        bool
    error:          Optional[str]


def start_ingestion(state: IngestionState) -> dict:
    url = state.get("url", "").strip()
    if not url:
        return {"error": "No URL provided", "success": False}
    return {
        "url":            url,
        "html":           "",
        "entity_name":    "",
        "raw_text":       "",
        "cleaned_text":   "",
        "chunks":         [],
        "generated_faqs": [],
        "validated_faqs": [],
        "documents":      [],
        "embeddings":     [],
        "embedded_count": 0,
        "success":        False,
        "error":          None,
    }


def scrape_page(state: IngestionState) -> dict:
    url = state["url"]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return {"html": response.text}
    except requests.exceptions.Timeout:
        return {"error": f"Timeout while scraping {url}", "success": False}
    except requests.exceptions.HTTPError as e:
        return {"error": f"HTTP {e.response.status_code} for {url}", "success": False}
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to scrape {url}: {str(e)}", "success": False}


def extract_content(state: IngestionState) -> dict:
    if not state.get("html"):
        return {"error": "No HTML to extract", "success": False}

    soup = BeautifulSoup(state["html"], "html.parser")

    entity_name = ""
    if soup.find("meta", property="og:site_name"):
        entity_name = soup.find("meta", property="og:site_name")["content"]
    elif soup.title:
        entity_name = soup.title.string.strip()
    elif soup.find("h1"):
        entity_name = soup.find("h1").get_text(strip=True)

    for tag in soup(["script", "style", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()

    raw_text = soup.get_text(separator="\n", strip=True)
    if not raw_text:
        return {"error": "No text content found on page", "success": False}

    return {"raw_text": raw_text, "entity_name": entity_name}


def clean_text(state: IngestionState) -> dict:
    if not state.get("raw_text"):
        return {"error": "No raw text to clean", "success": False}

    seen = set()
    cleaned_lines = []
    for line in state["raw_text"].split("\n"):
        line = line.strip()
        if len(line) < 20 or line in seen:
            continue
        seen.add(line)
        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)
    if not cleaned_text:
        return {"error": "No meaningful text after cleaning", "success": False}

    return {"cleaned_text": cleaned_text}


def chunk_text(state: IngestionState) -> dict:
    if not state.get("cleaned_text"):
        return {"error": "No cleaned text to chunk", "success": False}

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", " "]
    )
    chunks = splitter.split_text(state["cleaned_text"])
    if not chunks:
        return {"error": "No chunks created from text", "success": False}

    return {"chunks": chunks}


FAQ_PROMPT = """You are a FAQ generator for a business website.
Given the text below from {entity_name}'s website, generate FAQ pairs.

Rules:
- Only generate FAQs directly supported by the text
- Focus on hours, location, services, pricing, bookings, contact info, dietary options, allergies, accessibility, wifi, parking, delivery
- Include complete specific details in answers — full addresses, exact times, precise prices
- Skip if text is about cookies, privacy policy, or legal terms
- Generate as many FAQs as possible, covering every useful detail in the text
- Return a JSON array only, no markdown, no extra text

Format:
[{{"question": "...", "answer": "..."}}]

Text:
{chunk}"""


def generate_faqs(state: IngestionState) -> dict:
    if not state.get("chunks"):
        return {"error": "No chunks to generate FAQs from", "success": False}

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    all_faqs = []

    for chunk in state["chunks"]:
        try:
            response = llm.invoke([HumanMessage(content=FAQ_PROMPT.format(
                entity_name=state["entity_name"],
                chunk=chunk
            ))])
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            faqs = json.loads(content.strip())
            if isinstance(faqs, list):
                all_faqs.extend(faqs)
        except Exception:
            continue

    if not all_faqs:
        return {"error": "LLM could not generate any FAQs", "success": False}

    return {"generated_faqs": all_faqs}


def validate_faqs(state: IngestionState) -> dict:
    seen_questions = set()
    validated = []

    for faq in state.get("generated_faqs", []):
        question = faq.get("question", "").strip()
        answer   = faq.get("answer", "").strip()
        if not question or not answer:
            continue
        if len(answer) < 30:
            continue
        if question.lower() in seen_questions:
            continue
        seen_questions.add(question.lower())
        validated.append({"question": question, "answer": answer})

    if not validated:
        return {"error": "No valid FAQs after validation", "success": False}

    return {"validated_faqs": validated}


def create_documents(state: IngestionState) -> dict:
    documents = [
        Document(
            page_content=f"Q: {faq['question']}\nA: {faq['answer']}",
            metadata={
                "entity_name": state["entity_name"],
                "question":    faq["question"],
                "answer":      faq["answer"],
            }
        )
        for faq in state.get("validated_faqs", [])
    ]
    return {"documents": documents}


def embed_faqs(state: IngestionState) -> dict:
    if not state.get("documents"):
        return {"error": "No documents to embed", "success": False}

    try:
        model = OpenAIEmbeddings(model="text-embedding-3-small")
        embeddings = model.embed_documents(
            [doc.page_content for doc in state["documents"]]
        )
        return {"embeddings": embeddings}
    except Exception as e:
        return {"error": f"Embedding failed: {str(e)}", "success": False}


def store_in_chroma(state: IngestionState) -> dict:
    if not state.get("embeddings"):
        return {"error": "No embeddings to store", "success": False}

    try:
        client     = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_or_create_collection(name="faqs")
        collection.upsert(
            embeddings=state["embeddings"],
            documents =[doc.page_content for doc in state["documents"]],
            metadatas =[doc.metadata     for doc in state["documents"]],
            ids       =[f"{state['entity_name']}_{i}" for i in range(len(state["documents"]))]
        )
        return {"embedded_count": len(state["documents"]), "success": True}
    except Exception as e:
        return {"error": f"ChromaDB storage failed: {str(e)}", "success": False}


def update_metadata(state: IngestionState) -> dict:
    if not state.get("success"):
        return {}

    try:
        with open(METADATA_PATH, "r") as f:
            metadata = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        metadata = {}

    metadata[state["url"]] = {
        "entity_name":    state["entity_name"],
        "embedded_count": state["embedded_count"],
        "ingested_at":    datetime.now().isoformat(),
    }

    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2)

    return {}


graph_ingestion = StateGraph(IngestionState)

graph_ingestion.add_node("start_ingestion",  start_ingestion)
graph_ingestion.add_node("scrape_page",      scrape_page)
graph_ingestion.add_node("extract_content",  extract_content)
graph_ingestion.add_node("clean_text",       clean_text)
graph_ingestion.add_node("chunk_text",       chunk_text)
graph_ingestion.add_node("generate_faqs",    generate_faqs)
graph_ingestion.add_node("validate_faqs",    validate_faqs)
graph_ingestion.add_node("create_documents", create_documents)
graph_ingestion.add_node("embed_faqs",       embed_faqs)
graph_ingestion.add_node("store_in_chroma",  store_in_chroma)
graph_ingestion.add_node("update_metadata",  update_metadata)

graph_ingestion.add_edge(START,              "start_ingestion")
graph_ingestion.add_edge("start_ingestion",  "scrape_page")
graph_ingestion.add_edge("scrape_page",      "extract_content")
graph_ingestion.add_edge("extract_content",  "clean_text")
graph_ingestion.add_edge("clean_text",       "chunk_text")
graph_ingestion.add_edge("chunk_text",       "generate_faqs")
graph_ingestion.add_edge("generate_faqs",    "validate_faqs")
graph_ingestion.add_edge("validate_faqs",    "create_documents")
graph_ingestion.add_edge("create_documents", "embed_faqs")
graph_ingestion.add_edge("embed_faqs",       "store_in_chroma")
graph_ingestion.add_edge("store_in_chroma",  "update_metadata")
graph_ingestion.add_edge("update_metadata",  END)

app_ingestion = graph_ingestion.compile()


# ─── Graph 2: Customer Support Pipeline ───────────────────────────────────────

class SupportState(TypedDict):
    session_id:      str
    user_id:         str
    user_query:      str
    intent:          str
    chat_history:    list[dict]
    retrieved_docs:  list[Document]
    answer:          str
    escalate:        bool
    escalate_reason: str
    ticket_id:       str
    sources:         list[str]
    final_response:  str
    error:           Optional[str]


INTENT_PROMPT = """Classify the user's message into one of these intents:
- faq: user is asking any question or requesting information (use this when in doubt)
- escalate: user explicitly wants to speak to a human, book/make a reservation right now, or make a complaint
- other: message is a greeting (hi, hello) or clearly unrelated to any business

Reply with only one word — the intent label.

User message: {query}"""


ANSWER_PROMPT = """You are a helpful customer support assistant.
Answer the user's question using ONLY the context provided below.
If the answer is not in the context, say "I don't have that information."
Always respond in the same language as the user's question.

Context:
{context}

Conversation history:
{history}

User: {query}
Assistant:"""


def classify_intent(state: SupportState) -> dict:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    response = llm.invoke([HumanMessage(content=INTENT_PROMPT.format(query=state["user_query"]))])
    intent = response.content.strip().lower()
    if intent not in ["faq", "escalate", "other"]:
        intent = "faq"
    return {"intent": intent}


def route_after_intent(state: SupportState) -> str:
    return "escalation_node" if state["intent"] == "escalate" else "load_memory"


def load_memory(state: SupportState) -> dict:
    try:
        with open(CHAT_HISTORY_PATH, "r") as f:
            all_history = json.load(f)
        chat_history = all_history.get(state["session_id"], [])
    except (FileNotFoundError, json.JSONDecodeError):
        chat_history = []
    return {"chat_history": chat_history}


def retrieve_context(state: SupportState) -> dict:
    if state["intent"] != "faq":
        return {"retrieved_docs": []}

    vectorstore = Chroma(
        collection_name="faqs",
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
        persist_directory=CHROMA_PATH
    )
    return {"retrieved_docs": vectorstore.similarity_search(state["user_query"], k=5)}


def generate_answer(state: SupportState) -> dict:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

    if state["intent"] == "other":
        response = llm.invoke([HumanMessage(content=(
            f"The user said: '{state['user_query']}'\n"
            "Reply with a friendly greeting and offer to help with business questions. "
            "Respond in the same language as the user's message."
        ))])
        return {"answer": response.content.strip()}

    context = "\n\n".join([f"[{i}] {doc.page_content}" for i, doc in enumerate(state["retrieved_docs"], 1)])
    history = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in state["chat_history"][-4:]])

    response = llm.invoke([HumanMessage(content=ANSWER_PROMPT.format(
        context=context, history=history, query=state["user_query"]
    ))])
    return {"answer": response.content.strip()}


def save_memory(state: SupportState) -> dict:
    try:
        with open(CHAT_HISTORY_PATH, "r") as f:
            all_history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        all_history = {}

    sid = state["session_id"]
    all_history.setdefault(sid, [])
    all_history[sid].append({"role": "user",      "content": state["user_query"]})
    all_history[sid].append({"role": "assistant", "content": state["answer"]})

    with open(CHAT_HISTORY_PATH, "w") as f:
        json.dump(all_history, f, indent=2)

    return {}


def finalize_response(state: SupportState) -> dict:
    sources = list({
        doc.metadata.get("entity_name", "")
        for doc in state.get("retrieved_docs", [])
        if doc.metadata.get("entity_name")
    })
    return {"final_response": state["answer"], "sources": sources}


def _send_ticket_email(ticket_id: str, user_query: str, session_id: str):
    sender    = os.getenv("SMTP_SENDER_EMAIL")
    password  = os.getenv("SMTP_APP_PASSWORD")
    recipient = os.getenv("SUPPORT_EMAIL")

    if not all([sender, password, recipient]):
        return

    msg            = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = f"New Support Ticket — {ticket_id}"
    msg.attach(MIMEText(
        f"A new support ticket has been raised via SwiftHelp.\n\n"
        f"Ticket ID:   {ticket_id}\n"
        f"User Query:  {user_query}\n"
        f"Session ID:  {session_id}\n"
        f"Time:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Please follow up with the customer at your earliest convenience.",
        "plain"
    ))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
    except Exception:
        pass


def escalation_node(state: SupportState) -> dict:
    ticket_id = str(uuid.uuid4())[:8].upper()
    _send_ticket_email(ticket_id, state["user_query"], state["session_id"])
    return {
        "escalate":        True,
        "ticket_id":       ticket_id,
        "escalate_reason": "User requested human support or action",
        "final_response":  "A support ticket has been created. Our team will get back to you shortly.",
    }


graph_support = StateGraph(SupportState)
graph_support.add_node("classify_intent",  classify_intent)
graph_support.add_node("load_memory",      load_memory)
graph_support.add_node("retrieve_context", retrieve_context)
graph_support.add_node("generate_answer",  generate_answer)
graph_support.add_node("save_memory",      save_memory)
graph_support.add_node("finalize_response",finalize_response)
graph_support.add_node("escalation_node",  escalation_node)

graph_support.add_edge(START, "classify_intent")
graph_support.add_conditional_edges("classify_intent", route_after_intent, {
    "load_memory":     "load_memory",
    "escalation_node": "escalation_node",
})
graph_support.add_edge("load_memory",      "retrieve_context")
graph_support.add_edge("retrieve_context", "generate_answer")
graph_support.add_edge("generate_answer",  "save_memory")
graph_support.add_edge("save_memory",      "finalize_response")
graph_support.add_edge("finalize_response",END)
graph_support.add_edge("escalation_node",  END)

app_support = graph_support.compile()
