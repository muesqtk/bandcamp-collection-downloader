#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bandcamp Collection Downloader — графический запуск.

Проверяет зависимости и открывает главное окно.
Только для контента, который вы купили на Bandcamp.
"""

from __future__ import annotations

import sys

import bc_core as core
from bc_i18n import load_saved_language, set_language, tr


def _show_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()
    except Exception:
        print(f"{title}\n\n{message}", file=sys.stderr)


def _dependency_error(missing: list[str]) -> int:
    packages = "  ".join(missing)
    message = tr(
        "Не установлены необходимые библиотеки:\n\n"
        "  {packages}\n\n"
        "Откройте командную строку в папке программы и выполните:\n\n"
        "    pip install -r requirements.txt\n\n"
        "или:\n\n"
        "    pip install {packages}",
        packages=packages,
    )
    _show_error(core.APP_NAME, message)
    return 2


def main() -> int:
    if "--version" in sys.argv:
        print(f"{core.APP_NAME} {core.APP_VERSION}")
        return 0

    set_language(load_saved_language(core.config_dir() / "settings.json"))

    missing: list[str] = []
    if not core.HTTP_BACKEND:
        missing.append("curl_cffi requests")
    if core.BeautifulSoup is None:
        missing.append("beautifulsoup4")
    if missing:
        return _dependency_error(missing)

    try:
        from bc_gui import run
    except Exception as exc:
        _show_error(
            core.APP_NAME,
            tr(
                "Не удалось загрузить интерфейс приложения.\n\n"
                "{error}\n\n"
                "Убедитесь, что файлы bc_core.py, bc_ui.py, bc_actions.py, "
                "bc_dialogs.py, bc_theme.py и bc_gui.py находятся рядом с этим файлом.",
                error=exc,
            ),
        )
        return 1

    return run()


if __name__ == "__main__":
    sys.exit(main())
