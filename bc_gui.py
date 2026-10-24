#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка приложения и запуск главного окна."""

from __future__ import annotations

import sys
import traceback

import tkinter as tk
from tkinter import messagebox

import bc_core as core
from bc_actions import ActionMixin
from bc_i18n import load_saved_language, set_language, tr
from bc_ui import AppBase


class App(ActionMixin, AppBase):
    """Полное приложение: интерфейс из AppBase + сеть из ActionMixin."""


def _enable_dpi_awareness() -> None:
    """Включает чёткий рендеринг на мониторах с масштабированием (Windows)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        try:
            # PROCESS_SYSTEM_DPI_AWARE
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _configure_scaling(root: tk.Tk) -> None:
    """Подгоняет масштаб Tk под фактический DPI монитора."""
    try:
        dpi = float(root.winfo_fpixels("1i"))
        if dpi > 0:
            root.tk.call("tk", "scaling", max(1.0, dpi / 72.0))
    except Exception:
        pass


def run() -> int:
    _enable_dpi_awareness()
    set_language(load_saved_language(core.config_dir() / "settings.json"))

    try:
        root = tk.Tk()
    except Exception as exc:
        print(
            tr("Не удалось создать окно Tkinter: {error}", error=exc),
            file=sys.stderr,
        )
        return 1

    _configure_scaling(root)

    try:
        App(root)
    except Exception:
        text = traceback.format_exc()
        core.write_crash_log(text)
        try:
            root.withdraw()
            messagebox.showerror(
                core.APP_NAME,
                tr(
                    "Не удалось запустить приложение.\n\n"
                    "{error}\n\n"
                    "Подробности записаны в журнал ошибок.",
                    error=text.strip().splitlines()[-1],
                ),
                parent=root,
            )
        except Exception:
            print(text, file=sys.stderr)
        finally:
            try:
                root.destroy()
            except Exception:
                pass
        return 1

    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(run())
