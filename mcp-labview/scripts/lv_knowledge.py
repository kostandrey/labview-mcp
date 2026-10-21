#!/usr/bin/env python3
"""lv_knowledge.py - structured lookup over verified LabVIEW codegen facts.

Distills the prose knowledge base (gateway-recipe.md, subvi-placement.md,
SKILL.md) into machine-readable form (lv_knowledge.json, same directory) so
terminal maps, connector panes, wire kinds, resolver classes and setval
representation codes are looked up - not recalled from prose.

Usage:
  lv_knowledge.py <query> [more words...]   fuzzy search across all sections
  lv_knowledge.py --all                     dump everything

Examples:
  lv_knowledge.py add array elements
  lv_knowledge.py histogram
  lv_knowledge.py select
  lv_knowledge.py DBL              # representation code
  lv_knowledge.py st1              # wire kind
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "lv_knowledge.json")


def load():
    with open(DB, encoding="utf-8") as f:
        return json.load(f)


def fmt_terms(terms):
    if not terms:
        return ""
    return "; ".join("Terms[%s]=%s" % (k, v) for k, v in sorted(
        terms.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0))


def search(db, words):
    wl = [w.lower() for w in words]
    out = []

    def hit(text):
        t = text.lower()
        return all(w in t for w in wl)

    for kind, entry in db["primitives"].items():
        blob = "%s %s %s %s" % (kind, entry.get("name", ""),
                                fmt_terms(entry.get("terms", {})),
                                entry.get("note", ""))
        if hit(blob):
            out.append(("primitive %s = %s" % (kind, entry["name"]),
                        blob, entry.get("src", ""), entry.get("note", "")))
    for name, entry in db["structures"].items():
        blob = "%s %s %s" % (name, fmt_terms(entry.get("terms", {})),
                             entry.get("note", ""))
        if hit(blob):
            out.append(("structure %s" % name, blob, entry.get("src", ""),
                        entry.get("note", "")))
    for name, entry in db["subvi_panes"].items():
        blob = "%s %s %s" % (name, entry.get("path", ""),
                             " ".join("%s=%s" % kv
                                      for kv in entry.get("cells", {}).items()))
        if hit(blob):
            lines = ["subVI %s  (%s)" % (name, entry.get("path", ""))]
            for cell in sorted(entry.get("cells", {}), key=int):
                lines.append("  cell %s: %s" % (cell, entry["cells"][cell]))
            if entry.get("note"):
                lines.append("  note: " + entry["note"])
            out.append(("\n".join(lines), blob, entry.get("src", ""), ""))
    for kind, desc in db["wire_kinds"].items():
        if hit("%s %s" % (kind, desc)):
            out.append(("wire kind %s = %s" % (kind, desc), "", "", ""))
    for rep, name in db["representation_codes"].items():
        if hit("%s %s" % (rep, name)):
            out.append(("representation %s = setval arg3 code %s" % (name, rep),
                        "", "", ""))
    for e in db["resolver_classes"]["verified"]:
        if hit(e):
            out.append(("resolver class: %s" % e, "", db["resolver_classes"]["src"],
                        db["resolver_classes"]["syntax"]))
    for code, desc in db["error_codes"].items():
        if hit("%s %s" % (code, desc)):
            out.append(("error %s = %s" % (code, desc), "", "", ""))
    for key, desc in db["batch_format"].items():
        if hit("%s %s" % (key, desc)):
            out.append(("batch %s = %s" % (key, desc), "", db["batch_format"]["src"], ""))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    db = load()
    words = [] if argv[1] == "--all" else argv[1:]
    results = search(db, words)
    if not results:
        print("no match for: %s" % " ".join(argv[1:]))
        return 1
    for title, blob, src, note in results:
        print(title)
        if note:
            print("  note: %s" % note)
        if src:
            print("  verified: %s" % src)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
