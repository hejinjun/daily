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


def build_digest(cfg: dict, today: str) -> dict:
    limits = cfg["limits"]

    github_raw = fetchers.fetch_github_trending(limits["github_candidates"])
    hn = fetchers.fetch_hn_front_page(limits["news_candidates"] // 2)
    rss = fetchers.fetch_news_feeds(cfg["news_feeds"], cfg["site"]["news_window_hours"])
    news_raw = (hn + rss)[: limits["news_candidates"]]
    for i, it in enumerate(news_raw):
        it["id"] = f"n{i}"
    products_raw = fetchers.fetch_product_hunt(limits["products_candidates"])

    digest = {
        "date": today,
        "generated_at": dt.datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M"),
        "llm_used": True,
        "trends": [],
    }
    try:
        digest["github"] = llm.process_github(cfg["llm"], github_raw, limits["github_keep"])
        news = llm.process_news(cfg["llm"], news_raw, limits["news_keep"])
        digest["trends"] = news["trends"]
        digest["news"] = news["items"]
        digest["products"] = llm.process_products(cfg["llm"], products_raw, limits["products_keep"])
    except llm.LLMUnavailable as e:
        log.warning("LLM 不可用，降级为原始列表：%s", e)
        digest["llm_used"] = False
        digest["github"] = github_raw[: limits["github_keep"]]
        digest["news"] = news_raw[: limits["news_keep"]]
        digest["products"] = products_raw[: limits["products_keep"]]
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
