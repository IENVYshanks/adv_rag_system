# Streamlit Chat UI

Start the FastAPI backend:

```powershell
uvicorn app.main:app --port 8000
```

In a second terminal, start the chat interface:

```powershell
streamlit run streamlit_app.py
```

The UI uses `BACKEND_URL` from `.env` and defaults to
`http://localhost:8000`.

Each assistant response includes an expandable inspection panel with:

- response latency
- source filenames
- relevance scores
- complete retrieved chunk text

Backend configuration and internal agent details are intentionally hidden from users.
