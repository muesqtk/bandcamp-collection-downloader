#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ядро Bandcamp Collection Downloader.

Здесь нет tkinter: только работа с Bandcamp, cookies, файлами и загрузкой.
GUI использует эти классы и функции.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from string import Formatter
from typing import Any, Callable, Optional

from bc_i18n import get_language, tr

# ---------------------------------------------------------------------------
# Зависимости
# ---------------------------------------------------------------------------

try:
    from bs4 import BeautifulSoup, SoupStrainer
except Exception:  # pragma: no cover
    BeautifulSoup = None
    SoupStrainer = None

try:
    from curl_cffi import requests as _curl_requests
    HTTP_BACKEND = "curl_cffi"
except Exception:  # pragma: no cover
    _curl_requests = None
    try:
        import requests as _requests_lib
        HTTP_BACKEND = "requests"
    except Exception:
        _requests_lib = None
        HTTP_BACKEND = ""

try:
    import browser_cookie3
except Exception:  # pragma: no cover
    browser_cookie3 = None


# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

APP_NAME = "Bandcamp Collection Downloader"
APP_VERSION = "1.1.1"

PROFILE_URL = "https://bandcamp.com/{username}"
COLLECTION_API = "https://bandcamp.com/api/fancollection/1/collection_items"
HIDDEN_API = "https://bandcamp.com/api/fancollection/1/hidden_items"
ART_URL = "https://f4.bcbits.com/img/a{art_id}_5.jpg"

DEFAULT_TEMPLATE = "{artist}/{album}"
MAX_PARALLEL = 16
DEFAULT_THREADS = 4

FORMAT_EXTENSIONS = {
    "aac-hi": ".m4a",
    "aiff-lossless": ".aiff",
    "alac": ".m4a",
    "flac": ".flac",
    "mp3-320": ".mp3",
    "mp3-v0": ".mp3",
    "vorbis": ".ogg",
    "wav": ".wav",
}

# От лучшего к худшему (используется для «Авто» и для запасного варианта)
FORMAT_PREFERENCE = [
    "flac",
    "alac",
    "aiff-lossless",
    "wav",
    "mp3-320",
    "aac-hi",
    "vorbis",
    "mp3-v0",
]

FORMAT_LABELS = {
    "flac": "FLAC — lossless",
    "alac": "ALAC — lossless (.m4a)",
    "aiff-lossless": "AIFF — lossless",
    "wav": "WAV — lossless",
    "mp3-320": "MP3 320 kbps",
    "aac-hi": "AAC-HI (.m4a)",
    "vorbis": "Ogg Vorbis",
    "mp3-v0": "MP3 V0 (VBR)",
}

SHORT_FORMATS = {
    "flac": "FLAC",
    "alac": "ALAC",
    "aiff-lossless": "AIFF",
    "wav": "WAV",
    "mp3-320": "MP3 320",
    "aac-hi": "AAC",
    "vorbis": "Vorbis",
    "mp3-v0": "MP3 V0",
}

FORMAT_CHOICES = [
    ("auto", "Авто (лучшее доступное)"),
    ("mp3-320", "MP3 320 kbps"),
    ("mp3-v0", "MP3 V0 (VBR)"),
    ("flac", "FLAC — lossless"),
    ("alac", "ALAC — lossless (.m4a)"),
    ("aiff-lossless", "AIFF — lossless"),
    ("wav", "WAV — lossless"),
    ("aac-hi", "AAC-HI (.m4a)"),
    ("vorbis", "Ogg Vorbis"),
]

BROWSER_CHOICES = [
    ("auto", "Авто"),
    ("chrome", "Chrome"),
    ("edge", "Edge"),
    ("firefox", "Firefox"),
    ("brave", "Brave"),
    ("chromium", "Chromium"),
    ("opera", "Opera"),
    ("vivaldi", "Vivaldi"),
    ("opera_gx", "Opera GX"),
    ("librewolf", "LibreWolf"),
]
if sys.platform == "darwin":
    BROWSER_CHOICES.append(("safari", "Safari"))


def format_choices() -> list[tuple[str, str]]:
    """Return format IDs and labels localized for the current language."""
    return [(fmt, tr(label)) for fmt, label in FORMAT_CHOICES]


def browser_choices() -> list[tuple[str, str]]:
    """Return browser IDs and labels localized for the current language."""
    return [(bid, tr(label)) for bid, label in BROWSER_CHOICES]

TEMPLATE_FIELDS = {
    "artist",
    "album",
    "title",
    "year",
    "purchased",
    "type",
    "format",
    "id",
    "key",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

INVISIBLE_CHARS_RE = re.compile(r"[\u200b-\u200d\ufeff\u200e\u200f]")
ILLEGAL_PATH_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
RESERVED_NAMES_RE = re.compile(
    r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$"
)
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ---------------------------------------------------------------------------
# Исключения
# ---------------------------------------------------------------------------

class BandcampError(RuntimeError):
    """Понятная пользователю ошибка."""


class AuthError(BandcampError):
    """Нет входа в Bandcamp / не тот аккаунт."""


class ChallengeError(BandcampError):
    """Bandcamp ответил антибот-проверкой."""


class CancelledError(Exception):
    """Пользователь отменил операцию."""


# ---------------------------------------------------------------------------
# Данные
# ---------------------------------------------------------------------------

@dataclass
class CollectionItem:
    key: str
    item_id: int
    kind: str                 # album / track / package
    artist: str
    title: str
    album_title: str
    purchased_raw: str
    item_url: str
    redownload_url: str
    art_id: Optional[int] = None
    tralbum_type: str = ""
    state: str = ""
    message: str = ""
    formats: list[str] = field(default_factory=list)
    info_loaded: bool = False
    selected: bool = True
    exists: bool = False
    final_size: int = 0

    @property
    def is_album(self) -> bool:
        return self.tralbum_type == "a" or self.kind in ("album", "package")

    @property
    def purchased_dt(self) -> Optional[Any]:
        return parse_purchased(self.purchased_raw)

    @property
    def purchased_display(self) -> str:
        d = self.purchased_dt
        if not d:
            return self.purchased_raw or "—"
        if get_language() == "ru":
            return d.strftime("%d.%m.%Y")
        return d.strftime("%Y-%m-%d")

    @property
    def year(self) -> str:
        d = self.purchased_dt
        return str(d.year) if d else ""

    @property
    def kind_label(self) -> str:
        return tr("Альбом") if self.is_album else tr("Трек")


@dataclass
class DownloadInfo:
    downloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    artist: str = ""
    title: str = ""


@dataclass
class DownloadOptions:
    fmt: str = "mp3-320"
    out_dir: Path = field(default_factory=lambda: Path("."))
    template: str = DEFAULT_TEMPLATE
    threads: int = DEFAULT_THREADS
    skip_existing: bool = True
    extract: bool = False
    delete_zip: bool = False
    attempts: int = 4
    retry_wait: float = 3.0
    proxy: Optional[str] = None


# ---------------------------------------------------------------------------
# Мелочи
# ---------------------------------------------------------------------------

def human_size(num: float) -> str:
    num = float(max(0, num))
    if get_language() == "ru":
        if num < 1024:
            return f"{int(num)} Б"
        units = ("КБ", "МБ", "ГБ", "ТБ")
        decimal_sep = ","
    else:
        if num < 1024:
            return f"{int(num)} B"
        units = ("KB", "MB", "GB", "TB")
        decimal_sep = "."
    for unit in units:
        num /= 1024.0
        if num < 1024 or unit == units[-1]:
            text = f"{num:.1f}".rstrip("0").rstrip(".")
            return f"{text.replace('.', decimal_sep)} {unit}"
    return f"{num:.1f} {units[-1]}"


def human_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if get_language() == "ru":
        if h:
            return f"{h} ч {m:02d} мин"
        if m:
            return f"{m} мин {s:02d} с"
        return f"{s} с"
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def parse_purchased(value: str) -> Optional[Any]:
    """Разбирает '16 Sep 2026 19:34:42 GMT' без зависимости от локали."""
    if not value:
        return None
    m = re.match(
        r"\s*(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+"
        r"(\d{1,2}):(\d{2}):(\d{2})",
        str(value),
    )
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    try:
        import datetime as _dt
        return _dt.datetime(
            int(m.group(3)), month, int(m.group(1)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
        )
    except ValueError:
        return None


def normalize_username(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if "bandcamp.com" in text.lower() or "/" in text or "://" in text:
        raw = text if "://" in text else "https://" + text.lstrip("/")
        parsed = urllib.parse.urlparse(raw)
        host = (parsed.hostname or "").lower()
        if host.endswith(".bandcamp.com") and host not in ("bandcamp.com", "www.bandcamp.com"):
            return host[: -len(".bandcamp.com")].strip()
        parts = [p for p in parsed.path.split("/") if p]
        if parts:
            return parts[0].strip().lstrip("@")
        return ""
    return text.lstrip("@").strip().strip("/")


def sanitize_component(value: Any) -> str:
    text = INVISIBLE_CHARS_RE.sub("", str(value))
    text = ILLEGAL_PATH_RE.sub("-", text)
    text = re.sub(r"\s+", " ", text).strip().strip(".").strip()
    if not text:
        return "_"
    text = text[:100].rstrip(" .")
    if not text:
        return "_"
    if RESERVED_NAMES_RE.match(text):
        text = "_" + text
    return text


def validate_template(template: str) -> None:
    template = (template or "").strip()
    if not template:
        raise BandcampError(tr("Шаблон имени файла не может быть пустым."))
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as exc:
        raise BandcampError(
            tr("Ошибка в шаблоне имени: {error}", error=exc)
        ) from exc
    for _, field_name, _, _ in parsed:
        if field_name is None:
            continue
        base = field_name.split(".")[0].split("[")[0]
        if base not in TEMPLATE_FIELDS:
            raise BandcampError(
                tr(
                    "Неизвестное поле «{field}» в шаблоне. Доступно: {fields}.",
                    field=field_name,
                    fields=", ".join(sorted(TEMPLATE_FIELDS)),
                )
            )


def render_template(template: str, values: dict[str, Any], out_dir: Path) -> Path:
    parts = re.split(r"[\\/]+", (template or "").strip())
    rendered: list[str] = []
    for part in parts:
        if not part:
            continue
        try:
            text = part.format(**values)
        except (KeyError, ValueError, IndexError) as exc:
            raise BandcampError(
                tr("Не удалось применить шаблон имени: {error}", error=exc)
            ) from exc
        text = text.strip()
        if text:
            rendered.append(sanitize_component(text))
    if not rendered:
        rendered = ["Untitled"]
    return Path(out_dir).joinpath(*rendered)


def build_base_path(out_dir: Path, template: str, item: CollectionItem, fmt: str) -> Path:
    values = {
        "artist": item.artist,
        "album": item.album_title or item.title,
        "title": item.title,
        "year": item.year,
        "purchased": item.purchased_display,
        "type": item.kind,
        "format": fmt,
        "id": item.item_id,
        "key": item.key,
    }
    return render_template(template, values, Path(out_dir))


def preview_template(template: str, out_dir: Path, fmt: str) -> Path:
    dummy = CollectionItem(
        key="t0", item_id=0, kind="album", artist="Artist", title="Album",
        album_title="Album", purchased_raw="", item_url="", redownload_url="",
        tralbum_type="a",
    )
    return build_base_path(out_dir, template, dummy, fmt or "mp3-320")


def format_label(fmt: str) -> str:
    return tr(FORMAT_LABELS.get(fmt, fmt))


def sort_formats(formats) -> list[str]:
    def key(value: str):
        try:
            return (0, FORMAT_PREFERENCE.index(value))
        except ValueError:
            return (1, str(value).lower())
    return sorted(formats, key=key)


def pick_format(available, requested: str) -> tuple[Optional[str], bool]:
    keys = list(available)
    if not keys:
        return None, False
    if requested and requested != "auto":
        if requested in available:
            return requested, False
        for fmt in FORMAT_PREFERENCE:
            if fmt in available:
                return fmt, True
        return keys[0], True
    for fmt in FORMAT_PREFERENCE:
        if fmt in available:
            return fmt, False
    return keys[0], False


def extension_from_disposition(value: str) -> str:
    if not value:
        return ""
    name = ""
    m = re.search(r"filename\*=UTF-8''([^;]+)", value, flags=re.I)
    if m:
        name = urllib.parse.unquote(m.group(1).strip())
    if not name:
        m = re.search(r'filename="?([^";]+)"?', value, flags=re.I)
        if m:
            name = m.group(1).strip()
    ext = os.path.splitext(name)[1].lower()
    if re.fullmatch(r"\.[a-z0-9]{1,6}", ext or ""):
        return ext
    return ""


def is_already_downloaded(
    base: Path,
    item: CollectionItem,
    fmt: str,
    any_format: bool = False,
) -> bool:
    if item.is_album:
        zip_path = Path(str(base) + ".zip")
        try:
            if zip_path.is_file() and zip_path.stat().st_size > 0:
                return True
        except OSError:
            pass
        if base.is_dir():
            try:
                next(base.iterdir())
                return True
            except (StopIteration, OSError):
                return False
        return False
    if any_format or not fmt or fmt == "auto":
        extensions = sorted(set(FORMAT_EXTENSIONS.values()))
    else:
        ext = FORMAT_EXTENSIONS.get(fmt)
        extensions = [ext] if ext else []
    for ext in extensions:
        path = Path(str(base) + ext)
        try:
            if path.is_file() and path.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False


def config_dir() -> Path:
    override = os.environ.get("BCD_CONFIG_DIR")
    if override:
        path = Path(override)
    elif sys.platform == "win32":
        path = Path(os.environ.get("APPDATA") or Path.home()) / "BandcampCollectionDownloader"
    elif sys.platform == "darwin":
        path = Path.home() / "Library" / "Application Support" / "BandcampCollectionDownloader"
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "BandcampCollectionDownloader"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def default_output_dir() -> str:
    for name in ("Music", "Музыка"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return str(candidate / "Bandcamp")
    return str(Path.home() / "Bandcamp")


def open_path(path: Path | str) -> None:
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def write_crash_log(text: str) -> None:
    try:
        with open(config_dir() / "crash.log", "a", encoding="utf-8") as fh:
            fh.write(time.strftime("\n--- %Y-%m-%d %H:%M:%S ---\n"))
            fh.write(text)
            fh.write("\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def make_http_session(proxy: Optional[str] = None):
    if _curl_requests is not None:
        kwargs: dict[str, Any] = {"impersonate": "chrome"}
        if proxy:
            kwargs["proxies"] = {"http": proxy, "https": proxy}
        session = _curl_requests.Session(**kwargs)
        session.headers.update({"Accept-Language": "en-US,en;q=0.9"})
        return session
    if _requests_lib is None:
        raise BandcampError(
            tr(
                "Не установлен HTTP-клиент. Установите зависимости: "
                "pip install curl_cffi beautifulsoup4 browser_cookie3"
            )
        )
    session = _requests_lib.Session()
    session.headers.update(DEFAULT_HEADERS)
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def fetch_image(url: str, proxy: Optional[str] = None) -> bytes:
    session = make_http_session(proxy)
    try:
        response = session.get(url, timeout=25)
        if response.status_code != 200 or not response.content:
            raise BandcampError(f"HTTP {response.status_code}")
        return response.content
    finally:
        try:
            session.close()
        except Exception:
            pass


def _looks_like_challenge(text: str) -> bool:
    low = (text or "")[:8000].lower()
    return any(
        marker in low
        for marker in ("client challenge", "_fs-ch", "just a moment", "cf-chl", "checking your browser")
    )


class HttpClient:
    """Один потокобезопасный клиент для страниц Bandcamp и метаданных."""

    def __init__(
        self,
        log: Optional[Callable[[str, str], None]] = None,
        proxy: Optional[str] = None,
        attempts: int = 4,
        retry_wait: float = 3.0,
        timeout: float = 45.0,
    ):
        self._log_cb = log
        self.proxy = proxy or None
        self.attempts = max(1, min(10, int(attempts)))
        self.retry_wait = max(0.5, min(60.0, float(retry_wait)))
        self.timeout = timeout
        self.cookie_count = 0
        self.cookie_tuples: list[tuple[str, str, str, str]] = []
        self._lock = threading.RLock()
        self._session = self._new_session()
        self._cache: dict[tuple[str, str], Any] = {}
        self._dl_cache: dict[tuple[str, Optional[int]], DownloadInfo] = {}

    # -- сессия ------------------------------------------------------------

    def _new_session(self):
        return make_http_session(self.proxy)

    def set_limits(self, attempts: int, retry_wait: float) -> None:
        self.attempts = max(1, min(10, int(attempts)))
        self.retry_wait = max(0.5, min(60.0, float(retry_wait)))

    def set_proxy(self, proxy: Optional[str]) -> None:
        proxy = proxy or None
        if proxy == self.proxy:
            return
        self.proxy = proxy
        with self._lock:
            self._session = self._new_session()
            self._cache.clear()
            self._dl_cache.clear()
            self.cookie_count = 0
            self.cookie_tuples = []

    def set_cookies(self, cookies) -> int:
        with self._lock:
            try:
                self._session.cookies.clear()
            except Exception:
                pass
            self.cookie_tuples = []
            self._cache.clear()
            self._dl_cache.clear()
            seen: set[tuple[str, str, str]] = set()
            for raw in cookies or []:
                if len(raw) == 3:
                    name, value, domain = raw
                    path = "/"
                elif len(raw) >= 4:
                    name, value, domain, path = raw[:4]
                else:
                    continue
                name = str(name or "").strip()
                if not name:
                    continue
                value = str(value if value is not None else "")
                domain = str(domain or ".bandcamp.com")
                path = str(path or "/")
                marker = (name, domain, path)
                if marker in seen:
                    continue
                seen.add(marker)
                try:
                    if domain:
                        self._session.cookies.set(name, value, domain=domain, path=path)
                    else:
                        self._session.cookies.set(name, value)
                except Exception:
                    try:
                        self._session.cookies.set(name, value)
                    except Exception:
                        continue
                self.cookie_tuples.append((name, value, domain, path))
            self.cookie_count = len(self.cookie_tuples)
            return self.cookie_count

    def apply_cookies_to_session(self, session) -> None:
        for name, value, domain, path in list(self.cookie_tuples):
            try:
                session.cookies.set(name, value, domain=domain, path=path)
            except Exception:
                try:
                    session.cookies.set(name, value)
                except Exception:
                    pass

    # -- логирование -------------------------------------------------------

    def _log(self, message: str, level: str = "debug") -> None:
        if self._log_cb is None:
            return
        try:
            self._log_cb(message, level)
        except Exception:
            pass

    # -- запросы -----------------------------------------------------------

    def request(self, method: str, url: str, *, stream: bool = False,
                retries: Optional[int] = None, timeout: Optional[float] = None,
                **kwargs):
        attempts = self.attempts if retries is None else max(1, int(retries))
        timeout = self.timeout if timeout is None else timeout
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            response = None
            try:
                with self._lock:
                    response = self._session.request(
                        method, url, timeout=timeout, stream=stream, **kwargs
                    )
                    if not stream:
                        _ = response.content
            except Exception as exc:
                last_error = BandcampError(
                    tr("Сетевая ошибка: {error}", error=exc)
                )

            if response is not None:
                status = response.status_code
                if 200 <= status < 400:
                    return response

                body = ""
                if not stream:
                    try:
                        body = response.content[:8000].decode("utf-8", "replace")
                    except Exception:
                        body = ""
                if status == 429:
                    last_error = BandcampError(
                        tr("Bandcamp временно ограничил частоту запросов (HTTP 429).")
                    )
                elif status == 403:
                    if _looks_like_challenge(body):
                        last_error = ChallengeError(
                            tr(
                                "Bandcamp вернул антибот-проверку. Откройте bandcamp.com "
                                "в браузере, войдите в аккаунт и повторите загрузку."
                            )
                        )
                    else:
                        last_error = BandcampError(
                            tr(
                                "Доступ запрещён (HTTP 403). Возможно, ссылка устарела "
                                "или нужен вход в аккаунт."
                            )
                        )
                elif status == 404:
                    last_error = BandcampError(
                        tr("Страница не найдена (HTTP 404).")
                    )
                elif status >= 500:
                    last_error = BandcampError(
                        tr(
                            "Ошибка сервера Bandcamp (HTTP {status}).",
                            status=status,
                        )
                    )
                else:
                    last_error = BandcampError(
                        tr(
                            "HTTP {status} при запросе к Bandcamp.",
                            status=status,
                        )
                    )
                try:
                    response.close()
                except Exception:
                    pass
                if status == 404:
                    break

            if attempt < attempts:
                wait = min(30.0, self.retry_wait * (2 ** (attempt - 1)))
                self._log(
                    tr(
                        "{error} Повтор через {wait} с "
                        "(попытка {attempt} из {attempts}).",
                        error=last_error,
                        wait=f"{wait:.0f}",
                        attempt=attempt + 1,
                        attempts=attempts,
                    ),
                    "debug",
                )
                _sleep(wait)

        raise last_error or BandcampError(
            tr("Не удалось выполнить запрос к Bandcamp.")
        )

    # -- страницы ----------------------------------------------------------

    def get_page_data(self, url: str) -> dict:
        cache_key = ("page", url)
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

        if BeautifulSoup is None:
            raise BandcampError(
                tr(
                    "Не установлен beautifulsoup4. Выполните: "
                    "pip install beautifulsoup4"
                )
            )

        response = self.request("GET", url)
        text = response.text
        soup = BeautifulSoup(
            text, "html.parser", parse_only=SoupStrainer("div", id="pagedata")
        )
        div = soup.find("div")
        if div is None or not div.get("data-blob"):
            dump = Path(tempfile.gettempdir()) / "bandcamp_last_page.html"
            try:
                dump.write_text(text, encoding="utf-8", errors="replace")
            except OSError:
                pass
            if _looks_like_challenge(text):
                raise ChallengeError(
                    tr(
                        "Bandcamp вернул антибот-проверку вместо страницы. "
                        "Откройте bandcamp.com в браузере, войдите в аккаунт и повторите."
                    )
                )
            raise BandcampError(
                tr(
                    "Не удалось разобрать ответ Bandcamp. "
                    "HTML сохранён в {path}.",
                    path=dump,
                )
            )
        try:
            data = json.loads(html.unescape(div.get("data-blob")))
        except Exception as exc:
            raise BandcampError(
                tr(
                    "Повреждённые данные страницы Bandcamp: {error}",
                    error=exc,
                )
            ) from exc
        if not isinstance(data, dict):
            raise BandcampError(
                tr("Неожиданный формат данных Bandcamp.")
            )
        with self._lock:
            self._cache[cache_key] = data
        return data

    # -- коллекция ---------------------------------------------------------

    def get_collection(
        self,
        username: str,
        include_hidden: bool = False,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[CollectionItem]:
        username = normalize_username(username)
        if not username:
            raise BandcampError(
                tr("Не указано имя профиля Bandcamp.")
            )

        profile = PROFILE_URL.format(username=username)
        self._log(
            tr("Открываю профиль {profile} …", profile=profile), "debug"
        )
        data = self.get_page_data(profile)

        fan = data.get("fan_data") or {}
        if not fan or "fan_id" not in fan:
            raise BandcampError(
                tr(
                    "Профиль «{username}» не найден. Укажите имя из адреса "
                    "bandcamp.com/ваше_имя.",
                    username=username,
                )
            )

        current = data.get("current_fan") or {}
        my_id = current.get("fan_id")
        if my_id is None:
            raise AuthError(
                tr(
                    "Нет активного входа в Bandcamp. Войдите на bandcamp.com "
                    "в браузере, затем нажмите «Загрузить коллекцию» ещё раз "
                    "(cookies читаются автоматически) или вставьте их через «Войти…»."
                )
            )
        fan_id = fan.get("fan_id")
        if str(my_id) != str(fan_id):
            who = current.get("username") or tr("другой аккаунт")
            raise AuthError(
                tr(
                    "Вы вошли как «{who}», а указан профиль «{username}». "
                    "Укажите свой профиль Bandcamp.",
                    who=who,
                    username=username,
                )
            )

        collection_data = data.get("collection_data") or {}
        redownload_urls = collection_data.get("redownload_urls") or {}
        item_cache = data.get("item_cache") or {}
        cached = item_cache.get("collection") or {}
        if not isinstance(cached, dict):
            cached = {}

        items_map, skipped = self._merge_items(list(cached.values()), redownload_urls)
        total = int(collection_data.get("item_count") or 0)
        if progress:
            progress(len(items_map), total or len(items_map))

        if total > len(cached):
            token = collection_data.get("last_token") or ""
            remaining = total - len(cached)
            seen_tokens = {token}
            while remaining > 0 and token:
                page = self._fetch_collection_page(
                    False, fan_id, token, remaining, profile
                )
                page_items = page.get("items") or []
                page_urls = page.get("redownload_urls") or {}
                if page_urls:
                    redownload_urls.update(page_urls)
                merged, page_skipped = self._merge_items(page_items, redownload_urls)
                items_map.update(merged)
                skipped += page_skipped
                if not page_items:
                    break
                remaining -= len(page_items)
                new_token = (
                    page.get("last_token")
                    or page.get("older_than_token")
                    or ""
                )
                if not new_token or new_token in seen_tokens:
                    break
                seen_tokens.add(new_token)
                token = new_token
                if progress:
                    progress(len(items_map), total)

        if include_hidden:
            hidden_data = data.get("hidden_data") or {}
            hidden_cache = item_cache.get("hidden") or {}
            if not isinstance(hidden_cache, dict):
                hidden_cache = {}
            merged, hidden_skipped = self._merge_items(
                list(hidden_cache.values()), redownload_urls
            )
            items_map.update(merged)
            skipped += hidden_skipped
            hidden_total = int(hidden_data.get("item_count") or 0)
            if hidden_total > len(hidden_cache):
                token = hidden_data.get("last_token") or ""
                remaining = hidden_total - len(hidden_cache)
                seen_tokens = {token}
                while remaining > 0 and token:
                    page = self._fetch_collection_page(
                        True, fan_id, token, remaining, profile
                    )
                    page_items = page.get("items") or []
                    page_urls = page.get("redownload_urls") or {}
                    if page_urls:
                        redownload_urls.update(page_urls)
                    merged, page_skipped = self._merge_items(
                        page_items, redownload_urls
                    )
                    items_map.update(merged)
                    skipped += page_skipped
                    if not page_items:
                        break
                    remaining -= len(page_items)
                    new_token = (
                        page.get("last_token")
                        or page.get("older_than_token")
                        or ""
                    )
                    if not new_token or new_token in seen_tokens:
                        break
                    seen_tokens.add(new_token)
                    token = new_token

        if progress:
            progress(len(items_map), max(total, len(items_map)))
        if skipped:
            self._log(
                tr(
                    "Пропущено покупок без доступной ссылки на скачивание: {count}.",
                    count=skipped,
                ),
                "warn",
            )
        return list(items_map.values())

    def _fetch_collection_page(self, hidden: bool, fan_id, token: str,
                               count: int, profile: str) -> dict:
        url = HIDDEN_API if hidden else COLLECTION_API
        payload = {
            "fan_id": fan_id,
            "count": max(1, int(count)),
            "older_than_token": token,
        }
        response = self.request(
            "POST", url, json=payload, headers={"Referer": profile}
        )
        try:
            data = response.json()
        except Exception as exc:
            raise BandcampError(
                tr("Bandcamp вернул неожиданный ответ при загрузке коллекции.")
            ) from exc
        if not isinstance(data, dict) or data.get("error"):
            raise BandcampError(
                tr(
                    "Не удалось получить полный список покупок. "
                    "Попробуйте обновить коллекцию позже."
                )
            )
        return data

    def _merge_items(self, raw_items, urls: dict) -> tuple[dict[str, CollectionItem], int]:
        results: dict[str, CollectionItem] = {}
        skipped = 0
        for raw in raw_items or []:
            if not isinstance(raw, dict):
                skipped += 1
                continue
            sale_type = raw.get("sale_item_type")
            sale_id = raw.get("sale_item_id")
            if sale_type is None or sale_id is None:
                skipped += 1
                continue
            key = f"{sale_type}{sale_id}"
            url = urls.get(key)
            if isinstance(url, dict):
                url = url.get("url")
            if not url:
                skipped += 1
                continue
            if str(url).startswith("/"):
                url = "https://bandcamp.com" + str(url)

            item_type = raw.get("item_type") or ""
            tralbum_type = raw.get("tralbum_type") or ""
            if not tralbum_type:
                tralbum_type = "a" if item_type == "album" else "t"
            if not item_type:
                item_type = "album" if tralbum_type == "a" else "track"

            item_id = raw.get("item_id") or raw.get("tralbum_id") or 0
            try:
                item_id = int(item_id)
            except Exception:
                item_id = 0
            art_id = raw.get("item_art_id") or raw.get("art_id")
            try:
                art_id = int(art_id) if art_id else None
            except Exception:
                art_id = None
            title = str(raw.get("item_title") or tr("Без названия"))
            artist = str(raw.get("band_name") or tr("Неизвестный исполнитель"))
            album_title = str(raw.get("album_title") or title)

            results[key] = CollectionItem(
                key=key,
                item_id=item_id,
                kind=str(item_type),
                artist=artist,
                title=title,
                album_title=album_title,
                purchased_raw=str(raw.get("purchased") or ""),
                item_url=str(raw.get("item_url") or ""),
                redownload_url=str(url),
                art_id=art_id,
                tralbum_type=str(tralbum_type),
            )
        return results, skipped

    # -- страница скачивания ----------------------------------------------

    def get_download_info(
        self, redownload_url: str, item_id: Optional[int] = None
    ) -> DownloadInfo:
        cache_key = (redownload_url, item_id)
        with self._lock:
            cached = self._dl_cache.get(cache_key)
        if cached is not None:
            return cached

        data = self.get_page_data(redownload_url)
        download_items = data.get("download_items") or []
        if not isinstance(download_items, list) or not download_items:
            raise BandcampError(
                tr(
                    "На странице скачивания нет файлов. Возможно, ссылка устарела — "
                    "откройте покупку на Bandcamp и запросите новую ссылку."
                )
            )

        chosen = download_items[0]
        if item_id is not None:
            for candidate in download_items:
                if not isinstance(candidate, dict):
                    continue
                ids = {
                    str(candidate.get("item_id") or ""),
                    str(candidate.get("tralbum_id") or ""),
                }
                if str(item_id) in ids:
                    chosen = candidate
                    break
        if not isinstance(chosen, dict):
            raise BandcampError(
                tr("Не удалось разобрать страницу скачивания.")
            )

        raw_downloads = chosen.get("downloads") or {}
        downloads: dict[str, dict[str, Any]] = {}
        for fmt, value in raw_downloads.items():
            url = ""
            size = None
            if isinstance(value, str):
                url = value
            elif isinstance(value, dict):
                url = value.get("url") or value.get("download_url") or ""
                size = value.get("size_mb") or value.get("size")
            if not url:
                continue
            if str(url).startswith("/"):
                url = "https://bandcamp.com" + str(url)
            if isinstance(size, str):
                try:
                    size = float(size)
                except ValueError:
                    size = None
            downloads[str(fmt)] = {"url": str(url), "size_mb": size}

        if not downloads:
            raise BandcampError(
                tr(
                    "Для этой покупки Bandcamp не предложил ни одного формата скачивания."
                )
            )

        info = DownloadInfo(
            downloads=downloads,
            artist=str(chosen.get("artist") or ""),
            title=str(chosen.get("title") or ""),
        )
        with self._lock:
            self._dl_cache[cache_key] = info
        return info


# ---------------------------------------------------------------------------
# Cookies из браузера / из текста
# ---------------------------------------------------------------------------

def _browser_cookie3_chromium_compat() -> None:
    """Chrome 130+ добавляет к значению cookie хеш домена, а старый
    browser_cookie3 падает на недекодируемых байтах. Учим его сохранять
    такие значения: хеш потом снимается в import_browser_cookies().
    """
    if browser_cookie3 is None or sys.platform != "win32":
        return
    cls = getattr(browser_cookie3, "ChromiumBased", None)
    if cls is None or getattr(cls, "_bcd_utf8_compat", False):
        return
    try:
        AES = browser_cookie3.AES
        CookieError = browser_cookie3.BrowserCookieError
        unprotect = browser_cookie3._crypt_unprotect_data
    except Exception:  # pragma: no cover - другая версия библиотеки
        return

    def decode_bytes(data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", "surrogateescape")

    def decrypt_windows(value, encrypted_value):
        if len(value) != 0:
            return value
        if encrypted_value == b"":
            return ""
        _, data = unprotect(encrypted_value)
        if isinstance(data, bytes):
            return decode_bytes(data)
        return str(data)

    def decrypt(self, value, encrypted_value):
        if sys.platform != "win32":
            return _original_decrypt(self, value, encrypted_value)
        try:
            return decrypt_windows(value, encrypted_value)
        except RuntimeError:
            if not self.v10_key:
                raise RuntimeError(
                    "Failed to decrypt the cipher text with DPAPI and no AES key."
                )
            encrypted_value = encrypted_value[3:]
            nonce, tag = encrypted_value[:12], encrypted_value[-16:]
            aes = AES.new(self.v10_key, AES.MODE_GCM, nonce=nonce)
            try:
                data = aes.decrypt_and_verify(encrypted_value[12:-16], tag)
            except ValueError:
                raise CookieError("Unable to get key for cookie decryption")
            return decode_bytes(data)

    _original_decrypt = cls._decrypt
    cls._decrypt_windows_chromium = staticmethod(decrypt_windows)
    cls._decrypt = decrypt
    cls._bcd_utf8_compat = True


def _clean_chromium_cookie_value(value: str, domain: str) -> str:
    """Убирает SHA-256(host_key), который Chromium 130+ кладёт в начало
    расшифрованного значения cookie."""
    if not value or not domain:
        return value
    try:
        raw = value.encode("utf-8", "surrogateescape")
        prefix = hashlib.sha256(domain.encode("utf-8")).digest()
    except (UnicodeError, ValueError):
        return value
    if len(raw) > 32 and raw[:32] == prefix:
        raw = raw[32:]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", "replace")
    return value


CHROMIUM_BROWSERS = {
    "edge", "chrome", "chromium", "brave", "opera", "vivaldi", "opera_gx",
}


def import_browser_cookies(browser_id: str = "auto"):
    """
    Возвращает (cookies, использованный_браузер, список_ошибок).
    cookies: список (name, value, domain, path).
    Ищем только профили, где есть cookie identity (вход в Bandcamp).
    """
    if browser_cookie3 is None:
        return [], "", [tr("Модуль browser_cookie3 не установлен.")]

    _browser_cookie3_chromium_compat()

    if sys.platform == "darwin":
        order = ["safari", "chrome", "firefox", "brave", "chromium", "edge",
                 "opera", "vivaldi", "librewolf"]
    else:
        order = ["edge", "chrome", "firefox", "brave", "chromium", "opera",
                 "vivaldi", "opera_gx", "librewolf"]

    if browser_id and browser_id != "auto":
        candidates = [browser_id]
    else:
        candidates = order

    errors: list[str] = []
    for bid in candidates:
        func = getattr(browser_cookie3, bid, None)
        if func is None:
            errors.append(tr("{browser}: не поддерживается", browser=bid))
            continue
        try:
            jar = func(domain_name="bandcamp.com")
            cookies: list[tuple[str, str, str, str]] = []
            for cookie in jar:
                name = str(getattr(cookie, "name", "") or "").strip()
                if not name:
                    continue
                value = str(getattr(cookie, "value", "") or "")
                domain = str(getattr(cookie, "domain", "") or ".bandcamp.com")
                if bid in CHROMIUM_BROWSERS:
                    value = _clean_chromium_cookie_value(value, domain)
                cookies.append((
                    name,
                    value,
                    domain,
                    str(getattr(cookie, "path", "") or "/"),
                ))
            if not cookies:
                errors.append(
                    tr("{browser}: cookies Bandcamp не найдены", browser=bid)
                )
                continue
            has_identity = any(
                name == "identity" and value for name, value, _, _ in cookies
            )
            if not has_identity:
                errors.append(
                    tr(
                        "{browser}: нет активной сессии Bandcamp (identity)",
                        browser=bid,
                    )
                )
                continue
            return cookies, bid, errors
        except Exception as exc:
            errors.append(f"{bid}: {type(exc).__name__}: {exc}")

    return [], "", errors


def parse_cookie_text(text: str) -> list[tuple[str, str, str, str]]:
    """Понимает Netscape cookies.txt, заголовок Cookie и JSON-словарь."""
    text = (text or "").strip()
    if not text:
        return []
    pairs: list[tuple[str, str, str, str]] = []

    if text.startswith("{"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                for name, value in obj.items():
                    if isinstance(name, str) and name.strip():
                        pairs.append((
                            name.strip(), str(value),
                            ".bandcamp.com", "/",
                        ))
                if pairs:
                    return pairs
        except Exception:
            pass

    if text.lower().startswith("# netscape") or "\t" in text:
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain = parts[0].strip() or ".bandcamp.com"
                path = parts[2].strip() or "/"
                name = parts[5].strip()
                value = parts[6].strip()
                if name:
                    pairs.append((name, value, domain, path))
        if pairs:
            return pairs

    cleaned = re.sub(r"^\s*cookie\s*:\s*", "", text, flags=re.I)
    for chunk in re.split(r";\s*|\r?\n", cleaned):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"')
        if name and value:
            pairs.append((name, value, ".bandcamp.com", "/"))
    return pairs


# ---------------------------------------------------------------------------
# ZIP
# ---------------------------------------------------------------------------

def _zip_member_name(info: zipfile.ZipInfo) -> str:
    name = info.filename.replace("\\", "/")
    if not (info.flag_bits & 0x800):
        for encoding in ("utf-8", "cp1251", "cp1252"):
            try:
                candidate = name.encode("cp437").decode(encoding)
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if candidate:
                return candidate
    return name


def _common_root(names: list[str]) -> Optional[str]:
    roots: set[str] = set()
    for name in names:
        parts = PurePosixPath(name).parts
        if len(parts) < 2:
            return None
        roots.add(parts[0])
        if len(roots) > 1:
            return None
    return next(iter(roots)) if len(roots) == 1 else None


def safe_extract_zip(
    zip_path: Path,
    target_dir: Path,
    cancel: Optional[threading.Event] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> int:
    """Распаковка с защитой от zip-slip и снос общей корневой папки."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_resolved = target_dir.resolve()

    with zipfile.ZipFile(zip_path, "r") as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        names = [_zip_member_name(i) for i in infos]
        safe_names = [
            name for name in names
            if name and ".." not in PurePosixPath(name).parts
        ]
        root = _common_root(safe_names)
        total = len(safe_names)
        extracted = 0

        for info in infos:
            if cancel is not None and cancel.is_set():
                raise CancelledError()
            name = _zip_member_name(info)
            if root and name.startswith(root + "/"):
                name = name[len(root) + 1:]
            name = name.lstrip("/")
            if not name:
                continue
            parts = [p for p in PurePosixPath(name).parts if p not in ("", ".")]
            if not parts or any(p == ".." for p in parts):
                continue
            destination = target_dir.joinpath(*parts)
            try:
                resolved = destination.resolve()
            except OSError:
                continue
            if not str(resolved).lower().startswith(str(target_resolved).lower()):
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, open(destination, "wb") as out:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise CancelledError()
                    chunk = source.read(262144)
                    if not chunk:
                        break
                    out.write(chunk)
            extracted += 1
            if progress:
                progress(extracted, total)
    return extracted


# ---------------------------------------------------------------------------
# Загрузка
# ---------------------------------------------------------------------------

def _sleep(seconds: float, cancel: Optional[threading.Event] = None) -> None:
    end = time.monotonic() + max(0.0, seconds)
    while True:
        if cancel is not None and cancel.is_set():
            raise CancelledError()
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


class DownloadJob:
    """Параллельно скачивает выбранные позиции и шлёт события в GUI."""

    def __init__(
        self,
        client: HttpClient,
        items: list[CollectionItem],
        options: DownloadOptions,
        emit: Callable[[str, Any], None],
    ):
        self.client = client
        self.items = list(items)
        self.options = options
        self.emit = emit
        self.total = len(self.items)
        self.started_at = time.time()
        self._cancel = threading.Event()
        self._used_bases: set[str] = set()
        self._lock = threading.RLock()
        self._tls = threading.local()
        self._last_progress: dict[str, float] = {}
        self._thread: Optional[threading.Thread] = None

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    # -- вспомогательное ---------------------------------------------------

    def _log(self, message: str, level: str = "info") -> None:
        self.emit("log", (level, message))

    def _state(self, item: CollectionItem, state: str, message: str = "",
               size: Optional[int] = None,
               formats: Optional[list[str]] = None) -> None:
        payload: dict[str, Any] = {
            "key": item.key,
            "state": state,
            "message": message,
        }
        if size is not None:
            payload["size"] = int(size)
        if formats is not None:
            payload["formats"] = list(formats)
        self.emit("item_status", payload)

    def _progress(self, item: CollectionItem, done: int, total: int) -> None:
        now = time.monotonic()
        if done != total and now - self._last_progress.get(item.key, 0) < 0.2:
            return
        self._last_progress[item.key] = now
        self.emit(
            "item_progress",
            {"key": item.key, "done": int(done), "total": int(total)},
        )

    def _session(self):
        session = getattr(self._tls, "session", None)
        if session is None:
            session = make_http_session(self.options.proxy)
            try:
                self.client.apply_cookies_to_session(session)
            except Exception:
                pass
            self._tls.session = session
        return session

    def _unique_base(self, base: Path, key: str) -> Path:
        with self._lock:
            candidate = base
            counter = 2
            while str(candidate).casefold() in self._used_bases:
                suffix = f" [{key}]" if counter == 2 else f" [{key}-{counter}]"
                candidate = base.with_name(base.name + suffix)
                counter += 1
            self._used_bases.add(str(candidate).casefold())
            return candidate

    # -- основной цикл -----------------------------------------------------

    def _run(self) -> None:
        self.emit("job_started", {"total": self.total})
        try:
            workers = max(1, min(MAX_PARALLEL, int(self.options.threads)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(self._one, item): item for item in self.items
                }
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        future.result()
                    except CancelledError:
                        self._state(item, "cancelled", tr("Отменено"))
                    except Exception as exc:  # страховка
                        self._state(item, "error", str(exc)[:300])
                        self._log(
                            f"{item.artist} — {item.title}: {exc}", "error"
                        )
        finally:
            self.emit(
                "job_finished",
                {
                    "cancelled": self.cancelled,
                    "elapsed": time.time() - self.started_at,
                },
            )

    def _one(self, item: CollectionItem) -> None:
        if self.cancelled:
            self._state(item, "cancelled", tr("Отменено"))
            return

        try:
            requested = self.options.fmt

            # Быстрая проверка без запроса к Bandcamp, если формат задан явно.
            if self.options.skip_existing and requested != "auto":
                base = build_base_path(
                    self.options.out_dir, self.options.template, item, requested
                )
                if is_already_downloaded(base, item, requested):
                    self._state(item, "skipped", tr("Уже есть"))
                    return

            self._state(item, "working", tr("Получение ссылки…"))
            info = self.client.get_download_info(item.redownload_url, item.item_id)
            formats = sort_formats(info.downloads.keys())

            fmt, fallback = pick_format(info.downloads, requested)
            if not fmt:
                self._state(item, "unavailable", tr("Нет доступных форматов"),
                            formats=formats)
                return
            if fallback:
                self._log(
                    tr(
                        "{artist} — {title}: формат "
                        "«{requested}» недоступен, скачиваю "
                        "«{actual}».",
                        artist=item.artist,
                        title=item.title,
                        requested=format_label(requested),
                        actual=format_label(fmt),
                    ),
                    "warn",
                )

            base = self._unique_base(
                build_base_path(
                    self.options.out_dir, self.options.template, item, fmt
                ),
                item.key,
            )
            if self.options.skip_existing and is_already_downloaded(base, item, fmt):
                self._state(item, "skipped", tr("Уже есть"), formats=formats)
                return

            extension = ".zip" if item.is_album else FORMAT_EXTENSIONS.get(fmt, "")
            if not extension:
                extension = ""
            destination = Path(str(base) + extension)
            destination.parent.mkdir(parents=True, exist_ok=True)

            download = info.downloads.get(fmt) or {}
            url = download.get("url") or ""
            if not url:
                self._state(item, "unavailable", tr("Ссылка на файл отсутствует"),
                            formats=formats)
                return

            self._state(item, "working", tr("Скачивание…"), formats=formats)
            final_path, size = self._download_file(item, url, destination)
            item_done_message = human_size(size)
            self._state(item, "done", item_done_message, size=size,
                        formats=formats)
            self._log(
                tr(
                    "Скачано: {artist} — {title} "
                    "({size}) → {path}",
                    artist=item.artist,
                    title=item.title,
                    size=human_size(size),
                    path=final_path,
                ),
                "ok",
            )

            if self.options.extract and final_path.suffix.lower() == ".zip":
                self._state(item, "working", tr("Распаковка…"), formats=formats)
                target = Path(str(final_path)[:-4])
                self._log(tr("Распаковываю {name} …", name=final_path.name))
                try:
                    count = safe_extract_zip(
                        final_path, target, self._cancel,
                        progress=lambda done, total: self._progress(
                            item, done, total
                        ),
                    )
                    self._log(
                        tr(
                            "Распаковано файлов: {count} → {target}",
                            count=count,
                            target=target,
                        ),
                        "ok",
                    )
                    if self.options.delete_zip:
                        try:
                            final_path.unlink()
                            self._log(
                                tr(
                                    "ZIP удалён: {name}",
                                    name=final_path.name,
                                ),
                                "debug",
                            )
                        except OSError as exc:
                            self._log(
                                tr(
                                    "Не удалось удалить ZIP {path}: {error}",
                                    path=final_path,
                                    error=exc,
                                ),
                                "warn",
                            )
                    self._state(item, "done", item_done_message, size=size,
                                formats=formats)
                except CancelledError:
                    raise
                except Exception as exc:
                    self._state(
                        item, "error",
                        tr(
                            "Скачано, но не удалось распаковать: {error}",
                            error=exc,
                        ),
                        size=size, formats=formats,
                    )
                    self._log(
                        tr(
                            "Ошибка распаковки {name}: {error}",
                            name=final_path.name,
                            error=exc,
                        ),
                        "error",
                    )

        except CancelledError:
            self._state(item, "cancelled", tr("Отменено"))
        except Exception as exc:
            message = str(exc) or type(exc).__name__
            self._state(item, "error", message[:300])
            self._log(f"{item.artist} — {item.title}: {message}", "error")

    # -- файл --------------------------------------------------------------

    def _download_file(self, item: CollectionItem, url: str, destination: Path):
        part = Path(str(destination) + ".part")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not self.options.skip_existing and destination.exists():
            try:
                part.unlink()
            except OSError:
                pass

        session = self._session()
        attempts = max(1, min(10, int(self.options.attempts)))
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            if self.cancelled:
                raise CancelledError()
            offset = part.stat().st_size if part.is_file() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            response = None
            try:
                response = session.get(
                    url, headers=headers, stream=True, timeout=(20, 300)
                )
                status = response.status_code

                if status == 416 and offset:
                    try:
                        part.unlink()
                    except OSError:
                        pass
                    raise BandcampError(
                        tr("Сервер не принял докачку, начинаю заново.")
                    )

                if status not in (200, 206):
                    if status == 403:
                        raise BandcampError(
                            tr(
                                "HTTP 403 — ссылка на скачивание устарела или недоступна."
                            )
                        )
                    if status == 404:
                        raise BandcampError(
                            tr("HTTP 404 — файл не найден на сервере.")
                        )
                    raise BandcampError(
                        tr(
                            "HTTP {status} при скачивании файла.",
                            status=status,
                        )
                    )

                disposition = response.headers.get("content-disposition") or ""
                disp_ext = extension_from_disposition(disposition)
                length_header = response.headers.get("content-length") or ""
                content_length = (
                    int(length_header) if length_header.isdigit() else 0
                )

                if status == 200 and offset:
                    # Сервер проигнорировал Range — перезаписываем.
                    offset = 0
                    mode = "wb"
                    total = content_length
                else:
                    mode = "ab" if offset else "wb"
                    content_range = response.headers.get("content-range") or ""
                    if content_range and "/" in content_range:
                        tail = content_range.rsplit("/", 1)[1]
                        total = int(tail) if tail.isdigit() else offset + content_length
                    else:
                        total = offset + content_length

                done = offset
                self._progress(item, done, total)
                with open(part, mode) as out:
                    for chunk in response.iter_content(262144):
                        if self.cancelled:
                            raise CancelledError()
                        if not chunk:
                            continue
                        out.write(chunk)
                        done += len(chunk)
                        self._progress(item, done, total)

                size = part.stat().st_size
                if total and size != total:
                    raise BandcampError(
                        tr(
                            "Загрузка неполная: {size} из {total} байт.",
                            size=size,
                            total=total,
                        )
                    )
                if size <= 0:
                    raise BandcampError(tr("Получен пустой файл."))

                new_destination = destination
                if disp_ext and disp_ext.lower() != destination.suffix.lower():
                    new_destination = destination.with_suffix(disp_ext)
                os.replace(part, new_destination)
                return new_destination, size

            except CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    wait = max(0.5, float(self.options.retry_wait)) * attempt
                    self._log(
                        tr(
                            "Повтор загрузки «{artist} — {title}» "
                            "через {wait} с ({error}).",
                            artist=item.artist,
                            title=item.title,
                            wait=f"{wait:.0f}",
                            error=exc,
                        ),
                        "warn",
                    )
                    try:
                        _sleep(wait, self._cancel)
                    except CancelledError:
                        raise
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

        raise BandcampError(
            str(last_error) if last_error else tr("Не удалось скачать файл.")
        )
