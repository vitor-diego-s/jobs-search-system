#!/usr/bin/env python3
"""Diagnose LinkedIn description panel — discover the Requirements section selector.

LinkedIn's "Requirements added by the job poster" section is a sibling of
#job-details, not inside it.  This script clicks job cards and inspects the
DOM to find the exact selector for that sibling section.

Self-contained: no src/ imports (follows extract_cookies.py pattern).

Usage:
    .venv/bin/python scripts/diagnose_description.py
"""

import asyncio
import json
import random
import textwrap
from pathlib import Path

from patchright.async_api import async_playwright

# ── Constants ──────────────────────────────────────────────────────────

COOKIES_PATH = Path("config/linkedin_cookies.json")

# Known listings confirmed to have "Requirements added by the job poster" section
# with visa restrictions (from DB candidates analysis).
TARGET_JOBS = [
    {"external_id": "4379980427", "label": "Staff ML Engineer, Storm3"},
    {"external_id": "4378121014", "label": "Senior Python Dev, SwissPine Tech"},
]
# Direct view gives a full-page layout; search-panel gives the side-panel layout.
# We test BOTH to see where the requirements section lives in each.
JOB_VIEW_URL = "https://www.linkedin.com/jobs/view/{external_id}/"
# Search URL that loads the side panel for a specific job (currentJobId param)
SEARCH_PANEL_URL = (
    "https://www.linkedin.com/jobs/search/"
    "?currentJobId={external_id}&geoId=92000000&f_AL=true&f_WT=2"
)
CARD_SELECTORS = (
    "li[data-occludable-job-id]",
    "li.jobs-search-results__list-item",
    "li.scaffold-layout__list-item",
)
DESCRIPTION_PANEL_SELECTORS = (
    "#job-details",
    "div.jobs-description__content",
    "div.jobs-description-content__text",
    "article.jobs-description__container",
    ".jobs-box__html-content",
)
VISA_PHRASES = [
    "visa sponsorship",
    "work authorization",
    "authorized to work",
    "right to work",
    "work permit",
    "legally authorized",
    "eligible to work",
]

# ── Helpers ────────────────────────────────────────────────────────────


def _load_cookies() -> list[dict]:
    if not COOKIES_PATH.exists():
        print(f"WARNING: Cookie file not found: {COOKIES_PATH}")
        return []
    data = json.loads(COOKIES_PATH.read_text())
    return data if isinstance(data, list) else []


def _contains_visa(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in VISA_PHRASES)


def _preview(text: str, length: int = 200) -> str:
    text = " ".join(text.split())
    return textwrap.shorten(text, width=length, placeholder="...")


# ── JS payloads ────────────────────────────────────────────────────────

JS_MAP_PARENT_STRUCTURE = """
() => {
    const jd = document.querySelector('#job-details');
    if (!jd) return {error: 'no #job-details'};

    // Walk up 3 levels
    let ancestor = jd;
    for (let i = 0; i < 3; i++) {
        if (ancestor.parentElement) ancestor = ancestor.parentElement;
    }

    const children = Array.from(ancestor.children).map(el => ({
        tag: el.tagName.toLowerCase(),
        class: el.className || '',
        id: el.id || '',
        textLength: (el.textContent || '').length,
        textPreview: (el.textContent || '').substring(0, 200).trim(),
    }));

    return {
        ancestorTag: ancestor.tagName.toLowerCase(),
        ancestorClass: ancestor.className || '',
        ancestorId: ancestor.id || '',
        childCount: children.length,
        children: children,
    };
}
"""

JS_FIND_REQUIREMENTS_TEXT = """
() => {
    const results = [];
    const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    let node;
    while (node = walker.nextNode()) {
        const text = node.textContent.trim();
        if (text.toLowerCase().includes('requirement')) {
            const parent = node.parentElement;
            results.push({
                text: text.substring(0, 300),
                parentTag: parent ? parent.tagName.toLowerCase() : null,
                parentClass: parent ? (parent.className || '') : '',
                parentId: parent ? (parent.id || '') : '',
                isInsideJobDetails: parent ? !!parent.closest('#job-details') : false,
            });
        }
    }
    return results;
}
"""

JS_ENUMERATE_SIBLINGS = """
() => {
    const jd = document.querySelector('#job-details');
    if (!jd) return {error: 'no #job-details'};
    const parent = jd.parentElement;
    if (!parent) return {error: 'no parent of #job-details'};

    const siblings = Array.from(parent.children)
        .filter(el => el !== jd)
        .map(el => {
            const text = (el.textContent || '');
            const lower = text.toLowerCase();
            const visaPhrases = %s;
            return {
                tag: el.tagName.toLowerCase(),
                class: el.className || '',
                id: el.id || '',
                textLength: text.length,
                textPreview: text.substring(0, 200).trim(),
                containsVisa: visaPhrases.some(p => lower.includes(p)),
                containsRequirements: lower.includes('requirement'),
            };
        });

    return {
        parentTag: parent.tagName.toLowerCase(),
        parentClass: parent.className || '',
        parentId: parent.id || '',
        siblingCount: siblings.length,
        siblings: siblings,
    };
}
""" % json.dumps(VISA_PHRASES)

JS_TEST_SELECTORS = """
(selectors) => {
    const visaPhrases = %s;
    return selectors.map(sel => {
        const el = document.querySelector(sel);
        if (!el) return {selector: sel, found: false, textLength: 0, containsVisa: false};
        const text = (el.textContent || '');
        const lower = text.toLowerCase();
        return {
            selector: sel,
            found: true,
            textLength: text.length,
            containsVisa: visaPhrases.some(p => lower.includes(p)),
        };
    });
}
""" % json.dumps(VISA_PHRASES)

JS_VISA_ANCESTRY = """
() => {
    const visaPhrases = """ + json.dumps(VISA_PHRASES) + """;
    const results = [];
    const walker = document.createTreeWalker(
        document.body, NodeFilter.SHOW_TEXT, null, false
    );
    let node;
    while (node = walker.nextNode()) {
        const text = node.textContent.trim().toLowerCase();
        for (const phrase of visaPhrases) {
            if (text.includes(phrase)) {
                // Walk up the ancestor chain and record each level
                const chain = [];
                let el = node.parentElement;
                for (let i = 0; i < 10 && el && el !== document.body; i++) {
                    chain.push({
                        tag: el.tagName.toLowerCase(),
                        id: el.id || '',
                        class: el.className || '',
                        textLength: (el.textContent || '').length,
                    });
                    el = el.parentElement;
                }
                results.push({
                    phrase: phrase,
                    text: node.textContent.trim().substring(0, 200),
                    ancestorChain: chain,
                });
                break;
            }
        }
    }
    return results;
}
"""

JS_REQ_SECTION_ANCESTRY = """
() => {
    // Find the "Requirements added by the job poster" text and map its section
    const walker = document.createTreeWalker(
        document.body, NodeFilter.SHOW_TEXT, null, false
    );
    let node;
    while (node = walker.nextNode()) {
        if (node.textContent.trim().includes('Requirements added by the job poster')) {
            // Found it — walk up to find a meaningful container
            const chain = [];
            let el = node.parentElement;
            for (let i = 0; i < 15 && el && el !== document.body; i++) {
                const sibCount = el.parentElement ? el.parentElement.children.length : 0;
                chain.push({
                    level: i,
                    tag: el.tagName.toLowerCase(),
                    id: el.id || '',
                    class: el.className || '',
                    textLength: (el.textContent || '').length,
                    siblingCount: sibCount,
                });
                el = el.parentElement;
            }
            // Also get the full text of the section container (first element with >200 chars)
            let sectionEl = node.parentElement;
            while (sectionEl && (sectionEl.textContent || '').length < 200 && sectionEl.parentElement) {
                sectionEl = sectionEl.parentElement;
            }
            return {
                found: true,
                ancestorChain: chain,
                sectionTag: sectionEl ? sectionEl.tagName.toLowerCase() : null,
                sectionClass: sectionEl ? (sectionEl.className || '') : '',
                sectionId: sectionEl ? (sectionEl.id || '') : '',
                sectionTextLength: sectionEl ? (sectionEl.textContent || '').length : 0,
                sectionPreview: sectionEl ? (sectionEl.textContent || '').substring(0, 500).trim() : '',
            };
        }
    }
    return {found: false};
}
"""


# ── Main ───────────────────────────────────────────────────────────────


async def _analyze_page(page, idx: int, label: str) -> dict:
    """Run all 4 DOM analyses on the current page and print results."""
    print(f"\n{'='*70}")
    print(f"JOB {idx}: {label}")
    print(f"{'='*70}")

    # Wait for description panel to load
    try:
        await page.wait_for_selector("#job-details", timeout=8000)
    except Exception:
        print("  WARNING: #job-details not found within 8s, proceeding anyway...")
    await page.wait_for_timeout(1500)

    # (a) Map parent structure
    print("\n  [a] Parent structure of #job-details:")
    parent_info = await page.evaluate(JS_MAP_PARENT_STRUCTURE)
    if "error" in parent_info:
        print(f"      ERROR: {parent_info['error']}")
    else:
        anc = parent_info
        print(f"      Ancestor (3 levels up): <{anc['ancestorTag']} "
              f"id='{anc['ancestorId']}' class='{anc['ancestorClass'][:80]}'>")
        print(f"      Children of ancestor: {anc['childCount']}")
        for ci, child in enumerate(anc["children"]):
            label_str = f"<{child['tag']}"
            if child["id"]:
                label_str += f" id='{child['id']}'"
            if child["class"]:
                label_str += f" class='{child['class'][:60]}'"
            label_str += ">"
            print(f"        [{ci}] {label_str}  len={child['textLength']}")
            if child["textPreview"]:
                print(f"             preview: {_preview(child['textPreview'], 120)}")

    # (b) Find "Requirements" text nodes
    print("\n  [b] Text nodes containing 'Requirement':")
    req_nodes = await page.evaluate(JS_FIND_REQUIREMENTS_TEXT)
    if not req_nodes:
        print("      (none found)")
    for rn in req_nodes:
        inside = "INSIDE" if rn["isInsideJobDetails"] else "OUTSIDE"
        print(f"      [{inside}] <{rn['parentTag']}"
              f" id='{rn['parentId']}'"
              f" class='{rn['parentClass'][:60]}'>"
              f"\n               text: {_preview(rn['text'], 120)}")

    # (b2) Also search for visa phrases directly
    print("\n  [b2] Text nodes containing visa phrases:")
    visa_nodes = await page.evaluate("""
    () => {
        const visaPhrases = """ + json.dumps(VISA_PHRASES) + """;
        const results = [];
        const walker = document.createTreeWalker(
            document.body, NodeFilter.SHOW_TEXT, null, false
        );
        let node;
        while (node = walker.nextNode()) {
            const text = node.textContent.trim().toLowerCase();
            for (const phrase of visaPhrases) {
                if (text.includes(phrase)) {
                    const parent = node.parentElement;
                    results.push({
                        phrase: phrase,
                        text: node.textContent.trim().substring(0, 300),
                        parentTag: parent ? parent.tagName.toLowerCase() : null,
                        parentClass: parent ? (parent.className || '') : '',
                        parentId: parent ? (parent.id || '') : '',
                        isInsideJobDetails: parent ? !!parent.closest('#job-details') : false,
                    });
                    break;
                }
            }
        }
        return results;
    }
    """)
    if not visa_nodes:
        print("      (none found)")
    for vn in visa_nodes:
        inside = "INSIDE" if vn["isInsideJobDetails"] else "OUTSIDE"
        print(f"      [{inside}] phrase='{vn['phrase']}'"
              f" <{vn['parentTag']}"
              f" id='{vn['parentId']}'"
              f" class='{vn['parentClass'][:60]}'>"
              f"\n               text: {_preview(vn['text'], 150)}")

    # (c) Enumerate #job-details siblings
    print("\n  [c] Siblings of #job-details:")
    sib_info = await page.evaluate(JS_ENUMERATE_SIBLINGS)
    if "error" in sib_info:
        print(f"      ERROR: {sib_info['error']}")
    else:
        print(f"      Parent: <{sib_info['parentTag']}"
              f" id='{sib_info['parentId']}'"
              f" class='{sib_info['parentClass'][:80]}'>")
        print(f"      Sibling count: {sib_info['siblingCount']}")
        for si, sib in enumerate(sib_info["siblings"]):
            flags = []
            if sib["containsVisa"]:
                flags.append("VISA")
            if sib["containsRequirements"]:
                flags.append("REQUIREMENTS")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            sib_label = f"<{sib['tag']}"
            if sib["id"]:
                sib_label += f" id='{sib['id']}'"
            if sib["class"]:
                sib_label += f" class='{sib['class'][:60]}'"
            sib_label += ">"
            print(f"        [{si}] {sib_label}  len={sib['textLength']}{flag_str}")
            if sib["textPreview"]:
                print(f"             preview: {_preview(sib['textPreview'], 120)}")

    # (c2) Also walk up further — check grandparent and great-grandparent siblings
    print("\n  [c2] Extended ancestor walk (up to 5 levels from #job-details):")
    extended = await page.evaluate("""
    () => {
        const jd = document.querySelector('#job-details');
        if (!jd) return {error: 'no #job-details'};
        const visaPhrases = """ + json.dumps(VISA_PHRASES) + """;
        const levels = [];
        let current = jd;
        for (let lvl = 1; lvl <= 5; lvl++) {
            const parent = current.parentElement;
            if (!parent) break;
            const siblings = Array.from(parent.children)
                .filter(el => el !== current)
                .map(el => {
                    const text = (el.textContent || '');
                    const lower = text.toLowerCase();
                    return {
                        tag: el.tagName.toLowerCase(),
                        class: el.className || '',
                        id: el.id || '',
                        textLength: text.length,
                        textPreview: text.substring(0, 300).trim(),
                        containsVisa: visaPhrases.some(p => lower.includes(p)),
                        containsRequirements: lower.includes('requirement'),
                    };
                })
                .filter(s => s.textLength > 20);
            levels.push({
                level: lvl,
                parentTag: parent.tagName.toLowerCase(),
                parentClass: parent.className || '',
                parentId: parent.id || '',
                significantSiblings: siblings,
            });
            current = parent;
        }
        return {levels};
    }
    """)
    if "error" in extended:
        print(f"      ERROR: {extended['error']}")
    else:
        for lvl_info in extended["levels"]:
            interesting = [s for s in lvl_info["significantSiblings"]
                          if s["containsVisa"] or s["containsRequirements"] or s["textLength"] > 50]
            if not interesting:
                continue
            print(f"      Level {lvl_info['level']} — parent: <{lvl_info['parentTag']}"
                  f" id='{lvl_info['parentId']}'"
                  f" class='{lvl_info['parentClass'][:60]}'>")
            for sib in interesting:
                flags = []
                if sib["containsVisa"]:
                    flags.append("VISA")
                if sib["containsRequirements"]:
                    flags.append("REQUIREMENTS")
                flag_str = f" [{', '.join(flags)}]" if flags else ""
                sib_label = f"<{sib['tag']}"
                if sib["id"]:
                    sib_label += f" id='{sib['id']}'"
                if sib["class"]:
                    sib_label += f" class='{sib['class'][:60]}'"
                sib_label += ">"
                print(f"          {sib_label}  len={sib['textLength']}{flag_str}")
                if sib["textPreview"]:
                    print(f"               preview: {_preview(sib['textPreview'], 150)}")

    # (d) Test DESCRIPTION_PANEL_SELECTORS
    print("\n  [d] Existing selector coverage:")
    sel_results = await page.evaluate(
        JS_TEST_SELECTORS, list(DESCRIPTION_PANEL_SELECTORS)
    )
    for sr in sel_results:
        status = "FOUND" if sr["found"] else "MISS "
        visa = " [HAS VISA PHRASE]" if sr.get("containsVisa") else ""
        print(f"      [{status}] {sr['selector']:<45} len={sr['textLength']}{visa}")

    # (e) Per-card verdict
    req_inside = any(rn["isInsideJobDetails"] for rn in req_nodes) if req_nodes else False
    req_outside = any(not rn["isInsideJobDetails"] for rn in req_nodes) if req_nodes else False
    has_req = bool(req_nodes)
    visa_inside = any(vn["isInsideJobDetails"] for vn in visa_nodes) if visa_nodes else False
    visa_outside = any(not vn["isInsideJobDetails"] for vn in visa_nodes) if visa_nodes else False
    has_visa = bool(visa_nodes)

    if not has_req:
        verdict = "NOT FOUND"
    elif req_inside and not req_outside:
        verdict = "INSIDE"
    elif req_outside and not req_inside:
        verdict = "OUTSIDE"
    else:
        verdict = "MIXED (inside + outside)"

    visa_verdict = "NOT FOUND"
    if has_visa:
        if visa_inside and not visa_outside:
            visa_verdict = "INSIDE"
        elif visa_outside and not visa_inside:
            visa_verdict = "OUTSIDE"
        else:
            visa_verdict = "MIXED"

    jd_len = 0
    if "error" not in parent_info:
        for child in parent_info["children"]:
            if child["id"] == "job-details":
                jd_len = child["textLength"]

    # Identify sibling selector — check all levels
    sibling_selector = None
    if "error" not in sib_info:
        for sib in sib_info["siblings"]:
            if sib["containsRequirements"] or sib["containsVisa"]:
                if sib["id"]:
                    sibling_selector = f"#{sib['id']}"
                elif sib["class"]:
                    first_class = sib["class"].split()[0]
                    sibling_selector = f"{sib['tag']}.{first_class}"
                else:
                    sibling_selector = f"{sib['tag']} (no id/class)"
    # Also check extended levels
    if not sibling_selector and "error" not in extended:
        for lvl_info in extended["levels"]:
            for sib in lvl_info["significantSiblings"]:
                if sib["containsRequirements"] or sib["containsVisa"]:
                    if sib["id"]:
                        sibling_selector = f"#{sib['id']} (level {lvl_info['level']})"
                    elif sib["class"]:
                        first_class = sib["class"].split()[0]
                        sibling_selector = f"{sib['tag']}.{first_class} (level {lvl_info['level']})"
                    else:
                        sibling_selector = f"{sib['tag']} (no id/class, level {lvl_info['level']})"
                    break
            if sibling_selector:
                break

    # (f) Full ancestry of visa phrase elements
    print("\n  [f] Visa phrase ancestor chains:")
    visa_ancestry = await page.evaluate(JS_VISA_ANCESTRY)
    if not visa_ancestry:
        print("      (no visa phrases found)")
    for va in visa_ancestry:
        print(f"      phrase='{va['phrase']}' text='{_preview(va['text'], 100)}'")
        for ci, anc in enumerate(va["ancestorChain"]):
            indent = "        " + "  " * ci
            alabel = f"<{anc['tag']}"
            if anc["id"]:
                alabel += f" id='{anc['id']}'"
            if anc["class"]:
                alabel += f" class='{anc['class'][:70]}'"
            alabel += f">  len={anc['textLength']}"
            print(f"{indent}{alabel}")

    # (g) "Requirements added by the job poster" section deep-dive
    print("\n  [g] 'Requirements added by the job poster' section:")
    req_section = await page.evaluate(JS_REQ_SECTION_ANCESTRY)
    if not req_section.get("found"):
        print("      (section not found)")
    else:
        print(f"      Section container: <{req_section['sectionTag']}"
              f" id='{req_section['sectionId']}'"
              f" class='{req_section['sectionClass'][:80]}'>  len={req_section['sectionTextLength']}")
        print(f"      Section preview: {_preview(req_section['sectionPreview'], 200)}")
        print("      Ancestor chain:")
        for anc in req_section["ancestorChain"]:
            indent = "        " + "  " * anc["level"]
            alabel = f"<{anc['tag']}"
            if anc["id"]:
                alabel += f" id='{anc['id']}'"
            if anc["class"]:
                alabel += f" class='{anc['class'][:70]}'"
            alabel += f">  len={anc['textLength']} siblings={anc['siblingCount']}"
            print(f"{indent}{alabel}")

    print(f"\n  >>> VERDICT: Requirements = {verdict}")
    print(f"  >>> VERDICT: Visa phrases = {visa_verdict}")
    if sibling_selector:
        print(f"  >>> Sibling selector candidate: {sibling_selector}")

    return {
        "idx": idx,
        "title": label[:40],
        "jd_len": jd_len,
        "has_req": has_req,
        "verdict": verdict,
        "has_visa": has_visa,
        "visa_verdict": visa_verdict,
        "sibling_selector": sibling_selector or "-",
    }


async def diagnose() -> None:
    cookies = _load_cookies()
    print(f"Loaded {len(cookies)} cookies from {COOKIES_PATH}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        if cookies:
            await context.add_cookies(cookies)
        page = await context.new_page()

        summary_rows: list[dict] = []
        run_idx = 0

        # ── Phase 1: Search panel mode (matches real pipeline) ─────────
        print("\n" + "#" * 70)
        print("PHASE 1: SEARCH PANEL MODE (how the pipeline actually works)")
        print("#" * 70)

        for job in TARGET_JOBS:
            url = SEARCH_PANEL_URL.format(external_id=job["external_id"])
            print(f"\nNavigating to: {url}")
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # The currentJobId param should auto-select the job in the side panel.
            # Scroll down in the side panel to ensure full content loads.
            await page.evaluate("""
                () => {
                    const panel = document.querySelector('.jobs-search__right-rail')
                        || document.querySelector('.scaffold-layout__detail');
                    if (panel) panel.scrollTo(0, panel.scrollHeight);
                }
            """)
            await page.wait_for_timeout(2000)

            row = await _analyze_page(page, run_idx, f"[PANEL] {job['label']}")
            row["mode"] = "panel"
            summary_rows.append(row)
            run_idx += 1

            delay = random.uniform(2.0, 4.0)
            print(f"\n  (waiting {delay:.1f}s)")
            await page.wait_for_timeout(int(delay * 1000))

        # ── Phase 2: Direct view mode (full page) ─────────────────────
        print("\n" + "#" * 70)
        print("PHASE 2: DIRECT VIEW MODE (full page, different DOM)")
        print("#" * 70)

        for job in TARGET_JOBS:
            url = JOB_VIEW_URL.format(external_id=job["external_id"])
            print(f"\nNavigating to: {url}")
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # Scroll page to load all content
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

            row = await _analyze_page(page, run_idx, f"[DIRECT] {job['label']}")
            row["mode"] = "direct"
            summary_rows.append(row)
            run_idx += 1

            delay = random.uniform(2.0, 4.0)
            print(f"\n  (waiting {delay:.1f}s)")
            await page.wait_for_timeout(int(delay * 1000))

        # ── Summary table ──────────────────────────────────────────────
        print(f"\n\n{'='*110}")
        print("SUMMARY TABLE")
        print(f"{'='*110}")
        header = (f"{'#':<3} {'Mode':<7} {'Title':<40} {'JD Len':>7} {'Req?':<5} {'Req Where':<15} "
                  f"{'Visa?':<5} {'Visa Where':<12} {'Sibling Selector'}")
        print(header)
        print("-" * 110)
        for row in summary_rows:
            print(f"{row['idx']:<3} {row.get('mode','?'):<7} {row['title']:<40} {row['jd_len']:>7} "
                  f"{'YES' if row['has_req'] else 'NO':<5} "
                  f"{row['verdict']:<15} "
                  f"{'YES' if row['has_visa'] else 'NO':<5} "
                  f"{row['visa_verdict']:<12} "
                  f"{row['sibling_selector']}")

        # ── Final selector discovery ───────────────────────────────────
        discovered_panel = set()
        discovered_direct = set()
        for row in summary_rows:
            if row["sibling_selector"] != "-":
                if row.get("mode") == "panel":
                    discovered_panel.add(row["sibling_selector"])
                else:
                    discovered_direct.add(row["sibling_selector"])

        print(f"\n{'='*110}")
        print("DISCOVERED SELECTORS")
        print(f"{'='*110}")
        print("  Panel mode (pipeline-relevant):")
        if discovered_panel:
            for sel in sorted(discovered_panel):
                print(f"    -> {sel}")
        else:
            print("    (none)")
        print("  Direct view mode:")
        if discovered_direct:
            for sel in sorted(discovered_direct):
                print(f"    -> {sel}")
        else:
            print("    (none)")

        print("\nDone. Browser will close.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(diagnose())
