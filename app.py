import json
import os
import sqlite3
from datetime import datetime

import customtkinter as ctk
import requests

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(KB_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "platform.db")
AZURE_OPENAI_API_VERSION = "2024-10-21"


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
            title TEXT,
            created_at TEXT)"""
    )
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


def get_setting(key, default=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default


def save_setting(key, value):
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
    return providers


def get_provider_by_id(provider_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM api_providers WHERE id = ?", (provider_id,))
    provider = c.fetchone()
    conn.close()
    return provider


def get_provider_by_name(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM api_providers WHERE name = ?", (name,))
    provider = c.fetchone()
    conn.close()
    return provider


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


def set_active_provider(provider_id):
    save_setting("active_provider_id", str(provider_id))


def save_provider_record(name, api_type, base_url, api_key, model):
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
            (api_type, base_url, api_key, model, provider_id),
        )
    else:
        c.execute(
            """INSERT INTO api_providers (name, api_type, base_url, api_key, model, enabled)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (name, api_type, base_url, api_key, model),
        )
        provider_id = c.lastrowid

    conn.commit()
    conn.close()
    set_active_provider(provider_id)
    return provider_id


def delete_provider(provider_id):
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


def add_user(username, email):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (username, email, created_at) VALUES (?, ?, ?)",
        (username, email, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    c.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM user_projects WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_projects(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM user_projects WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    projects = c.fetchall()
    conn.close()
    return projects


def add_project_folder(user_id, folder_path):
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


def get_conversations(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    convs = c.fetchall()
    conn.close()
    return convs


def create_conversation(user_id, title):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (user_id, title, created_at) VALUES (?, ?, ?)",
        (user_id, title, datetime.now().isoformat()),
    )
    conv_id = c.lastrowid
    conn.commit()
    conn.close()
    return conv_id


def delete_conversation(conv_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
    c.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()


def save_message(conversation_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (conversation_id, role, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_messages(conversation_id):
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


def save_knowledge_doc(filename, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO knowledge_docs (filename, content, uploaded_at) VALUES (?, ?, ?)",
        (filename, content, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def delete_knowledge_doc(doc_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM knowledge_docs WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


def normalize_base_url(base_url):
    return base_url.strip().rstrip("/")


def provider_requires_api_key(api_type):
    return api_type not in ("Ollama",)


def format_error(prefix, response):
    try:
        details = response.json()
    except Exception:
        details = response.text
    return f"{prefix}: {response.status_code} - {str(details)[:250]}"


def convert_messages_for_anthropic(messages):
    anthropic_messages = []
    system_notes = []

    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "system":
            system_notes.append(content)
            continue

        mapped_role = "assistant" if role == "assistant" else "user"
        anthropic_messages.append({"role": mapped_role, "content": content})

    if system_notes:
        system_text = "\n".join(system_notes)
        if anthropic_messages and anthropic_messages[0]["role"] == "user":
            anthropic_messages[0]["content"] = f"{system_text}\n\n{anthropic_messages[0]['content']}"
        else:
            anthropic_messages.insert(0, {"role": "user", "content": system_text})

    if not anthropic_messages:
        anthropic_messages.append({"role": "user", "content": "Hi"})

    return anthropic_messages


def convert_messages_for_google(messages):
    contents = []
    system_notes = []

    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "system":
            system_notes.append(content)
            continue

        mapped_role = "model" if role == "assistant" else "user"
        contents.append({"role": mapped_role, "parts": [{"text": content}]})

    if system_notes:
        system_text = "\n".join(system_notes)
        if contents and contents[0]["role"] == "user":
            first_text = contents[0]["parts"][0]["text"]
            contents[0]["parts"][0]["text"] = f"{system_text}\n\n{first_text}"
        else:
            contents.insert(0, {"role": "user", "parts": [{"text": system_text}]})

    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Hi"}]})

    return contents


def call_openai(api_key, base_url, model, messages):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {"model": model, "messages": messages, "max_tokens": 2000}

    try:
        response = requests.post(
            f"{normalize_base_url(base_url)}/chat/completions",
            headers=headers,
            json=data,
            timeout=60,
        )
        if response.status_code == 200:
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_azure_openai(api_key, base_url, deployment_name, messages):
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    data = {"messages": messages, "max_tokens": 2000}

    try:
        response = requests.post(
            f"{normalize_base_url(base_url)}/openai/deployments/{deployment_name}/chat/completions",
            headers=headers,
            params={"api-version": AZURE_OPENAI_API_VERSION},
            json=data,
            timeout=60,
        )
        if response.status_code == 200:
            payload = response.json()
            return payload["choices"][0]["message"]["content"]
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_anthropic(api_key, model, messages):
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    data = {
        "model": model,
        "max_tokens": 2000,
        "messages": convert_messages_for_anthropic(messages),
    }

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=60,
        )
        if response.status_code == 200:
            payload = response.json()
            text_parts = [item.get("text", "") for item in payload.get("content", []) if item.get("type") == "text"]
            return "\n".join(part for part in text_parts if part).strip()
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_ollama(base_url, model, messages):
    data = {"model": model, "messages": messages, "stream": False}

    try:
        response = requests.post(
            f"{normalize_base_url(base_url)}/api/chat",
            json=data,
            timeout=120,
        )
        if response.status_code == 200:
            return response.json()["message"]["content"]
        return format_error("API 錯誤", response)
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_google(api_key, base_url, model, messages):
    data = {
        "contents": convert_messages_for_google(messages),
        "generationConfig": {"maxOutputTokens": 2000},
    }

    try:
        response = requests.post(
            f"{normalize_base_url(base_url)}/models/{model}:generateContent",
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=data,
            timeout=60,
        )
        payload = response.json()
        if response.status_code == 200:
            candidates = payload.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
            return "回應格式錯誤: 缺少 candidates"
        return f"API 錯誤: {response.status_code} - {str(payload)[:250]}"
    except Exception as exc:
        return f"連線錯誤: {str(exc)}"


def call_provider(api_type, api_key, base_url, model, messages):
    if api_type in ("OpenAI", "Custom"):
        return call_openai(api_key, base_url, model, messages)
    if api_type == "Azure OpenAI":
        return call_azure_openai(api_key, base_url, model, messages)
    if api_type == "Anthropic":
        return call_anthropic(api_key, model, messages)
    if api_type == "Ollama":
        return call_ollama(base_url, model, messages)
    if api_type == "Google Gemini":
        return call_google(api_key, base_url, model, messages)
    return f"不支援的供應商類型: {api_type}"


def verify_provider_config(api_type, api_key, base_url, model):
    if provider_requires_api_key(api_type) and not api_key:
        return False, "請輸入 API Key"
    if not base_url and api_type not in ("Anthropic",):
        return False, "請輸入 Base URL"
    if not model:
        return False, "請先指定模型"

    test_messages = [{"role": "user", "content": "Reply with OK only."}]
    result = call_provider(api_type, api_key, base_url, model, test_messages)
    if not result or "API 錯誤" in result or "連線錯誤" in result or "回應格式錯誤" in result:
        return False, result
    return True, f"驗證成功，模型可用: {model}"


def fetch_models_for_provider(api_type, api_key, base_url):
    if provider_requires_api_key(api_type) and not api_key:
        return False, "請先輸入 API Key", []
    if not base_url and api_type not in ("Anthropic",):
        return False, "請先輸入 Base URL", []

    try:
        if api_type in ("OpenAI", "Custom"):
            response = requests.get(
                f"{normalize_base_url(base_url)}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted(model["id"] for model in response.json().get("data", []))
            return True, f"找到 {len(models)} 個模型", models

        if api_type == "Azure OpenAI":
            response = requests.get(
                f"{normalize_base_url(base_url)}/openai/models",
                headers={"api-key": api_key},
                params={"api-version": AZURE_OPENAI_API_VERSION},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted(model["id"] for model in response.json().get("data", []))
            note = "找到可用模型。Azure 對話時通常仍需填入部署名稱。"
            return True, note, models

        if api_type == "Anthropic":
            response = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted(model["id"] for model in response.json().get("data", []))
            return True, f"找到 {len(models)} 個模型", models

        if api_type == "Ollama":
            response = requests.get(f"{normalize_base_url(base_url)}/api/tags", timeout=30)
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = sorted({model.get("name") or model.get("model") for model in response.json().get("models", []) if model.get("name") or model.get("model")})
            return True, f"找到 {len(models)} 個本機模型", models

        if api_type == "Google Gemini":
            response = requests.get(
                f"{normalize_base_url(base_url)}/models",
                params={"key": api_key},
                timeout=30,
            )
            if response.status_code != 200:
                return False, format_error("查詢失敗", response), []
            models = []
            for model in response.json().get("models", []):
                methods = model.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    model_name = model.get("name", "").replace("models/", "")
                    if model_name:
                        models.append(model_name)
            models = sorted(set(models))
            return True, f"找到 {len(models)} 個 Gemini 模型", models

        return False, "不支援的供應商類型", []
    except Exception as exc:
        return False, f"連線錯誤: {str(exc)}", []


init_db()


class AIPlatformApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AI 協作平台")
        self.geometry("1280x840")

        self.current_user = None
        self.current_conversation = None
        self.current_project = None
        self.selected_file = None
        self.history_expanded = False
        self.history_manage_mode = False

        self.setup_ui()

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self.topbar = ctk.CTkFrame(self, height=72, corner_radius=0, fg_color="#1b1b1d")
        self.topbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.topbar.grid_columnconfigure(1, weight=1)

        self.topbar_title = ctk.CTkLabel(
            self.topbar,
            text="AI 協作平台",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.topbar_title.grid(row=0, column=0, padx=(18, 12), pady=14, sticky="w")

        self.nav_frame = ctk.CTkFrame(self.topbar, fg_color="transparent")
        self.nav_frame.grid(row=0, column=1, padx=10, pady=12, sticky="w")

        self.btn_chat = ctk.CTkButton(self.nav_frame, text="AI 對話", width=110, command=self.show_chat)
        self.btn_chat.pack(side="left", padx=6)

        self.btn_users = ctk.CTkButton(self.nav_frame, text="使用者資料", width=110, command=self.show_users)
        self.btn_users.pack(side="left", padx=6)

        self.btn_settings = ctk.CTkButton(self.nav_frame, text="系統設定", width=110, command=self.show_settings)
        self.btn_settings.pack(side="left", padx=6)

        self.btn_knowledge = ctk.CTkButton(self.nav_frame, text="知識庫", width=110, command=self.show_knowledge)
        self.btn_knowledge.pack(side="left", padx=6)

        self.btn_tools = ctk.CTkButton(self.nav_frame, text="AI Tools", width=110, command=self.show_tools)
        self.btn_tools.pack(side="left", padx=6)

        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color="#171718")
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(3, weight=1)
        self.sidebar.grid_propagate(False)

        self.project_title = ctk.CTkLabel(
            self.sidebar,
            text="使用者專案",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.project_title.grid(row=0, column=0, padx=16, pady=(18, 8), sticky="w")

        self.project_user_label = ctk.CTkLabel(self.sidebar, text="目前使用者: 未選擇", text_color="#b8b8b8")
        self.project_user_label.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        self.btn_add_project = ctk.CTkButton(
            self.sidebar,
            text="新增專案資料夾",
            command=self.add_project_folder_from_dialog,
        )
        self.btn_add_project.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")

        self.project_list_frame = ctk.CTkScrollableFrame(self.sidebar, corner_radius=10)
        self.project_list_frame.grid(row=3, column=0, padx=12, pady=(0, 8), sticky="nsew")

        self.project_status_label = ctk.CTkLabel(self.sidebar, text="", text_color="#8f8f8f", justify="left")
        self.project_status_label.grid(row=4, column=0, padx=16, pady=(0, 16), sticky="ew")

        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=1, column=1, sticky="nsew")

        self.show_chat()
        self.refresh_project_sidebar()

    def clear_main(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def ensure_current_user(self):
        users = get_users()
        if self.current_user:
            for user in users:
                if user[0] == self.current_user[0]:
                    self.current_user = user
                    return self.current_user

        self.current_user = users[0] if users else None
        return self.current_user

    def set_active_nav(self, active_name):
        nav_buttons = {
            "chat": self.btn_chat,
            "users": self.btn_users,
            "settings": self.btn_settings,
            "knowledge": self.btn_knowledge,
            "tools": self.btn_tools,
        }
        for name, button in nav_buttons.items():
            if name == active_name:
                button.configure(fg_color="#2f7dc0")
            else:
                button.configure(fg_color=["#3a7ebf", "#1f538d"])

    def select_project(self, project):
        self.current_project = project
        self.refresh_project_sidebar()

    def refresh_project_sidebar(self):
        self.ensure_current_user()

        for widget in self.project_list_frame.winfo_children():
            widget.destroy()

        if not self.current_user:
            self.project_user_label.configure(text="目前使用者: 未選擇")
            self.project_status_label.configure(text="請先建立使用者後再新增專案資料夾", text_color="orange")
            self.btn_add_project.configure(state="disabled")
            empty_label = ctk.CTkLabel(self.project_list_frame, text="尚無使用者", text_color="#9f9f9f")
            empty_label.pack(anchor="w", padx=8, pady=8)
            return

        self.project_user_label.configure(text=f"目前使用者: {self.current_user[1]}")
        self.btn_add_project.configure(state="normal")

        projects = get_projects(self.current_user[0])
        if self.current_project and self.current_project[0] not in [project[0] for project in projects]:
            self.current_project = None
        if not self.current_project and projects:
            self.current_project = projects[0]

        if not projects:
            self.project_status_label.configure(text="尚未建立專案資料夾", text_color="#9f9f9f")
            empty_label = ctk.CTkLabel(self.project_list_frame, text="尚無專案資料夾", text_color="#9f9f9f")
            empty_label.pack(anchor="w", padx=8, pady=8)
            return

        for project in projects:
            is_active = self.current_project and self.current_project[0] == project[0]
            item_frame = ctk.CTkFrame(
                self.project_list_frame,
                fg_color="#244e73" if is_active else "#232427",
                corner_radius=10,
            )
            item_frame.pack(fill="x", padx=4, pady=6)

            item_button = ctk.CTkButton(
                item_frame,
                text=project[2],
                fg_color="transparent",
                hover_color="#315b82" if is_active else "#2d2f35",
                anchor="w",
                command=lambda project_item=project: self.select_project(project_item),
            )
            item_button.pack(fill="x", padx=8, pady=(8, 2))

            path_label = ctk.CTkLabel(
                item_frame,
                text=project[3],
                text_color="#b9c2cc",
                anchor="w",
                justify="left",
                wraplength=220,
            )
            path_label.pack(fill="x", padx=14, pady=(0, 10))

        active_path = self.current_project[3] if self.current_project else ""
        self.project_status_label.configure(text=active_path, text_color="#8f8f8f")

    def add_project_folder_from_dialog(self):
        import tkinter.filedialog

        user = self.ensure_current_user()
        if not user:
            self.project_status_label.configure(text="請先建立使用者", text_color="orange")
            return

        folder_path = tkinter.filedialog.askdirectory()
        if not folder_path:
            return

        try:
            project_id = add_project_folder(user[0], folder_path)
            projects = get_projects(user[0])
            self.current_project = next((project for project in projects if project[0] == project_id), None)
            self.project_status_label.configure(text=f"已新增: {folder_path}", text_color="lightgreen")
        except sqlite3.IntegrityError:
            self.project_status_label.configure(text="此專案資料夾已存在", text_color="orange")
        self.refresh_project_sidebar()

    def get_provider_defaults(self, provider_type):
        defaults = {
            "OpenAI": ("https://api.openai.com/v1", "gpt-4o-mini"),
            "Google Gemini": ("https://generativelanguage.googleapis.com/v1beta", "gemini-2.5-flash"),
            "Anthropic": ("https://api.anthropic.com", "claude-sonnet-4-20250514"),
            "Ollama": ("http://localhost:11434", "llama3.2"),
            "Azure OpenAI": ("https://your-resource.openai.azure.com", "gpt-4o-mini"),
            "Custom": ("", ""),
        }
        return defaults.get(provider_type, ("", ""))

    def set_status(self, widget, text, color="white"):
        widget.configure(text=text, text_color=color)

    def configure_chat_display(self):
        self.chat_bubble_max_width = 620
        self.chat_text_wrap = self.chat_bubble_max_width - 100
        self.input_min_height = 44
        self.input_max_height = 156
        self.input_wrap_chars = 52

    def clear_chat_display(self):
        for widget in self.chat_display.winfo_children():
            widget.destroy()

    def clear_conversation_history_widgets(self):
        if hasattr(self, "conversation_history_frame"):
            for widget in self.conversation_history_frame.winfo_children():
                widget.destroy()

    def toggle_history_panel(self):
        self.history_expanded = not self.history_expanded
        self.apply_history_panel_state()

    def toggle_history_manage_mode(self):
        self.history_manage_mode = not self.history_manage_mode
        if not self.history_manage_mode and hasattr(self, "conversation_check_vars"):
            for value in self.conversation_check_vars.values():
                value.set(False)
        self.apply_history_panel_state()
        if self.current_user:
            self.refresh_conversation_history_list(get_conversations(self.current_user[0]))

    def apply_history_panel_state(self):
        if hasattr(self, "history_toggle_button"):
            self.history_toggle_button.configure(
                text="歷史對話" if not self.history_expanded else "收合歷史"
            )

        if hasattr(self, "history_manage_button"):
            self.history_manage_button.configure(
                text="管理" if not self.history_manage_mode else "完成管理"
            )
            self.history_manage_button.configure(state="normal" if self.history_expanded else "disabled")

        if hasattr(self, "btn_delete_conversations"):
            if self.history_expanded and self.history_manage_mode:
                if not self.btn_delete_conversations.winfo_manager():
                    self.btn_delete_conversations.pack(side="right", padx=(8, 0))
            else:
                if self.btn_delete_conversations.winfo_manager():
                    self.btn_delete_conversations.pack_forget()

        if hasattr(self, "history_body_frame"):
            if self.history_expanded:
                if not self.history_body_frame.winfo_manager():
                    self.history_body_frame.pack(fill="x", padx=8, pady=(0, 8))
            else:
                if self.history_body_frame.winfo_manager():
                    self.history_body_frame.pack_forget()

        self.update_batch_delete_button_state()

    def update_batch_delete_button_state(self):
        if not hasattr(self, "btn_delete_conversations"):
            return

        selected_count = 0
        if hasattr(self, "conversation_check_vars"):
            selected_count = sum(1 for value in self.conversation_check_vars.values() if value.get())

        if self.history_manage_mode and selected_count > 0:
            self.btn_delete_conversations.configure(
                state="normal",
                text=f"刪除勾選對話 ({selected_count})",
            )
        else:
            self.btn_delete_conversations.configure(
                state="disabled",
                text="刪除勾選對話",
            )

    def update_current_conversation_summary(self):
        if not hasattr(self, "current_conversation_label"):
            return

        if self.current_conversation:
            title = self.current_conversation[2]
            created_at = self.current_conversation[3][:16].replace("T", " ")
            self.current_conversation_label.configure(
                text=f"目前對話: {title}  |  {created_at}",
                text_color="#d8e4f2",
            )
        else:
            self.current_conversation_label.configure(
                text="目前對話: 新對話",
                text_color="#b8b8b8",
            )

    def open_conversation_by_id(self, conversation_id):
        if not self.current_user:
            return

        conversations = get_conversations(self.current_user[0])
        target = next((conversation for conversation in conversations if conversation[0] == conversation_id), None)
        if not target:
            return

        self.current_conversation = target
        self.update_current_conversation_summary()
        self.load_messages()

    def refresh_conversation_history_list(self, conversations):
        self.clear_conversation_history_widgets()
        self.conversation_check_vars = {}
        if hasattr(self, "history_summary_label"):
            self.history_summary_label.configure(text=f"歷史對話 ({len(conversations)})")

        if not conversations:
            empty_label = ctk.CTkLabel(
                self.conversation_history_frame,
                text="尚無歷史對話",
                text_color="#9f9f9f",
            )
            empty_label.pack(anchor="w", padx=8, pady=8)
            self.update_batch_delete_button_state()
            return

        for conversation in conversations:
            conversation_id = conversation[0]
            check_var = ctk.BooleanVar(value=False)
            self.conversation_check_vars[conversation_id] = check_var

            is_active = self.current_conversation and self.current_conversation[0] == conversation_id
            item_frame = ctk.CTkFrame(
                self.conversation_history_frame,
                fg_color="#244e73" if is_active else "#232427",
                corner_radius=10,
            )
            item_frame.pack(fill="x", padx=4, pady=4)

            top_row = ctk.CTkFrame(item_frame, fg_color="transparent")
            top_row.pack(fill="x", padx=8, pady=(6, 6))

            if self.history_manage_mode:
                checkbox = ctk.CTkCheckBox(
                    top_row,
                    text="",
                    width=24,
                    variable=check_var,
                    command=self.update_batch_delete_button_state,
                )
                checkbox.pack(side="left", padx=(0, 6))

            open_button = ctk.CTkButton(
                top_row,
                text=conversation[2],
                fg_color="transparent",
                hover_color="#315b82" if is_active else "#2d2f35",
                anchor="w",
                command=lambda conversation_item_id=conversation_id: self.open_conversation_by_id(conversation_item_id),
            )
            open_button.pack(side="left", fill="x", expand=True)

            timestamp_label = ctk.CTkLabel(
                top_row,
                text=conversation[3][:16].replace("T", " "),
                text_color="#9ea7b3",
                font=ctk.CTkFont(size=11),
            )
            timestamp_label.pack(side="right", padx=(8, 2))

        self.update_batch_delete_button_state()

    def batch_delete_selected_conversations(self):
        if not self.current_user or not hasattr(self, "conversation_check_vars"):
            return

        selected_ids = [
            conversation_id
            for conversation_id, variable in self.conversation_check_vars.items()
            if variable.get()
        ]
        if not selected_ids:
            return

        current_conversation_id = self.current_conversation[0] if self.current_conversation else None

        for conversation_id in selected_ids:
            delete_conversation(conversation_id)

        if current_conversation_id in selected_ids:
            self.current_conversation = None

        self.load_conversations()

    def get_input_text(self):
        return self.msg_entry.get("1.0", "end-1c").strip()

    def clear_input_text(self):
        self.msg_entry.delete("1.0", "end")
        self.autosize_input_box()

    def estimate_input_line_count(self, text):
        raw_lines = text.splitlines() or [""]
        total_lines = 0

        for raw_line in raw_lines:
            visual_lines = max(1, (len(raw_line) // self.input_wrap_chars) + 1)
            total_lines += visual_lines

        return total_lines

    def autosize_input_box(self, event=None):
        text = self.msg_entry.get("1.0", "end-1c")
        visual_lines = min(6, max(1, self.estimate_input_line_count(text)))
        target_height = self.input_min_height + (visual_lines - 1) * 22
        target_height = max(self.input_min_height, min(self.input_max_height, target_height))
        self.msg_entry.configure(height=target_height)

    def on_input_return(self, event):
        if event.state & 0x0001:
            return None

        self.send_message()
        return "break"

    def format_display_value(self, value):
        if value is None:
            return ""

        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    return json.dumps(parsed, ensure_ascii=False, indent=2)
                except Exception:
                    return value
            return value

        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, ensure_ascii=False, indent=2)

        return str(value)

    def normalize_chat_item(self, item, default_role="assistant", default_kind="message"):
        if isinstance(item, str):
            return {
                "role": default_role,
                "kind": default_kind,
                "title": "",
                "content": item,
                "meta": {},
                "sections": [],
                "timestamp": "",
            }

        if not isinstance(item, dict):
            return {
                "role": default_role,
                "kind": default_kind,
                "title": "",
                "content": str(item),
                "meta": {},
                "sections": [],
                "timestamp": "",
            }

        return {
            "role": item.get("role", default_role),
            "kind": item.get("kind", default_kind),
            "title": item.get("title", ""),
            "content": item.get("content", item.get("text", item.get("message", ""))),
            "meta": item.get("meta", {}),
            "sections": item.get("sections", []),
            "timestamp": item.get("timestamp", ""),
        }

    def render_chat_item(self, item):
        normalized = self.normalize_chat_item(item)

        role_labels = {
            "user": "USER",
            "assistant": "AI",
            "system": "SYSTEM",
            "tool": "TOOL",
        }
        kind_labels = {
            "message": "",
            "status": "STATUS",
            "warning": "WARNING",
            "error": "ERROR",
            "result": "RESULT",
            "tool_call": "TOOL CALL",
            "tool_result": "TOOL RESULT",
        }

        header_parts = [role_labels.get(normalized["role"], str(normalized["role"]).upper())]
        kind_label = kind_labels.get(normalized["kind"], str(normalized["kind"]).replace("_", " ").upper())

        if kind_label:
            header_parts.append(kind_label)
        if normalized["title"]:
            header_parts.append(str(normalized["title"]))
        if normalized["timestamp"]:
            header_parts.append(str(normalized["timestamp"]))

        role = normalized["role"]
        kind = normalized["kind"]
        side = "right" if role == "user" else "left"

        bubble_styles = {
            "user": {"fg_color": "#1f6aa5", "text_color": "#ffffff", "header_color": "#d9ecff"},
            "assistant": {"fg_color": "#2b2b2b", "text_color": "#f2f2f2", "header_color": "#9fd3a8"},
            "system": {"fg_color": "#3a2f1e", "text_color": "#fff4d6", "header_color": "#f8d27a"},
            "tool": {"fg_color": "#2a2438", "text_color": "#efe7ff", "header_color": "#c8b8ff"},
        }
        kind_overrides = {
            "error": {"fg_color": "#4a1f1f", "text_color": "#ffd6d6", "header_color": "#ff9d9d"},
            "warning": {"fg_color": "#4a3b12", "text_color": "#fff0c7", "header_color": "#ffd36f"},
            "status": {"fg_color": "#1f2f45", "text_color": "#dbeafe", "header_color": "#93c5fd"},
            "result": {"fg_color": "#203529", "text_color": "#dbffe7", "header_color": "#8de1aa"},
        }

        style = dict(bubble_styles.get(role, bubble_styles["assistant"]))
        style.update(kind_overrides.get(kind, {}))

        row_frame = ctk.CTkFrame(self.chat_display, fg_color="transparent")
        row_frame.pack(fill="x", padx=10, pady=6)

        bubble_frame = ctk.CTkFrame(
            row_frame,
            fg_color=style["fg_color"],
            corner_radius=14,
        )
        bubble_frame.pack(side=side, anchor="e" if side == "right" else "w", padx=10)

        header_label = ctk.CTkLabel(
            bubble_frame,
            text=" | ".join(header_parts),
            text_color=style["header_color"],
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
            justify="left",
        )
        header_label.pack(fill="x", padx=14, pady=(10, 2))

        meta = normalized["meta"] or {}
        if isinstance(meta, dict) and meta:
            meta_line = " | ".join(f"{key}: {self.format_display_value(value)}" for key, value in meta.items())
            if meta_line:
                meta_label = ctk.CTkLabel(
                    bubble_frame,
                    text=meta_line,
                    text_color="#c7c7c7",
                    font=ctk.CTkFont(size=11),
                    anchor="w",
                    justify="left",
                    wraplength=self.chat_text_wrap,
                )
                meta_label.pack(fill="x", padx=14, pady=(0, 4))

        content = self.format_display_value(normalized["content"])
        if content:
            content_label = ctk.CTkLabel(
                bubble_frame,
                text=content,
                text_color=style["text_color"],
                font=ctk.CTkFont(size=14),
                anchor="w",
                justify="left",
                wraplength=self.chat_text_wrap,
            )
            content_label.pack(fill="x", padx=14, pady=(0, 8))

        for section in normalized["sections"] or []:
            if not isinstance(section, dict):
                section_label = ctk.CTkLabel(
                    bubble_frame,
                    text=self.format_display_value(section),
                    text_color=style["text_color"],
                    font=ctk.CTkFont(size=13),
                    anchor="w",
                    justify="left",
                    wraplength=self.chat_text_wrap,
                )
                section_label.pack(fill="x", padx=14, pady=(0, 6))
                continue

            section_title = section.get("title", "")
            section_content = self.format_display_value(section.get("content", ""))

            if section_title:
                section_title_label = ctk.CTkLabel(
                    bubble_frame,
                    text=f"[{section_title}]",
                    text_color=style["header_color"],
                    font=ctk.CTkFont(size=12, weight="bold"),
                    anchor="w",
                    justify="left",
                )
                section_title_label.pack(fill="x", padx=14, pady=(2, 2))
            if section_content:
                section_content_label = ctk.CTkLabel(
                    bubble_frame,
                    text=section_content,
                    text_color=style["text_color"],
                    font=ctk.CTkFont(size=13),
                    anchor="w",
                    justify="left",
                    wraplength=self.chat_text_wrap,
                )
                section_content_label.pack(fill="x", padx=14, pady=(0, 6))

        self.update_idletasks()
        if hasattr(self.chat_display, "_parent_canvas"):
            self.chat_display._parent_canvas.yview_moveto(1.0)

    def get_chat_provider_names(self):
        return [provider[1] for provider in get_providers()]

    def show_chat(self):
        self.clear_main()
        self.set_active_nav("chat")

        title = ctk.CTkLabel(
            self.main_frame,
            text="AI 對話區",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=10)

        toolbar_frame = ctk.CTkFrame(self.main_frame)
        toolbar_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(toolbar_frame, text="使用者").pack(side="left", padx=(10, 6))
        self.user_var = ctk.StringVar()
        self.user_combo = ctk.CTkComboBox(toolbar_frame, values=[], variable=self.user_var, command=self.on_user_changed, width=220)
        self.user_combo.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(toolbar_frame, text="供應商").pack(side="left", padx=(0, 6))
        self.chat_provider_var = ctk.StringVar()
        self.chat_provider_combo = ctk.CTkComboBox(
            toolbar_frame,
            values=[],
            variable=self.chat_provider_var,
            command=self.on_chat_provider_changed,
            width=240,
        )
        self.chat_provider_combo.pack(side="left", padx=(0, 12))

        self.chat_provider_status = ctk.CTkLabel(toolbar_frame, text="")
        self.chat_provider_status.pack(side="left", padx=(0, 12))

        self.btn_new_chat = ctk.CTkButton(toolbar_frame, text="新對話", width=110, command=self.new_conversation)
        self.btn_new_chat.pack(side="right", padx=(8, 10))

        summary_frame = ctk.CTkFrame(self.main_frame)
        summary_frame.pack(padx=20, pady=(0, 8), fill="x")

        self.current_conversation_label = ctk.CTkLabel(
            summary_frame,
            text="目前對話: 新對話",
            anchor="w",
            text_color="#d8e4f2",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.current_conversation_label.pack(side="left", padx=12, pady=8)

        history_frame = ctk.CTkFrame(self.main_frame)
        history_frame.pack(padx=20, pady=(0, 8), fill="x")

        history_header = ctk.CTkFrame(history_frame, fg_color="transparent")
        history_header.pack(fill="x", padx=8, pady=(6, 6))

        self.history_summary_label = ctk.CTkLabel(
            history_header,
            text="歷史對話",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.history_summary_label.pack(side="left")

        self.history_toggle_button = ctk.CTkButton(
            history_header,
            text="展開歷史對話",
            width=120,
            command=self.toggle_history_panel,
        )
        self.history_toggle_button.pack(side="right", padx=(8, 0))

        self.history_manage_button = ctk.CTkButton(
            history_header,
            text="管理",
            width=90,
            fg_color="#4b5563",
            hover_color="#374151",
            command=self.toggle_history_manage_mode,
        )
        self.history_manage_button.pack(side="right", padx=(8, 0))

        self.btn_delete_conversations = ctk.CTkButton(
            history_header,
            text="刪除勾選對話",
            width=140,
            state="disabled",
            fg_color="#9b2c2c",
            hover_color="#7f1d1d",
            command=self.batch_delete_selected_conversations,
        )

        self.history_body_frame = ctk.CTkFrame(history_frame, fg_color="transparent")

        self.conversation_history_frame = ctk.CTkScrollableFrame(self.history_body_frame, height=120, corner_radius=10)
        self.conversation_history_frame.pack(fill="x")
        self.conversation_check_vars = {}
        self.apply_history_panel_state()

        self.chat_display = ctk.CTkScrollableFrame(self.main_frame, corner_radius=10)
        self.chat_display.pack(padx=20, pady=10, fill="both", expand=True)
        self.configure_chat_display()

        input_frame = ctk.CTkFrame(self.main_frame)
        input_frame.pack(padx=20, pady=10, fill="x")

        input_hint = ctk.CTkLabel(
            input_frame,
            text="輸入訊息，Enter 送出，Shift+Enter 換行",
            text_color="#b8b8b8",
            anchor="w",
        )
        input_hint.pack(fill="x", padx=10, pady=(8, 4))

        input_row = ctk.CTkFrame(input_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=8, pady=(0, 8))

        self.msg_entry = ctk.CTkTextbox(input_row, height=self.input_min_height, corner_radius=10)
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.msg_entry.bind("<KeyRelease>", self.autosize_input_box)
        self.msg_entry.bind("<Return>", self.on_input_return)

        self.btn_send = ctk.CTkButton(input_row, text="傳送", width=96, command=self.send_message)
        self.btn_send.pack(side="right")
        self.autosize_input_box()

        self.load_chat_providers()
        self.load_users_for_chat()
        self.load_conversations()

    def load_chat_providers(self):
        provider_names = self.get_chat_provider_names()
        self.chat_provider_combo.configure(values=provider_names if provider_names else ["未設定供應商"])

        active_provider = get_active_provider()
        if active_provider:
            self.chat_provider_combo.set(active_provider[1])
            self.chat_provider_status.configure(text=f"模型: {active_provider[5]}", text_color="lightgreen")
        else:
            self.chat_provider_combo.set("未設定供應商")
            self.chat_provider_status.configure(text="請先到系統設定新增供應商", text_color="orange")

    def on_chat_provider_changed(self, event=None):
        provider = get_provider_by_name(self.chat_provider_var.get())
        if provider:
            set_active_provider(provider[0])
            self.chat_provider_status.configure(text=f"模型: {provider[5]}", text_color="lightgreen")

    def load_users_for_chat(self):
        users = get_users()
        user_names = [user[1] for user in users]
        self.user_combo.configure(values=user_names if user_names else [""])
        if user_names:
            selected_name = self.current_user[1] if self.current_user and self.current_user[1] in user_names else user_names[0]
            self.user_combo.set(selected_name)
            self.on_user_changed()
        else:
            self.user_combo.set("")
            self.current_user = None
            self.refresh_project_sidebar()

    def on_user_changed(self, event=None):
        users = get_users()
        user_map = {user[1]: user for user in users}
        selected_name = self.user_var.get()
        self.current_user = user_map.get(selected_name)
        self.current_project = None
        self.refresh_project_sidebar()
        self.load_conversations()

    def load_conversations(self, selected_title=None):
        if not self.current_user:
            self.current_conversation = None
            self.refresh_conversation_history_list([])
            self.apply_history_panel_state()
            self.update_current_conversation_summary()
            if hasattr(self, "chat_display"):
                self.clear_chat_display()
            return

        conversations = get_conversations(self.current_user[0])
        conversation_titles = [conversation[2] for conversation in conversations]

        if selected_title and selected_title in conversation_titles:
            self.current_conversation = next(
                (conversation for conversation in conversations if conversation[2] == selected_title),
                None,
            )
        elif conversation_titles:
            self.current_conversation = conversations[0]
        else:
            self.current_conversation = None

        self.refresh_conversation_history_list(conversations)
        self.apply_history_panel_state()
        self.update_current_conversation_summary()
        self.load_messages()

    def new_conversation(self):
        if not self.current_user:
            return None

        title = f"對話 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        conversation_id = create_conversation(self.current_user[0], title)
        self.current_conversation = (
            conversation_id,
            self.current_user[0],
            title,
            datetime.now().isoformat(),
        )
        self.load_conversations(selected_title=title)
        self.clear_chat_display()
        return self.current_conversation

    def load_messages(self):
        self.clear_chat_display()
        if not self.current_conversation:
            return

        messages = get_messages(self.current_conversation[0])
        for message in messages:
            self.render_chat_item(
                {
                    "role": message[2],
                    "content": message[3],
                    "timestamp": message[4],
                }
            )

    def send_message(self, event=None):
        if not self.current_user:
            self.render_chat_item({"role": "system", "kind": "warning", "content": "請先建立使用者"})
            return

        provider = get_active_provider()
        if not provider:
            self.render_chat_item(
                {
                    "role": "system",
                    "kind": "warning",
                    "content": "請先到「系統設定」新增並驗證 API 供應商",
                }
            )
            return

        message_text = self.get_input_text()
        if not message_text:
            return

        if not self.current_conversation:
            self.new_conversation()

        if not self.current_conversation:
            self.render_chat_item({"role": "system", "kind": "error", "content": "無法建立新對話，請重試"})
            return

        self.render_chat_item({"role": "user", "content": message_text})
        self.clear_input_text()
        try:
            save_message(self.current_conversation[0], "user", message_text)

            message_rows = get_messages(self.current_conversation[0])
            messages = [{"role": row[2], "content": row[3]} for row in message_rows]

            self.render_chat_item(
                {
                    "role": "assistant",
                    "kind": "status",
                    "title": "處理中",
                    "content": "模型正在處理你的請求。",
                    "meta": {"provider": provider[1], "model": provider[5]},
                }
            )
            self.update()

            response = call_provider(
                provider[2],
                provider[4],
                provider[3],
                provider[5],
                messages,
            )

            self.render_chat_item(
                {
                    "role": "assistant",
                    "kind": "result",
                    "content": response,
                    "meta": {"provider": provider[1], "model": provider[5]},
                }
            )
            save_message(self.current_conversation[0], "assistant", response)
        except Exception as exc:
            self.render_chat_item(
                {
                    "role": "system",
                    "kind": "error",
                    "title": "對話處理失敗",
                    "content": str(exc),
                    "meta": {"provider": provider[1], "model": provider[5]},
                }
            )

    def show_users(self):
        self.clear_main()
        self.set_active_nav("users")

        title = ctk.CTkLabel(
            self.main_frame,
            text="使用者資料區",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=10)

        add_frame = ctk.CTkFrame(self.main_frame)
        add_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(add_frame, text="使用者名稱:").pack(side="left", padx=5)
        self.new_username = ctk.CTkEntry(add_frame, width=200)
        self.new_username.pack(side="left", padx=5)

        ctk.CTkLabel(add_frame, text="Email:").pack(side="left", padx=5)
        self.new_email = ctk.CTkEntry(add_frame, width=200)
        self.new_email.pack(side="left", padx=5)

        btn_add = ctk.CTkButton(add_frame, text="建立使用者", command=self.add_new_user)
        btn_add.pack(side="left", padx=10)

        list_frame = ctk.CTkFrame(self.main_frame)
        list_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.user_list = ctk.CTkTextbox(list_frame, wrap="word")
        self.user_list.pack(padx=10, pady=10, fill="both", expand=True)

        self.refresh_user_list()

    def add_new_user(self):
        username = self.new_username.get().strip()
        email = self.new_email.get().strip()

        if not username:
            return

        try:
            add_user(username, email)
            users = get_users()
            self.current_user = next((user for user in users if user[1] == username), self.current_user)
            self.current_project = None
            self.new_username.delete(0, "end")
            self.new_email.delete(0, "end")
            self.refresh_user_list()
            self.refresh_project_sidebar()
        except sqlite3.IntegrityError:
            self.user_list.insert("end", "⚠️ 使用者已存在\n")

    def refresh_user_list(self):
        self.user_list.delete("1.0", "end")
        users = get_users()
        for user in users:
            self.user_list.insert(
                "end",
                f"ID: {user[0]} | {user[1]} ({user[2]}) - 建立於 {user[3]}\n",
            )

    def show_settings(self):
        self.clear_main()
        self.set_active_nav("settings")

        title = ctk.CTkLabel(
            self.main_frame,
            text="系統設定區",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=10)

        notebook = ctk.CTkTabview(self.main_frame)
        notebook.pack(padx=20, pady=10, fill="both", expand=True)

        tab_provider = notebook.add("API 供應商")

        provider_frame = ctk.CTkFrame(tab_provider)
        provider_frame.pack(padx=10, pady=10, fill="x")

        ctk.CTkLabel(provider_frame, text="名稱:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.prov_name = ctk.CTkEntry(provider_frame, width=180)
        self.prov_name.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.prov_name.insert(0, "OpenAI")

        ctk.CTkLabel(provider_frame, text="類型:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.prov_type = ctk.CTkComboBox(
            provider_frame,
            values=["OpenAI", "Google Gemini", "Anthropic", "Ollama", "Azure OpenAI", "Custom"],
            command=self.on_prov_type_changed,
            width=180,
        )
        self.prov_type.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.prov_type.set("OpenAI")

        ctk.CTkLabel(provider_frame, text="Base URL:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.prov_url = ctk.CTkEntry(provider_frame, width=320)
        self.prov_url.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(provider_frame, text="API Key:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.prov_key = ctk.CTkEntry(provider_frame, width=320, show="*")
        self.prov_key.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        ctk.CTkLabel(provider_frame, text="模型 / 部署名:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.prov_model = ctk.CTkComboBox(provider_frame, values=[], width=220)
        self.prov_model.grid(row=4, column=1, padx=5, pady=5, sticky="w")

        self.on_prov_type_changed()

        btn_save = ctk.CTkButton(provider_frame, text="儲存供應商", command=self.save_provider)
        btn_save.grid(row=5, column=0, pady=10, padx=5, sticky="w")

        self.btn_verify = ctk.CTkButton(provider_frame, text="驗證 API", command=self.verify_provider)
        self.btn_verify.grid(row=5, column=1, pady=10, padx=5, sticky="w")

        self.btn_check_models = ctk.CTkButton(provider_frame, text="查詢可用模型", command=self.check_models)
        self.btn_check_models.grid(row=5, column=2, pady=10, padx=5, sticky="w")

        self.verify_result = ctk.CTkLabel(provider_frame, text="")
        self.verify_result.grid(row=6, column=0, columnspan=3, pady=5, padx=5, sticky="w")

        manage_frame = ctk.CTkFrame(tab_provider)
        manage_frame.pack(padx=10, pady=10, fill="x")

        ctk.CTkLabel(manage_frame, text="已儲存供應商:").pack(side="left", padx=5)
        self.saved_provider_var = ctk.StringVar()
        self.saved_provider_combo = ctk.CTkComboBox(manage_frame, values=[], variable=self.saved_provider_var)
        self.saved_provider_combo.pack(side="left", padx=5, fill="x", expand=True)

        self.btn_load_provider = ctk.CTkButton(manage_frame, text="載入", width=90, command=self.load_selected_provider)
        self.btn_load_provider.pack(side="left", padx=5)

        self.btn_set_active = ctk.CTkButton(manage_frame, text="設為對話供應商", width=130, command=self.set_active_provider_from_ui)
        self.btn_set_active.pack(side="left", padx=5)

        self.btn_delete_provider = ctk.CTkButton(manage_frame, text="刪除", width=90, command=self.delete_selected_provider)
        self.btn_delete_provider.pack(side="left", padx=5)

        self.active_provider_label = ctk.CTkLabel(tab_provider, text="")
        self.active_provider_label.pack(padx=12, pady=(0, 8), anchor="w")

        self.model_result = ctk.CTkTextbox(tab_provider, height=220)
        self.model_result.pack(padx=10, pady=10, fill="both", expand=True)

        tab_system = notebook.add("系統設定")

        ctk.CTkLabel(tab_system, text="預設模型:").pack(padx=10, pady=10, anchor="w")
        self.sys_model = ctk.CTkEntry(tab_system, width=260)
        self.sys_model.pack(padx=10, pady=5, anchor="w")
        self.sys_model.insert(0, get_setting("default_model", ""))

        btn_save_sys = ctk.CTkButton(tab_system, text="儲存系統設定", command=self.save_system_settings)
        btn_save_sys.pack(padx=10, pady=10, anchor="w")

        self.refresh_provider_controls()

    def refresh_provider_controls(self):
        providers = get_providers()
        provider_names = [provider[1] for provider in providers]
        active_provider = get_active_provider()

        if hasattr(self, "saved_provider_combo"):
            self.saved_provider_combo.configure(values=provider_names if provider_names else [""])
            if provider_names:
                self.saved_provider_combo.set(provider_names[0])
            else:
                self.saved_provider_combo.set("")

        if hasattr(self, "active_provider_label"):
            if active_provider:
                self.active_provider_label.configure(
                    text=f"目前對話供應商: {active_provider[1]} / {active_provider[5]}",
                    text_color="lightgreen",
                )
            else:
                self.active_provider_label.configure(
                    text="目前尚未設定對話供應商",
                    text_color="orange",
                )

        if hasattr(self, "chat_provider_combo"):
            self.load_chat_providers()

    def on_prov_type_changed(self, event=None):
        provider_type = self.prov_type.get()
        default_url, default_model = self.get_provider_defaults(provider_type)

        self.prov_url.delete(0, "end")
        self.prov_url.insert(0, default_url)

        self.prov_model.configure(values=[default_model] if default_model else [])
        self.prov_model.set(default_model)

    def get_provider_form_data(self):
        return {
            "name": self.prov_name.get().strip(),
            "api_type": self.prov_type.get().strip(),
            "base_url": self.prov_url.get().strip(),
            "api_key": self.prov_key.get().strip(),
            "model": self.prov_model.get().strip(),
        }

    def save_provider(self):
        data = self.get_provider_form_data()
        if not data["name"]:
            self.set_status(self.verify_result, "請輸入供應商名稱", "orange")
            return

        if provider_requires_api_key(data["api_type"]) and not data["api_key"]:
            self.set_status(self.verify_result, "請輸入 API Key", "orange")
            return

        provider_id = save_provider_record(
            data["name"],
            data["api_type"],
            data["base_url"],
            data["api_key"],
            data["model"],
        )
        save_setting("default_model", data["model"])
        self.set_status(self.verify_result, f"已儲存並啟用: {data['name']}", "lightgreen")
        self.refresh_provider_controls()

        provider = get_provider_by_id(provider_id)
        if provider and hasattr(self, "saved_provider_combo"):
            self.saved_provider_combo.set(provider[1])

    def verify_provider(self):
        data = self.get_provider_form_data()
        success, message = verify_provider_config(
            data["api_type"],
            data["api_key"],
            data["base_url"],
            data["model"],
        )
        color = "lightgreen" if success else "red"
        self.set_status(self.verify_result, message[:100], color)

    def check_models(self):
        data = self.get_provider_form_data()
        success, message, models = fetch_models_for_provider(
            data["api_type"],
            data["api_key"],
            data["base_url"],
        )

        self.model_result.delete("1.0", "end")
        self.model_result.insert("end", f"{message}\n\n")

        if success and models:
            self.prov_model.configure(values=models)
            current_model = data["model"]
            selected_model = current_model if current_model in models else models[0]
            self.prov_model.set(selected_model)
            for model_name in models:
                self.model_result.insert("end", f"• {model_name}\n")
            self.set_status(self.verify_result, message, "lightgreen")
        else:
            self.set_status(self.verify_result, message[:100], "red" if not success else "orange")

    def load_selected_provider(self):
        provider = get_provider_by_name(self.saved_provider_var.get().strip())
        if not provider:
            return

        self.prov_name.delete(0, "end")
        self.prov_name.insert(0, provider[1])
        self.prov_type.set(provider[2])
        self.prov_url.delete(0, "end")
        self.prov_url.insert(0, provider[3] or "")
        self.prov_key.delete(0, "end")
        self.prov_key.insert(0, provider[4] or "")
        self.prov_model.configure(values=[provider[5]] if provider[5] else [])
        self.prov_model.set(provider[5] or "")
        self.set_status(self.verify_result, f"已載入: {provider[1]}", "lightgreen")

    def set_active_provider_from_ui(self):
        provider = get_provider_by_name(self.saved_provider_var.get().strip())
        if not provider:
            return

        set_active_provider(provider[0])
        self.refresh_provider_controls()
        self.set_status(self.verify_result, f"目前對話供應商已切換為: {provider[1]}", "lightgreen")

    def delete_selected_provider(self):
        provider = get_provider_by_name(self.saved_provider_var.get().strip())
        if not provider:
            return

        delete_provider(provider[0])
        self.refresh_provider_controls()
        self.set_status(self.verify_result, f"已刪除供應商: {provider[1]}", "orange")

    def save_system_settings(self):
        save_setting("default_model", self.sys_model.get().strip())

    def show_knowledge(self):
        self.clear_main()
        self.set_active_nav("knowledge")

        title = ctk.CTkLabel(
            self.main_frame,
            text="知識庫",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=10)

        upload_frame = ctk.CTkFrame(self.main_frame)
        upload_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(upload_frame, text="選擇文件:").pack(side="left", padx=5)

        self.kb_file = ctk.CTkButton(upload_frame, text="選擇檔案...", command=self.select_file)
        self.kb_file.pack(side="left", padx=5)

        self.kb_filename = ctk.CTkLabel(upload_frame, text="")
        self.kb_filename.pack(side="left", padx=5)

        self.btn_upload_kb = ctk.CTkButton(upload_frame, text="上傳", command=self.upload_knowledge)
        self.btn_upload_kb.pack(side="left", padx=5)

        list_frame = ctk.CTkFrame(self.main_frame)
        list_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.kb_list = ctk.CTkTextbox(list_frame, wrap="word")
        self.kb_list.pack(padx=10, pady=10, fill="both", expand=True)

        self.refresh_knowledge_list()

    def select_file(self):
        import tkinter.filedialog

        file_path = tkinter.filedialog.askopenfilename(
            filetypes=[("文字檔", "*.txt *.md"), ("所有檔案", "*.*")]
        )
        if file_path:
            self.kb_filename.configure(text=os.path.basename(file_path))
            self.selected_file = file_path

    def upload_knowledge(self):
        if not self.selected_file:
            return

        try:
            with open(self.selected_file, encoding="utf-8", errors="ignore") as file_handle:
                content = file_handle.read()
            save_knowledge_doc(os.path.basename(self.selected_file), content)
            self.refresh_knowledge_list()
        except Exception as exc:
            self.kb_list.insert("end", f"錯誤: {exc}\n")

    def refresh_knowledge_list(self):
        self.kb_list.delete("1.0", "end")
        for document in get_knowledge_docs():
            self.kb_list.insert(
                "end",
                f"• {document[1]} - 上傳於 {document[3]}\n",
            )

    def show_tools(self):
        self.clear_main()
        self.set_active_nav("tools")

        title = ctk.CTkLabel(
            self.main_frame,
            text="AI Tools & Skills",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=10)

        info_frame = ctk.CTkFrame(self.main_frame)
        info_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(info_frame, text="可用工具:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        tools = [
            "• 資料庫查詢 - AI 可直接查詢 SQLite 資料庫",
            "• 執行指令 - AI 可執行系統指令",
            "• 檔案操作 - AI 可讀寫檔案",
            "• 天氣查詢 - 查詢天氣資訊",
        ]
        for tool_text in tools:
            ctk.CTkLabel(info_frame, text=tool_text).pack(anchor="w", padx=20)

        ctk.CTkLabel(info_frame, text="可用 Skills:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(20, 5))
        skills = [
            "• Code Interpreter - 執行 Python 程式碼",
            "• Web Search - 搜尋網路",
            "• Knowledge Retrieval - 從知識庫擷取資訊",
        ]
        for skill_text in skills:
            ctk.CTkLabel(info_frame, text=skill_text).pack(anchor="w", padx=20)

        test_frame = ctk.CTkFrame(self.main_frame)
        test_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(test_frame, text="SQL 測試:").pack(side="left", padx=5)
        self.sql_test = ctk.CTkEntry(test_frame, width=320)
        self.sql_test.pack(side="left", padx=5)
        self.sql_test.insert(0, "SELECT * FROM users")

        btn_test = ctk.CTkButton(test_frame, text="執行", command=self.test_sql)
        btn_test.pack(side="left", padx=5)

        self.sql_result = ctk.CTkTextbox(self.main_frame, height=220)
        self.sql_result.pack(padx=20, pady=10, fill="both", expand=True)

    def test_sql(self):
        query = self.sql_test.get().strip()
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(query)
            results = cursor.fetchall()
            conn.close()

            self.sql_result.delete("1.0", "end")
            self.sql_result.insert("end", f"結果 ({len(results)} rows):\n\n")
            for row in results:
                self.sql_result.insert("end", f"{row}\n")
        except Exception as exc:
            self.sql_result.delete("1.0", "end")
            self.sql_result.insert("end", f"錯誤: {exc}\n")


if __name__ == "__main__":
    app = AIPlatformApp()
    app.mainloop()
