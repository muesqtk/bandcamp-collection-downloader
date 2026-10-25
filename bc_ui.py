#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Базовая часть GUI: оформление, виджеты, таблица, настройки, журнал."""

from __future__ import annotations

import io
import json
import os
import queue
import re
import sys
import time
import traceback
import webbrowser
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import bc_core as core
import bc_theme
from bc_dialogs import AdvancedDialog, HelpDialog, LoginDialog
from bc_i18n import (
    LANGUAGE_BY_LABEL,
    get_language,
    language_label,
    load_saved_language,
    set_language,
    tr,
)
from bc_localize import localize_widgets

try:
    from PIL import Image, ImageDraw, ImageTk
    HAVE_PIL = True
except Exception:  # pragma: no cover
    Image = ImageDraw = ImageTk = None
    HAVE_PIL = False

# ---------------------------------------------------------------------------
# Оформление
# ---------------------------------------------------------------------------

# Значения ниже синхронизируются с текущей палитрой при смене темы.
BG = ""
CARD = ""
BORDER = ""
TEXT = ""
MUTED = ""
ACCENT = ""
ACCENT_DARK = ""
SOFT = ""

# Ограничения кэша обложек: превью хранятся как сжатые JPEG (несколько
# десятков килобайт), но при просмотре тысяч позиций кэш всё равно нужно
# ограничивать по объёму, а не только по количеству.
ART_CACHE_MAX_BYTES = 12 * 1024 * 1024
ART_CACHE_MAX_ITEMS = 120

THEME_CHECK_INTERVAL_MS = 20000


def _sync_theme_globals() -> None:
    """Подхватывает цвета текущей палитры в глобальные константы."""
    global BG, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT_DARK, SOFT
    palette = bc_theme.palette()
    BG = palette["bg"]
    CARD = palette["card"]
    BORDER = palette["border"]
    TEXT = palette["text"]
    MUTED = palette["muted"]
    ACCENT = palette["accent"]
    ACCENT_DARK = palette["accent_dark"]
    SOFT = palette["soft"]


_sync_theme_globals()

TERMINAL_STATES = {"done", "error", "skipped", "exists", "cancelled", "unavailable"}

STATE_ORDER = {
    "working": 0,
    "queued": 1,
    "done": 2,
    "skipped": 3,
    "exists": 3,
    "unavailable": 4,
    "cancelled": 5,
    "error": 6,
    "": 7,
}

STATE_TAGS = {
    "done": "done",
    "error": "error",
    "working": "working",
    "skipped": "skipped",
    "exists": "exists",
    "unavailable": "warning",
    "cancelled": "skipped",
    "queued": "queued",
}


class Tooltip:
    def __init__(self, widget: tk.Misc, text: str):
        self.widget = widget
        self.text = text
        self._tip: tk.Toplevel | None = None
        self._after: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after = self.widget.after(550, self._show)

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except Exception:
                pass
            self._after = None

    def _show(self) -> None:
        if self._tip is not None or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 14
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tip, text=self.text, justify="left",
            bg=bc_theme.color("tooltip_bg"), fg=bc_theme.color("tooltip_fg"),
            font=("Segoe UI", 9), padx=8, pady=5, wraplength=360,
        )
        label.pack()
        self._tip = tip

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


class AppBase:
    """Виджеты и всё, что не связано с сетью/загрузкой."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self._closing = False
        self._settings = self._load_settings_file()
        set_language(load_saved_language(self._settings_path()))
        bc_theme.set_mode(self._settings.get("theme", bc_theme.THEME_AUTO))
        _sync_theme_globals()
        self._queue: queue.Queue = queue.Queue()

        self.client = None
        self.items: list[core.CollectionItem] = []
        self.items_by_key: dict[str, core.CollectionItem] = {}
        self._visible_keys: list[str] = []
        self._row_index: dict[str, int] = {}
        self._preview_key: str | None = None

        self._loading = False
        self._formats_running = False
        self.job = None
        self._job_items: list[core.CollectionItem] = []
        self._job_total = 0
        self._job_fraction: dict[str, float] = {}
        self._job_bytes: dict[str, tuple[int, int]] = {}
        self._speed_samples: deque = deque(maxlen=40)
        self._last_progress_ui = 0.0
        self._last_row_update: dict[str, float] = {}
        self._last_out_dir = Path(core.default_output_dir())

        self._cookie_source: str | None = None
        self._cookie_source_label = ""

        self._sort_key: str | None = None
        self._sort_reverse = False
        self._refresh_after = None
        self._search_after = None

        self.verbose_var = tk.BooleanVar(value=False)

        # Параметры из диалога «Дополнительно…». Создаются здесь, чтобы
        # настройки можно было применить ещё до открытия диалога.
        self.template_var = tk.StringVar(value=core.DEFAULT_TEMPLATE)
        self.proxy_var = tk.StringVar()
        self.attempts_var = tk.StringVar(value="4")
        self.retry_wait_var = tk.StringVar(value="3")
        self.open_folder_var = tk.BooleanVar(value=False)
        self.notify_var = tk.BooleanVar(value=True)

        self._art_token = 0
        self._art_cache: OrderedDict[int, bytes] = OrderedDict()
        self._art_cache_bytes = 0
        self._photo = None
        self._art_pool = _ArtPool()

        self._format_id_by_label: dict[str, str] = {}
        self._format_label_by_id: dict[str, str] = {}
        self._browser_id_by_label: dict[str, str] = {}
        self._browser_labels: dict[str, str] = {}
        self._build_choice_maps()

        self._headings = {
            "artist": tr("Исполнитель"),
            "title": tr("Название"),
            "kind": tr("Тип"),
            "purchased": tr("Куплено"),
            "formats": tr("Форматы"),
            "status": tr("Статус"),
        }

        self._build_style()
        self._build_ui()
        self._setup_icon()
        self._apply_settings()

        self.root.title(core.APP_NAME)
        self.root.minsize(980, 640)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._report_exception
        self.root.after(80, self._poll_queue)
        self.root.after(300, self._set_sash)
        self.root.after(500, self._startup_log)
        self.root.after(THEME_CHECK_INTERVAL_MS, self._poll_system_theme)
        self._sync_extract_controls()
        self._sync_action_buttons()
        self._update_cookie_status()

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------

    def _build_choice_maps(self) -> None:
        format_choices = core.format_choices()
        self._format_id_by_label = {
            label: fmt for fmt, label in format_choices
        }
        self._format_label_by_id = {
            fmt: label for fmt, label in format_choices
        }
        browser_choices = core.browser_choices()
        self._browser_id_by_label = {
            label: bid for bid, label in browser_choices
        }
        self._browser_labels = {
            bid: label for bid, label in browser_choices
        }

    def _settings_path(self) -> Path:
        return core.config_dir() / "settings.json"

    def _load_settings_file(self) -> dict:
        try:
            data = json.loads(self._settings_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_settings(self) -> None:
        data = {
            "username": self.username_var.get().strip(),
            "browser": self._selected_browser_id(),
            "format": self._selected_format_id(),
            "out_dir": self.folder_var.get().strip(),
            "template": self.template_var.get().strip(),
            "threads": self.threads_var.get().strip(),
            "include_hidden": bool(self.hidden_var.get()),
            "skip_existing": bool(self.skip_var.get()),
            "extract": bool(self.extract_var.get()),
            "delete_zip": bool(self.delete_zip_var.get()),
            "open_folder": bool(self.open_folder_var.get()),
            "notify": bool(self.notify_var.get()),
            "verbose": bool(self.verbose_var.get()),
            "proxy": self.proxy_var.get().strip(),
            "attempts": self.attempts_var.get().strip(),
            "retry_wait": self.retry_wait_var.get().strip(),
            "language": get_language(),
            "theme": bc_theme.get_mode(),
        }
        try:
            data["geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        self._settings = data
        path = self._settings_path()
        try:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass

    def _apply_settings(self) -> None:
        s = self._settings

        self.username_var.set(str(s.get("username") or ""))
        browser_id = s.get("browser", "auto")
        if browser_id not in self._browser_labels:
            browser_id = "auto"
        self.browser_label_var.set(self._browser_labels[browser_id])

        fmt = s.get("format", "mp3-320")
        if fmt not in self._format_label_by_id:
            fmt = "mp3-320"
        self.format_label_var.set(self._format_label_by_id[fmt])

        self.folder_var.set(str(s.get("out_dir") or core.default_output_dir()))
        self.template_var.set(str(s.get("template") or core.DEFAULT_TEMPLATE))
        try:
            threads = int(s.get("threads", core.DEFAULT_THREADS))
        except (TypeError, ValueError):
            threads = core.DEFAULT_THREADS
        self.threads_var.set(str(max(1, min(core.MAX_PARALLEL, threads))))

        self.hidden_var.set(bool(s.get("include_hidden", False)))
        self.skip_var.set(bool(s.get("skip_existing", True)))
        self.extract_var.set(bool(s.get("extract", False)))
        self.delete_zip_var.set(bool(s.get("delete_zip", False)))
        self.open_folder_var.set(bool(s.get("open_folder", False)))
        self.notify_var.set(bool(s.get("notify", True)))
        self.verbose_var.set(bool(s.get("verbose", False)))
        self.proxy_var.set(str(s.get("proxy") or ""))
        self.attempts_var.set(str(s.get("attempts") or "4"))
        self.retry_wait_var.set(str(s.get("retry_wait") or "3"))

        geometry = s.get("geometry")
        if not isinstance(geometry, str):
            geometry = None
        self.root.geometry(self._fit_geometry(geometry))
        if hasattr(self, "language_var"):
            self.language_var.set(language_label(get_language()))
        if hasattr(self, "theme_var"):
            self.theme_var.set(self._theme_label(bc_theme.get_mode()))

    @staticmethod
    def _theme_label(mode: str) -> str:
        return tr(bc_theme.THEME_LABELS.get(mode, "Авто"))

    def _theme_mode_by_label(self) -> dict[str, str]:
        return {
            self._theme_label(mode): mode for mode in bc_theme.THEMES
        }

    def _fit_geometry(self, geometry: str | None) -> str:
        """Подгоняет окно под экран, не давая ему уйти за границы."""
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
        except tk.TclError:
            return "1180x820"

        default_w = min(1180, max(980, screen_w - 80))
        default_h = min(820, max(640, screen_h - 100))
        if not geometry:
            return f"{default_w}x{default_h}"

        match = re.match(
            r"^\s*(\d+)x(\d+)([+-]\d+)([+-]\d+)\s*$", geometry
        )
        if not match:
            return f"{default_w}x{default_h}"
        width, height, x, y = (int(part) for part in match.groups())
        width = min(max(980, width), max(980, screen_w - 40))
        height = min(max(640, height), max(640, screen_h - 80))
        x = min(max(0, x), max(0, screen_w - width))
        y = min(max(0, y), max(0, screen_h - height - 40))
        return f"{width}x{height}+{x}+{y}"

    # ------------------------------------------------------------------
    # Стили
    # ------------------------------------------------------------------

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Выпадающие списки ttk не наследуют цвета из style.configure,
        # поэтому задаём их через опции Tk.
        try:
            self.root.option_add("*TCombobox*Listbox.background", CARD)
            self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
            self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
            self.root.option_add("*TCombobox*Listbox.selectForeground",
                                bc_theme.color("accent_text"))
        except tk.TclError:
            pass

        base_font = ("Segoe UI", 10)
        small = ("Segoe UI", 9)
        bold = ("Segoe UI", 10, "bold")
        style.configure(".", background=BG, foreground=TEXT, font=base_font)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Header.TFrame", background=CARD)
        style.configure("Status.TFrame", background=SOFT)
        style.configure("TLabel", background=BG, foreground=TEXT, font=base_font)
        style.configure("Header.TLabel", background=CARD, foreground=TEXT,
                        font=base_font)
        style.configure("HeaderMuted.TLabel", background=CARD, foreground=MUTED,
                        font=small)
        style.configure("Title.TLabel", background=CARD, foreground=TEXT,
                        font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=CARD, foreground=MUTED,
                        font=small)
        style.configure("H1.TLabel", background=BG, foreground=TEXT,
                        font=("Segoe UI", 14, "bold"))
        style.configure("H2.TLabel", background=BG, foreground=TEXT,
                        font=bold)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED,
                        font=small)
        style.configure("Empty.TLabel", background=CARD,
                        foreground=bc_theme.color("empty_fg"),
                        font=("Segoe UI", 11))
        style.configure("Status.TLabel", background=SOFT, foreground=MUTED,
                        font=small)
        style.configure("TButton", background=CARD, foreground=TEXT,
                        bordercolor=BORDER, lightcolor=CARD, darkcolor=CARD,
                        focusthickness=0, padding=(11, 5), font=base_font)
        style.map(
            "TButton",
            background=[("active", bc_theme.color("button_active")),
                        ("disabled", bc_theme.color("button_disabled"))],
            foreground=[("disabled", bc_theme.color("button_disabled_fg"))],
        )
        style.configure("Accent.TButton", background=ACCENT,
                        foreground=bc_theme.color("accent_text"),
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                        font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_DARK),
                        ("disabled", bc_theme.color("accent_disabled"))],
            foreground=[("disabled", bc_theme.color("accent_text"))],
        )
        style.configure("TCheckbutton", background=BG, foreground=TEXT,
                        font=base_font, focusthickness=0)
        style.configure("Header.TCheckbutton", background=CARD, foreground=TEXT,
                        font=base_font, focusthickness=0)
        style.map("TCheckbutton", background=[("active", BG)])
        style.map("Header.TCheckbutton", background=[("active", CARD)])
        style.configure("TEntry", fieldbackground=CARD, foreground=TEXT,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                        padding=5, insertcolor=TEXT)
        style.map(
            "TEntry",
            fieldbackground=[("disabled", SOFT)],
            foreground=[("disabled", MUTED)],
        )
        style.configure("TCombobox", fieldbackground=CARD, background=CARD,
                        foreground=TEXT, arrowsize=14, padding=4)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", CARD)],
            selectbackground=[("readonly", CARD)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure("TSpinbox", fieldbackground=CARD, foreground=TEXT,
                        bordercolor=BORDER, arrowsize=12, padding=4,
                        arrowcolor=MUTED, insertcolor=TEXT)
        for orient in ("Vertical", "Horizontal"):
            style.configure(
                f"{orient}.TScrollbar",
                background=BORDER, troughcolor=BG, bordercolor=BG,
                arrowcolor=MUTED, lightcolor=BORDER, darkcolor=BORDER,
            )
            style.map(
                f"{orient}.TScrollbar",
                background=[("active", MUTED)],
            )
        style.configure("TLabelframe", background=BG, bordercolor=BORDER,
                        relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=BG, foreground=TEXT,
                        font=bold)
        style.configure("Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=27, borderwidth=0,
                        font=("Segoe UI", 9))
        style.configure(
            "Treeview.Heading", background=bc_theme.color("heading_bg"),
            foreground=bc_theme.color("heading_fg"),
            relief="flat", font=("Segoe UI", 9, "bold"), padding=(6, 7),
        )
        style.map(
            "Treeview",
            background=[("selected", bc_theme.color("select_bg"))],
            foreground=[("selected", bc_theme.color("select_fg"))],
        )
        style.map("Treeview.Heading",
                  background=[("active", bc_theme.color("heading_active"))])
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=bc_theme.color("progress_trough"), background=ACCENT,
            bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT, thickness=9,
        )
        style.configure("TSeparator", background=BORDER)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.configure(bg=BG)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_header()

        self.body = ttk.PanedWindow(self.root, orient="vertical")
        self.body.grid(row=1, column=0, sticky="nsew")

        collection = ttk.Frame(self.body)
        collection.columnconfigure(0, weight=1)
        collection.columnconfigure(1, weight=0)
        collection.rowconfigure(1, weight=1)
        self.body.add(collection, weight=5)

        self._build_filters(collection)
        self._build_tree(collection)
        self._build_preview(collection)
        self._build_log()

        self._build_settings()
        self._build_progress()
        self._build_status()
        localize_widgets(self.root)

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame",
                           padding=(20, 15, 20, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title_box = ttk.Frame(header, style="Header.TFrame")
        title_box.grid(row=0, column=0, sticky="w")
        ttk.Label(title_box, text="Bandcamp Collection",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_box,
            text="Скачивание купленных альбомов и треков",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(1, 0))

        top_right = ttk.Frame(header, style="Header.TFrame")
        top_right.grid(row=0, column=1, sticky="e")
        ttk.Label(
            top_right, text="только ваш купленный контент",
            style="HeaderMuted.TLabel",
        ).pack(side="left", padx=(0, 12))
        ttk.Label(
            top_right, text=tr("Язык:"), style="HeaderMuted.TLabel"
        ).pack(side="left", padx=(0, 5))
        self.language_var = tk.StringVar(value=language_label(get_language()))
        self.language_combo = ttk.Combobox(
            top_right,
            textvariable=self.language_var,
            values=["English", "Русский"],
            state="readonly",
            width=9,
        )
        self.language_combo.pack(side="left", padx=(0, 12))
        self.language_combo.bind("<<ComboboxSelected>>",
                                 self._on_language_changed)
        ttk.Label(
            top_right, text=tr("Тема:"), style="HeaderMuted.TLabel"
        ).pack(side="left", padx=(0, 5))
        self.theme_var = tk.StringVar(
            value=self._theme_label(bc_theme.get_mode())
        )
        self.theme_combo = ttk.Combobox(
            top_right,
            textvariable=self.theme_var,
            values=[self._theme_label(mode) for mode in bc_theme.THEMES],
            state="readonly",
            width=9,
        )
        self.theme_combo.pack(side="left", padx=(0, 12))
        self.theme_combo.bind("<<ComboboxSelected>>",
                              self._on_theme_changed)
        Tooltip(
            self.theme_combo,
            tr("Следовать теме системы (автоматически)."),
        )
        ttk.Button(top_right, text="Справка", command=self._open_help).pack(
            side="left"
        )

        controls = ttk.Frame(header, style="Header.TFrame")
        controls.grid(row=1, column=0, columnspan=2, sticky="ew",
                      pady=(13, 0))

        ttk.Label(controls, text="Профиль:", style="Header.TLabel").pack(
            side="left"
        )
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(
            controls, textvariable=self.username_var, width=22
        )
        self.username_entry.pack(side="left", padx=(6, 8))
        self.username_entry.bind("<Return>", self._on_username_return)
        Tooltip(
            self.username_entry,
            tr(
                "Имя профиля из адреса bandcamp.com/имя. "
                "Можно вставить ссылку целиком."
            ),
        )

        self.load_btn = ttk.Button(
            controls, text="Загрузить коллекцию", style="Accent.TButton",
            command=self._on_load,
        )
        self.load_btn.pack(side="left")

        self.hidden_var = tk.BooleanVar(value=False)
        hidden_check = ttk.Checkbutton(
            controls, text="Скрытые покупки", variable=self.hidden_var,
            style="Header.TCheckbutton",
        )
        hidden_check.pack(side="left", padx=(12, 10))
        Tooltip(
            hidden_check,
            tr("Показывать покупки, скрытые в профиле Bandcamp."),
        )

        ttk.Separator(controls, orient="vertical").pack(
            side="left", fill="y", padx=(0, 12)
        )

        ttk.Label(controls, text="Cookies из:", style="Header.TLabel").pack(
            side="left"
        )
        self.browser_label_var = tk.StringVar(value=tr("Авто"))
        self.browser_combo = ttk.Combobox(
            controls,
            textvariable=self.browser_label_var,
            values=list(self._browser_id_by_label.keys()),
            state="readonly", width=10,
        )
        self.browser_combo.pack(side="left", padx=(6, 6))
        self.browser_combo.bind("<<ComboboxSelected>>",
                                self._on_browser_changed)
        Tooltip(
            self.browser_combo,
            tr(
                "Откуда читать cookies Bandcamp. «Авто» пробует браузеры "
                "по очереди. Cookies хранятся только в памяти."
            ),
        )

        ttk.Button(controls, text="Войти…", command=self._open_login).pack(
            side="left"
        )
        self.login_hint = ttk.Label(
            controls, text="", style="HeaderMuted.TLabel"
        )
        self.login_hint.pack(side="left", padx=(8, 0))

    def _build_filters(self, parent: ttk.Frame) -> None:
        filters = ttk.Frame(parent, padding=(20, 12, 20, 8))
        filters.grid(row=0, column=0, columnspan=2, sticky="ew")

        ttk.Label(filters, text="Поиск:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        self.search_entry = ttk.Entry(
            filters, textvariable=self.search_var, width=28
        )
        self.search_entry.pack(side="left", padx=(6, 14))
        self.search_entry.bind("<Escape>", lambda _e: self.search_var.set(""))
        Tooltip(
            self.search_entry,
            tr(
                "Фильтр по исполнителю, названию релиза или трека. "
                "Escape очищает поле."
            ),
        )

        ttk.Label(filters, text="Тип:").pack(side="left")
        self.type_filter_var = tk.StringVar(value=tr("Все"))
        type_combo = ttk.Combobox(
            filters, textvariable=self.type_filter_var,
            values=[tr("Все"), tr("Альбомы"), tr("Треки")],
            state="readonly", width=9,
        )
        type_combo.pack(side="left", padx=(6, 12))
        type_combo.bind("<<ComboboxSelected>>",
                        lambda _e: self._rebuild_tree())

        self.missing_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filters, text="Только не скачанные",
            variable=self.missing_only_var, command=self._rebuild_tree,
        ).pack(side="left")

        ttk.Button(
            filters, text="Снять все",
            command=lambda: self._select_all(False),
        ).pack(side="right")
        ttk.Button(
            filters, text="Выбрать все",
            command=lambda: self._select_all(True),
        ).pack(side="right", padx=(0, 6))

        self.selection_var = tk.StringVar(value=tr("Выбрано: 0"))
        ttk.Label(
            filters, textvariable=self.selection_var, style="Muted.TLabel"
        ).pack(side="right", padx=(0, 14))

    def _build_tree(self, parent: ttk.Frame) -> None:
        wrap = ttk.Frame(parent)
        wrap.grid(row=1, column=0, sticky="nsew", padx=(20, 0), pady=(0, 10))
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        columns = ("sel", "artist", "title", "kind", "purchased", "formats", "status")
        self.tree = ttk.Treeview(
            wrap, columns=columns, show="headings", selectmode="extended"
        )
        self.tree.grid(row=0, column=0, sticky="nsew")

        self.tree.heading("sel", text="✓")
        self.tree.column("sel", width=40, minwidth=40, anchor="center",
                         stretch=False)
        for key in ("artist", "title", "kind", "purchased", "formats", "status"):
            self.tree.heading(
                key, text=self._headings[key],
                command=lambda c=key: self._sort_by(c),
            )
        self.tree.column("artist", width=140, minwidth=105, anchor="w",
                         stretch=True)
        self.tree.column("title", width=220, minwidth=160, anchor="w",
                         stretch=True)
        self.tree.column("kind", width=60, minwidth=56, anchor="center",
                         stretch=False)
        self.tree.column("purchased", width=84, minwidth=80, anchor="center",
                         stretch=False)
        self.tree.column("formats", width=114, minwidth=95, anchor="w",
                         stretch=True)
        self.tree.column("status", width=165, minwidth=130, anchor="w",
                         stretch=True)

        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.tag_configure("even", background=CARD, foreground=TEXT)
        self.tree.tag_configure("odd", background=bc_theme.color("row_odd"),
                                foreground=TEXT)
        self.tree.tag_configure("done", background=bc_theme.color("done_bg"),
                                foreground=bc_theme.color("done_fg"))
        self.tree.tag_configure("error", background=bc_theme.color("error_bg"),
                                foreground=bc_theme.color("error_fg"))
        self.tree.tag_configure("working",
                                background=bc_theme.color("working_bg"),
                                foreground=bc_theme.color("working_fg"))
        self.tree.tag_configure("skipped",
                                background=bc_theme.color("skipped_bg"),
                                foreground=MUTED)
        self.tree.tag_configure("exists",
                                background=bc_theme.color("skipped_bg"),
                                foreground=MUTED)
        self.tree.tag_configure("warning",
                                background=bc_theme.color("warning_bg"),
                                foreground=bc_theme.color("warning_fg"))
        self.tree.tag_configure("queued",
                                background=bc_theme.color("queued_bg"),
                                foreground=bc_theme.color("queued_fg"))

        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<space>", self._on_tree_space)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._on_tree_context)

        self.empty_label = ttk.Label(
            wrap,
            text="Введите имя профиля Bandcamp\nи нажмите «Загрузить коллекцию»",
            style="Empty.TLabel", anchor="center", justify="center",
        )
        self.empty_label.place(relx=0.5, rely=0.42, anchor="center")

    def _build_preview(self, parent: ttk.Frame) -> None:
        wrap = ttk.Frame(parent, width=278)
        wrap.grid(row=1, column=1, sticky="ns", padx=(16, 20), pady=(0, 10))
        wrap.grid_propagate(False)

        card = tk.Frame(wrap, bg=CARD, highlightbackground=BORDER,
                        highlightthickness=1)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, bg=CARD, padx=12, pady=12)
        inner.pack(fill="both", expand=True)

        art_holder = tk.Frame(inner, bg=bc_theme.color("art_holder"),
                              width=160, height=160)
        art_holder.pack()
        art_holder.pack_propagate(False)
        self.art_label = tk.Label(
            art_holder, bg=bc_theme.color("art_holder"),
            fg=bc_theme.color("empty_fg"), text="♪",
            font=("Segoe UI", 34),
        )
        self.art_label.pack(fill="both", expand=True)

        self.preview_title = tk.Label(
            inner, text="Ничего не выбрано", bg=CARD, fg=TEXT,
            font=("Segoe UI", 11, "bold"), wraplength=232,
            justify="left", anchor="w",
        )
        self.preview_title.pack(fill="x", pady=(12, 2))
        self.preview_artist = tk.Label(
            inner, text="Выберите позицию в списке", bg=CARD, fg=MUTED,
            font=("Segoe UI", 10), wraplength=232, justify="left", anchor="w",
        )
        self.preview_artist.pack(fill="x")
        self.preview_meta = tk.Label(
            inner, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9),
            wraplength=232, justify="left", anchor="w",
        )
        self.preview_meta.pack(fill="x", pady=(6, 0))
        self.preview_formats = tk.Label(
            inner, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9),
            wraplength=232, justify="left", anchor="w",
        )
        self.preview_formats.pack(fill="x", pady=(6, 0))
        self.preview_link = tk.Label(
            inner, text="", bg=CARD, fg=bc_theme.color("link"),
            font=("Segoe UI", 9, "underline"), cursor="hand2",
            anchor="w", justify="left",
        )
        self.preview_link.pack(fill="x", pady=(10, 0))
        self.preview_link.bind("<Button-1>", lambda _e: self._open_selected_item())

    def _build_log(self) -> None:
        pane = ttk.Frame(self.body)
        pane.columnconfigure(0, weight=1)
        pane.rowconfigure(1, weight=1)
        self.body.add(pane, weight=1)

        header = ttk.Frame(pane, padding=(20, 8, 20, 4))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="Журнал", style="H2.TLabel").pack(side="left")
        self.verbose_check = ttk.Checkbutton(
            header, text="Подробно", variable=self.verbose_var,
        )
        self.verbose_check.pack(side="left", padx=(12, 0))
        ttk.Button(header, text="Очистить", command=self._clear_log).pack(
            side="right"
        )
        ttk.Button(header, text="Сохранить…", command=self._save_log).pack(
            side="right", padx=(0, 6)
        )

        wrap = ttk.Frame(pane, padding=(20, 0, 20, 8))
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            wrap, height=7, wrap="word", font=("Consolas", 9),
            bg=CARD, fg=TEXT, relief="flat", highlightthickness=1,
            highlightbackground=BORDER, padx=10, pady=8,
            insertbackground=TEXT, selectbackground=bc_theme.color("select_bg"),
            selectforeground=bc_theme.color("select_fg"),
            state="disabled",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(wrap, orient="vertical",
                                  command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.tag_configure("info", foreground=bc_theme.color("log_info"))
        self.log_text.tag_configure("ok", foreground=bc_theme.color("log_ok"))
        self.log_text.tag_configure("warn", foreground=bc_theme.color("log_warn"))
        self.log_text.tag_configure("error", foreground=bc_theme.color("log_error"))
        self.log_text.tag_configure("debug", foreground=bc_theme.color("log_debug"))

    def _build_settings(self) -> None:
        frame = ttk.LabelFrame(
            self.root, text=" Параметры загрузки ", padding=(16, 10, 16, 12)
        )
        frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 7))
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text="Формат:").grid(row=0, column=0, sticky="w")
        self.format_label_var = tk.StringVar()
        self.format_combo = ttk.Combobox(
            frame, textvariable=self.format_label_var,
            values=[label for _, label in core.format_choices()],
            state="readonly", width=26,
        )
        self.format_combo.grid(row=0, column=1, sticky="w", padx=(8, 22))
        self.format_combo.bind("<<ComboboxSelected>>",
                               self._on_format_changed)
        Tooltip(
            self.format_combo,
            tr(
                "Если выбранного формата нет у конкретной покупки, будет "
                "скачан лучший доступный — предупреждение появится в журнале."
            ),
        )

        ttk.Label(frame, text="Папка:").grid(row=0, column=2, sticky="w")
        self.folder_var = tk.StringVar()
        folder_entry = ttk.Entry(frame, textvariable=self.folder_var)
        folder_entry.grid(row=0, column=3, sticky="ew", padx=(8, 6))
        folder_entry.bind("<FocusOut>", lambda _e: self._schedule_existing_refresh())
        folder_entry.bind("<Return>", lambda _e: self._schedule_existing_refresh())
        ttk.Button(frame, text="Обзор…", command=self._browse_folder).grid(
            row=0, column=4, padx=(0, 20)
        )

        ttk.Label(frame, text="Потоков:").grid(row=0, column=5, sticky="w")
        self.threads_var = tk.StringVar(value="4")
        threads_spin = ttk.Spinbox(
            frame, from_=1, to=core.MAX_PARALLEL, width=4,
            textvariable=self.threads_var, state="readonly",
        )
        threads_spin.grid(row=0, column=6, padx=(6, 0))
        Tooltip(
            threads_spin,
            tr(
                "Сколько позиций скачивать одновременно (1–16). "
                "Слишком большое значение может ускорить появление HTTP 429."
            ),
        )

        checks = ttk.Frame(frame)
        checks.grid(row=1, column=0, columnspan=7, sticky="w", pady=(9, 0))
        self.skip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            checks, text="Пропускать уже скачанное",
            variable=self.skip_var,
        ).pack(side="left")
        self.extract_var = tk.BooleanVar(value=False)
        self.extract_check = ttk.Checkbutton(
            checks, text="Распаковывать ZIP", variable=self.extract_var,
            command=self._sync_extract_controls,
        )
        self.extract_check.pack(side="left", padx=(18, 0))
        self.delete_zip_var = tk.BooleanVar(value=False)
        self.delete_zip_check = ttk.Checkbutton(
            checks, text="Удалять ZIP после распаковки",
            variable=self.delete_zip_var,
        )
        self.delete_zip_check.pack(side="left", padx=(18, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, columnspan=7, sticky="ew", pady=(11, 0))
        ttk.Button(actions, text="Дополнительно…",
                   command=self._open_advanced).pack(side="left")
        self.check_formats_btn = ttk.Button(
            actions, text="Проверить форматы",
            command=self._on_check_formats,
        )
        self.check_formats_btn.pack(side="left", padx=8)
        ttk.Button(actions, text="Открыть папку",
                   command=self._open_output_dir).pack(side="left")

        self.cancel_btn = ttk.Button(
            actions, text="Отмена", command=self._on_cancel, state="disabled"
        )
        self.cancel_btn.pack(side="right")
        self.download_btn = ttk.Button(
            actions, text="Скачать выбранные (0)", style="Accent.TButton",
            command=self._on_download, state="disabled",
        )
        self.download_btn.pack(side="right", padx=(0, 8))

    def _build_progress(self) -> None:
        frame = ttk.Frame(self.root, padding=(20, 0, 20, 5))
        frame.grid(row=3, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.progress_label = ttk.Label(
            frame, text="Готово", style="Muted.TLabel"
        )
        self.progress_label.grid(row=1, column=0, sticky="w", pady=(3, 0))

    def _build_status(self) -> None:
        frame = ttk.Frame(self.root, style="Status.TFrame",
                          padding=(20, 5, 20, 5))
        frame.grid(row=4, column=0, sticky="ew")
        self.status_var = tk.StringVar(value=tr("Готово"))
        ttk.Label(frame, textvariable=self.status_var,
                  style="Status.TLabel").pack(side="left")
        ttk.Label(
            frame, text=f"v{core.APP_VERSION}", style="Status.TLabel"
        ).pack(side="right")
        self.cookie_status_var = tk.StringVar(value=tr("Cookies: не загружены"))
        ttk.Label(
            frame, textvariable=self.cookie_status_var, style="Status.TLabel"
        ).pack(side="right", padx=(0, 16))

    def _setup_icon(self) -> None:
        if not HAVE_PIL:
            return
        try:
            accent = bc_theme.rgb("accent", (26, 158, 196))
            image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((2, 2, 61, 61), radius=14,
                                   fill=(*accent, 255))
            draw.rounded_rectangle((27, 14, 33, 43), radius=3,
                                   fill=(255, 255, 255, 255))
            draw.ellipse((18, 38, 33, 51), fill=(255, 255, 255, 255))
            draw.polygon([(33, 14), (47, 20), (47, 27), (33, 21)],
                         fill=(255, 255, 255, 255))
            self._icon = ImageTk.PhotoImage(image)
            self.root.iconphoto(True, self._icon)
        except Exception:
            pass

    def _set_sash(self) -> None:
        try:
            height = self.body.winfo_height()
            if height > 320:
                self.body.sashpos(0, int(height * 0.72))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Логи / статус
    # ------------------------------------------------------------------

    def _queue_event(self, kind: str, payload: Any) -> None:
        """Для колбэков, которым нужен интерфейс ``(kind, payload)``."""
        self._queue.put((kind, payload))

    def _post_log(self, message: str, level: str = "info") -> None:
        self._queue.put(("log", (level, message)))

    def _client_log(self, message: str, level: str = "debug") -> None:
        self._queue.put(("log", (level, message)))

    def _append_log(self, message: str, level: str = "info") -> None:
        if level == "debug" and not self.verbose_var.get():
            return
        try:
            at_bottom = self.log_text.yview()[1] >= 0.995
            self.log_text.configure(state="normal")
            self.log_text.insert(
                "end", f"[{time.strftime('%H:%M:%S')}] {message}\n", level
            )
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 3000:
                self.log_text.delete("1.0", f"{lines - 2200}.0")
            self.log_text.configure(state="disabled")
            if at_bottom:
                self.log_text.see("end")
        except tk.TclError:
            pass

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root, title=tr("Сохранить журнал"),
            defaultextension=".txt",
            initialfile=f"bandcamp_log_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[(tr("Текст"), "*.txt"), (tr("Все файлы"), "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(
                self.log_text.get("1.0", "end"), encoding="utf-8"
            )
            self._set_status(tr("Журнал сохранён: ") + str(path))
        except OSError as exc:
            messagebox.showerror(
                tr("Журнал"),
                tr("Не удалось сохранить:\n") + str(exc),
                parent=self.root,
            )

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _update_cookie_status(self) -> None:
        count = self.client.cookie_count if self.client else 0
        if count:
            label = self._cookie_source_label or tr("из браузера")
            suffix = "" if self._cookie_source else tr(" · будут обновлены")
            self.cookie_status_var.set(
                f"Cookies: {count} · {label}{suffix}"
            )
        else:
            self.cookie_status_var.set(tr("Cookies: не загружены"))

    def _startup_log(self) -> None:
        self._append_log(
            tr(
                "Укажите имя профиля Bandcamp и нажмите «Загрузить коллекцию»."
            ),
            "info",
        )
        if self.username_var.get().strip():
            self._append_log(
                tr(
                    "Сохранённый профиль: {username}.",
                    username=self.username_var.get().strip(),
                ),
                "debug",
            )
        if core.HTTP_BACKEND == "requests":
            self._append_log(
                tr(
                    "curl_cffi не установлен — используется requests. Bandcamp может "
                    "показать антибот-проверку; рекомендуется pip install curl_cffi."
                ),
                "warn",
            )
        if core.browser_cookie3 is None:
            self._append_log(
                tr(
                    "browser_cookie3 не установлен: автоматическое чтение cookies "
                    "недоступно, используйте «Войти…» → вставить вручную."
                ),
                "warn",
            )
        if not HAVE_PIL:
            self._append_log(
                tr(
                    "Pillow не установлен: обложки в панели справа не показываются."
                ),
                "debug",
            )
        self._append_log(
            tr("Версия ") + f"{core.APP_VERSION} · HTTP: "
            f"{core.HTTP_BACKEND or tr('нет')}",
            "debug",
        )

    # ------------------------------------------------------------------
    # Очередь событий
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                item = self._queue.get_nowait()
                if not (isinstance(item, tuple) and len(item) == 2):
                    self._append_log(
                        tr(
                            "Пропущено некорректное событие очереди: {item}",
                            item=repr(item)[:160],
                        ),
                        "debug",
                    )
                    continue
                kind, payload = item
                handler = getattr(self, f"_ev_{kind}", None)
                if handler is None:
                    continue
                try:
                    handler(payload)
                except Exception:
                    self._report_exception(*sys.exc_info())
        except queue.Empty:
            pass
        try:
            self.root.after(80, self._poll_queue)
        except tk.TclError:
            pass

    def _report_exception(self, exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        core.write_crash_log(text)
        try:
            self._append_log(
                tr("Необработанная ошибка: {error}", error=exc_value),
                "error",
            )
            self._append_log(text, "debug")
        except Exception:
            print(text, file=sys.stderr)

    def _ev_log(self, payload) -> None:
        level, message = payload
        self._append_log(message, level)

    def _ev_art(self, payload) -> None:
        token, art_id, data = payload
        if token != self._art_token:
            return
        if not data:
            self._set_placeholder_art("♪")
            return
        self._cache_art(art_id, data)
        self._render_art(data)

    def _cache_art(self, art_id: int, data: bytes) -> None:
        """Кладёт обложку в LRU-кэш, ограниченный по количеству и объёму."""
        old = self._art_cache.pop(art_id, None)
        if old is not None:
            self._art_cache_bytes -= len(old)
        self._art_cache[art_id] = data
        self._art_cache_bytes += len(data)
        while (
            len(self._art_cache) > ART_CACHE_MAX_ITEMS
            or self._art_cache_bytes > ART_CACHE_MAX_BYTES
        ) and len(self._art_cache) > 1:
            _old_id, old_data = self._art_cache.popitem(last=False)
            self._art_cache_bytes -= len(old_data)

    def _clear_art_cache(self) -> None:
        self._art_cache.clear()
        self._art_cache_bytes = 0

    def _set_placeholder_art(self, text: str = "♪") -> None:
        self._photo = None
        try:
            self.art_label.configure(image="", text=text)
        except tk.TclError:
            pass

    def _render_art(self, data: bytes) -> None:
        if not HAVE_PIL:
            self._set_placeholder_art("♪")
            return
        try:
            image = Image.open(io.BytesIO(data)).convert("RGB")
            image.thumbnail((160, 160), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(image)
            self.art_label.configure(image=self._photo, text="")
        except Exception:
            self._set_placeholder_art("♪")

    # ------------------------------------------------------------------
    # Таблица / фильтры / выделение
    # ------------------------------------------------------------------

    def _has_filter(self) -> bool:
        return bool(
            self.search_var.get().strip()
            or self.type_filter_var.get() != tr("Все")
            or self.missing_only_var.get()
        )

    @staticmethod
    def _is_complete(item: core.CollectionItem) -> bool:
        if item.state in ("done", "skipped", "exists"):
            return True
        return not item.state and item.exists

    def _show_items(self) -> list[core.CollectionItem]:
        query = self.search_var.get().strip().casefold()
        kind_filter = self.type_filter_var.get()
        only_missing = self.missing_only_var.get()

        result: list[core.CollectionItem] = []
        for item in self.items:
            haystack = f"{item.artist} {item.title} {item.album_title}".casefold()
            if query and query not in haystack:
                continue
            if kind_filter == tr("Альбомы") and not item.is_album:
                continue
            if kind_filter == tr("Треки") and item.is_album:
                continue
            if only_missing and self._is_complete(item):
                continue
            result.append(item)

        if self._sort_key:
            result.sort(key=lambda i: self._sort_value(i, self._sort_key),
                        reverse=self._sort_reverse)
        return result

    def _sort_value(self, item: core.CollectionItem, column: str):
        if column == "artist":
            return (item.artist.casefold(), item.title.casefold())
        if column == "title":
            return (item.title.casefold(), item.artist.casefold())
        if column == "kind":
            return (0 if item.is_album else 1, item.title.casefold())
        if column == "purchased":
            purchased = item.purchased_dt
            return purchased.toordinal() if purchased else 0
        if column == "formats":
            return (len(item.formats), item.title.casefold())
        if column == "status":
            return (STATE_ORDER.get(item.state, 7), item.title.casefold())
        return item.title.casefold()

    def _sort_by(self, column: str) -> None:
        if column == "sel":
            return
        if self._sort_key == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = column
            self._sort_reverse = False
        self._rebuild_tree()

    def _update_headings(self) -> None:
        for key, label in self._headings.items():
            text = label
            if self._sort_key == key:
                text += " ▼" if self._sort_reverse else " ▲"
            self.tree.heading(key, text=text)

    def _rebuild_tree(self) -> None:
        visible = self._show_items()
        self.tree.delete(*self.tree.get_children())
        self._visible_keys = []
        self._row_index = {}
        for index, item in enumerate(visible):
            self._row_index[item.key] = index
            self._visible_keys.append(item.key)
            self.tree.insert(
                "", "end", iid=item.key,
                values=self._row_values(item),
                tags=self._row_tags(item, index),
            )
        if self._preview_key and self.tree.exists(self._preview_key):
            self.tree.selection_set(self._preview_key)

        self._update_headings()
        if not self.items:
            self.empty_label.configure(
                text=tr(
                    "Введите имя профиля Bandcamp\n"
                    "и нажмите «Загрузить коллекцию»"
                )
            )
            self.empty_label.place(relx=0.5, rely=0.42, anchor="center")
        elif not visible:
            self.empty_label.configure(
                text=tr("Ничего не найдено.\nИзмените фильтр.")
            )
            self.empty_label.place(relx=0.5, rely=0.42, anchor="center")
        else:
            self.empty_label.place_forget()
        self._update_selection()

    def _row_values(self, item: core.CollectionItem):
        if item.info_loaded:
            if item.formats:
                formats = ", ".join(
                    core.SHORT_FORMATS.get(f, f)
                    for f in core.sort_formats(item.formats)
                )
            else:
                formats = tr("нет")
        else:
            formats = "—"
        return (
            "☑" if item.selected else "☐",
            item.artist,
            item.title,
            item.kind_label,
            item.purchased_display,
            formats,
            self._status_text(item),
        )

    def _status_text(self, item: core.CollectionItem) -> str:
        state = item.state
        if state == "working":
            text = item.message or tr("Работа…")
        elif state == "error":
            text = tr("Ошибка: ") + (item.message or tr("неизвестно"))
        elif state == "done":
            text = tr("Готово")
            if item.final_size:
                text += f" · {core.human_size(item.final_size)}"
        elif state == "skipped":
            text = tr("Пропущено: уже есть")
        elif state == "unavailable":
            text = tr("Нет доступных форматов")
        elif state == "cancelled":
            text = tr("Отменено")
        elif state == "queued":
            text = tr("В очереди")
        elif item.exists:
            text = tr("Уже есть")
        else:
            text = "—"
        return text if len(text) <= 58 else text[:55] + "…"

    def _row_tags(self, item: core.CollectionItem, index: int):
        if item.state in STATE_TAGS:
            return (STATE_TAGS[item.state],)
        if item.exists:
            return ("exists",)
        return ("odd" if index % 2 else "even",)

    def _update_row(self, item: core.CollectionItem) -> None:
        try:
            if not self.tree.exists(item.key):
                return
            index = self._row_index.get(item.key, 0)
            self.tree.item(
                item.key,
                values=self._row_values(item),
                tags=self._row_tags(item, index),
            )
        except tk.TclError:
            pass

    def _update_all_rows(self) -> None:
        for key in self._visible_keys:
            item = self.items_by_key.get(key)
            if item is not None:
                self._update_row(item)

    def _on_search_changed(self, *_args) -> None:
        if getattr(self, "_search_after", None):
            try:
                self.root.after_cancel(self._search_after)
            except Exception:
                pass
        self._search_after = self.root.after(250, self._rebuild_tree)

    def _update_selection(self) -> None:
        selected = sum(1 for item in self.items if item.selected)
        text = tr(
            "Выбрано: {selected} из {total}",
            selected=selected,
            total=len(self.items),
        )
        if len(self._visible_keys) != len(self.items):
            text += tr(
                " · показано: {count}", count=len(self._visible_keys)
            )
        self.selection_var.set(text)
        self._sync_action_buttons()

    def _selected_items(self) -> list[core.CollectionItem]:
        return [item for item in self.items if item.selected]

    def _selected_count(self) -> int:
        return sum(1 for item in self.items if item.selected)

    def _toggle_item(self, key: str) -> None:
        item = self.items_by_key.get(key)
        if item is None:
            return
        item.selected = not item.selected
        self._update_row(item)
        self._update_selection()

    def _select_all(self, value: bool) -> None:
        targets = self._show_items() if self._has_filter() else self.items
        for item in targets:
            item.selected = value
            self._update_row(item)
        self._update_selection()

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        self.tree.selection_set(row)
        self.tree.focus(row)
        self._show_preview(row)
        self._toggle_item(row)
        return "break"

    def _on_tree_double(self, event):
        if self.tree.identify_column(event.x) == "#1":
            return "break"
        row = self.tree.identify_row(event.y)
        item = self.items_by_key.get(row) if row else None
        if item and item.item_url:
            webbrowser.open(item.item_url)
        return "break"

    def _on_tree_space(self, _event):
        for key in self.tree.selection():
            self._toggle_item(key)
        return "break"

    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        key = selection[0] if selection else None
        self._show_preview(key)

    def _on_tree_context(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        if row not in self.tree.selection():
            self.tree.selection_set(row)
        self.tree.focus(row)
        self._show_preview(row)

        item = self.items_by_key.get(row)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label=tr("Скачать выбранные"), command=self._on_download
        )
        menu.add_command(
            label=tr("Проверить форматы"), command=self._on_check_formats
        )
        menu.add_separator()
        if item and item.item_url:
            menu.add_command(
                label=tr("Открыть на Bandcamp"),
                command=lambda url=item.item_url: webbrowser.open(url),
            )
            menu.add_command(
                label=tr("Копировать ссылку"),
                command=lambda url=item.item_url: self._copy_url(url),
            )
            menu.add_separator()
        if item and item.selected:
            menu.add_command(
                label=tr("Снять выбор"),
                command=lambda: self._toggle_item(row),
            )
        else:
            menu.add_command(
                label=tr("Выбрать"),
                command=lambda: self._toggle_item(row),
            )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass

    def _copy_url(self, url: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self._set_status(tr("Ссылка скопирована"))
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Панель с обложкой
    # ------------------------------------------------------------------

    def _show_preview(self, key: str | None) -> None:
        item = self.items_by_key.get(key) if key else None
        if item is None:
            self._preview_key = None
            self._art_token += 1
            self._set_placeholder_art("♪")
            self.preview_title.configure(text=tr("Ничего не выбрано"))
            self.preview_artist.configure(text=tr("Выберите позицию в списке"))
            self.preview_meta.configure(text="")
            self.preview_formats.configure(text="")
            self.preview_link.configure(text="")
            return

        self._preview_key = item.key
        self.preview_title.configure(text=item.title)
        self.preview_artist.configure(text=item.artist)
        meta = item.kind_label
        if item.purchased_display and item.purchased_display != "—":
            meta += tr(
                " · куплено {date}", date=item.purchased_display
            )
        self.preview_meta.configure(text=meta)
        self._update_preview_info(item)
        self.preview_link.configure(
            text=tr("Открыть на Bandcamp") if item.item_url else ""
        )
        self._load_art(item)

    def _update_preview_info(self, item: core.CollectionItem) -> None:
        if self._preview_key != item.key:
            return
        if item.info_loaded:
            if item.formats:
                text = tr("Форматы: ") + ", ".join(
                    core.SHORT_FORMATS.get(f, f)
                    for f in core.sort_formats(item.formats)
                )
            else:
                text = tr("Форматы: недоступны")
        else:
            text = tr("Форматы: ещё не проверены")
        self.preview_formats.configure(text=text)

    def _load_art(self, item: core.CollectionItem) -> None:
        self._art_token += 1
        token = self._art_token
        if not item.art_id:
            self._set_placeholder_art("♪")
            return
        cached = self._art_cache.get(item.art_id)
        if cached:
            self._art_cache.move_to_end(item.art_id)
            self._render_art(cached)
            return
        self._set_placeholder_art("♪")
        url = core.ART_URL.format(art_id=item.art_id)
        proxy = self.proxy_var.get().strip() or None
        art_id = item.art_id
        art_pool = self._art_pool

        def work():
            try:
                data = core.fetch_image(url, proxy)
            except Exception:
                data = None
            self._queue.put(("art", (token, art_id, data)))

        try:
            art_pool.submit(work)
        except RuntimeError:
            pass

    def _open_selected_item(self) -> None:
        item = self.items_by_key.get(self._preview_key or "")
        if item and item.item_url:
            webbrowser.open(item.item_url)

    # ------------------------------------------------------------------
    # Настройки / файлы
    # ------------------------------------------------------------------

    def _selected_format_id(self) -> str:
        return self._format_id_by_label.get(
            self.format_label_var.get(), "mp3-320"
        )

    def _selected_browser_id(self) -> str:
        return self._browser_id_by_label.get(
            self.browser_label_var.get(), "auto"
        )

    def _on_browser_changed(self, _event=None) -> None:
        self._cookie_source = None
        self._cookie_source_label = ""
        self._update_cookie_status()
        self._save_settings()

    def _on_format_changed(self, _event=None) -> None:
        self._schedule_existing_refresh()
        self._save_settings()

    def _browse_folder(self) -> None:
        current = self.folder_var.get().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        path = filedialog.askdirectory(
            parent=self.root, title=tr("Папка для загрузок"), initialdir=initial
        )
        if path:
            self.folder_var.set(path)
            self._schedule_existing_refresh()
            self._save_settings()

    def _open_output_dir(self) -> None:
        folder = self.folder_var.get().strip() or core.default_output_dir()
        path = Path(folder)
        try:
            path.mkdir(parents=True, exist_ok=True)
            core.open_path(path)
        except Exception as exc:
            messagebox.showerror(
                tr("Папка"),
                tr("Не удалось открыть папку:\n") + str(exc),
                parent=self.root,
            )

    def _schedule_existing_refresh(self) -> None:
        if self._refresh_after is not None:
            try:
                self.root.after_cancel(self._refresh_after)
            except Exception:
                pass
        self._refresh_after = self.root.after(700, self._refresh_existing_flags)

    def _mark_existing(self, items: list[core.CollectionItem]) -> None:
        fmt = self._selected_format_id()
        template = self.template_var.get().strip() or core.DEFAULT_TEMPLATE
        out_dir = Path(
            self.folder_var.get().strip() or core.default_output_dir()
        )
        any_format = fmt == "auto"
        for item in items:
            try:
                base = core.build_base_path(out_dir, template, item, fmt)
                item.exists = core.is_already_downloaded(
                    base, item, fmt, any_format=any_format
                )
            except Exception:
                item.exists = False

    def _refresh_existing_flags(self) -> None:
        self._refresh_after = None
        if not self.items or self._loading or self.job is not None:
            return
        self._mark_existing(self.items)
        if self.missing_only_var.get():
            self._rebuild_tree()
        else:
            self._update_all_rows()

    def _sync_extract_controls(self) -> None:
        if self.extract_var.get():
            self.delete_zip_check.state(["!disabled"])
        else:
            self.delete_zip_var.set(False)
            self.delete_zip_check.state(["disabled"])

    def _sync_action_buttons(self) -> None:
        busy = (self.job is not None or self._loading
                or self._formats_running)
        selected = self._selected_count()
        can_download = selected > 0 and not busy and self.client is not None
        self.download_btn.configure(
            state="normal" if can_download else "disabled",
            text=tr(
                "Скачать выбранные ({count})", count=selected
            ),
        )
        self.check_formats_btn.configure(
            state="normal" if can_download else "disabled"
        )
        self.cancel_btn.configure(
            state="normal" if self.job is not None else "disabled"
        )
        self.load_btn.configure(
            state="disabled" if busy else "normal",
            text=tr("Загрузка…") if self._loading else tr("Загрузить коллекцию"),
        )

    def _on_username_return(self, _event=None) -> None:
        self._on_load()

    def _open_login(self) -> None:
        LoginDialog(self.root, self)

    def _open_advanced(self) -> None:
        AdvancedDialog(self.root, self)

    def _open_help(self) -> None:
        HelpDialog(self.root)

    def _busy(self) -> bool:
        return bool(
            self.job is not None
            or self._loading
            or self._formats_running
        )

    def _on_language_changed(self, _event=None) -> None:
        code = LANGUAGE_BY_LABEL.get(self.language_var.get(), "en")
        if code == get_language():
            return
        if self._busy():
            self.language_var.set(language_label(get_language()))
            messagebox.showwarning(
                tr("Язык"),
                tr(
                    "Сначала завершите текущую загрузку или проверку форматов."
                ),
                parent=self.root,
            )
            return
        set_language(code)
        self._save_settings()
        self._rebuild_ui()
        self._append_log(
            tr(
                "Язык интерфейса изменён: {language}.",
                language=language_label(get_language()),
            ),
            "info",
        )

    def _on_theme_changed(self, _event=None) -> None:
        mode = self._theme_mode_by_label().get(
            self.theme_var.get(), bc_theme.THEME_AUTO
        )
        if mode == bc_theme.get_mode():
            return
        if self._busy():
            self.theme_var.set(self._theme_label(bc_theme.get_mode()))
            messagebox.showwarning(
                tr("Тема:"),
                tr(
                    "Сначала завершите текущую загрузку или проверку форматов."
                ),
                parent=self.root,
            )
            return
        bc_theme.set_mode(mode)
        self._save_settings()
        self._rebuild_ui()
        self._append_log(
            tr(
                "Тема интерфейса изменена: {theme}.",
                theme=self._theme_name(mode),
            ),
            "info",
        )

    def _theme_name(self, mode: str | None = None) -> str:
        mode = bc_theme.normalize_mode(mode if mode is not None
                                       else bc_theme.get_mode())
        if mode == bc_theme.THEME_AUTO:
            return (
                tr("Системная тема") + " · "
                + self._theme_label(bc_theme.get_resolved())
            )
        return self._theme_label(mode)

    def _has_open_dialog(self) -> bool:
        try:
            return any(
                isinstance(child, tk.Toplevel)
                for child in self.root.winfo_children()
            )
        except tk.TclError:
            return False

    def _poll_system_theme(self) -> None:
        """Следит за сменой системной темы в режиме «Авто»."""
        if self._closing:
            return
        try:
            if (
                bc_theme.get_mode() == bc_theme.THEME_AUTO
                and not self._busy()
                and not self._has_open_dialog()
                and bc_theme.refresh()
            ):
                self._rebuild_ui()
                self._append_log(
                    tr(
                        "Тема интерфейса: {theme} (как в системе).",
                        theme=self._theme_label(bc_theme.get_resolved()),
                    ),
                    "info",
                )
        except Exception:
            pass
        finally:
            try:
                self.root.after(THEME_CHECK_INTERVAL_MS,
                                self._poll_system_theme)
            except tk.TclError:
                pass

    def _rebuild_ui(self) -> None:
        """Пересоздаёт интерфейс, сохраняя данные и текущее состояние."""
        username = self.username_var.get().strip()
        preview_key = self._preview_key
        try:
            log_content = self.log_text.get("1.0", "end-1c")
        except tk.TclError:
            log_content = ""
        try:
            status_text = self.status_var.get()
        except (AttributeError, tk.TclError):
            status_text = ""
        try:
            current_geometry = self.root.geometry()
        except tk.TclError:
            current_geometry = None

        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass

        _sync_theme_globals()
        self._build_choice_maps()
        self._build_style()
        self._build_ui()
        self._apply_settings()
        if current_geometry:
            try:
                self.root.geometry(self._fit_geometry(current_geometry))
            except tk.TclError:
                pass
        self.root.title(
            f"{username} — {core.APP_NAME}" if username else core.APP_NAME
        )
        if log_content:
            try:
                self.log_text.configure(state="normal")
                self.log_text.insert("1.0", log_content + "\n")
                lines = int(self.log_text.index("end-1c").split(".")[0])
                if lines > 3000:
                    self.log_text.delete("1.0", f"{lines - 2200}.0")
                self.log_text.configure(state="disabled")
                self.log_text.see("end")
            except tk.TclError:
                pass
        if status_text:
            self._set_status(status_text)
        self._rebuild_tree()
        self._show_preview(preview_key)
        self._sync_extract_controls()
        self._sync_action_buttons()
        self._update_cookie_status()
        self.root.after(300, self._set_sash)


class _ArtPool:
    """Ленивый пул потоков для обложек (создаётся без tkinter)."""

    def __init__(self):
        self._pool = None

    def submit(self, func):
        if self._pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._pool = ThreadPoolExecutor(max_workers=2,
                                            thread_name_prefix="art")
        return self._pool.submit(func)

    def shutdown(self):
        if self._pool is not None:
            self._pool.shutdown(wait=False)
            self._pool = None
