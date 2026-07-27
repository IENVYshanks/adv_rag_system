import os
import time
import uuid
from typing import Any

import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

st.set_page_config(
    page_title="Enterprise Knowledge Assistant",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1180px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid rgba(128, 128, 128, 0.2);
    }
    .app-kicker {
        color: #5b7cfa;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }
    .app-subtitle {
        color: rgba(128, 128, 128, 0.95);
        margin-top: -0.6rem;
        margin-bottom: 1.4rem;
    }
    .source-card {
        border: 1px solid rgba(128, 128, 128, 0.22);
        border-radius: 0.75rem;
        padding: 0.8rem 1rem;
        margin-bottom: 0.6rem;
        background: rgba(128, 128, 128, 0.04);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def new_session() -> None:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []


def normalize_source(source: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        return {
            "content": str(source.get("content", "")),
            "source": str(source.get("source", "Unknown")),
            "score": source.get("score"),
        }
    return {
        "content": str(source),
        "source": "Retrieved context",
        "score": None,
    }


def format_score(score: Any) -> str:
    if isinstance(score, (int, float)):
        return f"{score:.4f}"
    return "N/A"


def render_details(message: dict[str, Any]) -> None:
    sources = [
        normalize_source(source)
        for source in message.get("sources", [])
    ]
    if not sources:
        return

    with st.expander(
        f"Sources · {len(sources)} relevant chunks",
        expanded=False,
    ):
        for index, source in enumerate(sources, start=1):
            title = (
                f"{index}. {source['source']} · "
                f"relevance {format_score(source['score'])}"
            )
            with st.expander(title):
                st.text(source["content"])


def ask_backend(
    base_url: str,
    question: str,
    thread_id: str,
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    response = requests.post(
        f"{base_url}/query",
        json={"q": question, "thread_id": thread_id},
        timeout=120,
    )
    latency = time.perf_counter() - started
    response.raise_for_status()
    return response.json(), latency


if "thread_id" not in st.session_state:
    new_session()

if "backend_url" not in st.session_state:
    st.session_state.backend_url = os.getenv(
        "BACKEND_URL",
        "http://localhost:8000",
    ).rstrip("/")


with st.sidebar:
    st.markdown("### Conversation")
    if st.button("New conversation", use_container_width=True):
        new_session()
        st.rerun()

    st.divider()
    st.markdown("### Sources")
    st.caption(
        "Open the Sources section under an answer to inspect the supporting "
        "document chunks."
    )


st.markdown('<div class="app-kicker">Enterprise RAG</div>', unsafe_allow_html=True)
st.title("Knowledge Assistant")
st.markdown(
    '<div class="app-subtitle">'
    "Ask questions about your documents and review the supporting sources."
    "</div>",
    unsafe_allow_html=True,
)


if not st.session_state.messages:
    st.info(
        "Start with a question about your indexed documents. "
        "Open “Retrieval and agent details” below an answer to inspect its evidence."
    )


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant":
            if isinstance(message.get("latency"), (int, float)):
                st.caption(f"Answered in {message['latency']:.2f}s")
            render_details(message)


if prompt := st.chat_input(
    "Ask a question about your documents...",
):
    user_message = {"role": "user", "content": prompt}
    st.session_state.messages.append(user_message)

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.status("Finding relevant information...", expanded=True) as status_box:
            st.write("Searching your documents")
            try:
                data, latency = ask_backend(
                    st.session_state.backend_url,
                    prompt,
                    st.session_state.thread_id,
                )
                status_box.update(
                    label="Response ready",
                    state="complete",
                    expanded=False,
                )
            except requests.Timeout:
                status_box.update(
                    label="Request timed out",
                    state="error",
                    expanded=True,
                )
                st.error(
                    "The backend took longer than 120 seconds. "
                    "Check the API and provider logs, then try again."
                )
                st.stop()
            except requests.RequestException as exc:
                status_box.update(
                    label="Backend request failed",
                    state="error",
                    expanded=True,
                )
                detail = ""
                if getattr(exc, "response", None) is not None:
                    try:
                        detail = exc.response.json().get("detail", "")
                    except ValueError:
                        detail = exc.response.text[:300]
                st.error(detail or "Could not get a response from the backend.")
                st.stop()

        answer = data.get("answer") or "The backend returned no answer."
        assistant_message = {
            "role": "assistant",
            "content": answer,
            "sources": data.get("sources") or [],
            "latency": latency,
        }
        st.markdown(answer)
        st.caption(f"Answered in {latency:.2f}s")
        render_details(assistant_message)
        st.session_state.messages.append(assistant_message)
