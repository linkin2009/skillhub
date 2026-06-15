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
THROTTLE = float(os.environ.get("SKILL_THROTTLE", "4.0"))  # stay well under 30/min
TIME_BUDGET = int(os.environ.get("SKILL_BUDGET", "1080"))  # max seconds spent searching
MIN_SPLIT = 48  # don't bisect size ranges narrower than this
BASE_Q = "filename:SKILL.md"
_t0 = [0.0]


def _add(seen, items):
    for it in items:
        hu = it.get("html_url")
        if not hu or hu in seen:
            continue
        repo = it.get("repository") or {}
        owner = repo.get("owner") or {}
        seen[hu] = {"html_url": hu, "repo": repo.get("full_name", ""),
                    "path": it.get("path", ""), "owner": owner.get("login", ""),
                    "avatar": owner.get("avatar_url", "")}


def search_req(url):
    """Code-search GET with secondary-rate-limit backoff (403/429 -> wait)."""
    for attempt in range(6):
        try:
            data, _ = bd.req(url)
            time.sleep(THROTTLE)
            return data
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                ra = e.headers.get("Retry-After")
                wait = int(ra) if (ra and str(ra).isdigit()) else 60
                print(f"  rate-limited ({e.code}); sleeping {wait}s", file=sys.stderr, flush=True)
                time.sleep(wait)
                continue
            print(f"  ! HTTP {e.code}", file=sys.stderr, flush=True)
            return None
        except Exception:
            time.sleep(5)
    return None


def search_count(q):
    d = search_req(f"{API}/search/code?q={urllib.parse.quote(q)}&per_page=1")
    return d.get("total_count", -1) if d else -1


def collect_query(q, seen):
    for page in range(1, 11):  # 1000 results max per query
        d = search_req(f"{API}/search/code?q={urllib.parse.quote(q)}&per_page=100&page={page}")
        if not d:
            break
        items = d.get("items", [])
        if not items:
            break
        _add(seen, items)
        if len(items) < 100 or len(seen) >= MAX_FILES:
            break


def code_search():
    """Bisect on file size to escape the 1000-results-per-query cap."""
    _t0[0] = time.time()
    seen = {}
    stack = [(0, 100000)]
    while stack and len(seen) < MAX_FILES and (time.time() - _t0[0]) < TIME_BUDGET:
        lo, hi = stack.pop()
        cnt = search_count(f"{BASE_Q} size:{lo}..{hi}")
        if cnt == 0:
            continue
        if cnt < 0 or cnt <= 1000 or (hi - lo) <= MIN_SPLIT:
            collect_query(f"{BASE_Q} size:{lo}..{hi}", seen)
            print(f"  size {lo}..{hi}: cnt={cnt} -> unique={len(seen)}", flush=True)
        else:
            mid = (lo + hi) // 2
            stack.append((mid + 1, hi))
            stack.append((lo, mid))  # denser small-size buckets first
    print(f"  [code_search] {len(seen)} files in {int(time.time()-_t0[0])}s", flush=True)
    return list(seen.values())[:MAX_FILES]


def parse_frontmatter(text):
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    if end < 0:
        return None, None
    lines = text[3:end].splitlines()
    name = desc = None
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        low = s.lower()
        if name is None and low.startswith("name:"):
            name = s.split(":", 1)[1].strip().strip("\"'")
        elif desc is None and low.startswith("description:"):
            val = s.split(":", 1)[1].strip()
            if val in ("", ">", ">-", ">+", "|", "|-", "|+"):
                # YAML block scalar: gather the following more-indented lines
                base = len(lines[i]) - len(lines[i].lstrip())
                block, j = [], i + 1
                while j < len(lines):
                    ln = lines[j]
                    if ln.strip() == "":
                        block.append(""); j += 1; continue
                    if (len(ln) - len(ln.lstrip())) > base:
                        block.append(ln.strip()); j += 1
                    else:
                        break
                desc = " ".join(x for x in block if x).strip()
            else:
                desc = val.strip("\"'")
        i += 1
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


def graphql_repo_meta(repos):
    """Fetch stars/topics/etc for many repos via batched GraphQL (~80/call)."""
    out = {}
    B = 80
    for i in range(0, len(repos), B):
        batch = repos[i:i + B]
        parts = []
        for j, full in enumerate(batch):
            if "/" not in full:
                continue
            o, n = full.split("/", 1)
            o = o.replace("\\", "").replace('"', '')
            n = n.replace("\\", "").replace('"', '')
            parts.append(f'r{j}: repository(owner:"{o}", name:"{n}"){{stargazerCount forkCount '
                         f'pushedAt createdAt primaryLanguage{{name}} licenseInfo{{spdxId}} '
                         f'repositoryTopics(first:8){{nodes{{topic{{name}}}}}}}}')
        query = "query{" + " ".join(parts) + "}"
        body = json.dumps({"query": query}).encode()
        try:
            r = urllib.request.Request("https://api.github.com/graphql", data=body,
                headers={"User-Agent": UA, "Authorization": "Bearer " + TOKEN,
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=45) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            data = d.get("data") or {}
            for j, full in enumerate(batch):
                node = data.get(f"r{j}")
                if not node:
                    continue
                out[full] = {
                    "stars": node.get("stargazerCount", 0), "forks": node.get("forkCount", 0),
                    "pushed_at": node.get("pushedAt") or "", "created_at": node.get("createdAt") or "",
                    "language": (node.get("primaryLanguage") or {}).get("name") or "",
                    "license": (node.get("licenseInfo") or {}).get("spdxId") or "",
                    "topics": [t["topic"]["name"] for t in
                               ((node.get("repositoryTopics") or {}).get("nodes") or [])][:8],
                }
        except Exception as e:
            print(f"  ! graphql batch {i//B} err: {e}", file=sys.stderr)
        time.sleep(0.4)
        if (i // B) % 10 == 0:
            print(f"  graphql meta: {len(out)}/{len(repos)}")
    return out


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

    with cf.ThreadPoolExecutor(max_workers=32) as ex:
        found = list(ex.map(fetch_raw, found))

    # unique repos -> star metadata (bulk GraphQL)
    repos = sorted({f["repo"] for f in found if f["repo"]})
    print(f"[skills] GraphQL metadata for {len(repos)} repos...")
    meta = graphql_repo_meta(repos)

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

    # incremental: union with previously indexed skills so re-runs accumulate
    existing = {}
    sp = os.path.join(DATA, "skills.json")
    if os.environ.get("SKILL_FRESH") != "1" and os.path.exists(sp):
        try:
            for r in json.load(open(sp)):
                existing[r["id"]] = r
        except Exception:
            pass
    existing.update(seen_ids)  # new data wins
    records = list(existing.values())
    print(f"[skills] {len(seen_ids)} this run; merged total {len(records)}")

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
