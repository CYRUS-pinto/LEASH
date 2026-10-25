import asyncio
import os
from playwright.async_api import async_playwright

KEYFRAME_TIMES = [
    (1.5, "01_hook"),
    (6.5, "02_blast_radius"),
    (15.0, "03_thesis_brake"),
    (24.0, "04_stages_gateway"),
    (42.0, "05_live_enforcement_block"),
    (60.0, "06_climax_benchmark_bars"),
    (82.0, "07_resolution_cta")
]

async def capture_critique_frames(iteration=1):
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    stage_path = f"file:///{os.path.join(base_dir, 'stage_89s.html').replace('\\', '/')}"
    out_dir = os.path.join(base_dir, "critique_frames")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Launching Playwright to capture Iteration {iteration} keyframes...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 1920x1080 viewport
        page = await browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        await page.goto(stage_path, wait_until="networkidle")
        await page.wait_for_timeout(1000)

        for t_sec, label in KEYFRAME_TIMES:
            print(f"Seeking to t={t_sec:05.2f}s [{label}]...")
            await page.evaluate(f"window.seek({t_sec});")
            await page.wait_for_timeout(100) # let DOM paint
            frame_path = os.path.join(out_dir, f"iter_{iteration}_{label}.png")
            await page.screenshot(path=frame_path)
            print(f"Saved keyframe: {frame_path}")

        await browser.close()
    print(f"Iteration {iteration} keyframes captured successfully.")

if __name__ == "__main__":
    import sys
    it = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    asyncio.run(capture_critique_frames(it))
