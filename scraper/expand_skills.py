#!/usr/bin/env python3
"""Expand the skill index WITHOUT code search.

Code search gets rate-limited fast. Instead, for every repo we already know,
fetch its full git tree (core API, 5000/hr — a different, generous quota) and
pull in EVERY SKILL.md it contains (multi-skill repos / awesome-lists hold
hundreds–thousands each). Ranks new skills by repo stars, caps the total,
fetches frontmatter in parallel, merges, and writes the data files.

Run: GITHUB_TOKEN=$(gh auth token) python3 scraper/expand_skills.py
"""

import os, sys, json, urllib.request, urllib.parse, urllib.error
import concurrent.futures as cf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_data as bd
import build_skills as bs

DATA, API, TOKEN, UA = bd.DATA, bd.API, bd.TOKEN, bd.UA
CAP = int(os.environ.get("EXPAND_MAX", "11000"))   # max NEW skills to add


def tree_paths(arg):
    repo, branch, stars = arg
    try:
        d, _ = bd.req(f"{API}/repos/{repo}/git/trees/{urllib.parse.quote(branch)}?recursive=1")
        out = []
        for t in d.get("tree", []):
            p = t.get("path", "")
            if t.get("type") == "blob" and p.rsplit("/", 1)[-1] == "SKILL.md":
                out.append((repo, branch, p, stars))
        return out
    except Exception:
        return []


def main():
    if not TOKEN:
        print("ERROR: GITHUB_TOKEN required.", file=sys.stderr); sys.exit(1)
    today = bd.now_utc().date().isoformat()
    existing = json.load(open(os.path.join(DATA, "skills.json")))
    by_id = {r["id"]: r for r in existing}
    repo_info, repo_branch = {}, {}
    for r in existing:
        repo_info.setdefault(r["repo"], r)
        u = r.get("url", "")
        if "/blob/" in u:
            repo_branch.setdefault(r["repo"], u.split("/blob/")[1].split("/")[0])

    repos = [(repo, br, repo_info.get(repo, {}).get("stars", 0)) for repo, br in repo_branch.items()]
    repos.sort(key=lambda x: x[2], reverse=True)
    print(f"[expand] {len(repos)} known repos; fetching trees (core API)...", flush=True)

    candidates = []
    done = 0
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        for lst in ex.map(tree_paths, repos):
            done += 1
            for repo, branch, p, stars in lst:
                rid = repo + "//" + p
                if rid not in by_id:
                    candidates.append((repo, branch, p, stars))
            if done % 150 == 0:
                print(f"  trees {done}/{len(repos)} | new candidates {len(candidates)}", flush=True)

    print(f"[expand] {len(candidates)} new SKILL.md found; capping at {CAP}", flush=True)
    candidates.sort(key=lambda x: x[3], reverse=True)
    candidates = candidates[:CAP]

    items = [{"repo": repo, "path": p, "owner": repo.split("/")[0],
              "html_url": f"https://github.com/{repo}/blob/{branch}/{p}",
              "avatar": repo_info.get(repo, {}).get("avatar", "")}
             for repo, branch, p, stars in candidates]

    print(f"[expand] fetching frontmatter for {len(items)} files...", flush=True)
    fetched = []
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        for i, r in enumerate(ex.map(bs.fetch_raw, items)):
            fetched.append(r)
            if (i + 1) % 1500 == 0:
                print(f"  fetched {i+1}/{len(items)}", flush=True)

    added = 0
    for f in fetched:
        name = f.get("name") or bs.dirname_of(f["path"]) or f["repo"].split("/")[-1]
        desc = (f.get("description") or "").strip()
        if not (name or desc):
            continue
        if len(desc) > 180:
            desc = desc[:177] + "…"
        ri = repo_info.get(f["repo"], {})
        owner = f["owner"]
        by_id[f["repo"] + "//" + f["path"]] = {
            "id": f["repo"] + "//" + f["path"], "name": name, "author": owner, "description": desc,
            "repo": f["repo"], "url": f["html_url"], "stars": ri.get("stars", 0),
            "forks": ri.get("forks", 0), "trend": 0, "category": bd.categorize(name + " " + desc),
            "topics": ri.get("topics", []), "official": owner.lower() in bd.OFFICIAL_OWNERS,
            "verified": ri.get("verified", False), "language": ri.get("language", ""),
            "license": ri.get("license", ""), "avatar": ri.get("avatar", ""),
            "pushed_at": ri.get("pushed_at", ""), "created_at": ri.get("created_at", ""),
        }
        added += 1

    records = list(by_id.values())
    for r in records:
        bd.add_tier(r)
    bd.apply_translations(records)
    records.sort(key=lambda r: r["stars"], reverse=True)

    os.makedirs(bd.SNAPDIR, exist_ok=True)
    json.dump([{"id": r["id"], "stars": r["stars"]} for r in records],
              open(os.path.join(bd.SNAPDIR, f"{today}.json"), "w"))
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
    print(f"[expand] +{added} -> {len(records)} skills, {metaj['total_stars']:,} stars, {len(cats)} cats", flush=True)


if __name__ == "__main__":
    main()
