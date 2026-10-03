import os
import html
import time
import json
from datetime import datetime
import streamlit as st
import requests

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
USER_AVATAR = os.path.join(ASSETS_DIR, "user.svg")
BOT_AVATAR = os.path.join(ASSETS_DIR, "bot.svg")

# Inline SVG icons (Lucide, MIT) for places that accept raw HTML
SVG_ICONS = {
    "message": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "bot": '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "lightbulb": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
}

def svg_icon(name: str, size: int = 18) -> str:
    return (
        f'<svg class="svg-icon" xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{SVG_ICONS[name]}</svg>'
    )

# ---------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="DocuChat AI | Document Q&A Assistant",
    page_icon=os.path.join(ASSETS_DIR, "logo.svg"),
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for modern, clean UI
st.markdown("""
<style>
    /* Global styles */
    .main {
        background-color: #f8fafc;
    }
    
    /* Header badge styling */
    .status-badge {
        display: inline-flex;
        align-items: center;
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-left: 8px;
    }
    .badge-success {
        background-color: #dcfce7;
        color: #166534;
        border: 1px solid #bbf7d0;
    }
    .badge-warning {
        background-color: #fef9c3;
        color: #854d0e;
        border: 1px solid #fef08a;
    }
    .badge-info {
        background-color: #e0f2fe;
        color: #0369a1;
        border: 1px solid #bae6fd;
    }

    /* Document banner in chat */
    .upload-container {
        background: #ffffff;
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
        text-align: center;
        transition: border-color 0.2s;
    }
    .upload-container:hover {
        border-color: #3b82f6;
    }
    
    .active-doc-banner {
        background: #f0fdf4;
        border: 1px solid #86efac;
        border-radius: 10px;
        padding: 12px 18px;
        margin-bottom: 16px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    /* Chat message container refinements */
    .stChatMessage {
        border-radius: 12px;
        margin-bottom: 10px;
    }
    
    /* Sidebar header */
    .sidebar-header {
        font-size: 1.2rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.25rem;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .svg-icon {
        display: inline-block;
        vertical-align: -0.2em;
        flex-shrink: 0;
    }
    .icon-heading {
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .msg-timestamp {
        font-size: 0.72rem;
        color: #94a3b8;
        float: right;
        margin-top: -4px;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# State Initialization
# ---------------------------------------------------------
if "sessions" not in st.session_state:
    st.session_state.sessions = {
        "Session 1": {
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "messages": [
                {
                    "role": "assistant",
                    "content": "Welcome! Upload your document above in the chat to start asking questions.",
                    "time": datetime.now().strftime("%H:%M"),
                    "sources": []
                }
            ],
            "active_doc": None,
            "doc_meta": None
        }
    }

if "current_session_id" not in st.session_state or st.session_state.current_session_id not in st.session_state.sessions:
    st.session_state.current_session_id = next(iter(st.session_state.sessions))

if "backend_url" not in st.session_state:
    st.session_state.backend_url = "http://localhost:8000"

def check_backend_alive(url: str) -> bool:
    try:
        r = requests.get(f"{url.rstrip('/')}/", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

if "use_mock_backend" not in st.session_state:
    # Auto-detect: if backend is up, use real backend
    st.session_state.use_mock_backend = not check_backend_alive(st.session_state.backend_url)

if "show_uploader" not in st.session_state:
    st.session_state.show_uploader = True


# ---------------------------------------------------------
# Backend API Helper Functions
# ---------------------------------------------------------
def call_backend_upload(file, backend_url: str):
    """
    Sends the uploaded file to the backend: POST {backend_url}/api/upload
    Expects JSON: { "status": "success", "document_id": "...", "filename": "...", "total_pages": ... }
    """
    url = f"{backend_url.rstrip('/')}/api/upload"
    file_bytes = file.getvalue()
    mime_type = file.type or "application/octet-stream"
    files = {"file": (file.name, file_bytes, mime_type)}
    response = requests.post(url, files=files, timeout=60)
    response.raise_for_status()
    return response.json()

def call_backend_query(question: str, doc_name: str, history: list, backend_url: str):
    """
    Sends user query to the backend: POST {backend_url}/api/chat
    """
    url = f"{backend_url.rstrip('/')}/api/chat"
    payload = {
        "query": question,
        "document_name": doc_name,
        "history": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in history]
    }
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()

def mock_document_answer(question: str, doc_name: str) -> dict:
    """
    Fallback mock response generator when backend is not running yet.
    """
    time.sleep(0.6)  # simulate brief network latency
    q_lower = question.lower()
    
    if "summary" in q_lower or "summarize" in q_lower:
        answer = (
            f"### Document Summary for **{doc_name}**\n\n"
            f"Based on the analysis of `{doc_name}`:\n"
            f"1. **Core Subject**: Overview of key themes, processes, and findings detailed within the document.\n"
            f"2. **Major Takeaways**: Identified actionable insights, performance benchmarks, and recommendations.\n"
            f"3. **Next Steps**: Outlined operational strategies and key review points.\n\n"
            f"*(Note: Running in Frontend Demo/Mock mode. Connect your backend API to retrieve actual LLM citations.)*"
        )
        sources = [
            {"page": 1, "snippet": f"Introduction and executive summary in {doc_name}."},
            {"page": 3, "snippet": f"Key methodology and findings section."}
        ]
    elif "key" in q_lower or "points" in q_lower:
        answer = (
            f"Here are the highlighted key points extracted from **{doc_name}**:\n\n"
            f"- **Point 1**: High priority requirements and background criteria.\n"
            f"- **Point 2**: Analytical breakdown of performance data.\n"
            f"- **Point 3**: Governance, constraints, and standard operating procedures.\n"
            f"- **Point 4**: Concluding observations and forward recommendations."
        )
        sources = [{"page": 2, "snippet": "Section 2.1: Key findings & parameters."}]
    else:
        answer = (
            f"Regarding your question *\"{question}\"* on **{doc_name}**:\n\n"
            f"The document highlights this subject in the context of standard guidelines and reported data points. "
            f"Relevant sections indicate targeted outcomes, timeline requirements, and responsible stakeholders.\n\n"
            f"*(Connect the backend API at `{st.session_state.backend_url}` to query your live RAG pipeline!)*"
        )
        sources = [{"page": 1, "snippet": f"Context matching query '{question}'."}]

    return {"answer": answer, "sources": sources}


# ---------------------------------------------------------
# Sidebar: Sessions, Backend Settings, and Export
# ---------------------------------------------------------
current_session = st.session_state.sessions[st.session_state.current_session_id]

with st.sidebar:
    st.markdown(f'<div class="sidebar-header">{svg_icon("message", 20)} Chat Manager</div>', unsafe_allow_html=True)
    st.caption("Document Q&A Sessions & Settings")
    st.divider()

    # Chat Sessions Management
    st.markdown(f'<h3 class="icon-heading">{svg_icon("history", 20)} Conversation History</h3>', unsafe_allow_html=True)
    
    session_keys = list(st.session_state.sessions.keys())
    active_idx = session_keys.index(st.session_state.current_session_id) if st.session_state.current_session_id in session_keys else 0

    col1, col2 = st.columns([3, 1])
    with col1:
        selected_session = st.selectbox(
            "Select Session",
            options=session_keys,
            index=active_idx,
            label_visibility="collapsed"
        )
        if selected_session != st.session_state.current_session_id:
            st.session_state.current_session_id = selected_session
            st.rerun()

    with col2:
        if st.button("", icon=":material/add:", help="New Session"):
            new_id = f"Session {len(st.session_state.sessions) + 1}"
            st.session_state.sessions[new_id] = {
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "messages": [
                    {
                        "role": "assistant",
                        "content": "New conversation session! Upload a document in the chat to start.",
                        "time": datetime.now().strftime("%H:%M"),
                        "sources": []
                    }
                ],
                "active_doc": None,
                "doc_meta": None
            }
            st.session_state.current_session_id = new_id
            st.rerun()

    # Session stats
    msg_count = len(current_session["messages"])
    active_doc_name = current_session.get("active_doc")
    st.caption(f"{svg_icon('chart', 14)} Messages: **{msg_count}** | Active Doc: **{html.escape(active_doc_name or 'None')}**", unsafe_allow_html=True)

    # Chat history action buttons
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Clear Chat", icon=":material/mop:", use_container_width=True):
            current_session["messages"] = [
                {
                    "role": "assistant",
                    "content": "Conversation cleared. Feel free to ask a new question.",
                    "time": datetime.now().strftime("%H:%M"),
                    "sources": []
                }
            ]
            st.rerun()
    with c2:
        chat_export = json.dumps(current_session["messages"], indent=2)
        st.download_button(
            label="Export",
            icon=":material/download:",
            data=chat_export,
            file_name=f"{st.session_state.current_session_id}_history.json",
            mime="application/json",
            use_container_width=True
        )

    st.divider()

    # Backend Integration & Settings
    with st.expander("Backend API Settings", icon=":material/settings:", expanded=False):
        st.session_state.use_mock_backend = st.toggle(
            "Mock / Standalone Mode",
            value=st.session_state.use_mock_backend,
            help="Toggle ON to test frontend immediately without a running backend. Toggle OFF to hit your friend's backend API."
        )
        
        st.session_state.backend_url = st.text_input(
            "Backend Base URL",
            value=st.session_state.backend_url,
            help="Endpoint where your friend's FastAPI / Flask backend is running"
        )
        
        st.markdown("""
        **Expected Endpoints:**
        - `POST /api/upload`: multipart/form-data
        - `POST /api/chat`: JSON `{ query, document_name, history }`
        """)


# ---------------------------------------------------------
# Main Chat Area
# ---------------------------------------------------------
header_col1, header_col2 = st.columns([3, 1])

with header_col1:
    st.markdown(f'<h1 class="icon-heading">{svg_icon("bot", 36)} Document Q&amp;A Chatbot</h1>', unsafe_allow_html=True)

with header_col2:
    mode_text = "Mock Demo" if st.session_state.use_mock_backend else "Backend API"
    badge_cls = "badge-info" if st.session_state.use_mock_backend else "badge-success"
    st.markdown(f"<div style='text-align: right; padding-top: 15px;'><span class='status-badge {badge_cls}'>Mode: {mode_text}</span></div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# Document Upload Section (IN THE CHAT PART)
# ---------------------------------------------------------
active_doc = current_session.get("active_doc")

# Document status banner if active
if active_doc:
    b_col1, b_col2 = st.columns([4, 1])
    with b_col1:
        st.markdown(f"""
        <div class="active-doc-banner">
            <div>
                {svg_icon("file")} <b>Active Document:</b> <code>{html.escape(active_doc)}</code>
                <span class='status-badge badge-success'>Attached & Ready</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with b_col2:
        if st.button("Replace / Detach", icon=":material/sync:", use_container_width=True):
            current_session["active_doc"] = None
            current_session["doc_meta"] = None
            st.rerun()

# Document Upload Box right in chat view
with st.expander("Upload Document to Chat", icon=":material/attach_file:", expanded=(active_doc is None)):
    up_col1, up_col2 = st.columns([3, 1])
    with up_col1:
        chat_uploaded_file = st.file_uploader(
            "Choose a document (PDF, Word, TXT, CSV, Markdown)",
            type=["pdf", "docx", "txt", "csv", "md"],
            key="chat_doc_uploader",
            label_visibility="collapsed"
        )
    with up_col2:
        upload_btn = st.button("Upload & Analyze", icon=":material/bolt:", use_container_width=True, type="primary")

    if chat_uploaded_file is not None:
        file_size_kb = chat_uploaded_file.size / 1024
        file_size_str = f"{file_size_kb:.1f} KB" if file_size_kb < 1024 else f"{(file_size_kb/1024):.2f} MB"
        st.caption(f"{svg_icon('folder', 14)} **Selected:** <code>{html.escape(chat_uploaded_file.name)}</code> ({file_size_str})", unsafe_allow_html=True)

        if upload_btn:
            with st.spinner("Processing and indexing document..."):
                doc_name = chat_uploaded_file.name
                if not st.session_state.use_mock_backend:
                    try:
                        resp = call_backend_upload(chat_uploaded_file, st.session_state.backend_url)
                        current_session["active_doc"] = doc_name
                        current_session["doc_meta"] = resp
                        current_session["messages"].append({
                            "role": "assistant",
                            "content": f"**{doc_name}** has been uploaded and indexed via the backend! Ask me anything about it.",
                            "time": datetime.now().strftime("%H:%M"),
                            "sources": []
                        })
                        st.success(f"Attached `{doc_name}` to chat!")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Failed to connect to backend: {err}")
                        st.info("Tip: You can enable 'Mock / Standalone Mode' in the sidebar to test without backend.")
                else:
                    current_session["active_doc"] = doc_name
                    current_session["doc_meta"] = {
                        "filename": doc_name,
                        "size": file_size_str,
                        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    current_session["messages"].append({
                        "role": "assistant",
                        "content": f"**{doc_name}** has been processed and attached to this chat! Ask me anything about it.",
                        "time": datetime.now().strftime("%H:%M"),
                        "sources": []
                    })
                    st.success(f"Attached `{doc_name}` to chat!")
                    st.rerun()

st.write("---")

# Quick suggestion chips when a document is active
quick_query = None
if current_session.get("active_doc"):
    st.caption(f"{svg_icon('lightbulb', 14)} Quick prompts for this document:", unsafe_allow_html=True)
    q_cols = st.columns(4)
    if q_cols[0].button("Summarize Document", icon=":material/summarize:", use_container_width=True):
        quick_query = "Please provide a comprehensive summary of this document."
    if q_cols[1].button("Key Takeaways", icon=":material/key:", use_container_width=True):
        quick_query = "What are the main key takeaways and highlights?"
    if q_cols[2].button("Action Items", icon=":material/checklist:", use_container_width=True):
        quick_query = "What action items or next steps are mentioned?"
    if q_cols[3].button("Extract Conclusions", icon=":material/search:", use_container_width=True):
        quick_query = "What are the final conclusions of this document?"


# Display conversation history
for msg in current_session["messages"]:
    role = msg.get("role", "assistant")
    avatar = USER_AVATAR if role == "user" else BOT_AVATAR
    with st.chat_message(role, avatar=avatar):
        timestamp = msg.get("time", "")
        if timestamp:
            st.markdown(f'<span class="msg-timestamp">{timestamp}</span>', unsafe_allow_html=True)
        st.markdown(msg.get("content", ""))

        # Display source citations if available
        sources = msg.get("sources", [])
        if sources:
            with st.expander("Citations & Sources", icon=":material/menu_book:", expanded=False):
                for idx, src in enumerate(sources):
                    page_info = f"Page {src.get('page')}" if "page" in src else f"Source #{idx+1}"
                    snippet = src.get("snippet") or src.get("text") or "Relevant text excerpt"
                    st.markdown(f"**{page_info}:** {snippet}")


# Handle Chat Input
chat_prompt = st.chat_input("Ask a question about your document...")
user_input = chat_prompt if chat_prompt else quick_query

if user_input:
    # 1. Append user message to history
    user_time = datetime.now().strftime("%H:%M")
    current_session["messages"].append({
        "role": "user",
        "content": user_input,
        "time": user_time,
        "sources": []
    })
    
    # Display user query immediately
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(f'<span class="msg-timestamp">{user_time}</span>', unsafe_allow_html=True)
        st.markdown(user_input)

    # 2. Get answer from backend or mock
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        with st.spinner("Analyzing document and thinking..."):
            active_doc_name = current_session.get("active_doc") or "Uploaded Document"
            answer_text = ""
            sources = []

            if st.session_state.use_mock_backend:
                resp = mock_document_answer(user_input, active_doc_name)
                answer_text = resp["answer"]
                sources = resp["sources"]
            else:
                try:
                    resp = call_backend_query(
                        question=user_input,
                        doc_name=active_doc_name,
                        history=current_session["messages"],
                        backend_url=st.session_state.backend_url
                    )
                    answer_text = resp.get("answer", "No answer text returned from backend.")
                    sources = resp.get("sources", [])
                except Exception as err:
                    answer_text = (
                        f":material/warning: **Error connecting to backend API:**\n\n"
                        f"`{str(err)}`\n\n"
                        f"Please ensure your friend's backend is running at `{st.session_state.backend_url}` "
                        f"or toggle on **'Mock / Standalone Mode'** in the sidebar settings."
                    )
            
            # Render response
            ans_time = datetime.now().strftime("%H:%M")
            st.markdown(f'<span class="msg-timestamp">{ans_time}</span>', unsafe_allow_html=True)
            st.markdown(answer_text)

            if sources:
                with st.expander("Citations & Sources", icon=":material/menu_book:", expanded=False):
                    for idx, src in enumerate(sources):
                        page_info = f"Page {src.get('page')}" if "page" in src else f"Source #{idx+1}"
                        snippet = src.get("snippet") or src.get("text") or "Relevant text excerpt"
                        st.markdown(f"**{page_info}:** {snippet}")

    # 3. Save assistant message to session state
    current_session["messages"].append({
        "role": "assistant",
        "content": answer_text,
        "time": ans_time,
        "sources": sources
    })
    st.rerun()
