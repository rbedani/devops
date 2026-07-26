#!/usr/bin/env python3
"""Inspect opencode.ai design system — colors, fonts, animations, layout."""
import asyncio, json, sys
from playwright.async_api import async_playwright

OUTPUT = "/home/opc/devops/reports/opencode-design.json"

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("https://opencode.ai/es", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)  # let JS render + animations settle

        # -- Extract CSS custom properties ---------------------------------
        css_vars = await page.evaluate("""() => {
            const style = getComputedStyle(document.documentElement);
            const vars = {};
            for (let i = 0; i < style.length; i++) {
                const prop = style[i];
                if (prop.startsWith('--')) {
                    vars[prop] = style.getPropertyValue(prop).trim();
                }
            }
            return vars;
        }""")

        # -- Extract computed styles from key elements ---------------------
        selectors = [
            "body", "h1", "h2", "p", "a", "button",
            "nav", "header", "footer", "main",
            "[class*=hero]", "[class*=btn]", "[class*=button]",
            "[class*=card]", "[class*=container]",
            "[class*=gradient]", "[class*=glow]", "[class*=neon]",
            "[class*=progress]", "[class*=bar]",
            "[class*=input]", "[class*=search]",
        ]
        element_styles = {}
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    tag = await el.evaluate("el => el.tagName.toLowerCase()")
                    classes = await el.evaluate("el => el.className")
                    styles = await el.evaluate("""el => {
                        const s = getComputedStyle(el);
                        return {
                            bg: s.backgroundColor,
                            color: s.color,
                            font: s.fontFamily,
                            size: s.fontSize,
                            weight: s.fontWeight,
                            border: s.border,
                            radius: s.borderRadius,
                            shadow: s.boxShadow,
                            transform: s.transform,
                            transition: s.transition,
                            animation: s.animationName,
                            display: s.display,
                            padding: s.padding,
                            margin: s.margin,
                            gap: s.gap,
                            letterSpacing: s.letterSpacing,
                            textTransform: s.textTransform,
                            textShadow: s.textShadow,
                        };
                    }""")
                    element_styles[sel] = {"tag": tag, "classes": classes, "styles": styles}
            except Exception:
                pass

        # -- Extract key colors from palette -------------------------------
        all_colors = {}
        for key, val in css_vars.items():
            if any(c in val for c in ["#", "rgb", "hsl"]):
                all_colors[key] = val

        # -- Detect animations ---------------------------------------------
        animations = await page.evaluate("""() => {
            const sheets = document.styleSheets;
            const anims = {};
            for (const sheet of sheets) {
                try {
                    for (const rule of sheet.cssRules || []) {
                        if (rule.type === 7) { // KEYFRAMES_RULE
                            const frames = [];
                            for (const r of rule.cssRules) {
                                frames.push(r.keyText + " {" + r.cssText + "}");
                            }
                            anims[rule.name] = frames;
                        }
                    }
                } catch(e) {}
            }
            return anims;
        }""")

        # -- Screenshot ----------------------------------------------------
        await page.screenshot(path="/home/opc/devops/reports/opencode-home.png", full_page=True)

        # -- Wait for animations to detect neon/glow -----------------------
        neon_elements = await page.evaluate("""() => {
            const all = document.querySelectorAll('*');
            const neon = [];
            for (const el of all) {
                const s = getComputedStyle(el);
                if (s.boxShadow && s.boxShadow !== 'none' && s.boxShadow.includes('rgb')) {
                    neon.push({
                        tag: el.tagName,
                        class: el.className.slice(0, 80),
                        shadow: s.boxShadow.slice(0, 120),
                        color: s.color,
                        bg: s.backgroundColor,
                    });
                }
            }
            return neon.slice(0, 20);
        }""")

        await browser.close()

        # -- Build report --------------------------------------------------
        report = {
            "url": "https://opencode.ai/es",
            "css_vars": css_vars,
            "colors_detected": all_colors,
            "element_styles": element_styles,
            "animations": animations,
            "neon_glow_elements": neon_elements,
            "counts": {
                "css_vars": len(css_vars),
                "colors": len(all_colors),
                "elements": len(element_styles),
                "animations": len(animations),
                "neon": len(neon_elements),
            }
        }

        with open(OUTPUT, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"[OK] Design report saved to {OUTPUT}")
        print(f"     CSS vars: {len(css_vars)}")
        print(f"     Colors: {len(all_colors)}")
        print(f"     Animations: {len(animations)}")
        print(f"     Neon/glow elements: {len(neon_elements)}")
        print(f"     Screenshot: reports/opencode-home.png")

if __name__ == "__main__":
    asyncio.run(main())