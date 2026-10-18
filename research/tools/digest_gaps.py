import json, os, sys
src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding="utf-8"))["result"]
print("failed:", d.get("failed"))
for i, g in enumerate(d["gaps"], 1):
    r = g["research"]
    L = [f"# gap: {g['key']}\n", "## Summary\n", r["summary"], "\n## Plan changes\n"]
    L += [f"- {x}" for x in r.get("plan_changes", [])]
    L.append("\n## Recommendations\n")
    for x in r["recommendations"]:
        L.append(f"- **{x['recommendation']}** — {x['rationale']}" + (f" _Alt:_ {x['alternatives']}" if x.get("alternatives") else ""))
    L.append("\n## Load-bearing findings\n")
    for f in r["findings"]:
        if f.get("load_bearing"):
            L.append(f"- [{f['confidence']}] {f['claim']} — {' '.join(f['sources'][:3])}")
    if r.get("key_numbers"):
        L.append("\n## Key numbers\n")
        L += [f"- {k['quantity']}: {k['value']}" + (f" ({k['source']})" if k.get("source") else "") for k in r["key_numbers"]]
    L.append("\n## Still unknown\n")
    L += [f"- {x}" for x in r.get("still_unknown", [])]
    if r.get("questions_for_user"):
        L.append("\n## Questions for user\n")
        L += [f"- {x}" for x in r["questions_for_user"]]
    fn = os.path.join(out, f"gaps-{i:02d}-{g['key']}.md")
    open(fn, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(fn, os.path.getsize(fn))
