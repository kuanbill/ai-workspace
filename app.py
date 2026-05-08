import base64
import io
import json
import os
import re
import shutil
import sqlite3
import threading
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

import customtkinter as ctk

from api_calls import call_provider, fetch_models_for_provider, provider_requires_api_key, verify_provider_config
from config import (
    get_chat_bubble_width, get_chat_color_theme, get_ui_font_sizes,
    save_chat_bubble_width, save_chat_color_theme, save_ui_font_sizes,
)
from data.db import (
    DB_PATH, KB_DIR, KB_SOURCE_DIR,
    add_project_folder, add_user, create_conversation, delete_conversation,
    delete_knowledge_doc, delete_provider, get_active_provider, get_conversations,
    get_knowledge_docs, get_messages, get_projects, get_provider_by_name,
    get_provider_by_id, get_providers, get_setting, get_users, init_db, save_knowledge_doc,
    save_message, save_provider_record, save_setting, set_active_provider,
)
from knowledge import (
    backup_knowledge, build_knowledge_context, get_local_vector_stats,
    read_text_file, restore_knowledge, vectorize_knowledge_doc,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

UI_FONT_DEFAULTS = {
    "app_title": 20,
    "nav": 14,
    "sidebar_title": 18,
    "sidebar_body": 13,
    "page_title": 18,
    "control": 13,
    "chat_body": 14,
    "chat_meta": 11,
    "input": 14,
}

UI_FONT_LABELS = {
    "app_title": "頂部標題",
    "nav": "上方導覽按鈕",
    "sidebar_title": "左側專案標題",
    "sidebar_body": "左側專案內容",
    "page_title": "各頁主標題",
    "control": "表單、按鈕與清單",
    "chat_body": "AI 對話內容",
    "chat_meta": "對話資訊與時間",
    "input": "訊息輸入框",
}

CHAT_THEME_OPTIONS = ["黑灰白", "藍灰", "綠灰"]

CHAT_THEME_STYLES = {
    "黑灰白": {
        "user": {"fg_color": "#111111", "text_color": "#ffffff", "header_color": "#dcdcdc"},
        "assistant": {"fg_color": "#2b2b2b", "text_color": "#f3f3f3", "header_color": "#f0f0f0"},
        "system": {"fg_color": "#3a3a3a", "text_color": "#f5f5f5", "header_color": "#ffffff"},
        "tool": {"fg_color": "#242424", "text_color": "#eeeeee", "header_color": "#d0d0d0"},
        "copy": {"fg_color": "#444444", "hover_color": "#5a5a5a", "text_color": "#ffffff"},
    },
    "藍灰": {
        "user": {"fg_color": "#17202a", "text_color": "#f5f8fb", "header_color": "#dce6ef"},
        "assistant": {"fg_color": "#26313b", "text_color": "#f1f4f7", "header_color": "#cfd9e2"},
        "system": {"fg_color": "#323940", "text_color": "#f2f4f5", "header_color": "#e5eaee"},
        "tool": {"fg_color": "#202830", "text_color": "#f0f4f7", "header_color": "#cdd7df"},
        "copy": {"fg_color": "#3f5263", "hover_color": "#526879", "text_color": "#ffffff"},
    },
    "綠灰": {
        "user": {"fg_color": "#16211d", "text_color": "#f4fbf7", "header_color": "#d8e8de"},
        "assistant": {"fg_color": "#25312c", "text_color": "#f2f7f4", "header_color": "#d2ddd7"},
        "system": {"fg_color": "#343b38", "text_color": "#f3f6f4", "header_color": "#e3ebe6"},
        "tool": {"fg_color": "#1f2824", "text_color": "#eff6f2", "header_color": "#cad8d0"},
        "copy": {"fg_color": "#3e574b", "hover_color": "#506b5e", "text_color": "#ffffff"},
    },
}

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
        self.current_view = "chat"
        self.font_size_vars = {}
        self.attachments = []
        self.load_ui_font_sizes()
        self.load_chat_display_settings()

        self.setup_ui()

    def load_ui_font_sizes(self):
        stored = get_ui_font_sizes()
        self.ui_font_sizes = {}
        for key, default_size in UI_FONT_DEFAULTS.items():
            self.ui_font_sizes[key] = stored.get(key, default_size)

    def ui_font(self, key, weight=None):
        size = self.ui_font_sizes.get(key, UI_FONT_DEFAULTS.get(key, 13))
        return ctk.CTkFont(size=size, weight=weight)

    def load_chat_display_settings(self):
        self.chat_bubble_setting_width = get_chat_bubble_width(860)

        theme = get_chat_color_theme("黑灰白")
        self.chat_color_theme = theme if theme in CHAT_THEME_STYLES else "黑灰白"

    def get_chat_theme_styles(self):
        return CHAT_THEME_STYLES.get(self.chat_color_theme, CHAT_THEME_STYLES["黑灰白"])

    def apply_ui_fonts(self):
        if hasattr(self, "topbar_title"):
            self.topbar_title.configure(font=self.ui_font("app_title", "bold"))
        if hasattr(self, "project_title"):
            self.project_title.configure(font=self.ui_font("sidebar_title", "bold"))
        if hasattr(self, "project_user_label"):
            self.project_user_label.configure(font=self.ui_font("sidebar_body"))
        if hasattr(self, "project_status_label"):
            self.project_status_label.configure(font=self.ui_font("sidebar_body"))
        if hasattr(self, "btn_add_project"):
            self.btn_add_project.configure(font=self.ui_font("control"))

        if hasattr(self, "nav_frame"):
            for widget in self.nav_frame.winfo_children():
                if isinstance(widget, ctk.CTkButton):
                    widget.configure(font=self.ui_font("nav"))

    def apply_font_to_tree(self, parent):
        for widget in parent.winfo_children():
            try:
                if isinstance(widget, ctk.CTkButton):
                    widget.configure(font=self.ui_font("control"))
                elif isinstance(widget, ctk.CTkLabel):
                    widget.configure(font=self.ui_font("control"))
                elif isinstance(widget, ctk.CTkEntry):
                    widget.configure(font=self.ui_font("control"))
                elif isinstance(widget, ctk.CTkComboBox):
                    widget.configure(font=self.ui_font("control"))
                elif isinstance(widget, ctk.CTkCheckBox):
                    widget.configure(font=self.ui_font("control"))
                elif isinstance(widget, ctk.CTkTextbox):
                    role = "input" if widget == getattr(self, "msg_entry", None) else "control"
                    widget.configure(font=self.ui_font(role))
            except Exception:
                pass
            self.apply_font_to_tree(widget)

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
            font=self.ui_font("app_title", "bold"),
        )
        self.topbar_title.grid(row=0, column=0, padx=(18, 12), pady=14, sticky="w")

        self.nav_frame = ctk.CTkFrame(self.topbar, fg_color="transparent")
        self.nav_frame.grid(row=0, column=1, padx=10, pady=12, sticky="w")

        self.btn_chat = ctk.CTkButton(self.nav_frame, text="AI 對話", width=110, font=self.ui_font("nav"), command=self.show_chat)
        self.btn_chat.pack(side="left", padx=6)

        self.btn_users = ctk.CTkButton(self.nav_frame, text="使用者資料", width=110, font=self.ui_font("nav"), command=self.show_users)
        self.btn_users.pack(side="left", padx=6)

        self.btn_settings = ctk.CTkButton(self.nav_frame, text="系統環境設定", width=140, font=self.ui_font("nav"), command=self.show_settings)
        self.btn_settings.pack(side="left", padx=6)

        self.btn_knowledge = ctk.CTkButton(self.nav_frame, text="知識庫", width=110, font=self.ui_font("nav"), command=self.show_knowledge)
        self.btn_knowledge.pack(side="left", padx=6)

        self.btn_tools = ctk.CTkButton(self.nav_frame, text="AI Tools", width=110, font=self.ui_font("nav"), command=self.show_tools)
        self.btn_tools.pack(side="left", padx=6)

        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color="#171718")
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(3, weight=1)
        self.sidebar.grid_propagate(False)

        self.project_title = ctk.CTkLabel(
            self.sidebar,
            text="使用者專案",
            font=self.ui_font("sidebar_title", "bold"),
        )
        self.project_title.grid(row=0, column=0, padx=16, pady=(18, 8), sticky="w")

        self.project_user_label = ctk.CTkLabel(
            self.sidebar,
            text="目前使用者: 未選擇",
            text_color="#b8b8b8",
            font=self.ui_font("sidebar_body"),
        )
        self.project_user_label.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        self.btn_add_project = ctk.CTkButton(
            self.sidebar,
            text="新增專案資料夾",
            font=self.ui_font("control"),
            command=self.add_project_folder_from_dialog,
        )
        self.btn_add_project.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="ew")

        self.project_list_frame = ctk.CTkScrollableFrame(self.sidebar, corner_radius=10)
        self.project_list_frame.grid(row=3, column=0, padx=12, pady=(0, 8), sticky="nsew")

        self.project_status_label = ctk.CTkLabel(
            self.sidebar,
            text="",
            text_color="#8f8f8f",
            justify="left",
            font=self.ui_font("sidebar_body"),
        )
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
            empty_label = ctk.CTkLabel(
                self.project_list_frame,
                text="尚無使用者",
                text_color="#9f9f9f",
                font=self.ui_font("sidebar_body"),
            )
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
            empty_label = ctk.CTkLabel(
                self.project_list_frame,
                text="尚無專案資料夾",
                text_color="#9f9f9f",
                font=self.ui_font("sidebar_body"),
            )
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
                font=self.ui_font("sidebar_body"),
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
                font=self.ui_font("sidebar_body"),
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
            "Google Gemini": ("https://generativelanguage.googleapis.com/v1beta", "gemini-2.0-flash"),
            "Anthropic": ("https://api.anthropic.com", "claude-sonnet-4-20250514"),
            "Ollama": ("http://localhost:11434", "llama3.2"),
            "Azure OpenAI": ("https://your-resource.openai.azure.com", "gpt-4o-mini"),
            "Custom": ("", ""),
        }
        return defaults.get(provider_type, ("", ""))

    def set_status(self, widget, text, color="white"):
        widget.configure(text=text, text_color=color)

    def configure_chat_display(self):
        self.chat_bubble_max_width = self.chat_bubble_setting_width
        self.chat_content_width = max(360, self.chat_bubble_max_width - 56)
        self.chat_text_wrap = self.chat_content_width
        self.input_min_height = max(44, self.ui_font_sizes.get("input", 14) * 3)
        self.input_max_height = 156
        self.input_wrap_chars = 52

    def copy_text_to_clipboard(self, text, button=None):
        self.clipboard_clear()
        self.clipboard_append(text)
        if button:
            button.configure(text="已複製")
            button.after(1200, lambda: button.configure(text="複製"))

    def get_chat_item_copy_text(self, normalized):
        parts = []
        content = self.format_display_value(normalized["content"])
        if content:
            parts.append(content)

        for section in normalized["sections"] or []:
            if isinstance(section, dict):
                title = section.get("title", "")
                section_content = self.format_display_value(section.get("content", ""))
                if title and section_content:
                    parts.append(f"[{title}]\n{section_content}")
                elif section_content:
                    parts.append(section_content)
            else:
                section_text = self.format_display_value(section)
                if section_text:
                    parts.append(section_text)

        return "\n\n".join(parts).strip()

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
                font=self.ui_font("control"),
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
                font=self.ui_font("control"),
                command=lambda conversation_item_id=conversation_id: self.open_conversation_by_id(conversation_item_id),
            )
            open_button.pack(side="left", fill="x", expand=True)

            timestamp_label = ctk.CTkLabel(
                top_row,
                text=conversation[3][:16].replace("T", " "),
                text_color="#9ea7b3",
                font=self.ui_font("chat_meta"),
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
        self.attachments.clear()
        self.refresh_attach_preview()
        self.autosize_input_box()

    def attach_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[
                ("圖片", "*.png *.jpg *.jpeg *.gif *.webp"),
                ("所有檔案", "*.*"),
            ]
        )
        if not file_path:
            return
        self.add_attachment(file_path)

    def add_attachment(self, file_path):
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            ext = os.path.splitext(file_path)[1].lower()
            mime_map = {
                ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp",
            }
            mime = mime_map.get(ext, "image/png")
            self.attachments.append({
                "name": os.path.basename(file_path),
                "data": data,
                "mime": mime,
            })
            self.refresh_attach_preview()
        except Exception as exc:
            self.render_chat_item({
                "role": "system", "kind": "warning",
                "content": f"無法讀取檔案: {exc}",
            })

    def remove_attachment(self, index):
        if 0 <= index < len(self.attachments):
            self.attachments.pop(index)
            self.refresh_attach_preview()

    def refresh_attach_preview(self):
        for widget in self.attach_frame.winfo_children():
            widget.destroy()
        if not self.attachments:
            self.attach_frame.pack_forget()
            return
        self.attach_frame.pack(fill="x", padx=8, pady=(0, 4))
        for i, att in enumerate(self.attachments):
            frame = ctk.CTkFrame(self.attach_frame, fg_color="#2a2a2a", corner_radius=8)
            frame.pack(side="left", padx=4, pady=4)
            try:
                img = Image.open(io.BytesIO(att["data"]))
                img.thumbnail((48, 48))
                ctk_img = ctk.CTkImage(img, size=img.size)
                label = ctk.CTkLabel(frame, image=ctk_img, text="")
                label.pack(side="left", padx=4, pady=4)
            except Exception:
                ctk.CTkLabel(frame, text="📄", font=ctk.CTkFont(size=24)).pack(side="left", padx=6, pady=4)
            name_label = ctk.CTkLabel(
                frame, text=att["name"][:20], text_color="#cccccc",
                font=self.ui_font("chat_meta"),
            )
            name_label.pack(side="left", padx=2)
            rm_btn = ctk.CTkButton(
                frame, text="✕", width=24, height=24,
                fg_color="#6b2c2c", hover_color="#8a3a3a",
                command=lambda idx=i: self.remove_attachment(idx),
            )
            rm_btn.pack(side="left", padx=4)

    def on_paste(self, event):
        try:
            clip_image = self.clipboard_get_image()
            if clip_image:
                buf = io.BytesIO()
                clip_image.save(buf, format="PNG")
                buf.seek(0)
                data = buf.read()
                self.attachments.append({
                    "name": "clipboard.png",
                    "data": data,
                    "mime": "image/png",
                })
                self.refresh_attach_preview()
                return "break"
        except Exception:
            pass
        return None

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

    def is_markdown_table_separator(self, line):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)

    def is_markdown_table_line(self, line):
        return line.strip().startswith("|") and line.strip().endswith("|") and line.count("|") >= 2

    def parse_markdown_table(self, lines):
        rows = []
        for line in lines:
            if self.is_markdown_table_separator(line):
                continue
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
        if not rows:
            return []
        column_count = max(len(row) for row in rows)
        return [row + [""] * (column_count - len(row)) for row in rows]

    def clean_inline_markdown(self, text):
        cleaned = text.strip()
        cleaned = cleaned.replace("\\rightarrow", "->").replace("\\Rightarrow", "=>")
        cleaned = re.sub(r"\$(.*?)\$", r"\1", cleaned)
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"\*([^\s*][^*]*?[^\s*])\*", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        return cleaned

    def looks_like_formula_or_operator_block(self, text):
        stripped = text.strip()
        if not stripped:
            return False
        if stripped.startswith(("{", "[")):
            return True
        if "```" in stripped or "$$" in stripped or "\\[" in stripped or "\\(" in stripped:
            return True
        if re.search(r"^\s*[-*]\s+", stripped, re.MULTILINE):
            return False
        if re.search(r"\*\*.*?\*\*", stripped):
            return False
        operator_pattern = r"(<=|>=|==|!=|=>|->|<-|=|≤|≥|≠|≈|×|÷|√|∑|∫|∆|∂|π|∞|\^)"
        lines = [line for line in stripped.splitlines() if line.strip()]
        operator_lines = sum(1 for line in lines if re.search(operator_pattern, line))
        return operator_lines >= 2 or (operator_lines == 1 and len(stripped) <= 120)

    def split_rich_text_blocks(self, text):
        lines = text.splitlines()
        blocks = []
        current_text = []
        index = 0
        in_code = False
        code_lines = []

        def flush_text():
            if current_text:
                block_text = "\n".join(current_text).strip("\n")
                if block_text:
                    block_type = "mono" if self.looks_like_formula_or_operator_block(block_text) else "text"
                    blocks.append((block_type, block_text))
                current_text.clear()

        while index < len(lines):
            line = lines[index]
            if line.strip().startswith("```"):
                if in_code:
                    code_lines.append(line)
                    blocks.append(("mono", "\n".join(code_lines).strip("\n")))
                    code_lines = []
                    in_code = False
                else:
                    flush_text()
                    code_lines = [line]
                    in_code = True
                index += 1
                continue

            if in_code:
                code_lines.append(line)
                index += 1
                continue

            if self.is_markdown_table_line(line):
                flush_text()
                table_lines = []
                while index < len(lines) and self.is_markdown_table_line(lines[index]):
                    table_lines.append(lines[index])
                    index += 1
                blocks.append(("table", self.parse_markdown_table(table_lines)))
                continue

            current_text.append(line)
            index += 1

        if code_lines:
            blocks.append(("mono", "\n".join(code_lines).strip("\n")))
        flush_text()
        return blocks or [("text", text)]

    def estimate_textbox_height(self, text, min_height=54, max_height=260):
        line_count = max(1, len(text.splitlines()))
        longest_line = max((len(line) for line in text.splitlines()), default=0)
        wrapped_extra = max(0, longest_line // 92)
        return max(min_height, min(max_height, (line_count + wrapped_extra) * 22 + 24))

    def render_table_content(self, parent, rows, style, padx=14, pady=(0, 8)):
        if not rows:
            return

        column_count = max(len(row) for row in rows)
        cell_width = max(120, int((self.chat_content_width - 16) / max(1, column_count)))
        table_frame = ctk.CTkFrame(parent, fg_color="#171717", border_width=1, border_color="#555555", corner_radius=8)
        table_frame.pack(fill="x", padx=padx, pady=pady)

        for column_index in range(column_count):
            table_frame.grid_columnconfigure(column_index, weight=1, uniform="chat_table")

        for row_index, row in enumerate(rows):
            is_header = row_index == 0
            for column_index in range(column_count):
                cell_text = self.clean_inline_markdown(row[column_index] if column_index < len(row) else "")
                cell_frame = ctk.CTkFrame(
                    table_frame,
                    fg_color="#2f2f2f" if is_header else "#1f1f1f",
                    corner_radius=0,
                    border_width=1,
                    border_color="#4c4c4c",
                )
                cell_frame.grid(row=row_index, column=column_index, sticky="nsew", padx=0, pady=0)
                cell_label = ctk.CTkLabel(
                    cell_frame,
                    text=cell_text,
                    text_color=style["text_color"],
                    font=self.ui_font("chat_body", "bold" if is_header else None),
                    anchor="w",
                    justify="left",
                    width=cell_width,
                    wraplength=max(90, cell_width - 18),
                )
                cell_label.pack(fill="both", expand=True, padx=8, pady=7)

    def render_text_content(self, parent, text, style, padx=14, pady=(0, 8)):
        for block_type, block_text in self.split_rich_text_blocks(text):
            if block_type == "table":
                self.render_table_content(parent, block_text, style, padx=padx, pady=pady)
                continue

            if block_type == "mono":
                textbox = ctk.CTkTextbox(
                    parent,
                    width=self.chat_content_width,
                    height=self.estimate_textbox_height(block_text),
                    wrap="none",
                    font=ctk.CTkFont(family="Consolas", size=self.ui_font_sizes.get("chat_body", 14)),
                    text_color=style["text_color"],
                    fg_color="#171717",
                    border_color="#555555",
                    border_width=1,
                    corner_radius=8,
                )
                textbox.pack(fill="x", padx=padx, pady=pady)
                textbox.insert("1.0", block_text)
                textbox.configure(state="disabled")
                continue

            label = ctk.CTkLabel(
                parent,
                text=self.clean_inline_markdown(block_text),
                text_color=style["text_color"],
                font=self.ui_font("chat_body"),
                anchor="w",
                justify="left",
                wraplength=self.chat_text_wrap,
            )
            label.pack(fill="x", padx=padx, pady=pady)

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
            "attachments": item.get("attachments", []),
        }

    def build_ai_response_item(self, response, provider, timestamp=""):
        return {
            "role": "assistant",
            "kind": "result",
            "title": "AI 回覆",
            "content": "",
            "timestamp": timestamp,
            "meta": {"provider": provider[1], "model": provider[5]},
            "sections": [
                {
                    "title": "",
                    "content": response,
                },
            ],
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

        theme_styles = self.get_chat_theme_styles()
        bubble_styles = {
            "user": theme_styles["user"],
            "assistant": theme_styles["assistant"],
            "system": theme_styles["system"],
            "tool": theme_styles["tool"],
        }
        kind_overrides = {
            "error": {"fg_color": "#3d3d3d", "text_color": "#ffffff", "header_color": "#ffffff"},
            "warning": {"fg_color": "#363636", "text_color": "#f7f7f7", "header_color": "#ffffff"},
            "status": {"fg_color": "#303030", "text_color": "#eeeeee", "header_color": "#f2f2f2"},
            "result": theme_styles["assistant"],
        }

        style = dict(bubble_styles.get(role, bubble_styles["assistant"]))
        style.update(kind_overrides.get(kind, {}))

        row_frame = ctk.CTkFrame(self.chat_display, fg_color="transparent")
        row_frame.pack(fill="x", padx=10, pady=6)

        bubble_frame = ctk.CTkFrame(
            row_frame,
            fg_color=style["fg_color"],
            corner_radius=14,
            width=self.chat_bubble_max_width,
        )
        bubble_frame.pack(side=side, anchor="e" if side == "right" else "w", padx=10)

        header_row = ctk.CTkFrame(bubble_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=14, pady=(10, 2))

        header_label = ctk.CTkLabel(
            header_row,
            text=" | ".join(header_parts),
            text_color=style["header_color"],
            font=self.ui_font("chat_meta", "bold"),
            anchor="w",
            justify="left",
        )
        header_label.pack(side="left", fill="x", expand=True)

        copy_text = self.get_chat_item_copy_text(normalized)
        if copy_text:
            copy_button = ctk.CTkButton(
                header_row,
                text="複製",
                width=58,
                height=24,
                font=self.ui_font("chat_meta"),
                fg_color=theme_styles["copy"]["fg_color"],
                hover_color=theme_styles["copy"]["hover_color"],
                text_color=theme_styles["copy"]["text_color"],
            )
            copy_button.configure(command=lambda text=copy_text, button=copy_button: self.copy_text_to_clipboard(text, button))
            copy_button.pack(side="right", padx=(8, 0))

        meta = normalized["meta"] or {}
        if isinstance(meta, dict) and meta:
            meta_line = " | ".join(f"{key}: {self.format_display_value(value)}" for key, value in meta.items())
            if meta_line:
                meta_label = ctk.CTkLabel(
                    bubble_frame,
                    text=meta_line,
                    text_color="#c7c7c7",
                    font=self.ui_font("chat_meta"),
                    anchor="w",
                    justify="left",
                    wraplength=self.chat_text_wrap,
                )
                meta_label.pack(fill="x", padx=14, pady=(0, 4))

        for att in normalized.get("attachments", []):
            try:
                img = Image.open(io.BytesIO(att["data"]))
                max_w = min(400, self.chat_content_width)
                ratio = max_w / img.width if img.width > max_w else 1.0
                new_size = (int(img.width * ratio), int(img.height * ratio))
                ctk_img = ctk.CTkImage(img, size=new_size)
                img_label = ctk.CTkLabel(bubble_frame, image=ctk_img, text="")
                img_label.pack(fill="x", padx=14, pady=(4, 4))
            except Exception:
                pass

        content = self.format_display_value(normalized["content"])
        if content:
            self.render_text_content(bubble_frame, content, style)

        for section in normalized["sections"] or []:
            if not isinstance(section, dict):
                self.render_text_content(
                    bubble_frame,
                    self.format_display_value(section),
                    style,
                    pady=(0, 6),
                )
                continue

            section_title = section.get("title", "")
            section_content = self.format_display_value(section.get("content", ""))

            if section_title:
                section_title_label = ctk.CTkLabel(
                    bubble_frame,
                    text=f"[{section_title}]",
                    text_color=style["header_color"],
                    font=self.ui_font("chat_meta", "bold"),
                    anchor="w",
                    justify="left",
                )
                section_title_label.pack(fill="x", padx=14, pady=(2, 2))
            if section_content:
                self.render_text_content(bubble_frame, section_content, style, pady=(0, 6))

        self.update_idletasks()
        if hasattr(self.chat_display, "_parent_canvas"):
            self.chat_display._parent_canvas.yview_moveto(1.0)

    def get_chat_provider_names(self):
        return [provider[1] for provider in get_providers()]

    def show_chat(self):
        self.current_view = "chat"
        self.clear_main()
        self.set_active_nav("chat")

        title = ctk.CTkLabel(
            self.main_frame,
            text="AI 對話區",
            font=self.ui_font("page_title", "bold"),
        )
        title.pack(pady=10)

        toolbar_frame = ctk.CTkFrame(self.main_frame)
        toolbar_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(toolbar_frame, text="使用者", font=self.ui_font("control")).pack(side="left", padx=(10, 6))
        self.user_var = ctk.StringVar()
        self.user_combo = ctk.CTkComboBox(toolbar_frame, values=[], variable=self.user_var, command=self.on_user_changed, width=220)
        self.user_combo.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(toolbar_frame, text="供應商", font=self.ui_font("control")).pack(side="left", padx=(0, 6))
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
            font=self.ui_font("control", "bold"),
        )
        self.current_conversation_label.pack(side="left", padx=12, pady=8)

        history_frame = ctk.CTkFrame(self.main_frame)
        history_frame.pack(padx=20, pady=(0, 8), fill="x")

        history_header = ctk.CTkFrame(history_frame, fg_color="transparent")
        history_header.pack(fill="x", padx=8, pady=(6, 6))

        self.history_summary_label = ctk.CTkLabel(
            history_header,
            text="歷史對話",
            font=self.ui_font("control", "bold"),
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

        self.attach_frame = ctk.CTkFrame(input_frame, fg_color="transparent", height=60)
        self.attach_frame.pack(fill="x", padx=8, pady=(0, 4))
        self.attach_frame.pack_forget()

        input_row = ctk.CTkFrame(input_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=8, pady=(0, 8))

        self.msg_entry = ctk.CTkTextbox(
            input_row,
            height=self.input_min_height,
            corner_radius=10,
            font=self.ui_font("input"),
        )
        self.msg_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.msg_entry.bind("<KeyRelease>", self.autosize_input_box)
        self.msg_entry.bind("<Return>", self.on_input_return)
        self.msg_entry.bind("<<Paste>>", self.on_paste)

        self.btn_attach = ctk.CTkButton(
            input_row, text="📎", width=40, command=self.attach_file,
            font=ctk.CTkFont(size=16),
        )
        self.btn_attach.pack(side="right", padx=(0, 4))

        self.btn_send = ctk.CTkButton(input_row, text="傳送", width=80, command=self.send_message)
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
            self.chat_provider_status.configure(text="請先到系統環境設定新增供應商", text_color="orange")

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
            if message[2] == "assistant":
                provider = get_active_provider()
                if provider:
                    self.render_chat_item(self.build_ai_response_item(message[3], provider, message[4]))
                    continue

            self.render_chat_item({"role": message[2], "content": message[3], "timestamp": message[4]})

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
                    "content": "請先到「系統環境設定」新增並驗證 API 供應商",
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

        attachments = list(self.attachments)
        self.render_chat_item({"role": "user", "content": message_text, "attachments": attachments})
        self.clear_input_text()
        self.render_chat_item(
            {
                "role": "assistant",
                "kind": "status",
                "title": "處理中",
                "content": "正在產生回答。",
                "meta": {"provider": provider[1], "model": provider[5]},
            }
        )
        self.update()

        thread = threading.Thread(
            target=self._do_api_call,
            args=(provider, message_text, attachments),
            daemon=True,
        )
        thread.start()

    def _build_multimodal_content(self, text, attachments):
        if not attachments:
            return text
        parts = [{"type": "text", "text": text or "（附件）"}]
        for att in attachments:
            b64 = base64.b64encode(att["data"]).decode("utf-8")
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{att['mime']};base64,{b64}"},
            })
        return parts

    def _do_api_call(self, provider, message_text, attachments):
        try:
            user_content = self._build_multimodal_content(message_text, attachments)
            save_message(self.current_conversation[0], "user", message_text)

            message_rows = get_messages(self.current_conversation[0])
            messages = [{"role": row[2], "content": row[3]} for row in message_rows]
            messages[-1]["content"] = user_content
            knowledge_context, knowledge_matches = build_knowledge_context(message_text)
            if knowledge_context:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": (
                            "以下是本機向量知識庫檢索到的相關資料。"
                            "回答時請優先參考這些內容；若資料不足，請明確說明不足之處。\n\n"
                            f"{knowledge_context}"
                        ),
                    },
                )

            response = call_provider(
                provider[2],
                provider[4],
                provider[3],
                provider[5],
                messages,
            )
            self.after(0, self._handle_api_response, response, provider, knowledge_matches)
        except Exception as exc:
            self.after(0, self._render_api_error, str(exc), provider)

    def _handle_api_response(self, response, provider, knowledge_matches):
        self.render_chat_item(self.build_ai_response_item(response, provider))
        save_message(self.current_conversation[0], "assistant", response)

    def _render_api_error(self, error_text, provider):
        self.render_chat_item(
            {
                "role": "system",
                "kind": "error",
                "title": "對話處理失敗",
                "content": error_text,
                "meta": {"provider": provider[1], "model": provider[5]},
            }
        )

    def show_users(self):
        self.current_view = "users"
        self.clear_main()
        self.set_active_nav("users")

        title = ctk.CTkLabel(
            self.main_frame,
            text="使用者資料區",
            font=self.ui_font("page_title", "bold"),
        )
        title.pack(pady=10)

        add_frame = ctk.CTkFrame(self.main_frame)
        add_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(add_frame, text="使用者名稱:", font=self.ui_font("control")).pack(side="left", padx=5)
        self.new_username = ctk.CTkEntry(add_frame, width=200, font=self.ui_font("control"))
        self.new_username.pack(side="left", padx=5)

        ctk.CTkLabel(add_frame, text="Email:", font=self.ui_font("control")).pack(side="left", padx=5)
        self.new_email = ctk.CTkEntry(add_frame, width=200, font=self.ui_font("control"))
        self.new_email.pack(side="left", padx=5)

        btn_add = ctk.CTkButton(add_frame, text="建立使用者", font=self.ui_font("control"), command=self.add_new_user)
        btn_add.pack(side="left", padx=10)

        list_frame = ctk.CTkFrame(self.main_frame)
        list_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.user_list = ctk.CTkTextbox(list_frame, wrap="word", font=self.ui_font("control"))
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
        self.current_view = "settings"
        self.clear_main()
        self.set_active_nav("settings")

        title = ctk.CTkLabel(
            self.main_frame,
            text="系統環境設定",
            font=self.ui_font("page_title", "bold"),
        )
        self.settings_title_label = title
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

        tab_system = notebook.add("系統環境設定")

        ctk.CTkLabel(tab_system, text="預設模型:", font=self.ui_font("control")).pack(padx=10, pady=10, anchor="w")
        self.sys_model = ctk.CTkEntry(tab_system, width=260, font=self.ui_font("control"))
        self.sys_model.pack(padx=10, pady=5, anchor="w")
        self.sys_model.insert(0, get_setting("default_model", ""))

        font_frame = ctk.CTkFrame(tab_system)
        font_frame.pack(padx=10, pady=(16, 10), fill="x")

        ctk.CTkLabel(
            font_frame,
            text="UI 字體大小",
            font=self.ui_font("control", "bold"),
        ).grid(row=0, column=0, columnspan=3, padx=10, pady=(10, 6), sticky="w")

        self.font_size_vars = {}
        for row_index, (key, label) in enumerate(UI_FONT_LABELS.items(), start=1):
            ctk.CTkLabel(font_frame, text=label, font=self.ui_font("control")).grid(
                row=row_index,
                column=0,
                padx=10,
                pady=5,
                sticky="w",
            )
            value_var = ctk.StringVar(value=str(self.ui_font_sizes.get(key, UI_FONT_DEFAULTS[key])))
            self.font_size_vars[key] = value_var
            size_entry = ctk.CTkEntry(font_frame, width=72, textvariable=value_var, font=self.ui_font("control"))
            size_entry.grid(row=row_index, column=1, padx=10, pady=5, sticky="w")
            ctk.CTkLabel(font_frame, text="px", text_color="#a8a8a8", font=self.ui_font("control")).grid(
                row=row_index,
                column=2,
                padx=(0, 10),
                pady=5,
                sticky="w",
            )

        chat_frame = ctk.CTkFrame(tab_system)
        chat_frame.pack(padx=10, pady=(8, 10), fill="x")

        ctk.CTkLabel(
            chat_frame,
            text="對話區顯示",
            font=self.ui_font("control", "bold"),
        ).grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 6), sticky="w")

        ctk.CTkLabel(chat_frame, text="訊息顯示寬度", font=self.ui_font("control")).grid(
            row=1,
            column=0,
            padx=10,
            pady=5,
            sticky="w",
        )
        self.chat_width_var = ctk.StringVar(value=str(self.chat_bubble_setting_width))
        self.chat_width_entry = ctk.CTkEntry(
            chat_frame,
            width=90,
            textvariable=self.chat_width_var,
            font=self.ui_font("control"),
        )
        self.chat_width_entry.grid(row=1, column=1, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(chat_frame, text="對話配色", font=self.ui_font("control")).grid(
            row=2,
            column=0,
            padx=10,
            pady=5,
            sticky="w",
        )
        self.chat_theme_var = ctk.StringVar(value=self.chat_color_theme)
        self.chat_theme_combo = ctk.CTkComboBox(
            chat_frame,
            values=CHAT_THEME_OPTIONS,
            variable=self.chat_theme_var,
            width=160,
            font=self.ui_font("control"),
        )
        self.chat_theme_combo.grid(row=2, column=1, padx=10, pady=5, sticky="w")

        self.font_settings_status = ctk.CTkLabel(tab_system, text="", font=self.ui_font("control"))
        self.font_settings_status.pack(padx=10, pady=(0, 6), anchor="w")

        btn_save_sys = ctk.CTkButton(
            tab_system,
            text="儲存系統環境設定",
            font=self.ui_font("control"),
            command=self.save_system_settings,
        )
        btn_save_sys.pack(padx=10, pady=10, anchor="w")

        self.refresh_provider_controls()
        self.apply_font_to_tree(notebook)

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
        new_sizes = {}
        for key, default_size in UI_FONT_DEFAULTS.items():
            value_var = self.font_size_vars.get(key)
            raw_value = value_var.get().strip() if value_var else str(default_size)
            try:
                size = int(raw_value)
            except ValueError:
                size = default_size
            size = max(9, min(32, size))
            new_sizes[key] = size
        save_ui_font_sizes(new_sizes)

        raw_chat_width = self.chat_width_var.get().strip() if hasattr(self, "chat_width_var") else str(self.chat_bubble_setting_width)
        try:
            chat_width = int(raw_chat_width)
        except ValueError:
            chat_width = 860
        chat_width = max(520, min(1100, chat_width))
        chat_theme = self.chat_theme_var.get().strip() if hasattr(self, "chat_theme_var") else self.chat_color_theme
        chat_theme = chat_theme if chat_theme in CHAT_THEME_STYLES else "黑灰白"
        save_chat_bubble_width(chat_width)
        save_chat_color_theme(chat_theme)

        self.ui_font_sizes = new_sizes
        self.chat_bubble_setting_width = chat_width
        self.chat_color_theme = chat_theme
        self.configure_chat_display()
        self.apply_ui_fonts()
        self.apply_font_to_tree(self.main_frame)
        if hasattr(self, "settings_title_label"):
            self.settings_title_label.configure(font=self.ui_font("page_title", "bold"))
        if hasattr(self, "chat_width_var"):
            self.chat_width_var.set(str(chat_width))
        if hasattr(self, "chat_theme_var"):
            self.chat_theme_var.set(chat_theme)
        if hasattr(self, "font_settings_status"):
            self.font_settings_status.configure(text="已儲存系統環境設定，UI 字體與對話區顯示已套用。", text_color="lightgreen")

    def show_knowledge(self):
        self.current_view = "knowledge"
        self.clear_main()
        self.set_active_nav("knowledge")
        self.kb_selected_files = []

        title = ctk.CTkLabel(
            self.main_frame,
            text="知識庫",
            font=self.ui_font("page_title", "bold"),
        )
        title.pack(pady=10)

        upload_frame = ctk.CTkFrame(self.main_frame)
        upload_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(upload_frame, text="選擇文件:", font=self.ui_font("control")).pack(side="left", padx=5)

        self.kb_file_btn = ctk.CTkButton(
            upload_frame, text="選擇多個檔案...", font=self.ui_font("control"),
            command=self.select_kb_files,
        )
        self.kb_file_btn.pack(side="left", padx=5)

        self.kb_file_label = ctk.CTkLabel(upload_frame, text="", font=self.ui_font("control"))
        self.kb_file_label.pack(side="left", padx=5)

        self.btn_upload_kb = ctk.CTkButton(
            upload_frame,
            text="批次上傳並向量化",
            font=self.ui_font("control"),
            command=self.batch_upload_knowledge,
        )
        self.btn_upload_kb.pack(side="left", padx=5)

        self.kb_status_label = ctk.CTkLabel(upload_frame, text="", font=self.ui_font("control"))
        self.kb_status_label.pack(side="left", padx=10)

        action_frame = ctk.CTkFrame(self.main_frame)
        action_frame.pack(padx=20, pady=(0, 10), fill="x")

        self.btn_kb_backup = ctk.CTkButton(
            action_frame, text="備份知識庫", font=self.ui_font("control"),
            command=self.backup_knowledge_base, width=120,
        )
        self.btn_kb_backup.pack(side="left", padx=5)

        self.btn_kb_restore = ctk.CTkButton(
            action_frame, text="還原知識庫", font=self.ui_font("control"),
            command=self.restore_knowledge_base, width=120,
        )
        self.btn_kb_restore.pack(side="left", padx=5)

        self.btn_kb_delete = ctk.CTkButton(
            action_frame, text="刪除選取文件", font=self.ui_font("control"),
            command=self.delete_knowledge_doc_handler, width=120,
            fg_color="#8b3a3a", hover_color="#a04545",
        )
        self.btn_kb_delete.pack(side="left", padx=5)

        self.kb_doc_selector = ctk.CTkComboBox(
            action_frame, values=[""],
            font=self.ui_font("control"), width=300,
            state="readonly",
        )
        self.kb_doc_selector.pack(side="left", padx=5)

        list_frame = ctk.CTkFrame(self.main_frame)
        list_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.kb_list = ctk.CTkTextbox(list_frame, wrap="word", font=self.ui_font("control"))
        self.kb_list.pack(padx=10, pady=10, fill="both", expand=True)

        self.refresh_knowledge_list()

    def select_kb_files(self):
        import tkinter.filedialog

        file_paths = tkinter.filedialog.askopenfilenames(
            filetypes=[("文字檔", "*.txt *.md"), ("所有檔案", "*.*")]
        )
        if file_paths:
            self.kb_selected_files = list(file_paths)
            names = [os.path.basename(p) for p in self.kb_selected_files]
            if len(names) <= 3:
                self.kb_file_label.configure(text=", ".join(names))
            else:
                self.kb_file_label.configure(text=f"{len(names)} 個檔案已選取")
            if hasattr(self, "kb_status_label"):
                self.kb_status_label.configure(text="")

    def batch_upload_knowledge(self):
        if not self.kb_selected_files:
            return
        self.btn_upload_kb.configure(state="disabled", text="處理中...")
        self.kb_status_label.configure(text="")

        def process():
            total_ok = 0
            total_err = 0
            for i, file_path in enumerate(self.kb_selected_files):
                try:
                    filename = os.path.basename(file_path)
                    ts = datetime.now().strftime("%Y%m%d%H%M%S")
                    stored_name = f"{ts}_{filename}"
                    stored_path = os.path.join(KB_SOURCE_DIR, stored_name)
                    shutil.copy2(file_path, stored_path)
                    content = read_text_file(stored_path)
                    doc_id = save_knowledge_doc(filename, content, stored_path)
                    chunk_count = vectorize_knowledge_doc(doc_id, filename, content)
                    total_ok += 1
                    msg = f"({i+1}/{len(self.kb_selected_files)}) {filename} → {chunk_count} chunks"
                    self.after(0, self.kb_status_label.configure, {"text": msg, "text_color": "lightgreen"})
                except Exception as exc:
                    total_err += 1
                    self.after(
                        0, self.kb_list.insert, "end",
                        f"錯誤: {os.path.basename(file_path)} → {exc}\n",
                    )
            self.after(0, self.batch_upload_done, total_ok, total_err)

        threading.Thread(target=process, daemon=True).start()

    def batch_upload_done(self, total_ok, total_err):
        self.btn_upload_kb.configure(state="normal", text="批次上傳並向量化")
        self.kb_selected_files = []
        self.kb_file_label.configure(text="")
        status = f"完成: {total_ok} 個成功"
        if total_err:
            status += f", {total_err} 個失敗"
        self.kb_status_label.configure(text=status, text_color="lightgreen" if not total_err else "orange")
        self.refresh_knowledge_list()

    def backup_knowledge_base(self):
        import tkinter.filedialog
        path = tkinter.filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("Zip 檔案", "*.zip")],
            title="備份知識庫",
        )
        if not path:
            return
        try:
            result = backup_knowledge(path)
            self.kb_status_label.configure(text=f"備份完成: {result}", text_color="lightgreen")
        except Exception as exc:
            self.kb_status_label.configure(text=f"備份失敗: {exc}", text_color="red")

    def restore_knowledge_base(self):
        import tkinter.filedialog
        path = tkinter.filedialog.askopenfilename(
            filetypes=[("Zip 檔案", "*.zip")],
            title="還原知識庫",
        )
        if not path:
            return
        import tkinter.messagebox
        confirm = tkinter.messagebox.askyesno(
            "確認還原",
            "還原將會覆蓋現有的向量資料與來源檔案。\n建議先備份目前的知識庫。\n確定要繼續嗎？",
        )
        if not confirm:
            return
        success, msg = restore_knowledge(path)
        self.kb_status_label.configure(text=msg, text_color="lightgreen" if success else "red")
        if success:
            self.refresh_knowledge_list()

    def delete_knowledge_doc_handler(self):
        selected = self.kb_doc_selector.get() if hasattr(self, "kb_doc_selector") else ""
        if not selected:
            return
        doc_id_str = selected.split(" (id:")[-1].rstrip(")") if " (id:" in selected else ""
        if not doc_id_str.isdigit():
            return
        doc_id = int(doc_id_str)
        import tkinter.messagebox
        if not tkinter.messagebox.askyesno("確認刪除", f"確定要刪除「{selected}」及其向量資料？"):
            return
        delete_knowledge_doc(doc_id)
        self.kb_status_label.configure(text=f"已刪除: {selected}", text_color="orange")
        self.refresh_knowledge_list()

    def refresh_knowledge_list(self):
        self.kb_list.delete("1.0", "end")
        self.kb_list.insert("end", f"本機向量索引: {get_local_vector_stats()} 個片段\n")
        chroma_path = os.path.join(KB_DIR, "chroma.sqlite3")
        if os.path.exists(chroma_path):
            self.kb_list.insert("end", "偵測到既有 Chroma 向量庫: knowledge_base/chroma.sqlite3\n")
        self.kb_list.insert("end", "\n")
        docs = get_knowledge_docs()
        doc_names = []
        for document in docs:
            chunk_count = document[5] if len(document) > 5 and document[5] is not None else 0
            vector_status = document[6] if len(document) > 6 and document[6] else "unknown"
            label = f"{document[1]} (id:{document[0]}) - {vector_status}/{chunk_count}"
            doc_names.append(label)
            self.kb_list.insert(
                "end",
                f"• {document[1]} - 上傳於 {document[3]} - 向量狀態: {vector_status} / {chunk_count} chunks\n",
            )
        if hasattr(self, "kb_doc_selector"):
            self.kb_doc_selector.configure(values=[""] + doc_names)
            self.kb_doc_selector.set("")

    def show_tools(self):
        self.current_view = "tools"
        self.clear_main()
        self.set_active_nav("tools")

        title = ctk.CTkLabel(
            self.main_frame,
            text="AI Tools & Skills",
            font=self.ui_font("page_title", "bold"),
        )
        title.pack(pady=10)

        info_frame = ctk.CTkFrame(self.main_frame)
        info_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(info_frame, text="可用工具:", font=self.ui_font("control", "bold")).pack(anchor="w", padx=10, pady=5)
        tools = [
            "• 資料庫查詢 - AI 可直接查詢 SQLite 資料庫",
            "• 執行指令 - AI 可執行系統指令",
            "• 檔案操作 - AI 可讀寫檔案",
            "• 天氣查詢 - 查詢天氣資訊",
        ]
        for tool_text in tools:
            ctk.CTkLabel(info_frame, text=tool_text, font=self.ui_font("control")).pack(anchor="w", padx=20)

        ctk.CTkLabel(info_frame, text="可用 Skills:", font=self.ui_font("control", "bold")).pack(anchor="w", padx=10, pady=(20, 5))
        skills = [
            "• Code Interpreter - 執行 Python 程式碼",
            "• Web Search - 搜尋網路",
            "• Knowledge Retrieval - 從知識庫擷取資訊",
        ]
        for skill_text in skills:
            ctk.CTkLabel(info_frame, text=skill_text, font=self.ui_font("control")).pack(anchor="w", padx=20)

        test_frame = ctk.CTkFrame(self.main_frame)
        test_frame.pack(padx=20, pady=10, fill="x")

        ctk.CTkLabel(test_frame, text="SQL 測試:", font=self.ui_font("control")).pack(side="left", padx=5)
        self.sql_test = ctk.CTkEntry(test_frame, width=320, font=self.ui_font("control"))
        self.sql_test.pack(side="left", padx=5)
        self.sql_test.insert(0, "SELECT * FROM users")

        btn_test = ctk.CTkButton(test_frame, text="執行", font=self.ui_font("control"), command=self.test_sql)
        btn_test.pack(side="left", padx=5)

        self.sql_result = ctk.CTkTextbox(self.main_frame, height=220, font=self.ui_font("control"))
        self.sql_result.pack(padx=20, pady=10, fill="both", expand=True)

    def _is_read_only_query(self, query: str) -> bool:
        stripped = query.strip().upper()
        if not stripped:
            return False
        if ";" in stripped.rstrip(";"):
            return False
        return stripped.startswith("SELECT") or stripped.startswith("PRAGMA") or stripped.startswith("EXPLAIN")

    def test_sql(self):
        query = self.sql_test.get().strip()
        if not self._is_read_only_query(query):
            self.sql_result.delete("1.0", "end")
            self.sql_result.insert("end", "錯誤: 僅允許 SELECT / PRAGMA / EXPLAIN 等唯讀查詢\n")
            return
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
