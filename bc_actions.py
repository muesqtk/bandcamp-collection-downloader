#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сетевая часть GUI: загрузка коллекции, cookies, скачивание, форматы."""

from __future__ import annotations

import threading
import time
import traceback
import webbrowser
from collections import Counter, deque
from pathlib import Path

from tkinter import messagebox

import bc_core as core
from bc_i18n import tr

_TERMINAL = {"done", "error", "skipped", "exists", "cancelled", "unavailable"}


class ActionMixin:
    # ------------------------------------------------------------------
    # Клиент / cookies
    # ------------------------------------------------------------------

    def _ensure_client(self):
        proxy = self.proxy_var.get().strip() or None
        if self.client is None:
            self.client = core.HttpClient(log=self._client_log, proxy=proxy)
        else:
            old_proxy = self.client.proxy
            self.client.set_proxy(proxy)
            if old_proxy != proxy:
                self._cookie_source = None
                self._cookie_source_label = ""
                self._post_log(
                    tr("Прокси изменён — cookies Bandcamp нужно загрузить заново."),
                    "warn",
                )
        try:
            attempts = max(1, min(10, int(self.attempts_var.get())))
        except (TypeError, ValueError):
            attempts = 4
        try:
            retry_wait = max(1.0, min(60.0, float(self.retry_wait_var.get())))
        except (TypeError, ValueError):
            retry_wait = 3.0
        self.client.set_limits(attempts, retry_wait)
        self._update_cookie_status()
        return self.client

    def _on_cookies_applied(self, source: str, label: str, count: int) -> None:
        self._cookie_source = source
        self._cookie_source_label = label
        self._update_cookie_status()
        self._set_status(
            tr("Cookies загружены: {count} ({label})", count=count, label=label)
        )

    def _ev_cookies_ok(self, payload) -> None:
        source, label, count = payload
        self._cookie_source = source
        self._cookie_source_label = label
        self._update_cookie_status()
        self._append_log(
            tr(
                "Cookies Bandcamp загружены из {label}: {count}.",
                label=label,
                count=count,
            ),
            "ok",
        )

    # ------------------------------------------------------------------
    # Загрузка коллекции
    # ------------------------------------------------------------------

    def _on_load(self) -> None:
        if self._loading or self.job is not None or self._formats_running:
            return
        username = core.normalize_username(self.username_var.get())
        if not username:
            messagebox.showinfo(
                tr("Профиль Bandcamp"),
                tr(
                    "Укажите имя профиля — часть адреса после bandcamp.com/.\n"
                    "Например: myname или https://bandcamp.com/myname"
                ),
                parent=self.root,
            )
            self.username_entry.focus_set()
            return
        self.username_var.set(username)

        try:
            client = self._ensure_client()
        except Exception as exc:
            messagebox.showerror(
                tr("HTTP-клиент"),
                tr("Не удалось создать клиент:\n") + str(exc),
                parent=self.root,
            )
            return

        browser_id = self._selected_browser_id()
        source = self._cookie_source or ""
        need_cookies = client.cookie_count == 0 or self._cookie_source is None
        if (not need_cookies and source.startswith("browser:")
                and browser_id != "auto"
                and source != f"browser:{browser_id}"):
            need_cookies = True

        self._loading = True
        self._set_status(tr("Загрузка коллекции…"))
        self._sync_action_buttons()
        try:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        except Exception:
            pass
        self._save_settings()
        self._append_log(
            tr(
                "Загружаю коллекцию профиля «{username}»{hidden} …",
                username=username,
                hidden=tr(" (включая скрытые)") if self.hidden_var.get() else "",
            ),
            "debug",
        )

        threading.Thread(
            target=self._load_worker,
            args=(username, bool(self.hidden_var.get()), browser_id,
                  need_cookies),
            daemon=True,
        ).start()

    def _load_worker(self, username: str, include_hidden: bool,
                     browser_id: str, need_cookies: bool) -> None:
        try:
            if need_cookies:
                cookies, used, errors = core.import_browser_cookies(browser_id)
                if not cookies:
                    detail = (
                        "; ".join(errors[:4])
                        if errors
                        else tr("cookies не найдены")
                    )
                    raise core.AuthError(
                        tr(
                            "Не удалось прочитать cookies Bandcamp из браузера.\n"
                            "({detail})\n\n"
                            "Войдите на bandcamp.com в браузере и повторите, либо "
                            "нажмите «Войти…» и вставьте cookies вручную.",
                            detail=detail,
                        )
                    )
                count = self.client.set_cookies(cookies)
                label = self._browser_labels.get(used, used)
                self._queue.put(
                    ("cookies_ok", (f"browser:{used}", label, count))
                )
            items = self.client.get_collection(
                username,
                include_hidden,
                progress=lambda loaded, total: self._queue.put(
                    ("load_progress", (loaded, total))
                ),
            )
            self._queue.put(("collection", (items, username)))
        except core.AuthError as exc:
            self._queue.put(
                ("load_error", (str(exc), traceback.format_exc(), True))
            )
        except Exception as exc:
            self._queue.put(
                ("load_error", (str(exc), traceback.format_exc(), False))
            )

    def _ev_load_progress(self, payload) -> None:
        loaded, total = payload
        if total:
            self._set_status(
                tr(
                    "Загрузка коллекции… {loaded} из {total}",
                    loaded=loaded,
                    total=total,
                )
            )
        else:
            self._set_status(
                tr("Загрузка коллекции… {loaded}", loaded=loaded)
            )

    def _ev_collection(self, payload) -> None:
        items, username = payload
        self._loading = False
        try:
            self.progress.stop()
        except Exception:
            pass
        self.progress.configure(mode="determinate", value=0)

        self.items = list(items)
        self.items_by_key = {item.key: item for item in self.items}
        for item in self.items:
            item.selected = True

        self._preview_key = None
        self._show_preview(None)
        self._mark_existing(self.items)
        self._rebuild_tree()

        self.username_var.set(username)
        self.root.title(f"{username} — {core.APP_NAME}")
        count = len(self.items)
        if count:
            self._set_status(
                tr("Коллекция: {count} позиций", count=count)
            )
            self._append_log(
                tr(
                    "Коллекция «{username}»: {count} позиций, доступных для скачивания.",
                    username=username,
                    count=count,
                ),
                "ok",
            )
            self._append_log(
                tr(
                    "Все позиции отмечены. Снимите галочки с ненужных "
                    "и нажмите «Скачать выбранные»."
                ),
                "debug",
            )
        else:
            self._set_status(tr("Коллекция пуста"))
            self._append_log(
                tr(
                    "В коллекции не найдено покупок с доступным скачиванием."
                ),
                "warn",
            )
        self._save_settings()
        self._sync_action_buttons()

    def _ev_load_error(self, payload) -> None:
        message, details, auth = payload
        self._loading = False
        try:
            self.progress.stop()
        except Exception:
            pass
        self.progress.configure(mode="determinate", value=0)
        self._set_status(tr("Ошибка загрузки коллекции"))
        self._append_log(message, "error")
        if details:
            self._append_log(details, "debug")
        self._sync_action_buttons()

        if auth:
            if messagebox.askyesno(
                tr("Нужен вход в Bandcamp"),
                message + "\n\n" + tr("Открыть bandcamp.com в браузере?"),
                parent=self.root,
            ):
                webbrowser.open("https://bandcamp.com/")
        else:
            messagebox.showerror(tr("Ошибка"), message, parent=self.root)

    # ------------------------------------------------------------------
    # Скачивание
    # ------------------------------------------------------------------

    def _on_download(self) -> None:
        if self.job is not None or self._loading or self._formats_running:
            return
        selected = self._selected_items()
        if not selected:
            messagebox.showinfo(
                tr("Нет выбора"),
                tr("Отметьте хотя бы один альбом или трек."),
                parent=self.root,
            )
            return

        out_dir = Path(
            self.folder_var.get().strip() or core.default_output_dir()
        )
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                tr("Папка"),
                tr("Не удалось создать папку загрузки:\n") + str(exc),
                parent=self.root,
            )
            return

        template = self.template_var.get().strip() or core.DEFAULT_TEMPLATE
        try:
            core.validate_template(template)
        except core.BandcampError as exc:
            messagebox.showerror(
                tr("Шаблон имени"), str(exc), parent=self.root
            )
            return

        try:
            threads = int(self.threads_var.get())
        except (TypeError, ValueError):
            threads = core.DEFAULT_THREADS
        threads = max(1, min(core.MAX_PARALLEL, threads))
        self.threads_var.set(str(threads))

        try:
            attempts = max(1, min(10, int(self.attempts_var.get())))
            retry_wait = max(1.0, min(60.0, float(self.retry_wait_var.get())))
        except (TypeError, ValueError):
            attempts, retry_wait = 4, 3.0
        self.attempts_var.set(str(attempts))
        self.retry_wait_var.set(str(retry_wait))

        try:
            client = self._ensure_client()
        except Exception as exc:
            messagebox.showerror(tr("HTTP-клиент"), str(exc), parent=self.root)
            return

        extract = bool(self.extract_var.get())
        options = core.DownloadOptions(
            fmt=self._selected_format_id(),
            out_dir=out_dir,
            template=template,
            threads=threads,
            skip_existing=bool(self.skip_var.get()),
            extract=extract,
            delete_zip=bool(self.delete_zip_var.get()) and extract,
            attempts=attempts,
            retry_wait=retry_wait,
            proxy=self.proxy_var.get().strip() or None,
        )

        self._last_out_dir = out_dir
        for item in selected:
            item.state = "queued"
            item.message = ""
            item.final_size = 0
        self._job_items = selected
        self._job_total = len(selected)
        self._job_fraction = {item.key: 0.0 for item in selected}
        self._job_bytes = {}
        self._last_row_update = {}
        self._speed_samples = deque([(time.monotonic(), 0)], maxlen=40)
        self._last_progress_ui = 0.0

        self.progress.configure(mode="determinate", maximum=100, value=0)
        self.progress_label.configure(
            text=tr("0 из {total}", total=len(selected))
        )
        self._update_all_rows()

        job = core.DownloadJob(client, selected, options, self._queue_event)
        self.job = job
        self._sync_action_buttons()
        self._set_status(
            tr("Скачивание: 0 из {total}", total=len(selected))
        )
        self._append_log(
            tr(
                "Начинаю загрузку: {count} поз., формат "
                "«{format}», потоков {threads}, папка {folder}.",
                count=len(selected),
                format=core.format_label(options.fmt),
                threads=threads,
                folder=out_dir,
            ),
            "info",
        )
        self._save_settings()
        job.start()

    def _on_cancel(self) -> None:
        if self.job is None:
            return
        self.job.cancel()
        self.cancel_btn.configure(state="disabled")
        self._set_status(tr("Отмена…"))
        self._append_log(tr("Запрошена отмена загрузки."), "warn")


    def _ev_job_started(self, payload) -> None:
        total = int(payload.get("total") or 0)
        self._set_status(tr("Скачивание: 0 из {total}", total=total))

    def _ev_item_status(self, payload) -> None:
        key = payload.get("key")
        item = self.items_by_key.get(key)
        if item is None:
            return
        item.state = str(payload.get("state") or "")
        item.message = str(payload.get("message") or "")
        if "formats" in payload:
            item.formats = list(payload.get("formats") or [])
            item.info_loaded = True
        if "size" in payload:
            try:
                item.final_size = int(payload.get("size") or 0)
            except (TypeError, ValueError):
                item.final_size = 0
        if item.state in ("done", "skipped"):
            item.exists = True
        if item.state in _TERMINAL:
            self._job_fraction[key] = 1.0
            if item.final_size:
                self._job_bytes[key] = (item.final_size, item.final_size)
            self._last_row_update.pop(key, None)
        self._update_row(item)
        if self._preview_key == key:
            self._update_preview_info(item)
        self._refresh_progress_ui()

    def _ev_item_progress(self, payload) -> None:
        key = payload.get("key")
        item = self.items_by_key.get(key)
        if item is None:
            return
        done = int(payload.get("done") or 0)
        total = int(payload.get("total") or 0)
        fraction = min(1.0, done / total) if total > 0 else 0.0
        self._job_fraction[key] = fraction
        self._job_bytes[key] = (done, total)
        item.state = "working"
        if total > 0:
            item.message = tr(
                "Скачивание {done}%", done=int(fraction * 100)
            )
        else:
            item.message = tr(
                "Скачивание {size}", size=core.human_size(done)
            )

        now = time.monotonic()
        if now - self._last_row_update.get(key, 0) >= 0.4:
            self._last_row_update[key] = now
            self._update_row(item)
        self._refresh_progress_ui()

    def _refresh_progress_ui(self) -> None:
        if not self._job_total:
            return
        now = time.monotonic()
        if now - self._last_progress_ui < 0.15:
            return
        self._last_progress_ui = now

        fraction = sum(self._job_fraction.values()) / max(1, self._job_total)
        self.progress["value"] = min(100.0, max(0.0, fraction * 100.0))
        completed = sum(
            1 for item in self._job_items if item.state in _TERMINAL
        )
        active = sum(
            1 for item in self._job_items if item.state == "working"
        )
        done_bytes = sum(done for done, _total in self._job_bytes.values())

        self._speed_samples.append((now, done_bytes))
        while (len(self._speed_samples) > 2
               and now - self._speed_samples[0][0] > 5.0):
            self._speed_samples.popleft()
        speed = 0.0
        if len(self._speed_samples) >= 2:
            first_t, first_b = self._speed_samples[0]
            last_t, last_b = self._speed_samples[-1]
            span = last_t - first_t
            if span > 0.4:
                speed = max(0.0, (last_b - first_b) / span)

        parts = [
            tr(
                "{completed} из {total}",
                completed=completed,
                total=self._job_total,
            )
        ]
        if active:
            parts.append(tr("{active} в работе", active=active))
        if done_bytes:
            parts.append(core.human_size(done_bytes))
        if speed > 0:
            parts.append(tr("{size}/с", size=core.human_size(speed)))
        try:
            self.progress_label.configure(text=" • ".join(parts))
        except Exception:
            pass

    def _ev_job_finished(self, payload) -> None:
        items = list(self._job_items)
        cancelled = bool(payload.get("cancelled"))
        elapsed = float(payload.get("elapsed") or 0.0)

        if not items:
            self.job = None
            self._sync_action_buttons()
            return

        states = Counter(item.state for item in items)
        done = states.get("done", 0)
        skipped = states.get("skipped", 0) + states.get("exists", 0)
        errors = states.get("error", 0)
        unavailable = states.get("unavailable", 0)
        cancelled_count = states.get("cancelled", 0)
        total_bytes = sum(item.final_size for item in items)

        for item in items:
            self._job_fraction[item.key] = 1.0
        self.job = None

        summary_parts = [tr("Скачано: {done}", done=done)]
        if skipped:
            summary_parts.append(
                tr("пропущено: {count}", count=skipped)
            )
        if unavailable:
            summary_parts.append(
                tr("без формата: {count}", count=unavailable)
            )
        if errors:
            summary_parts.append(tr("ошибок: {count}", count=errors))
        if cancelled_count:
            summary_parts.append(
                tr("отменено: {count}", count=cancelled_count)
            )
        if total_bytes:
            summary_parts.append(core.human_size(total_bytes))
        if elapsed:
            summary_parts.append(core.human_duration(elapsed))
        summary = " • ".join(summary_parts)

        if cancelled:
            self.progress["value"] = min(
                100.0,
                sum(self._job_fraction.values()) / max(1, len(items)) * 100.0,
            )
        else:
            self.progress["value"] = 100
        self.progress_label.configure(text=summary)
        self._set_status(
            tr("Загрузка отменена") if cancelled else tr("Готово")
        )
        self._append_log(
            tr("Загрузка завершена: {summary}.", summary=summary),
            "warn" if (errors or cancelled) else "ok",
        )

        self._job_total = 0
        self._job_items = []
        self._job_fraction = {}
        self._job_bytes = {}
        self._sync_action_buttons()
        self._refresh_existing_flags()
        self._save_settings()

        if self.open_folder_var.get() and done:
            try:
                core.open_path(self._last_out_dir)
            except Exception as exc:
                self._append_log(
                    tr(
                        "Не удалось открыть папку: {error}",
                        error=exc,
                    ),
                    "warn",
                )

        if self.notify_var.get():
            title = (
                tr("Загрузка отменена")
                if cancelled
                else tr("Загрузка завершена")
            )
            text = tr(
                "Скачано: {done}\n"
                "Пропущено: {skipped}\n"
                "Без доступного формата: {unavailable}\n"
                "Ошибок: {errors}\n"
                "Отменено: {cancelled}\n"
                "Объём: {size}\n"
                "Время: {elapsed}",
                done=done,
                skipped=skipped,
                unavailable=unavailable,
                errors=errors,
                cancelled=cancelled_count,
                size=core.human_size(total_bytes),
                elapsed=core.human_duration(elapsed),
            )
            if errors:
                messagebox.showwarning(title, text, parent=self.root)
            else:
                messagebox.showinfo(title, text, parent=self.root)

    # ------------------------------------------------------------------
    # Проверка форматов
    # ------------------------------------------------------------------

    def _on_check_formats(self) -> None:
        if self._formats_running or self._loading or self.job is not None:
            return
        if self.client is None:
            messagebox.showinfo(
                tr("Форматы"),
                tr("Сначала загрузите коллекцию."),
                parent=self.root,
            )
            return
        items = self._selected_items()
        if not items:
            messagebox.showinfo(
                tr("Форматы"),
                tr("Отметьте хотя бы одну позицию."),
                parent=self.root,
            )
            return
        if len(items) > 80:
            if not messagebox.askyesno(
                tr("Проверка форматов"),
                tr(
                    "Выбрано {count} позиций. Bandcamp придётся запросить "
                    "по одной странице — это может занять несколько минут.\n\n"
                    "Продолжить?",
                    count=len(items),
                ),
                parent=self.root,
            ):
                return

        self._formats_running = True
        self._sync_action_buttons()
        self._set_status(
            tr("Проверка форматов: 0 из {total}", total=len(items))
        )
        try:
            self.progress.configure(mode="determinate", maximum=100, value=0)
        except Exception:
            pass
        self._append_log(
            tr(
                "Проверяю доступные форматы для {count} позиций…",
                count=len(items),
            ),
            "info",
        )
        selected_fmt = self._selected_format_id()

        def work():
            ok = 0
            unavailable = 0
            for index, item in enumerate(items, start=1):
                if self._closing:
                    return
                try:
                    info = self.client.get_download_info(
                        item.redownload_url, item.item_id
                    )
                    formats = core.sort_formats(info.downloads.keys())
                    self._queue.put(("item_formats", (item.key, formats)))
                    ok += 1
                    if selected_fmt != "auto" and selected_fmt not in info.downloads:
                        unavailable += 1
                except Exception as exc:
                    self._queue.put((
                        "log",
                        (
                            "warn",
                            tr(
                                "Не удалось проверить «{artist} — {title}»: {error}",
                                artist=item.artist,
                                title=item.title,
                                error=exc,
                            ),
                        ),
                    ))
                self._queue.put(
                    ("formats_progress", (index, len(items)))
                )
                time.sleep(0.35)
            self._queue.put(
                ("formats_done", (ok, unavailable, len(items)))
            )

        threading.Thread(target=work, daemon=True).start()

    def _ev_item_formats(self, payload) -> None:
        key, formats = payload
        item = self.items_by_key.get(key)
        if item is None:
            return
        item.formats = list(formats)
        item.info_loaded = True
        self._update_row(item)
        if self._preview_key == key:
            self._update_preview_info(item)

    def _ev_formats_progress(self, payload) -> None:
        index, total = payload
        self._set_status(
            tr(
                "Проверка форматов: {index} из {total}",
                index=index,
                total=total,
            )
        )
        try:
            pct = (index / total * 100.0) if total else 0.0
            self.progress.configure(mode="determinate", maximum=100, value=pct)
        except Exception:
            pass

    def _ev_formats_done(self, payload) -> None:
        ok, unavailable, total = payload
        self._formats_running = False
        self._sync_action_buttons()
        self._set_status(
            tr(
                "Форматы проверены: {ok} из {total}",
                ok=ok,
                total=total,
            )
        )
        try:
            self.progress.configure(mode="determinate", maximum=100, value=100)
        except Exception:
            pass
        self._append_log(
            tr(
                "Проверка форматов завершена: {ok} из {total}.",
                ok=ok,
                total=total,
            ),
            "ok",
        )
        if unavailable:
            self._append_log(
                tr(
                    "У {count} позиций нет выбранного формата "
                    "«{format}» — будет скачан лучший доступный.",
                    count=unavailable,
                    format=core.format_label(self._selected_format_id()),
                ),
                "warn",
            )

    # ------------------------------------------------------------------
    # Прочее
    # ------------------------------------------------------------------

    def _on_advanced_saved(self) -> None:
        self._save_settings()
        self._sync_extract_controls()
        self._schedule_existing_refresh()
        if self.client is not None:
            try:
                self._ensure_client()
            except Exception as exc:
                self._post_log(
                    tr(
                        "Не удалось применить параметры клиента: {error}",
                        error=exc,
                    ),
                    "warn",
                )
        self._post_log(tr("Дополнительные параметры сохранены."), "debug")

    def _on_close(self) -> None:
        if self.job is not None:
            if not messagebox.askyesno(
                tr("Выход"),
                tr("Идёт скачивание. Прервать загрузку и выйти?"),
                parent=self.root,
            ):
                return
            self.job.cancel()
        self._save_settings()
        self._closing = True
        try:
            self._art_pool.shutdown()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
