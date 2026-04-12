import streamlit as st
import re
from services.task_manager import parse_thread_history

def render_thread(task: dict, title="Thread History"):
    """
    Consolidated thread rendering component.
    Handles parsing both manager_notes and the legacy dev_notes column.
    """
    # 1. Unified parsing from manager_notes (the new source of truth)
    notes_raw = task.get("manager_notes") or ""
    
    # LEGACY SUPPORT: If dev_notes has content not in manager_notes, we can show it
    # but for now we focus on the consolidated history.
    dev_notes = task.get("dev_notes")
    if dev_notes and dev_notes.strip() and dev_notes not in notes_raw:
        # One-time visual merge for older tasks
        legacy_messages = [f"[💻 Dev (Old)]: {msg}" for msg in dev_notes.split("\n") if msg.strip()]
        notes_raw = "\n".join(legacy_messages) + "\n" + notes_raw

    messages = parse_thread_history(notes_raw)
    
    if not messages:
        st.caption("No thread history yet.")
        return

    st.markdown(f"**{title} ({len(messages)} msgs)**")
    with st.container(height=250, border=True):
        for msg in messages:
            icon = msg["icon"]
            label = msg["label"]
            text = msg["text"]
            
            # Treat @ as a normal character - no special regex replacement
            # Just render the text as is.
            
            if icon in ["💻", "user"] or "Dev" in label:
                with st.chat_message("user", avatar="💻"):
                    st.markdown(text)
            elif icon in ["💼", "👔", "assistant"] or "Mngr" in label:
                with st.chat_message("assistant", avatar="💼"):
                    st.markdown(text)
            elif icon == "🤖" or "AI" in label:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown(text)
            else:
                with st.chat_message("assistant", avatar=icon if len(icon)==1 else "💬"):
                    st.markdown(text)
