#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bilingual UI strings (Russian source, English translation).

The application keeps Russian as the source language.  Use ``tr()`` for every
user-visible string; when English is selected, the lookup table below is used.
Unknown strings are returned unchanged so technical values (formats, paths,
server messages) are never damaged.
"""

from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path
from typing import Any

LANGUAGES = {"ru": "Русский", "en": "English"}
LANGUAGE_BY_LABEL = {label: code for code, label in LANGUAGES.items()}
DEFAULT_LANGUAGE = "en"

LANGUAGE = DEFAULT_LANGUAGE


# Russian source -> English translation.
EN: dict[str, str] = {
    # ------------------------------------------------------------------
    # Common
    # ------------------------------------------------------------------
    "Готово": "Ready",
    "Отмена": "Cancel",
    "Отмена…": "Cancelling…",
    "Закрыть": "Close",
    "Сохранить": "Save",
    "Применить": "Apply",
    "Ошибка": "Error",
    "Ошибка: ": "Error: ",
    "неизвестно": "unknown",
    "нет": "none",
    "Все": "All",
    "Авто": "Auto",
    "Авто (лучшее доступное)": "Auto (best available)",
    "Альбом": "Album",
    "Трек": "Track",
    "Альбомы": "Albums",
    "Треки": "Tracks",
    "Папка": "Folder",
    "Файл": "File",
    "Журнал": "Log",
    "Справка": "Help",
    "Шаблон": "Template",
    "Шаблон имени": "Filename template",
    "Параметры": "Settings",
    "Выход": "Exit",
    "Все файлы": "All files",
    "Текст": "Text",
    "Язык:": "Language:",
    "вручную": "manually",
    "из браузера": "from browser",
    " · будут обновлены": " · will be refreshed",
    "—": "—",
    "…": "…",
    " ▼": " ▼",
    " ▲": " ▲",
    " · ": " · ",
    " • ": " • ",
    " из ": " of ",
    "…": "…",

    # ------------------------------------------------------------------
    # Main window
    # ------------------------------------------------------------------
    "Скачивание купленных альбомов и треков": "Download your purchased albums and tracks",
    "только ваш купленный контент": "purchased content only",
    "Профиль:": "Profile:",
    "Загрузить коллекцию": "Load collection",
    "Загрузка…": "Loading…",
    "Скрытые покупки": "Hidden purchases",
    "Cookies из:": "Cookies from:",
    "Войти…": "Sign in…",
    "Поиск:": "Search:",
    "Тип:": "Type:",
    "Только не скачанные": "Missing only",
    "Снять все": "Clear all",
    "Выбрать все": "Select all",
    "Выбрано: 0": "Selected: 0",
    "Исполнитель": "Artist",
    "Название": "Title",
    "Тип": "Type",
    "Куплено": "Purchased",
    "Форматы": "Formats",
    "Статус": "Status",
    "Введите имя профиля Bandcamp\nи нажмите «Загрузить коллекцию»":
        "Enter your Bandcamp profile name\nand click “Load collection”",
    "Ничего не выбрано": "Nothing selected",
    "Выберите позицию в списке": "Select an item in the list",
    "Журнал": "Log",
    "Подробно": "Verbose",
    "Очистить": "Clear",
    "Сохранить…": "Save…",
    " Параметры загрузки ": " Download settings ",
    "Формат:": "Format:",
    "Папка:": "Folder:",
    "Обзор…": "Browse…",
    "Потоков:": "Threads:",
    "Пропускать уже скачанное": "Skip already downloaded",
    "Распаковывать ZIP": "Extract ZIP",
    "Удалять ZIP после распаковки": "Delete ZIP after extraction",
    "Дополнительно…": "Advanced…",
    "Проверить форматы": "Check formats",
    "Открыть папку": "Open folder",
    "Скачать выбранные (0)": "Download selected (0)",
    "Cookies: не загружены": "Cookies: not loaded",
    "Скачивание купленных альбомов и треков": "Download your purchased albums and tracks",
    "Введите имя профиля Bandcamp\nи нажмите «Загрузить коллекцию»":
        "Enter your Bandcamp profile name\nand click “Load collection”",
    "Ничего не найдено.\nИзмените фильтр.": "Nothing found.\nChange the filter.",
    "Работа…": "Working…",
    "Пропущено: уже есть": "Skipped: already exists",
    "Нет доступных форматов": "No available formats",
    "В очереди": "Queued",
    "Уже есть": "Already exists",
    "Форматы: ещё не проверены": "Formats: not checked yet",
    "Форматы: недоступны": "Formats: unavailable",
    "Форматы: ": "Formats: ",
    "Ссылка скопирована": "Link copied",
    " · показано: ": " · shown: ",
    " · куплено ": " · purchased ",
    "Скачать выбранные": "Download selected",
    "Скачать выбранные (": "Download selected (",
    "Открыть на Bandcamp": "Open on Bandcamp",
    "Копировать ссылку": "Copy link",
    "Снять выбор": "Deselect",
    "Выбрать": "Select",
    "Укажите имя профиля Bandcamp и нажмите «Загрузить коллекцию».":
        "Enter your Bandcamp profile name and click “Load collection”.",
    "Сохранённый профиль: ": "Saved profile: ",
    "curl_cffi не установлен — используется requests. Bandcamp может показать антибот-проверку; рекомендуется pip install curl_cffi.":
        "curl_cffi is not installed, using requests. Bandcamp may show an anti-bot check; installing curl_cffi is recommended.",
    "browser_cookie3 не установлен: автоматическое чтение cookies недоступно, используйте «Войти…» → вставить вручную.":
        "browser_cookie3 is not installed: automatic cookie import is unavailable. Use “Sign in…” → paste manually.",
    "Pillow не установлен: обложки в панели справа не показываются.":
        "Pillow is not installed: cover art is not shown in the side panel.",
    "Версия ": "Version ",
    " · HTTP: ": " · HTTP: ",
    "нет": "none",
    "Необработанная ошибка: ": "Unhandled error: ",
    "Необработанная ошибка: {error}": "Unhandled error: {error}",
    "Журнал сохранён: ": "Log saved: ",
    "Сохранить журнал": "Save log",
    "Не удалось сохранить:\n": "Could not save:\n",
    "Папка для загрузок": "Download folder",
    "Не удалось открыть папку:\n": "Could not open the folder:\n",
    "Выбрано: 0": "Selected: 0",
    "Выбрано: {selected} из {total}": "Selected: {selected} of {total}",
    "0 из {total}": "0 of {total}",
    " · показано: {count}": " · shown: {count}",
    " · куплено {date}": " · purchased {date}",
    "Сохранённый профиль: {username}.": "Saved profile: {username}.",
    "Скачать выбранные ({count})": "Download selected ({count})",
    "Язык": "Language",
    "Язык интерфейса изменён: {language}.": "Interface language changed: {language}.",
    "Тема:": "Theme:",
    "Светлая": "Light",
    "Тёмная": "Dark",
    "Тема интерфейса изменена: {theme}.": "Interface theme changed: {theme}.",
    "Тема интерфейса: {theme} (как в системе).":
        "Interface theme: {theme} (following the system).",
    "Светлая тема": "Light theme",
    "Тёмная тема": "Dark theme",
    "Системная тема": "System theme",
    "Следовать теме системы (автоматически).":
        "Follow the system theme (automatic).",
    "Сначала завершите текущую загрузку или проверку форматов.":
        "Finish the current download or format check first.",
    "Сначала загрузите коллекцию.": "Load the collection first.",
    "Отметьте хотя бы одну позицию.": "Select at least one item.",
    "Не удалось проверить «{artist} — {title}»: {error}":
        "Could not check “{artist} — {title}”: {error}",
    "Не удалось создать окно Tkinter: {error}":
        "Could not create the Tkinter window: {error}",
    "Не удалось запустить приложение.\n\n{error}\n\nПодробности записаны в журнал ошибок.":
        "Could not start the application.\n\n{error}\n\nThe details were written to the error log.",
    "Не установлены необходимые библиотеки:\n\n  {packages}\n\nОткройте командную строку в папке программы и выполните:\n\n    pip install -r requirements.txt\n\nили:\n\n    pip install {packages}":
        "Required libraries are not installed:\n\n  {packages}\n\nOpen a command prompt in the application folder and run:\n\n    pip install -r requirements.txt\n\nor:\n\n    pip install {packages}",
    "Не удалось загрузить интерфейс приложения.\n\n{error}\n\nУбедитесь, что файлы bc_core.py, bc_ui.py, bc_actions.py, bc_dialogs.py и bc_gui.py находятся рядом с этим файлом.":
        "Could not load the application interface.\n\n{error}\n\nMake sure bc_core.py, bc_ui.py, bc_actions.py, bc_dialogs.py and bc_gui.py are next to this file.",

    # Tooltips
    "Имя профиля из адреса bandcamp.com/имя. Можно вставить ссылку целиком.":
        "Your profile name from bandcamp.com/name. You can paste the full URL.",
    "Показывать покупки, скрытые в профиле Bandcamp.":
        "Show purchases hidden from your Bandcamp profile.",
    "Откуда читать cookies Bandcamp. «Авто» пробует браузеры по очереди. Cookies хранятся только в памяти.":
        "Where to read Bandcamp cookies from. “Auto” tries browsers one by one. Cookies are kept in memory only.",
    "Фильтр по исполнителю, названию релиза или трека. Escape очищает поле.":
        "Filter by artist, release or track title. Escape clears the field.",
    "Если выбранного формата нет у конкретной покупки, будет скачан лучший доступный — предупреждение появится в журнале.":
        "If a purchase does not offer the selected format, the best available one is downloaded and a warning is written to the log.",
    "Сколько позиций скачивать одновременно (1–16). Слишком большое значение может ускорить появление HTTP 429.":
        "How many items to download at once (1–16). A large value may trigger HTTP 429 sooner.",

    # ------------------------------------------------------------------
    # Login dialog
    # ------------------------------------------------------------------
    "Вход в Bandcamp": "Sign in to Bandcamp",
    "Приложение не просит пароль. Оно читает cookies уже авторизованного браузера или принимает их вручную.":
        "The app never asks for your password. It reads cookies from a browser where you are already signed in, or accepts them manually.",
    " 1. Импорт из браузера ": " 1. Import from browser ",
    "Браузер:": "Browser:",
    "Импортировать cookies": "Import cookies",
    "Сначала войдите на bandcamp.com в браузере.":
        "First sign in to bandcamp.com in your browser.",
    " 2. Вставить cookies вручную ": " 2. Paste cookies manually ",
    "Подойдёт заголовок Cookie (name=value; name2=value2), файл cookies.txt в формате Netscape или JSON-словарь. Обязательно должна быть cookie identity.":
        "A Cookie header (name=value; name2=value2), a Netscape cookies.txt file or a JSON object works. The identity cookie is required.",
    "Из файла…": "From file…",
    "Открыть bandcamp.com": "Open bandcamp.com",
    "Проект на GitHub": "Project on GitHub",
    "Cookies хранятся только в памяти и не записываются на диск.":
        "Cookies are kept in memory only and are never written to disk.",
    "Читаю cookies из браузера…": "Reading cookies from the browser…",
    "Загружено cookies: {count} ({label}).": "Loaded {count} cookies ({label}).",
    "Cookies Bandcamp загружены из {label}: {count}.":
        "Bandcamp cookies loaded from {label}: {count}.",
    "Причина неизвестна.": "Unknown reason.",
    "Активная сессия Bandcamp не найдена.": "No active Bandcamp session found.",
    "Cookies не найдены": "Cookies not found",
    "Не удалось найти вход в Bandcamp в этом браузере.\n\n{detail}\n\nВойдите на bandcamp.com (именно в этом браузере) или вставьте cookies вручную.":
        "Could not find a Bandcamp login in this browser.\n\n{detail}\n\nSign in to bandcamp.com (in this browser) or paste cookies manually.",
    "Не удалось распознать cookies. Вставьте строку вида identity=...; session=... или файл cookies.txt.":
        "Could not recognize the cookies. Paste a line like identity=...; session=... or a cookies.txt file.",
    "Применено cookies: {count}.": "Applied {count} cookies.",
    "Cookies применены вручную: {count}.": "Cookies applied manually: {count}.",
    "Файл cookies": "Cookies file",
    "Не удалось прочитать файл:\n": "Could not read the file:\n",

    # ------------------------------------------------------------------
    # Advanced dialog
    # ------------------------------------------------------------------
    "Дополнительные параметры": "Advanced settings",
    "Эти настройки сохраняются между запусками.":
        "These settings are saved between launches.",
    "Шаблон имени:": "Filename template:",
    "Доступные поля: {artist}, {album}, {title}, {year}, {purchased}, {type}, {format}, {id}, {key}.\nСимвол / создаёт вложенные папки. Например: {artist}/{year} - {album}":
        "Available fields: {artist}, {album}, {title}, {year}, {purchased}, {type}, {format}, {id}, {key}.\nA / creates subfolders. For example: {artist}/{year} - {album}",
    "Пример пути:": "Path preview:",
    "  (+ расширение .zip / .mp3 / .flac …)": "  (+ .zip / .mp3 / .flac extension …)",
    "Прокси:": "Proxy:",
    "Необязательно. Например: http://127.0.0.1:8080 или socks5://127.0.0.1:1080. Применяется при следующем обновлении коллекции.":
        "Optional. For example: http://127.0.0.1:8080 or socks5://127.0.0.1:1080. Applied at the next collection refresh.",
    "Попыток на файл:": "Attempts per file:",
    "Пауза между попытками, с:": "Retry delay, seconds:",
    "Открывать папку после загрузки": "Open folder after download",
    "Показывать окно по завершении": "Show a summary when finished",
    "Подробный журнал (отладка)": "Verbose log (debug)",
    "Попытки и пауза должны быть числами.":
        "Attempts and retry delay must be numbers.",

    # ------------------------------------------------------------------
    # Collection / actions
    # ------------------------------------------------------------------
    "Загрузка коллекции…": "Loading collection…",
    "Загрузка коллекции… {loaded} из {total}": "Loading collection… {loaded} of {total}",
    "Загрузка коллекции… {loaded}": "Loading collection… {loaded}",
    "Ошибка загрузки коллекции": "Could not load collection",
    "Коллекция: {count} позиций": "Collection: {count} items",
    "Коллекция «{username}»: {count} позиций, доступных для скачивания.":
        "Collection “{username}”: {count} downloadable items.",
    "Все позиции отмечены. Снимите галочки с ненужных и нажмите «Скачать выбранные».":
        "All items are selected. Clear the checkboxes for unwanted items and click “Download selected”.",
    "Коллекция пуста": "Collection is empty",
    "В коллекции не найдено покупок с доступным скачиванием.":
        "No purchases with a download link were found in the collection.",
    "Нужен вход в Bandcamp": "Bandcamp sign-in required",
    "Открыть bandcamp.com в браузере?": "Open bandcamp.com in your browser?",
    "Запрошена отмена загрузки.": "Download cancellation requested.",
    "Нет выбора": "Nothing selected",
    "Отметьте хотя бы один альбом или трек.":
        "Select at least one album or track.",
    "Скачивание: 0 из {total}": "Downloading: 0 of {total}",
    "Начинаю загрузку: {count} поз., формат «{format}», потоков {threads}, папка {folder}.":
        "Starting download: {count} items, {format} format, {threads} threads, folder {folder}.",
    "Скачивание {done}%": "Downloading {done}%",
    "Скачивание {size}": "Downloading {size}",
    "{completed} из {total}": "{completed} of {total}",
    "{active} в работе": "{active} active",
    "{size}/с": "{size}/s",
    "Пропущено некорректное событие очереди: {item}":
        "Skipped an invalid queue event: {item}",
    "Загрузка отменена": "Download cancelled",
    "Загрузка завершена": "Download complete",
    "Загрузка завершена: {summary}.": "Download complete: {summary}.",
    "Скачано: {done}": "Downloaded: {done}",
    "пропущено: {count}": "skipped: {count}",
    "без формата: {count}": "no format: {count}",
    "ошибок: {count}": "errors: {count}",
    "отменено: {count}": "cancelled: {count}",
    "Скачано: {done}\nПропущено: {skipped}\nБез доступного формата: {unavailable}\nОшибок: {errors}\nОтменено: {cancelled}\nОбъём: {size}\nВремя: {elapsed}":
        "Downloaded: {done}\nSkipped: {skipped}\nNo available format: {unavailable}\nErrors: {errors}\nCancelled: {cancelled}\nSize: {size}\nTime: {elapsed}",
    "Проверка форматов: 0 из {total}": "Checking formats: 0 of {total}",
    "Проверяю доступные форматы для {count} позиций…":
        "Checking available formats for {count} items…",
    "Проверка форматов: {index} из {total}": "Checking formats: {index} of {total}",
    "Форматы проверены: {ok} из {total}": "Formats checked: {ok} of {total}",
    "Проверка форматов завершена: {ok} из {total}.":
        "Format check complete: {ok} of {total}.",
    "У {count} позиций нет выбранного формата «{format}» — будет скачан лучший доступный.":
        "{count} items do not offer the selected “{format}” format; the best available format will be downloaded.",
    "Дополнительные параметры сохранены.": "Advanced settings saved.",
    "Прокси изменён — cookies Bandcamp нужно загрузить заново.":
        "Proxy changed — Bandcamp cookies must be loaded again.",
    "Cookies загружены: {count} ({label})": "Cookies loaded: {count} ({label})",
    "Cookies Bandcamp загружены из {label}: {count}.":
        "Bandcamp cookies loaded from {label}: {count}.",
    "Профиль Bandcamp": "Bandcamp profile",
    "Укажите имя профиля — часть адреса после bandcamp.com/.\nНапример: myname или https://bandcamp.com/myname":
        "Enter your profile name — the part after bandcamp.com/.\nFor example: myname or https://bandcamp.com/myname",
    "Не удалось создать клиент:\n": "Could not create the HTTP client:\n",
    "Загружаю коллекцию профиля «{username}»{hidden} …":
        "Loading collection for “{username}”{hidden}…",
    " (включая скрытые)": " (including hidden)",
    "cookies не найдены": "cookies not found",
    "Не удалось прочитать cookies Bandcamp из браузера.\n({detail})\n\nВойдите на bandcamp.com в браузере и повторите, либо нажмите «Войти…» и вставьте cookies вручную.":
        "Could not read Bandcamp cookies from the browser.\n({detail})\n\nSign in to bandcamp.com in the browser and try again, or click “Sign in…” and paste cookies manually.",
    "Не удалось создать папку загрузки:\n": "Could not create the download folder:\n",
    "Выбрано {count} позиций. Bandcamp придётся запросить по одной странице — это может занять несколько минут.\n\nПродолжить?":
        "{count} items are selected. Bandcamp is queried one page per item, which may take several minutes.\n\nContinue?",
    "Проверка форматов": "Format check",
    "Не удалось проверить «{artist} — {title}»: {exc}":
        "Could not check “{artist} — {title}”: {exc}",
    "Не удалось открыть папку: {error}": "Could not open the folder: {error}",
    "Не удалось применить параметры клиента: {error}":
        "Could not apply the HTTP client settings: {error}",
    "Идёт скачивание. Прервать загрузку и выйти?":
        "A download is in progress. Cancel it and exit?",
    "HTTP-клиент": "HTTP client",
    "Выход": "Exit",

    # ------------------------------------------------------------------
    # Core: formats, size, errors
    # ------------------------------------------------------------------
    "Шаблон имени файла не может быть пустым.":
        "The filename template cannot be empty.",
    "Ошибка в шаблоне имени: {error}": "Filename template error: {error}",
    "Неизвестное поле «{field}» в шаблоне. Доступно: {fields}.":
        "Unknown field “{field}” in the template. Available: {fields}.",
    "Не удалось применить шаблон имени: {error}":
        "Could not apply the filename template: {error}",
    "Не установлен HTTP-клиент. Установите зависимости: pip install curl_cffi beautifulsoup4 browser_cookie3":
        "No HTTP client is installed. Install dependencies: pip install curl_cffi beautifulsoup4 browser_cookie3",
    "Сетевая ошибка: {error}": "Network error: {error}",
    "Bandcamp временно ограничил частоту запросов (HTTP 429).":
        "Bandcamp temporarily rate-limited the request (HTTP 429).",
    "Bandcamp вернул антибот-проверку. Откройте bandcamp.com в браузере, войдите в аккаунт и повторите загрузку.":
        "Bandcamp returned an anti-bot check. Open bandcamp.com in your browser, sign in and try again.",
    "Доступ запрещён (HTTP 403). Возможно, ссылка устарела или нужен вход в аккаунт.":
        "Access denied (HTTP 403). The link may be outdated or a sign-in may be required.",
    "Страница не найдена (HTTP 404).": "Page not found (HTTP 404).",
    "Ошибка сервера Bandcamp (HTTP {status}).":
        "Bandcamp server error (HTTP {status}).",
    "HTTP {status} при запросе к Bandcamp.":
        "HTTP {status} while requesting Bandcamp.",
    "{error} Повтор через {wait} с (попытка {attempt} из {attempts}).":
        "{error} Retrying in {wait} s (attempt {attempt} of {attempts}).",
    "Не удалось выполнить запрос к Bandcamp.":
        "Could not complete the request to Bandcamp.",
    "Не установлен beautifulsoup4. Выполните: pip install beautifulsoup4":
        "beautifulsoup4 is not installed. Run: pip install beautifulsoup4",
    "Bandcamp вернул антибот-проверку вместо страницы. Откройте bandcamp.com в браузере, войдите в аккаунт и повторите.":
        "Bandcamp returned an anti-bot check instead of a page. Open bandcamp.com in your browser, sign in and try again.",
    "Не удалось разобрать ответ Bandcamp. HTML сохранён в {path}.":
        "Could not parse the Bandcamp response. HTML was saved to {path}.",
    "Повреждённые данные страницы Bandcamp: {error}":
        "Corrupted Bandcamp page data: {error}",
    "Неожиданный формат данных Bandcamp.":
        "Unexpected Bandcamp data format.",
    "Не указано имя профиля Bandcamp.": "No Bandcamp profile name was provided.",
    "Открываю профиль {profile} …": "Opening profile {profile}…",
    "Профиль «{username}» не найден. Укажите имя из адреса bandcamp.com/ваше_имя.":
        "Profile “{username}” was not found. Enter the name from bandcamp.com/your_name.",
    "Нет активного входа в Bandcamp. Войдите на bandcamp.com в браузере, затем нажмите «Загрузить коллекцию» ещё раз (cookies читаются автоматически) или вставьте их через «Войти…».":
        "There is no active Bandcamp login. Sign in to bandcamp.com in your browser, then click “Load collection” again (cookies are read automatically), or paste them via “Sign in…”.",
    "другой аккаунт": "another account",
    "Вы вошли как «{who}», а указан профиль «{username}». Укажите свой профиль Bandcamp.":
        "You are signed in as “{who}”, but the profile is “{username}”. Enter your own Bandcamp profile.",
    "Пропущено покупок без доступной ссылки на скачивание: {count}.":
        "Purchases skipped because no download link was available: {count}.",
    "Bandcamp вернул неожиданный ответ при загрузке коллекции.":
        "Bandcamp returned an unexpected response while loading the collection.",
    "Не удалось получить полный список покупок. Попробуйте обновить коллекцию позже.":
        "Could not retrieve the complete purchase list. Try refreshing the collection later.",
    "Без названия": "Untitled",
    "Неизвестный исполнитель": "Unknown artist",
    "На странице скачивания нет файлов. Возможно, ссылка устарела — откройте покупку на Bandcamp и запросите новую ссылку.":
        "The download page has no files. The link may be outdated — open the purchase on Bandcamp and request a new link.",
    "Не удалось разобрать страницу скачивания.":
        "Could not parse the download page.",
    "Для этой покупки Bandcamp не предложил ни одного формата скачивания.":
        "Bandcamp did not offer any download format for this purchase.",
    "Модуль browser_cookie3 не установлен.":
        "The browser_cookie3 module is not installed.",
    "{browser}: не поддерживается": "{browser}: not supported",
    "{browser}: cookies Bandcamp не найдены":
        "{browser}: no Bandcamp cookies found",
    "{browser}: нет активной сессии Bandcamp (identity)":
        "{browser}: no active Bandcamp session (identity)",

    # Download engine
    "Получение ссылки…": "Getting download link…",
    "Скачивание…": "Downloading…",
    "Распаковка…": "Extracting…",
    "Ссылка на файл отсутствует": "File link is missing",
    "Скачано: {artist} — {title} ({size}) → {path}":
        "Downloaded: {artist} — {title} ({size}) → {path}",
    "Распаковываю {name} …": "Extracting {name}…",
    "Распаковано файлов: {count} → {target}":
        "Extracted files: {count} → {target}",
    "ZIP удалён: {name}": "ZIP deleted: {name}",
    "Не удалось удалить ZIP {path}: {error}":
        "Could not delete ZIP {path}: {error}",
    "Скачано, но не удалось распаковать: {error}":
        "Downloaded, but extraction failed: {error}",
    "Ошибка распаковки {name}: {error}":
        "Extraction error for {name}: {error}",
    "Уже есть": "Already exists",
    "{artist} — {title}: формат «{requested}» недоступен, скачиваю «{actual}».":
        "{artist} — {title}: “{requested}” format is unavailable, downloading “{actual}”.",
    "Сервер не принял докачку, начинаю заново.":
        "The server rejected the resume request; starting over.",
    "HTTP 403 — ссылка на скачивание устарела или недоступна.":
        "HTTP 403 — the download link is outdated or unavailable.",
    "HTTP 404 — файл не найден на сервере.":
        "HTTP 404 — the file was not found on the server.",
    "HTTP {status} при скачивании файла.":
        "HTTP {status} while downloading the file.",
    "Загрузка неполная: {size} из {total} байт.":
        "Incomplete download: {size} of {total} bytes.",
    "Получен пустой файл.": "The server returned an empty file.",
    "Повтор загрузки «{artist} — {title}» через {wait} с ({error}).":
        "Retrying “{artist} — {title}” in {wait} s ({error}).",
    "Не удалось скачать файл.": "Could not download the file.",
    "Отменено": "Cancelled",
}


def set_language(code: str | None) -> str:
    """Set the UI language and return the effective code."""
    global LANGUAGE
    code = (code or "").lower()
    if code not in LANGUAGES:
        code = DEFAULT_LANGUAGE
    LANGUAGE = code
    return LANGUAGE


def get_language() -> str:
    return LANGUAGE


def is_russian() -> bool:
    return LANGUAGE == "ru"


def language_label(code: str | None = None) -> str:
    return LANGUAGES.get(code or LANGUAGE, LANGUAGES[DEFAULT_LANGUAGE])


def tr(text: str, **values: Any) -> str:
    """Translate a Russian source string into the selected language."""
    if LANGUAGE == "ru" or not text:
        result = text
    else:
        result = EN.get(text, text)
    if values:
        try:
            result = result.format(**values)
        except (KeyError, IndexError, ValueError):
            pass
    return result


def detect_system_language() -> str:
    """Return the best initial language: environment, Windows UI, or locale."""
    override = os.environ.get("BCD_LANG", "").strip().lower()
    if override in LANGUAGES:
        return override
    if sys.platform == "win32":
        try:
            import ctypes

            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if (int(lang_id) & 0x3FF) == 0x19:  # LANG_RUSSIAN
                return "ru"
            return "en"
        except Exception:
            pass
    try:
        code = locale.getlocale()[0] or ""
    except Exception:
        code = ""
    return "ru" if code.lower().startswith("ru") else "en"


# Initialize immediately so core helpers (sizes, dates, errors) use the
# environment/system language even when imported outside the GUI.
LANGUAGE = detect_system_language()


def load_saved_language(settings_path: Path | str | None) -> str:
    """Read the language from settings.json, falling back to the system UI."""
    override = os.environ.get("BCD_LANG", "").strip().lower()
    if override in LANGUAGES:
        return override
    if settings_path:
        try:
            data = json.loads(Path(settings_path).read_text(encoding="utf-8"))
            code = str(data.get("language") or "").lower()
            if code in LANGUAGES:
                return code
        except Exception:
            pass
    return detect_system_language()
