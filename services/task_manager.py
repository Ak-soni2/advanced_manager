"""
services/task_manager.py
------------------------
All Supabase task CRUD.  Adapted from the repo's TaskManager patterns:
- Stats breakdown (priority + status groups) from get_stats()
- Migration-safe field defaults
- Filter helpers (by priority, status, assignee)
"""

from datetime import datetime, timezone
from database import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def check_and_bump_priority(task: dict) -> tuple[dict, str | None]:
    """
    Checks if deadline is approaching.
    If 1-2 days away -> bump low to medium.
    If today/past -> bump to high.
    Updates DB directly and returns mutated task + toast msg.
    """
    dl = task.get("deadline")
    if not dl or task.get("status") in ("done", "rejected"):
        return task, None

    try:
        from datetime import datetime as dt
        # Extract DD-MM-YYYY anywhere in the string
        import re
        match = re.search(r'\d{2}-\d{2}-\d{4}', dl)
        if not match:
            return task, None
            
        d_val = dt.strptime(match.group(), "%d-%m-%Y").date()
        today = dt.now().date()
        days_left = (d_val - today).days

        new_prio = None
        if days_left <= 0 and task["priority"] != "high":
            new_prio = "high"
        elif days_left in (1, 2) and task["priority"] == "low":
            new_prio = "medium"

        if new_prio:
            get_db().table("tasks").update({"priority": new_prio}).eq("id", task["id"]).execute()
            task["priority"] = new_prio
            return task, f"🚨 Priority for '{task['description'][:20]}...' increased to {new_prio.upper()} due to deadline ({days_left} days left)!"
            
    except Exception:
        pass
        
    return task, None


# ── Meetings ─────────────────────────────────────────────────────────

def save_meeting(title: str, transcript: str, uploaded_by: str, attendees: list[str]) -> str:
    db = get_db()
    result = (
        db.table("meetings")
        .insert({
            "title": title, 
            "transcript": transcript, 
            "uploaded_by": uploaded_by,
            "attendees": attendees
        })
        .execute()
    )
    return result.data[0]["id"]


def get_meetings() -> list[dict]:
    db = get_db()
    result = db.table("meetings").select("*").order("created_at", desc=True).execute()
    return result.data or []


# ── Task queries ──────────────────────────────────────────────────────

def _flatten_joins(rows: list[dict]) -> list[dict]:
    """Flatten Supabase nested join dicts into flat task dicts."""
    out = []
    for row in rows:
        meetings_data = row.pop("meetings", None) or {}
        row["meeting_title"]      = meetings_data.get("title", "")
        row["meeting_attendees"]  = meetings_data.get("attendees", [])
        row["assigned_username"]  = (row.pop("users",    None) or {}).get("username", "")
        out.append(row)
    return out


def get_pending_tasks() -> list[dict]:
    """All tasks awaiting manager review — sorted low-confidence first."""
    db = get_db()
    result = (
        db.table("tasks")
        .select("*, meetings(title, attendees)")
        .eq("status", "pending_review")
        .order("confidence", desc=True)
        .execute()
    )
    return _flatten_joins(result.data or [])


def get_all_tasks_for_manager(
    status_filter: list[str] | None = None,
    meeting_id: str | None = None,
) -> list[dict]:
    db = get_db()
    q = db.table("tasks").select("*, meetings(title, attendees), users(username)")
    if status_filter:
        q = q.in_("status", status_filter)
    if meeting_id:
        q = q.eq("meeting_id", meeting_id)
    result = q.order("created_at", desc=True).execute()
    return _flatten_joins(result.data or [])


def get_tasks_for_developer(user_id: str) -> list[dict]:
    db = get_db()
    try:
        result = (
            db.table("tasks")
            .select("*, meetings(title, attendees)")
            .contains("assignees_list", f'["{user_id}"]')
            .not_.in_("status", ["rejected", "pending_review"])
            .order("created_at", desc=True)
            .execute()
        )
    except Exception:
        result = (
            db.table("tasks")
            .select("*, meetings(title, attendees)")
            .eq("assigned_to", user_id)
            .not_.in_("status", ["rejected", "pending_review"])
            .order("created_at", desc=True)
            .execute()
        )
    return _flatten_joins(result.data or [])


# ── Stats (mirrors repo get_stats()) ─────────────────────────────────

def get_stats_for_manager() -> dict:
    tasks = get_all_tasks_for_manager()
    total        = len(tasks)
    confirmed    = sum(1 for t in tasks if t["status"] == "confirmed")
    in_progress  = sum(1 for t in tasks if t["status"] == "in_progress")
    done         = sum(1 for t in tasks if t["status"] == "done")
    pending_rev  = sum(1 for t in tasks if t["status"] == "pending_review")
    rejected     = sum(1 for t in tasks if t["status"] == "rejected")
    high         = sum(1 for t in tasks if t["priority"] == "high")
    medium       = sum(1 for t in tasks if t["priority"] == "medium")
    low          = sum(1 for t in tasks if t["priority"] == "low")
    return dict(
        total=total, confirmed=confirmed, in_progress=in_progress,
        done=done, pending_review=pending_rev, rejected=rejected,
        high=high, medium=medium, low=low
    )


def get_stats_for_developer(user_id: str) -> dict:
    tasks       = get_tasks_for_developer(user_id)
    total       = len(tasks)
    todo        = sum(1 for t in tasks if t["status"] == "confirmed")
    in_progress = sum(1 for t in tasks if t["status"] == "in_progress")
    done        = sum(1 for t in tasks if t["status"] == "done")
    high        = sum(1 for t in tasks if t["priority"] == "high")
    return dict(total=total, todo=todo, in_progress=in_progress, done=done, high=high)


def get_leaderboard_matrix() -> list[dict]:
    """Cross-team developer leaderboard used by manager and developer dashboards."""
    db = get_db()
    dev_result = (
        db.table("users")
        .select("id, username")
        .eq("role", "developer")
        .order("username")
        .execute()
    )
    developers = dev_result.data or []
    all_tasks = get_all_tasks_for_manager()

    rows = []
    for dev in developers:
        dev_id = dev["id"]
        dev_tasks = []

        for task in all_tasks:
            assignees = task.get("assignees_list") or []
            assigned_to = task.get("assigned_to")
            if dev_id in assignees or assigned_to == dev_id:
                dev_tasks.append(task)

        total = len(dev_tasks)
        completed = sum(1 for t in dev_tasks if t.get("status") == "done")
        github_linked = sum(1 for t in dev_tasks if t.get("github_issue_url"))
        completion_rate = (completed / total) * 100 if total else 0
        avg_confidence = (
            sum((float(t.get("confidence") or 50) for t in dev_tasks)) / total
            if total else 0
        )
        overall_score = (completion_rate * 0.5) + (github_linked * 5) + (avg_confidence * 0.2)

        rows.append({
            "developer": dev.get("username", "Unknown"),
            "developer_id": dev_id,
            "total": total,
            "completed": completed,
            "completion_rate": completion_rate,
            "github_linked": github_linked,
            "avg_confidence": avg_confidence,
            "overall_score": overall_score,
        })

    rows.sort(key=lambda x: x["overall_score"], reverse=True)
    return rows


# ── Writes ───────────────────────────────────────────────────────────

def save_extracted_tasks(meeting_id: str, tasks: list[dict]):
    db = get_db()
    rows = []
    for t in tasks:
        # Join list of assignees into a single string for the DB 'raw_assignee' column
        raw_list = t.get("raw_assignees") or []
        if isinstance(raw_list, str): raw_list = [raw_list] # fallback
        raw_str = ", ".join(raw_list) if raw_list else t.get("raw_assignee")

        rows.append({
            "meeting_id":   meeting_id,
            "description":  t["description"],
            "raw_assignee": raw_str,
            "confidence":   int(t.get("confidence", 50)),
            "priority":     t.get("priority", "medium"),
            "deadline":     t.get("deadline"),
            "reasoning":    t.get("reasoning"),
            "manager_notes": None,
        })
    if rows:
        db.table("tasks").insert(rows).execute()


def manager_update_task(task_id: str, updates: dict):
    """Manager can update ANY field on ANY task."""
    updates["updated_at"] = _now()
    try:
        get_db().table("tasks").update(updates).eq("id", task_id).execute()
    except Exception as e:
        if "assignees_list" in updates:
            # Fallback for when the SQL migration hasn't been run yet
            updates.pop("assignees_list")
            get_db().table("tasks").update(updates).eq("id", task_id).execute()
        else:
            raise e


def confirm_and_assign(
    task_id: str,
    assigned_to: str,
    description: str,
    priority: str,
    deadline: str | None,
    manager_notes: str | None,
    assignees_list: list[str] = None
):
    updates = {
        "status":        "confirmed",
        "description":   description,
        "priority":      priority,
        "deadline":      deadline,
        "manager_notes": manager_notes,
    }
    
    if assignees_list:
        updates["assignees_list"] = assignees_list
        updates["assigned_to"] = assignees_list[0]
    else:
        updates["assigned_to"] = assigned_to

    manager_update_task(task_id, updates)


def reject_task(task_id: str):
    manager_update_task(task_id, {"status": "rejected"})


def developer_update_task(task_id: str, user_id: str, updates: dict):
    """Developer can only move their own tasks forward in status and update notes."""
    updates["updated_at"] = _now()
    try:
        (
            get_db()
            .table("tasks")
            .update(updates)
            .eq("id", task_id)
            .contains("assignees_list", f'["{user_id}"]')
            .execute()
        )
    except Exception:
        (
            get_db()
            .table("tasks")
            .update(updates)
            .eq("id", task_id)
            .eq("assigned_to", user_id)
            .execute()
        )

def append_task_note(task_id: str, note_text: str, sender_icon: str, sender_label: str):
    """
    Safely appends a message to the task thread by fetching the latest content first.
    Uses manager_notes as the consolidated thread history.
    """
    db = get_db()
    current_task = db.table("tasks").select("manager_notes").eq("id", task_id).maybe_single().execute()
    if not current_task.data:
        return
        
    old_notes = current_task.data.get("manager_notes") or ""
    
    # Clean up note text: replace real newlines with a marker to keep the storage line-based
    # but allow UI to render multiple lines if needed. 
    # Or just keep them and split by the [SENDER] pattern.
    cleaned_text = note_text.strip()
    
    new_entry = f"[{sender_icon} {sender_label}]: {cleaned_text}"
    full_notes = f"{old_notes}\n{new_entry}" if old_notes else new_entry
    
    db.table("tasks").update({
        "manager_notes": full_notes.strip(),
        "updated_at": _now()
    }).eq("id", task_id).execute()

def parse_thread_history(notes_raw: str | None) -> list[dict]:
    """
    Parses the raw notes string into a list of message objects.
    Logic: Splits by lines, but handles messages that might have been 
    appended with internal newlines (we look for the [ICON LABEL]: pattern).
    """
    if not notes_raw:
        return []
    
    lines = notes_raw.split("\n")
    messages = []
    
    import re
    # Pattern to detect a new message header: [emoji Label]:
    # e.g., [💼 Mngr]: , [💻 Dev]: , [🤖 AI]:
    header_pattern = re.compile(r"^\[(.*?)\s+(.*?)\]:\s*(.*)")
    
    current_msg = None
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        match = header_pattern.match(line)
        if match:
            if current_msg:
                messages.append(current_msg)
            
            icon, label, content = match.groups()
            current_msg = {
                "icon": icon,
                "label": label,
                "text": content,
                "raw": line
            }
        else:
            if current_msg:
                current_msg["text"] += "\n" + line
                current_msg["raw"] += "\n" + line
            else:
                # Fallback for orphaned lines (though shouldn't happen with our append logic)
                messages.append({
                    "icon": "❓",
                    "label": "System",
                    "text": line,
                    "raw": line
                })
    
    if current_msg:
        messages.append(current_msg)
        
    return messages

def delete_task(task_id: str):
    get_db().table("tasks").delete().eq("id", task_id).execute()


def delete_all_tasks():
    get_db().table("tasks").delete().neq("id", "0").execute()