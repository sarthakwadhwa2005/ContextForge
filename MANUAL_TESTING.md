# ContextForge Manual Testing

This guide is for the Windows PowerShell workflow. It separates one-time setup from repeatable manual checks so the project can be verified without guessing which command is needed.

## 1. One-Time Setup

Run these steps once from the project root:

```powershell
# Confirm that you are in the repository
Get-Location

# Create the virtual environment if it does not exist
if (-not (Test-Path .\venv\Scripts\python.exe)) {
  py -3 -m venv venv
}

# Install or refresh every Python dependency listed by the project
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# Verify that the required packages can be imported
.\venv\Scripts\python.exe -c "import flask, flasgger, flask_cors, flask_limiter, langchain, chromadb, streamlit, requests, pytest, pymupdf; print('Python dependencies: OK')"

# Confirm Ollama is available, then download the configured model once
ollama --version
ollama pull llama3.2
```

Run `py -0p` to list installed Python versions. `py -3` selects the available Python 3 installation; Python 3.11 or newer is required. If `py` is not found, install Python 3.11 or newer and enable **Add Python to PATH**. If `ollama` is not found, install Ollama, restart PowerShell, and run the setup commands again.

If you have Python 3.11 installed alongside another version, you can select it explicitly with `py -3.11 -m venv venv`.

The current project defaults are:

- API: `http://127.0.0.1:5001`
- Swagger: `http://127.0.0.1:5001/apidocs`
- Streamlit UI: `http://localhost:8501`
- Ollama: `http://127.0.0.1:11434`
- Model: `llama3.2`

## 2. Check Whether Ingestion Is Needed

The repository already includes `source_documents\test.pdf` and a persisted Chroma database under `db\`. Check both before starting:

```powershell
Test-Path .\db\chroma.sqlite3
Get-ChildItem .\source_documents -File | Select-Object Name,Length
```

If the first command returns `True` and the source document is already listed, skip ingestion for the first test. Run ingestion when you add or replace documents, or when the database does not exist:

```powershell
.\venv\Scripts\python.exe ingest.py
```

To rebuild the vector store from scratch, stop the API first and use:

```powershell
Remove-Item -Recurse -Force .\db
.\venv\Scripts\python.exe ingest.py
```

## 3. Start the Application

Use two PowerShell windows, both opened in the project root.

### Terminal 1: API

```powershell
.\venv\Scripts\python.exe api.py
```

Leave this terminal running. The API initializes its embedding model, Chroma connection, and Ollama client lazily on the first model-backed request, so the first request can take longer.

### Terminal 2: Streamlit

```powershell
.\venv\Scripts\python.exe -m streamlit run ui\streamlit_app.py
```

Open the UI at <http://localhost:8501>.

## 4. Smoke Test the API

Run these commands from a third PowerShell window while the API is running:

```powershell
# Health check: should return status=ok
Invoke-RestMethod http://127.0.0.1:5001/health

# Swagger UI: open this URL in a browser
Start-Process http://127.0.0.1:5001/apidocs

# List the current corpus
Invoke-RestMethod http://127.0.0.1:5001/files

# RAG request: should return answer and documents
Invoke-RestMethod http://127.0.0.1:5001/ask `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"query":"What is this document about?"}'

# Direct model request: should return an answer without source documents
Invoke-RestMethod http://127.0.0.1:5001/chat `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{"query":"Explain retrieval augmented generation in one sentence."}'

# Corpus summary
Invoke-RestMethod http://127.0.0.1:5001/summarize `
  -Method Post `
  -ContentType 'application/json' `
  -Body '{}'
```

Expected results:

- `/health` returns `status: ok`.
- `/files` lists `test.pdf` with a chunk count.
- `/ask` returns `answer` and a `documents` array.
- `/chat` returns `answer` without retrieval sources.
- `/summarize` returns `answer`, `chunks_used`, and `time_taken`.

## 5. Test Upload and Delete

Use `curl.exe` for multipart upload because it works in both Windows PowerShell 5.1 and PowerShell 7:

```powershell
# Upload a copy so the sample file is preserved
Copy-Item .\source_documents\test.pdf .\source_documents\manual-test.pdf
curl.exe -X POST http://127.0.0.1:5001/ingest -F "file=@source_documents/manual-test.pdf"

# Confirm that the file is listed and has chunks
Invoke-RestMethod http://127.0.0.1:5001/files

# Delete the uploaded file after testing
curl.exe -X DELETE http://127.0.0.1:5001/files/manual-test.pdf

# Confirm that it is gone
Invoke-RestMethod http://127.0.0.1:5001/files
```

Upload a copy with a different filename if you want to preserve the sample file:

```powershell
Copy-Item .\source_documents\test.pdf .\source_documents\manual-test.pdf
curl.exe -X POST http://127.0.0.1:5001/ingest -F "file=@source_documents/manual-test.pdf"
curl.exe -X DELETE http://127.0.0.1:5001/files/manual-test.pdf
Remove-Item .\source_documents\manual-test.pdf
```

## 6. Test the UI

At <http://localhost:8501>:

1. Confirm the sidebar reports that the API is available.
2. In **RAG** mode, ask a question and confirm that an answer and source section appear.
3. In **Search** mode, confirm that retrieved chunks appear without a generated answer.
4. In **Basic** mode, confirm that the local model answers without document retrieval.
5. In **Summarize** mode, summarize `test.pdf`.
6. Upload a document, click **Ingest uploaded**, and confirm its chunk count appears.
7. Delete the uploaded document and confirm it disappears from the list.

## 7. Automated Check

Manual testing uses a real Ollama model. The automated tests mock heavyweight services and do not require Ollama:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

A successful run should report all tests passing.

## 8. Optional Docker Check

Docker is not required for the local workflow. If Docker Desktop is installed and running:

```powershell
docker build -t contextforge .
docker run --rm -p 5001:5001 -p 8501:8501 -p 11434:11434 `
  -v "${PWD}\source_documents:/app/source_documents" `
  -v "${PWD}\db:/app/db" `
  contextforge
```

Then repeat the smoke tests from section 4. The container installs Python dependencies, starts Ollama, pulls `llama3.2` if needed, conditionally ingests the source directory, and starts the API and UI.

If `docker` is not found, install Docker Desktop and restart PowerShell before running this section. The local Python workflow remains the recommended first test.

## Troubleshooting

- **`ModuleNotFoundError`**: run `.\venv\Scripts\python.exe -m pip install -r requirements.txt`.
- **`ollama` is not recognized**: install Ollama, restart PowerShell, then run `ollama pull llama3.2`.
- **Connection refused on port 5001**: start the API in Terminal 1.
- **Streamlit reports the API is unreachable**: start the API first, then reload the UI.
- **No chunks are returned**: run `.\venv\Scripts\python.exe ingest.py`, or rebuild `db` using section 2.
- **Port already in use**: stop the existing process or set `PORT` to another port before starting the API.
- **First request is slow**: wait for the embedding model and Ollama model to initialize; later requests should be faster.
