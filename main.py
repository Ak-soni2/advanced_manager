"""
main.py - FastAPI Backend for Automated Task Manager
Provides REST API endpoints consumed by the Next.js frontend.
"""

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import hashlib
import os

from database import get_db
from services.task_manager import (
    get_all_tasks_for_manager,
    get_tasks_for_developer,
    get_stats_for_manager,
    get_stats_for_developer,
    get_leaderboard_matrix,
    get_meetings,
    save_meeting,
    save_extracted_tasks,
    confirm_and_assign,
    reject_task,
    developer_update_task,
    append_task_note,
    parse_thread_history,
    delete_task,
    get_pending_tasks,
    manager_update_task,
)
from services.github_sync import create_github_issue, sync_github_issue_statuses
from services.extractor import infer_task_status_from_note

app = FastAPI(title="Automated Task Manager Manager OS API", version="1.0.0")

# ── CORS ────────────────────────────────────────────────────────────────────
FRONTEND_ORIGIN = os.getenv("FRONTEND_URL", "http://localhost:3000")
EXTRA_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ADDITIONAL_ALLOWED_ORIGINS", "").split(",") if o.strip()
]

ALLOWED_ORIGINS = [
    FRONTEND_ORIGIN,
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8000",
    "https://advanced-manager-ui.vercel.app",
    "http://172.31.112.12:3000",
    "http://172.31.112.12",
    *EXTRA_ALLOWED_ORIGINS,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Models ──────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class SignupRequest(BaseModel):
    username: str
    password: str
    github_handle: str

class TaskUpdateRequest(BaseModel):
    description: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[str] = None
    assigned_to: Optional[str] = None
    assignees_list: Optional[List[str]] = None
    manager_notes: Optional[str] = None
    status: Optional[str] = None

class ConfirmTaskRequest(BaseModel):
    assigned_to: str
    description: str
    priority: str
    deadline: Optional[str] = None
    manager_notes: Optional[str] = None
    assignees_list: Optional[List[str]] = None

class UpdateTaskStatusRequest(BaseModel):
    status: str
    notes: Optional[str] = None

class AppendNoteRequest(BaseModel):
    note_text: str
    sender_icon: str
    sender_label: str

class MeetingUploadRequest(BaseModel):
    title: str
    transcript: str
    uploaded_by: str
    attendees: List[str] = []

class ExtractTasksRequest(BaseModel):
    meeting_id: str
    transcript: str

class GitHubSyncRequest(BaseModel):
    task_id: str
    assignee_github_handle: Optional[str] = None

class CreateDeveloperRequest(BaseModel):
    username: str
    github_handle: Optional[str] = None

class AISuggestStatusRequest(BaseModel):
    note: Optional[str] = None


class HelpQueryRequest(BaseModel):
    question: str
    mode: Optional[str] = "question"


# ── Auth Helpers ─────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user(x_user_id: str = Header(None), x_user_role: str = Header(None)):
    """Simple header-based auth. Frontend sends X-User-Id and X-User-Role."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": x_user_id, "role": x_user_role}


def require_manager(user=Depends(get_current_user)):
    if user["role"] != "manager":
        raise HTTPException(status_code=403, detail="Manager access required")
    return user


# ── Auth Routes ──────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    db = get_db()
    result = (
        db.table("users")
        .select("*")
        .eq("username", req.username)
        .eq("password_hash", _hash(req.password))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user = result.data[0] if isinstance(result.data, list) else result.data
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "github_handle": user.get("github_handle"),
    }


@app.post("/api/auth/signup")
async def signup(req: SignupRequest):
    try:
        db = get_db()
        db.table("users").insert({
            "username": req.username,
            "password_hash": _hash(req.password),
            "role": "developer",
            "github_handle": req.github_handle,
        }).execute()
        return {"success": True, "message": "Account created successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/auth/developers")
async def get_developers(user=Depends(require_manager)):
    db = get_db()
    result = (
        db.table("users")
        .select("id, username, github_handle")
        .eq("role", "developer")
        .order("username")
        .execute()
    )
    return result.data or []


@app.post("/api/auth/create-developer")
async def create_developer(req: CreateDeveloperRequest, user=Depends(require_manager)):
    try:
        db = get_db()
        db.table("users").insert({
            "username": req.username,
            "password_hash": _hash("dev123"),
            "role": "developer",
            "github_handle": req.github_handle,
        }).execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Stats Routes ─────────────────────────────────────────────────────────────

@app.get("/api/stats/manager")
async def manager_stats(user=Depends(require_manager)):
    return get_stats_for_manager()


@app.get("/api/stats/developer/{user_id}")
async def developer_stats(user_id: str, user=Depends(get_current_user)):
    return get_stats_for_developer(user_id)


@app.get("/api/stats/leaderboard")
async def leaderboard_stats(user=Depends(get_current_user)):
    return get_leaderboard_matrix()


@app.get("/api/leaderboard")
async def leaderboard(user=Depends(get_current_user)):
    return get_leaderboard_matrix()


# ── Meeting Routes ────────────────────────────────────────────────────────────

@app.get("/api/meetings")
async def list_meetings(user=Depends(get_current_user)):
    return get_meetings()


@app.post("/api/meetings/upload")
async def upload_meeting(req: MeetingUploadRequest, user=Depends(require_manager)):
    meeting_id = save_meeting(req.title, req.transcript, req.uploaded_by, req.attendees)
    return {"success": True, "meeting_id": meeting_id}


@app.post("/api/meetings/extract")
async def extract_tasks(req: ExtractTasksRequest, user=Depends(require_manager)):
    """Runs AI extraction (slow — up to 30s). Called after meeting upload."""
    from services.extractor import extract_tasks_and_attendees
    tasks, attendees = extract_tasks_and_attendees(req.transcript)
    if tasks:
        save_extracted_tasks(req.meeting_id, tasks)
    return {"tasks_extracted": len(tasks), "attendees": attendees, "tasks": tasks}


# ── Task Routes ───────────────────────────────────────────────────────────────

@app.get("/api/tasks/pending")
async def pending_tasks(user=Depends(require_manager)):
    return get_pending_tasks()


@app.get("/api/tasks/manager")
async def all_tasks_manager(
    status: Optional[str] = None,
    meeting_id: Optional[str] = None,
    user=Depends(require_manager),
):
    status_filter = [status] if status else None
    return get_all_tasks_for_manager(status_filter, meeting_id)


@app.get("/api/tasks/developer/{user_id}")
async def tasks_for_developer(user_id: str, user=Depends(get_current_user)):
    return get_tasks_for_developer(user_id)


@app.put("/api/tasks/{task_id}")
async def update_task_fully(task_id: str, req: TaskUpdateRequest, user=Depends(require_manager)):
    """Full task update for managers."""
    updates = req.dict(exclude_unset=True)
    manager_update_task(task_id, updates)
    return {"success": True}


@app.post("/api/tasks/{task_id}/confirm")
async def confirm_task(task_id: str, req: ConfirmTaskRequest, user=Depends(require_manager)):
    confirm_and_assign(
        task_id=task_id,
        assigned_to=req.assigned_to,
        description=req.description,
        priority=req.priority,
        deadline=req.deadline,
        manager_notes=req.manager_notes,
        assignees_list=req.assignees_list,
    )
    return {"success": True}


@app.post("/api/tasks/{task_id}/reject")
async def reject_task_route(task_id: str, user=Depends(require_manager)):
    reject_task(task_id)
    return {"success": True}


@app.patch("/api/tasks/{task_id}/status")
async def update_task_status(task_id: str, req: UpdateTaskStatusRequest, user=Depends(get_current_user)):
    updates = {"status": req.status}
    if req.notes:
        updates["dev_notes"] = req.notes
    developer_update_task(task_id, user["id"], updates)
    return {"success": True}


@app.post("/api/tasks/{task_id}/note")
async def append_note(task_id: str, req: AppendNoteRequest, user=Depends(get_current_user)):
    append_task_note(task_id, req.note_text, req.sender_icon, req.sender_label)
    return {"success": True}


@app.post("/api/tasks/{task_id}/ai-suggest-status")
async def ai_suggest_status(task_id: str, req: AISuggestStatusRequest, user=Depends(get_current_user)):
    db = get_db()
    result = (
        db.table("tasks")
        .select("id, assigned_to, assignees_list, status, manager_notes")
        .eq("id", task_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")

    task = result.data
    is_manager = user.get("role") == "manager"
    assignees = task.get("assignees_list") or []
    is_assigned = user.get("id") == task.get("assigned_to") or user.get("id") in assignees
    if not is_manager and not is_assigned:
        raise HTTPException(status_code=403, detail="Not allowed for this task")

    note = (req.note or "").strip()
    if not note:
        thread = parse_thread_history(task.get("manager_notes"))
        if thread:
            note = thread[-1].get("text", "").strip()

    if not note:
        raise HTTPException(status_code=400, detail="No thread note found to analyze")

    current_status = task.get("status") or "confirmed"
    suggested_status = infer_task_status_from_note(note, current_status)
    return {
        "current_status": current_status,
        "suggested_status": suggested_status,
        "changed": suggested_status != current_status,
        "based_on_note": note,
    }


@app.get("/api/tasks/{task_id}/thread")
async def get_thread(task_id: str, user=Depends(get_current_user)):
    db = get_db()
    result = db.table("tasks").select("manager_notes").eq("id", task_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    thread = parse_thread_history(result.data.get("manager_notes"))
    return {"thread": thread}


@app.delete("/api/tasks/{task_id}")
async def delete_task_route(task_id: str, user=Depends(require_manager)):
    delete_task(task_id)
    return {"success": True}


# ── AI Sidebar Assistant ─────────────────────────────────────────────────────

@app.post("/api/help/query")
async def help_query(req: HelpQueryRequest, user=Depends(get_current_user)):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    mode = (req.mode or "question").strip().lower()
    if mode not in ("question", "command"):
        raise HTTPException(status_code=400, detail="Invalid mode")

    # Lazily initialize services so startup is lightweight and fallback still works
    from services.help_service import HelpService

    agent = None
    if os.getenv("HF_TOKEN"):
        try:
            from services.agent_service import AgentService
            agent = AgentService(user=user)
        except Exception:
            agent = None

    helper = HelpService(agent)
    response = helper.get_response(question, mode=mode, user=user)
    return {"response": response, "mode": mode}


# ── GitHub Sync ───────────────────────────────────────────────────────────────

@app.post("/api/tasks/{task_id}/github-sync")
async def github_sync(task_id: str, req: GitHubSyncRequest, user=Depends(get_current_user)):
    db = get_db()
    result = db.table("tasks").select("*, meetings(title, attendees)").eq("id", task_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Task not found")
    task = result.data

    is_manager = user.get("role") == "manager"
    assignees = task.get("assignees_list") or []
    is_assigned = user.get("id") == task.get("assigned_to") or user.get("id") in assignees
    if not is_manager and not is_assigned:
        raise HTTPException(status_code=403, detail="Not allowed for this task")

    assignee_handle = req.assignee_github_handle
    if not assignee_handle and task.get("assigned_to"):
        assignee_user = (
            db.table("users")
            .select("github_handle")
            .eq("id", task.get("assigned_to"))
            .maybe_single()
            .execute()
        )
        assignee_handle = (assignee_user.data or {}).get("github_handle")

    url = create_github_issue(task, assignee_handle)
    if url and url.startswith("ERROR"):
        raise HTTPException(status_code=400, detail=url)
    return {"github_issue_url": url}


@app.post("/api/tasks/github-sync-all")
async def github_sync_all(user=Depends(require_manager)):
    db = get_db()
    tasks = get_all_tasks_for_manager()
    created = 0
    failed = 0
    failed_details = []

    for task in tasks:
        if task.get("status") in ("rejected", "pending_review"):
            continue
        if task.get("github_issue_url"):
            continue

        assignee_handle = None
        if task.get("assigned_to"):
            assignee_user = (
                db.table("users")
                .select("github_handle")
                .eq("id", task.get("assigned_to"))
                .maybe_single()
                .execute()
            )
            assignee_handle = (assignee_user.data or {}).get("github_handle")

        url = create_github_issue(task, assignee_handle)
        if url and not str(url).startswith("ERROR"):
            created += 1
        else:
            failed += 1
            failed_details.append({
                "task_id": task.get("id"),
                "description": task.get("description", "Untitled task"),
                "error": str(url or "Unknown GitHub error"),
            })

    sync_github_issue_statuses(get_all_tasks_for_manager(), notify=False)
    return {"success": True, "created": created, "failed": failed, "failed_details": failed_details}


@app.post("/api/tasks/developer/{user_id}/github-sync-all")
async def github_sync_all_for_developer(user_id: str, user=Depends(get_current_user)):
    if user.get("role") != "manager" and user.get("id") != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    db = get_db()
    tasks = get_tasks_for_developer(user_id)
    created = 0
    failed = 0
    failed_details = []

    assignee_user = (
        db.table("users")
        .select("github_handle")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    assignee_handle = (assignee_user.data or {}).get("github_handle")

    for task in tasks:
        if task.get("status") in ("rejected", "pending_review"):
            continue
        if task.get("github_issue_url"):
            continue

        url = create_github_issue(task, assignee_handle)
        if url and not str(url).startswith("ERROR"):
            created += 1
        else:
            failed += 1
            failed_details.append({
                "task_id": task.get("id"),
                "description": task.get("description", "Untitled task"),
                "error": str(url or "Unknown GitHub error"),
            })

    sync_github_issue_statuses(get_all_tasks_for_manager(), notify=False)
    return {"success": True, "created": created, "failed": failed, "failed_details": failed_details}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
