"""Capture the report in 1200-px chunks to inspect tall sections."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent.parent
REPORT = (ROOT / "docs" / "PULSE_phase1_phase2_report.html").resolve()
OUT = ROOT / "docs" / "qa"


async def main():
    url = "file:///" + str(REPORT).replace("\\", "/")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(500)
        height = await page.evaluate("document.documentElement.scrollHeight")
        print(f"doc height: {height}")
        chunk = 1100
        for i, y in enumerate(range(0, height, chunk)):
            out = OUT / f"chunk_{i:02d}.png"
            await page.evaluate(f"window.scrollTo(0, {y})")
            await page.wait_for_timeout(120)
            await page.screenshot(
                path=str(out),
                clip={"x": 0, "y": 0, "width": 1280, "height": min(chunk, 900)},
            )
            print(f"  y={y:5d} -> {out}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
