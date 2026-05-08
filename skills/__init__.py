import os
import sys

_SKILL_BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.join(_SKILL_BASE, "office")

SKILL_KEYWORDS = {
    "pptx": {
        "file": os.path.join(SKILL_DIR, "public", "pptx", "SKILL.md"),
        "keywords": ["presentation", "slide", "pptx", "powerpoint", "投影片", "簡報"],
    },
    "docx": {
        "file": os.path.join(SKILL_DIR, "public", "docx", "SKILL.md"),
        "keywords": ["word", "document", "docx", "文件", "word 文件"],
    },
    "pdf": {
        "file": os.path.join(SKILL_DIR, "public", "pdf", "SKILL.md"),
        "keywords": ["pdf", "form", "pdf 表單", "pdf 檔案"],
    },
    "xlsx": {
        "file": os.path.join(SKILL_DIR, "public", "xlsx", "SKILL.md"),
        "keywords": ["excel", "spreadsheet", "xlsx", "試算表", "excel 檔案"],
    },
}


def _detect_skills(message_text: str) -> list[str]:
    lower = message_text.lower()
    matched = []
    for skill_id, info in SKILL_KEYWORDS.items():
        for kw in info["keywords"]:
            if kw.lower() in lower:
                matched.append(skill_id)
                break
    return matched


def _read_skill_file(file_path: str, max_chars: int = 6000) -> str:
    if not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n...（內容過長已截斷）"
        return content
    except Exception:
        return ""


def build_skill_context(message_text: str) -> str:
    matched = _detect_skills(message_text)
    if not matched:
        return ""

    sections = []
    for skill_id in matched:
        file_path = SKILL_KEYWORDS[skill_id]["file"]
        content = _read_skill_file(file_path)
        if content:
            sections.append(f"=== {skill_id.upper()} 技能指南 ===\n\n{content}")

    if not sections:
        return ""

    return (
        "以下是可用的 Office 文件處理技能。請根據使用者需求參考對應的指南來建立、編輯或分析文件。\n\n"
        + "\n\n".join(sections)
    )
