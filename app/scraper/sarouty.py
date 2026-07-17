"""
LEGACY / NOT IN THE LIVE SERVICE — Sarouty.ma stealth scraper.

Superseded by the Phase-1 pivot to a static dataset (Cloudflare blocked live scraping).
Nothing in the API, engine, or ML pipeline imports this module; it is kept only as a
reference for a future live-data pipeline. It is the sole reason `playwright` and
`playwright-stealth` appear in requirements.txt.

Do not wire this into the request path without revisiting the anti-bot/ToS constraints.
"""
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth

async def create_stealth_context(browser: Browser) -> BrowserContext:
    """
    Creates a new browser context equipped with a standard user-agent,
    realistic viewport, and strict language headers to mimic human traffic.
    """
    context: BrowserContext = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="fr-FR",
        viewport={"width": 1920, "height": 1080},
        extra_http_headers={
            "Accept-Language": "fr-FR,fr;q=0.9,ar-MA;q=0.8,en-US;q=0.7",
            "Upgrade-Insecure-Requests": "1"
        }
    )
    return context

async def fetch_sarouty_target_page(target_url: str) -> Optional[str]:
    """
    Navigates to the targeted Sarouty URL using advanced stealth evasion.
    """
    async with async_playwright() as p:
        # Changed headless to False. The browser will open visually.
        browser: Browser = await p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--start-maximized'
            ]
        )
        
        context: BrowserContext = await create_stealth_context(browser)
        page: Page = await context.new_page()
        
        # INJECT STEALTH SCRIPTS BEFORE NAVIGATION
        stealth_instance = Stealth()
        await stealth_instance.apply_stealth_async(page)
        
        print(f"Executing advanced stealth navigation to: {target_url}...")
        
        try:
            response = await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            
            if response and response.status == 200:
                page_title: str = await page.title()
                print("Connection established. WAF bypassed.")
                
                # Give it 3 seconds to let any dynamic JS finish rendering
                await asyncio.sleep(3) 
                return page_title
            else:
                status_code = response.status if response else "Unknown"
                print(f"Connection failed. HTTP Status: {status_code}")
                return None
                
        except Exception as e:
            print(f"Extraction error encountered: {e}")
            return None
            
        finally:
            await browser.close()

if __name__ == "__main__":
    test_url: str = "https://www.sarouty.ma/en/buy/properties-for-sale/casablanca/land/"
    result: Optional[str] = asyncio.run(fetch_sarouty_target_page(test_url))
    
    if result:
        print(f"Target Acquired: {result}")

