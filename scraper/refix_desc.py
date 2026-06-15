#!/usr/bin/env python3
"""Re-fetch + re-parse skills whose description came out broken/empty.

Earlier parsing missed YAML block scalars (description: > / |), leaving values
like '>', '>-', '|', '—'. The parser is fixed in build_skills.parse_frontmatter;
this re-fetches just those files, re-parses, recategorizes, and drops their stale
machine translations so they get re-translated.
"""

import os, sys, json
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_skills as bs
import build_data as bd

DATA = bs.DATA


def broken(x):
    x = (x or "").strip()
    return x in ("", "-", ">", ">-", ">+", "|", "|-", "|+", "—", "...", "…") or len(x) <= 2


def main():
    d = json.load(open(os.path.join(DATA, "skills.json")))
    targets = [s for s in d if broken(s.get("description"))]
    print(f"[refix] {len(targets)} broken descriptions; re-fetching...")
    by_url = {}
    for s in targets:
        by_url.setdefault(s["url"], s)
    items = [{"html_url": u} for u in by_url]

    fetched = []
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        for i, r in enumerate(ex.map(bs.fetch_raw, items)):
            fetched.append(r)
            if (i + 1) % 500 == 0:
                print(f"  refetched {i+1}/{len(items)}")

    tr_path = os.path.join(DATA, "translations.json")
    tr = json.load(open(tr_path)) if os.path.exists(tr_path) else {}

    fixed = 0
    for f in fetched:
        s = by_url.get(f["html_url"])
        nd = (f.get("description") or "").strip()
        if s and nd and not broken(nd):
            if len(nd) > 180:
                nd = nd[:177] + "…"
            s["description"] = nd
            s["category"] = bd.categorize(s["name"] + " " + nd + " " + " ".join(s.get("topics", [])))
            tr.pop(s["id"], None)  # force re-translation of the now-real text
            fixed += 1

    json.dump(d, open(os.path.join(DATA, "skills.json"), "w"), ensure_ascii=False)
    json.dump(tr, open(tr_path, "w"), ensure_ascii=False)
    still = sum(1 for s in d if broken(s.get("description")))
    print(f"[refix] fixed {fixed}; still broken {still}")


if __name__ == "__main__":
    main()
