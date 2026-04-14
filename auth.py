import hashlib
import streamlit as st
from database import get_db


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def login(username: str, password: str) -> dict | None:
    db = get_db()
    result = (
        db.table("users")
        .select("*")
        .eq("username", username)
        .eq("password_hash", _hash(password))
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0] if isinstance(result.data, list) else result.data

def signup(username: str, password: str, github_handle: str) -> bool:
    try:
        db = get_db()
        db.table("users").insert({
            "username": username,
            "password_hash": _hash(password),
            "role": "developer",
            "github_handle": github_handle
        }).execute()
        return True
    except Exception as e:
        st.error(f"Failed to create account: {e}")
        return False

def create_developer(username: str, github_handle: str = None) -> bool:
    """Manager-side creation — uses default password 'dev123'"""
    try:
        db = get_db()
        db.table("users").insert({
            "username": username,
            "password_hash": _hash("dev123"),
            "role": "developer",
            "github_handle": github_handle
        }).execute()
        return True
    except Exception as e:
        print(f"Failed to create developer: {e}")
        return False


def get_all_developers() -> list[dict]:
    db = get_db()
    result = (
        db.table("users")
        .select("id, username, github_handle")
        .eq("role", "developer")
        .order("username")
        .execute()
    )
    return result.data or []


def get_all_users() -> list[dict]:
    """Get all users for global @mentions"""
    db = get_db()
    result = (
        db.table("users")
        .select("id, username, role")
        .order("username")
        .execute()
    )
    return result.data or []


def require_login() -> dict:
    if not st.session_state.get("user"):
        st.title("🟠 Automated Task Manager Manager OS")
        st.caption("Meeting intelligence -> AI action planning -> Team execution")
        st.divider()

        tab_login, tab_signup = st.tabs(["🔑 Sign In", "📝 Create Account"])

        with tab_login:
            col_form, col_info = st.columns([1, 1])
            with col_form:
                st.subheader("Sign in")
                username = st.text_input("Username", key="login_un")
                password = st.text_input("Password", type="password", key="login_pw")

                if st.button("Sign in", type="primary", key="login_btn"):
                    user = login(username, password)
                    if user:
                        st.session_state.user = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password")

            with col_info:
                st.info(
                    "**How to start?**\n\n"
                    "If you are a manager, sign in with your credentials-  username: manager1, password: manager123.\n\n"
                    "If you are a developer, use the **Create Account** tab or ask your manager to add you."
                )

        with tab_signup:
            col_sform, col_sinfo = st.columns([1, 1])
            with col_sform:
                st.subheader("Sign up (Developer Only)")
                s_username = st.text_input("Choose Username", key="signup_un")
                s_password = st.text_input("Choose Password", type="password", key="signup_pw")
                s_github   = st.text_input("GitHub Username", placeholder="e.g. akshay-dev", key="signup_gh")

                if st.button("Create My Account", type="primary", key="signup_btn"):
                    if not s_username or not s_password or not s_github:
                        st.warning("All fields are required.")
                    else:
                        if signup(s_username, s_password, s_github):
                            st.success("Account created successfully! You can now Sign In.")
            with col_sinfo:
                st.info(
                    "💡 **Quick Setup**\n\n"
                    "Every developer account created will be automatically synced with the Manager's dashboard for task assignment."
                )

        st.stop()

    return st.session_state.user
