#!/usr/bin/env python3
"""Hourly watcher for Melbourne cleaning / housekeeping / care / nanny job posts (yeeyi + 华人贴).

Read-only: fetches public pages, never contacts employers.
Usage: python3 yeeyi_jobs.py [--limit N]   (--limit 0 = show all new matches)
"""
import argparse
import difflib
import math
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
DETAIL_CACHE = Path(__file__).with_name("details_cache.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
DAY = 86400
WINDOW_DAYS = 30          # by last refresh (lastpost), renewed posts count
RECENT_DAYS = 15          # group 1: 0-15 days, group 2: 15-30 days
HOME = (-37.8190, 145.1250)  # Box Hill: alerts are grouped by distance from here
NEAR_KM = 10              # "附近" group; already-sent posts here are re-alerted when renewed
MAX_KM = 25               # posts farther than this are not emailed (still shown on the map)
REALERT_DAYS = 7          # re-alert a nearby post at most once per this many days
MIN_AGE_LIMIT = 60        # exclude posts whose stated upper age limit is below this
REQUEST_DELAY = 0.5
DETAIL_VERSION = 2        # bump when fetch_detail output changes, so build_map.py re-fetches cached posts

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
MALE_ONLY_RE = re.compile(r"只招男|只要男|限男|仅限男|只限男|僅限男")
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
    # Keep the poster's layout as plain text: block ends become line breaks, list items become bullets.
    raw = re.sub(r"<br\s*/?>|</(?:p|div|h[1-6]|li|ul|ol|tr)>", "\n", raw, flags=re.I)
    raw = re.sub(r"<li[^>]*>", "• ", raw, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"<?/?p>", " ", text)  # yeeyi sometimes emits broken "<p<p>" markup
    lines = [re.sub(r"[ \t　\xa0]+", " ", line).strip() for line in text.splitlines()]
    return {
        "position": fields.get("职位名称") or "",
        "job_type": fields.get("招聘类型") or "",
        "salary": fields.get("工资待遇") or "",
        "contact": " ".join(names[:1] + contacts) or "见帖子",
        "text": "\n".join(line for line in lines if line),
        "fields": {k: v for k, v in fields.items() if v and v != "不限"},
        "v": DETAIL_VERSION,
    }


CN_DIGITS = {c: i for i, c in enumerate("零一二三四五六七八九")}


def arabic_numbers(text):
    """'五十五岁' -> '55岁', keycap emoji '2️⃣5️⃣' -> '25', so the age patterns can read them."""
    text = re.sub(r"(\d)\ufe0f?\u20e3", r"\1", text).replace("➖", "-")
    def two_digit(m):
        tens, ones = m.group(1), m.group(2)
        return str((CN_DIGITS[tens] if tens else 1) * 10 + (CN_DIGITS[ones] if ones else 0))
    return re.sub(r"([二三四五六七八九])?十([一二三四五六七八九])?", two_digit, text)


def age_limit(text):
    text = arabic_numbers(text)
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
    if MALE_ONLY_RE.search(blob):
        return "male only"
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


def distance_km(latlng):
    """Great-circle distance from HOME, or None when the post has no location."""
    if not latlng:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (*HOME, *latlng))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def area_unknown(item):
    """yeeyi fills in "Melbourne, VIC 3000" when the poster gives no suburb, so CBD distance is meaningless."""
    return bool(re.match(r"\s*melbourne\s*,?\s*(vic)?\s*(3000)?\s*$", item.get("suburb") or "", re.I))


def format_job(n, item, detail, km=None, note=""):
    ts = int(item["lastpost"])
    refreshed = time.strftime("%m-%d %H:%M", time.localtime(ts))
    posted = time.strftime("%Y-%m-%d", time.localtime(int(item["dateline"])))
    tag = f" [{', '.join(tags(item, detail))}]" if tags(item, detail) else ""
    source = f"【{item['source']}】" if item.get("source") else ""
    return (
        f"{n}. {note}{source}{item['subject'].strip()}{tag}\n"
        f"   区域: {item.get('suburb') or '-'}{f'（离Box Hill约{km:.0f}公里）' if km is not None and not area_unknown(item) else ''} | 薪资: {detail['salary'] or '面议'} | 工时: {hours_hint(item, detail)}\n"
        f"   刷新: {refreshed} (首发 {posted}) | 联系: {detail['contact']}\n"
        f"   {item_url(item)}"
    )


def item_url(item):
    return item.get("url") or BASE + item["tid"]


def load_json(path):
    return json.loads(path.read_text()) if path.exists() else {}


def _norm_title(title):
    return re.sub(r"[\W_]+", "", title.lower())


def _phones(text):
    return {re.sub(r"\D", "", p) for p in re.findall(r"04\d{2}[\s-]?\d{3}[\s-]?\d{3}", text)}


def is_duplicate(hrt_detail, yeeyi_pairs):
    """华人贴 often reposts yeeyi ads: same title, or same masked phone (041*****88) and same suburb."""
    title = _norm_title(hrt_detail["title"])
    mask = re.search(r"(04\d)\*+(\d{2})", hrt_detail["contact"])
    suburb = hrt_detail["suburb"].split(",")[0].strip().lower()
    for item, detail in yeeyi_pairs:
        if difflib.SequenceMatcher(None, title, _norm_title(item["subject"])).ratio() >= 0.8:
            return True
        if mask and suburb and suburb in (item.get("suburb") or "").lower():
            if any(p.startswith(mask.group(1)) and p.endswith(mask.group(2)) for p in _phones(detail["contact"] + detail["text"])):
                return True
    return False


def current_matches(details, now=None):
    """Every post (yeeyi + 华人贴) refreshed in the last WINDOW_DAYS that passes the filters, newest first.
    `details` is the detail-page cache; it is updated in place and should be saved by the caller."""
    import huarentie  # local module; imported here to avoid a cycle (it uses http_read/UA from this one)

    window_start = (now or time.time()) - WINDOW_DAYS * DAY
    pairs = []
    for tid, item in crawl_list(window_start).items():
        if not is_candidate(item):
            continue
        if details.get(tid, {}).get("v") != DETAIL_VERSION:
            try:
                details[tid] = fetch_detail(tid)
            except Exception as e:  # one bad post must not kill the run
                print(f"warn: detail {tid} failed: {e}", file=sys.stderr)
                continue
            time.sleep(REQUEST_DELAY)
        pairs.append(({**item, "source": "yeeyi"}, details[tid]))
    yeeyi_pairs = list(pairs)
    keep = {item["tid"] for item, _ in pairs}
    try:
        hrt_items, hrt_listed = huarentie.collect(window_start, details)
        keep |= hrt_listed
        for tid, item in hrt_items.items():
            if is_candidate(item) and not is_duplicate(details[tid], yeeyi_pairs):
                pairs.append((item, details[tid]))
    except Exception as e:  # a second source being down must not stop the yeeyi report
        print(f"warn: huarentie skipped: {e}", file=sys.stderr)
    matches = [(item, detail) for item, detail in pairs if reject_reason(item, detail) is None]
    matches.sort(key=lambda m: -int(m[0]["lastpost"]))
    for k in [k for k in details if k not in keep]:
        del details[k]
    return matches


def report_new(matches, limit=10, now=None, km_by_tid=None):
    """Print the alert (new posts plus renewed nearby ones, grouped by distance from HOME) and update state.json.

    New posts: never sent before; at most `limit`, nearest first, farther than MAX_KM skipped.
    Still hiring: nearby posts sent before, refreshed since, last sent REALERT_DAYS+ ago; at most `limit`.
    Unshown overflow stays unsent, so it comes up again next run.
    """
    now = now or time.time()
    window_start = now - WINDOW_DAYS * DAY
    state = load_json(STATE_FILE)
    reported = state.get("reported", {})  # tid -> lastpost when last sent
    sent_at = state.get("sent_at", {})    # tid -> time last sent (older entries fall back to `reported`)
    km_by_tid = km_by_tid or {}

    def group_of(item):
        km = km_by_tid.get(item["tid"])
        if area_unknown(item) or km is None:
            return 2
        return 0 if km < NEAR_KM else (1 if km <= MAX_KM else None)

    new, renewed = [], []
    for item, detail in matches:
        g, tid = group_of(item), item["tid"]
        if g is None:
            continue
        if tid not in reported:
            new.append((g, item, detail))
        elif g == 0 and int(item["lastpost"]) > reported[tid] and now - sent_at.get(tid, reported[tid]) >= REALERT_DAYS * DAY:
            renewed.append((g, item, detail))
    new.sort(key=lambda m: m[0])  # stable: keeps newest-first inside each group
    shown_new = new[:limit] if limit else new
    shown_renewed = renewed[:limit] if limit else renewed

    if not shown_new and not shown_renewed:
        print("本小时无新增职位")
    else:
        head = []
        if shown_new:
            head.append(f"墨尔本新增职位 {len(shown_new)} 条")
        if shown_renewed:
            head.append(f"Box Hill 附近仍在招 {len(shown_renewed)} 条")
        more = len(new) - len(shown_new) + len(renewed) - len(shown_renewed)
        print("，".join(head) + (f"（另有 {more} 条下次显示）" if more > 0 else ""))
        titles = [f"Box Hill 附近（{NEAR_KM}公里内）", f"其他区域（{NEAR_KM}–{MAX_KM}公里）", "区域未写明（地址只写 Melbourne 3000，看标题）"]
        n = 0
        for g, title in enumerate(titles):
            group = [m for m in shown_new if m[0] == g]
            if group:
                print(f"\n## {title}")
                for _, item, detail in group:
                    n += 1
                    print(format_job(n, item, detail, km_by_tid.get(item["tid"])))
        if shown_renewed:
            print(f"\n## Box Hill 附近·之前推送过、最近又刷新（说明还在招人）")
            for _, item, detail in shown_renewed:
                n += 1
                last = time.strftime("%m-%d", time.localtime(sent_at.get(item["tid"], reported[item["tid"]])))
                print(format_job(n, item, detail, km_by_tid.get(item["tid"]), note=f"【仍在招·上次推送{last}】"))

    for _, item, _ in shown_new + shown_renewed:
        reported[item["tid"]] = int(item["lastpost"])
        sent_at[item["tid"]] = int(now)
    # Forget posts outside the window; if one gets renewed later it counts as new again.
    keep = {k: v for k, v in reported.items() if v >= window_start}
    STATE_FILE.write_text(json.dumps({"reported": keep, "sent_at": {k: v for k, v in sent_at.items() if k in keep}}, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10, help="max jobs to show (0 = all)")
    args = ap.parse_args()
    details = load_json(DETAIL_CACHE)
    matches = current_matches(details)
    DETAIL_CACHE.write_text(json.dumps(details, ensure_ascii=False))
    report_new(matches, args.limit)


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
    assert age_limit("女性，五十岁以下，手脚麻利") == 50
    assert age_limit("女性，五十五岁以下") == 55
    assert age_limit("年龄 2️⃣5️⃣➖4️⃣0️⃣岁以内") == 40
    assert age_limit("工作十小时") is None
    assert 0 < distance_km((-37.8770, 145.1650)) < 10  # Glen Waverley ~7.5 km from Box Hill
    assert area_unknown({"suburb": "Melbourne, VIC 3000"}) and not area_unknown({"suburb": "West Melbourne, VIC 3003"})
    assert MALE_ONLY_RE.search("#墨尔本Glen Waverley诚聘园艺助工，只招男工#")
    d = {"title": "Box Hill招跟车清洁女工", "contact": "Helen 041*****88", "suburb": "Box Hill, VIC 3128"}
    assert is_duplicate(d, [({"subject": "Box Hill 招跟车清洁女工！", "suburb": "Box Hill"}, {"contact": "", "text": ""})])
    assert is_duplicate(d, [({"subject": "完全不同", "suburb": "Box Hill, VIC"}, {"contact": "电话:0412 345 688", "text": ""})])
    assert not is_duplicate(d, [({"subject": "完全不同", "suburb": "Clayton"}, {"contact": "电话:0412345688", "text": ""})])
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        main()
