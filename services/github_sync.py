import os
from github import Github          # pip install PyGithub
from services.task_manager import manager_update_task

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME    = os.getenv("GITHUB_REPO")   # e.g. "your-org/your-repo"

def create_github_issue(task: dict, assignee_github_handle: str = None):
    if not GITHUB_TOKEN or not REPO_NAME:
        print("Warning: GITHUB_TOKEN or GITHUB_REPO not set. Skipping GitHub Issue creation.")
        return None

    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)

        priority_label = f"priority:{task['priority']}"
        labels = [priority_label] if priority_label in [l.name for l in repo.get_labels()] else []

        body = f"""
**From meeting:** {task.get('meeting_title', 'N/A')}
**Assigned via:** Automated Task Manager
**Manager notes:** {task.get('manager_notes') or 'None'}
**Deadline:** {task.get('deadline') or 'Not specified'}
        """.strip()

        issue = repo.create_issue(
            title=task["description"][:80],
            body=body,
            labels=labels,
            assignee=assignee_github_handle  # None = unassigned
        )
    except Exception as e:
        err_msg = str(e)
        if "Bad credentials" in err_msg:
            return "ERROR: Invalid GitHub Token in .env"
        if "Not Found" in err_msg:
            return f"ERROR: Repository '{REPO_NAME}' not found."
        return f"ERROR: {err_msg}"

    # Store the GitHub issue URL back in DB
    try:
        manager_update_task(task["id"], {"github_issue_url": issue.html_url})
        return issue.html_url
    except Exception as e:
        err_str = str(e).lower()
        if "column" in err_str and "not exist" in err_str:
            return "ERR_MISSING_COLUMN"
        return f"ERROR (DB): {str(e)}"

def sync_github_issue_statuses(tasks: list[dict], notify: bool = False):
    """
    Check GitHub for 'closed' status and update automated tasks to 'done'.
    """
    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPO")
    if not token or not repo_name:
        return
    
    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        
        for task in tasks:
            url = task.get("github_issue_url")
            if not url or task.get("status") in ("done", "rejected"):
                continue
                
            # Extract issue number from URL (e.g. .../issues/123)
            try:
                issue_number = int(url.split("/")[-1])
                issue = repo.get_issue(number=issue_number)
                
                if issue.state == "closed":
                    manager_update_task(task["id"], {"status": "done"})
                    if notify:
                        try:
                            import streamlit as st
                            st.toast(f"✅ GitHub Issue #{issue_number} was resolved! Task updated to DONE.", icon="🐙")
                        except Exception:
                            pass
            except Exception as e:
                print(f"Failed to sync issue {url}: {e}")
                
    except Exception as e:
        print(f"GitHub Sync Error: {e}")

    return True