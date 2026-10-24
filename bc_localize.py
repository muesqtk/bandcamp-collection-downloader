#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small helper for translating already-created Tk widget trees."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bc_i18n import tr


def localize_widgets(widget: tk.Misc) -> None:
    """Translate static widget texts and read-only combobox values in place."""
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except (tk.TclError, AttributeError):
            text = None
        if isinstance(text, str) and text:
            translated = tr(text)
            if translated != text:
                try:
                    child.configure(text=translated)
                except tk.TclError:
                    pass
        if isinstance(child, ttk.Combobox):
            try:
                values = list(child.cget("values"))
                translated_values = [tr(str(value)) for value in values]
                if translated_values != values:
                    child.configure(values=translated_values)
            except tk.TclError:
                pass
        localize_widgets(child)
