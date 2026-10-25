#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Темы оформления: светлая, тёмная и «как в системе».

Модуль не зависит от tkinter, поэтому его можно использовать и в GUI,
и в диалогах.  Цвета хранятся в одном словаре: любая часть интерфейса
получает актуальные значения через :func:`color` / :func:`palette`.

Режимы:
    ``auto``  — следовать системной теме (проверяется при запуске и
               периодически во время работы);
    ``light`` — всегда светлая;
    ``dark``  — всегда тёмная.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

THEME_AUTO = "auto"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEMES = (THEME_AUTO, THEME_LIGHT, THEME_DARK)

# Русские подписи режимов (перевод выполняется в GUI через tr()).
THEME_LABELS = {
    THEME_AUTO: "Авто",
    THEME_LIGHT: "Светлая",
    THEME_DARK: "Тёмная",
}

LIGHT: dict[str, str] = {
    # Основные поверхности
    "bg": "#f3f5f7",
    "card": "#ffffff",
    "border": "#d8dee6",
    "text": "#1f2937",
    "muted": "#667085",
    "accent": "#1a9ec4",
    "accent_dark": "#1582a2",
    "accent_text": "#ffffff",
    "soft": "#e9edf2",
    # Таблица
    "row_odd": "#fafbfc",
    "heading_bg": "#f0f3f7",
    "heading_fg": "#475467",
    "heading_active": "#e6ebf1",
    "select_bg": "#d9edf6",
    "select_fg": "#0b2530",
    "done_bg": "#eef9f2",
    "done_fg": "#0b6b3a",
    "error_bg": "#fdf2f2",
    "error_fg": "#b42318",
    "working_bg": "#eef5fd",
    "working_fg": "#0b5cad",
    "skipped_bg": "#f6f7f8",
    "warning_bg": "#fdf8ec",
    "warning_fg": "#9a6700",
    "queued_bg": "#f2f7fd",
    "queued_fg": "#475467",
    "empty_fg": "#98a2b3",
    # Кнопки и прочее
    "button_active": "#eef2f6",
    "button_disabled": "#f1f3f5",
    "button_disabled_fg": "#a0a8b3",
    "accent_disabled": "#a9d6e4",
    "progress_trough": "#e2e7ee",
    "art_holder": "#eef2f6",
    "link": "#157b99",
    # Журнал
    "log_info": "#374151",
    "log_ok": "#047857",
    "log_warn": "#b45309",
    "log_error": "#b91c1c",
    "log_debug": "#6b7280",
    # Подсказки
    "tooltip_bg": "#1f2937",
    "tooltip_fg": "#ffffff",
}

DARK: dict[str, str] = {
    # Основные поверхности
    "bg": "#14181d",
    "card": "#1b2026",
    "border": "#2c343d",
    "text": "#e5e9ee",
    "muted": "#98a2b0",
    "accent": "#2bb3d6",
    "accent_dark": "#1f93b1",
    "accent_text": "#0b1a1f",
    "soft": "#20262d",
    # Таблица
    "row_odd": "#1e242a",
    "heading_bg": "#232a32",
    "heading_fg": "#b9c2cd",
    "heading_active": "#2b333c",
    "select_bg": "#24414d",
    "select_fg": "#eaf7fb",
    "done_bg": "#17281f",
    "done_fg": "#6fd39a",
    "error_bg": "#2a1b1c",
    "error_fg": "#ff8d85",
    "working_bg": "#17232f",
    "working_fg": "#7cbcf5",
    "skipped_bg": "#1f242a",
    "warning_bg": "#2a2417",
    "warning_fg": "#e2b93b",
    "queued_bg": "#19232d",
    "queued_fg": "#a9b6c4",
    "empty_fg": "#6b7480",
    # Кнопки и прочее
    "button_active": "#252d35",
    "button_disabled": "#1a1f24",
    "button_disabled_fg": "#5d6672",
    "accent_disabled": "#2b5160",
    "progress_trough": "#2a323b",
    "art_holder": "#232b33",
    "link": "#4fc3e0",
    # Журнал
    "log_info": "#c3cbd5",
    "log_ok": "#5fce9a",
    "log_warn": "#e0ac4a",
    "log_error": "#f27a72",
    "log_debug": "#8b95a2",
    # Подсказки
    "tooltip_bg": "#2b333c",
    "tooltip_fg": "#f2f5f8",
}

PALETTES = {THEME_LIGHT: LIGHT, THEME_DARK: DARK}

_lock = threading.RLock()
_mode = THEME_AUTO
_resolved = THEME_LIGHT


def normalize_mode(value: object) -> str:
    """Приводит сохранённое значение к одному из поддерживаемых режимов."""
    text = str(value or "").strip().lower()
    return text if text in THEMES else THEME_AUTO


def _windows_theme() -> str | None:
    try:
        import winreg  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            key.Close()
        return THEME_LIGHT if int(value) else THEME_DARK
    except Exception:
        return None


def _macos_theme() -> str | None:
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return THEME_LIGHT
    return THEME_DARK if "dark" in result.stdout.strip().lower() else THEME_LIGHT


def _linux_theme() -> str | None:
    # GNOME / Cinnamon / Budgie / большинство современных оболочек.
    commands = (
        ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
        ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
        ["gsettings", "get", "org.cinnamon.desktop.interface", "gtk-theme"],
    )
    for command in commands:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=2.0
            )
        except Exception:
            continue
        if result.returncode != 0:
            continue
        value = result.stdout.strip().lower()
        if not value:
            continue
        if "dark" in value:
            return THEME_DARK
        if "light" in value or "default" in value:
            return THEME_LIGHT
    # Переменная окружения — удобный способ задать тему в нестандартном
    # окружении без DBus.
    env = os.environ.get("BC_THEME", "").strip().lower()
    if env in (THEME_LIGHT, THEME_DARK):
        return env
    gtk_env = os.environ.get("GTK_THEME", "").strip().lower()
    if gtk_env:
        return THEME_DARK if "dark" in gtk_env else THEME_LIGHT
    # KDE Plasma хранит выбранную схему в kdeglobals.
    try:
        with open(
            os.path.expanduser("~/.config/kdeglobals"), encoding="utf-8"
        ) as handle:
            for line in handle:
                low = line.strip().lower()
                if low.startswith("colorscheme="):
                    return THEME_DARK if "dark" in low else THEME_LIGHT
    except OSError:
        pass
    return None


def detect_system_theme() -> str:
    """Определяет системную тему. При неудаче возвращает светлую."""
    if sys.platform == "win32":
        detected = _windows_theme()
    elif sys.platform == "darwin":
        detected = _macos_theme()
    else:
        detected = _linux_theme()
    return detected or THEME_LIGHT


def resolve_mode(mode: object = None) -> str:
    """Режим -> фактическая тема (``light`` или ``dark``)."""
    mode = normalize_mode(_mode if mode is None else mode)
    if mode == THEME_DARK:
        return THEME_DARK
    if mode == THEME_LIGHT:
        return THEME_LIGHT
    return detect_system_theme()


def set_mode(mode: object) -> bool:
    """Задаёт режим и обновляет фактическую тему.

    Возвращает ``True``, если фактическая тема изменилась (например,
    при режиме «авто» система переключилась на тёмную).
    """
    global _mode, _resolved
    new_mode = normalize_mode(mode)
    new_resolved = resolve_mode(new_mode)
    with _lock:
        changed = new_resolved != _resolved
        _mode = new_mode
        _resolved = new_resolved
    return changed


def refresh() -> bool:
    """Перепроверяет системную тему (для режима «авто»)."""
    with _lock:
        mode = _mode
    return set_mode(mode)


def get_mode() -> str:
    with _lock:
        return _mode


def get_resolved() -> str:
    """Фактическая тема: ``light`` или ``dark``."""
    with _lock:
        return _resolved


def is_dark() -> bool:
    return get_resolved() == THEME_DARK


def palette() -> dict[str, str]:
    """Копия текущей палитры (безопасно менять/кэшировать)."""
    with _lock:
        return dict(PALETTES[_resolved])


def color(name: str, default: str = "#000000") -> str:
    """Цвет по имени из текущей палитры."""
    with _lock:
        return PALETTES[_resolved].get(name, default)


def rgb(
    name: str, default: tuple[int, int, int] = (0, 0, 0)
) -> tuple[int, int, int]:
    """Цвет по имени в виде кортежа RGB (для Pillow)."""
    value = color(name, "").lstrip("#")
    if len(value) != 6:
        return default
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return default
