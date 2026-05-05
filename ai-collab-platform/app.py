import customtkinter as ctk
import sqlite3
import os
import json
from datetime import datetime
import threading
import requests

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(KB_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "platform.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS api_providers
                 (id INTEGER PRIMARY KEY, name TEXT, api_type TEXT, base_url TEXT, 
                  api_key TEXT, model TEXT, enabled INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT,
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS conversations
                 (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT,
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id INTEGER PRIMARY KEY, conversation_id INTEGER,
                  role TEXT, content TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS knowledge_docs
                 (id INTEGER PRIMARY KEY, filename TEXT, content TEXT,
                  uploaded_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def get_providers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM api_providers")
    providers = c.fetchall()
    conn.close()
    return providers

def save_provider(name, api_type, base_url, api_key, model):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO api_providers (name, api_type, base_url, api_key, model) VALUES (?, ?, ?, ?, ?)",
             (name, api_type, base_url, api_key, model))
    conn.commit()
    conn.close()

def delete_provider(provider_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM api_providers WHERE id = ?", (provider_id,))
    conn.commit()
    conn.close()

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
    c.execute("INSERT INTO users (username, email, created_at) VALUES (?, ?, ?)",
             (username, email, datetime.now().isoformat()))
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
    c.execute("SELECT * FROM conversations WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    convs = c.fetchall()
    conn.close()
    return convs

def create_conversation(user_id, title):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO conversations (user_id, title, created_at) VALUES (?, ?, ?)",
             (user_id, title, datetime.now().isoformat()))
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
    c.execute("INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
             (conversation_id, role, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_messages(conversation_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at", (conversation_id,))
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
    c.execute("INSERT INTO knowledge_docs (filename, content, uploaded_at) VALUES (?, ?, ?)",
             (filename, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def delete_knowledge_doc(doc_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM knowledge_docs WHERE id = ?", (doc_id,))
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

def call_openai(api_key, base_url, model, messages):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {"model": model, "messages": messages, "max_tokens": 2000}
    try:
        r = requests.post(f"{base_url}/chat/completions", headers=headers, json=data, timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"API 錯誤: {r.status_code} - {r.text}"
    except Exception as e:
        return f"連線錯誤: {str(e)}"

def call_anthropic(api_key, model, messages):
    headers = {"x-api-key": api_key, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}
    content = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    data = {"model": model, "max_tokens": 2000, "messages": [{"role": "user", "content": content}]}
    try:
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data, timeout=60)
        if r.status_code == 200:
            return r.json()["content"][0]["text"]
        return f"API 錯誤: {r.status_code} - {r.text}"
    except Exception as e:
        return f"連線錯誤: {str(e)}"

def call_ollama(base_url, model, messages):
    data = {"model": model, "messages": messages, "stream": False}
    try:
        r = requests.post(f"{base_url}/api/chat", json=data, timeout=120)
        if r.status_code == 200:
            return r.json()["message"]["content"]
        return f"API 錯誤: {r.status_code} - {r.text}"
    except Exception as e:
        return f"連線錯誤: {str(e)}"

def call_google(api_key, model, messages):
    headers = {"Content-Type": "application/json"}
    contents = [{"role": m["role"], "parts": [{"text": m["content"]}]} for m in messages]
    data = {"contents": contents, "generationConfig": {"maxOutputTokens": 2000}}
    try:
        if not model or model == "gemini-pro":
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={api_key}"
        else:
            url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}"
        r = requests.post(url, headers=headers, json=data, timeout=60)
        result = r.json()
        if r.status_code == 200:
            if "candidates" in result and len(result["candidates"]) > 0:
                return result["candidates"][0]["content"]["parts"][0]["text"]
            return f"回應格式錯誤: {result}"
        elif r.status_code == 429:
            return "API 錯誤: 超出配額限制，請檢查 Google Cloud 帳單"
        elif r.status_code == 404:
            return f"API 錯誤: 模型不存在，請確認模型名稱 (可用: gemini-pro)"
        return f"API 錯誤: {r.status_code} - {str(result)[:200]}"
    except Exception as e:
        return f"連線錯誤: {str(e)}"

init_db()

class AIPlatformApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("🤖 AI 協作平台")
        self.geometry("1200x800")
        
        self.current_user = None
        self.current_conversation = None
        
        self.setup_ui()
    
    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        self.btn_chat = ctk.CTkButton(self.sidebar, text="💬 AI 對話", command=self.show_chat)
        self.btn_chat.pack(padx=20, pady=20, fill="x")
        
        self.btn_users = ctk.CTkButton(self.sidebar, text="👥 使用者資料", command=self.show_users)
        self.btn_users.pack(padx=20, pady=20, fill="x")
        
        self.btn_settings = ctk.CTkButton(self.sidebar, text="⚙️ 系統設定", command=self.show_settings)
        self.btn_settings.pack(padx=20, pady=20, fill="x")
        
        self.btn_knowledge = ctk.CTkButton(self.sidebar, text="📚 知識庫", command=self.show_knowledge)
        self.btn_knowledge.pack(padx=20, pady=20, fill="x")
        
        self.btn_tools = ctk.CTkButton(self.sidebar, text="🛠️ AI Tools", command=self.show_tools)
        self.btn_tools.pack(padx=20, pady=20, fill="x")
        
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        
        self.show_chat()
    
    def clear_main(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()
    
    def show_chat(self):
        self.clear_main()
        
        self.main_frame.title = ctk.CTkLabel(self.main_frame, text="💬 AI 對話區", font=ctk.CTkFont(size=18, weight="bold"))
        self.main_frame.title.pack(pady=10)
        
        top_frame = ctk.CTkFrame(self.main_frame)
        top_frame.pack(padx=20, pady=10, fill="x")
        
        ctk.CTkLabel(top_frame, text="使用者:").pack(side="left", padx=5)
        self.user_var = ctk.StringVar()
        self.user_combo = ctk.CTkComboBox(top_frame, values=[], variable=self.user_var, command=self.on_user_changed)
        self.user_combo.pack(side="left", padx=5, fill="x", expand=True)
        
        self.btn_new_chat = ctk.CTkButton(top_frame, text="➕ 新對話", command=self.new_conversation)
        self.btn_new_chat.pack(side="left", padx=5)
        
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
        
        self.load_users_for_chat()
        self.load_conversations()
    
    def load_users_for_chat(self):
        users = get_users()
        user_names = [u[1] for u in users]
        self.user_combo.configure(values=user_names)
        if user_names:
            self.user_combo.set(user_names[0])
            self.on_user_changed(None)
    
    def on_user_changed(self, event):
        users = get_users()
        user_dict = {u[1]: u for u in users}
        selected = self.user_var.get()
        if selected and selected in user_dict:
            self.current_user = user_dict[selected]
            self.load_conversations()
    
    def load_conversations(self):
        if not self.current_user:
            self.conv_combo.configure(values=[])
            return
        
        convs = get_conversations(self.current_user[0])
        conv_titles = [c[2] for c in convs]
        conv_titles.insert(0, "新對話")
        self.conv_combo.configure(values=conv_titles)
        if conv_titles:
            self.conv_combo.set(conv_titles[0])
            if conv_titles[0] == "新對話":
                self.current_conversation = None
            else:
                for c in convs:
                    if c[2] == conv_titles[0]:
                        self.current_conversation = c
                        break
            self.load_messages()
    
    def on_conv_changed(self, event):
        selected = self.conv_var.get()
        if selected == "新對話":
            self.current_conversation = None
            self.chat_display.delete("1.0", "end")
            return
        
        convs = get_conversations(self.current_user[0]) if self.current_user else []
        for c in convs:
            if c[2] == selected:
                self.current_conversation = c
                break
        self.load_messages()
    
    def new_conversation(self):
        title = f"對話 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        if self.current_user:
            conv_id = create_conversation(self.current_user[0], title)
            self.current_conversation = (conv_id, self.current_user[0], title, datetime.now().isoformat())
            self.load_conversations()
            self.conv_combo.set(title)
            self.chat_display.delete("1.0", "end")
    
    def load_messages(self):
        self.chat_display.delete("1.0", "end")
        if not self.current_conversation:
            return
        
        msgs = get_messages(self.current_conversation[0])
        for m in msgs:
            role = "User" if m[2] == "user" else "AI"
            self.chat_display.insert("end", f"【{role}】\n")
            self.chat_display.insert("end", f"{m[3]}\n\n")
    
    def send_message(self, event=None):
        if not self.current_user:
            self.chat_display.insert("end", "⚠️ 請先建立使用者\n\n")
            return
        
        msg = self.msg_entry.get().strip()
        if not msg:
            return
        
        if not self.current_conversation:
            self.new_conversation()
        
        self.chat_display.insert("end", f"【User】\n{msg}\n\n")
        self.msg_entry.delete(0, "end")
        
        save_message(self.current_conversation[0], "user", msg)
        
        providers = get_providers()
        if not providers:
            response = "⚠️ 請在「系統設定」設定 API 供應商"
            self.chat_display.insert("end", f"【AI】\n{response}\n\n")
            self.chat_display.see("end")
            save_message(self.current_conversation[0], "assistant", response)
            return
        
        p = providers[0]
        api_type = p[2]
        api_key = p[4]
        model = p[5]
        base_url = p[3]
        
        msgs = get_messages(self.current_conversation[0])
        messages = [{"role": m[2], "content": m[3]} for m in msgs]
        
        self.chat_display.insert("end", "【AI】處理中...\n")
        self.chat_display.see("end")
        
        try:
            if api_type == "OpenAI" or api_type == "Azure OpenAI":
                response = call_openai(api_key, base_url, model, messages)
            elif api_type == "Anthropic":
                response = call_anthropic(api_key, model, messages)
            elif api_type == "Ollama":
                response = call_ollama(base_url, model, messages)
            elif api_type == "Google Gemini":
                response = call_google(api_key, model, messages)
            else:
                response = f"不支援的供應商類型: {api_type}"
        except Exception as e:
            response = f"錯誤: {str(e)}"
        
        self.chat_display.insert("end", f"{response}\n\n")
        self.chat_display.see("end")
        
        save_message(self.current_conversation[0], "assistant", response)
    
    def show_users(self):
        self.clear_main()
        
        title = ctk.CTkLabel(self.main_frame, text="👥 使用者資料區", font=ctk.CTkFont(size=18, weight="bold"))
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
        if username:
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
        for u in users:
            self.user_list.insert("end", f"ID: {u[0]} | {u[1]} ({u[2]}) - 建立於 {u[3]}\n")
    
    def show_settings(self):
        self.clear_main()
        
        title = ctk.CTkLabel(self.main_frame, text="⚙️ 系統設定區", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=10)
        
        notebook = ctk.CTkTabview(self.main_frame)
        notebook.pack(padx=20, pady=10, fill="both", expand=True)
        
        tab_provider = notebook.add("API 供應商")
        
        prov_frame = ctk.CTkFrame(tab_provider)
        prov_frame.pack(padx=10, pady=10, fill="x")
        
        ctk.CTkLabel(prov_frame, text="名稱:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.prov_name = ctk.CTkEntry(prov_frame, width=150)
        self.prov_name.grid(row=0, column=1, padx=5, pady=5)
        self.prov_name.insert(0, "OpenAI")
        
        ctk.CTkLabel(prov_frame, text="類型:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.prov_type = ctk.CTkComboBox(prov_frame, values=["OpenAI", "Google Gemini", "Anthropic", "Ollama", "Azure OpenAI", "Custom"], command=self.on_prov_type_changed)
        self.prov_type.grid(row=1, column=1, padx=5, pady=5)
        self.prov_type.set("OpenAI")
        
        ctk.CTkLabel(prov_frame, text="Base URL:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.prov_url = ctk.CTkEntry(prov_frame, width=250)
        self.prov_url.grid(row=2, column=1, padx=5, pady=5)
        self.prov_url.insert(0, "https://generativelanguage.googleapis.com/v1")
        
        ctk.CTkLabel(prov_frame, text="API Key:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.prov_key = ctk.CTkEntry(prov_frame, width=250, show="*")
        self.prov_key.grid(row=3, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(prov_frame, text="模型:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.prov_model = ctk.CTkEntry(prov_frame, width=150)
        self.prov_model.grid(row=4, column=1, padx=5, pady=5)
        self.prov_model.insert(0, "gpt-4o")
        
        btn_save = ctk.CTkButton(prov_frame, text="儲存供應商", command=self.save_provider)
        btn_save.grid(row=5, column=0, pady=10, padx=5)
        
        self.btn_verify = ctk.CTkButton(prov_frame, text="驗證 API", command=self.verify_provider)
        self.btn_verify.grid(row=6, column=0, pady=5, padx=5)
        
        self.btn_check_models = ctk.CTkButton(prov_frame, text="查詢可用模型", command=self.check_models)
        self.btn_check_models.grid(row=6, column=1, pady=5, padx=5)
        
        self.verify_result = ctk.CTkLabel(prov_frame, text="")
        self.verify_result.grid(row=7, column=0, columnspan=2, pady=5)
        
        tab_system = notebook.add("系統設定")
        
        ctk.CTkLabel(tab_system, text="預設模型:").pack(padx=10, pady=10, anchor="w")
        self.sys_model = ctk.CTkEntry(tab_system, width=200)
        self.sys_model.pack(padx=10, pady=5, anchor="w")
        self.sys_model.insert(0, get_setting("default_model", "gpt-4o"))
        
        btn_save_sys = ctk.CTkButton(tab_system, text="儲存系統設定", command=self.save_system_settings)
        btn_save_sys.pack(padx=10, pady=10, anchor="w")
    
    def on_prov_type_changed(self, event=None):
        prov_type = self.prov_type.get()
        defaults = {
            "OpenAI": ("https://api.openai.com/v1", "gpt-4o"),
            "Google Gemini": ("https://generativelanguage.googleapis.com/v1", "gemini-pro"),
            "Anthropic": ("https://api.anthropic.com", "claude-3-5-sonnet-20241022"),
            "Ollama": ("http://localhost:11434", "llama3.2"),
            "Azure OpenAI": ("https://your-resource.openai.azure.com", "gpt-4o"),
            "Custom": ("", "")
        }
        url, model = defaults.get(prov_type, ("", ""))
        self.prov_url.delete(0, "end")
        self.prov_url.insert(0, url)
        self.prov_model.delete(0, "end")
        self.prov_model.insert(0, model)
    
    def save_provider(self):
        save_provider(
            self.prov_name.get(),
            self.prov_type.get(),
            self.prov_url.get(),
            self.prov_key.get(),
            self.prov_model.get()
        )
        self.verify_result.configure(text="已儲存", text_color="green")
    
    def verify_provider(self):
        api_type = self.prov_type.get()
        api_key = self.prov_key.get().strip()
        base_url = self.prov_url.get().strip()
        model = self.prov_model.get().strip()
        
        if not api_key:
            self.verify_result.configure(text="請輸入 API Key", text_color="orange")
            return
        
        test_msg = [{"role": "user", "content": "Hi"}]
        
        try:
            if api_type == "OpenAI" or api_type == "Azure OpenAI":
                result = call_openai(api_key, base_url, model, test_msg)
            elif api_type == "Anthropic":
                result = call_anthropic(api_key, model, test_msg)
            elif api_type == "Ollama":
                result = call_ollama(base_url, model, test_msg)
            elif api_type == "Google Gemini":
                result = call_google(api_key, model, test_msg)
            else:
                result = "不支援的供應商類型"
            
            if "錯誤" in result or "連線錯誤" in result:
                self.verify_result.configure(text=result[:50], text_color="red")
            else:
                self.verify_result.configure(text="驗證成功 ✓", text_color="green")
        except Exception as e:
            self.verify_result.configure(text=f"驗證失敗: {str(e)[:30]}", text_color="red")
    
    def check_models(self):
        api_key = self.prov_key.get().strip()
        if not api_key:
            self.verify_result.configure(text="請先輸入 API Key", text_color="orange")
            return
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1/models?key={api_key}"
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                models = r.json().get("models", [])
                model_names = [m["name"].replace("models/", "") for m in models if "gemini" in m["name"]]
                if model_names:
                    self.verify_result.configure(text=f"可用: {', '.join(model_names[:5])}", text_color="green")
                    self.prov_model.delete(0, "end")
                    self.prov_model.insert(0, model_names[0])
                else:
                    self.verify_result.configure(text="未找到 Gemini 模型", text_color="orange")
            else:
                self.verify_result.configure(text=f"查詢失敗: {r.status_code}", text_color="red")
        except Exception as e:
            self.verify_result.configure(text=f"錯誤: {str(e)[:50]}", text_color="red")
    
    def save_system_settings(self):
        save_setting("default_model", self.sys_model.get())
    
    def show_knowledge(self):
        self.clear_main()
        
        title = ctk.CTkLabel(self.main_frame, text="📚 知識庫", font=ctk.CTkFont(size=18, weight="bold"))
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
        file_path = tkinter.filedialog.askopenfilename(filetypes=[("文字檔", "*.txt *.md"), ("所有檔案", "*.*")])
        if file_path:
            self.kb_filename.configure(text=os.path.basename(file_path))
            self.selected_file = file_path
    
    def upload_knowledge(self):
        if hasattr(self, 'selected_file') and self.selected_file:
            try:
                with open(self.selected_file, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                save_knowledge_doc(os.path.basename(self.selected_file), content)
                self.refresh_knowledge_list()
            except Exception as e:
                self.kb_list.insert("end", f"錯誤: {e}\n")
    
    def refresh_knowledge_list(self):
        self.kb_list.delete("1.0", "end")
        docs = get_knowledge_docs()
        for d in docs:
            self.kb_list.insert("end", f"• {d[2]} - 上傳於 {d[4]}\n")
    
    def show_tools(self):
        self.clear_main()
        
        title = ctk.CTkLabel(self.main_frame, text="🛠️ AI Tools & Skills", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=10)
        
        info_frame = ctk.CTkFrame(self.main_frame)
        info_frame.pack(padx=20, pady=10, fill="x")
        
        ctk.CTkLabel(info_frame, text="可用工具:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        tools = [
            "• 資料庫查詢 - AI 可直接查詢 SQLite 資料庫",
            "• 執行指令 - AI 可執行系統指令",
            "• 檔案操作 - AI 可讀寫檔案",
            "• 天氣查詢 - 查詢天氣資訊"
        ]
        for t in tools:
            ctk.CTkLabel(info_frame, text=t).pack(anchor="w", padx=20)
        
        ctk.CTkLabel(info_frame, text="可用 Skills:", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(20,5))
        skills = [
            "• Code Interpreter - 執行 Python 程式碼",
            "• Web Search - 搜尋網路",
            "• Knowledge Retrieval - 從知識庫擷取資訊"
        ]
        for s in skills:
            ctk.CTkLabel(info_frame, text=s).pack(anchor="w", padx=20)
        
        test_frame = ctk.CTkFrame(self.main_frame)
        test_frame.pack(padx=20, pady=10, fill="x")
        
        ctk.CTkLabel(test_frame, text="SQL 測試:").pack(side="left", padx=5)
        self.sql_test = ctk.CTkEntry(test_frame, width=300)
        self.sql_test.pack(side="left", padx=5)
        self.sql_test.insert(0, "SELECT * FROM users")
        
        btn_test = ctk.CTkButton(test_frame, text="執行", command=self.test_sql)
        btn_test.pack(side="left", padx=5)
        
        self.sql_result = ctk.CTkTextbox(self.main_frame, height=200)
        self.sql_result.pack(padx=20, pady=10, fill="both", expand=True)
    
    def test_sql(self):
        query = self.sql_test.get().strip()
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(query)
            results = c.fetchall()
            conn.close()
            self.sql_result.delete("1.0", "end")
            self.sql_result.insert("end", f"結果 ({len(results)} rows):\n\n")
            for r in results:
                self.sql_result.insert("end", f"{r}\n")
        except Exception as e:
            self.sql_result.delete("1.0", "end")
            self.sql_result.insert("end", f"錯誤: {e}\n")

if __name__ == "__main__":
    app = AIPlatformApp()
    app.mainloop()