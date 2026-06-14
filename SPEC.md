# SkillHub — 设计文档

> 目标：1:1 复刻 SkillBox（skill.aialiang.com）——一个 AI Agent 技能聚合目录站。
> 约束：单人维护、**全程免费**、尽量零运维。

## 1. 定性

SkillBox = GitHub 技能的「App Store + Product Hunt 排行榜 + 编辑精选」。
本质是**只读展示站**：没有任何功能依赖实时后端 → 用静态重建即可做到像素级 + 功能级 1:1。

## 2. 架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 运行模式 | 静态重建（非实时后端）| 只读站，零运维、零月费、不会挂 |
| 托管 | GitHub Pages | 免费、与 Actions 同仓 |
| 定时 | GitHub Actions cron（每日）| 免费额度内；自动提供 GITHUB_TOKEN |
| 爬虫 | Python 标准库 | 无 pip 依赖，Actions/本地都能跑 |
| 前端 | 纯静态 vanilla（无框架/无构建）| 自治运行最稳，单文件夹可部署 |
| 搜索 | 客户端 over JSON | 几千~几万条 includes/预建索引足够 |

## 3. 数据契约（skill 记录）

```
id, name, author, description, repo, url,
stars, forks, trend(/天), category,
topics[], official(bool), verified(bool),
language, license, avatar, pushed_at, created_at
```

生成文件：`skills.json`（全量）、`meta.json`（计数/分类）、`collections.json`、
`treasure.json`、`daily.json`、`snapshots/<date>.json`（隔日 diff 出趋势）。

## 4. 模块边界

- **scraper/build_data.py** — 发现（repo 搜索 + 关键词）→ 归类 → 打标 → 算趋势 → 写 JSON。
  token 可选；无 token 降级为非鉴权（仍真实，量少）。`USE_CACHE=1` 可跳过抓取、只重算合集（迭代用）。
- **js/i18n.js** — 品牌 / 分类标签 / UI 文案（中英）。改这里换品牌和文案。
- **js/app.js** — 数据加载、hash 路由、各视图渲染、搜索/排序/筛选、暗色/语言。
- **css/styles.css** — `:root` CSS 变量驱动浅/深色。

## 5. 已知简化（P4 再补）

- 当前按 **repo 粒度** 索引；SkillBox 是 **单个 SKILL.md 粒度**（需 code search + token，放 Actions 做）。
- "安装量" GitHub 无此指标 → 用 Fork 数代位展示，标注为 Fork。
- 趋势需快照积累（首日为 0，次日起自然出现）。
- 合集成员由关键词匹配真实数据自动填充（非人工逐条挑选）。

## 6. 验收（P1–P3 已通过）

- 4 视图渲染正常、0 console 错误、浅/深色、中英、搜索/排序/筛选、合集、本地 http 服务 200。
