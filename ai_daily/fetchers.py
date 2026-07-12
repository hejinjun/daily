"""各板块的原始数据抓取。每个 fetcher 返回 item 列表，失败时返回空列表而不是抛异常。"""

import re
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


AI_RE = re.compile(
    r"\b(ai|llm|ml|gpt|rag|agents?|genai|machine.learning|deep.learning|nlp|"
    r"computer.vision|pytorch|diffusion|transformer)\b",
    re.I,
)
AI_KEYWORDS_ZH = ("大模型", "智能体", "机器学习", "深度学习", "多模态", "算法", "人工智能")


def _is_ai_related(text: str) -> bool:
    return bool(AI_RE.search(text)) or any(kw in text for kw in AI_KEYWORDS_ZH)


def fetch_market_signals() -> list[dict]:
    """周更"市场需求"板块的原始信号：远程岗位、外包/接单、HN 招聘帖。

    只做关键词粗筛控制体量，精筛交给 LLM。返回前统一编号 m0, m1...
    """
    items = []

    # RemoteOK：JSON API，第一个元素是法律声明
    try:
        for job in _get("https://remoteok.com/api").json()[1:]:
            if not isinstance(job, dict) or not job.get("position"):
                continue
            tags = ", ".join(job.get("tags", [])[:8])
            if not _is_ai_related(f"{job['position']} {tags}"):
                continue
            items.append({
                "title": f"{job['position']} @ {job.get('company', '?')}",
                "desc": tags,
                "url": job.get("url", ""),
                "source": "RemoteOK",
            })
    except Exception as e:
        log.warning("remoteok failed: %s", e)

    # We Work Remotely + V2EX 酷工作：普通 RSS/Atom
    for name, url in (
        ("WeWorkRemotely", "https://weworkremotely.com/categories/remote-programming-jobs.rss"),
        ("V2EX 酷工作", "https://www.v2ex.com/feed/jobs.xml"),
    ):
        try:
            parsed = feedparser.parse(_get(url).content)
            for entry in parsed.entries:
                desc = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)
                if not _is_ai_related(f"{entry.get('title', '')} {desc[:500]}"):
                    continue
                items.append({
                    "title": entry.get("title", "").strip(),
                    "desc": desc[:300],
                    "url": entry.get("link", ""),
                    "source": name,
                })
        except Exception as e:
            log.warning("%s failed: %s", name, e)

    # 电鸭社区：招聘&找人分类的公开 API
    try:
        data = _get("https://svc.eleduck.com/api/v1/posts?category=5&page=1").json()
        for post in data.get("posts", []):
            text = f"{post.get('title', '')} {post.get('summary', '')}"
            if not _is_ai_related(text):
                continue
            items.append({
                "title": post.get("title", "").strip(),
                "desc": (post.get("summary") or "")[:300],
                "url": f"https://eleduck.com/posts/{post['id']}",
                "source": "电鸭社区",
            })
    except Exception as e:
        log.warning("eleduck failed: %s", e)

    # HN Who is hiring：找最新月帖，取其评论（每条评论是一个岗位）
    try:
        story = _get(
            "https://hn.algolia.com/api/v1/search_by_date"
            "?query=%22who%20is%20hiring%22&tags=story,author_whoishiring&hitsPerPage=1"
        ).json()["hits"][0]
        comments = _get(
            f"https://hn.algolia.com/api/v1/search_by_date"
            f"?tags=comment,story_{story['objectID']}&hitsPerPage=100"
        ).json()["hits"]
        for c in comments:
            text = BeautifulSoup(c.get("comment_text", ""), "html.parser").get_text(" ", strip=True)
            if not text or not _is_ai_related(text):
                continue
            items.append({
                "title": text[:80],
                "desc": text[:400],
                "url": f"https://news.ycombinator.com/item?id={c['objectID']}",
                "source": f"HN {story['title'][8:]}",
            })
    except Exception as e:
        log.warning("hn who is hiring failed: %s", e)

    for i, it in enumerate(items):
        it["id"] = f"m{i}"
    log.info("market signals: %d items", len(items))
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
