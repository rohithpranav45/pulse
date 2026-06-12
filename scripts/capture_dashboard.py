"""
Headless screenshots of the running PULSE dashboard for the Phase 1+2 report.

Pre-req: Flask running at http://127.0.0.1:5000 + playwright installed.

Output: docs/screenshots/*.png
"""
from __future__ import annotations
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:5000"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1600, "height": 1000},
            device_scale_factor=1.5,
        )
        page = await ctx.new_page()
        page.on("console", lambda msg: None)
        page.on("pageerror", lambda err: None)

        print(f"-> {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        await page.evaluate(
            "localStorage.setItem('pulse.onboarding.seen.v2', '1');"
            "localStorage.setItem('pulse.view', '\"signal\"');"
        )
        await page.reload(wait_until="networkidle", timeout=60_000)
        await page.wait_for_timeout(7_000)

        async def scroll_main(y: int) -> None:
            await page.evaluate(f"document.querySelector('main').scrollTo(0, {y})")
            await page.wait_for_timeout(500)

        async def shot(key: str, label: str) -> None:
            out = OUT / f"{key}.png"
            await page.screenshot(path=str(out), full_page=False)
            print(f"   {label} -> {out}  ({out.stat().st_size // 1024} KB)")

        # ── 1. Signal tab — hero ──────────────────────────────────────────
        await page.keyboard.press("1")
        await page.wait_for_timeout(4500)
        await scroll_main(0)
        await shot("01_signal", "Signal tab")

        # ── 2. Charts tab — OHLCV with EXTRA WAIT for candles to settle ──
        await page.keyboard.press("2")
        await page.wait_for_timeout(8000)
        await scroll_main(0)
        await page.wait_for_timeout(2000)
        await shot("02_charts", "Charts — OHLCV + forward curve")

        # ── 2b. Forward curve panel (zoomed in via scroll) ───────────────
        await scroll_main(520)
        await page.wait_for_timeout(1000)
        await shot("02b_forward_curve", "Charts — forward curve + evolution")

        # ── 2c. Seasonality strip — clean centered shot ──────────────────
        # Need the seasonality 5-card strip centered with breathing room above/below.
        # Layout-wise this sits right above the first row of crack spreads.
        await scroll_main(1100)
        await page.wait_for_timeout(800)
        await shot("02c_seasonality", "Charts — seasonality strip")

        # ── 2d. All 4 crack spread charts visible in ONE tall screenshot ─
        # Use a taller viewport for this single capture so all 4 charts (2 rows of 2)
        # fit cleanly without cropping the bottom row.
        await page.set_viewport_size({"width": 1600, "height": 1400})
        await page.wait_for_timeout(400)
        await scroll_main(1500)
        await page.wait_for_timeout(1000)
        await shot("02d_cracks_4", "Charts — 4 crack spreads in one")
        # Restore standard viewport
        await page.set_viewport_size({"width": 1600, "height": 1000})
        await page.wait_for_timeout(400)

        # ── 3. Fundamentals tab ──────────────────────────────────────────
        await page.keyboard.press("3")
        await page.wait_for_timeout(3500)
        await scroll_main(0)
        await shot("03_fundamentals", "Fundamentals")

        # ── 4. Intelligence tab ──────────────────────────────────────────
        await page.keyboard.press("4")
        await page.wait_for_timeout(3500)
        await scroll_main(0)
        await shot("04_intelligence", "Intelligence")

        # ── 5. Spreads tab ───────────────────────────────────────────────
        await page.keyboard.press("5")
        await page.wait_for_timeout(3500)
        await scroll_main(0)
        await shot("05_spreads", "Spreads")

        # ── 6. Paper trading ─────────────────────────────────────────────
        await page.keyboard.press("7")
        await page.wait_for_timeout(4500)
        await scroll_main(0)
        await shot("06_paper", "Paper trading")

        # ── 7. Regime tab — Phase 2 hero ─────────────────────────────────
        await page.keyboard.press("8")
        await page.wait_for_timeout(5000)
        await scroll_main(0)
        await shot("07_regime", "Regime — Phase 2 hero")

        # ── Ask PULSE chat dock ──────────────────────────────────────────
        print("   -> Ask PULSE chat dock")
        await page.keyboard.press("1")
        await page.wait_for_timeout(2500)
        await scroll_main(0)
        try:
            buttons = await page.query_selector_all("button")
            for b in buttons:
                txt = (await b.inner_text()).strip().lower()
                if "ask pulse" in txt:
                    await b.click()
                    break
            await page.wait_for_timeout(1500)
            inp = await page.query_selector("textarea, input[type='text']")
            if inp:
                await inp.fill("What's driving Brent today?")
                await page.wait_for_timeout(500)
                for b in await page.query_selector_all("button"):
                    txt = (await b.inner_text()).strip().lower()
                    if txt in {"ask", "send", "submit"} or "submit" in txt:
                        await b.click()
                        break
                await page.wait_for_timeout(8000)
            await shot("10_ask_pulse", "Ask PULSE chat")
        except Exception as e:
            print(f"   skipped chat: {e}")

        # ── Regime drill modal ───────────────────────────────────────────
        print("   -> Regime drill modal")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        await page.keyboard.press("8")
        await page.wait_for_timeout(5000)
        try:
            for b in await page.query_selector_all("button"):
                txt = (await b.inner_text()).strip().lower()
                if "evidence" in txt:
                    await b.click()
                    await page.wait_for_timeout(2500)
                    await shot("09_regime_drill", "Regime drill modal")
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                    break
        except Exception as e:
            print(f"   skipped drill: {e}")

        # ── News squawk close-up ─────────────────────────────────────────
        print("   -> News squawk close-up")
        await page.keyboard.press("1")
        await page.wait_for_timeout(3500)
        await scroll_main(0)
        try:
            out = OUT / "11_squawk.png"
            await page.screenshot(
                path=str(out),
                clip={"x": 800, "y": 0, "width": 800, "height": 380},
            )
            print(f"   squawk -> {out}")
        except Exception as e:
            print(f"   skipped squawk: {e}")

        await browser.close()
        print("done.")


if __name__ == "__main__":
    asyncio.run(main())
