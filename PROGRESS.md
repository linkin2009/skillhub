# PROGRESS

> 自动化构建进度。每完成一块勾掉；阻塞项标 ⛔。

## P1 — 核心切片  ✅
- [x] 项目骨架 + git init（`/Users/j/skillbox-clone`，独立于 vault）
- [x] 爬虫 `scraper/build_data.py`（stdlib、token 可选、重试、相关性过滤）
- [x] 抓到真实数据：**799 技能 / 7.75M 星标 / 20 分类**
- [x] 目录页：卡片流 + 搜索 + 排序（推荐/星标/趋势/Fork/最新）+ 筛选（已验证/官方）
- [x] 分类侧栏（带数量）+ 暗色 + 中英
- [x] 本地验证（playwright 截图 4 视图，0 console error）

## P2 — 自动化引擎  ✅
- [x] `data/snapshots/` 隔日 diff 出趋势
- [x] 技能日报页（当前热点 / 上升 / 新增）
- [x] GitHub Actions `update.yml`（每日 cron + 抓取 + 提交 + 部署 Pages）

## P3 — 策划层  ✅
- [x] 场景合集（关键词→真实数据自动填充技能包）
- [x] 宝藏仓库（精选）
- [x] 一键复制安装命令

## 域扩展（按 LINKIN 领域）  ✅
- [x] 广告/营销 + 数据分析查询 + `广告营销` 分类（+559 → 1358 技能）
- [x] 竞品分析 / Shopify电商 / 邮件营销 查询 + 合集
- [x] `MERGE` 增量模式（只抓新域不重扫全库）
- [x] 合集共 21：含 Meta/Google广告投放、数据分析工作台、竞品分析雷达、邮件营销包

## P4 — 像素级打磨  ⏳（持续推进中，不停）
- [x] A/B/C 分级徽章 + ⚠️ 陈旧标记（>1 年未更新）
- [x] "+N 个同类" 去重 + "显示全部（含重复）" 开关（SkillBox 同款）
- [x] 技能详情弹窗（描述/topics/全指标/安装）
- [x] **中文翻译**：1806 条描述经 16 个 haiku agent 并行翻译 → `data/translations.json`；
      scraper `apply_translations` 持久化，ZH 模式显示中文、EN 回退英文。新增技能重跑翻译 workflow 即可补全。
- [ ] 个体 SKILL.md 粒度索引（需 code search + token，放 Actions）
- [ ] 热点 sparkline（需快照积累几天）
- [ ] 全文搜索索引（minisearch）
- [ ] 绑定域名

## ⛔ 阻塞
- **上线需 `gh auth login`**：当前机器 gh token 已过期，无法自动 push / 建仓。
  代码与部署流水线已就绪，恢复登录后一条命令即可上线（见 README「上线」）。

## 关键路径 / 命令
```
cd /Users/j/skillbox-clone
python3 scraper/build_data.py          # 抓数据
USE_CACHE=1 python3 scraper/build_data.py   # 只重算合集（快）
python3 -m http.server 8099            # 本地预览
```
