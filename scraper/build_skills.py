#!/usr/bin/env python3
"""Skill-LEVEL builder — true 1:1 with SkillBox.

Instead of one card per repo, this indexes every individual SKILL.md file on
GitHub (a repo may contain many skills), parsing each skill's name/description
from its YAML frontmatter. Requires GITHUB_TOKEN (code search needs auth).

Pipeline: code-search SKILL.md -> parallel raw fetch + frontmatter parse ->
parallel repo-star fetch -> assemble skill records -> reuse build_data helpers
(categorize / tier / collections / translations) -> write the same data files.
"""

import os, sys, json, time, urllib.request, urllib.parse, urllib.error
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_data as bd  # reuse categorize, add_tier, build_collections, etc.

DATA = bd.DATA
SNAPDIR = bd.SNAPDIR
TOKEN = bd.TOKEN
API = bd.API
UA = bd.UA
MAX_FILES = int(os.environ.get("SKILL_MAX", "1800"))

CODE_QUERIES = [
    "filename:SKILL.md",
    "path:skills filename:SKILL.md",
    "path:.claude/skills filename:SKILL.md",
    "path:.claude filename:SKILL.md",
]


def code_search():
    seen = {}
    for q in CODE_QUERIES:
        for page in range(1, 11):  # max 1000 results / query
            url = f"{API}/search/code?q={urllib.parse.quote(q)}&per_page=100&page={page}"
            try:
                data, _ = bd.req(url)
            except urllib.error.HTTPError as e:
                print(f"  ! code search {e.code} on '{q}' p{page}", file=sys.stderr)
                time.sleep(5)
                break
            except Exception as e:
                print(f"  ! {e}", file=sys.stderr)
                break
            items = data.get("items", [])
            if not items:
                break
            for it in items:
                hu = it.get("html_url")
                if not hu or hu in seen:
                    continue
                repo = it.get("repository") or {}
                owner = repo.get("owner") or {}
                seen[hu] = {
                    "html_url": hu, "repo": repo.get("full_name", ""),
                    "path": it.get("path", ""), "owner": owner.get("login", ""),
                    "avatar": owner.get("avatar_url", ""),
                }
            time.sleep(2.5)  # authenticated search ~30/min
            if len(items) < 100 or len(seen) >= MAX_FILES:
                break
        print(f"  code '{q}': total unique {len(seen)}")
        if len(seen) >= MAX_FILES:
            break
    return list(seen.values())[:MAX_FILES]


def parse_frontmatter(text):
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    if end < 0:
        return None, None
    name = desc = None
    for line in text[3:end].splitlines():
        s = line.strip()
        low = s.lower()
        if name is None and low.startswith("name:"):
            name = s.split(":", 1)[1].strip().strip("\"'")
        elif desc is None and low.startswith("description:"):
            desc = s.split(":", 1)[1].strip().strip("\"'")
        if name and desc:
            break
    return name, desc


def fetch_raw(item):
    raw = (item["html_url"].replace("https://github.com/", "https://raw.githubusercontent.com/")
           .replace("/blob/", "/"))
    try:
        r = urllib.request.Request(raw, headers={"User-Agent": UA})
        with urllib.request.urlopen(r, timeout=20) as resp:
            text = resp.read().decode("utf-8", "ignore")
        item["name"], item["description"] = parse_frontmatter(text[:6000])
    except Exception:
        item["name"], item["description"] = None, None
    return item


def fetch_repo_meta(full):
    try:
        d, _ = bd.req(f"{API}/repos/{full}")
        return full, {
            "stars": d.get("stargazers_count", 0), "forks": d.get("forks_count", 0),
            "topics": (d.get("topics") or [])[:8],
            "license": (d.get("license") or {}).get("spdx_id") or "" if d.get("license") else "",
            "pushed_at": d.get("pushed_at") or "", "created_at": d.get("created_at") or "",
            "language": d.get("language") or "",
        }
    except Exception:
        return full, {}


def dirname_of(path):
    parts = [p for p in path.split("/") if p and p != "SKILL.md"]
    return parts[-1] if parts else ""


def main():
    if not TOKEN:
        print("ERROR: GITHUB_TOKEN required for code search.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(SNAPDIR, exist_ok=True)
    today = os.environ.get("BUILD_DATE") or bd.now_utc().date().isoformat()
    print(f"[skills] date={today} max={MAX_FILES}")

    found = code_search()
    print(f"[skills] {len(found)} SKILL.md files found; fetching content...")

    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        found = list(ex.map(fetch_raw, found))

    # unique repos -> star metadata
    repos = sorted({f["repo"] for f in found if f["repo"]})
    print(f"[skills] fetching metadata for {len(repos)} repos...")
    meta = {}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for full, m in ex.map(fetch_repo_meta, repos):
            meta[full] = m

    records = []
    for f in found:
        name = f.get("name") or dirname_of(f["path"]) or f["repo"].split("/")[-1]
        desc = (f.get("description") or "").strip()
        if len(desc) > 180:
            desc = desc[:177] + "…"
        m = meta.get(f["repo"], {})
        owner = f["owner"]
        stars = m.get("stars", 0)
        official = owner.lower() in bd.OFFICIAL_OWNERS
        verified = bool(m.get("license")) and stars >= 25
        topics = m.get("topics", [])
        blob = name + " " + desc + " " + " ".join(topics)
        records.append({
            "id": f["repo"] + "//" + f["path"],
            "name": name, "author": owner, "description": desc,
            "repo": f["repo"], "url": f["html_url"],
            "stars": stars, "forks": m.get("forks", 0), "trend": 0,
            "category": bd.categorize(blob), "topics": topics,
            "official": official, "verified": verified,
            "language": m.get("language", ""), "license": m.get("license", ""),
            "avatar": f["avatar"], "pushed_at": m.get("pushed_at", ""),
            "created_at": m.get("created_at", ""),
        })

    # drop empties (no name AND no desc), dedupe by id
    seen_ids = {}
    for r in records:
        if not r["name"] and not r["description"]:
            continue
        seen_ids[r["id"]] = r
    records = list(seen_ids.values())

    for r in records:
        bd.add_tier(r)
    bd.apply_translations(records)
    records.sort(key=lambda r: r["stars"], reverse=True)
    print(f"[skills] assembled {len(records)} skill records")

    # snapshot for trend continuity
    json.dump([{"id": r["id"], "stars": r["stars"]} for r in records],
              open(os.path.join(SNAPDIR, f"{today}.json"), "w"))

    collections = bd.build_collections(records)
    treasure = [r["id"] for r in records[:18]]
    hot = sorted(records, key=lambda r: (r["trend"], r["stars"]), reverse=True)[:12]
    daily = {"date": today, "new": [], "rising": [], "hot": [r["id"] for r in hot], "added_count": 0}
    cats = {}
    for r in records:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    metaj = {"updated_at": bd.now_utc().isoformat(), "total_skills": len(records),
             "total_stars": sum(r["stars"] for r in records), "categories": cats,
             "authenticated": True, "granularity": "skill"}

    for fn, obj in [("skills.json", records), ("collections.json", collections),
                    ("treasure.json", treasure), ("daily.json", daily), ("meta.json", metaj)]:
        json.dump(obj, open(os.path.join(DATA, fn), "w"), ensure_ascii=False)

    print(f"[skills] DONE: {len(records)} skills, {metaj['total_stars']:,} stars, "
          f"{len(collections)} collections, {len(cats)} cats")


if __name__ == "__main__":
    main()
