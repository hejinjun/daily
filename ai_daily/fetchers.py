"""各板块的原始数据抓取。每个 fetcher 返回 item 列表，失败时返回空列表而不是抛异常。"""

import time
import calendar
import logging

import requests
import feedparser
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT = 30


def _get(url: str) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def fetch_github_trending(limit: int) -> list[dict]:
    """GitHub trending（当日、全语言）。页面结构变了会解析出 0 条，靠日志发现。"""
    try:
        html = _get("https://github.com/trending?since=daily").text
    except Exception as e:
        log.warning("github trending fetch failed: %s", e)
        return []

    items = []
    for row in BeautifulSoup(html, "html.parser").select("article.Box-row")[:limit]:
        link = row.select_one("h2 a")
        if not link or not link.get("href"):
            continue
        repo = link["href"].strip("/")
        desc_el = row.select_one("p")
        lang_el = row.select_one("[itemprop=programmingLanguage]")
        stars_el = row.select_one('a[href$="/stargazers"]')
        today_el = row.select_one("span.d-inline-block.float-sm-right")
        items.append({
            "id": f"gh{len(items)}",
            "title": repo,
            "url": f"https://github.com/{repo}",
            "desc": desc_el.get_text(strip=True) if desc_el else "",
            "lang": lang_el.get_text(strip=True) if lang_el else "",
            "stars": stars_el.get_text(strip=True) if stars_el else "",
            "stars_today": today_el.get_text(strip=True) if today_el else "",
        })
    log.info("github trending: %d items", len(items))
    return items


def fetch_hn_front_page(limit: int) -> list[dict]:
    """Hacker News 当前首页（Algolia API），AI 相关性交给 LLM 判断。"""
    try:
        data = _get(
            f"https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={limit}"
        ).json()
    except Exception as e:
        log.warning("hn fetch failed: %s", e)
        return []

    items = []
    for hit in data.get("hits", []):
        title = hit.get("title")
        if not title:
            continue
        items.append({
            "title": title,
            "url": hit.get("url")
            or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
            "desc": "",
            "source": "Hacker News",
            "lang": "en",
            "points": hit.get("points", 0),
        })
    log.info("hn front page: %d items", len(items))
    return items


def fetch_news_feeds(feeds: list[dict], window_hours: int) -> list[dict]:
    """按 config 里的 RSS 列表抓新闻，只保留窗口期内的条目。"""
    cutoff = time.time() - window_hours * 3600
    items = []
    for feed in feeds:
        try:
            raw = _get(feed["url"]).content
            parsed = feedparser.parse(raw)
        except Exception as e:
            log.warning("feed %s failed: %s", feed["name"], e)
            continue
        count = 0
        for entry in parsed.entries:
            ts = entry.get("published_parsed") or entry.get("updated_parsed")
            if ts and calendar.timegm(ts) < cutoff:
                continue
            summary = BeautifulSoup(
                entry.get("summary", ""), "html.parser"
            ).get_text(" ", strip=True)
            items.append({
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "desc": summary[:300],
                "source": feed["name"],
                "lang": feed.get("lang", "en"),
            })
            count += 1
        log.info("feed %s: %d items in window", feed["name"], count)
    return items


def fetch_product_hunt(limit: int) -> list[dict]:
    """Product Hunt 官方 Atom feed，是否 AI 产品交给 LLM 判断。"""
    try:
        raw = _get("https://www.producthunt.com/feed").content
        parsed = feedparser.parse(raw)
    except Exception as e:
        log.warning("product hunt fetch failed: %s", e)
        return []

    items = []
    for entry in parsed.entries[:limit]:
        desc = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(
            " ", strip=True
        )
        items.append({
            "id": f"ph{len(items)}",
            "title": entry.get("title", "").strip(),
            "url": entry.get("link", ""),
            "desc": desc[:300],
        })
    log.info("product hunt: %d items", len(items))
    return items
