import asyncio
import os
from playwright.async_api import async_playwright

KEYFRAMES_210 = [
    (10.0, "act1_governance_gap"),
    (35.0, "act2_thesis_brake"),
    (60.0, "act3_8_stages_pipeline"),
    (95.0, "act4_live_attack_block"),
    (125.0, "act5_cryptographic_audit_dag"),
    (152.0, "act6_policy_as_code_yaml"),
    (175.0, "act7_pytest_23_tests"),
    (200.0, "act8_empirical_climax_cta")
]

async def capture_210_critique():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    stage_path = f"file:///{os.path.join(base_dir, 'stage_210s.html').replace('\\', '/')}"
    out_dir = os.path.join(base_dir, "critique_frames", "walkthrough_210")
    os.makedirs(out_dir, exist_ok=True)

    print("Capturing 210s Technical Walkthrough keyframes...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(stage_path, wait_until="networkidle")
        await page.wait_for_timeout(600)

        for t_sec, label in KEYFRAMES_210:
            await page.evaluate(f"window.seek({t_sec});")
            await page.wait_for_timeout(100)
            frame_path = os.path.join(out_dir, f"{label}.png")
            await page.screenshot(path=frame_path)
            print(f"Captured: {label} (t={t_sec}s)", flush=True)

        await browser.close()
    print("All 210s walkthrough keyframes captured.", flush=True)

if __name__ == "__main__":
    asyncio.run(capture_210_critique())
