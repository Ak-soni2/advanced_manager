# 🎤 Automated Task Manager

**Automated Task Manager** is a high-performance, AI-driven task management system designed to sit between your meetings and your engineering workflow. It uses **Large Language Models (LLMs)** to ingest meeting transcripts, extract actionable technical tasks, and synchronize them directly with your developer dashboards and GitHub repositories. It also helps to evaluate the performance of the developers based on the tasks assigned to them and their github actions.

---

## 🚀 Key Features

### 🧠 1. AI-Powered Task Extraction
- **Zero Manual Input**: Paste a meeting transcript, and Automated Task Manager automatically identifies action items, assignees, deadlines, and priorities.
- **Contextual Reasoning**: Each task comes with an **AI Reasoning** block explaining *why* it was extracted (helping managers validate the task).
- **Calendar Logic**: AI understands relative dates like "tomorrow," "next Friday," or "EOD" and converts them to precise `YYYY-MM-DD` deadlines.

### 🔍 2. The Gatekeeper: Review Queue
- **High-Confidence Filtering**: Tasks with names and clear instructions are pre-assigned.
- **Low-Confidence Flags**: Vague tasks (e.g., "we should improve speed") are flagged for manual manager review before appearing on developer boards.
- **Dynamic Assignee Suggestions**: If the AI detects a name not in your system, it offers a "One-Click Profile Create" button for the new developer.

### 📈 3. Goal-Oriented Developer Dashboard
- **Role-Based Views**: Developers see only the tasks assigned to them, keeping them focused.
- **Automated Progression**: Tasks move seamlessly from **To Do** → **In Progress** → **Done**.
- **Performance Evaluation**: A detailed analytics tab tracks completion rates and task confidence to evaluate developer performance over time.

### 💬 4. WhatsApp-Style Interactive @Mentions
- **Threaded Communication**: Every task has its own chat history, keeping discussions context-specific.
- **Smart Mentions**: Type `@` anywhere in a note to trigger a real-time team member selection list.
- **Reply Popover**: A dedicated "Fast-Reply" button allows for quick updates without opening complex forms.

### 🐙 5. GitHub Synchronization
- **One-Click Pushes**: Managers can push confirmed tasks as **GitHub Issues** in a single click.
- **Automated Status Tracking**: Automated Task Manager syncs with your repo periodically to see if an issue has been closed or commented on, updating the Automated Task Manager status automatically.

---

## 🔄 Project Workflow

### 1. The Intake
A **Manager** uploads a meeting transcript (e.g., from Zoom, Teams, or Otter.ai) into the "Upload" tab. The system processes the text using **Qwen-2.5-7B** (via HuggingFace Inference API).

### 2. The Review
Tasks appear in the **Review Queue**. 
- The Manager can edit descriptions, adjust priorities, or re-assign tasks.
- If the AI was 90% confident, the task is already filled out. If 30%, it requires manual tweak.

### 3. The Assignment (Confirmation)
Once "Confirmed," the task is moved to the developer's board.
- **Statuses**: 
    - `pending_review`: AI extracted but not yet approved by Manager.
    - `confirmed`: Approved and waiting in the developer's "To Do" list.
    - `in_progress`: Developer is currently working on it.
    - `done`: Task is completed.
    - `rejected`: Manager decided not to proceed.

### 4. The Collaboration
Developers and Managers communicate via **Threaded Notes**.
- Use `@manager1` to ask a question.
- Use `@akshay` to give direction.

### 5. Finalization
Manager marks the task as **Done** or pushes it to **GitHub**. 

---

## 📂 File Structure & Usage

### ⚙️ Core System
- **`app.py`**: The central brain. Handles Auth-gating, Sidebar navigation, and Route switching between Manager and Developer views.
- **`database.py`**: Manages the connection to **Supabase (PostgreSQL)**. 
- **`auth.py`**: Handles user login, registration, and permission levels.

### 🛠️ Services (Logic Layer)
- **`services/extractor.py`**: Contains the **LangChain** prompt engineering and LLM logic for parsing transcripts.
- **`services/task_manager.py`**: Performs all database CRUD operations (Create, Read, Update, Delete) for tasks and meetings.
- **`services/github_sync.py`**: Connects to the **GitHub REST API** via PyGithub to manage issues and track sync status.
- **`services/help_service.py`**: Powers the **AI Sidebar Assistant** which helps managers find data or execute commands via natural language.

### 🖥️ Views (Presentation Layer)
- **`views/manager_dashboard.py`**: A complex UI with Upload, Review, and Global Task management. 
- **`views/developer_dashboard.py`**: A streamlined UI focused on focused execution and threaded chat.

---

## 🗄️ Database Setup (Supabase)

To set up the database, run the queries provided in **[`SCHEMA.sql`]** in your Supabase SQL Editor. 

### Core Tables:
- **`users`**: Login credentials and role (`manager` or `developer`).
- **`meetings`**: Stores the raw transcripts for historical reference.
- **`tasks`**: The central table tracking description, assignee, status, priority, and chat threads.

---

## 🛠️ Installation & Setup

1. **Clone the Repo**: 
   ```bash
   git clone <repo_url>
   cd automated_manager
   ```
2. **Install Dependencies**:
   ```bash
   pip install streamlit supabase langchain-huggingface python-dotenv PyGithub
   ```
3. **Environment Variables**:
   Create a `.env` file with:
   ```bash
   SUPABASE_URL=...
   SUPABASE_KEY=...
   HF_TOKEN=...       # HuggingFace API Token
   GITHUB_TOKEN=...   # GitHub Personal Access Token of manager github account
   GITHUB_REPO=...    # Format: username/repo-name
   ```
4. **Run the App**:
   ```bash
   streamlit run app.py
   ```

---

*Built with ❤️ for Engineering Managers who hate manual task entry.*