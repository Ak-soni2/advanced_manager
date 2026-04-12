"""
pages/manager_dashboard.py
---------------------------
Three tabs:
  1. Upload transcript → AI extraction
  2. Review queue → confirm / reject with full inline editing
  3. All tasks → manager can edit every field on every task
"""

import streamlit as st
import re
from services.extractor import extract_tasks_and_attendees
from services.task_manager import (
    save_meeting, save_extracted_tasks,
    get_pending_tasks, get_all_tasks_for_manager,
    get_stats_for_manager, manager_update_task,
    confirm_and_assign, reject_task, delete_task, delete_all_tasks
)
from services.help_service import HelpService
from auth import get_all_developers, get_all_users
from views.ui_components import render_thread

# ── Constants ─────────────────────────────────────────────────────────
PRIORITY_OPTS  = ["high", "medium", "low"]
STATUS_OPTS    = ["pending_review", "confirmed", "in_progress", "done", "rejected"]
STATUS_LABELS  = {
    "pending_review": "🕐 Pending review",
    "confirmed":      "✅ Confirmed",
    "in_progress":    "🔄 In progress",
    "done":           "🏁 Done",
    "rejected":       "❌ Rejected",
}

def _conf_icon(c: int) -> str:
    if c >= 70: return "🟢"
    if c >= 40: return "🟡"
    return "🔴"


def show(user: dict):
    # ── Contextual tip ───────────────────────────────────────────────
    stats = get_stats_for_manager()
    tip   = HelpService().get_contextual_suggestions(stats)
    st.info(f"💡 {tip}")

    # ── Stats row (mirrors repo render_stats) ────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total tasks",     stats["total"])
    c2.metric("Pending review",  stats["pending_review"])
    c3.metric("In progress",     stats["in_progress"])
    c4.metric("Done",            stats["done"])
    c5.metric("High priority",   stats["high"])

    st.divider()

    # ── Devs lookup ──────────────────────────────────────────────────
    devs        = get_all_developers()
    dev_by_name = {d["username"]: d["id"]       for d in devs}
    dev_by_id   = {d["id"]:       d["username"] for d in devs}
    dev_gh_by_id = {d["id"]:      d.get("github_handle") for d in devs}

    with st.sidebar:
        st.divider()
        if st.button("🔄 Sync GitHub Status", use_container_width=True):
            from services.github_sync import sync_github_issue_statuses
            all_t = get_all_tasks_for_manager()
            if sync_github_issue_statuses(all_t):
                st.success("Synced with GitHub!")
                st.rerun()

    with st.expander("👥 Quick Add missing developer"):
        with st.form("add_dev_form", clear_on_submit=True):
            nd_col1, nd_col2 = st.columns(2)
            new_dev_name = nd_col1.text_input("Username (e.g. Shreya)")
            new_dev_gh = nd_col2.text_input("GitHub Handle (Mandatory)")
            if st.form_submit_button("Create Profile"):
                if not new_dev_name or not new_dev_gh:
                    st.error("Both Username and GitHub Handle are required.")
                else:
                    from auth import create_developer
                    if create_developer(new_dev_name, new_dev_gh):
                        st.success(f"Added {new_dev_name}! Default password is 'dev123'.")
                        st.rerun()

    tab_upload, tab_review, tab_all, tab_analytics = st.tabs([
        "📤 Upload transcript",
        f"🔍 Review queue  ({stats['pending_review']})",
        "📋 All tasks",
        "📈 Analytics"
    ])

    # ═══════════════════════════════════════════════════════════════
    # TAB 1: Upload
    # ═══════════════════════════════════════════════════════════════
    with tab_upload:
        st.subheader("Upload meeting transcript")
        col_form, col_tip = st.columns([2, 1])

        with col_form:
            title = st.text_input(
                "Meeting title",
                placeholder="Sprint planning — Apr 3"
            )
            transcript = st.text_area(
                "Paste transcript here",
                height=340,
                placeholder=(
                    "Akshay: I'll handle the auth refactor by Friday.\n"
                    "Priya: I can take the dashboard design, should be done by next week.\n"
                    "Manager: Rahul, can you look into the API performance issues?\n"
                    "Rahul: Sure, I'll investigate and report back on Monday."
                )
            )
            btn_disabled = not transcript.strip()
            if st.button("🧠 Extract tasks with AI", type="primary", disabled=btn_disabled):
                with st.spinner(f"Running AI extraction with Qwen…"):
                    tasks, attendees = extract_tasks_and_attendees(transcript)

                if not tasks:
                    st.warning(
                        "No tasks found. Make sure the transcript has clear action items "
                        "with assignee names."
                    )
                else:
                    mid = save_meeting(
                        title.strip() or "Untitled meeting",
                        transcript,
                        user["id"],
                        attendees
                    )
                    save_extracted_tasks(mid, tasks)
                    st.success(
                        f"✅ Extracted **{len(tasks)} tasks** — go to Review queue to confirm them."
                    )
                    st.session_state.last_meeting_id = mid
                    st.balloons()

        with col_tip:
            st.info(
                "**How extraction works**\n\n"
                "The AI reads your transcript and identifies:\n"
                "- Action items\n"
                "- Who is responsible\n"
                "- Deadlines mentioned\n"
                "- Priority signals\n\n"
                "Each task gets a **confidence score** — "
                "low-confidence tasks expand automatically in the Review queue."
            )

    # ═══════════════════════════════════════════════════════════════
    # TAB 2: Review Queue
    # ═══════════════════════════════════════════════════════════════
    with tab_review:
        pending = get_pending_tasks()

        if not pending:
            st.success("All tasks reviewed — nothing pending! 🎉")
        else:
            c_rev1, c_rev2 = st.columns([2, 1])
            search_query = c_rev1.text_input("🔍 Filter pending tasks", placeholder="Search by name or description...", key="rev_search")
            
            # Group by meeting logic
            meetings_map = {}
            for t in pending:
                m_title = t.get("meeting_title") or "Unknown Meeting"
                if m_title not in meetings_map: meetings_map[m_title] = []
                meetings_map[m_title].append(t)

            st.caption(
                f"**{len(pending)} tasks** need review · grouped by meeting · sorted by low confidence"
            )
            st.divider()

            for m_title, tasks in meetings_map.items():
                # Filter tasks within meeting
                if search_query:
                    tasks = [t for t in tasks if search_query.lower() in t["description"].lower() or search_query.lower() in (t.get("raw_assignee") or "").lower()]
                
                if not tasks: continue

                # Sort tasks within meeting by confidence descending
                tasks.sort(key=lambda x: x.get("confidence", 0), reverse=True)

                with st.expander(f"📁 **{m_title}** ({len(tasks)} tasks)", expanded=True):
                    for task in tasks:
                        conf = task["confidence"]
                        with st.expander(f"{_conf_icon(conf)} **{conf}% confidence** — {task['description']}", expanded=(conf < 50)):
                            col_left, col_right = st.columns([3, 2])

                            with col_left:
                                # Fully editable description (repo edit pattern)
                                new_desc = st.text_area(
                                    "Task description",
                                    value=task["description"],
                                    height=90,
                                    key=f"rev_desc_{task['id']}",
                                    help="Edit the task before confirming"
                                )
                                
                                reasoning = task.get("reasoning")
                                if reasoning:
                                    st.info(f"🤖 **AI Reasoning:** {reasoning}")
                        new_notes = st.text_input(
                            "Manager notes (optional)",
                            value=task.get("manager_notes") or "",
                            key=f"rev_notes_{task['id']}"
                        )
                        if task.get("meeting_title"):
                            st.caption(f"📋 From: {task['meeting_title']}")

                            with col_right:
                                # Smart assignee pre-selection from AI raw_assignee and meeting attendees
                                meeting_attendees = task.get("meeting_attendees") or []
                                show_all = st.checkbox("Show all developers", key=f"show_all_{task['id']}")
                                
                                if show_all or not meeting_attendees:
                                    available_devs = dev_by_name
                                else:
                                    available_devs = {
                                        k: v for k, v in dev_by_name.items() 
                                        if any(att.lower() in k.lower() or k.lower() in att.lower() for att in meeting_attendees)
                                    }
                                    if not available_devs:
                                        available_devs = dev_by_name

                                ai_name_raw  = task.get("raw_assignee") or ""
                                # Split by commas, "and", "&" to find all suggested names
                                ai_names = [n.strip().lower() for n in re.split(r'[,&]|\band\b', ai_name_raw) if n.strip()]
                                
                                best_devs = [
                                    k for k in available_devs
                                    if any(n in k.lower() or k.lower() in n for n in ai_names)
                                ]

                                from auth import create_developer
                                if ai_names and not best_devs:
                                    missing_dev = ai_names[0].title() # just suggest the first one for quick create
                                    st.warning(f"🚨 **New Developer Detected:** '{missing_dev}'. They are not in your system.")
                                    
                                    gh_col1, gh_col2 = st.columns([2, 1])
                                    gh_handle = gh_col1.text_input("GitHub Username", key=f"cr_gh_{task['id']}")
                                    if gh_col2.button(f"Create Profile", key=f"cr_dev_{task['id']}"):
                                        if not gh_handle:
                                            st.error("GitHub handle required.")
                                        else:
                                            if create_developer(missing_dev, gh_handle):
                                                st.success(f"Added {missing_dev}! Refreshing...")
                                                st.rerun()

                                if not available_devs:
                                    st.warning("No developers found. Add developer accounts first.")
                                    assignees = []
                                else:
                                    assignees = st.multiselect(
                                        "Assign to (select one or multiple)",
                                        list(available_devs.keys()),
                                        default=best_devs,
                                        key=f"rev_assign_{task['id']}"
                                    )
                                    if ai_name_raw:
                                        st.caption(f"AI suggested: **{ai_name_raw}** ({conf}% confident)")
                                    if meeting_attendees and not show_all:
                                        st.caption(f"👥 Filtered to attendees: {', '.join(meeting_attendees)}")

                                    priority = st.selectbox(
                                        "Priority",
                                        PRIORITY_OPTS,
                                        index=PRIORITY_OPTS.index(task.get("priority", "medium")),
                                        key=f"rev_prio_{task['id']}"
                                    )
                                    # Format for display: yyyy-mm-dd -> dd-mm-yyyy if possible
                                    d_val = task.get("deadline") or ""
                                    if "-" in d_val and len(d_val.split("-")[0]) == 4:
                                        y,m,day = d_val.split("-")
                                        d_val = f"{day}-{m}-{y}"
                                        
                                    deadline = st.text_input(
                                        "Deadline",
                                        value=d_val,
                                        placeholder="e.g. 10-04-2024",
                                        key=f"rev_dead_{task['id']}"
                                    )

                            # Action buttons
                            t_b1, t_b2, t_b3, _ = st.columns([1.5, 1, 1, 2])
                            with t_b1:
                                if st.button(
                                    "✅ Confirm & assign",
                                    key=f"rev_confirm_{task['id']}",
                                    type="primary",
                                    disabled=not assignees
                                ):
                                    # Append note to thread if it exists using safe atomic helper
                                    if new_notes:
                                        from services.task_manager import append_task_note
                                        append_task_note(task["id"], new_notes.strip(), "👔", "Mngr")
                                        
                                    assignees_list = [dev_by_name[a] for a in assignees] if assignees else []
                                    primary_assignee = dev_by_name[assignees[0]] if assignees else None

                                    confirm_and_assign(
                                        task["id"],
                                        primary_assignee,
                                        new_desc,
                                        priority,
                                        deadline or None,
                                        task.get("manager_notes"), # Keep existing notes
                                        assignees_list=assignees_list
                                    )
                                    st.success(f"Assigned successfully!")
                                    st.rerun()
                            with t_b2:
                                if st.button("❌ Reject", key=f"rev_reject_{task['id']}"):
                                    reject_task(task["id"])
                                    st.rerun()
                            with t_b3:
                                if st.button("🗑️ Delete", type="tertiary", key=f"rev_del_{task['id']}"):
                                    delete_task(task["id"])
                                    st.rerun()
                        st.divider()

    # ═══════════════════════════════════════════════════════════════
    # TAB 3: All Tasks — full edit access (manager superpower)
    # ═══════════════════════════════════════════════════════════════
    with tab_all:
        col_filter, col_sort, col_mtg = st.columns([3, 1, 2])
        with col_filter:
            status_filter = st.multiselect(
                "Filter by status",
                STATUS_OPTS,
                default=["confirmed", "in_progress", "done"],
                format_func=lambda s: STATUS_LABELS.get(s, s)
            )
        with col_sort:
            priority_filter = st.selectbox(
                "Priority",
                ["All", "high", "medium", "low"]
            )
        with col_mtg:
            mtg_filter = st.text_input("Filter by Meeting Title")

        all_tasks = get_all_tasks_for_manager(status_filter or None)
        # Sort by confidence descending by default for better visibility
        all_tasks.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        if priority_filter != "All":
            all_tasks = [t for t in all_tasks if t["priority"] == priority_filter]
        if mtg_filter:
            all_tasks = [t for t in all_tasks if mtg_filter.lower() in (t.get("meeting_title") or "").lower()]

        if not all_tasks:
            st.info("No tasks match the current filters.")
        else:
            st.caption(f"Showing **{len(all_tasks)}** tasks")
            if st.button("🚨 Delete All tasks (Dangerous!)"):
                delete_all_tasks()
                st.rerun()
                
            st.divider()

            for task in all_tasks:
                _render_manager_task_card(task, dev_by_name, dev_by_id, dev_gh_by_id, user)

    # ═══════════════════════════════════════════════════════════════
    # TAB 4: Analytics
    # ═══════════════════════════════════════════════════════════════
    with tab_analytics:
        st.subheader("Evaluation Dashboard")
        st.markdown("Quantitative Employee Evaluation based on Automated Tasks and GitHub.")
        
        all_tasks_stats = get_all_tasks_for_manager()
        
        dev_stats = []
        for dev in devs:
            dev_tasks = [t for t in all_tasks_stats if t.get("assigned_to") == dev["id"]]
            total = len(dev_tasks)
            done = sum(1 for t in dev_tasks if t["status"] == "done")
            github_linked = sum(1 for t in dev_tasks if t.get("github_issue_url"))
            
            completion_rate = (done / total * 100) if total > 0 else 0
            
            confidence_sum = sum(t.get("confidence", 50) for t in dev_tasks)
            avg_conf = (confidence_sum / total) if total > 0 else 0
            
            score = (completion_rate * 0.5) + (github_linked * 5) + (avg_conf * 0.2)
            
            dev_stats.append({
                "Developer": dev["username"],
                "Total Tasks": total,
                "Completed": done,
                "Completion %": f"{completion_rate:.1f}%",
                "GH Pushes": github_linked,
                "Avg Confidence": f"{avg_conf:.1f}",
                "Overall Score": round(score, 1)
            })
            
        import pandas as pd
        if dev_stats:
            df = pd.DataFrame(dev_stats).sort_values(by="Overall Score", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption("Score Calculation = (Completion Rate * 0.5) + (GitHub Pushes * 5) + (Avg Task Confidence * 0.2)")
        else:
            st.info("No developer data available.")


def _render_manager_task_card(task: dict, dev_by_name: dict, dev_by_id: dict, dev_gh_by_id: dict, current_user: dict):
    """
    Inline-editable task card for the manager.
    """
    username = current_user.get("username", "Mngr")
    edit_key = f"mgr_edit_{task['id']}"
    if edit_key not in st.session_state:
        st.session_state[edit_key] = False

    with st.container(border=True):
        if not st.session_state[edit_key]:
            # ── Display mode ─────────────────────────────────────────
            top, action = st.columns([5, 1.5])
            with top:
                st.markdown(f"**{task['description']}**")
                
                reasoning = task.get("reasoning")
                if reasoning:
                    st.info(f"🤖 **AI Reasoning:** {reasoning}")

                meta = []
                if task.get("assignees_list"):
                    names = [dev_by_id.get(uid, "Unknown") for uid in task.get("assignees_list")]
                    meta.append(f"👥 {', '.join(names)}")
                elif task.get("assigned_username"):
                    meta.append(f"👤 {task['assigned_username']}")
                if task.get("priority"):
                    icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                    meta.append(icons.get(task["priority"], "") + " " + task["priority"])
                if task.get("deadline"):
                    d = task["deadline"]
                    if "-" in d and len(d.split("-")[0]) == 4:
                        y,m,day = d.split("-")
                        d = f"{day}-{m}-{y}"
                    meta.append(f"📅 Deadline: {d}")
                if task.get("meeting_title"):
                    meta.append(f"📋 {task['meeting_title']}")
                if task.get("github_issue_url"):
                    meta.append(f"🐙 [GitHub Issue]({task['github_issue_url']})")
                st.caption("  ·  ".join(meta))

                status_badge = STATUS_LABELS.get(task["status"], task["status"])
                st.caption(status_badge)

                # Threaded Chat display (Consolidated component)
                if task.get("manager_notes") or task.get("dev_notes"):
                    tgl_key = f"tgl_v_{task['id']}"
                    if st.toggle(f"💬 View Thread", key=tgl_key):
                        render_thread(task)

            with action:
                if st.button("✏️ Edit", key=f"mgr_editbtn_{task['id']}", use_container_width=True):
                    st.session_state[edit_key] = True
                    st.rerun()

                reply_key = f"fast_reply_open_{task['id']}"
                if reply_key not in st.session_state: st.session_state[reply_key] = False

                thread_exists = bool(task.get("manager_notes") or task.get("dev_notes"))
                if st.button("💬 Reply" if thread_exists else "📝 Start Thread", key=f"fast_reply_btn_{task['id']}", use_container_width=True):
                    st.session_state[reply_key] = not st.session_state[reply_key]
                    st.rerun()

                if st.session_state[reply_key]:
                    with st.popover("Quick Message"):
                        note_input_key = f"fast_note_{task['id']}"
                        if note_input_key not in st.session_state: st.session_state[note_input_key] = ""
                        
                        # Process Send BUTTON BEFORE the text area
                        if st.button("📤 Send", key=f"fast_send_{task['id']}", use_container_width=True):
                            f_note = st.session_state[note_input_key]
                            if f_note.strip():
                                from services.task_manager import append_task_note
                                append_task_note(task["id"], f_note.strip(), "💼", username)
                                st.session_state[note_input_key] = ""
                                st.session_state[reply_key] = False
                                st.rerun()
                        st.text_area("Message", key=note_input_key, placeholder="Type message...")

                if st.button("🐙 Push to GH", key=f"mgr_ghbtn_{task['id']}", use_container_width=True):
                    from services.github_sync import create_github_issue
                    gh_handle = dev_gh_by_id.get(task.get("assigned_to"))
                    with st.spinner("Pushing..."):
                        url = create_github_issue(task, gh_handle)
                    
                    if url == "ERR_MISSING_COLUMN":
                        st.error("🚨 Database Column Missing!")
                    elif url and not url.startswith("ERROR"):
                        st.success(f"🚀 [Issue Created]({url})")
                        st.rerun()
                    else:
                        st.error(f"❌ GitHub Error: {url or 'Check .env'}")
                            
                if st.button("🗑️ Delete", key=f"mgr_delbtn_{task['id']}", use_container_width=True):
                    delete_task(task["id"])
                    st.rerun()

        else:
            # ── Edit mode ──
            st.markdown("**Editing task**")
            with st.form(key=f"mgr_form_{task['id']}"):
                e_desc = st.text_area("Description", value=task["description"], height=80)
                
                reasoning = task.get("reasoning")
                if reasoning:
                    st.info(f"🤖 **AI Reasoning:** {reasoning}")

                ec1, ec2, ec3 = st.columns(3)
                with ec1:
                    curr_ids = task.get("assignees_list") or ([task.get("assigned_to")] if task.get("assigned_to") else [])
                    def_names = [dev_by_id[uid] for uid in curr_ids if uid in dev_by_id]
                    e_assignees = st.multiselect("Assignees", list(dev_by_name.keys()), default=def_names)
                with ec2:
                    e_prio = st.selectbox("Priority", PRIORITY_OPTS, index=PRIORITY_OPTS.index(task.get("priority", "medium")))
                with ec3:
                    e_status = st.selectbox("Status", STATUS_OPTS, index=STATUS_OPTS.index(task["status"]), format_func=lambda s: STATUS_LABELS.get(s, s))

                # Format for display
                d_val = task.get("deadline") or ""
                if "-" in d_val and len(d_val.split("-")[0]) == 4:
                    y,m,day = d_val.split("-")
                    d_val = f"{day}-{m}-{y}"
                e_deadline = st.text_input("Deadline", value=d_val)

                save_col, cancel_col = st.columns(2)
                with save_col:
                    if st.form_submit_button("💾 Save core changes", type="primary", use_container_width=True):
                        assignees_ids = [dev_by_name[a] for a in e_assignees]
                        manager_update_task(task["id"], {
                            "description":   e_desc,
                            "priority":      e_prio,
                            "status":        e_status,
                            "deadline":      e_deadline or None,
                            "assignees_list": assignees_ids,
                            "assigned_to":   assignees_ids[0] if assignees_ids else None
                        })
                        st.session_state[edit_key] = False
                        st.rerun()
                with cancel_col:
                    if st.form_submit_button("Cancel", use_container_width=True):
                        st.session_state[edit_key] = False
                        st.rerun()

            st.divider()
            # ── Note Section (Consolidated) ──
            st.markdown("💬 **Thread Management**")
            render_thread(task)
            
            note_input_key = f"mgr_note_input_{task['id']}"
            if note_input_key not in st.session_state:
                st.session_state[note_input_key] = ""
            
            # Process Send BUTTON BEFORE the text area
            if st.button("📤 Send Message", key=f"send_e_{task['id']}", use_container_width=True):
                val = st.session_state[note_input_key]
                if val.strip():
                    from services.task_manager import append_task_note
                    append_task_note(task["id"], val.strip(), "💼", username)
                    st.session_state[note_input_key] = "" 
                    st.rerun()
            st.text_area("New Message", key=note_input_key, height=100, placeholder="Type message...")