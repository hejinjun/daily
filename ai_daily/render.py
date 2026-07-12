"""从 data/*.json 生成 site/ 下的全部静态页面。"""

import json
import shutil
import datetime as dt
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def render_site(data_dir: Path, site_dir: Path, site_title: str) -> None:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=True,
    )
    daily_tpl = env.get_template("daily.html.j2")
    archive_tpl = env.get_template("archive.html.j2")

    site_dir.mkdir(parents=True, exist_ok=True)
    dates = []
    for path in sorted(data_dir.glob("*.json"), reverse=True):
        digest = json.loads(path.read_text())
        date = digest["date"]
        dates.append(date)
        weekday = WEEKDAYS[dt.date.fromisoformat(date).weekday()]
        html = daily_tpl.render(site_title=site_title, weekday=weekday, **digest)
        (site_dir / f"{date}.html").write_text(html)

    if not dates:
        raise SystemExit("data/ 下没有任何日报数据，无法生成站点")

    shutil.copyfile(site_dir / f"{dates[0]}.html", site_dir / "index.html")
    (site_dir / "archive.html").write_text(
        archive_tpl.render(site_title=site_title, dates=dates)
    )
