import streamlit as st
import os
from dotenv import load_dotenv
from database import init_db
from auth import require_login
from views import manager_dashboard, developer_dashboard

load_dotenv()

st.set_page_config(
    page_title="Automated Task Manager",
    page_icon="🎤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Auto-refresh was removed as per user request to prevent unwanted reloads.

# ── Init DB once ─────────────────────────────────────────────────────
init_db()

# ── Init session state (pattern from repo) ───────────────────────────
DEFAULTS = {
    "user":                      None,
    "help_panel_open":           False,
    "help_question":             "",
    "help_response":             "",
    "help_mode":                 "question",   # 'question' | 'command'
    "last_help_processed":       None,
    "tasks_updated":             False,
    "last_meeting_id":           None,
    "agent_thinking":            False,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Auth gate ────────────────────────────────────────────────────────
user = require_login()

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### 👤 {user['username']}")
    st.caption(f"Role: **{user['role'].capitalize()}**")
    st.divider()

    # ── AI Assistant panel (from repo HelpService pattern) ───────────
    st.markdown("### 🤖 AI Assistant")

    status_icon = "🟢" if st.session_state.help_panel_open else "⚪"
    if st.button(f"Toggle Panel ({status_icon})", use_container_width=True):
        st.session_state.help_panel_open = not st.session_state.help_panel_open
        st.rerun()

    if st.session_state.help_panel_open:
        st.divider()

        # Mode toggle (Question vs Command — from repo)
        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "✅ Q&A" if st.session_state.help_mode == "question" else "❓ Q&A",
                use_container_width=True,
                type="primary" if st.session_state.help_mode == "question" else "secondary",
                key="btn_qmode"
            ):
                st.session_state.help_mode = "question"
                st.session_state.help_response = ""
                st.rerun()
        with col2:
            if st.button(
                "✅ Command" if st.session_state.help_mode == "command" else "⚡ Command",
                use_container_width=True,
                type="primary" if st.session_state.help_mode == "command" else "secondary",
                key="btn_cmode"
            ):
                st.session_state.help_mode = "command"
                st.session_state.help_response = ""
                st.rerun()

        if st.session_state.help_mode == "question":
            st.info("📚 Ask how to use the app")
        else:
            st.success("🚀 I'll execute actions for you")

        st.divider()

        # Text input for assistant
        with st.form("help_form", clear_on_submit=True):
            placeholder = (
                "How do I assign a task?" if st.session_state.help_mode == "question"
                else "Show me all high priority tasks"
            )
            help_input = st.text_input("Your question / command:", placeholder=placeholder)
            submitted = st.form_submit_button("Send", use_container_width=True)

            if submitted and help_input.strip():
                st.session_state.help_question = help_input.strip()
                # Lazy import to avoid circular
                from services.agent_service import AgentService
                from services.help_service import HelpService
                agent  = AgentService()
                helper = HelpService(agent)
                response = helper.get_response(
                    help_input.strip(),
                    mode=st.session_state.help_mode,
                    user=user
                )
                st.session_state.help_response = response
                st.rerun()

        # Show last Q&A
        if st.session_state.help_question:
            st.markdown("**You asked:**")
            st.code(st.session_state.help_question, language=None)
        if st.session_state.help_response:
            st.markdown("**Response:**")
            st.markdown(st.session_state.help_response)
            if st.button("Clear", key="clear_help"):
                st.session_state.help_question = ""
                st.session_state.help_response  = ""
                st.rerun()

    st.divider()
    if st.button("Sign out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ── Role router ──────────────────────────────────────────────────────
if user["role"] == "manager":
    manager_dashboard.show(user)
else:
    developer_dashboard.show(user)