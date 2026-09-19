"""
Tests for ollama-rag-api.

Uses Flask's test client with mocked LLM/embeddings/Chroma so no running
Ollama instance is required.
"""

import io
import os
import json
import pytest
from unittest.mock import patch, MagicMock

# Set env vars BEFORE importing api so the module picks them up
os.environ.setdefault("PERSIST_DIRECTORY", "test_db")
os.environ.setdefault("SOURCE_DIRECTORY", "test_source_documents")


# ---------------------------------------------------------------------------
# Mock the heavy components so tests don't need Ollama / HuggingFace / Chroma
# ---------------------------------------------------------------------------

def _mock_init():
    """Provide fake components for the lazy-init path."""
    import api

    mock_db = MagicMock()
    mock_db.get.return_value = {"metadatas": [], "ids": [], "documents": []}
    mock_db.as_retriever.return_value = MagicMock()

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = "This is a mock answer."

    mock_qa = MagicMock()
    mock_qa.return_value = {
        "result": "Mock RAG answer",
        "source_documents": [],
    }

    api._components.update(
        db=mock_db,
        llm=mock_llm,
        qa=mock_qa,
        retriever=MagicMock(),
        embeddings=MagicMock(),
    )
    return mock_db, mock_llm, mock_qa


@pytest.fixture(autouse=True)
def _setup_mocks(tmp_path):
    """Set up mocks and temp directories for every test."""
    import api

    api._components.clear()
    api.source_directory = str(tmp_path / "source_documents")
    os.makedirs(api.source_directory, exist_ok=True)

    _mock_init()
    yield
    api._components.clear()


@pytest.fixture
def client():
    """Flask test client."""
    import api
    api.app.config["TESTING"] = True
    with api.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "ok"
        assert "model" in data

    def test_health_is_rate_limit_exempt(self, client):
        for _ in range(100):
            r = client.get("/health")
            assert r.status_code == 200


# ---------------------------------------------------------------------------
# /ask
# ---------------------------------------------------------------------------

class TestAsk:
    def test_ask_missing_body(self, client):
        r = client.post("/ask", content_type="application/json")
        assert r.status_code == 400

    def test_ask_empty_query(self, client):
        r = client.post("/ask", json={"query": ""})
        assert r.status_code == 400

    def test_ask_valid_query(self, client):
        import api
        mock_qa = api._components["qa"]
        mock_qa.return_value = {
            "result": "Test answer",
            "source_documents": [],
        }
        r = client.post("/ask", json={"query": "What is this?"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["query"] == "What is this?"
        assert data["answer"] == "Test answer"
        assert "time_taken" in data
        assert "documents" in data

    def test_ask_query_too_long(self, client):
        import api
        api.MAX_QUERY_LENGTH = 100
        r = client.post("/ask", json={"query": "x" * 101})
        assert r.status_code == 400
        assert "too long" in r.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# /chat
# ---------------------------------------------------------------------------

class TestChat:
    def test_chat_missing_body(self, client):
        r = client.post("/chat", content_type="application/json")
        assert r.status_code == 400

    def test_chat_empty_query(self, client):
        r = client.post("/chat", json={"query": ""})
        assert r.status_code == 400

    def test_chat_valid_query(self, client):
        r = client.post("/chat", json={"query": "Hello"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["query"] == "Hello"
        assert "answer" in data
        assert "time_taken" in data


# ---------------------------------------------------------------------------
# /files
# ---------------------------------------------------------------------------

class TestFiles:
    def test_list_files_empty(self, client):
        r = client.get("/files")
        assert r.status_code == 200
        data = r.get_json()
        assert data["files"] == []

    def test_list_files_with_file(self, client, tmp_path):
        import api
        # Create a file in the source directory
        src = tmp_path / "source_documents"
        (src / "demo.txt").write_text("hello world")
        api.source_directory = str(src)

        r = client.get("/files")
        assert r.status_code == 200
        names = [f["name"] for f in r.get_json()["files"]]
        assert "demo.txt" in names


# ---------------------------------------------------------------------------
# /ingest
# ---------------------------------------------------------------------------

class TestIngest:
    def test_ingest_no_file(self, client):
        r = client.post("/ingest")
        assert r.status_code == 400

    def test_ingest_empty_filename(self, client):
        data = {"file": (io.BytesIO(b""), "")}
        r = client.post("/ingest", data=data, content_type="multipart/form-data")
        assert r.status_code == 400

    def test_ingest_oversize_file(self, client):
        import api
        api.app.config["MAX_CONTENT_LENGTH"] = 1024  # 1 KB for test
        big_data = b"x" * 2048
        data = {"file": (io.BytesIO(big_data), "big.txt")}
        r = client.post("/ingest", data=data, content_type="multipart/form-data")
        assert r.status_code == 413


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAuth:
    def test_no_auth_required_by_default(self, client):
        """When API_KEY is not set, all endpoints are open."""
        r = client.post("/ask", json={"query": "test"})
        assert r.status_code == 200

    def test_auth_required_when_key_set(self, client):
        import api
        api.API_KEY = "test-secret-key"
        try:
            # No header → 401
            r = client.post("/ask", json={"query": "test"})
            assert r.status_code == 401

            # Wrong header → 401
            r = client.post(
                "/ask",
                json={"query": "test"},
                headers={"Authorization": "Bearer wrong-key"},
            )
            assert r.status_code == 401

            # Correct header → 200
            r = client.post(
                "/ask",
                json={"query": "test"},
                headers={"Authorization": "Bearer test-secret-key"},
            )
            assert r.status_code == 200

            # Health is always exempt
            r = client.get("/health")
            assert r.status_code == 200
        finally:
            api.API_KEY = None

    def test_delete_requires_auth_when_key_set(self, client):
        import api
        api.API_KEY = "mykey"
        try:
            r = client.delete("/files/test.pdf")
            assert r.status_code == 401
        finally:
            api.API_KEY = None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_exception_details_hidden_in_production(self, client):
        """In non-debug mode, error details should NOT leak to the client."""
        import api
        api.debug_mode = False
        # Make the QA chain raise
        api._components["qa"].side_effect = RuntimeError("secret internal path /etc/foo")
        r = client.post("/ask", json={"query": "trigger error"})
        assert r.status_code == 500
        data = r.get_json()
        assert "secret internal path" not in json.dumps(data)
        assert "details" not in data
        # Clean up
        api._components["qa"].side_effect = None

    def test_exception_details_shown_in_debug(self, client):
        """In debug mode, error details ARE returned."""
        import api
        api.debug_mode = True
        api._components["qa"].side_effect = RuntimeError("debug info here")
        r = client.post("/ask", json={"query": "trigger error"})
        assert r.status_code == 500
        data = r.get_json()
        assert "details" in data
        assert "debug info here" in data["details"]
        # Clean up
        api._components["qa"].side_effect = None
        api.debug_mode = False

