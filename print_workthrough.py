"""Print solution-workthrough.html to solution-workthrough.pdf, same shape as the shipped copy.

The shipped PDF was made by Firefox's print dialog: A4, light sheet, no headers. This reproduces it
with Playwright so the file can be regenerated without a desktop browser.

    .venv/Scripts/python.exe print_workthrough.py [browser]

`browser` is `firefox` (default) or `chromium`.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

PAGE = pathlib.Path("solution-workthrough.html").resolve()
OUTPUT = pathlib.Path("solution-workthrough.pdf").resolve()


def main(browser_name: str = "firefox") -> None:
    with sync_playwright() as play:
        browser = getattr(play, browser_name).launch()
        page = browser.new_page()
        page.goto(PAGE.as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.emulate_media(media="print")
        page.pdf(path=str(OUTPUT), format="A4", print_background=True)
        browser.close()
    print(f"{OUTPUT} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "firefox")
