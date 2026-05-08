import configparser
import os
import sys

if getattr(sys, "frozen", False):
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.ini")


def _ensure_config():
    if not os.path.exists(CONFIG_PATH):
        cfg = configparser.ConfigParser()
        cfg["ui_fonts"] = {}
        cfg["chat_display"] = {}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            cfg.write(f)


def get_ui_font_sizes() -> dict[str, int]:
    _ensure_config()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    result = {}
    if cfg.has_section("ui_fonts"):
        for key, val in cfg.items("ui_fonts"):
            try:
                result[key] = max(9, min(32, int(val)))
            except (TypeError, ValueError):
                pass
    return result


def save_ui_font_sizes(fonts: dict[str, int]) -> None:
    _ensure_config()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    if not cfg.has_section("ui_fonts"):
        cfg.add_section("ui_fonts")
    for key, val in fonts.items():
        cfg.set("ui_fonts", key, str(val))
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)


def get_chat_bubble_width(default: int = 860) -> int:
    _ensure_config()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    if cfg.has_option("chat_display", "bubble_width"):
        try:
            return max(520, min(1100, int(cfg.get("chat_display", "bubble_width"))))
        except (TypeError, ValueError):
            pass
    return default


def save_chat_bubble_width(width: int) -> None:
    _ensure_config()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    if not cfg.has_section("chat_display"):
        cfg.add_section("chat_display")
    cfg.set("chat_display", "bubble_width", str(width))
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)


def get_chat_color_theme(default: str = "黑灰白") -> str:
    _ensure_config()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    if cfg.has_option("chat_display", "color_theme"):
        return cfg.get("chat_display", "color_theme")
    return default


def save_chat_color_theme(theme: str) -> None:
    _ensure_config()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH, encoding="utf-8")
    if not cfg.has_section("chat_display"):
        cfg.add_section("chat_display")
    cfg.set("chat_display", "color_theme", theme)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)
