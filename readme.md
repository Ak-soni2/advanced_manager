# Automated Task Manager Backend

Backend service for Automated Task Manager. This service powers authentication, meeting transcript extraction, task lifecycle operations, AI assistant responses, GitHub issue sync, and leaderboard analytics.

## What This Backend Does

- Exposes a FastAPI REST API for manager and developer dashboards.
- Stores and reads data from Supabase PostgreSQL tables.
- Converts transcript text into structured tasks using LLM extraction.
- Supports threaded collaboration notes per task.
- Suggests status transitions from thread context using AI heuristics.
- Pushes tasks to GitHub Issues and syncs issue state.
- Serves a cross-team developer leaderboard matrix.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- Supabase Python client
- LangChain + HuggingFace Inference API (Qwen)
- PyGithub

## High-Level Architecture

1. Frontend sends requests with `X-User-Id` and `X-User-Role` headers.
2. FastAPI auth guards validate role access (`get_current_user`, `require_manager`).
3. Routes call service-layer modules (`task_manager`, `extractor`, `github_sync`, `help_service`).
4. Service layer reads/writes Supabase and returns normalized response objects.

## Core Backend Modules

- `main.py`
  - Route definitions and auth dependencies.
  - CORS policy and request model schemas.
- `database.py`
  - Supabase connection bootstrap.
- `services/task_manager.py`
  - Task/meeting CRUD.
  - Manager/developer stats.
  - Thread parsing and note appends.
  - Leaderboard matrix calculation.
- `services/extractor.py`
  - Transcript-to-task extraction.
  - Assignee/date/priority inference.
  - AI status suggestion helper from thread notes.
- `services/github_sync.py`
  - Creates issues and syncs issue state back to tasks.
- `services/help_service.py`
  - Q&A and command interpretation for sidebar assistant.
- `services/agent_service.py`
  - Tool-calling agent with role-scoped behavior.

## Database Model

Main tables used by backend:

- `users`
  - `id`, `username`, `password_hash`, `role`, `github_handle`
- `meetings`
  - `id`, `title`, `transcript`, `uploaded_by`, `attendees`, `created_at`
- `tasks`
  - `id`, `meeting_id`, `description`, `status`, `priority`, `deadline`
  - `assigned_to`, `assignees_list`, `raw_assignee`, `confidence`, `reasoning`
  - `manager_notes`, `github_issue_url`, timestamps

## Task Status State Machine

- `pending_review` -> created by AI extraction, awaiting manager review
- `confirmed` -> accepted/assigned by manager
- `in_progress` -> developer started execution
- `done` -> developer/manager marked complete or GitHub closed sync
- `rejected` -> manager rejected task

## Extraction Pipeline (Detailed)

1. Manager uploads transcript (`/api/meetings/upload`).
2. Manager triggers extraction (`/api/meetings/extract`).
3. Extractor prompts LLM to produce structured candidate tasks.
4. Backend normalizes fields:
   - description
  - assignee hints (`raw_assignee`)
   - confidence score
   - inferred priority
   - normalized deadline
5. Tasks are inserted as `pending_review` for manager confirmation.

## Leaderboard Formula

The leaderboard is generated in `task_manager.get_leaderboard_matrix()` and returned by:

- `GET /api/stats/leaderboard`
- `GET /api/leaderboard`

Per developer metrics:

- `total`
- `completed`
- `completion_rate`
- `github_linked`
- `avg_confidence`
- `overall_score`

Score formula:

`overall_score = (completion_rate * 0.5) + (github_linked * 5) + (avg_confidence * 0.2)`

## AI Assistant Behavior

Sidebar assistant endpoint:

- `POST /api/help/query`

Modes:

- `question` -> documentation-style help and workflow guidance
- `command` -> tool-backed data queries

Role isolation:

- Manager assistant can access manager-wide task insights.
- Developer assistant is restricted to developer-visible data and denies manager-only operations.

## Main API Surface

Auth:

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `GET /api/auth/developers` (manager)
- `POST /api/auth/create-developer` (manager)

Stats:

- `GET /api/stats/manager` (manager)
- `GET /api/stats/developer/{user_id}`
- `GET /api/stats/leaderboard`
- `GET /api/leaderboard`

Meetings:

- `GET /api/meetings`
- `POST /api/meetings/upload` (manager)
- `POST /api/meetings/extract` (manager)

Tasks:

- `GET /api/tasks/pending` (manager)
- `GET /api/tasks/manager` (manager)
- `GET /api/tasks/developer/{user_id}`
- `PUT /api/tasks/{task_id}` (manager)
- `POST /api/tasks/{task_id}/confirm` (manager)
- `POST /api/tasks/{task_id}/reject` (manager)
- `PATCH /api/tasks/{task_id}/status`
- `POST /api/tasks/{task_id}/note`
- `POST /api/tasks/{task_id}/ai-suggest-status`
- `GET /api/tasks/{task_id}/thread`
- `DELETE /api/tasks/{task_id}` (manager)

GitHub:

- `POST /api/tasks/{task_id}/github-sync`
- `POST /api/tasks/github-sync-all` (manager)
- `POST /api/tasks/developer/{user_id}/github-sync-all`

System:

- `GET /api/health`

## Environment Variables

Required:

- `SUPABASE_URL`
- `SUPABASE_KEY`

Optional/feature-based:

- `HF_TOKEN` (assistant/extraction model calls)
- `GITHUB_TOKEN`
- `GITHUB_REPO` (format: `owner/repo`)
- `FRONTEND_URL`
- `ADDITIONAL_ALLOWED_ORIGINS` (comma-separated list)

## Run Locally

From `backend/`:

```bash
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

## Notes

- CORS includes localhost and LAN origins for dev.
- Header-based auth is simple and intended for controlled internal use.
- If running from another machine/browser, bind Uvicorn to `0.0.0.0` and allow that frontend origin.
