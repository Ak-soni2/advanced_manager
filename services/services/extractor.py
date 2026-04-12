"""
services/extractor.py
---------------------
LangChain + HuggingFace task extraction from meeting transcripts.

Model choice (swap MODEL_ID to change):
  "Qwen/Qwen2.5-7B-Instruct"                 ← default, best JSON adherence on HF free tier
  "mistralai/Mistral-7B-Instruct-v0.3"        ← reliable fallback
  "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"  ← stronger reasoning, slower
  "meta-llama/Llama-3.1-8B-Instruct"         ← great quality, needs HF access grant
  "google/gemma-2-9b-it"                      ← solid alternative

All run FREE on HuggingFace Serverless Inference API.
DeepSeek-V3 / V3.2 (685B params) is NOT available on HF free tier.
"""

import os, json, re
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import Optional

load_dotenv()

# ── Swap this one line to change the model ───────────────────────────
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

class ExtractedTask(BaseModel):
    description:  str           = Field(description="Clear actionable task in 1-2 sentences")
    raw_assignees: list[str]    = Field(default_factory=list, description="List of exact names from transcript, or empty list")
    confidence:   int           = Field(description="0-100 score — how certain is the assignment")
    priority:     str           = Field(description="high | medium | low")
    deadline:     Optional[str] = Field(None, description="Deadline strictly formatted as YYYY-MM-DD. Use the {current_date} to calculate relative days (e.g., 'this Friday'). If no deadline is found, return null. NEVER guess a year or month if not implied. E.g. 'EOD' must evaluate exactly to this context's {current_date}. 'Tomorrow' is {current_date} + 1 day. 'Next Monday' must be the upcoming Monday.")
    reasoning:    str           = Field(description="Brief explanation of why this was identified as a task and how the deadline was calculated.")

class MeetingExtraction(BaseModel):
    attendees: list[str] = Field(description="List of all unique people present or mentioned as participating in the meeting")
    tasks: list[ExtractedTask]

parser = PydanticOutputParser(pydantic_object=MeetingExtraction)

# ── Prompt ──
PROMPT = ChatPromptTemplate.from_messages([
    ("human", """You are an expert meeting analyst for a software engineering team.

Read the meeting transcript and extract EVERY actionable task you can find.

{format_instructions}

CONFIDENCE RULES (be strict):
- 90-100: Explicit name(s) + clear task + deadline  e.g. "Akshay and Priya will fix auth by Friday"
- 70-89 : Named person(s) + clear task, no deadline  e.g. "Priya should update docs"
- 50-69 : Task clear, owner only implied           e.g. "backend team should fix this"
- 0-49  : Vague or mentioned in passing            e.g. "we should improve performance"

PRIORITY RULES (Base your calculation on today's date: {current_date}):
- high   : Within 1-2 days of {current_date}, OR "EOD", "end of day", "production", "urgent".
- medium : 3 to 7 days away from {current_date}.
- low    : More than 7 days away, or nice-to-have.

STRICT CALENDAR LOGIC:
- Today is: {current_date}.
- ANY relative timeframe (today, tomorrow, next week, Friday, Weekday, Weekend, EOD) MUST be converted to an absolute date in `YYYY-MM-DD` format.
- "EOD" or "Today" is ALWAYS {current_date}.
- "Tomorrow" is ALWAYS {current_date} + 1 day.
- If a day of the week is mentioned (e.g. "by Friday"), calculate the date of the NEXT occurrence of that day relative to {current_date}.
- ANY suggested deadline MUST be >= {current_date}. 
- IMPORTANT: If a task mentions a timeframe like "in 2 weeks", calculate the exact date.
- Return ONLY the JSON object. No markdown fences. No preamble. No conversational filler.

TRANSCRIPT:
{transcript}""")
])

# We don't partial it immediately because current_date is dynamic
# We will inject format_instructions and current_date at runtime.

# ── LangChain LLM ────────────────────────────────────────────────────
def _build_llm():
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not found in environment")
    endpoint = HuggingFaceEndpoint(
        repo_id=MODEL_ID,
        huggingfacehub_api_token=token,
        max_new_tokens=2048,
        temperature=0.05,
        repetition_penalty=1.1,
        task="conversational",
    )
    return ChatHuggingFace(llm=endpoint)

_chain = None

def _get_chain():
    global _chain
    if _chain is None:
        _chain = PROMPT | _build_llm()
    return _chain


# ── Public API ───────────────────────────────────────────────────────
def extract_tasks_and_attendees(transcript: str) -> tuple[list[dict], list[str]]:
    """
    Returns (tasks_list, attendees_list) ready to insert into Supabase.
    Falls back to ([], []) on any failure — never raises.
    """
    from datetime import datetime
    current_date = datetime.now().strftime("%B %d, %Y")
    
    try:
        # Build prompt at runtime to ensure fresh date
        prompt = PROMPT.partial(
            format_instructions=parser.get_format_instructions(),
            current_date=current_date
        )
        chain = prompt | _build_llm()
        result = chain.invoke({"transcript": transcript})
        raw = result.content if hasattr(result, "content") else str(result)

        # Strip markdown fences if model adds them
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()

        # Find the outermost JSON object even if model adds preamble text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return [], []

        try:
            extraction = parser.parse(match.group())
            return [t.model_dump() for t in extraction.tasks], extraction.attendees
        except Exception:
            # Graceful fallback: try raw json.loads
            data = json.loads(match.group())
            return data.get("tasks", []), data.get("attendees", [])

    except Exception as e:
        print(f"[extractor] extract_tasks_and_attendees failed: {e}")
        return [], []


def infer_task_status_from_note(note: str, current_status: str) -> str:
    """Uses LLM to infer if a note implies a status shift."""
    prompt = ChatPromptTemplate.from_messages([
        ("human", "A developer commented on a task: '{note}'\n\nThe current status is '{status}'. \n\nBased on their comment, what should the new status be? Must be exactly one of: 'confirmed', 'in_progress', 'done'.\n\nIf they say they finished, hit done. If they started, hit in_progress. Otherwise keep current status. Reply with ONLY the status word.")
    ])
    chain = prompt | _build_llm()
    try:
        res = chain.invoke({"note": note, "status": current_status})
        text = res.content.lower() if hasattr(res, "content") else str(res).lower()
        if "done" in text: return "done"
        if "in_progress" in text or "progress" in text: return "in_progress"
        return current_status
    except:
        return current_status