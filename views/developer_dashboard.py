"""
views/developer_dashboard.py
------------------------------
Developer view — only their assigned tasks.
Status flow: confirmed → in_progress → done
"""

import streamlit as st
import re
from services.task_manager import get_tasks_for_developer, developer_update_task, get_stats_for_developer
from auth import get_all_users
from views.ui_components import render_thread

PRIORITY_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}

STATUS_NEXT  = {"confirmed": "in_progress", "in_progress": "done"}
STATUS_LABEL = {"confirmed": "▶ Start task", "in_progress": "✅ Mark done"}

GROUPS = [
    ("confirmed",   "To do"),
    ("in_progress", "In progress"),
    ("done",        "Completed"),
]


def show(user: dict):
    stats = get_stats_for_developer(user["id"])
    tasks = get_tasks_for_developer(user["id"])

    with st.sidebar:
        st.divider()
        if st.button("🔄 Sync GitHub Status", use_container_width=True):
            from services.github_sync import sync_github_issue_statuses
            if sync_github_issue_statuses(tasks):
                st.success("Synced!")
                st.rerun()

    # ── Metrics row ──────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total assigned", stats["total"])
    c2.metric("To do",          stats["todo"])
    c3.metric("In progress",    stats["in_progress"])
    c4.metric("Done",           stats["done"])
    c5.metric("High priority",  stats["high"])

    st.divider()

    tab_tasks, tab_analytics = st.tabs(["📋 My Tasks", "📈 My Performance"])

    with tab_tasks:
        if not tasks:
            st.info("No tasks assigned to you yet.")
            return

        from services.task_manager import check_and_bump_priority
        prio_map = {"high": 1, "medium": 2, "low": 3}
        
        for group_status, heading in GROUPS:
            group = [t for t in tasks if t["status"] == group_status]
            if not group:
                continue

            for t in group:
                _, bump_msg = check_and_bump_priority(t)
                if bump_msg:
                    st.toast("🚨 Priority bumped by AI due to deadline", icon="🚨")
            
            group.sort(key=lambda t: prio_map.get(t.get("priority", "medium"), 2))
            st.subheader(heading)
            for task in group:
                _render_dev_task(task, user)
            st.divider()

    with tab_analytics:
        st.subheader("Your Performance Overview")
        total = len(tasks)
        done = sum(1 for t in tasks if t["status"] == "done")
        github_linked = sum(1 for t in tasks if t.get("github_issue_url"))
        completion_rate = (done / total * 100) if total > 0 else 0
        confidence_sum = sum(t.get("confidence", 50) for t in tasks)
        avg_conf = (confidence_sum / total) if total > 0 else 0
        score = (completion_rate * 0.5) + (github_linked * 5) + (avg_conf * 0.2)
        
        st.metric("Overall Score", round(score, 1))
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Completion Rate", f"{completion_rate:.1f}%")
        sc2.metric("Avg Task Confidence", f"{avg_conf:.1f}")
        sc3.metric("GitHub Pushes", github_linked)


def _render_dev_task(task: dict, user: dict):
    user_id = user["id"]
    username = user.get("username", "Dev")
    note_key = f"dev_note_open_{task['id']}"
    if note_key not in st.session_state:
        st.session_state[note_key] = False

    with st.container(border=True):
        col_info, col_actions = st.columns([4, 1.5])

        with col_info:
            p_icon = PRIORITY_ICON.get(task["priority"], "⚪")
            st.markdown(f"{p_icon} **{task['description']}**")

            meta = []
            if task.get("deadline"): meta.append(f"📅 Deadline: {task['deadline']}")
            if task.get("meeting_title"): meta.append(f"📋 {task['meeting_title']}")
            if task.get("github_issue_url"): meta.append(f"🐙 [GitHub Issue]({task['github_issue_url']})")
            if meta: st.caption("  ·  ".join(meta))

            # Threaded Chat display (Consolidated)
            if task.get("manager_notes") or task.get("dev_notes"):
                tgl_key = f"dev_tgl_{task['id']}"
                if st.toggle(f"💬 View Thread", key=tgl_key):
                    render_thread(task)

            # ── Note Section (Consolidated) ──
            if st.session_state[note_key]:
                st.divider()
                note_input_key = f"dev_note_input_{task['id']}"
                if note_input_key not in st.session_state:
                    st.session_state[note_input_key] = ""
                
                ai_check_key = f"ai_check_{task['id']}"
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("🤖 AI Status & Send", key=f"dev_ai_btn_{task['id']}", use_container_width=True):
                        note_val = st.session_state[note_input_key]
                        if note_val.strip():
                            from services.extractor import infer_task_status_from_note
                            new_status = infer_task_status_from_note(note_val, task["status"])
                            st.session_state[ai_check_key] = (note_val, new_status)
                            st.rerun()

                with col_btn2:
                    if st.button("📤 Send plain", key=f"dev_send_btn_{task['id']}", use_container_width=True):
                        note_val = st.session_state[note_input_key]
                        if note_val.strip():
                            from services.task_manager import append_task_note
                            append_task_note(task["id"], note_val.strip(), "💻", username)
                            st.session_state[note_input_key] = ""
                            st.rerun()

                if ai_check_key in st.session_state and st.session_state[ai_check_key]:
                    msg, sug_status = st.session_state[ai_check_key]
                    st.warning(f"🤖 AI suggests status: **{sug_status.upper()}**")
                    c1, c2 = st.columns(2)
                    if c1.button("Confirm Status & Send", key=f"dev_confirm_send_{task['id']}", use_container_width=True):
                        from services.task_manager import append_task_note
                        append_task_note(task["id"], msg.strip(), "💻", username)
                        developer_update_task(task["id"], user_id, {"status": sug_status})
                        st.session_state[ai_check_key] = None
                        st.session_state[note_input_key] = ""
                        st.rerun()
                    if c2.button("Keep original & Send", key=f"dev_keep_send_{task['id']}", use_container_width=True):
                        from services.task_manager import append_task_note
                        append_task_note(task["id"], msg.strip(), "💻", username)
                        st.session_state[ai_check_key] = None
                        st.session_state[note_input_key] = ""
                        st.rerun()

                st.text_area("Your message", key=note_input_key, height=100, placeholder="Type message...")

        with col_actions:
            next_status = STATUS_NEXT.get(task["status"])
            if next_status:
                if st.button(STATUS_LABEL[task["status"]], key=f"dev_progress_{task['id']}", type="primary", use_container_width=True):
                    developer_update_task(task["id"], user_id, {"status": next_status})
                    st.rerun()

            # Fast Reply
            thread_exists = bool(task.get("manager_notes") or task.get("dev_notes"))
            fast_key = f"dev_fast_reply_{task['id']}"
            if fast_key not in st.session_state: st.session_state[fast_key] = False
                
            if st.button("💬 Reply" if thread_exists else "📝 Start Thread", key=f"dev_fast_btn_{task['id']}", use_container_width=True):
                st.session_state[fast_key] = not st.session_state[fast_key]
                st.rerun()
                
            if st.session_state[fast_key]:
                with st.popover("Quick Message"):
                    i_key = f"fast_note_dev_{task['id']}"
                    if i_key not in st.session_state: st.session_state[i_key] = ""
                    
                    if st.button("📤 Send", key=f"fast_send_dev_{task['id']}", use_container_width=True):
                        f_note = st.session_state[i_key]
                        if f_note.strip():
                            from services.task_manager import append_task_note
                            append_task_note(task["id"], f_note.strip(), "💻", username)
                            st.session_state[i_key] = ""
                            st.session_state[fast_key] = False
                            st.rerun()
                    st.text_area("Message", key=i_key, placeholder="Type message...")