import os
import sqlite3
import sys
from datetime import datetime

import keyring

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(BASE_DIR, "data")
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
KB_SOURCE_DIR = os.path.join(KB_DIR, "sources")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(KB_DIR, exist_ok=True)
os.makedirs(KB_SOURCE_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "platform.db")
AZURE_OPENAI_API_VERSION = "2024-10-21"

CREDENTIAL_SERVICE = "AIPlatform"
STORED_KEY_PLACEHOLDER = "__keyring__"


def _cred_key_name(provider_name: str) -> str:
    return f"provider_api_key_{provider_name}"


def _save_api_key_secure(provider_name: str, api_key: str) -> None:
    try:
        keyring.set_password(CREDENTIAL_SERVICE, _cred_key_name(provider_name), api_key)
    except Exception:
        pass


def _get_api_key_secure(provider_name: str) -> str | None:
    try:
        return keyring.get_password(CREDENTIAL_SERVICE, _cred_key_name(provider_name))
    except Exception:
        return None


def _resolve_provider_key(provider_row):
    row = list(provider_row)
    raw_key = row[4]
    if raw_key == STORED_KEY_PLACEHOLDER:
        secure_key = _get_api_key_secure(row[1])
        if secure_key:
            row[4] = secure_key
    return tuple(row)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS api_providers
           (id INTEGER PRIMARY KEY,
            name TEXT,
            api_type TEXT,
            base_url TEXT,
            api_key TEXT,
            model TEXT,
            enabled INTEGER DEFAULT 1)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS users
           (id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            email TEXT,
            created_at TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS conversations
           (id INTEGER PRIMARY KEY,
            user_id INTEGER,
            project_id INTEGER,
            title TEXT,
            created_at TEXT)"""
    )
    c.execute("PRAGMA table_info(conversations)")
    existing_conv_columns = {row[1] for row in c.fetchall()}
    if "project_id" not in existing_conv_columns:
        c.execute("ALTER TABLE conversations ADD COLUMN project_id INTEGER")
    c.execute(
        """CREATE TABLE IF NOT EXISTS messages
           (id INTEGER PRIMARY KEY,
            conversation_id INTEGER,
            role TEXT,
            content TEXT,
            created_at TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS knowledge_docs
           (id INTEGER PRIMARY KEY,
            filename TEXT,
            content TEXT,
            uploaded_at TEXT)"""
    )
    c.execute("PRAGMA table_info(knowledge_docs)")
    existing_knowledge_columns = {row[1] for row in c.fetchall()}
    knowledge_columns = {
        "source_path": "TEXT",
        "chunk_count": "INTEGER DEFAULT 0",
        "vector_status": "TEXT DEFAULT 'pending'",
        "vectorized_at": "TEXT",
    }
    for column_name, column_type in knowledge_columns.items():
        if column_name not in existing_knowledge_columns:
            c.execute(f"ALTER TABLE knowledge_docs ADD COLUMN {column_name} {column_type}")
    c.execute(
        """CREATE TABLE IF NOT EXISTS settings
           (key TEXT PRIMARY KEY,
            value TEXT)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS user_projects
           (id INTEGER PRIMARY KEY,
            user_id INTEGER,
            name TEXT,
            folder_path TEXT,
            created_at TEXT,
            UNIQUE(user_id, folder_path))"""
    )
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def save_setting(key: str, value: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_providers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM api_providers ORDER BY enabled DESC, id DESC")
    providers = c.fetchall()
    conn.close()
    return [_resolve_provider_key(p) for p in providers]


def get_provider_by_id(provider_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM api_providers WHERE id = ?", (provider_id,))
    provider = c.fetchone()
    conn.close()
    return _resolve_provider_key(provider) if provider else None


def get_provider_by_name(name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM api_providers WHERE name = ?", (name,))
    provider = c.fetchone()
    conn.close()
    return _resolve_provider_key(provider) if provider else None


def get_active_provider():
    active_provider_id = get_setting("active_provider_id", "").strip()
    if active_provider_id.isdigit():
        provider = get_provider_by_id(int(active_provider_id))
        if provider:
            return provider

    providers = get_providers()
    if providers:
        return providers[0]
    return None


def set_active_provider(provider_id: int) -> None:
    save_setting("active_provider_id", str(provider_id))


def save_provider_record(name: str, api_type: str, base_url: str, api_key: str, model: str) -> int:
    _save_api_key_secure(name, api_key)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM api_providers WHERE name = ?", (name,))
    existing = c.fetchone()

    if existing:
        provider_id = existing[0]
        c.execute(
            """UPDATE api_providers
               SET api_type = ?, base_url = ?, api_key = ?, model = ?, enabled = 1
               WHERE id = ?""",
            (api_type, base_url, STORED_KEY_PLACEHOLDER, model, provider_id),
        )
    else:
        c.execute(
            """INSERT INTO api_providers (name, api_type, base_url, api_key, model, enabled)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (name, api_type, base_url, STORED_KEY_PLACEHOLDER, model),
        )
        provider_id = c.lastrowid

    conn.commit()
    conn.close()
    set_active_provider(provider_id)
    return provider_id


def delete_provider(provider_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM api_providers WHERE id = ?", (provider_id,))
    conn.commit()
    conn.close()

    active_provider = get_setting("active_provider_id", "")
    if active_provider == str(provider_id):
        providers = get_providers()
        if providers:
            set_active_provider(providers[0][0])
        else:
            save_setting("active_provider_id", "")


def get_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    users = c.fetchall()
    conn.close()
    return users


def add_user(username: str, email: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (username, email, created_at) VALUES (?, ?, ?)",
        (username, email, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def delete_user(user_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    c.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_projects(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM user_projects WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    projects = c.fetchall()
    conn.close()
    return projects


def add_project_folder(user_id: int, folder_path: str) -> int:
    normalized_path = os.path.normpath(folder_path)
    project_name = os.path.basename(normalized_path.rstrip("\\/")) or normalized_path

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO user_projects (user_id, name, folder_path, created_at)
           VALUES (?, ?, ?, ?)""",
        (user_id, project_name, normalized_path, datetime.now().isoformat()),
    )
    project_id = c.lastrowid
    conn.commit()
    conn.close()
    return project_id


def get_conversations(user_id: int, project_id: int | None = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = (
        "SELECT id, user_id, title, created_at, project_id "
        "FROM conversations WHERE user_id = ?"
    )
    if project_id is not None:
        c.execute(f"{query} AND project_id = ? ORDER BY created_at DESC", (user_id, project_id))
    else:
        c.execute(f"{query} AND project_id IS NULL ORDER BY created_at DESC", (user_id,))
    convs = c.fetchall()
    conn.close()
    return convs


def create_conversation(user_id: int, title: str, project_id: int | None = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (user_id, project_id, title, created_at) VALUES (?, ?, ?, ?)",
        (user_id, project_id, title, datetime.now().isoformat()),
    )
    conv_id = c.lastrowid
    conn.commit()
    conn.close()
    return conv_id


def delete_conversation(conv_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()


def save_message(conversation_id: int, role: str, content: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conversation_id, role, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_messages(conversation_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at",
        (conversation_id,),
    )
    msgs = c.fetchall()
    conn.close()
    return msgs


def get_knowledge_docs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM knowledge_docs ORDER BY uploaded_at DESC")
    docs = c.fetchall()
    conn.close()
    return docs


def save_knowledge_doc(filename: str, content: str, source_path: str = "") -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT INTO knowledge_docs
           (filename, content, uploaded_at, source_path, chunk_count, vector_status)
           VALUES (?, ?, ?, ?, 0, 'pending')""",
        (filename, content, datetime.now().isoformat(), source_path),
    )
    doc_id = c.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def update_knowledge_vector_status(doc_id: int, chunk_count: int, status: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """UPDATE knowledge_docs
           SET chunk_count = ?, vector_status = ?, vectorized_at = ?
           WHERE id = ?""",
        (chunk_count, status, datetime.now().isoformat(), doc_id),
    )
    conn.commit()
    conn.close()


def delete_knowledge_doc(doc_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM knowledge_docs WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()
