#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диалоги приложения: вход, дополнительные параметры, справка."""

from __future__ import annotations

import queue
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import bc_core as core
import bc_theme
from bc_i18n import get_language, tr
from bc_localize import localize_widgets


def center_window(window: tk.Toplevel, parent: tk.Misc) -> None:
    window.update_idletasks()
    width = max(window.winfo_width(), window.winfo_reqwidth())
    height = max(window.winfo_height(), window.winfo_reqheight())
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 3)
    window.geometry(f"{width}x{height}+{x}+{y}")


# ---------------------------------------------------------------------------
# Вход
# ---------------------------------------------------------------------------

class LoginDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent)
        self.app = app
        self.title(tr("Вход в Bandcamp"))
        self.configure(bg=bc_theme.color("bg"))
        self.transient(parent)
        self.resizable(True, True)
        self.minsize(560, 480)

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="Вход в Bandcamp", style="H1.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            body,
            text=(
                "Приложение не просит пароль. Оно читает cookies уже "
                "авторизованного браузера или принимает их вручную."
            ),
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        # -- из браузера ----------------------------------------------------
        browser_box = ttk.LabelFrame(body, text=" 1. Импорт из браузера ",
                                     padding=12)
        browser_box.grid(row=2, column=0, sticky="ew")
        browser_box.columnconfigure(1, weight=1)

        ttk.Label(browser_box, text="Браузер:").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.browser_var = tk.StringVar(value=app.browser_label_var.get())
        self.browser_combo = ttk.Combobox(
            browser_box,
            textvariable=self.browser_var,
            values=list(app._browser_id_by_label.keys()),
            state="readonly",
            width=18,
        )
        self.browser_combo.grid(row=0, column=1, sticky="w")

        self.import_btn = ttk.Button(
            browser_box,
            text="Импортировать cookies",
            style="Accent.TButton",
            command=self._import_browser,
        )
        self.import_btn.grid(row=0, column=2, padx=(10, 0))

        self.status_var = tk.StringVar(
            value=tr("Сначала войдите на bandcamp.com в браузере.")
        )
        ttk.Label(
            browser_box,
            textvariable=self.status_var,
            style="Muted.TLabel",
            wraplength=500,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # -- вручную --------------------------------------------------------
        manual_box = ttk.LabelFrame(body, text=" 2. Вставить cookies вручную ",
                                    padding=12)
        manual_box.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        manual_box.columnconfigure(0, weight=1)
        manual_box.rowconfigure(1, weight=1)
        body.rowconfigure(3, weight=1)

        ttk.Label(
            manual_box,
            text=(
                "Подойдёт заголовок Cookie (name=value; name2=value2), "
                "файл cookies.txt в формате Netscape или JSON-словарь. "
                "Обязательно должна быть cookie identity."
            ),
            style="Muted.TLabel",
            wraplength=500,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        text_wrap = ttk.Frame(manual_box)
        text_wrap.grid(row=1, column=0, columnspan=2, sticky="nsew")
        text_wrap.rowconfigure(0, weight=1)
        text_wrap.columnconfigure(0, weight=1)

        self.cookie_text = tk.Text(
            text_wrap,
            height=7,
            wrap="word",
            font=("Consolas", 9),
            bg=bc_theme.color("card"),
            fg=bc_theme.color("text"),
            insertbackground=bc_theme.color("text"),
            selectbackground=bc_theme.color("select_bg"),
            selectforeground=bc_theme.color("select_fg"),
            relief="flat",
            highlightthickness=1,
            highlightbackground=bc_theme.color("border"),
            padx=8,
            pady=6,
        )
        self.cookie_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            text_wrap, orient="vertical", command=self.cookie_text.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.cookie_text.configure(yscrollcommand=scrollbar.set)

        manual_buttons = ttk.Frame(manual_box)
        manual_buttons.grid(row=2, column=0, columnspan=2, sticky="ew",
                            pady=(8, 0))
        ttk.Button(
            manual_buttons, text="Применить", command=self._apply_manual
        ).pack(side="left")
        ttk.Button(
            manual_buttons, text="Из файла…", command=self._load_file
        ).pack(side="left", padx=8)
        ttk.Button(
            manual_buttons,
            text="Открыть bandcamp.com",
            command=lambda: webbrowser.open("https://bandcamp.com/"),
        ).pack(side="left")

        # -- низ ------------------------------------------------------------
        footer = ttk.Frame(body)
        footer.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        ttk.Label(
            footer,
            text="Cookies хранятся только в памяти и не записываются на диск.",
            style="Muted.TLabel",
        ).pack(side="left")
        ttk.Button(footer, text="Закрыть", command=self.destroy).pack(
            side="right"
        )

        localize_widgets(body)
        center_window(self, parent)
        self.grab_set()
        self.cookie_text.focus_set()

    # ------------------------------------------------------------------

    def _import_browser(self) -> None:
        browser_label = self.browser_var.get()
        browser_id = self.app._browser_id_by_label.get(browser_label, "auto")
        self.import_btn.configure(state="disabled")
        self.status_var.set(tr("Читаю cookies из браузера…"))
        results: queue.Queue = queue.Queue()

        def work():
            results.put(core.import_browser_cookies(browser_id))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                cookies, used, errors = results.get_nowait()
            except queue.Empty:
                self.after(120, poll)
                return
            self.import_btn.configure(state="normal")
            if cookies:
                client = self.app._ensure_client()
                count = client.set_cookies(cookies)
                label = self.app._browser_labels.get(used, used)
                self.app._on_cookies_applied(
                    f"browser:{used}", label, count
                )
                self.status_var.set(
                    tr(
                        "Загружено cookies: {count} ({label}).",
                        count=count,
                        label=label,
                    )
                )
                self.app._post_log(
                    tr(
                        "Cookies Bandcamp загружены из {label}: {count}.",
                        label=label,
                        count=count,
                    ),
                    "ok",
                )
            else:
                detail = (
                    "\n".join(errors[:5])
                    if errors
                    else tr("Причина неизвестна.")
                )
                self.status_var.set(
                    tr("Активная сессия Bandcamp не найдена.")
                )
                messagebox.showerror(
                    tr("Cookies не найдены"),
                    tr(
                        "Не удалось найти вход в Bandcamp в этом браузере.\n\n"
                        "{detail}\n\n"
                        "Войдите на bandcamp.com (именно в этом браузере) или "
                        "вставьте cookies вручную.",
                        detail=detail,
                    ),
                    parent=self,
                )

        self.after(120, poll)

    def _apply_manual(self) -> None:
        pairs = core.parse_cookie_text(
            self.cookie_text.get("1.0", "end")
        )
        if not pairs:
            messagebox.showwarning(
                "Cookies",
                tr(
                    "Не удалось распознать cookies. Вставьте строку вида "
                    "identity=...; session=... или файл cookies.txt."
                ),
                parent=self,
            )
            return
        client = self.app._ensure_client()
        count = client.set_cookies(pairs)
        self.app._on_cookies_applied("manual", tr("вручную"), count)
        self.status_var.set(
            tr("Применено cookies: {count}.", count=count)
        )
        self.app._post_log(
            tr("Cookies применены вручную: {count}.", count=count), "ok"
        )

    def _load_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=tr("Файл cookies"),
            filetypes=[
                ("Cookies", "*.txt"),
                (tr("Все файлы"), "*.*"),
            ],
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            messagebox.showerror(
                tr("Файл"),
                tr("Не удалось прочитать файл:\n") + str(exc),
                parent=self,
            )
            return
        self.cookie_text.delete("1.0", "end")
        self.cookie_text.insert("1.0", text)
        self._apply_manual()


# ---------------------------------------------------------------------------
# Дополнительные параметры
# ---------------------------------------------------------------------------

class AdvancedDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, app):
        super().__init__(parent)
        self.app = app
        self.title(tr("Дополнительные параметры"))
        self.configure(bg=bc_theme.color("bg"))
        self.transient(parent)
        self.grab_set()
        self.resizable(True, False)
        self.minsize(620, 480)

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Дополнительные параметры", style="H1.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            body,
            text="Эти настройки сохраняются между запусками.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))

        row = 2

        ttk.Label(body, text="Шаблон имени:").grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=5
        )
        self.template_var = tk.StringVar(value=app.template_var.get())
        template_entry = ttk.Entry(body, textvariable=self.template_var)
        template_entry.grid(row=row, column=1, sticky="ew", pady=5)
        template_entry.bind("<KeyRelease>", self._update_preview)
        row += 1

        ttk.Label(
            body,
            text=(
                "Доступные поля: {artist}, {album}, {title}, {year}, "
                "{purchased}, {type}, {format}, {id}, {key}.\n"
                "Символ / создаёт вложенные папки. Например: "
                "{artist}/{year} - {album}"
            ),
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=row, column=1, sticky="w", pady=(0, 6))
        row += 1

        ttk.Label(body, text="Пример пути:").grid(
            row=row, column=0, sticky="nw", padx=(0, 10), pady=4
        )
        self.preview_var = tk.StringVar()
        ttk.Label(
            body,
            textvariable=self.preview_var,
            style="Muted.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=row, column=1, sticky="w", pady=4)
        row += 1

        ttk.Separator(body, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=12
        )
        row += 1

        ttk.Label(body, text="Прокси:").grid(
            row=row, column=0, sticky="w", padx=(0, 10), pady=5
        )
        self.proxy_var = tk.StringVar(value=app.proxy_var.get())
        ttk.Entry(body, textvariable=self.proxy_var).grid(
            row=row, column=1, sticky="ew", pady=5
        )
        row += 1

        ttk.Label(
            body,
            text=(
                "Необязательно. Например: http://127.0.0.1:8080 или "
                "socks5://127.0.0.1:1080. Применяется при следующем "
                "обновлении коллекции."
            ),
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=row, column=1, sticky="w", pady=(0, 6))
        row += 1

        numbers = ttk.Frame(body)
        numbers.grid(row=row, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(numbers, text="Попыток на файл:").pack(side="left")
        self.attempts_var = tk.StringVar(value=app.attempts_var.get())
        ttk.Spinbox(
            numbers, from_=1, to=10, width=5,
            textvariable=self.attempts_var,
        ).pack(side="left", padx=(8, 22))
        ttk.Label(numbers, text="Пауза между попытками, с:").pack(side="left")
        self.retry_wait_var = tk.StringVar(value=app.retry_wait_var.get())
        ttk.Spinbox(
            numbers, from_=1, to=60, width=5,
            textvariable=self.retry_wait_var,
        ).pack(side="left", padx=8)
        row += 1

        options = ttk.Frame(body)
        options.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.open_folder_var = tk.BooleanVar(value=app.open_folder_var.get())
        self.notify_var = tk.BooleanVar(value=app.notify_var.get())
        self.verbose_var = tk.BooleanVar(value=app.verbose_var.get())
        ttk.Checkbutton(
            options, text="Открывать папку после загрузки",
            variable=self.open_folder_var,
        ).pack(anchor="w")
        ttk.Checkbutton(
            options, text="Показывать окно по завершении",
            variable=self.notify_var,
        ).pack(anchor="w")
        ttk.Checkbutton(
            options, text="Подробный журнал (отладка)",
            variable=self.verbose_var,
        ).pack(anchor="w")
        row += 1

        footer = ttk.Frame(body)
        footer.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        ttk.Button(footer, text="Отмена", command=self.destroy).pack(
            side="right"
        )
        ttk.Button(
            footer, text="Сохранить", style="Accent.TButton",
            command=self._save,
        ).pack(side="right", padx=(0, 8))

        self._update_preview()
        localize_widgets(body)
        center_window(self, parent)

    # ------------------------------------------------------------------

    def _update_preview(self, *_args) -> None:
        try:
            core.validate_template(self.template_var.get())
            out_dir = Path(
                self.app.folder_var.get().strip() or core.default_output_dir()
            )
            fmt = self.app._selected_format_id()
            path = core.preview_template(self.template_var.get(), out_dir, fmt)
            self.preview_var.set(
                str(path) + tr("  (+ расширение .zip / .mp3 / .flac …)")
            )
        except Exception as exc:
            self.preview_var.set(tr("Ошибка: ") + str(exc))

    def _save(self) -> None:
        template = self.template_var.get().strip()
        try:
            core.validate_template(template)
        except core.BandcampError as exc:
            messagebox.showerror(tr("Шаблон"), str(exc), parent=self)
            return
        try:
            attempts = max(1, min(10, int(self.attempts_var.get())))
            retry_wait = max(1.0, min(60.0, float(self.retry_wait_var.get())))
        except ValueError:
            messagebox.showerror(
                tr("Параметры"),
                tr("Попытки и пауза должны быть числами."),
                parent=self,
            )
            return

        self.app.template_var.set(template)
        self.app.proxy_var.set(self.proxy_var.get().strip())
        self.app.attempts_var.set(str(attempts))
        self.app.retry_wait_var.set(str(retry_wait))
        self.app.open_folder_var.set(self.open_folder_var.get())
        self.app.notify_var.set(self.notify_var.get())
        self.app.verbose_var.set(self.verbose_var.get())
        self.app._on_advanced_saved()
        self.destroy()


# ---------------------------------------------------------------------------
# Справка
# ---------------------------------------------------------------------------

class HelpDialog(tk.Toplevel):
    HELP_TEXT_EN = """How to use

1. Sign in to your Bandcamp account in a browser (Chrome, Edge, Firefox, Brave, etc.).
2. Enter your profile name: the part of the address after bandcamp.com/.
   For example, for https://bandcamp.com/myname enter myname.
3. Click “Load collection”. Cookies are read automatically from the selected
   browser. If that fails, use “Sign in…” to import cookies from a browser or
   paste them manually.
4. Select the albums/tracks you need (the checkbox on the left), choose a format
   and a destination folder.
5. Click “Download selected”.

Formats

Bandcamp stores albums as ZIP archives and individual tracks as audio files.
The format is selected on the download page of each purchase. If the selected
format is unavailable, the app downloads the best available one and writes a
warning to the log. “Auto” prefers lossless when it is available.

With “Extract ZIP” enabled, each archive is extracted into a folder with the
same name. “Delete ZIP after extraction” removes the archive after a successful
extraction.

Filename template

{artist}    artist
{album}     album title (for a track: track title)
{title}     item title
{year}      purchase year
{purchased} purchase date
{type}      album / track
{format}    selected format (mp3-320, flac, etc.)
{id}        internal Bandcamp ID
{key}       purchase key

A / creates subfolders. Default: {artist}/{album}

Good to know

• Only purchases linked to your account are downloaded.
• Bandcamp rate-limits requests. On HTTP 429 the app pauses and retries.
• Unfinished downloads are kept as .part files and resumed on retry.
• Cookies are kept in memory only and are never written to disk.
• The app does not bypass DRM or capture streamed audio.

“Check formats” asks Bandcamp for the formats available for the selected items
(one request at a time to avoid rate limits).

Language

Use the language selector in the top-right corner. The interface can be switched
between English and Russian instantly when no download or format check is active.

Theme

The theme selector is next to the language selector. “Auto” follows the system
theme (Windows, macOS, GNOME/GTK, KDE); “Light” and “Dark” force it manually.
The choice is stored in settings.json.

Project and attribution

This application is based on the original bandcamp-downloader by Andrew Slice:
https://github.com/easlice/bandcamp-downloader

This GUI is part of the muesqtk fork:
https://github.com/muesqtk/bandcamp-downloader

The legacy command-line script has been removed from this GUI distribution.
The upstream command-line tool is still available at the original repository.

License (MIT)

Copyright (c) 2022 Andrew Slice
Copyright (c) 2026 muesqtk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

    HELP_TEXT_RU = """Как пользоваться

1. Войдите в свой аккаунт Bandcamp в браузере (Chrome, Edge, Firefox, Brave и т.п.).
2. Укажите имя профиля: часть адреса после bandcamp.com/.
   Например, для https://bandcamp.com/myname введите myname.
3. Нажмите «Загрузить коллекцию». Cookies читаются из выбранного браузера
   автоматически. Если это не сработало — кнопка «Войти…» позволяет
   импортировать cookies из браузера или вставить их вручную.
4. Отметьте нужные альбомы/треки (галочка слева), выберите формат и папку.
5. Нажмите «Скачать выбранные».

Форматы

Bandcamp хранит альбомы в ZIP-архиве, а отдельные треки — файлами.
Формат выбирается на странице скачивания конкретной покупки. Если выбранного
формата нет, приложение скачает лучший доступный и предупредит в журнале.
«Авто» выбирает lossless, если он доступен.

При включённой галочке «Распаковывать ZIP» архив будет распакован в папку
с тем же именем. «Удалять ZIP после распаковки» удаляет архив после успешной
распаковки.

Шаблон имени файла

{artist}    исполнитель
{album}     название альбома (для трека — название трека)
{title}     название позиции
{year}      год покупки
{purchased} дата покупки
{type}      album / track
{format}    выбранный формат (mp3-320, flac …)
{id}        внутренний id Bandcamp
{key}       ключ покупки

Символ / создаёт подпапки. По умолчанию: {artist}/{album}

Полезно знать

• Скачиваются только покупки, привязанные к вашему аккаунту.
• Bandcamp ограничивает частоту запросов. При HTTP 429 приложение
  само делает паузу и повторяет попытку.
• Незавершённые загрузки сохраняются как .part и докачиваются при повторе.
• Cookies не сохраняются на диск — только в оперативной памяти.
• Приложение не обходит DRM и не скачивает потоковое аудио.

Кнопка «Проверить форматы» запрашивает у Bandcamp список форматов
для выбранных позиций (по одной, чтобы не получить блокировку).

Язык

Переключатель языка находится в правом верхнем углу. Интерфейс можно
мгновенно переключить между английским и русским, если не идёт загрузка
или проверка форматов.

Тема

Переключатель темы находится рядом с языком. «Авто» следует теме системы
(Windows, macOS, GNOME/GTK, KDE), «Светлая» и «Тёмная» задают её вручную.
Выбор сохраняется в settings.json.

Проект и авторство

Приложение основано на оригинальном bandcamp-downloader Эндрю Слайса:
https://github.com/easlice/bandcamp-downloader

Этот GUI является частью форка muesqtk:
https://github.com/muesqtk/bandcamp-downloader

Старый консольный скрипт удалён из этой GUI-сборки. Оригинальный
командный инструмент по-прежнему доступен в исходном репозитории.

Лицензия (MIT)

Copyright (c) 2022 Andrew Slice
Copyright (c) 2026 muesqtk

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title(tr("Справка"))
        self.configure(bg=bc_theme.color("bg"))
        self.transient(parent)
        self.minsize(680, 560)

        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text="Справка", style="H1.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        text_wrap = ttk.Frame(body)
        text_wrap.grid(row=1, column=0, sticky="nsew")
        text_wrap.rowconfigure(0, weight=1)
        text_wrap.columnconfigure(0, weight=1)
        text = tk.Text(
            text_wrap,
            wrap="word",
            font=("Segoe UI", 9),
            bg=bc_theme.color("card"),
            fg=bc_theme.color("text"),
            insertbackground=bc_theme.color("text"),
            selectbackground=bc_theme.color("select_bg"),
            selectforeground=bc_theme.color("select_fg"),
            relief="flat",
            highlightthickness=1,
            highlightbackground=bc_theme.color("border"),
            padx=12,
            pady=10,
        )
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            text_wrap, orient="vertical", command=text.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        text.configure(yscrollcommand=scrollbar.set)
        help_text = (
            self.HELP_TEXT_RU if get_language() == "ru" else self.HELP_TEXT_EN
        )
        text.insert("1.0", help_text)
        text.configure(state="disabled")

        footer = ttk.Frame(body)
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(
            footer, text="Открыть bandcamp.com",
            command=lambda: webbrowser.open("https://bandcamp.com/"),
        ).pack(side="left")
        ttk.Button(
            footer, text="Проект на GitHub",
            command=lambda: webbrowser.open(
                "https://github.com/muesqtk/bandcamp-collection-downloader"
            ),
        ).pack(side="left", padx=(8, 0))
        ttk.Button(footer, text="Закрыть", command=self.destroy).pack(
            side="right"
        )
        localize_widgets(body)
        center_window(self, parent)
