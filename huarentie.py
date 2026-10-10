"""华人贴 (au.huarentie.com) Melbourne cleaning / nanny-carer boards, normalised to yeeyi-style items.

robots.txt disallows *.php and any URL with "?", so only the plain category and post pages are fetched.
Full phone numbers sit behind a .php endpoint, so contacts keep the masked number and point to the post.
"""
import html
import re
import sys
import time
import urllib.request

LIST_URL = "https://au.huarentie.com/melbourne/{board}/"
# Board -> yeeyi position id it corresponds to, so the shared filters treat it as in-category.
BOARDS = {"baojie": "31", "baomu": "57"}  # 保洁|清洁工, 保姆|护工
REQUEST_DELAY = 3
DETAIL_VERSION = 1
POST_RE = re.compile(r'href="(https?://au\.huarentie\.com/(baojie|baomu)/(\d+)\.html)"')


def _get(url):
    import yeeyi_jobs as y  # lazy: yeeyi_jobs imports this module
    return y.http_read(urllib.request.Request(url, headers=y.UA))


def _text(fragment):
    fragment = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", fragment, flags=re.I)
    fragment = re.sub(r"<li[^>]*>", "• ", fragment, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    lines = [re.sub(r"[ \t　\xa0]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_post(page):
    """Return (posted_ts, days_left, title, fields, body) from a post page."""
    posted = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})发布", page)
    days_left = re.search(r"还有\s*(?:<[^>]+>\s*)*(\d+)", page)
    title = re.search(r"<title>(.*?)(?: - 澳洲华人贴)?</title>", page, re.S)
    fields = {k.strip(): _text(v) for k, v in re.findall(r"<li[^>]*>\s*<span>([^<：]{1,8})：</span>(.*?)</li>", page, re.S)}
    body = re.search(r'class="maincon cfix">(.*?)<div class="clear">', page, re.S)
    ts = time.mktime(time.strptime(posted.group(1), "%Y-%m-%d %H:%M:%S")) if posted else 0
    return (
        int(ts),
        int(days_left.group(1)) if days_left else None,
        html.unescape(title.group(1)).strip() if title else "",
        fields,
        _text(body.group(1)) if body else "",
    )


def fetch_detail(url):
    posted, days_left, title, fields, body = parse_post(_get(url))
    contact = " ".join(v for v in (fields.get("联系人"), fields.get("联系电话", "").replace("点击查看完整号码", "")) if v)
    return {
        "posted": posted,
        "expired": days_left == 0 or "已过期" in body,
        "title": title,
        "suburb": fields.get("详细地址", ""),
        "position": fields.get("供求", ""),
        "job_type": fields.get("性质", ""),
        "salary": fields.get("薪资", ""),
        "contact": (contact + "（完整号码在原帖点“查看完整号码”）") if contact else "见原帖",
        "text": body,
        "fields": {k: v for k, v in {"公司名称": fields.get("企业名称"), "性别要求": fields.get("性别要求")}.items() if v},
        "v": DETAIL_VERSION,
    }


def collect(stop_before, details):
    """Return ({tid: item} for posts published at/after stop_before, every tid still listed).
    Fills `details` (cache) as it goes; keep the listed tids cached so old posts aren't re-fetched hourly."""
    items, listed = {}, set()
    for board, position_id in BOARDS.items():
        listing = _get(LIST_URL.format(board=board))
        time.sleep(REQUEST_DELAY)
        for url, _, post_id in dict.fromkeys(POST_RE.findall(listing)):
            tid = f"hrt-{post_id}"
            listed.add(tid)
            if details.get(tid, {}).get("v") != DETAIL_VERSION or details[tid].get("source") != "huarentie":
                try:
                    details[tid] = {**fetch_detail(url), "source": "huarentie"}
                except Exception as e:  # one bad post must not kill the run
                    print(f"warn: huarentie {post_id} failed: {e}", file=sys.stderr)
                    continue
                time.sleep(REQUEST_DELAY)
            d = details[tid]
            if d["posted"] < stop_before or d["expired"]:
                continue
            items[tid] = {
                "tid": tid, "url": url, "subject": d["title"], "suburb": d["suburb"],
                "lastpost": str(d["posted"]), "dateline": str(d["posted"]),
                "position_id": position_id, "iftopad": "0", "source": "华人贴",
            }
    return items, listed


def selftest():
    page = (
        "<title>Box Hill招跟车清洁 - 澳洲华人贴</title>2026-08-25 05:50:36发布，还有<font color=red>134</font>天过期"
        '<li style=""><span>性质：</span> 全职 </li><li class="qqbm"><span>详细地址：</span>Box Hill, VIC 3128</li>'
        '<div class="maincon cfix"><p>招跟车<br/>清洁工</p><div class="clear">'
    )
    posted, days_left, title, fields, body = parse_post(page)
    assert title == "Box Hill招跟车清洁" and days_left == 134 and posted > 0
    assert fields["性质"] == "全职" and fields["详细地址"] == "Box Hill, VIC 3128"
    assert body == "招跟车\n清洁工"
    print("huarentie selftest ok")


if __name__ == "__main__":
    selftest()
