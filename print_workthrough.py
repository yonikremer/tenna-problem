"""Print solution-workthrough.html to solution-workthrough.pdf, light sheet on A4.

Uses the page's own print stylesheet, so the printed copy is always the light sheet whatever theme
is on screen. Needs Playwright and its Chromium build:

    .venv/Scripts/python.exe -m pip install playwright
    .venv/Scripts/python.exe -m playwright install chromium

    .venv/Scripts/python.exe print_workthrough.py [output.pdf]

Firefox is not an option: Playwright's Firefox build cannot produce a PDF.
"""

import pathlib
import sys

from playwright.sync_api import sync_playwright

PAGE = pathlib.Path("solution-workthrough.html").resolve()
OUTPUT = pathlib.Path("solution-workthrough.pdf").resolve()


def main(output: pathlib.Path = OUTPUT) -> None:
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page()
        page.goto(PAGE.as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.emulate_media(media="print")
        page.pdf(path=str(output), format="A4", print_background=True)
        browser.close()
    print(f"{output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else OUTPUT)
