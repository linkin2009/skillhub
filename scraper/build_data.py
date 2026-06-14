#!/usr/bin/env python3
"""SkillBox-clone data builder.

Discovers AI-agent / Claude "skill" repositories on GitHub, enriches them with
real metadata (stars, description, topics, owner avatar), classifies them into a
SkillBox-style taxonomy, computes day-over-day trend from snapshots, and emits
the JSON files the static site consumes.

Stdlib only. Uses GITHUB_TOKEN env var when present (GitHub Actions provides one
for free at 5000 req/hr). Without a token it falls back to unauthenticated repo
search, which still returns real repos with real star counts.
"""

import json
import os
import sys
import time
import datetime
import urllib.request
import urllib.parse
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SNAPDIR = os.path.join(DATA, "snapshots")
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
API = "https://api.github.com"
UA = "skillbox-clone-scraper"

# More queries / pages when we have a token (higher rate limit).
HAS_TOKEN = bool(TOKEN)
PAGES = 4 if HAS_TOKEN else 1
THROTTLE = 2.5 if HAS_TOKEN else 7.0  # search limit: 30/min auth, 10/min unauth

SEARCH_QUERIES = [
    "topic:claude-skill",
    "topic:claude-skills",
    "topic:claude-code",
    "topic:claude-code-skill",
    "topic:agent-skills",
    "topic:claude-agent",
    "topic:claude-plugin",
    "topic:mcp-server",
    "claude skill in:name,description",
    "claude code skill in:name,description",
    "agent skill in:name,description",
    "SKILL.md in:readme",
]

# Domain expansion: advertising / marketing / data-analysis skills.
# (Paired with the relevance filter so only skill/agent/mcp repos in these
#  domains are kept — not every random marketing library.)
EXTRA_QUERIES = [
    "google ads in:name,description",
    "meta ads in:name,description",
    "facebook ads agent in:name,description",
    "marketing agent in:name,description",
    "advertising mcp in:name,description",
    "seo agent in:name,description",
    "data analysis agent in:name,description",
    "analytics agent in:name,description",
    "competitor analysis in:name,description",
    "competitive intelligence agent in:name,description",
    "shopify agent in:name,description",
    "ecommerce agent in:name,description",
    "email marketing in:name,description",
    "cold email agent in:name,description",
    "newsletter agent in:name,description",
]
SEARCH_QUERIES = SEARCH_QUERIES + EXTRA_QUERIES

SKILL_SIGNALS = ["skill", "claude", "agent", "mcp", "plugin", "slash-command",
                 "sub-agent", "subagent", "anthropic", "prompt", "llm-tool",
                 "ai-assistant", "copilot", "cursor"]

OFFICIAL_OWNERS = {
    "anthropics", "openai", "microsoft", "google", "googleapis",
    "google-gemini", "vercel", "shopify", "cloudflare", "huggingface",
    "githubnext", "github", "modelcontextprotocol",
}

# category key -> (priority-ordered) keyword detectors. First match wins.
CATEGORY_RULES = [
    ("security",  ["security", "pentest", "vulnerab", "exploit", "secret", "auth0", "oauth", "crypto", "owasp"]),
    ("design",    ["design", "figma", "excalidraw", "diagram", "illustrat", "svg", "drawing", "ui/ux", "wireframe", "midjourney", "image-gen", "imagegen", "canvas"]),
    ("ai-ml",     ["llm", "machine-learning", "machine learning", "rag", "embedding", "pytorch", "tensorflow", "fine-tune", "finetune", "transformer", "neural", "deep-learning"]),
    ("research",  ["research", "arxiv", "paper", "literature", "scholar", "academic", "citation", "zotero"]),
    ("data",      ["data-analysis", "analytics", "dataviz", "visualization", "pandas", "chart", "plot", "spreadsheet", "dashboard", "bigquery"]),
    ("frontend",  ["frontend", "react", "vue", "svelte", "tailwind", "next.js", "nextjs", "component", "css", "ui-kit"]),
    ("backend",   ["backend", "fastapi", "django", "express", "graphql", "postgres", "mysql", "supabase", "firebase", "rest-api", "microservice"]),
    ("devops",    ["devops", "docker", "kubernetes", "k8s", "terraform", "ansible", "ci/cd", "cicd", "deploy", "aws", "azure", "gcp", "cloud", "helm"]),
    ("testing",   ["testing", "pytest", "jest", "playwright", "selenium", "unit-test", "e2e", "debug", "qa"]),
    ("docs",      ["documentation", "docx", "pdf", "markdown", "notion", "confluence", "readme"]),
    ("writing",   ["writing", "copywriting", "blog", "seo", "content", "article", "newsletter", "ghostwriter"]),
    ("integration", ["integration", "mcp", "webhook", "zapier", "slack", "telegram", "discord", "n8n", "automation-platform"]),
    ("marketing", ["advertis", "marketing", "google-ads", "meta-ads", "facebook-ads", "tiktok-ads", "ppc", "adwords", "campaign", "growth-marketing", "ad-creative", "competitor", "competitive", "email-marketing", "newsletter", "cold-email"]),
    ("business",  ["ecommerce", "shopify", "invoice", "crm", "sales", "finance", "trading", "stock"]),
    ("productivity", ["productivity", "workflow", "automation", "todo", "calendar", "email", "task-management"]),
    ("communication", ["communication", "collaboration", "chatbot", "messaging", "meeting"]),
    ("planning",  ["planning", "roadmap", "project-management", "gantt", "okr"]),
    ("meta",      ["skill-creator", "create-skill", "meta-skill", "scaffold", "generator", "boilerplate", "template-repo"]),
    ("programming", ["refactor", "lint", "git", "compiler", "code-review", "debugger", "ide", "language-server"]),
    ("devtools",  ["cli", "terminal", "shell", "developer-tool", "sdk"]),
]


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def req(url, accept="application/vnd.github+json"):
    headers = {"User-Agent": UA, "Accept": accept,
               "X-GitHub-Api-Version": "2022-11-28"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    last = None
    for attempt in range(4):
        try:
            r = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8")), dict(resp.headers)
        except urllib.error.HTTPError:
            raise  # caller handles HTTP status codes (rate limits etc.)
        except Exception as e:  # transient SSL/connection blips -> retry
            last = e
            time.sleep(3 * (attempt + 1))
    raise last


def search_repos(query, page):
    q = urllib.parse.quote(query)
    url = f"{API}/search/repositories?q={q}&sort=stars&order=desc&per_page=100&page={page}"
    try:
        data, hdrs = req(url)
        return data.get("items", [])
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        print(f"  ! HTTP {e.code} on '{query}' p{page}: {body}", file=sys.stderr)
        if e.code in (403, 429):
            time.sleep(60)
        return []
    except Exception as e:
        print(f"  ! err on '{query}' p{page}: {e}", file=sys.stderr)
        return []


def categorize(text):
    t = text.lower()
    for key, kws in CATEGORY_RULES:
        for kw in kws:
            if kw in t:
                return key
    return "other"


def to_record(item):
    full = item.get("full_name", "")
    owner = (item.get("owner") or {}).get("login", "")
    topics = item.get("topics", []) or []
    desc = item.get("description") or ""
    blob = " ".join([item.get("name", ""), desc, " ".join(topics)])
    stars = item.get("stargazers_count", 0)
    pushed = item.get("pushed_at") or ""
    official = owner.lower() in OFFICIAL_OWNERS
    # verified heuristic: maintained + has license + meaningful traction
    verified = bool(item.get("license")) and stars >= 25 and bool(pushed)
    return {
        "id": full,
        "name": item.get("name", ""),
        "author": owner,
        "description": desc,
        "repo": full,
        "url": item.get("html_url", ""),
        "stars": stars,
        "forks": item.get("forks_count", 0),
        "trend": 0,
        "category": categorize(blob),
        "topics": topics[:8],
        "official": official,
        "verified": verified,
        "language": item.get("language") or "",
        "license": ((item.get("license") or {}).get("spdx_id") or "") if item.get("license") else "",
        "avatar": (item.get("owner") or {}).get("avatar_url", ""),
        "pushed_at": pushed,
        "created_at": item.get("created_at") or "",
    }


def add_tier(r):
    """Assign an A/B/C quality tier and a 'stale' flag (no push in >1yr)."""
    s = r.get("stars", 0)
    if r.get("official") or s >= 1000:
        r["tier"] = "A"
    elif r.get("verified") and s >= 100:
        r["tier"] = "B"
    else:
        r["tier"] = "C"
    r["stale"] = False
    p = (r.get("pushed_at") or "")[:10]
    if p:
        try:
            r["stale"] = (now_utc().date() - datetime.date.fromisoformat(p)).days > 365
        except Exception:
            pass
    return r


def load_translations():
    p = os.path.join(DATA, "translations.json")
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            return {}
    return {}


def apply_translations(records):
    """Attach cached Chinese descriptions (id -> zh) so they survive re-scrapes."""
    tr = load_translations()
    if not tr:
        return
    n = 0
    for r in records:
        z = tr.get(r["id"])
        if z:
            r["desc_zh"] = z
            n += 1
    print(f"  applied {n} cached zh translations")


def is_relevant(r):
    if r["author"].lower() in OFFICIAL_OWNERS:
        return True
    blob = (r["name"] + " " + r["description"] + " " + " ".join(r["topics"])).lower()
    return any(s in blob for s in SKILL_SIGNALS)


def discover():
    seen = {}
    for q in SEARCH_QUERIES:
        got = 0
        for p in range(1, PAGES + 1):
            items = search_repos(q, p)
            if not items:
                break
            for it in items:
                full = it.get("full_name")
                if not full:
                    continue
                # keep the richest copy (max stars seen)
                if full not in seen or it.get("stargazers_count", 0) > seen[full].get("stargazers_count", 0):
                    seen[full] = it
            got += len(items)
            time.sleep(THROTTLE)
            if len(items) < 100:
                break
        print(f"  query '{q}': +{got} (total unique {len(seen)})")
        time.sleep(THROTTLE)
    return [to_record(it) for it in seen.values()]


def load_prev_snapshot():
    """Return {repo_id: stars} from the most recent prior snapshot."""
    if not os.path.isdir(SNAPDIR):
        return {}, None
    snaps = sorted(f for f in os.listdir(SNAPDIR) if f.endswith(".json"))
    if not snaps:
        return {}, None
    last = snaps[-1]
    try:
        with open(os.path.join(SNAPDIR, last)) as f:
            rows = json.load(f)
        return {r["id"]: r.get("stars", 0) for r in rows}, last.replace(".json", "")
    except Exception:
        return {}, None


def compute_trend(records, today):
    prev, prev_date = load_prev_snapshot()
    if not prev or not prev_date:
        return [], []  # no history yet
    try:
        d0 = datetime.date.fromisoformat(prev_date)
        d1 = datetime.date.fromisoformat(today)
        days = max((d1 - d0).days, 1)
    except Exception:
        days = 1
    rising, new = [], []
    prev_ids = set(prev.keys())
    for r in records:
        old = prev.get(r["id"])
        if old is None:
            r["trend"] = 0
            if r["id"] not in prev_ids:
                new.append(r)
        else:
            r["trend"] = round((r["stars"] - old) / days, 1)
    rising = sorted([r for r in records if r["trend"] > 0],
                    key=lambda r: r["trend"], reverse=True)[:40]
    new = sorted(new, key=lambda r: r["stars"], reverse=True)[:40]
    return rising, new


COLLECTIONS_SEED = [
    {"id": "ppt", "name_zh": "PPT 全家桶", "name_en": "PPT Suite", "icon": "\U0001F4CA",
     "desc_zh": "从大纲到成片，AI 替你做一整套演示", "match": ["ppt", "slide", "presentation", "deck", "powerpoint", "keynote"]},
    {"id": "creator", "name_zh": "自媒体创作引擎", "name_en": "Creator Engine", "icon": "✍️",
     "desc_zh": "选题、成稿、SEO、抓素材，一条龙", "match": ["content", "writing", "seo", "blog", "copywriting", "social", "newsletter"]},
    {"id": "vibe", "name_zh": "Vibe Coding 套装", "name_en": "Vibe Coding Kit", "icon": "\U0001F4BB",
     "desc_zh": "让 AI 写出的前端不再有 AI 味", "match": ["frontend", "react", "vue", "ui", "component", "tailwind", "css"]},
    {"id": "office", "name_zh": "办公文档全家桶", "name_en": "Office Docs", "icon": "\U0001F4C4",
     "desc_zh": "PDF / Word / Excel / PPT 全覆盖", "match": ["pdf", "docx", "excel", "word", "document", "spreadsheet", "office"]},
    {"id": "art", "name_zh": "AI 绘图工作台", "name_en": "AI Art Studio", "icon": "\U0001F3A8",
     "desc_zh": "生图、改图、修图，主流模型一站调齐", "match": ["image", "draw", "art", "diagram", "design", "midjourney", "imagegen", "illustrat"]},
    {"id": "video", "name_zh": "视频创作流水线", "name_en": "Video Pipeline", "icon": "\U0001F3AC",
     "desc_zh": "图生视频、模型直调、代码级剪辑", "match": ["video", "ffmpeg", "subtitle", "clip", "youtube", "edit"]},
    {"id": "agent", "name_zh": "Agent 开发者工具箱", "name_en": "Agent Dev Kit", "icon": "\U0001F916",
     "desc_zh": "做 skill、建 MCP、找 skill 的元工具", "match": ["agent", "mcp", "skill", "tool", "builder", "scaffold"]},
    {"id": "research", "name_zh": "研究检索增强", "name_en": "Research Boost", "icon": "\U0001F50D",
     "desc_zh": "论文复现、深度检索、知识库问答", "match": ["research", "paper", "arxiv", "rag", "literature", "scholar", "search"]},
    {"id": "shopify", "name_zh": "Shopify 电商全家桶", "name_en": "Shopify Commerce", "icon": "\U0001F6D2",
     "desc_zh": "建店、主题、API 全覆盖", "match": ["shopify", "ecommerce", "store", "product", "commerce"]},
    {"id": "scrape", "name_zh": "爬虫数据采集包", "name_en": "Scraper Pack", "icon": "\U0001F577️",
     "desc_zh": "搜索、抓取、提取结构化数据，一套搞定", "match": ["scrape", "crawl", "spider", "scraping", "extract", "data-collection"]},
    {"id": "test", "name_zh": "测试调试急救箱", "name_en": "Test & Debug ER", "icon": "\U0001F9EA",
     "desc_zh": "从 TDD 到疑难杂症定位，bug 无处可藏", "match": ["test", "debug", "pytest", "jest", "qa", "playwright"]},
    {"id": "git", "name_zh": "Git 协作规范包", "name_en": "Git Workflow", "icon": "\U0001F500",
     "desc_zh": "提交信息、代码评审、CI 工作流，团队协作不拉胯", "match": ["git", "commit", "pull-request", "code-review", "ci", "changelog"]},
    {"id": "db", "name_zh": "数据库后端包", "name_en": "Database & Backend", "icon": "\U0001F5C4️",
     "desc_zh": "Postgres、Supabase、Firebase、迁移全覆盖", "match": ["database", "postgres", "supabase", "firebase", "mysql", "mongodb", "sql", "orm", "backend"]},
    {"id": "cloud", "name_zh": "云运维全家桶", "name_en": "Cloud Ops", "icon": "☁️",
     "desc_zh": "部署、诊断、扩缩容，云上一把梭", "match": ["aws", "azure", "gcp", "kubernetes", "terraform", "cloud", "deploy", "devops", "docker"]},
    {"id": "voice", "name_zh": "声音工坊", "name_en": "Voice Studio", "icon": "\U0001F399️",
     "desc_zh": "配音、转写、字幕、音频内容一站式", "match": ["tts", "speech", "voice", "audio", "transcribe", "whisper", "subtitle", "podcast"]},
    {"id": "invest", "name_zh": "投资研究助手", "name_en": "Investing Research", "icon": "\U0001F4C8",
     "desc_zh": "A 股、美股、加密、回测，数据说话", "match": ["stock", "trading", "finance", "crypto", "backtest", "invest", "portfolio", "market"]},
    {"id": "legacy", "name_zh": "老项目焕新包", "name_en": "Legacy Revival", "icon": "\U0001F6E0️",
     "desc_zh": "架构梳理、深度追问、设计升级，旧码焕新", "match": ["refactor", "legacy", "migration", "modernize", "codebase", "cleanup", "architecture"]},
    {"id": "ads", "name_zh": "Meta / Google 广告投放", "name_en": "Paid Ads", "icon": "\U0001F4E3",
     "desc_zh": "投放、诊断、素材、报表，广告主一条龙", "match": ["advertis", "marketing", "google-ads", "meta-ads", "facebook-ads", "ppc", "adwords", "campaign", "seo", "ad-copy"]},
    {"id": "analysis", "name_zh": "数据分析工作台", "name_en": "Data Analysis", "icon": "\U0001F9EE",
     "desc_zh": "取数、清洗、可视化、报表，让数据说话", "match": ["data-analysis", "analytics", "data-science", "pandas", "dashboard", "visualization", "bigquery", "dataviz", "chart", "plot", "sql"]},
    {"id": "competitor", "name_zh": "竞品分析雷达", "name_en": "Competitor Radar", "icon": "\U0001F52D",
     "desc_zh": "对手监控、市场情报、定位拆解", "match": ["competitor", "competitive", "market-research", "intelligence", "rival", "benchmark"]},
    {"id": "email", "name_zh": "邮件营销包", "name_en": "Email Marketing", "icon": "\U0001F4E7",
     "desc_zh": "冷启邮件、自动化序列、Newsletter 一条龙", "match": ["email", "newsletter", "cold-email", "email-marketing", "mailchimp", "drip", "outreach"]},
]


def build_collections(records):
    by_stars = sorted(records, key=lambda r: r["stars"], reverse=True)
    out = []
    for c in COLLECTIONS_SEED:
        kws = c["match"]
        members = []
        for r in by_stars:
            blob = (r["name"] + " " + r["description"] + " " + " ".join(r["topics"])).lower()
            if any(k in blob for k in kws):
                members.append(r["id"])
            if len(members) >= 18:
                break
        out.append({**{k: c[k] for k in ("id", "name_zh", "name_en", "icon", "desc_zh")},
                    "count": len(members), "skills": members})
    return out


def main():
    os.makedirs(SNAPDIR, exist_ok=True)
    today = os.environ.get("BUILD_DATE") or now_utc().date().isoformat()
    print(f"[build] date={today} token={'yes' if HAS_TOKEN else 'NO (unauth)'} pages={PAGES}")

    # Fast path: recompute collections/treasure/meta from cached skills.json
    # (skips the ~3 min scrape; leaves daily.json + snapshots untouched).
    skills_path = os.path.join(DATA, "skills.json")
    if os.environ.get("USE_CACHE") == "1" and os.path.exists(skills_path):
        with open(skills_path) as f:
            records = json.load(f)
        for r in records:
            add_tier(r)
        apply_translations(records)
        records.sort(key=lambda r: r["stars"], reverse=True)
        collections = build_collections(records)
        treasure = [r["id"] for r in records[:18]]
        cats = {}
        for r in records:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        meta = {
            "updated_at": now_utc().isoformat(), "total_skills": len(records),
            "total_stars": sum(r["stars"] for r in records),
            "categories": cats, "authenticated": HAS_TOKEN,
        }
        with open(skills_path, "w") as f:
            json.dump(records, f, ensure_ascii=False)
        with open(os.path.join(DATA, "collections.json"), "w") as f:
            json.dump(collections, f, ensure_ascii=False)
        with open(os.path.join(DATA, "treasure.json"), "w") as f:
            json.dump(treasure, f, ensure_ascii=False)
        with open(os.path.join(DATA, "meta.json"), "w") as f:
            json.dump(meta, f, ensure_ascii=False)
        print(f"[build] CACHE: recomputed {len(collections)} collections from {len(records)} cached skills")
        return

    # Incremental: scrape ONLY the extra-domain queries and merge into the
    # existing skills.json (fast — no full re-scrape). Leaves daily/snapshots.
    if os.environ.get("MERGE") == "1" and os.path.exists(skills_path):
        with open(skills_path) as f:
            base = json.load(f)
        seen = {r["id"]: r for r in base}
        found = {}
        for q in EXTRA_QUERIES:
            for p in range(1, PAGES + 1):
                items = search_repos(q, p)
                if not items:
                    break
                for it in items:
                    fn = it.get("full_name")
                    if fn and (fn not in found or it.get("stargazers_count", 0) > found[fn].get("stargazers_count", 0)):
                        found[fn] = it
                time.sleep(THROTTLE)
                if len(items) < 100:
                    break
            print(f"  +query '{q}'")
            time.sleep(THROTTLE)
        added = 0
        for it in found.values():
            rec = to_record(it)
            if not is_relevant(rec):
                continue
            if rec["id"] not in seen:
                seen[rec["id"]] = rec
                added += 1
            elif rec["stars"] > seen[rec["id"]]["stars"]:
                seen[rec["id"]] = rec
        records = list(seen.values())
        for r in records:
            add_tier(r)
        apply_translations(records)
        records.sort(key=lambda r: r["stars"], reverse=True)
        collections = build_collections(records)
        treasure = [r["id"] for r in records[:18]]
        cats = {}
        for r in records:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        meta = {"updated_at": now_utc().isoformat(), "total_skills": len(records),
                "total_stars": sum(r["stars"] for r in records), "categories": cats,
                "authenticated": HAS_TOKEN}
        with open(skills_path, "w") as f:
            json.dump(records, f, ensure_ascii=False)
        with open(os.path.join(DATA, "collections.json"), "w") as f:
            json.dump(collections, f, ensure_ascii=False)
        with open(os.path.join(DATA, "treasure.json"), "w") as f:
            json.dump(treasure, f, ensure_ascii=False)
        with open(os.path.join(DATA, "meta.json"), "w") as f:
            json.dump(meta, f, ensure_ascii=False)
        print(f"[build] MERGE: +{added} new skills -> {len(records)} total")
        return

    records = discover()
    before = len(records)
    records = [r for r in records if is_relevant(r)]
    for r in records:
        add_tier(r)
    apply_translations(records)
    print(f"  relevance filter: {before} -> {len(records)} kept")
    if not records:
        print("[build] WARNING: discovery returned 0 records.", file=sys.stderr)

    # trend + new/rising relative to previous snapshot
    rising, new = compute_trend(records, today)

    records.sort(key=lambda r: r["stars"], reverse=True)

    # snapshot (minimal: id + stars) for tomorrow's diff
    snap = [{"id": r["id"], "stars": r["stars"]} for r in records]
    with open(os.path.join(SNAPDIR, f"{today}.json"), "w") as f:
        json.dump(snap, f)

    # collections + treasure
    collections = build_collections(records)
    treasure = [r["id"] for r in records[:18]]

    # daily digest
    hot = sorted(records, key=lambda r: (r["trend"], r["stars"]), reverse=True)[:12]
    daily = {
        "date": today,
        "new": [r["id"] for r in new[:12]],
        "rising": [r["id"] for r in rising[:12]],
        "hot": [r["id"] for r in hot],
        "added_count": len(new),
    }

    # category counts
    cats = {}
    for r in records:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    meta = {
        "updated_at": now_utc().isoformat(),
        "total_skills": len(records),
        "total_stars": sum(r["stars"] for r in records),
        "categories": cats,
        "authenticated": HAS_TOKEN,
    }

    with open(os.path.join(DATA, "skills.json"), "w") as f:
        json.dump(records, f, ensure_ascii=False)
    with open(os.path.join(DATA, "collections.json"), "w") as f:
        json.dump(collections, f, ensure_ascii=False)
    with open(os.path.join(DATA, "treasure.json"), "w") as f:
        json.dump(treasure, f, ensure_ascii=False)
    with open(os.path.join(DATA, "daily.json"), "w") as f:
        json.dump(daily, f, ensure_ascii=False)
    with open(os.path.join(DATA, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False)

    print(f"[build] DONE: {len(records)} skills, {meta['total_stars']:,} stars, "
          f"{len(collections)} collections, cats={len(cats)}")


if __name__ == "__main__":
    main()
