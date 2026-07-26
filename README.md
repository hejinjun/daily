# AI 每日情报站

自用的 AI 信息聚合日报：每天清晨（北京时间）自动抓取 → DeepSeek 筛选并生成中文摘要 → 静态页面发布到 GitHub Pages，手机浏览器直接看。

## 板块（一期）

- 🧭 **今日风向** — LLM 从当天全部新闻里归纳的行业/创业趋势要点
- 📰 **AI 新闻** — Hacker News 首页 + OpenAI/DeepMind/HuggingFace 官博 + TechCrunch/The Verge AI + 机器之心/量子位，去重排序后的中文摘要
- 🔥 **GitHub 热点** — 当日 trending 中的 AI 相关项目
- 🚀 **热门 AI 产品** — Product Hunt 当日 AI 产品
- 📊 **市场需求** — 每周汇总招聘/远程岗位/外包接单信号，LLM 归纳技能与需求走向（周报，本 ISO 周内复用）

二期计划：AI 博主动态。（技能要求趋势、外包/接单机会已并入"市场需求"周报）

## 本地运行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-...       # 不设置则降级为原始列表（无摘要）
.venv/bin/python -m ai_daily.main    # 生成 data/YYYY-MM-DD.json 和 site/
open site/index.html
```

只改了模板想重新生成页面：`python -m ai_daily.main --render-only`

## 一次性部署配置

1. **DeepSeek**：在 [platform.deepseek.com](https://platform.deepseek.com) 注册、充值（月消耗约 1-2 元）、创建 API key。模型在 `config.yaml` 的 `llm.model` 配置（当前 `deepseek-v4-flash`）；DeepSeek 若下线模型名会返回 400，届时改这里即可。
2. **GitHub**：仓库设为公开（免费账户的 Pages 只支持公开仓库），开启 Pages（Source 选 GitHub Actions），添加 secret `DEEPSEEK_API_KEY`：
   ```bash
   gh api -X POST repos/<user>/<repo>/pages -f build_type=workflow
   gh secret set DEEPSEEK_API_KEY -R <user>/<repo>
   ```
3. 在 Actions 页手动触发一次 `daily-digest` 验证，成功后访问 `https://<user>.github.io/<repo>/`。
4. 手机 Safari 打开页面 → 分享 → 添加到主屏幕。

之后每天清晨自动更新（定时北京时间 6:20 触发，Actions 排队后稍晚出稿），历史日报在"历史"页可回翻（数据以 JSON 形式提交回仓库 `data/` 目录）。

## 怎么自己加博主

「👤 博主」板块就是一份精选 RSS 订阅（`config.yaml` 的 `bloggers`）。想加一个人，判断两步：

1. **他有没有 RSS/Atom feed？** 常见规律：
   - Substack / 很多 Newsletter：`域名/feed`（如 `https://xxx.substack.com/feed`）
   - 独立博客：试 `/feed`、`/rss`、`/atom.xml`、`/index.xml`、`/feed.xml`
   - YouTube 频道：`https://www.youtube.com/feeds/videos.xml?channel_id=<频道ID>`
   - Twitter/X：**没有可靠 RSS，别加**——挑那些把推文汇编成 Newsletter 的人代替
2. **feed 近期有没有内容？** 停更的人加了也是空。用下面这条命令验证（抓到几条、最新一条多久前）：
   ```bash
   .venv/bin/python - 'https://那个人的/feed' <<'PY'
   import sys, time, calendar, requests, feedparser
   r = requests.get(sys.argv[1], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
   p = feedparser.parse(r.content); now = time.time()
   print(f"HTTP {r.status_code}, {len(p.entries)} 条")
   for e in p.entries[:3]:
       ts = e.get("published_parsed") or e.get("updated_parsed")
       age = f"{(now-calendar.timegm(ts))/86400:.0f}天前" if ts else "无日期"
       print(f"  {age} · {e.get('title','')[:60]}")
   PY
   ```
   `0 条` 或最新一条几百天前 → 别加。加进 `config.yaml` 后，日报页脚的**源健康度**也会显示每个源抓到几条，`0` 一眼看出填错的 URL。

几个可调参数（都在 `config.yaml`）：`blogger_window_hours`（抓多久内的新帖，默认 7 天）、`bloggers_per_author`（每人最多几条，防高产者刷屏）、`bloggers_keep`（板块总条数上限）。注意窗口别超过去重回看的 8 天，否则同一篇会重复出现。

## 调口味

- 增删新闻源、调每个板块条数：改 `config.yaml`
- 改筛选标准和摘要风格：改 `ai_daily/llm.py` 里的提示词
- 改页面样式：改 `ai_daily/templates/`
