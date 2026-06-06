import html as html_lib
import streamlit as st
import uuid
import json
import os
from Chatbot_Backend import app_ingestion, app_support

st.set_page_config(
    page_title="SwiftHelp",
    page_icon="💬",
    layout="centered"
)

st.markdown("""
<style>
    .stApp { background-color: #F8FAFC; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    .app-header {
        background: linear-gradient(135deg, #1E40AF 0%, #3B82F6 100%);
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
    }

    .stTabs [data-baseweb="tab-list"] {
        background-color: #EFF6FF;
        border-radius: 8px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        padding: 8px 24px;
        font-weight: 500;
        color: #1E40AF;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563EB !important;
        color: white !important;
    }

    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 1.5px solid #CBD5E1;
        padding: 12px;
        font-size: 15px;
        background: white;
    }
    .stTextInput > div > div > input:focus {
        border-color: #2563EB;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
    }

    .stButton > button {
        background: linear-gradient(135deg, #1E40AF 0%, #3B82F6 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: 600;
        font-size: 15px;
        width: 100%;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }

    .success-box {
        background-color: #F0FDF4;
        border: 1px solid #86EFAC;
        border-left: 4px solid #22C55E;
        border-radius: 8px;
        padding: 16px;
        margin: 12px 0;
        color: #166534;
    }
    .warning-box {
        background-color: #FFFBEB;
        border: 1px solid #FCD34D;
        border-left: 4px solid #F59E0B;
        border-radius: 8px;
        padding: 16px;
        margin: 12px 0;
        color: #92400E;
    }
    .error-box {
        background-color: #FEF2F2;
        border: 1px solid #FECACA;
        border-left: 4px solid #EF4444;
        border-radius: 8px;
        padding: 16px;
        margin: 12px 0;
        color: #991B1B;
    }
    .disclaimer {
        background-color: #EFF6FF;
        border: 1px solid #BFDBFE;
        border-radius: 6px;
        padding: 10px 14px;
        font-size: 13px;
        color: #1E40AF;
        margin: 8px 0 16px 0;
    }
    .source-tag {
        display: inline-block;
        background-color: #EFF6FF;
        color: #1E40AF;
        font-size: 12px;
        padding: 2px 10px;
        border-radius: 20px;
        margin-top: 6px;
        border: 1px solid #BFDBFE;
    }
    .section-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #1E293B;
        margin-bottom: 0.5rem;
    }
    .section-subtitle {
        font-size: 0.9rem;
        color: #64748B;
        margin-bottom: 1.2rem;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="app-header">
    <h1 style="margin:0; font-size: 2rem;">💬 SwiftHelp</h1>
    <p style="margin: 8px 0 0 0; opacity: 0.85; font-size: 1rem;">
        Powered by AI — Instant answers from your business knowledge base
    </p>
</div>
""", unsafe_allow_html=True)

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("""
    <div style="max-width:400px; margin:80px auto; text-align:center;">
        <h2 style="color:#1E293B;">🔒 SwiftHelp</h2>
        <p style="color:#64748B;">Enter your password to continue</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("Password", type="password", label_visibility="collapsed",
                                  placeholder="Enter password")
        if st.button("Login", use_container_width=True):
            _required_pw = os.getenv("SETUP_PASSWORD")
            if not _required_pw:
                st.error("SETUP_PASSWORD environment variable is not configured.")
            elif password == _required_pw:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
    st.stop()

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "ingestion_result" not in st.session_state:
    st.session_state.ingestion_result = None
if "feedback" not in st.session_state:
    st.session_state.feedback = {}

FEEDBACK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feedback.json")

def _save_feedback(answer: str, rating: str):
    try:
        with open(FEEDBACK_PATH, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []
    data.append({"answer": answer, "rating": rating})
    with open(FEEDBACK_PATH, "w") as f:
        json.dump(data, f, indent=2)

tab1, tab2, tab3, tab4 = st.tabs(["⚙️  Setup", "💬  Chat", "📊  Analytics", "📋  FAQs"])


# ─── Tab 1: Setup ─────────────────────────────────────────────────────────────
with tab1:
    st.markdown('<p class="section-title">Ingest Your Business Website</p>', unsafe_allow_html=True)
    st.markdown('<p class="section-subtitle">Enter one or more URLs (one per line) to generate FAQs and power your support assistant.</p>', unsafe_allow_html=True)

    urls_input = st.text_area(
        "Website URLs",
        placeholder="https://yourbusiness.com\nhttps://yourbusiness.com/menu\nhttps://yourbusiness.com/contact",
        height=120,
        label_visibility="collapsed"
    )

    st.markdown("""
    <div class="disclaimer">
        🔒 By submitting URLs, you confirm you have the right to process content from those websites.
    </div>
    """, unsafe_allow_html=True)

    confirmed = st.checkbox("I confirm these are my own websites and I have the right to process their content.")

    if st.button("⚡ Ingest FAQs"):
        urls = [u.strip() for u in urls_input.strip().split("\n") if u.strip()]

        if not urls:
            st.markdown('<div class="error-box">❌ Please enter at least one valid URL.</div>', unsafe_allow_html=True)
        elif not confirmed:
            st.markdown('<div class="error-box">❌ Please confirm you own these websites before proceeding.</div>', unsafe_allow_html=True)
        else:
            total_faqs = 0
            entity_name = ""
            errors = []

            for i, url in enumerate(urls, 1):
                with st.spinner(f"Processing URL {i}/{len(urls)}: {url}"):
                    result = app_ingestion.invoke({"url": url})

                if result.get("error"):
                    errors.append(f"{url}: {result['error']}")
                else:
                    total_faqs += result.get("embedded_count", 0)
                    if not entity_name:
                        entity_name = result.get("entity_name", "")

            if errors:
                for err in errors:
                    st.markdown(f'<div class="error-box">❌ {err}</div>', unsafe_allow_html=True)

            if total_faqs > 0:
                st.session_state.ingestion_result = {
                    "entity_name":    entity_name,
                    "embedded_count": total_faqs,
                    "urls_processed": len(urls) - len(errors),
                }

    if st.session_state.ingestion_result:
        r = st.session_state.ingestion_result
        _name = html_lib.escape(r.get('entity_name', 'Unknown'))
        st.markdown(f"""
        <div class="success-box">
            ✅ <strong>Knowledge base active</strong><br><br>
            🏢 <b>Business:</b> {_name}<br>
            🔗 <b>Pages processed:</b> {r.get('urls_processed', 1)}<br>
            📚 <b>Total FAQs stored:</b> {r.get('embedded_count', 0)}
        </div>
        """, unsafe_allow_html=True)


# ─── Tab 2: Chat ──────────────────────────────────────────────────────────────
with tab2:
    st.markdown('<p class="section-title">Ask a Question</p>', unsafe_allow_html=True)
    st.markdown('<p class="section-subtitle">Type your question below and get instant answers.</p>', unsafe_allow_html=True)

    chat_container = st.container(height=450)

    with chat_container:
        for i, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("sources"):
                    for source in msg["sources"]:
                        st.markdown(f'<span class="source-tag">📌 {source}</span>', unsafe_allow_html=True)
                if msg.get("ticket_id"):
                    st.markdown(f"""
                    <div class="warning-box">
                        🎫 <strong>Ticket ID: {msg['ticket_id']}</strong><br>
                        Our support team will get back to you shortly.
                    </div>
                    """, unsafe_allow_html=True)

                if msg["role"] == "assistant" and not msg.get("ticket_id"):
                    existing = st.session_state.feedback.get(i)
                    if existing == "positive":
                        st.caption("👍 Helpful")
                    elif existing == "negative":
                        st.caption("👎 Not helpful")
                    else:
                        col1, col2, _ = st.columns([1, 1, 10])
                        if col1.button("👍", key=f"up_{i}"):
                            st.session_state.feedback[i] = "positive"
                            _save_feedback(msg["content"], "positive")
                            st.rerun()
                        if col2.button("👎", key=f"down_{i}"):
                            st.session_state.feedback[i] = "negative"
                            _save_feedback(msg["content"], "negative")
                            st.rerun()

    if query := st.chat_input("Type your question here..."):
        st.session_state.messages.append({"role": "user", "content": query})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(query)

        with chat_container:
            with st.chat_message("assistant"):
                input_data = {
                    "session_id":      st.session_state.session_id,
                    "user_id":         "streamlit_user",
                    "user_query":      query,
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
                }

                stream_box    = st.empty()
                streamed_text = ""
                final_state   = {}

                for kind, data in app_support.stream(input_data, stream_mode=["messages", "updates"]):
                    if kind == "messages":
                        message, metadata = data
                        if (
                            metadata.get("langgraph_node") == "generate_answer"
                            and hasattr(message, "content")
                            and message.content
                        ):
                            streamed_text += message.content
                            stream_box.markdown(streamed_text + "▌")
                    elif kind == "updates":
                        for node_output in data.values():
                            if isinstance(node_output, dict):
                                final_state.update(node_output)

                response  = final_state.get("final_response") or final_state.get("answer", "I'm sorry, I couldn't process your request.")
                sources   = final_state.get("sources", [])
                ticket_id = final_state.get("ticket_id", "")

                stream_box.markdown(response)

                if sources:
                    for source in sources:
                        st.markdown(f'<span class="source-tag">📌 {source}</span>', unsafe_allow_html=True)

                if ticket_id:
                    st.markdown(f"""
                    <div class="warning-box">
                        🎫 <strong>Ticket ID: {ticket_id}</strong><br>
                        Our support team will get back to you shortly.
                    </div>
                    """, unsafe_allow_html=True)

        st.session_state.messages.append({
            "role": "assistant",
            "content": response,
            "sources": sources,
            "ticket_id": ticket_id
        })


# ─── Tab 3: Analytics ─────────────────────────────────────────────────────────
with tab3:
    st.markdown('<p class="section-title">Analytics Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="section-subtitle">Overview of your knowledge base and usage.</p>', unsafe_allow_html=True)

    # Load metadata
    metadata = {}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata.json"), "r") as f:
            metadata = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Load chat history
    chat_history_all = {}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.json"), "r") as f:
            chat_history_all = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Calculate stats
    total_faqs    = sum(v.get("embedded_count", 0) for v in metadata.values())
    pages_ingested = len(metadata)
    total_sessions = len(chat_history_all)
    total_questions = sum(
        len([m for m in msgs if m["role"] == "user"])
        for msgs in chat_history_all.values()
    )

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total FAQs", total_faqs)
    col2.metric("Pages Ingested", pages_ingested)
    col3.metric("Questions Asked", total_questions)
    col4.metric("Sessions", total_sessions)

    st.markdown("---")

    # Knowledge base details
    if metadata:
        st.markdown('<p class="section-title">Knowledge Base</p>', unsafe_allow_html=True)
        for url, info in metadata.items():
            ingested_at = info.get("ingested_at", "")[:10]
            _ename = html_lib.escape(info.get('entity_name', 'Unknown'))
            _url   = html_lib.escape(url)
            st.markdown(f"""
            <div class="success-box">
                🏢 <b>{_ename}</b><br>
                🔗 {_url}<br>
                📚 <b>{info.get('embedded_count', 0)} FAQs</b> &nbsp;|&nbsp; 🕐 Ingested: {ingested_at}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="error-box">No knowledge base found. Go to Setup tab to ingest a website.</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Export FAQs
    if total_faqs > 0:
        st.markdown('<p class="section-title">Export FAQs</p>', unsafe_allow_html=True)
        try:
            _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
            _col  = __import__("chromadb").PersistentClient(path=_path).get_collection("faqs")
            _data = _col.get()
            rows  = ["question,answer"]
            for doc, meta in zip(_data["documents"], _data["metadatas"]):
                q = meta.get("question", "").replace('"', '""')
                a = meta.get("answer", "").replace('"', '""')
                rows.append(f'"{q}","{a}"')
            csv = "\n".join(rows)
            st.download_button(
                label="⬇️ Download FAQs as CSV",
                data=csv,
                file_name="faqs.csv",
                mime="text/csv"
            )
        except Exception:
            st.info("No FAQs available to export yet.")

    st.markdown("---")

    # FAQ topic breakdown
    if total_faqs > 0:
        st.markdown('<p class="section-title">FAQ Topics Breakdown</p>', unsafe_allow_html=True)

        import chromadb as _chromadb
        topics = {
            "Hours":        ["hours", "open", "close", "time", "weekend", "monday", "friday"],
            "Location":     ["location", "address", "street", "where", "directions", "tube", "station"],
            "Menu":         ["menu", "food", "cuisine", "dish", "pasta", "pizza", "dessert", "drink"],
            "Dietary":      ["vegan", "vegetarian", "gluten", "allergy", "dietary", "allergen"],
            "Reservations": ["reservation", "book", "table", "group", "walk-in", "deposit"],
            "Delivery":     ["delivery", "takeaway", "deliveroo", "uber", "order"],
            "Contact":      ["phone", "email", "contact", "call", "reach"],
            "Facilities":   ["wifi", "parking", "wheelchair", "accessible", "private", "event"],
        }

        try:
            _path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
            _col  = _chromadb.PersistentClient(path=_path).get_collection("faqs")
            docs  = _col.get()["documents"]

            counts = {}
            for topic, keywords in topics.items():
                counts[topic] = sum(
                    1 for doc in docs
                    if any(kw in doc.lower() for kw in keywords)
                )

            chart_data = {k: v for k, v in counts.items() if v > 0}
            if chart_data:
                st.bar_chart(chart_data)
        except Exception:
            st.info("Ingest a website to see the FAQ topic breakdown.")


# ─── Tab 4: FAQ Management ────────────────────────────────────────────────────
with tab4:
    st.markdown('<p class="section-title">FAQ Management</p>', unsafe_allow_html=True)
    st.markdown('<p class="section-subtitle">View, search and delete stored FAQs.</p>', unsafe_allow_html=True)

    try:
        import chromadb as _chromadb
        _path       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
        _client     = _chromadb.PersistentClient(path=_path)
        _collection = _client.get_collection("faqs")
        _data       = _collection.get()

        all_faqs = [
            {
                "id":       _data["ids"][i],
                "question": _data["metadatas"][i].get("question", ""),
                "answer":   _data["metadatas"][i].get("answer", ""),
                "entity":   _data["metadatas"][i].get("entity_name", ""),
            }
            for i in range(len(_data["ids"]))
        ]

        st.markdown(f"**{len(all_faqs)} FAQs stored**")

        search = st.text_input("🔍 Search FAQs", placeholder="Type to filter...", label_visibility="collapsed")

        filtered = [
            f for f in all_faqs
            if not search or search.lower() in f["question"].lower() or search.lower() in f["answer"].lower()
        ]

        st.markdown(f"*Showing {len(filtered)} result(s)*")

        for faq in filtered:
            with st.expander(f"❓ {faq['question']}"):
                st.markdown(f"**Answer:** {faq['answer']}")
                st.caption(f"Source: {faq['entity']}")
                if st.button("🗑️ Delete", key=f"del_{faq['id']}"):
                    _collection.delete(ids=[faq["id"]])
                    st.success("FAQ deleted.")
                    st.rerun()

    except Exception:
        st.markdown('<div class="error-box">No FAQs found. Go to Setup tab to ingest a website first.</div>', unsafe_allow_html=True)
