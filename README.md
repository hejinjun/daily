# AI 每日情报站

自用的 AI 信息聚合日报：每天早 7 点（北京时间）自动抓取 → DeepSeek 筛选并生成中文摘要 → 静态页面发布到 Cloudflare Pages，手机浏览器直接看。

## 板块（一期）

- 🧭 **今日风向** — LLM 从当天全部新闻里归纳的行业/创业趋势要点
- 📰 **AI 新闻** — Hacker News 首页 + OpenAI/DeepMind/HuggingFace 官博 + TechCrunch/The Verge AI + 机器之心/量子位，去重排序后的中文摘要
- 🔥 **GitHub 热点** — 当日 trending 中的 AI 相关项目
- 🚀 **热门 AI 产品** — Product Hunt 当日 AI 产品

二期计划：AI 博主动态、技能要求趋势、外包/接单机会。

## 本地运行

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-...       # 不设置则降级为原始列表（无摘要）
.venv/bin/python -m ai_daily.main    # 生成 data/YYYY-MM-DD.json 和 site/
open site/index.html
```

只改了模板想重新生成页面：`python -m ai_daily.main --render-only`

## 一次性部署配置

1. **DeepSeek**：在 [platform.deepseek.com](https://platform.deepseek.com) 注册、充值（月消耗约 1-2 元）、创建 API key。
2. **Cloudflare**：注册后在 dashboard 创建 API Token（模板选 "Cloudflare Pages — Edit"），记下 Account ID（dashboard 右侧栏可见）。
3. **GitHub**：把本仓库推到 GitHub（私有即可），在 Settings → Secrets and variables → Actions 添加三个 secret：
   - `DEEPSEEK_API_KEY`
   - `CLOUDFLARE_API_TOKEN`
   - `CLOUDFLARE_ACCOUNT_ID`
4. 在 Actions 页手动触发一次 `daily-digest` 验证，成功后访问 `https://ai-daily.pages.dev`（首次部署时自动创建该 Pages 项目）。
5. 手机 Safari 打开页面 → 分享 → 添加到主屏幕。

之后每天早 7 点自动更新，历史日报在"历史"页可回翻（数据以 JSON 形式提交回仓库 `data/` 目录）。

## 调口味

- 增删新闻源、调每个板块条数：改 `config.yaml`
- 改筛选标准和摘要风格：改 `ai_daily/llm.py` 里的提示词
- 改页面样式：改 `ai_daily/templates/`
