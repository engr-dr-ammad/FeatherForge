"""Live browser test; requires running FeatherForge and Docker executor."""

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8000")
    page.get_by_role("button", name="＋ New project").click()
    page.get_by_label("Project name").fill("Browser-verified reference")
    page.get_by_role("button", name="Create project", exact=True).click()
    page.get_by_role("button", name="Generate plan", exact=True).click()
    page.get_by_role("button", name="Build task-tracker web app", exact=False).click()
    page.locator("#taskTitle").fill("Build accessible task-tracker")
    page.get_by_role("button", name="Save task", exact=True).click()
    page.get_by_role("button", name="Approve plan & run", exact=True).click()
    page.wait_for_function(
        "document.querySelector('.column:last-child h3')?.textContent.includes('3')",
        timeout=120000,
    )
    page.wait_for_selector("#preview")
    frame = page.frame_locator("#preview")
    frame.get_by_role("textbox").fill("Preview task")
    frame.get_by_role("button", name="Add task", exact=True).click()
    assert frame.get_by_text("Preview task", exact=True).count() == 1
    page.screenshot(path="docs/evidence/dashboard.png", full_page=True)
    assert not errors, errors
    print(
        "PASS dashboard: create, plan, edit task, approve, completed gates, sandbox preview interaction; no JS errors"
    )
    browser.close()
