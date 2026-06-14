#!/usr/bin/env python3
"""Free, token-free Chinese translation of skill descriptions.

Uses the public Google Translate gtx endpoint (no key, no LLM tokens) in
parallel threads. Prefers any higher-quality cached translations already in
data/_t/out_*.json (from the Haiku workflow). Writes data/translations.json,
which the scraper's apply_translations() picks up. Re-runnable & incremental:
ids already in translations.json are skipped.
"""

import os, sys, json, glob, time, random
import urllib.request, urllib.parse
import concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


def mt(text):
    q = text[:480]
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
           "&sl=en&tl=zh-CN&dt=t&q=" + urllib.parse.quote(q))
    for attempt in range(3):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(r, timeout=15) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            zh = "".join(seg[0] for seg in d[0] if seg and seg[0]).strip()
            return zh or None
        except Exception:
            time.sleep(1.5 * (attempt + 1) + random.random())
    return None


def main():
    skills = json.load(open(os.path.join(DATA, "skills.json")))

    tr = {}
    tp = os.path.join(DATA, "translations.json")
    if os.path.exists(tp):
        try:
            tr = json.load(open(tp))
        except Exception:
            tr = {}
    # prefer higher-quality salvaged Haiku output
    for f in glob.glob(os.path.join(DATA, "_t", "out_*.json")):
        try:
            for x in json.load(open(f)):
                if x.get("id") and (x.get("zh") or "").strip():
                    tr[x["id"]] = x["zh"].strip()
        except Exception:
            pass

    todo = [(s["id"], s["description"]) for s in skills
            if (s.get("description") or "").strip() and s["id"] not in tr]
    print(f"[mt] cached={len(tr)} to_translate={len(todo)}")

    def work(item):
        i, q = item
        time.sleep(random.random() * 0.4)
        return i, mt(q)

    ok = 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for i, zh in ex.map(work, todo):
            if zh:
                tr[i] = zh
                ok += 1
    print(f"[mt] translated {ok}/{len(todo)} this pass; total={len(tr)}")
    json.dump(tr, open(tp, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
