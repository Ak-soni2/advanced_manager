import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None

def get_db() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        _client = create_client(url, key)
    return _client


def init_db():
    """
    Run once at startup — verifies connection is alive.
    Actual schema lives in Supabase SQL editor (see README).
    """
    try:
        db = get_db()
        db.table("users").select("id").limit(1).execute()
    except Exception as e:
        import streamlit as st
        st.error(f"Database connection failed: {e}")
        st.stop()