"""Build the shareable HTML page from PLAN.md (designed wrapper + converted plan body)."""
import html
import re
import sys

import markdown

src, out = sys.argv[1], sys.argv[2]
md_text = open(src, encoding="utf-8").read()

# Privacy / portability: no personal paths, no links to files that only exist locally.
md_text = md_text.replace("Leonard Lind", "&lt;user&gt;")
md_text = re.sub(r"\[([^\]]+)\]\((?!https?://)([^)]+)\)", r"\1 (project repo)", md_text)
md_text = md_text.replace("- [ ] ", "- ☐ ")

# Drop the document's own H1 + front matter (the page has its own header).
body_md = md_text.split("\n---\n", 1)[1] if "\n---\n" in md_text else md_text

conv = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                         extension_configs={"toc": {"permalink": False, "toc_depth": "2-3"}})
body = conv.convert(body_md)
body = re.sub(r"<table>", '<div class="table-wrap"><table>', body)
body = body.replace("</table>", "</table></div>")
body = re.sub(r"<pre><code>", '<div class="pre-wrap"><pre><code>', body)
body = body.replace("</code></pre>", "</code></pre></div>")
# Bare URLs -> links (only in text, not inside existing href attributes).
body = re.sub(r'(?<!["=>])(https?://[^\s<)·]+)', lambda m: f'<a href="{m.group(1)}">{html.escape(m.group(1))}</a>', body)

# TOC from h2 headings only (h3 shown as sub-items).
toc_items = []
for tok in conv.toc_tokens:
    subs = "".join(f'<li><a href="#{c["id"]}">{c["name"]}</a></li>' for c in tok.get("children", []))
    toc_items.append(f'<li><a href="#{tok["id"]}">{tok["name"]}</a>' + (f"<ol>{subs}</ol>" if subs else "") + "</li>")
toc = "<ol>" + "".join(toc_items) + "</ol>"

page = f"""<title>Forest LiDAR &amp; Splat Plan</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: field-survey report. Sticky section index on the left, one reading column (~70ch); wide tables scroll in place. */
:root {{
  --bg: #f4f6f3; --surface: #ffffff; --fg: #1a2320; --muted: #56635d; --rule: #d5ddd7;
  --accent: #2c6a4c; --accent-soft: #e2eee6; --warn: #9a6512; --warn-soft: #f6ecd9;
  --code-bg: #eaefeb;
  --f-display: "Archivo", "Arial Narrow", system-ui, sans-serif;
  --f-body: "Source Serif 4", Georgia, "Times New Roman", serif;
  --f-mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #111816; --surface: #17201d; --fg: #e2e9e5; --muted: #9aa9a1; --rule: #2c3833;
  --accent: #7cc49d; --accent-soft: #1d3329; --warn: #e3b25e; --warn-soft: #33281a; --code-bg: #1c2622; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #111816; --surface: #17201d; --fg: #e2e9e5; --muted: #9aa9a1; --rule: #2c3833;
  --accent: #7cc49d; --accent-soft: #1d3329; --warn: #e3b25e; --warn-soft: #33281a; --code-bg: #1c2622; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--fg); font-family: var(--f-body); font-size: 17px; line-height: 1.6;
  margin: 0; padding-inline: 16px; padding-block: 0 64px; }}
a {{ color: var(--accent); text-underline-offset: 2px; word-break: break-word; }}
a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.masthead {{ max-width: 1240px; margin: 0 auto; padding-block: 40px 28px; border-bottom: 1px solid var(--rule); }}
.eyebrow {{ font-family: var(--f-mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }}
h1 {{ font-family: var(--f-display); font-stretch: 80%; font-weight: 800; font-size: clamp(32px, 6vw, 56px); line-height: 1.02;
  margin: 10px 0 14px; text-wrap: balance; letter-spacing: -.01em; }}
.lede {{ max-width: 68ch; font-size: 19px; color: var(--fg); margin: 0 0 18px; }}
.meta {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.chip {{ font-family: var(--f-mono); font-size: 12.5px; padding: 4px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--fg); }}
.chip.warn {{ background: var(--warn-soft); }}
.layout {{ max-width: 1240px; margin: 0 auto; display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 48px; padding-top: 28px; }}
nav.toc {{ position: sticky; top: env(safe-area-inset-top, 0px); align-self: start; max-height: 100vh; overflow-y: auto; padding-block: 12px 24px;
  font-family: var(--f-display); font-stretch: 90%; font-size: 14px; }}
nav.toc ol {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }}
nav.toc > ol > li > a {{ font-weight: 700; }}
nav.toc ol ol {{ padding-left: 12px; margin: 2px 0 8px; border-left: 1px solid var(--rule); }}
nav.toc ol ol a {{ font-weight: 500; color: var(--muted); }}
nav.toc a {{ text-decoration: none; display: block; padding: 2px 6px; border-radius: 4px; }}
nav.toc a:hover {{ background: var(--accent-soft); }}
details.toc-mobile {{ display: none; }}
main {{ min-width: 0; }}
.start {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 36px; }}
.start section {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; padding: 18px 20px; min-width: 0; }}
.start h2 {{ font-size: 15px; margin: 0 0 8px; font-family: var(--f-display); text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }}
.start p, .start li {{ font-size: 15.5px; }}
.start ul {{ margin: 0; padding-left: 18px; }}
.doc h2 {{ font-family: var(--f-display); font-stretch: 85%; font-weight: 800; font-size: 30px; line-height: 1.15; margin: 56px 0 14px;
  padding-top: 14px; border-top: 2px solid var(--fg); text-wrap: balance; }}
.doc h3 {{ font-family: var(--f-display); font-stretch: 90%; font-weight: 700; font-size: 21px; margin: 34px 0 10px; text-wrap: balance; }}
.doc h4 {{ font-family: var(--f-display); font-size: 17px; margin: 22px 0 8px; }}
.doc p, .doc li {{ max-width: 72ch; }}
.doc ul, .doc ol {{ padding-left: 22px; }}
.doc li + li {{ margin-top: 4px; }}
.doc blockquote {{ margin: 18px 0; padding: 12px 16px; background: var(--warn-soft); border-radius: 6px; max-width: 72ch; }}
.doc blockquote p {{ margin: 0; }}
.doc hr {{ display: none; }}
.table-wrap {{ overflow-x: auto; margin: 16px 0 22px; border: 1px solid var(--rule); border-radius: 6px; background: var(--surface); }}
table {{ border-collapse: collapse; width: 100%; font-family: var(--f-display); font-stretch: 92%; font-size: 14.5px; line-height: 1.45; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; vertical-align: top; padding: 9px 12px; border-bottom: 1px solid var(--rule); min-width: 120px; }}
th {{ font-weight: 700; background: var(--code-bg); position: sticky; top: 0; }}
tr:last-child td {{ border-bottom: 0; }}
td:first-child {{ font-weight: 600; }}
code {{ font-family: var(--f-mono); font-size: .86em; background: var(--code-bg); padding: 1px 5px; border-radius: 4px; word-break: break-word; }}
.pre-wrap {{ overflow-x: auto; margin: 16px 0; background: var(--code-bg); border-radius: 6px; }}
pre {{ margin: 0; padding: 14px 16px; }}
pre code {{ background: none; padding: 0; font-size: 12.5px; line-height: 1.4; white-space: pre; word-break: normal; }}
strong {{ font-weight: 600; }}
footer {{ max-width: 1240px; margin: 48px auto 0; padding-top: 16px; border-top: 1px solid var(--rule); color: var(--muted); font-size: 14px; }}
@media (max-width: 900px) {{
  .layout {{ grid-template-columns: minmax(0, 1fr); gap: 0; }}
  nav.toc {{ display: none; }}
  details.toc-mobile {{ display: block; margin: 0 0 24px; background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; padding: 10px 14px;
    font-family: var(--f-display); font-size: 15px; }}
  details.toc-mobile ol {{ padding-left: 18px; }}
  details.toc-mobile ol ol {{ display: none; }}
  body {{ font-size: 16px; }}
}}
@media (prefers-reduced-motion: no-preference) {{ html {{ scroll-behavior: smooth; }} }}
</style>

<header class="masthead">
  <div class="eyebrow">Research summary &amp; phased plan · Revision 2 · 7 Oct 2026</div>
  <h1>Forest LiDAR &amp; Splat Plan</h1>
  <p class="lede">A local pipeline and web viewer that registers a Gaussian splat trained from Insta360 360° video to a Leica BLK2GO
  LiDAR scan at metric scale, lets you toggle the point cloud, the splat or both, and keeps the camera above the forest floor.
  It is built for a 10×10 m Swedish test plot first, then tropical forest.</p>
  <div class="meta">
    <span class="chip">Personal, non-commercial project</span>
    <span class="chip">No code written yet</span>
    <span class="chip">Next: Phase 0 audits</span>
    <span class="chip warn">Some vendor facts still marked "verify day 0"</span>
  </div>
</header>

<div class="layout">
  <nav class="toc" aria-label="Sections">{toc}</nav>
  <main>
    <details class="toc-mobile"><summary>Sections</summary>{toc}</details>
    <div class="start">
      <section>
        <h2>5-minute read</h2>
        <p>Section 0, <em>Decisions at a glance</em>: what we recommend and where it departs from the original idea.</p>
      </section>
      <section>
        <h2>Before the field test</h2>
        <ul><li>§3 Capture protocol and checklist</li><li>§4 Risks and cheap tests</li><li>§5 Phase 0 and Phase 1 gates</li></ul>
      </section>
      <section>
        <h2>Open questions</h2>
        <p>§6 lists what is still needed from the project owner, ordered by what it blocks.</p>
      </section>
    </div>
    <article class="doc">
{body}
    </article>
  </main>
</div>
<footer>Every claim was researched against primary sources and fact-checked by a second agent; the full evidence trail with URLs lives in the project repository (research/digest).</footer>
"""
open(out, "w", encoding="utf-8").write(page)
print("written", out, len(page) // 1024, "KB")
