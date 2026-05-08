import json
import os

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "讀取專案資料夾中的檔案內容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相對於專案資料夾的檔案路徑",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "寫入內容到專案資料夾中的檔案（會覆蓋既有檔案）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相對於專案資料夾的檔案路徑",
                    },
                    "content": {
                        "type": "string",
                        "description": "要寫入的檔案內容",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出專案資料夾中指定目錄的檔案與子資料夾",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相對於專案資料夾的目錄路徑（留空則列出根目錄）",
                    }
                },
                "required": [],
            },
        },
    },
]


def _get_project_root(messages) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "system" and "專案資料夾" in msg.get("content", ""):
            for line in msg["content"].splitlines():
                line = line.strip()
                if line.startswith("你有一個專案資料夾") and "：" in line:
                    return line.split("：", 1)[1].strip()
    return ""


def handle_tool_call(tool_name: str, args: dict, project_root: str) -> str:
    if not project_root or not os.path.isdir(project_root):
        return json.dumps({"error": "找不到有效的專案資料夾"})

    safe_path = os.path.normpath(os.path.join(project_root, args.get("path", "")))
    if not safe_path.startswith(os.path.normpath(project_root)):
        return json.dumps({"error": "不允許存取專案資料夾以外的路徑"})

    try:
        if tool_name == "read_file":
            if not os.path.isfile(safe_path):
                return json.dumps({"error": f"檔案不存在: {args.get('path')}"})
            with open(safe_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            return json.dumps({"content": content, "path": args.get("path")})

        if tool_name == "write_file":
            os.makedirs(os.path.dirname(safe_path), exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(args.get("content", ""))
            return json.dumps({"status": "ok", "path": args.get("path")})

        if tool_name == "list_files":
            target = safe_path if os.path.isdir(safe_path) else project_root
            entries = []
            for entry in sorted(os.scandir(target), key=lambda e: (not e.is_dir(), e.name.lower())):
                if not entry.name.startswith("."):
                    entries.append({"name": entry.name, "type": "dir" if entry.is_dir() else "file"})
            return json.dumps({"entries": entries, "path": args.get("path", "")})

    except Exception as e:
        return json.dumps({"error": str(e)})

    return json.dumps({"error": f"未知工具: {tool_name}"})
