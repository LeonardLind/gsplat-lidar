"""Turn the raw workflow results into one readable markdown digest per topic."""
import json
import os
import sys

src_dir, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)


def md_topic(t):
    r, v = t["research"], t["verification"]
    L = [f"# {t['key']}\n", "## Summary\n", r["summary"], "\n## Recommendations\n"]
    for x in r["recommendations"]:
        L.append(f"- **{x['recommendation']}** — {x['rationale']}" + (f" _Alternatives:_ {x['alternatives']}" if x.get("alternatives") else ""))
    L.append("\n## Load-bearing findings (claim + sources)\n")
    for f in r["findings"]:
        if f.get("load_bearing"):
            L.append(f"- [{f['confidence']}] {f['claim']} — {' '.join(f['sources'][:3])}")
    if r.get("key_numbers"):
        L.append("\n## Key numbers\n")
        for k in r["key_numbers"]:
            L.append(f"- {k['quantity']}: {k['value']}" + (f" ({k['source']})" if k.get("source") else ""))
    if r.get("tools_and_licenses"):
        L.append("\n## Tools & licenses\n")
        for k in r["tools_and_licenses"]:
            L.append(f"- {k['tool']} | {k.get('version_or_date','')} | {k['license']} | win: {k.get('windows','')} | {k.get('notes','')}")
    for name in ("risks", "open_questions", "questions_for_user"):
        if r.get(name):
            L.append(f"\n## {name}\n")
            L += [f"- {x}" for x in r[name]]
    if v:
        L.append("\n## FACT-CHECK: non-confirmed verdicts\n")
        for x in v["verdicts"]:
            if x["verdict"] != "confirmed":
                L.append(f"- **{x['verdict'].upper()}**: {x['claim']} → {x.get('correction','')} ({' '.join(x['sources'][:2])})")
        n_ok = sum(1 for x in v["verdicts"] if x["verdict"] == "confirmed")
        L.append(f"\n_{n_ok} of {len(v['verdicts'])} checked claims confirmed._\n")
        if v.get("missed_developments"):
            L.append("\n## FACT-CHECK: missed developments\n")
            for x in v["missed_developments"]:
                L.append(f"- {x['claim']}: {x['details']} ({' '.join(x['sources'][:2])})")
        L.append("\n## FACT-CHECK: recommendation assessment\n")
        L.append(v["recommendation_assessment"])
    return "\n".join(L) + "\n"


for fname, prefix in (("research-main.json", "main"), ("research-addendum.json", "addendum")):
    d = json.load(open(os.path.join(src_dir, fname), encoding="utf-8"))["result"]
    for i, t in enumerate(d["topics"], 1):
        if t["research"]:
            with open(os.path.join(out_dir, f"{prefix}-{i:02d}-{t['key']}.md"), "w", encoding="utf-8") as fh:
                fh.write(md_topic(t))
    with open(os.path.join(out_dir, f"{prefix}-99-critic.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# {prefix} critic\n\n```json\n{json.dumps(d['critic'], indent=1, ensure_ascii=False)}\n```\n")
    print(prefix, "missing:", d.get("missing"), "gaps returned:", len(d.get("gaps") or []))

for f in sorted(os.listdir(out_dir)):
    print(f, os.path.getsize(os.path.join(out_dir, f)))
