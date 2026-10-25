import asyncio
import time
import os
from playwright.async_api import async_playwright

async def benchmark():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    stage_path = f"file:///{os.path.join(base_dir, 'stage_89s.html').replace('\\', '/')}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(stage_path, wait_until="networkidle")
        
        t0 = time.time()
        frames = 60
        for i in range(frames):
            await page.evaluate(f"window.seek({i / 60.0});")
            data = await page.screenshot(type="jpeg", quality=90)
        dur = time.time() - t0
        fps = frames / dur
        print(f"Captured {frames} frames in {dur:.2f}s ({fps:.1f} fps)")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(benchmark())
