"""Basic Streamlit interface for the retail agent."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from retail_agent.agent.chat_runtime import run_agent_turn
from retail_agent.cli import AppContext, load_or_initialize_app


APP_TITLE = "Retail Store Agent"
WELCOME_TEXT = (
    "Ask the agent to ring up sales, process returns, reorder stock, "
    "receive purchase orders, or answer store questions."
)


@st.cache_resource
def get_app_context() -> AppContext:
    """Load and cache the shared application context for the Streamlit app."""
    return load_or_initialize_app()


def main() -> None:
    """Render the Streamlit chat experience."""
    st.set_page_config(page_title=APP_TITLE, page_icon=":shopping_bags:", layout="centered")
    st.title(APP_TITLE)
    st.caption(WELCOME_TEXT)

    try:
        app_context = get_app_context()
    except Exception as exc:  # pragma: no cover - UI boundary
        st.error(f"Failed to initialize app context: {exc}")
        return

    session_id = st.session_state.setdefault(
        "retail_agent_session_id",
        f"streamlit-{uuid4().hex}",
    )
    messages = st.session_state.setdefault("retail_agent_messages", [])

    with st.sidebar:
        st.subheader("Runtime")
        st.write(f"Model: `{app_context.settings.model_name}`")
        st.write(f"Database: `{app_context.settings.db_path}`")
        st.write(f"Seed data: `{app_context.settings.seed_data_dir}`")
        if st.button("Clear Chat"):
            st.session_state["retail_agent_messages"] = []
            app_context.session_state.pop(session_id, None)
            st.rerun()

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("Ask the retail agent to do something")
    if not prompt:
        return

    messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Working..."):
            try:
                response = run_agent_turn(prompt, session_id=session_id, app_context=app_context)
            except Exception as exc:  # pragma: no cover - UI boundary
                response = f"Error: {exc}"
            st.markdown(response)

    messages.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
