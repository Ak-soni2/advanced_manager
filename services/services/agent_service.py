"""
services/agent_service.py
--------------------------
LangGraph ReAct agent with LangChain tools — adapted directly from the repo's
AgentService pattern, but using HuggingFace instead of OpenAI.

LangChain provides: @tool decorators, PromptTemplate, output parsers.
LangGraph provides: create_react_agent — the ReAct loop (Reason → Act → Observe).

They are designed to work together. This is not unusual — LangGraph is the
orchestration layer built ON TOP of LangChain.
"""

import os, asyncio
from typing import Optional
from dotenv import load_dotenv

from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

load_dotenv()

# Qwen2.5 is the best free model on HF for tool calling / structured output.
# For the agent, we need a chat model that supports tool_calls in its response.
AGENT_MODEL = "Qwen/Qwen2.5-7B-Instruct"


def _build_llm():
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not set")
    endpoint = HuggingFaceEndpoint(
        repo_id=AGENT_MODEL,
        huggingfacehub_api_token=token,
        max_new_tokens=1024,
        temperature=0.1,
        task="conversational",
    )
    return ChatHuggingFace(llm=endpoint)


class AgentService:
    """
    Thin wrapper around a LangGraph ReAct agent with read-only task tools.
    Used by HelpService for the 'command' mode in the sidebar Q&A panel.

    Write operations (confirm, reject, assign) stay in the manager dashboard
    intentionally — the agent is for queries and summaries only, not mutations.
    That keeps the human-in-the-loop guarantee intact.
    """

    def __init__(self):
        self._agent = None  # lazy init

    def _get_agent(self):
        if self._agent is not None:
            return self._agent

        llm   = _build_llm()
        tools = self._build_tools()

        system_prompt = (
            "You are a helpful assistant for the Automated Task Manager app. "
            "Use the provided tools to answer questions about tasks and meetings. "
            "Always use tools to fetch real data — never make up task details. "
            "For write operations (assigning, rejecting, editing tasks), politely "
            "tell the user to use the manager dashboard directly."
        )
        self._agent = create_react_agent(llm, tools, prompt=system_prompt)
        return self._agent

    # ── Tools (mirrors repo tool pattern with @tool decorator) ───────

    def _build_tools(self):

        @tool
        def list_all_tasks(status: str = "all") -> str:
            """
            List tasks from the database.
            status: 'all' | 'pending_review' | 'confirmed' | 'in_progress' | 'done'
            Returns a formatted task list with IDs, assignees, priorities, and status.
            """
            from services.task_manager import get_all_tasks_for_manager
            status_filter = None if status == "all" else [status]
            tasks = get_all_tasks_for_manager(status_filter)
            if not tasks:
                return f"No tasks found with status '{status}'."
            lines = [f"Found {len(tasks)} tasks:\n"]
            for i, t in enumerate(tasks, 1):
                lines.append(
                    f"{i}. [{t['status'].upper()}] {t['description'][:80]}\n"
                    f"   Assignee: {t['assigned_username'] or 'Unassigned'} | "
                    f"Priority: {t['priority']} | Deadline: {t.get('deadline') or 'None'}\n"
                    f"   Meeting: {t['meeting_title']}\n"
                )
            return "\n".join(lines)

        @tool
        def get_task_stats() -> str:
            """
            Get overall statistics — total tasks, breakdown by status and priority.
            Useful for questions like 'how many tasks are in progress?'
            """
            from services.task_manager import get_stats_for_manager
            s = get_stats_for_manager()
            return (
                f"Task statistics:\n"
                f"  Total: {s['total']}\n"
                f"  Pending review: {s['pending_review']}\n"
                f"  Confirmed (todo): {s['confirmed']}\n"
                f"  In progress: {s['in_progress']}\n"
                f"  Done: {s['done']}\n"
                f"  Rejected: {s['rejected']}\n\n"
                f"  High priority: {s['high']}\n"
                f"  Medium priority: {s['medium']}\n"
                f"  Low priority: {s['low']}\n"
            )

        @tool
        def list_tasks_by_priority(priority: str) -> str:
            """
            Filter tasks by priority level.
            priority: 'high' | 'medium' | 'low'
            """
            from services.task_manager import get_all_tasks_for_manager
            tasks = [
                t for t in get_all_tasks_for_manager()
                if t["priority"] == priority
            ]
            if not tasks:
                return f"No {priority} priority tasks found."
            lines = [f"{len(tasks)} {priority} priority tasks:\n"]
            for i, t in enumerate(tasks, 1):
                lines.append(
                    f"{i}. {t['description'][:80]} "
                    f"[{t['status']}] → {t['assigned_username'] or 'Unassigned'}"
                )
            return "\n".join(lines)

        @tool
        def list_tasks_for_developer(username: str) -> str:
            """
            List all tasks assigned to a specific developer.
            username: the developer's username (e.g. 'akshay', 'priya')
            """
            from services.task_manager import get_all_tasks_for_manager
            tasks = [
                t for t in get_all_tasks_for_manager()
                if (t.get("assigned_username") or "").lower() == username.lower()
            ]
            if not tasks:
                return f"No tasks found assigned to '{username}'."
            lines = [f"{len(tasks)} tasks for {username}:\n"]
            for i, t in enumerate(tasks, 1):
                lines.append(
                    f"{i}. [{t['status']}] {t['description'][:80]} "
                    f"| Priority: {t['priority']}"
                )
            return "\n".join(lines)

        @tool
        def list_meetings() -> str:
            """List all uploaded meeting transcripts."""
            from services.task_manager import get_meetings
            meetings = get_meetings()
            if not meetings:
                return "No meetings uploaded yet."
            lines = [f"{len(meetings)} meetings:\n"]
            for m in meetings:
                lines.append(f"- {m['title']} (uploaded: {m['created_at'][:10]})")
            return "\n".join(lines)

        return [
            list_all_tasks,
            get_task_stats,
            list_tasks_by_priority,
            list_tasks_for_developer,
            list_meetings,
        ]

    # ── Async invoke (mirrors repo process_request pattern) ──────────

    async def _invoke(self, user_input: str) -> str:
        agent = self._get_agent()
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": user_input}]
        })
        # Extract final AI text from message list (repo pattern)
        for msg in reversed(result.get("messages", [])):
            msg_type = getattr(msg, "type", None)
            if msg_type == "ai" and msg.content:
                return msg.content
        return "I couldn't find an answer to that."

    def invoke(self, user_input: str) -> str:
        """Sync wrapper for Streamlit compatibility (from repo process_request_sync)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._invoke(user_input))
        except Exception as e:
            return f"Agent error: {e}"
        finally:
            loop.close()