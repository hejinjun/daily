"""每日日报入口：抓取 → LLM 加工 → 存 data/YYYY-MM-DD.json → 生成 site/。

用法：
  python -m ai_daily.main               # 完整流程
  python -m ai_daily.main --render-only # 只从已有 data/ 重新生成页面
"""

import sys
import json
import logging
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import fetchers, llm, render

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"


def get_market_report(cfg: dict) -> dict | None:
    """"市场需求"周报：本 ISO 周已生成则直接复用，否则抓取生成。

    生成失败返回 None 且不落盘，下一天的运行会自动重试。
    """
    iso = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isocalendar()
    key = f"{iso.year}-W{iso.week:02d}"
    path = DATA_DIR / "weekly" / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())

    raw = fetchers.fetch_market_signals()
    if not raw:
        log.warning("市场信号一条都没抓到，本次跳过周报")
        return None
    try:
        report = llm.process_market(cfg["llm"], raw, cfg["limits"]["market_links"])
    except llm.LLMUnavailable as e:
        log.warning("周报 LLM 加工失败，本次跳过：%s", e)
        return None
    report["week"] = key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    log.info("weekly market report saved: %s", path)
    return report


def load_recent_selections(today: str, days: int = 3) -> tuple[set, list]:
    """最近几天日报里已选中的内容：URL 集合（硬去重用）+ 新闻标题（给 LLM 参考）。"""
    urls: set = set()
    titles: list = []
    paths = [p for p in sorted(DATA_DIR.glob("*.json"), reverse=True) if p.stem != today]
    for path in paths[:days]:
        d = json.loads(path.read_text())
        for sec in ("github", "news", "products"):
            for it in d.get(sec) or []:
                if it.get("url"):
                    urls.add(it["url"])
        titles += [it["title"] for it in d.get("news") or [] if it.get("title")]
    return urls, titles


def build_digest(cfg: dict, today: str) -> dict:
    limits = cfg["limits"]
    seen_urls, seen_titles = load_recent_selections(today)

    github_raw = fetchers.fetch_github_trending(limits["github_candidates"])
    hn = fetchers.fetch_hn_front_page(limits["news_candidates"] // 2)
    rss = fetchers.fetch_news_feeds(cfg["news_feeds"], cfg["site"]["news_window_hours"])
    news_raw = (hn + rss)[: limits["news_candidates"]]
    for i, it in enumerate(news_raw):
        it["id"] = f"n{i}"
    products_raw = fetchers.fetch_product_hunt(limits["products_candidates"])

    # 源健康度：统计的是原始抓取量，为 0 说明该源可能坏了（或当天真没内容）
    stats = [("GitHub Trending", len(github_raw)), ("Hacker News", len(hn))]
    stats += [
        (f["name"], sum(1 for it in rss if it["source"] == f["name"]))
        for f in cfg["news_feeds"]
    ]
    stats.append(("Product Hunt", len(products_raw)))

    # 跨天去重：最近几天上过日报的 repo/产品不再进候选
    github_raw = [it for it in github_raw if it["url"] not in seen_urls]
    products_raw = [it for it in products_raw if it["url"] not in seen_urls]

    digest = {
        "date": today,
        "generated_at": dt.datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M"),
        "llm_used": True,
        "trends": [],
        "source_stats": [{"name": n, "count": c} for n, c in stats],
    }
    try:
        digest["github"] = llm.process_github(cfg["llm"], github_raw, limits["github_keep"])
        news = llm.process_news(cfg["llm"], news_raw, limits["news_keep"], seen_titles)
        digest["trends"] = news["trends"]
        digest["news"] = news["items"]
        digest["products"] = llm.process_products(cfg["llm"], products_raw, limits["products_keep"])
    except llm.LLMUnavailable as e:
        log.warning("LLM 不可用，降级为原始列表：%s", e)
        digest["llm_used"] = False
        digest["github"] = github_raw[: limits["github_keep"]]
        digest["news"] = news_raw[: limits["news_keep"]]
        digest["products"] = products_raw[: limits["products_keep"]]

    digest["market"] = get_market_report(cfg)
    return digest


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())

    if "--render-only" not in sys.argv:
        today = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        digest = build_digest(cfg, today)
        DATA_DIR.mkdir(exist_ok=True)
        out = DATA_DIR / f"{today}.json"
        out.write_text(json.dumps(digest, ensure_ascii=False, indent=1))
        log.info("digest saved: %s", out)

    render.render_site(DATA_DIR, SITE_DIR, cfg["site"]["title"])
    log.info("site rendered to %s", SITE_DIR)


if __name__ == "__main__":
    main()
