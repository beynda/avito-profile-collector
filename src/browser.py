from __future__ import annotations
from pathlib import Path
from typing import Optional
from playwright.sync_api import BrowserContext, sync_playwright

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

def launch_browser(user_data_dir: Path, headless: bool=False, proxy: Optional[dict]=None):
    user_data_dir.mkdir(parents=True, exist_ok=True)
    playwright = sync_playwright().start()
    launch_kwargs = dict(user_data_dir=str(user_data_dir), headless=headless, user_agent=USER_AGENT, args=['--disable-blink-features=AutomationControlled'], viewport={'width': 1366, 'height': 900}, locale='ru-RU')
    if proxy:
        launch_kwargs['proxy'] = proxy
    try:
        context: BrowserContext = playwright.chromium.launch_persistent_context(**launch_kwargs)
        # Keep the persistent context alive between short-lived collection tabs.
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        context._manual_verification_enabled = not headless
        context.new_page()
    except BaseException:
        playwright.stop()
        raise
    return (playwright, context)
