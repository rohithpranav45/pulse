"""
Render the report in headless Chromium and take section-by-section screenshots
for visual QA.
"""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent.parent
REPORT = (ROOT / "docs" / "PULSE_phase1_phase2_report.html").resolve()
OUT = ROOT / "docs" / "qa"
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    url = "file:///" + str(REPORT).replace("\\", "/")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=1.0,
        )
        page = await ctx.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(800)

        # Full page screenshot — chopped into chunks for review
        height = await page.evaluate("document.documentElement.scrollHeight")
        print(f"document height: {height} px")
        await page.screenshot(path=str(OUT / "full_page.png"), full_page=True)
        print(f"wrote {OUT / 'full_page.png'}")

        # Section-by-section
        sections = await page.query_selector_all("section, header.hero, footer")
        for i, s in enumerate(sections):
            try:
                await s.scroll_into_view_if_needed()
                box = await s.bounding_box()
                if not box:
                    continue
                out = OUT / f"section_{i:02d}.png"
                await page.screenshot(
                    path=str(out),
                    clip={"x": 0, "y": box["y"], "width": 1280, "height": min(box["height"], 1600)},
                )
                print(f"wrote {out}  ({int(box['height'])} px)")
            except Exception as e:
                print(f"section {i}: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
