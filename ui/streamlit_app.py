import os
from html import escape as html_escape

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:5001")
API_KEY = os.getenv("API_KEY", "")  # pass through to the backend if set

SUPPORTED_EXTS = [
    "pdf", "txt", "md", "docx", "doc", "csv",
    "html", "pptx", "ppt", "epub", "odt", "eml", "enex", "msg",
]

st.set_page_config(page_title="ContextForge", page_icon="◈", layout="wide")

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
    :root {
        --cf-ink: #101716;
        --cf-panel: #17211f;
        --cf-panel-light: #202c29;
        --cf-line: rgba(222, 235, 219, .12);
        --cf-text: #edf2e8;
        --cf-muted: #91a39a;
        --cf-lime: #c7f36b;
        --cf-coral: #ff8066;
    }
    html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; }
    html, body, #root, .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stAppViewContainer"] > .main,
    [data-testid="stMain"],
    [data-testid="stBottomBlockContainer"] {
        background: #0d1413 !important;
        color: var(--cf-text) !important;
    }
    .stApp {
        background: linear-gradient(135deg, #0d1413 0%, #111b19 52%, #18231f 100%) !important;
    }
    header[data-testid="stHeader"] {
        background: rgba(13, 20, 19, .94) !important;
        border-bottom: 1px solid var(--cf-line);
    }
    [data-testid="stBottomBlockContainer"] {
        border-top: 1px solid var(--cf-line) !important;
        box-shadow: 0 -14px 28px rgba(0, 0, 0, .18) !important;
    }
    [data-testid="stBottomBlockContainer"] > div { background: transparent !important; }
    .main .block-container { max-width: 1440px; padding: 3rem 4.5rem 2.5rem; }
    section[data-testid="stSidebar"] {
        background: #0b1211;
        border-right: 1px solid var(--cf-line);
    }
    section[data-testid="stSidebar"] > div { padding: 1.8rem 1.25rem 2rem; }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stCaption { color: var(--cf-muted); }
    section[data-testid="stSidebar"] .stRadio > label,
    section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] label {
        color: var(--cf-text); font-weight: 600; letter-spacing: .01em;
    }
    section[data-testid="stSidebar"] [data-baseweb="radio"] { padding: .2rem 0; }
    section[data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {
        border-color: #63746b; background: transparent;
    }
    section[data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div { border-color: var(--cf-lime); }
    section[data-testid="stSidebar"] hr { border-color: var(--cf-line); margin: 1.35rem 0; }
    section[data-testid="stSidebar"] .stButton button,
    section[data-testid="stSidebar"] .stDownloadButton button {
        border: 1px solid var(--cf-line); background: var(--cf-panel); color: var(--cf-text);
        border-radius: 8px; min-height: 2.55rem; transition: border-color .2s, transform .2s;
    }
    section[data-testid="stSidebar"] .stButton button:hover { border-color: var(--cf-lime); transform: translateY(-1px); }
    section[data-testid="stSidebar"] .stButton button[kind="primary"] { background: var(--cf-lime); color: #152018; border-color: var(--cf-lime); font-weight: 700; }
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] {
        background: var(--cf-panel); border: 1px dashed #54675d; border-radius: 10px; padding: .4rem;
    }
    [data-testid="stFileUploaderDropzone"] { background: transparent; border: 0; }
    [data-testid="stFileUploaderDropzone"] small { color: var(--cf-muted); }
    [data-testid="stFileUploaderDropzone"] button { color: var(--cf-lime); border-color: var(--cf-lime); }
    [data-testid="stStatusWidget"] { border-radius: 10px; }
    .cf-brand { padding: .3rem 0 1.4rem; }
    .cf-brand-mark { color: var(--cf-lime); font: 500 1rem 'DM Mono', monospace; letter-spacing: .18em; }
    .cf-brand h1 { color: var(--cf-text); font-size: 1.5rem; letter-spacing: -.04em; margin: .35rem 0 .2rem; }
    .cf-brand p { color: var(--cf-muted); font-size: .78rem; margin: 0; line-height: 1.45; }
    .cf-section-label { color: var(--cf-muted); font: 500 .68rem 'DM Mono', monospace; letter-spacing: .16em; text-transform: uppercase; margin-bottom: .55rem; }
    .cf-hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 2rem; margin-bottom: 1.9rem; }
    .cf-kicker { color: var(--cf-lime); font: 500 .72rem 'DM Mono', monospace; letter-spacing: .15em; text-transform: uppercase; margin-bottom: .8rem; }
    .cf-hero h1 { color: var(--cf-text); font-size: clamp(2.2rem, 4vw, 4.6rem); line-height: .98; letter-spacing: -.065em; margin: 0; max-width: 760px; }
    .cf-hero h1 span { color: var(--cf-lime); }
    .cf-hero p { color: var(--cf-muted); font-size: 1rem; line-height: 1.5; max-width: 410px; margin: 0 0 .25rem; }
    .cf-model-bar { display: flex; flex-wrap: wrap; gap: .65rem; align-items: center; margin: 0 0 1.5rem; }
    .cf-chip { border: 1px solid var(--cf-line); border-radius: 999px; color: var(--cf-muted); font: 400 .72rem 'DM Mono', monospace; padding: .45rem .72rem; background: rgba(23, 33, 31, .65); }
    .cf-chip strong { color: var(--cf-text); font-weight: 500; }
    .cf-chip.live { color: var(--cf-lime); border-color: rgba(199, 243, 107, .38); }
    .cf-empty { border: 1px dashed #506158; border-radius: 14px; padding: 2.5rem; text-align: center; color: var(--cf-muted); background: rgba(23, 33, 31, .45); }
    .cf-file-row { align-items: center; }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { gap: .35rem; }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stButton"] button {
        min-width: 2.35rem; width: 2.35rem; padding: 0; font-size: 1rem; line-height: 1;
    }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stMarkdownContainer"] p {
        overflow-wrap: anywhere; line-height: 1.2; margin: 0;
    }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] [data-testid="stCaptionContainer"] { white-space: nowrap; }
    .cf-file-meta {
        color: var(--cf-muted); display: inline-block; font: 400 .7rem 'DM Mono', monospace;
        min-width: 4.4rem; white-space: nowrap;
    }
    [data-testid="stChatMessage"] { border: 0; padding: 1rem 1.1rem; gap: .85rem; }
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { font-size: .98rem; line-height: 1.65; }
    [data-testid="stChatMessage"] [data-testid="chatAvatarIcon-user"] { background: var(--cf-coral); color: #1a100e; }
    [data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] { background: var(--cf-lime); color: #152018; }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) { background: rgba(255, 128, 102, .07); border-left: 2px solid var(--cf-coral); border-radius: 0 12px 12px 0; }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) { background: rgba(199, 243, 107, .055); border-left: 2px solid var(--cf-lime); border-radius: 0 12px 12px 0; }
    [data-testid="stChatInput"] { border: 1px solid #52655c !important; background: var(--cf-panel) !important; border-radius: 12px; }
    [data-testid="stChatInput"] textarea { background: transparent !important; color: var(--cf-text) !important; font-family: 'Space Grotesk', sans-serif; }
    [data-testid="stChatInput"]:focus-within { border-color: var(--cf-lime); box-shadow: 0 0 0 1px var(--cf-lime); }
    .stButton button { border-radius: 8px; font-family: 'Space Grotesk', sans-serif; font-weight: 600; }
    .stButton button[kind="primary"] { background: var(--cf-lime); color: #152018; border-color: var(--cf-lime); }
    .stButton button[kind="primary"]:hover { background: #d8ff87; border-color: #d8ff87; }
    [data-testid="stExpander"] { border: 1px solid var(--cf-line); background: rgba(23, 33, 31, .75); border-radius: 10px; }
    [data-testid="stExpander"] summary p { color: var(--cf-lime); font: 500 .76rem 'DM Mono', monospace; }
    code, pre { font-family: 'DM Mono', monospace !important; }
    a { color: var(--cf-lime); }
    .stAlert { border-radius: 10px; }
    @media (max-width: 900px) {
        .main .block-container { padding: 2rem 1.2rem 1.5rem; }
        .cf-hero { display: block; }
        .cf-hero p { margin-top: 1rem; }
    }
</style>
<div class="cf-hero">
    <div>
        <div class="cf-kicker">Private knowledge console / 01</div>
        <h1>Ask your documents<br><span>better questions.</span></h1>
    </div>
    <p>ContextForge keeps your files local while turning them into a fast, inspectable workspace for retrieval, chat, and summaries.</p>
</div>
""",
    unsafe_allow_html=True,
)


# --------------------------- API client ---------------------------

def _headers() -> dict:
    """Build request headers, including auth if API_KEY is configured."""
    h = {}
    if API_KEY:
        h["Authorization"] = f"Bearer {API_KEY}"
    return h


def api_health():
    try:
        return requests.get(f"{API_URL}/health", timeout=3).json()
    except Exception:
        return None


def api_list_files():
    try:
        return requests.get(f"{API_URL}/files", headers=_headers(), timeout=5).json().get("files", [])
    except Exception:
        return []


def api_upload(uploaded_file):
    files = {"file": (uploaded_file.name, uploaded_file.getbuffer(), uploaded_file.type or "application/octet-stream")}
    return requests.post(f"{API_URL}/ingest", files=files, headers=_headers(), timeout=600)


def api_delete(filename: str):
    return requests.delete(f"{API_URL}/files/{filename}", headers=_headers(), timeout=60)


def api_ask(query: str):
    return requests.post(f"{API_URL}/ask", json={"query": query}, headers=_headers(), timeout=300).json()


def api_chat(query: str):
    return requests.post(f"{API_URL}/chat", json={"query": query}, headers=_headers(), timeout=300).json()


def api_summarize(file: str | None = None):
    body = {"file": file} if file else {}
    return requests.post(f"{API_URL}/summarize", json=body, headers=_headers(), timeout=600).json()


# --------------------------- session state ---------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None
if "pending_mode" not in st.session_state:
    st.session_state.pending_mode = None


# --------------------------- sidebar ---------------------------

with st.sidebar:
    st.markdown(
        """
        <div class="cf-brand">
          <div class="cf-brand-mark">◈ CONTEXTFORGE</div>
          <h1>Knowledge, in focus.</h1>
          <p>A local-first workspace for asking better questions of your own files.</p>
        </div>
        <div class="cf-section-label">Workspace mode</div>
        """,
        unsafe_allow_html=True,
    )
    mode_options = ["RAG", "Search", "Basic", "Summarize"]
    mode = st.radio("Mode", mode_options, index=0, label_visibility="collapsed")
    mode_help = {
        "RAG": "Get contextualized answers from your ingested files.",
        "Search": "Return retrieved chunks only — no LLM synthesis.",
        "Basic": "Talk to the model directly, no retrieval.",
        "Summarize": "Summarize a selected file (or the whole corpus).",
    }
    st.caption(mode_help[mode])

    st.divider()

    st.markdown('<div class="cf-section-label">Add to knowledge base</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "Upload",
        accept_multiple_files=True,
        label_visibility="collapsed",
        type=SUPPORTED_EXTS,
    )
    if uploaded:
        if st.button("Ingest uploaded", type="primary", use_container_width=True):
            ok, fail = 0, 0
            with st.spinner(f"Uploading {len(uploaded)} file(s)…"):
                for f in uploaded:
                    try:
                        r = api_upload(f)
                        if r.status_code == 200:
                            ok += 1
                        elif r.status_code == 413:
                            fail += 1
                            st.error(f"{f.name}: File too large")
                        elif r.status_code == 401:
                            fail += 1
                            st.error(f"{f.name}: Unauthorized — check API_KEY")
                        else:
                            fail += 1
                            st.error(f"{f.name}: {r.json().get('error', r.text)}")
                    except Exception as e:
                        fail += 1
                        st.error(f"{f.name}: {e}")
            if ok:
                st.success(f"Ingested {ok} file(s).")
            if fail == 0:
                st.rerun()

    st.divider()

    st.markdown('<div class="cf-section-label">Corpus / indexed files</div>', unsafe_allow_html=True)
    files = api_list_files()
    if not files:
        st.markdown('<div class="cf-empty">No files indexed yet.<br><small>Upload a document above to begin.</small></div>', unsafe_allow_html=True)
        selected_file = None
    else:
        for f in files:
            st.markdown('<div class="cf-file-row">', unsafe_allow_html=True)
            cols = st.columns([4.5, 2.8, 1.4], gap="small")
            cols[0].markdown(f"📄 `{f['name']}`")
            cols[1].markdown(f'<span class="cf-file-meta">{f["chunks"]} chunks</span>', unsafe_allow_html=True)
            if cols[2].button("✕", key=f"del_{f['name']}", help=f"Delete {f['name']}"):
                with st.spinner(f"Deleting {f['name']}…"):
                    api_delete(f["name"])
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        if st.button("🗑️ Delete ALL files", use_container_width=True, type="secondary"):
            with st.spinner("Deleting all files…"):
                for f in files:
                    api_delete(f["name"])
            st.rerun()

    # Selector used by Summarize mode (and could power future per-file ask)
    selected_file = None
    if files and mode == "Summarize":
        st.divider()
        st.markdown('<div class="cf-section-label">Summary target</div>', unsafe_allow_html=True)
        choices = ["(all files)"] + [f["name"] for f in files]
        choice = st.selectbox("Pick a file or summarize everything", choices, label_visibility="collapsed")
        selected_file = None if choice == "(all files)" else choice

    st.divider()

    h = api_health()
    if h:
        st.success(f"● API online — `{h.get('model','?')}`")
    else:
        st.error(f"❌ API unreachable at {API_URL}")
        if st.button("🔄 Recheck", use_container_width=True, key="recheck_health"):
            st.rerun()
    st.markdown(f"- [Swagger UI]({API_URL}/apidocs)")
    st.markdown(f"- [Raw spec]({API_URL}/apispec_1.json)")


# --------------------------- model info bar ---------------------------

# FIX: HTML-escape the model name to prevent XSS via a tampered /health response
model_name = html_escape((h or {}).get("model", "unknown"))
st.markdown(
        f"""<div class="cf-model-bar">
            <span class="cf-chip live">● SYSTEM ONLINE</span>
            <span class="cf-chip">ENGINE <strong>Ollama</strong></span>
            <span class="cf-chip">MODEL <strong>{model_name}</strong></span>
            <span class="cf-chip">MODE <strong>{html_escape(mode)}</strong></span>
        </div>""",
    unsafe_allow_html=True,
)


# --------------------------- chat rendering ---------------------------

def render_sources(documents):
    if not documents:
        return
    with st.expander(f"📚 Sources ({len(documents)})"):
        for i, d in enumerate(documents, 1):
            st.markdown(f"**{i}. {d['source']}**")
            snippet = d["content"][:500] + ("…" if len(d["content"]) > 500 else "")
            st.code(snippet)


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        render_sources(msg.get("documents") or [])


# --------------------------- query dispatcher ---------------------------

def fire_query(prompt: str, run_mode: str, target_file: str | None, append_user_msg: bool):
    if append_user_msg:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                docs = []
                if run_mode == "RAG":
                    data = api_ask(prompt)
                    answer = data.get("answer", "(no answer)")
                    docs = data.get("documents", [])
                elif run_mode == "Search":
                    data = api_ask(prompt)
                    docs = data.get("documents", [])
                    answer = f"_Search mode — {len(docs)} chunks retrieved, no synthesis._"
                elif run_mode == "Basic":
                    data = api_chat(prompt)
                    answer = data.get("answer", "(no answer)")
                elif run_mode == "Summarize":
                    data = api_summarize(target_file)
                    truncated = " _(truncated)_" if data.get("truncated") else ""
                    scope = data.get("file", "all")
                    answer = (
                        f"**Summary of `{scope}`** "
                        f"(used {data.get('chunks_used', '?')} chunks{truncated})\n\n"
                        f"{data.get('answer', '(no answer)')}"
                    )
                else:
                    answer = f"Unknown mode: {run_mode}"

                st.markdown(answer)
                render_sources(docs)
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer, "documents": docs}
                )
            except Exception as e:
                err = f"Request failed: {e}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})


pending_q = st.session_state.pending_query
pending_m = st.session_state.pending_mode
st.session_state.pending_query = None
st.session_state.pending_mode = None

# Summarize mode auto-fires on click (no chat input needed)
if mode == "Summarize":
    if st.button("📝 Generate summary", type="primary"):
        scope = selected_file or "all files"
        fire_query(f"Summarize {scope}", "Summarize", selected_file, append_user_msg=True)

prompt = st.chat_input(
    "Ask a question…" if mode != "Summarize" else "(Summarize mode — use the button above)",
    disabled=(mode == "Summarize"),
)

if pending_q:
    fire_query(pending_q, pending_m or mode, selected_file, append_user_msg=False)
elif prompt:
    fire_query(prompt, mode, selected_file, append_user_msg=True)


# --------------------------- retry / undo / clear ---------------------------

def last_user_query():
    for m in reversed(st.session_state.messages):
        if m["role"] == "user":
            return m["content"]
    return None


col_retry, col_undo, col_clear = st.columns(3)

if col_retry.button(
    "🔄 Retry",
    use_container_width=True,
    disabled=last_user_query() is None,
    help="Re-run the last question with the current model + mode",
):
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        st.session_state.messages.pop()
    st.session_state.pending_query = last_user_query()
    st.session_state.pending_mode = mode
    st.rerun()

if col_undo.button(
    "↩️ Undo",
    use_container_width=True,
    disabled=not st.session_state.messages,
    help="Remove the last question and its answer",
):
    while (
        st.session_state.messages
        and st.session_state.messages[-1]["role"] == "assistant"
    ):
        st.session_state.messages.pop()
    if st.session_state.messages:
        st.session_state.messages.pop()
    st.rerun()

if col_clear.button(
    "🗑️ Clear",
    use_container_width=True,
    disabled=not st.session_state.messages,
    help="Wipe the chat history",
):
    st.session_state.messages = []
    st.rerun()
