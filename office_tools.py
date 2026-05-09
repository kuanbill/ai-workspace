import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from data.db import get_setting
except Exception:
    get_setting = None


BASE_DIR = Path(__file__).resolve().parent
OFFICE_ROOT = BASE_DIR / "skills" / "office"
OFFICE_PUBLIC = OFFICE_ROOT / "public"
VENDOR_DIR = BASE_DIR / "vendor"
TEMP_TOOL_ROOT = Path(os.environ.get("TEMP", "")) / "office_local_tools"
LOCAL_TOOL_ROOTS = [
    TEMP_TOOL_ROOT,
    BASE_DIR / "tool_runtime",
    BASE_DIR / "local_tools",
]
TOOL_SETTING_KEYS = {
    "pandoc": "pandoc_path",
    "soffice": "soffice_path",
    "pdftoppm": "pdftoppm_path",
}

if VENDOR_DIR.exists():
    vendor_str = str(VENDOR_DIR)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)


OFFICE_DOCS = {
    "docx_skill": OFFICE_PUBLIC / "docx" / "SKILL.md",
    "docx_ooxml": OFFICE_PUBLIC / "docx" / "ooxml.md",
    "docx_js": OFFICE_PUBLIC / "docx" / "docx-js.md",
    "pptx_skill": OFFICE_PUBLIC / "pptx" / "SKILL.md",
    "pptx_ooxml": OFFICE_PUBLIC / "pptx" / "ooxml.md",
    "pptx_html2pptx": OFFICE_PUBLIC / "pptx" / "html2pptx.md",
    "xlsx_skill": OFFICE_PUBLIC / "xlsx" / "SKILL.md",
    "pdf_skill": OFFICE_PUBLIC / "pdf" / "SKILL.md",
    "pdf_forms": OFFICE_PUBLIC / "pdf" / "FORMS.md",
    "pdf_reference": OFFICE_PUBLIC / "pdf" / "REFERENCE.md",
}


OFFICE_SCRIPTS = {
    "docx_unpack": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "docx" / "ooxml" / "scripts" / "unpack.py",
        "args_template": ["input_path", "output_dir"],
    },
    "docx_pack": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "docx" / "ooxml" / "scripts" / "pack.py",
        "args_template": ["input_dir", "output_path"],
    },
    "docx_validate": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "docx" / "ooxml" / "scripts" / "validate.py",
        "args_template": ["input_dir", "--original", "input_path"],
    },
    "pptx_unpack": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pptx" / "ooxml" / "scripts" / "unpack.py",
        "args_template": ["input_path", "output_dir"],
    },
    "pptx_pack": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pptx" / "ooxml" / "scripts" / "pack.py",
        "args_template": ["input_dir", "output_path"],
    },
    "pptx_validate": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pptx" / "ooxml" / "scripts" / "validate.py",
        "args_template": ["input_dir", "--original", "input_path"],
    },
    "pptx_inventory": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pptx" / "scripts" / "inventory.py",
        "args_template": ["input_path", "output_path"],
    },
    "pptx_thumbnail": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pptx" / "scripts" / "thumbnail.py",
        "args_template": ["input_path", "output_path"],
    },
    "xlsx_recalc": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "xlsx" / "recalc.py",
        "args_template": ["input_path"],
    },
    "pdf_extract_form_fields": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pdf" / "scripts" / "extract_form_field_info.py",
        "args_template": ["input_path", "output_path"],
    },
    "pdf_fill_form_fields": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pdf" / "scripts" / "fill_fillable_fields.py",
        "args_template": ["input_path", "json_path", "output_path"],
    },
    "pdf_convert_to_images": {
        "runtime": "python",
        "script": OFFICE_PUBLIC / "pdf" / "scripts" / "convert_pdf_to_images.py",
        "args_template": ["input_path", "output_dir"],
    },
}


SCRIPT_DEPENDENCIES = {
    "pptx_thumbnail": {"commands": ["soffice", "pdftoppm"], "python_modules": ["PIL", "pptx"]},
    "pptx_inventory": {"python_modules": ["pptx"]},
    "xlsx_recalc": {"commands": ["soffice"], "python_modules": ["openpyxl"]},
    "pdf_extract_form_fields": {"python_modules": ["pypdf"]},
    "pdf_fill_form_fields": {"python_modules": ["pypdf"]},
    "pdf_convert_to_images": {"commands": ["pdftoppm"], "python_modules": ["pdf2image", "PIL"]},
    "docx_validate": {"python_modules": ["defusedxml"]},
    "pptx_validate": {"python_modules": ["defusedxml"]},
}


def _find_command(command_name: str) -> str | None:
    configured = _get_configured_command(command_name)
    if configured:
        return configured

    found = shutil.which(command_name)
    if found:
        return found

    for candidate in _get_standard_candidates(command_name):
        if candidate.is_file():
            return str(candidate)

    candidate_names = [command_name]
    if os.name == "nt" and not command_name.lower().endswith(".exe"):
        candidate_names.append(f"{command_name}.exe")

    for root in LOCAL_TOOL_ROOTS:
        if not root.exists():
            continue
        for candidate_name in candidate_names:
            matches = list(root.rglob(candidate_name))
            if matches:
                file_match = next((match for match in matches if match.is_file()), None)
                if file_match:
                    return str(file_match)
    return None


def _get_configured_command(command_name: str) -> str | None:
    if get_setting is None:
        return None
    key = TOOL_SETTING_KEYS.get(command_name)
    if not key:
        return None
    try:
        configured = (get_setting(key, "") or "").strip()
    except Exception:
        return None
    if configured and os.path.isfile(configured):
        return configured
    return None


def _get_standard_candidates(command_name: str) -> list[Path]:
    candidates: list[Path] = []
    if os.name != "nt":
        return candidates

    program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
    local_app_data = os.environ.get("LOCALAPPDATA")

    if command_name == "soffice":
        for base in program_files:
            if base:
                candidates.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    elif command_name == "pandoc":
        for base in program_files:
            if base:
                candidates.append(Path(base) / "Pandoc" / "pandoc.exe")
    elif command_name == "pdftoppm" and local_app_data:
        candidates.extend(
            Path(local_app_data).glob(
                "Microsoft/WinGet/Packages/oschwartz10612.Poppler_*/poppler-*/Library/bin/pdftoppm.exe"
            )
        )
    return candidates


def _has_python_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def get_office_environment_status() -> dict:
    system_name = platform.system()
    commands = {
        "python": _find_command("python"),
        "node": _find_command("node"),
        "npm": _find_command("npm"),
        "pandoc": _find_command("pandoc"),
        "soffice": _find_command("soffice"),
        "pdftoppm": _find_command("pdftoppm"),
    }
    modules = {
        "openpyxl": _has_python_module("openpyxl"),
        "pypdf": _has_python_module("pypdf"),
        "defusedxml": _has_python_module("defusedxml"),
        "python_docx": _has_python_module("docx"),
        "python_pptx": _has_python_module("pptx"),
        "PIL": _has_python_module("PIL"),
    }
    node_modules = OFFICE_ROOT / "node_modules"
    packages = {
        "pptxgenjs": (node_modules / "pptxgenjs").exists(),
        "playwright": (node_modules / "playwright").exists(),
        "react": (node_modules / "react").exists(),
        "react_dom": (node_modules / "react-dom").exists(),
        "sharp": (node_modules / "sharp").exists(),
    }
    script_status = {}
    for script_id in OFFICE_SCRIPTS:
        script_status[script_id] = _check_script_dependencies(script_id)
    recommended_installs = {
        "Linux": {
            "pandoc": "sudo apt-get update && sudo apt-get install -y pandoc",
            "soffice": "sudo apt-get update && sudo apt-get install -y libreoffice",
            "pdftoppm": "sudo apt-get update && sudo apt-get install -y poppler-utils",
            "python_pptx": "python3 -m pip install python-pptx",
            "node_packages": "cd skills/office && npm install",
        },
        "Darwin": {
            "pandoc": "brew install pandoc",
            "soffice": "brew install --cask libreoffice",
            "pdftoppm": "brew install poppler",
            "python_pptx": "python3 -m pip install python-pptx",
            "node_packages": "cd skills/office && npm install",
        },
        "Windows": {
            "pandoc": "可放在 tool_runtime/pandoc 或於系統環境設定指定 pandoc.exe",
            "soffice": "安裝 LibreOffice 後可於系統環境設定指定 soffice.exe",
            "pdftoppm": "choco install poppler -y",
            "python_pptx": "python -m pip install --target vendor python-pptx",
            "node_packages": "cd skills\\office && npm install",
        },
    }
    return {
        "platform": system_name,
        "office_root": str(OFFICE_ROOT),
        "commands": commands,
        "python_modules": modules,
        "node_packages": packages,
        "scripts": script_status,
        "recommended_installs": recommended_installs.get(system_name, {}),
    }


def _check_script_dependencies(script_id: str) -> dict:
    spec = SCRIPT_DEPENDENCIES.get(script_id, {})
    missing_commands = [
        cmd for cmd in spec.get("commands", [])
        if not _find_command(cmd)
    ]
    missing_modules = [
        mod for mod in spec.get("python_modules", [])
        if not _has_python_module(mod)
    ]
    return {
        "ready": not missing_commands and not missing_modules,
        "missing_commands": missing_commands,
        "missing_python_modules": missing_modules,
    }


def _ensure_relative_to_project(
    project_root: str,
    relative_path: str,
    expect_dir: bool = False,
    must_exist: bool = True,
    create_dir: bool = False,
) -> str:
    if not relative_path:
        raise ValueError("缺少相對路徑")
    root = os.path.normpath(project_root)
    full_path = os.path.normpath(os.path.join(root, relative_path))
    try:
        in_root = os.path.commonpath([root, full_path]) == root
    except ValueError:
        in_root = False
    if not in_root:
        raise ValueError("不允許存取專案資料夾以外的路徑")
    if create_dir:
        os.makedirs(full_path, exist_ok=True)
    elif not must_exist:
        parent_dir = full_path if expect_dir else os.path.dirname(full_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
    if must_exist:
        if expect_dir and not os.path.isdir(full_path):
            raise ValueError(f"目錄不存在: {relative_path}")
        if not expect_dir and not os.path.exists(full_path):
            raise ValueError(f"檔案不存在: {relative_path}")
    return full_path


def _normalize_args(args) -> list[str]:
    if args is None:
        return []
    if not isinstance(args, list) or any(not isinstance(arg, str) for arg in args):
        raise ValueError("args 必須是字串陣列")
    return args


def _run_command(command: list[str], cwd: str, timeout_seconds: int) -> dict:
    env = os.environ.copy()
    if VENDOR_DIR.exists():
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(VENDOR_DIR) if not existing else f"{VENDOR_DIR}{os.pathsep}{existing}"
    
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    completed = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        env=env,
        creationflags=creationflags,
    )
    return {
        "command": command,
        "cwd": cwd,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def read_office_skill_doc(doc_id: str) -> str:
    doc_path = OFFICE_DOCS.get(doc_id)
    if not doc_path or not doc_path.exists():
        return json.dumps({"error": f"找不到 Office skill 文件: {doc_id}"}, ensure_ascii=False)
    try:
        with open(doc_path, encoding="utf-8") as f:
            content = f.read()
        return json.dumps(
            {"doc_id": doc_id, "path": str(doc_path), "content": content},
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def run_project_script(project_root: str, runtime: str, path: str, args=None, timeout_seconds: int = 120) -> str:
    try:
        script_path = _ensure_relative_to_project(project_root, path)
        if not os.path.isfile(script_path):
            return json.dumps({"error": f"檔案不存在: {path}"}, ensure_ascii=False)
        arg_list = _normalize_args(args)
        runtime_cmd = "python" if runtime == "python" else "node"
        runtime_path = _find_command(runtime_cmd)
        if not runtime_path:
            return json.dumps({"error": f"找不到執行環境: {runtime_cmd}"}, ensure_ascii=False)
        result = _run_command(
            [runtime_path, script_path, *arg_list],
            cwd=project_root,
            timeout_seconds=max(1, min(timeout_seconds, 600)),
        )
        result["path"] = path
        return json.dumps(result, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "腳本執行逾時"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def run_office_script(project_root: str, script_id: str, paths: dict | None = None, args=None, timeout_seconds: int = 180) -> str:
    try:
        script_spec = OFFICE_SCRIPTS.get(script_id)
        if not script_spec:
            return json.dumps({"error": f"未知 Office 腳本: {script_id}"}, ensure_ascii=False)

        dep_status = _check_script_dependencies(script_id)
        if not dep_status["ready"]:
            return json.dumps(
                {
                    "error": "Office 腳本依賴不足",
                    "script_id": script_id,
                    "dependency_status": dep_status,
                },
                ensure_ascii=False,
            )

        arg_list = _normalize_args(args)
        path_args = []
        for item in script_spec.get("args_template", []):
            if item.startswith("--"):
                path_args.append(item)
                continue
            if not paths or not paths.get(item):
                return json.dumps(
                    {"error": f"缺少必要路徑參數: {item}", "script_id": script_id},
                    ensure_ascii=False,
                )
            expect_dir = item.endswith("_dir")
            must_exist = item.startswith("input_") or item == "json_path"
            create_dir = item == "output_dir"
            path_args.append(
                _ensure_relative_to_project(
                    project_root,
                    paths[item],
                    expect_dir=expect_dir,
                    must_exist=must_exist,
                    create_dir=create_dir,
                )
            )

        python_runtime = _find_command("python")
        if not python_runtime:
            return json.dumps({"error": "找不到可執行的 Python 環境"}, ensure_ascii=False)

        if script_id in ("pptx_thumbnail", "xlsx_recalc"):
            soffice_path = _find_command("soffice")
            if soffice_path:
                arg_list = ["--soffice-path", soffice_path] + list(arg_list)

        command = [python_runtime, str(script_spec["script"]), *path_args, *arg_list]
        result = _run_command(
            command,
            cwd=str(OFFICE_ROOT),
            timeout_seconds=max(1, min(timeout_seconds, 900)),
        )
        result["script_id"] = script_id
        result["paths"] = paths or {}
        result["dependency_status"] = dep_status
        return json.dumps(result, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Office 腳本執行逾時"}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
