import os
import time
import logging
from pathlib import Path
from html import escape as html_escape

from flask import Flask, jsonify, request
from flasgger import Swagger
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename

from langchain_classic.chains import RetrievalQA
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaLLM
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

from ingest import load_single_document  # reuse loader registry

# ----------------------------- logging -----------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ----------------------------- app setup -----------------------------

app = Flask(__name__)

# --- Security configuration ---
API_KEY = os.getenv("API_KEY")  # opt-in bearer-token auth
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "10000"))
debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"

# CORS
cors_origins = os.getenv("CORS_ORIGINS", "*")
CORS(app, origins=[o.strip() for o in cors_origins.split(",")])

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],
    storage_uri="memory://",
)

# Swagger
swagger = Swagger(app, template={
    "info": {
        "title": "ContextForge API",
        "description": "A local-first document intelligence API for grounded chat, "
                       "search, summaries, and file management.",
        "version": "2.0.0",
    },
    "schemes": ["http"],
})

# --- Model / store configuration ---
model = os.getenv("MODEL", "llama3.2")
embeddings_model_name = os.getenv("EMBEDDINGS_MODEL_NAME", "all-MiniLM-L6-v2")
persist_directory = os.getenv("PERSIST_DIRECTORY", "db")
source_directory = os.getenv("SOURCE_DIRECTORY", "source_documents")
target_source_chunks = int(os.getenv("TARGET_SOURCE_CHUNKS", "4"))

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
SUMMARIZE_CHAR_LIMIT = 16000  # cap on text fed to the LLM for a summary

# ----------------------------- lazy init -----------------------------
# Heavy components (embeddings model, Chroma, LLM) are initialized on first
# request instead of at import time, so the module can be imported quickly
# (e.g. for tests) and the cold-start delay is deferred.

_components = {}


def _get_db():
    if "db" not in _components:
        _init_components()
    return _components["db"]


def _get_llm():
    if "llm" not in _components:
        _init_components()
    return _components["llm"]


def _get_qa():
    if "qa" not in _components:
        _init_components()
    return _components["qa"]


def _init_components():
    if _components:
        return
    logger.info("Initializing components (embeddings, vectorstore, LLM)…")
    start = time.time()
    embeddings = HuggingFaceEmbeddings(model_name=embeddings_model_name)
    db = Chroma(persist_directory=persist_directory, embedding_function=embeddings)
    retriever = db.as_retriever(search_kwargs={"k": target_source_chunks})
    llm = OllamaLLM(model=model)
    qa = RetrievalQA.from_chain_type(
        llm=llm, chain_type="stuff", retriever=retriever, return_source_documents=True
    )
    _components.update(db=db, llm=llm, qa=qa, retriever=retriever, embeddings=embeddings)
    logger.info("Components initialized in %.1fs.", time.time() - start)


# ----------------------------- request hooks -----------------------------

@app.before_request
def _auth_check():
    """Enforce bearer-token auth when API_KEY is set."""
    if not API_KEY:
        return
    # Exempt health / swagger so probes and docs work unauthenticated
    exempt_prefixes = ("/health", "/apidocs", "/apispec_1.json", "/flasgger_static")
    if any(request.path.startswith(p) for p in exempt_prefixes):
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401


@app.errorhandler(413)
def _too_large(e):
    return jsonify({"error": f"File exceeds the {MAX_UPLOAD_MB} MB upload limit"}), 413


@app.errorhandler(429)
def _rate_limited(e):
    return jsonify({"error": "Rate limit exceeded. Try again later."}), 429


# ----------------------------- helpers -----------------------------

def _error_response(message: str, exc: Exception, status: int = 500):
    """Return a JSON error. Include exception details only in debug mode."""
    payload = {"error": message}
    if debug_mode:
        payload["details"] = str(exc)
    logger.exception(message)
    return jsonify(payload), status


def _safe_source_path(filename: str) -> Path:
    """Resolve a user-supplied filename inside source_directory, blocking path traversal."""
    safe = secure_filename(filename)
    if not safe:
        raise ValueError("Invalid filename")
    return (Path(source_directory) / safe).resolve()


def _all_metadatas():
    db = _get_db()
    try:
        data = db.get(include=["metadatas"])
        return data.get("metadatas") or [], data.get("ids") or []
    except Exception:
        logger.warning("Failed to read metadatas from vectorstore", exc_info=True)
        return [], []


def _dedupe_docs(docs):
    seen, unique = set(), []
    for doc in docs:
        key = (doc.metadata.get("source", ""), doc.page_content)
        if key in seen:
            continue
        seen.add(key)
        unique.append({"source": key[0], "content": key[1]})
    return unique


def _validate_query(data: dict) -> str | None:
    """Extract and validate the query string. Returns error message or None."""
    query = (data or {}).get("query")
    if not query:
        return "No query provided"
    if len(query) > MAX_QUERY_LENGTH:
        return f"Query too long ({len(query)} chars). Max is {MAX_QUERY_LENGTH}."
    return None


# ----------------------------- meta -----------------------------

@app.route("/health", methods=["GET"])
@limiter.exempt
def health():
    """Liveness probe.
    ---
    tags: [meta]
    responses:
      200:
        description: API is up and the configured model name
        schema:
          type: object
          properties:
            status: { type: string, example: ok }
            model:  { type: string, example: llama3.2 }
    """
    return jsonify({"status": "ok", "model": model})


# ----------------------------- chat modes -----------------------------

@app.route("/ask", methods=["POST"])
@limiter.limit("10 per minute")
def ask_question():
    """RAG-style question: retrieves chunks then asks the LLM for an answer.
    ---
    tags: [chat]
    consumes: [application/json]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [query]
          properties:
            query: { type: string, example: "What is this document about?" }
    responses:
      200:
        description: Answer plus the deduped source chunks used to produce it
        schema:
          type: object
          properties:
            query:      { type: string }
            answer:     { type: string }
            time_taken: { type: number, format: float }
            documents:
              type: array
              items:
                type: object
                properties:
                  source:  { type: string }
                  content: { type: string }
      400: { description: Missing or empty query }
      500: { description: Internal error while processing the query }
    """
    try:
        data = request.get_json(silent=True) or {}
        err = _validate_query(data)
        if err:
            return jsonify({"error": err}), 400

        query = data["query"]
        start = time.time()
        res = _get_qa()(query)
        elapsed = time.time() - start
        return jsonify({
            "query": query,
            "answer": res["result"],
            "time_taken": elapsed,
            "documents": _dedupe_docs(res["source_documents"]),
        })
    except Exception as e:
        return _error_response("Failed to process the request", e)


@app.route("/chat", methods=["POST"])
@limiter.limit("10 per minute")
def chat():
    """Talk to the LLM directly with no retrieval.
    ---
    tags: [chat]
    consumes: [application/json]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          required: [query]
          properties:
            query: { type: string, example: Explain RAG in one sentence. }
    responses:
      200:
        description: Model answer (no source documents)
        schema:
          type: object
          properties:
            query:      { type: string }
            answer:     { type: string }
            time_taken: { type: number, format: float }
      400: { description: Missing or empty query }
      500: { description: Internal error while calling the LLM }
    """
    try:
        data = request.get_json(silent=True) or {}
        err = _validate_query(data)
        if err:
            return jsonify({"error": err}), 400

        query = data["query"]
        start = time.time()
        answer = _get_llm().invoke(query)
        elapsed = time.time() - start
        return jsonify({"query": query, "answer": answer, "time_taken": elapsed})
    except Exception as e:
        return _error_response("Failed to process the request", e)


@app.route("/summarize", methods=["POST"])
@limiter.limit("5 per minute")
def summarize():
    """Summarize one specific ingested file, or the whole corpus if no file is given.
    ---
    tags: [chat]
    consumes: [application/json]
    parameters:
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            file:
              type: string
              description: Filename (basename) of an ingested file. Omit to summarize everything.
              example: test.pdf
    responses:
      200:
        description: Summary plus metadata about what was summarized
        schema:
          type: object
          properties:
            file:        { type: string, description: "'all' or the requested filename" }
            answer:      { type: string }
            chunks_used: { type: integer }
            truncated:   { type: boolean, description: True if the corpus was clipped to fit the LLM context }
            time_taken:  { type: number, format: float }
      404: { description: No matching content in the vectorstore }
      500: { description: Internal error }
    """
    try:
        data = request.get_json(silent=True) or {}
        target = data.get("file")
        start = time.time()

        db = _get_db()

        # Optimized: when targeting a single file, use Chroma's where filter
        # instead of fetching ALL documents then filtering in Python.
        if target:
            result = db.get(
                include=["documents", "metadatas"],
                where={"source": {"$contains": target}},
            )
            contents = result.get("documents") or []
            metas = result.get("metadatas") or []
            # Double-check basename match (the $contains may be too broad)
            contents = [
                c for c, m in zip(contents, metas)
                if os.path.basename(m.get("source", "")) == target
            ]
            if not contents:
                return jsonify({"error": f"No chunks found for file '{target}'"}), 404
        else:
            result = db.get(include=["documents"])
            contents = result.get("documents") or []
            if not contents:
                return jsonify({"error": "No ingested content"}), 404

        full_text = "\n\n".join(contents)
        truncated = len(full_text) > SUMMARIZE_CHAR_LIMIT
        if truncated:
            full_text = full_text[:SUMMARIZE_CHAR_LIMIT] + "\n\n[... truncated ...]"

        prompt = (
            "Summarize the following document content concisely. "
            "Capture the main points and any key facts.\n\n"
            f"---\n{full_text}\n---\n\nSummary:"
        )
        answer = _get_llm().invoke(prompt)
        elapsed = time.time() - start

        return jsonify({
            "file": target or "all",
            "answer": answer,
            "chunks_used": len(contents),
            "truncated": truncated,
            "time_taken": elapsed,
        })
    except Exception as e:
        return _error_response("Failed to summarize", e)


# ----------------------------- file management -----------------------------

@app.route("/files", methods=["GET"])
def list_files():
    """List files in source_documents/ with per-file chunk counts from the vectorstore.
    ---
    tags: [files]
    responses:
      200:
        description: Files currently in the corpus
        schema:
          type: object
          properties:
            files:
              type: array
              items:
                type: object
                properties:
                  name:       { type: string, example: test.pdf }
                  size_bytes: { type: integer, example: 141013 }
                  chunks:     { type: integer, description: Number of chunks in the vectorstore }
    """
    src = Path(source_directory)
    if not src.exists():
        return jsonify({"files": []})

    chunk_counts = {}
    for meta in _all_metadatas()[0]:
        base = os.path.basename(meta.get("source", ""))
        chunk_counts[base] = chunk_counts.get(base, 0) + 1

    files = []
    for entry in sorted(src.iterdir()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        files.append({
            "name": entry.name,
            "size_bytes": entry.stat().st_size,
            "chunks": chunk_counts.get(entry.name, 0),
        })
    return jsonify({"files": files})


@app.route("/ingest", methods=["POST"])
@limiter.limit("5 per minute")
def ingest_file():
    """Upload a file (multipart form, field name 'file') and ingest it into the vectorstore.
    ---
    tags: [files]
    consumes: [multipart/form-data]
    parameters:
      - in: formData
        name: file
        type: file
        required: true
        description: Document to ingest. Supported types match ingest.py's loader registry.
    responses:
      200:
        description: File saved and chunked into the vectorstore
        schema:
          type: object
          properties:
            file:          { type: string }
            chunks_added:  { type: integer }
            time_taken:    { type: number, format: float }
      400: { description: Missing file or unsupported extension }
      413: { description: File exceeds the upload size limit }
      500: { description: Failed to load or embed the file }
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded (multipart field name must be 'file')"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    try:
        dest = _safe_source_path(f.filename)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    dest.parent.mkdir(parents=True, exist_ok=True)
    f.save(dest)

    try:
        start = time.time()
        docs = load_single_document(str(dest))
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
        )
        chunks = splitter.split_documents(docs)
        db = _get_db()
        if chunks:
            db.add_documents(chunks)
        elapsed = time.time() - start
        return jsonify({
            "file": dest.name,
            "chunks_added": len(chunks),
            "time_taken": elapsed,
        })
    except Exception as e:
        # Roll back the saved file so a failed ingest doesn't leave orphans
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return _error_response("Ingest failed", e)


@app.route("/files/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    """Remove a file from source_documents/ and delete its chunks from the vectorstore.
    ---
    tags: [files]
    parameters:
      - in: path
        name: filename
        type: string
        required: true
        description: Basename of the file to delete (e.g. test.pdf)
    responses:
      200:
        description: File and its chunks removed
        schema:
          type: object
          properties:
            deleted:         { type: string }
            chunks_removed:  { type: integer }
            file_removed:    { type: boolean }
      400: { description: Invalid filename }
    """
    try:
        target = _safe_source_path(filename)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    chunks_removed = 0
    metadatas, ids = _all_metadatas()
    ids_to_drop = [
        i for i, m in zip(ids, metadatas)
        if os.path.basename(m.get("source", "")) == target.name
    ]
    if ids_to_drop:
        try:
            db = _get_db()
            db.delete(ids=ids_to_drop)
            chunks_removed = len(ids_to_drop)
        except Exception as e:
            return _error_response("Failed to delete chunks", e)

    file_removed = False
    if target.exists():
        target.unlink()
        file_removed = True

    return jsonify({
        "deleted": target.name,
        "chunks_removed": chunks_removed,
        "file_removed": file_removed,
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    host = os.getenv("BIND_HOST", "127.0.0.1")
    app.run(debug=debug_mode, host=host, port=port)
