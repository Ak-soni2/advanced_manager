"""
services/help_service.py
------------------------
Dual-mode help: question mode explains the UI, command mode uses the agent.
Adapted from the repo's HelpService pattern.
"""


KNOWLEDGE_BASE = """
# Automated Task Manager — Help

## What the app does
Automated Task Manager turns meeting transcripts into assigned tasks.
AI extracts tasks, managers review and assign them, developers track and update them.

## Roles
- **Manager**: uploads transcripts, reviews AI-extracted tasks, assigns to developers, can edit any task
- **Developer**: sees only their own tasks, moves them through To Do → In Progress → Done

## Manager workflow
1. Go to "Upload transcript" tab → paste transcript → click "Extract tasks with AI"
2. Go to "Review queue" tab → low-confidence tasks expand automatically
3. For each task: edit description, pick assignee, set priority/deadline → Confirm & assign
4. Use "All tasks" tab to edit any task at any time

## Developer workflow
1. Log in → see your assigned tasks grouped by status
2. Click "Start task" to move to In Progress
3. Click "Mark as done" when complete
4. Add notes at any time

## Confidence scores
- 🟢 70-100%: AI is very confident about task and assignee
- 🟡 40-69%: Task clear but assignee uncertain — review carefully
- 🔴 0-39%: Vague task or no assignee — needs your judgment

## Tips
- Tasks sorted lowest-confidence first in review queue
- Rejected tasks disappear from all views
- Managers can change status, priority, assignee on any task in "All tasks" tab
"""


class HelpService:
    def __init__(self, agent_service=None):
        self.agent = agent_service

    def get_response(self, question: str, mode: str = "question", user: dict | None = None) -> str:
        role = (user or {}).get("role", "developer")

        if mode == "command" and self.agent:
            try:
                return self.agent.invoke(question)
            except Exception as e:
                return f"Agent error: {e}. Try rephrasing."

        # Question mode — answer from knowledge base using the agent as LLM
        if self.agent:
            try:
                prompt = (
                    f"You are a helpful assistant for the Automated Task Manager app.\n\n"
                    f"CURRENT USER ROLE: {role}\n"
                    "You must obey role boundaries. Managers can review/reject/assign all tasks. "
                    "Developers can only see and work on their own assigned tasks. "
                    "Never provide manager-only queue data to developers.\n\n"
                    f"Use the following documentation to answer the user's question.\n\n"
                    f"DOCUMENTATION:\n{KNOWLEDGE_BASE}\n\n"
                    f"USER QUESTION: {question}\n\n"
                    f"Answer helpfully and concisely. If the question is about data "
                    f"(tasks, meetings, stats), say you can fetch that in Command Mode."
                )
                return self.agent.invoke(prompt)
            except Exception:
                pass

        # Fallback: keyword-based from knowledge base
        return self._kb_lookup(question, role)

    def _kb_lookup(self, question: str, role: str = "developer") -> str:
        q = question.lower()
        if any(w in q for w in ["reject", "rejection", "pending review"]):
            if role == "manager":
                return (
                    "Managers can reject tasks from the Pending Review queue. "
                    "Use the manager dashboard Pending Review tab to reject tasks."
                )
            return (
                "Task rejection is manager-only. As a developer, you can update your own task status and notes, "
                "but you cannot reject tasks or view pending-review queue items."
            )
        if any(w in q for w in ["confidence", "score", "percent"]):
            return (
                "Confidence scores show how certain the AI is:\n"
                "🟢 70-100%: High confidence\n"
                "🟡 40-69%: Medium — check the assignee\n"
                "🔴 0-39%: Low — needs your judgment"
            )
        if any(w in q for w in ["assign", "who", "developer"]):
            return (
                "In the Review queue, each task has an 'Assign to' dropdown. "
                "The AI pre-selects the best match based on names in the transcript. "
                "You can change it before confirming."
            )
        if any(w in q for w in ["upload", "transcript", "extract"]):
            return (
                "Go to the 'Upload transcript' tab, paste your meeting transcript, "
                "give it a title, and click 'Extract tasks with AI'."
            )
        if any(w in q for w in ["edit", "change", "update", "modify"]):
            return (
                "Managers: use the 'All tasks' tab → click 'Edit' on any task. "
                "Developers: click 'Add note' or use the status buttons on your task."
            )
        return (
            "I can help with:\n"
            "- How to upload transcripts\n"
            "- Understanding confidence scores\n"
            "- Assigning and editing tasks\n"
            "- Developer task workflow\n\n"
            "Switch to Command Mode to query live task data."
        )

    def get_contextual_suggestions(self, stats: dict) -> str:
        """Context-aware tip based on current task state — mirrors repo pattern."""
        if stats.get("pending_review", 0) > 0:
            return (
                f"You have **{stats['pending_review']} tasks** waiting in the review queue. "
                "Go to Review queue to confirm or reject them."
            )
        if stats.get("high", 0) > 0:
            return (
                f"**{stats['high']} high-priority tasks** are active. "
                "Check the All tasks tab filtered by priority."
            )
        if stats.get("in_progress", 0) > 0:
            return f"**{stats['in_progress']} tasks** are in progress across your team."
        return "All caught up! Upload a new meeting transcript to extract more tasks."