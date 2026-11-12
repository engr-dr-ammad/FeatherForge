"""Independent reference-project browser checks. Runs only inside executor."""

import functools
import http.server
import threading
from playwright.sync_api import sync_playwright

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory="/project")
server = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    page = browser.new_page()
    failures = []
    page.on("pageerror", lambda e: failures.append(str(e)))
    page.goto("http://127.0.0.1:8765")
    textbox = page.get_by_role("textbox").first
    textbox.fill("Acceptance task")
    page.get_by_role("button", name="Add task", exact=True).click()
    assert page.get_by_text("Acceptance task", exact=False).count() == 1, (
        "Add task failed"
    )
    page.reload()
    assert page.get_by_text("Acceptance task", exact=False).count() == 1, (
        "Persistence failed"
    )
    checkbox = page.get_by_role("checkbox").first
    checkbox.check()
    page.reload()
    assert page.get_by_role("checkbox").first.is_checked(), (
        "Completion persistence failed"
    )
    page.get_by_role("button", name="Delete", exact=False).first.click()
    assert page.get_by_text("Acceptance task", exact=False).count() == 0, (
        "Deletion failed"
    )
    page.reload()
    assert page.get_by_text("Acceptance task", exact=False).count() == 0, (
        "Deletion persistence failed"
    )
    textbox = page.get_by_role("textbox").first
    textbox.fill("<img src=x onerror=alert(1)>")
    page.get_by_role("button", name="Add task", exact=True).click()
    assert page.locator("img").count() == 0, "User-controlled HTML injection"
    assert (
        textbox.get_attribute("aria-label")
        or textbox.get_attribute("id")
        and page.locator('label[for="' + textbox.get_attribute("id") + '"]').count()
    ), "Input lacks accessible label"
    assert not failures, failures
    browser.close()
print(
    "PASS: add, persist, complete, delete, HTML injection, accessible input, no browser exceptions"
)
server.shutdown()
