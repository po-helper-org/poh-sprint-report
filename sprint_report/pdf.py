"""HTML → PDF через headless Chrome/Chromium: шрифт Inter из пакета, печать без колонтитулов.

Какой браузер: SPRINT_REPORT_CHROME или pdf.chrome в конфиге, иначе первый найденный —
chrome-headless-shell из кеша Playwright (печатает за секунды, не виснет на dbus), chromium, google-chrome.
"""
import glob
import os
import shutil
import subprocess
from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
WEIGHTS = (400, 500, 600, 700)
RANGES = {"cyrillic": "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",   # как у Google Fonts / fontsource
          "latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
                   "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"}
SHELLS = ("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell",
          "/opt/pw-browsers/chromium_headless_shell-*/*/headless_shell",
          "/opt/pw-browsers/chromium_headless_shell-*/*/chrome-headless-shell")


def fonts_css():
    """@font-face для Inter: без unicode-range латинский файл перекрыл бы кириллицу."""
    out = []
    for w in WEIGHTS:
        for subset in ("cyrillic", "latin"):
            p = FONTS / f"inter-{subset}-{w}-normal.woff2"
            if p.exists():
                out.append(f"@font-face {{ font-family: Inter; font-weight: {w}; src: url('{p.as_uri()}') format('woff2'); "
                           f"unicode-range: {RANGES[subset]}; }}")
    return "\n".join(out)


def with_fonts(page):
    return page.replace("<style>", f"<style>{fonts_css()}\n", 1)


def find_chrome(explicit=None):
    if explicit or os.environ.get("SPRINT_REPORT_CHROME"):
        return os.path.expanduser(explicit or os.environ["SPRINT_REPORT_CHROME"])
    for pattern in SHELLS:
        found = sorted(glob.glob(os.path.expanduser(pattern)))
        if found:
            return found[-1]
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        if shutil.which(name):
            return shutil.which(name)
    raise RuntimeError("не найден Chrome/Chromium для печати PDF: укажите SPRINT_REPORT_CHROME или pdf.chrome в конфиге")


def print_pdf(html_path, pdf_path, chrome, profile_dir):
    cmd = [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=5000",
           f"--user-data-dir={profile_dir}", f"--print-to-pdf={pdf_path}", Path(html_path).resolve().as_uri()]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.insert(1, "--no-sandbox")   # под root (контейнер, CI) песочница Chrome не стартует
    subprocess.run(cmd, check=True, timeout=120, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not Path(pdf_path).is_file() or not Path(pdf_path).stat().st_size:
        raise RuntimeError(f"Chrome не напечатал {pdf_path}")
