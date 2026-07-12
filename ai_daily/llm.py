"""DeepSeek 筛选 + 中文摘要。所有函数在无 key 或调用失败时抛 LLMUnavailable，由 main 降级处理。"""

import os
import json
import logging

import requests

log = logging.getLogger(__name__)

TIMEOUT = 180


class LLMUnavailable(Exception):
    pass


def _chat(cfg: dict, system: str, user: str) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise LLMUnavailable("DEEPSEEK_API_KEY not set")
    try:
        resp = requests.post(
            f"{cfg['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": cfg["model"],
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except LLMUnavailable:
        raise
    except Exception as e:
        raise LLMUnavailable(f"LLM call failed: {e}") from e


def _items_block(items: list[dict], fields: tuple[str, ...]) -> str:
    lines = []
    for it in items:
        parts = [f"[{it['id']}]"]
        parts += [f"{f}: {it[f]}" for f in fields if it.get(f)]
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _apply_selection(items: list[dict], selected: list[dict], keep: int) -> list[dict]:
    """按 LLM 返回的 id 顺序取原 item，附上中文摘要。"""
    by_id = {it["id"]: it for it in items}
    out = []
    for sel in selected[:keep]:
        it = by_id.get(sel.get("id"))
        if not it:
            continue
        out.append({**it, "summary": sel.get("summary", "").strip()})
    return out


SYSTEM = (
    "你是一位资深 AI 行业分析师，为一份个人中文日报做信息筛选和摘要。"
    "读者是关注 AI 技术趋势、职业方向和创业机会的开发者。"
    "摘要必须是中文、口语化、信息密度高，先说这是什么，再说为什么值得关注。"
    "严格按要求返回 JSON。"
)


def process_github(cfg: dict, items: list[dict], keep: int) -> list[dict]:
    user = f"""以下是今天 GitHub trending 的仓库列表：

{_items_block(items, ("title", "desc", "lang", "stars", "stars_today"))}

从中挑出与 AI/LLM/机器学习最相关、最值得关注的至多 {keep} 个（不相关的宁缺毋滥），按值得关注程度排序。
每个写 1-2 句中文摘要：这个项目是做什么的、为什么现在火。
返回 JSON：{{"items": [{{"id": "...", "summary": "..."}}]}}"""
    result = _chat(cfg, SYSTEM, user)
    return _apply_selection(items, result.get("items", []), keep)


def process_news(cfg: dict, items: list[dict], keep: int, seen_titles: list[str] | None = None) -> dict:
    seen_block = ""
    if seen_titles:
        recent = "\n".join(f"- {t}" for t in seen_titles[:40])
        seen_block = f"""
以下是最近几天日报里已经报道过的标题，讲同一件事的条目不要再选（除非有明显新进展）：
{recent}
"""
    user = f"""以下是过去一天多个信息源的 AI 相关新闻/文章（含 Hacker News 首页帖，可能混有非 AI 内容）：

{_items_block(items, ("title", "desc", "source"))}
{seen_block}
任务：
1. 剔除与 AI 无关的条目；同一事件多个来源报道的只保留信息量最大的一条。
2. 挑出最重要的至多 {keep} 条，按重要性排序，每条写 2-3 句中文摘要（发生了什么、意味着什么）。
3. 基于全部信息，用 2-4 条要点归纳"今日风向"：行业动向、创业/产品机会、值得注意的技术趋势。

返回 JSON：{{"trends": ["要点1", "要点2"], "items": [{{"id": "...", "summary": "..."}}]}}"""
    result = _chat(cfg, SYSTEM, user)
    return {
        "trends": [t.strip() for t in result.get("trends", []) if t.strip()],
        "items": _apply_selection(items, result.get("items", []), keep),
    }


def process_market(cfg: dict, items: list[dict], keep_links: int) -> dict:
    user = f"""以下是过去一周多个渠道抓取的 AI 相关招聘、远程岗位、外包/接单信号（中英混杂）：

{_items_block(items, ("title", "desc", "source"))}

读者不是在找具体工作，而是想了解"市场对 AI 的需求方向和演进"。请写一份中文周报：
1. skills：3-5 条要点——招聘方当前最想要的技能组合和岗位方向，观察到变化趋势的明确点出来。
2. gigs：2-4 条要点——外包/接单/远程市场在发生什么：什么类型的活多、什么背景的人抢手。样本不足的判断要说明"样本有限"。
3. highlights：从原始条目挑至多 {keep_links} 条最有代表性的，每条一句话说明它代表什么信号。

返回 JSON：{{"skills": ["..."], "gigs": ["..."], "highlights": [{{"id": "...", "summary": "..."}}]}}"""
    result = _chat(cfg, SYSTEM, user)
    return {
        "skills": [s.strip() for s in result.get("skills", []) if s.strip()],
        "gigs": [g.strip() for g in result.get("gigs", []) if g.strip()],
        "highlights": _apply_selection(items, result.get("highlights", []), keep_links),
    }


def process_products(cfg: dict, items: list[dict], keep: int) -> list[dict]:
    user = f"""以下是今天 Product Hunt 上的新产品：

{_items_block(items, ("title", "desc"))}

挑出其中的 AI 产品（不是 AI 产品的剔除），按有趣程度排序，至多保留 {keep} 个。
每个写 1-2 句中文摘要：产品解决什么问题、亮点是什么。
返回 JSON：{{"items": [{{"id": "...", "summary": "..."}}]}}"""
    result = _chat(cfg, SYSTEM, user)
    return _apply_selection(items, result.get("items", []), keep)
