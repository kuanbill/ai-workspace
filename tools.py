import json
import os

from office_tools import (
    get_office_environment_status,
    read_office_skill_doc,
    run_office_script,
    run_project_script,
)

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
            "name": "run_project_python",
            "description": "執行專案資料夾中的 Python 腳本，可用於驅動 Office skill 所需的輔助腳本",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相對於專案資料夾的 Python 腳本路徑",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "傳給腳本的命令列參數",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "執行逾時秒數，預設 120",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_project_node",
            "description": "執行專案資料夾中的 Node.js 腳本，可用於驅動 html2pptx 等 Office workflow",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "相對於專案資料夾的 Node.js 腳本路徑",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "傳給腳本的命令列參數",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "執行逾時秒數，預設 120",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_office_skill_doc",
            "description": "讀取內建 Office skill 文件的完整內容，適用於 DOCX、PPTX、XLSX、PDF 工作流程",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "enum": [
                            "docx_skill",
                            "docx_ooxml",
                            "docx_js",
                            "pptx_skill",
                            "pptx_ooxml",
                            "pptx_html2pptx",
                            "xlsx_skill",
                            "pdf_skill",
                            "pdf_forms",
                            "pdf_reference",
                        ],
                        "description": "要讀取的 Office skill 文件代號",
                    }
                },
                "required": ["doc_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_office_environment_status",
            "description": "檢查 Office skill 所需的命令、Python 模組與 node 套件是否可用",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_office_script",
            "description": "執行內建白名單 Office skill 腳本，例如 unpack/pack/validate、thumbnail、表單欄位提取與填寫、Excel 公式重算",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_id": {
                        "type": "string",
                        "enum": [
                            "docx_unpack",
                            "docx_pack",
                            "docx_validate",
                            "pptx_unpack",
                            "pptx_pack",
                            "pptx_validate",
                            "pptx_inventory",
                            "pptx_thumbnail",
                            "xlsx_recalc",
                            "pdf_extract_form_fields",
                            "pdf_fill_form_fields",
                            "pdf_convert_to_images",
                        ],
                        "description": "Office 腳本代號",
                    },
                    "paths": {
                        "type": "object",
                        "properties": {
                            "input_path": {"type": "string"},
                            "output_path": {"type": "string"},
                            "input_dir": {"type": "string"},
                            "output_dir": {"type": "string"},
                            "json_path": {"type": "string"},
                        },
                        "description": "Office 腳本需要的相對路徑參數，路徑皆相對於專案資料夾",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "額外命令列參數",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "執行逾時秒數，預設 180",
                    },
                },
                "required": ["script_id"],
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
        content = msg.get("content", "")
        if msg.get("role") == "system" and "workspace 目錄" in content:
            for line in content.splitlines():
                line = line.strip()
                if "workspace 目錄為：" in line:
                    return line.split("workspace 目錄為：", 1)[1].strip()
    return ""


def handle_tool_call(tool_name: str, args: dict, project_root: str) -> str:
    if not project_root or not os.path.isdir(project_root):
        return json.dumps({"error": "找不到有效的專案資料夾"})

    project_root = os.path.normpath(project_root)
    safe_path = os.path.normpath(os.path.join(project_root, args.get("path", "")))
    try:
        in_project_root = os.path.commonpath([project_root, safe_path]) == project_root
    except ValueError:
        in_project_root = False
    if not in_project_root:
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

        if tool_name == "run_project_python":
            return run_project_script(
                project_root,
                "python",
                args.get("path", ""),
                args.get("args"),
                args.get("timeout_seconds", 120),
            )

        if tool_name == "run_project_node":
            return run_project_script(
                project_root,
                "node",
                args.get("path", ""),
                args.get("args"),
                args.get("timeout_seconds", 120),
            )

        if tool_name == "read_office_skill_doc":
            return read_office_skill_doc(args.get("doc_id", ""))

        if tool_name == "get_office_environment_status":
            return json.dumps(get_office_environment_status(), ensure_ascii=False)

        if tool_name == "run_office_script":
            return run_office_script(
                project_root,
                args.get("script_id", ""),
                args.get("paths"),
                args.get("args"),
                args.get("timeout_seconds", 180),
            )

        if tool_name == "list_files":
            target = safe_path
            if args.get("path") and not os.path.isdir(target):
                return json.dumps({"error": f"目錄不存在: {args.get('path')}"})
            if not args.get("path"):
                target = project_root
            entries = []
            for entry in sorted(os.scandir(target), key=lambda e: (not e.is_dir(), e.name.lower())):
                if not entry.name.startswith("."):
                    entries.append({"name": entry.name, "type": "dir" if entry.is_dir() else "file"})
            return json.dumps({"entries": entries, "path": args.get("path", "")})

    except Exception as e:
        return json.dumps({"error": str(e)})

    return json.dumps({"error": f"未知工具: {tool_name}"})
