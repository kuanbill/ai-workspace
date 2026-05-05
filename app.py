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
    conn.commit()
    conn.close()


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
        self.selected_file = None

        self.setup_ui()

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.btn_chat = ctk.CTkButton(self.sidebar, text="AI 對話", command=self.show_chat)
        self.btn_chat.pack(padx=20, pady=20, fill="x")

        self.btn_users = ctk.CTkButton(self.sidebar, text="使用者資料", command=self.show_users)
        self.btn_users.pack(padx=20, pady=20, fill="x")

        self.btn_settings = ctk.CTkButton(self.sidebar, text="系統設定", command=self.show_settings)
        self.btn_settings.pack(padx=20, pady=20, fill="x")

        self.btn_knowledge = ctk.CTkButton(self.sidebar, text="知識庫", command=self.show_knowledge)
        self.btn_knowledge.pack(padx=20, pady=20, fill="x")

        self.btn_tools = ctk.CTkButton(self.sidebar, text="AI Tools", command=self.show_tools)
        self.btn_tools.pack(padx=20, pady=20, fill="x")

        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        self.show_chat()

    def clear_main(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

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

    def get_chat_provider_names(self):
        return [provider[1] for provider in get_providers()]

    def show_chat(self):
        self.clear_main()

        title = ctk.CTkLabel(
            self.main_frame,
            text="AI 對話區",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(pady=10)

        top_frame = ctk.CTkFrame(self.main_frame)
        top_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(top_frame, text="使用者:").pack(side="left", padx=5)
        self.user_var = ctk.StringVar()
        self.user_combo = ctk.CTkComboBox(top_frame, values=[], variable=self.user_var, command=self.on_user_changed)
        self.user_combo.pack(side="left", padx=5, fill="x", expand=True)

        self.btn_new_chat = ctk.CTkButton(top_frame, text="新對話", command=self.new_conversation)
        self.btn_new_chat.pack(side="left", padx=5)

        provider_frame = ctk.CTkFrame(self.main_frame)
        provider_frame.pack(padx=20, pady=5, fill="x")

        ctk.CTkLabel(provider_frame, text="對話供應商:").pack(side="left", padx=5)
        self.chat_provider_var = ctk.StringVar()
        self.chat_provider_combo = ctk.CTkComboBox(
            provider_frame,
            values=[],
            variable=self.chat_provider_var,
            command=self.on_chat_provider_changed,
        )
        self.chat_provider_combo.pack(side="left", padx=5, fill="x", expand=True)

        self.chat_provider_status = ctk.CTkLabel(provider_frame, text="")
        self.chat_provider_status.pack(side="left", padx=8)

        conv_frame = ctk.CTkFrame(self.main_frame)
        conv_frame.pack(padx=20, pady=5, fill="x")

        ctk.CTkLabel(conv_frame, text="對話:").pack(side="left", padx=5)
        self.conv_var = ctk.StringVar()
        self.conv_combo = ctk.CTkComboBox(conv_frame, values=[], variable=self.conv_var, command=self.on_conv_changed)
        self.conv_combo.pack(side="left", padx=5, fill="x", expand=True)

        self.chat_display = ctk.CTkTextbox(self.main_frame, wrap="word")
        self.chat_display.pack(padx=20, pady=10, fill="both", expand=True)

        input_frame = ctk.CTkFrame(self.main_frame)
        input_frame.pack(padx=20, pady=10, fill="x")

        self.msg_entry = ctk.CTkEntry(input_frame, placeholder_text="輸入訊息...")
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.msg_entry.bind("<Return>", self.send_message)

        self.btn_send = ctk.CTkButton(input_frame, text="傳送", command=self.send_message)
        self.btn_send.pack(side="left", padx=5)

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
            self.user_combo.set(user_names[0])
            self.on_user_changed()
        else:
            self.user_combo.set("")
            self.current_user = None

    def on_user_changed(self, event=None):
        users = get_users()
        user_map = {user[1]: user for user in users}
        selected_name = self.user_var.get()
        self.current_user = user_map.get(selected_name)
        self.load_conversations()

    def load_conversations(self):
        if not self.current_user:
            self.conv_combo.configure(values=[""])
            self.conv_combo.set("")
            self.current_conversation = None
            if hasattr(self, "chat_display"):
                self.chat_display.delete("1.0", "end")
            return

        conversations = get_conversations(self.current_user[0])
        conversation_titles = [conversation[2] for conversation in conversations]
        values = ["新對話"] + conversation_titles
        self.conv_combo.configure(values=values)
        self.conv_combo.set("新對話")
        self.current_conversation = None
        self.load_messages()

    def on_conv_changed(self, event=None):
        selected = self.conv_var.get()
        if selected == "新對話":
            self.current_conversation = None
            self.chat_display.delete("1.0", "end")
            return

        conversations = get_conversations(self.current_user[0]) if self.current_user else []
        for conversation in conversations:
            if conversation[2] == selected:
                self.current_conversation = conversation
                break
        self.load_messages()

    def new_conversation(self):
        if not self.current_user:
            return

        title = f"對話 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        conversation_id = create_conversation(self.current_user[0], title)
        self.current_conversation = (
            conversation_id,
            self.current_user[0],
            title,
            datetime.now().isoformat(),
        )
        self.load_conversations()
        self.conv_combo.set(title)
        self.chat_display.delete("1.0", "end")

    def load_messages(self):
        self.chat_display.delete("1.0", "end")
        if not self.current_conversation:
            return

        messages = get_messages(self.current_conversation[0])
        for message in messages:
            role = "User" if message[2] == "user" else "AI"
            self.chat_display.insert("end", f"【{role}】\n{message[3]}\n\n")

    def send_message(self, event=None):
        if not self.current_user:
            self.chat_display.insert("end", "⚠️ 請先建立使用者\n\n")
            return

        provider = get_active_provider()
        if not provider:
            self.chat_display.insert("end", "⚠️ 請先到「系統設定」新增並驗證 API 供應商\n\n")
            return

        message_text = self.msg_entry.get().strip()
        if not message_text:
            return

        if not self.current_conversation:
            self.new_conversation()

        self.chat_display.insert("end", f"【User】\n{message_text}\n\n")
        self.msg_entry.delete(0, "end")
        save_message(self.current_conversation[0], "user", message_text)

        message_rows = get_messages(self.current_conversation[0])
        messages = [{"role": row[2], "content": row[3]} for row in message_rows]

        self.chat_display.insert("end", f"【AI / {provider[1]} / {provider[5]}】處理中...\n")
        self.chat_display.see("end")
        self.update()

        response = call_provider(
            provider[2],
            provider[4],
            provider[3],
            provider[5],
            messages,
        )

        self.chat_display.insert("end", f"{response}\n\n")
        self.chat_display.see("end")
        save_message(self.current_conversation[0], "assistant", response)

    def show_users(self):
        self.clear_main()

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
            self.new_username.delete(0, "end")
            self.new_email.delete(0, "end")
            self.refresh_user_list()
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
