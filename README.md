# SkillHub — AI 技能库 / The AI Skills Directory

一个 **SkillBox 风格** 的 AI Agent 技能聚合目录站。每天自动从 GitHub 抓取技能仓库，
计算星标 / 趋势 / 分类，展示成可搜索、可筛选、可排序的目录 + 场景合集 + 宝藏仓库 + 技能日报。

**全静态、零后端、零月费**：Python 爬虫 + GitHub Actions 每日定时 + GitHub Pages 托管，全部免费额度内。

---

## 它长什么样

| 视图 | 路由 | 内容 |
|------|------|------|
| 首页 | `#/` | Hero + 搜索 + 今日变化（新增/上升）+ 当前热点 |
| 目录 | `#/catalog` | 卡片流 + 搜索 + 排序（推荐/星标/趋势/Fork/最新）+ 筛选（已验证/官方）|
| 技能日报 | `#/daily` | 当前热点 / 上升 / 新增 |
| 场景合集 | `#/collections` | 手工策划的技能包（PPT 全家桶、自媒体引擎…）|
| 宝藏仓库 | `#/treasure` | 编辑精选 |

支持：中英切换、暗色模式、分类侧栏（带数量）、一键复制安装命令。

---

## 架构

```
GitHub 仓库 ──(每日 cron)──> scraper/build_data.py ──> data/*.json ──> 静态站 ──> GitHub Pages
                                   │
                          data/snapshots/ (历史快照，用于算趋势)
```

- **scraper/build_data.py** — Python 标准库（无需 pip）。用 GitHub repo 搜索发现技能，
  用 `GITHUB_TOKEN`（Actions 自动提供，5000 req/hr）；本地无 token 时降级为非鉴权搜索（仍返回真实数据）。
- **data/** — 生成的 JSON：`skills.json` / `meta.json` / `collections.json` / `treasure.json` /
  `daily.json` + `snapshots/<date>.json`（隔日 diff 出趋势）。
- **前端** — 纯静态 `index.html` + `css/` + `js/`，无构建步骤、无框架、无依赖。
- **.github/workflows/update.yml** — 每天跑爬虫 → 提交数据 → 部署 Pages。

---

## 本地运行

```bash
python3 scraper/build_data.py      # 抓数据（本地非鉴权，约 3 分钟）
python3 -m http.server 8099        # 起静态服务器
open http://localhost:8099
```

想本地用满速抓取：`export GITHUB_TOKEN=ghp_xxx` 再跑 scraper。

---

## 上线（免费 · GitHub Pages）

> 当前机器的 `gh` token 已过期，上线前先重新登录一次。

```bash
# 1) 重新登录 GitHub CLI（一次性）
gh auth login

# 2) 创建公开仓库并推送（在项目目录内）
cd /Users/j/skillbox-clone
git add -A && git commit -m "init: SkillHub"   # 若尚未提交
gh repo create skillhub --public --source=. --remote=origin --push

# 3) 打开仓库 Settings → Pages → Build and deployment → Source 选 "GitHub Actions"
#    （workflow 会在 push 后自动跑，几分钟后出站点）
```

站点地址：`https://<你的用户名>.github.io/skillhub/`
之后每天 03:17 UTC 自动刷新数据并重新部署，无需任何手动操作。

---

## 自定义

| 想改什么 | 改哪里 |
|----------|--------|
| 品牌名 / 副标题 | `js/i18n.js` 顶部 `BRAND` |
| 分类中英文名 | `js/i18n.js` 的 `CAT_LABELS` |
| 界面文案 | `js/i18n.js` 的 `UI` |
| 抓取范围 / 关键词 | `scraper/build_data.py` 的 `SEARCH_QUERIES` |
| 分类归类规则 | `scraper/build_data.py` 的 `CATEGORY_RULES` |
| 场景合集 | `scraper/build_data.py` 的 `COLLECTIONS_SEED` |
| 配色 / 暗色 | `css/styles.css` 顶部 `:root` 变量 |

---

## 路线图

- [x] **P1** 爬虫 + 目录站（搜索/排序/筛选/分类/暗色/中英）
- [x] **P2** GitHub Actions 每日定时 + 快照趋势 + 技能日报
- [x] **P3** 场景合集 + 宝藏仓库 + 安装命令
- [ ] **P4** 像素级对齐 SkillBox、个体 skill（SKILL.md）粒度索引、全文搜索索引、绑定域名

详见 `SPEC.md` 与 `PROGRESS.md`。
