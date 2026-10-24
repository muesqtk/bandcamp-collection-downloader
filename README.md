# Bandcamp Collection Downloader (GUI)

A bilingual (English / Russian) desktop app for Windows, macOS and Linux that
downloads **your own Bandcamp purchases**: albums and individual tracks in the
format you choose.

The app does not search for pirated links, bypass payments or remove DRM. It
opens the official Bandcamp re-download pages (`/download?payment_id=…`) that
are available only to the owner of a purchase, and saves the files Bandcamp
itself offers.

## Project lineage and attribution

This graphical application is based on the original
[`bandcamp-downloader`](https://github.com/easlice/bandcamp-downloader) by
Andrew Slice (2022), distributed under the MIT License.

This GUI is part of the
[my fork](https://github.com/muesqtk/bandcamp-collection-downloader).

The legacy command-line script `bandcamp-downloader.py` has been **removed from
this GUI distribution**. The original command-line tool is still available in
the upstream repository. The GUI uses its own core (`bc_core.py`) and keeps the
same legal scope: only content you purchased on Bandcamp.

## Features

* Load a complete Bandcamp collection or include hidden purchases.
* Search by artist/title, filter albums/tracks, and show missing items only.
* Select individual items, select all / clear all, toggle with the space bar.
* Preview panel with cover art, title, purchase date and available formats.
* Formats: **FLAC, ALAC, AIFF, WAV, MP3 320, MP3 V0, AAC-HI, Ogg Vorbis**,
  plus **Auto** (best available lossless first).
* Parallel downloads (1–16 threads), per-item and overall progress, speed and
  elapsed/remaining statistics.
* Resume interrupted downloads (`.part` + HTTP `Range`) and verify file size.
* Retries with backoff for network errors, HTTP 429 and 5xx responses.
* Skip already downloaded files and continue interrupted jobs.
* Safe ZIP extraction with `zip-slip` protection; optional ZIP deletion after
  successful extraction.
* Path templates such as `{artist}/{album}` and other fields.
* HTTP/HTTPS/SOCKS proxy, configurable retry count and delay.
* Log panel with a verbose mode and log export.
* Completion notification, open-folder action, and persistent settings.
* Cookies are read from a browser or pasted manually; they are **kept in memory
  only and never written to disk**.
* Instant English/Russian interface switching from the title bar.

## Requirements

### Portable executable

The release build is a single Windows executable and does **not** require
Python. See [Building the Windows executable](#building-the-windows-executable)
to create it locally.

### Running from source

* Python **3.10+** (3.11–3.14 recommended).
* Tkinter, included in the standard Windows Python installer.
* Internet access and a Bandcamp account that owns the purchased content.

Check Python:

```bat
python --version
```

If the command is not found, install Python from python.org and enable
“Add Python to PATH” and the “tcl/tk and IDLE” component.

## Installation from source

Open a command prompt in the project folder:

```bat
pip install -r requirements.txt
```

Or run `install.bat`.

Main libraries:

| Package | Purpose |
|---|---|
| `curl_cffi` | Browser-like TLS fingerprint for reliable Bandcamp requests |
| `requests` | Fallback HTTP client |
| `beautifulsoup4` | Parsing Bandcamp pages |
| `browser_cookie3` | Reading the Bandcamp login from browsers |
| `Pillow` | Cover art in the preview panel |

Without `curl_cffi` the app falls back to `requests`, but Bandcamp is more
likely to show a “Client Challenge” or HTTP 429.

## Running from source

* `run.bat` — start without a console window.
* `run_console.bat` — start with a console and error messages (useful for
  troubleshooting).
* Manually:

```bat
python bandcamp_gui.py
```

Command-line options:

```bat
python bandcamp_gui.py --version
```

## Interface language

The app is fully translated into English and Russian.

* Click the language selector in the top-right corner to switch instantly. It
  is disabled while a download or format check is running.
* On first launch the language is detected from the Windows UI language. Other
  systems fall back to English.
* The choice is stored in `settings.json`.
* Set the environment variable `BCD_LANG=en` or `BCD_LANG=ru` to force a
  language for a launch.
* The complete English and Russian Help text (including attribution, license and
  usage instructions) is available from the **Help** button.

## Signing in to Bandcamp

1. Sign in to [bandcamp.com](https://bandcamp.com/) in a browser (Chrome, Edge,
   Firefox, Brave, Opera, etc.).
2. In the app's top bar, choose the browser under **Cookies from**. “Auto”
   tries browsers one by one.
3. Enter your profile name: the part of the address after `bandcamp.com/`.
   For example, for `https://bandcamp.com/user` enter `user`.
4. Click **Load collection**.

If automatic cookie import does not work:

* click **Sign in…** → **Import cookies** for the selected browser;
* or paste cookies manually and click **Apply**. Supported formats:
  * a `Cookie: name=value; …` header;
  * a Netscape `cookies.txt` file;
  * a JSON object `{"name": "value", …}`;
  * the **From file…** button.

An `identity` cookie (an active Bandcamp session) is required. Cookies are kept
only in RAM and never written to settings or logs.

## Downloading

1. Load the collection.
2. Clear the checkboxes of unwanted items (the `✓` column), or use search and
   filters, then **Select all** / **Clear all**.
3. Choose a **format**, a destination **folder** and the number of **threads**.
4. If needed, open **Advanced…**: filename template, proxy, retry count/delay,
   notifications and verbose logging.
5. Click **Download selected**.

During a download the **Cancel** button stops the job; current files remain as
`.part` files and can be resumed on the next run.

Useful actions:

* **Space** — toggle the selection of highlighted rows.
* **Double-click** — open the purchase on Bandcamp.
* **Right-click** — context menu: download, check formats, open page, copy
  link, select/deselect.
* **Check formats** — preview which formats Bandcamp offers for the selected
  items (one request per item; Bandcamp may rate-limit).

## Formats

Bandcamp returns albums as ZIP archives and individual tracks as audio files.

* The selected format is requested for every purchase.
* If the format is unavailable, the best available one is downloaded and a
  warning is written to the log.
* **Auto** prefers lossless: FLAC → ALAC → AIFF → WAV → MP3 320 → AAC → Vorbis
  → MP3 V0.
* Extensions `.zip`, `.flac`, `.mp3`, `.m4a`, `.aiff`, `.wav`, `.ogg` are
  detected automatically; if the server sends `Content-Disposition`, it is used
  to refine the extension.

## Filename template

Default: `{artist}/{album}`.

Available fields:

| Field | Value |
|---|---|
| `{artist}` | artist |
| `{album}` | album title (for a track: track title) |
| `{title}` | item title |
| `{year}` | purchase year |
| `{purchased}` | purchase date (`YYYY-MM-DD` in English, `DD.MM.YYYY` in Russian) |
| `{type}` | `album` or `track` |
| `{format}` | format identifier (`flac`, `mp3-320`, …) |
| `{id}` | internal Bandcamp purchase ID |
| `{key}` | collection item key |

A `/` creates subfolders. Characters invalid on Windows are replaced with `-`,
and reserved names (`CON`, `NUL`, …) are escaped. Example:
`{artist}/{year} - {album}`.

## Settings and files

Settings are stored in:

* Windows: `%APPDATA%\BandcampCollectionDownloader\settings.json`
* macOS: `~/Library/Application Support/BandcampCollectionDownloader/`
* Linux: `~/.config/BandcampCollectionDownloader/`

`crash.log` is written there on an unhandled error.

Set `BCD_CONFIG_DIR` to use a different settings directory (useful for tests and
portable setups).

Settings contain only UI/download preferences: profile, format, folder,
template, threads, proxy, language and checkboxes. **Cookies are never stored.**

## Building the Windows executable

The build produces a **single portable `.exe`** with Python, Tkinter, Pillow,
curl_cffi and all runtime dependencies bundled. The target computer does not
need Python installed.

```bat
build.bat
```

Or manually:

```bat
pip install -r requirements.txt -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name BandcampCollectionDownloader ^
  --icon assets\app.ico ^
  --version-file version_info.txt ^
  --hidden-import PIL._tkinter_finder ^
  --collect-all curl_cffi ^
  --collect-all browser_cookie3 ^
  --collect-data certifi ^
  --workpath build --distpath dist ^
  bandcamp_gui.py
```

Output:

```text
dist\BandcampCollectionDownloader.exe
```

The first launch of a one-file build may take a few seconds while PyInstaller
unpacks the bundled runtime. Settings still live in `%APPDATA%`, so the EXE
itself remains portable.

## Troubleshooting

**“There is no active Bandcamp login”**  
Sign in to bandcamp.com in a browser, choose that browser in the app and click
Load collection again. Or paste cookies manually via **Sign in…**.

**“Bandcamp returned an anti-bot check” / “Client Challenge”**  
Install `curl_cffi` (`pip install curl_cffi`), open bandcamp.com in a browser,
make sure you are signed in, and retry. Another network or proxy may help.

**HTTP 429**  
Bandcamp is rate-limiting requests. Reduce threads to 2–4, increase the retry
delay in **Advanced…**, and retry later. The app already retries with backoff.

**“Profile not found”**  
Use the part of the address after `bandcamp.com/`, without spaces. A full URL is
also accepted and parsed automatically.

**“You are signed in as … but the profile is …”**  
Use your own profile name. A collection is only accessible to its owner.

**A file is incomplete**  
Leave the `.part` file in place and run again with “Skip already downloaded”
enabled; the download resumes from the interruption point. Increasing the retry
count also helps.

**Cover art is missing**  
Install Pillow: `pip install Pillow`.

**The window is too large/small**  
The app enables Windows DPI awareness. If scaling is still uncomfortable,
adjust the display scale in Windows settings.

## Project structure

```text
bandcamp_gui.py          entry point, dependency checks, --version
bc_gui.py                App assembly and main loop
bc_ui.py                 interface, table, settings, log
bc_actions.py            network actions, cookies, downloads, events
bc_core.py               HTTP, collection, formats, ZIP, DownloadJob
bc_dialogs.py            sign-in, advanced settings, Help and license
bc_i18n.py               Russian source strings and English translation
bc_localize.py           static widget-tree localization helper
requirements.txt         runtime dependencies
requirements-build.txt   PyInstaller build dependency
build.bat                one-file Windows build script
assets/app.ico           application icon
version_info.txt         Windows version resource
LICENSE                  MIT license and attribution
```

## Legal notice

* Download only content you purchased on Bandcamp.
* Do not redistribute the downloaded files: they are for personal use under
  Bandcamp's and rights holders' terms.
* The app does not bypass payment, DRM or access restrictions. It only
  automates the official re-download of your purchases.

## License

MIT License. Copyright (c) 2022 Andrew Slice; fork modifications and GUI
copyright (c) 2026 muesqtk. See [LICENSE](LICENSE). The same notice and full
license text are included in the in-app Help.

Русская документация: [README.ru.md](README.ru.md).
