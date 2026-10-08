#!/usr/bin/env python3
"""Hourly watcher for yeeyi Melbourne job posts (cleaning / housekeeping / care / nanny).

Read-only: fetches public pages, never contacts employers.
Usage: python3 yeeyi_jobs.py [--limit N]   (--limit 0 = show all new matches)
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

os.environ["TZ"] = "Australia/Melbourne"  # cloud runners are UTC
time.tzset()

BASE = "https://www.yeeyi.com/classified-advertisement/au/melbourne/jobs/"
LIST_API = "https://www.yeeyi.com/api/getSectionList/"
STATE_FILE = Path(__file__).with_name("state.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
DAY = 86400
WINDOW_DAYS = 30          # by last refresh (lastpost), renewed posts count
RECENT_DAYS = 15          # group 1: 0-15 days, group 2: 15-30 days
MIN_AGE_LIMIT = 60        # exclude posts whose stated upper age limit is below this
REQUEST_DELAY = 0.5

# yeeyi position_id: 31 清洁工/保洁, 57 保姆/月嫂/育儿嫂, 111 护理, 110 护士 (needs aged-care keyword)
CORE_POSITIONS = {"31", "57", "111"}
NURSE_POSITION = "110"
CATEGORY_RE = re.compile(
    r"清洁|保洁|清潔|保潔|客房|housekeep|house keep|cleaner|cleaning|护理|護理|护工|老人院|养老|養老|aged ?care"
    r"|陪护|陪護|家政|保姆|月嫂|育儿嫂|育兒嫂|钟点工|鐘點工|住家阿姨|nanny|carer|\bPCA\b|NDIS", re.I)
# Server-side keyword searches catch matching posts filed under other position ids.
SEARCH_TERMS = ["清洁", "清潔", "保洁", "客房", "housekeep", "clean", "护理", "护工", "老人院", "养老", "aged care",
                "陪护", "家政", "保姆", "月嫂", "育儿嫂", "钟点工", "阿姨", "nanny", "carer", "PCA", "NDIS"]
AGED_CARE_RE = re.compile(r"老人院|养老|養老|aged ?care", re.I)
SEEKER_RE = re.compile(r"求职|求職|求工作|找工作|求工")
# Keyword hits that are not cleaning/care jobs: courses, franchise pitches, salons, dry cleaners, office roles.
NOT_JOB_RE = re.compile(r"课程|課程|RPL|拿证|拿證|加盟|回本|美发|美髮|美容|美甲|发型|髮型|头皮|頭皮|dry ?clean|干洗|乾洗|文职|文職", re.I)
EXPIRED_RE = re.compile(r"已招到|已招满|已招滿|招满了|已满员|已過期|已过期|停止招聘|已找到|暂停招聘")
SCAM_RE = re.compile(r"押金|保证金|保證金|培训费|培訓費|报名费|報名費|中介费|中介費|服装费|工服费|入职费|先交|先付|预付|預付")
# Strip negated mentions like "不收任何费用/无需押金" before scam check.
NEGATED_FEE_RE = re.compile(r"(不收|无需|無需|不需|不用|免|没有|沒有|无|無)[^，。,.!！\n]{0,6}(押金|费|費|先交|先付)")
AGE_PATTERNS = [
    re.compile(r"(\d{2})\s*(?:周岁|岁|歲)?\s*(?:以下|以内|以內|之内|之內)"),
    re.compile(r"\d{2}\s*[-~～到至]\s*(\d{2})\s*(?:周岁|岁|歲)"),
    re.compile(r"(?:不超过|不超過|小于|小於|低于|低於|under|below)\s*(\d{2})", re.I),
]
PART_TIME_RE = re.compile(r"兼职|兼職|part[ -]?time|casual|时间自由|時間自由|时间灵活|時間靈活|灵活工时|工时灵活|时间弹性|時間彈性|自由安排", re.I)
CHINESE_FRIENDLY_RE = re.compile(r"华人|華人|中文|普通话|普通話|国语|國語|不需要英语|无需英语|不要求英语|英语不要求")
HEAVY_RE = re.compile(r"搬运|搬運|重活|体力好|體力好|能吃苦")
HOURS_RE = re.compile(r"(每周|一周|每天|周[一二三四五六日末]|早上|上午|下午|晚上|夜班|\d+\s*(?:小时|小時|hours?))[^，。,.!！\n<]{0,14}", re.I)


def http_read(req):
    for attempt in range(3):
        try:
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except OSError:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def fetch_props(url):
    page = http_read(urllib.request.Request(url, headers=UA))
    m = re.search(r'__NEXT_DATA__" type="application/json">(.*?)</script>', page)
    if not m:
        raise ValueError(f"no __NEXT_DATA__ in {url}")
    return json.loads(m.group(1))["props"]["pageProps"]


def api_list(page, extra):
    """The site's own read-only list API. Plain ?page=N pagination wraps/skips after ~10 pages,
    so we always query a narrow filter (position ids or a search keyword)."""
    body = {"fid": 161, "nextPage": page, "start": 0, "cityFilter": "1", **extra}
    req = urllib.request.Request(LIST_API, data=json.dumps(body).encode(), headers={**UA, "Content-Type": "application/json"})
    return json.loads(http_read(req)).get("threadlist") or []


def crawl_list(stop_before):
    """Return {tid: item} for matching-category posts refreshed at/after stop_before."""
    items = {}
    for extra in [{"position": ",".join(sorted(CORE_POSITIONS | {NURSE_POSITION}))}] + [{"search": k} for k in SEARCH_TERMS]:
        seen = set()
        for page in range(1, 50):
            rows = [r for r in api_list(page, extra) if "ad_id" not in r]
            fresh = [r for r in rows if r["tid"] not in seen]
            seen.update(r["tid"] for r in rows)
            for row in fresh:
                if int(row["lastpost"]) >= stop_before:
                    prev = items.get(row["tid"])
                    if not prev or int(row["lastpost"]) > int(prev["lastpost"]):
                        items[row["tid"]] = row
            time.sleep(REQUEST_DELAY)
            normal = [int(r["lastpost"]) for r in fresh if r.get("iftopad") != "1"]
            if not normal or min(normal) < stop_before:
                break
    return items


def fetch_detail(tid):
    info = fetch_props(BASE + tid)["houseRentDetails"]["threadInfo"]
    fields = dict(info.get("section_3") or [])
    contacts = [f"{k}:{v}" for k, v in (info.get("section_5") or []) if v and k != "姓名"]
    names = [v for k, v in (info.get("section_5") or []) if k == "姓名" and v]
    tel = (info.get("section_2") or {}).get("tel")
    if tel and not any(tel in c for c in contacts):
        contacts.insert(0, f"电话:{tel}")
    raw = (info.get("section_4") or {}).get("message") or ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"<?/?p>", " ", text)  # yeeyi sometimes emits broken "<p<p>" markup
    return {
        "position": fields.get("职位名称") or "",
        "job_type": fields.get("招聘类型") or "",
        "salary": fields.get("工资待遇") or "",
        "contact": " ".join(names[:1] + contacts) or "见帖子",
        "text": re.sub(r"\s+", " ", text).strip(),
    }


def age_limit(text):
    limits = [int(m.group(1)) for p in AGE_PATTERNS for m in p.finditer(text)]
    limits = [n for n in limits if 18 <= n <= 80]
    return min(limits) if limits else None


def is_candidate(item):
    """Cheap pre-filter on list data, before fetching the detail page."""
    if SEEKER_RE.search(item["subject"]) or NOT_JOB_RE.search(item["subject"]):
        return False
    return item["position_id"] in CORE_POSITIONS or item["position_id"] == NURSE_POSITION or bool(CATEGORY_RE.search(item["subject"]))


def reject_reason(item, detail):
    """Return why a post is excluded, or None if it passes."""
    blob = f"{item['subject']} {detail['position']} {detail['text']}"
    if item["position_id"] == NURSE_POSITION:
        if not AGED_CARE_RE.search(blob):
            return "not aged care"
    elif item["position_id"] not in CORE_POSITIONS and not CATEGORY_RE.search(f"{item['subject']} {detail['position']}"):
        return "category"
    if EXPIRED_RE.search(blob):
        return "expired"
    if SCAM_RE.search(NEGATED_FEE_RE.sub("", blob)):
        return "fee/deposit"
    limit = age_limit(blob)
    if limit is not None and limit < MIN_AGE_LIMIT:
        return f"age<{limit}"
    return None


def tags(item, detail):
    blob = f"{item['subject']} {detail['job_type']} {detail['text']}"
    out = []
    if PART_TIME_RE.search(blob):
        out.append("兼职/灵活")
    if CHINESE_FRIENDLY_RE.search(blob):
        out.append("华人友好")
    if HEAVY_RE.search(blob):
        out.append("体力偏重")
    return out


def hours_hint(item, detail):
    m = HOURS_RE.search(detail["text"])
    parts = [p for p in (detail["job_type"], m.group(0).strip() if m else "") if p and p != "不限"]
    return " / ".join(parts) or "未注明"


def format_job(n, item, detail):
    ts = int(item["lastpost"])
    refreshed = time.strftime("%m-%d %H:%M", time.localtime(ts))
    posted = time.strftime("%Y-%m-%d", time.localtime(int(item["dateline"])))
    tag = f" [{', '.join(tags(item, detail))}]" if tags(item, detail) else ""
    return (
        f"{n}. {item['subject'].strip()}{tag}\n"
        f"   区域: {item.get('suburb') or '-'} | 薪资: {detail['salary'] or '面议'} | 工时: {hours_hint(item, detail)}\n"
        f"   刷新: {refreshed} (首发 {posted}) | 联系: {detail['contact']}\n"
        f"   {BASE}{item['tid']}"
    )


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    # reported: {tid: lastpost when shown}; pending: overflow items not yet shown; details: detail-page cache
    return {"last_run": 0, "reported": {}, "pending": {}, "details": {}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="max jobs to show (0 = all)")
    args = ap.parse_args()

    state = load_state()
    now = time.time()
    window_start = now - WINDOW_DAYS * DAY
    # After the first run only re-scan what changed since last run (+1h margin).
    stop_before = max(window_start, state["last_run"] - 3600) if state["last_run"] else window_start
    reported = state["reported"]
    details = state["details"]

    items = crawl_list(stop_before)
    for tid, item in state.get("pending", {}).items():
        if int(item["lastpost"]) >= window_start:
            items.setdefault(tid, item)
    matches = []
    for tid, item in items.items():
        if tid in reported or not is_candidate(item):
            continue
        if tid not in details:
            try:
                details[tid] = fetch_detail(tid)
            except Exception as e:  # one bad post must not kill the run
                print(f"warn: detail {tid} failed: {e}", file=sys.stderr)
                continue
            time.sleep(REQUEST_DELAY)
        if reject_reason(item, details[tid]) is None:
            matches.append(item)

    matches.sort(key=lambda x: -int(x["lastpost"]))
    shown = matches[: args.limit] if args.limit else matches
    recent_cut = now - RECENT_DAYS * DAY
    groups = [
        (f"近{RECENT_DAYS}天内刷新", [x for x in shown if int(x["lastpost"]) >= recent_cut]),
        (f"{RECENT_DAYS}-{WINDOW_DAYS}天前刷新（可询问是否还缺人）", [x for x in shown if int(x["lastpost"]) < recent_cut]),
    ]

    if not shown:
        print("本小时无新增职位")
    else:
        print(f"yeeyi 墨尔本新增职位 {len(shown)} 条" + (f"（另有 {len(matches) - len(shown)} 条下次显示）" if len(matches) > len(shown) else ""))
        n = 0
        for title, group in groups:
            if group:
                print(f"\n## {title}")
                for item in group:
                    n += 1
                    print(format_job(n, item, details[item["tid"]]))

    reported.update({x["tid"]: int(x["lastpost"]) for x in shown})
    # Forget posts outside the window; if one gets renewed later it counts as new again.
    state["reported"] = {k: v for k, v in reported.items() if v >= window_start}
    # Overflow is kept as pending so it shows up next run even if it falls out of the incremental scan.
    state["pending"] = {x["tid"]: x for x in matches[len(shown):]}
    state["details"] = {k: v for k, v in details.items() if k in items and k not in state["reported"]}
    state["last_run"] = now
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def selftest():
    assert age_limit("希望您年龄55岁以下") == 55
    assert age_limit("年龄25-50岁") == 50
    assert age_limit("不超过45岁") == 45
    assert age_limit("60岁以下") == 60
    assert age_limit("工作4-6小时") is None
    assert SCAM_RE.search(NEGATED_FEE_RE.sub("", "需先交押金200")) is not None
    assert SCAM_RE.search(NEGATED_FEE_RE.sub("", "不收任何押金，免培训费")) is None
    assert EXPIRED_RE.search("本岗位已招满，谢谢")
    assert not is_candidate({"subject": "Forever Lengths 高级美发沙龙高薪诚聘头皮护理师", "position_id": "0"})
    assert not is_candidate({"subject": "清洁公司招聘招加盟，3-4月回本", "position_id": "31"})
    assert is_candidate({"subject": "招做客服接线，做清洁的姐姐", "position_id": "0"})
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main()
