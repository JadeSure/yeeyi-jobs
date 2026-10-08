export const DAY = 86400;
export const NEW_POST_DAYS = 7;
export const WINDOW_PRESETS = [1, 3, 7, 15, 30];

// Six age bands; index = color step --r0 (newest) .. --r5 (oldest) in styles.css.
export const BANDS = [
  { max: 1, label: "24小时内" },
  { max: 2, label: "昨天" },
  { max: 4, label: "2–3天前" },
  { max: 8, label: "4–7天前" },
  { max: 16, label: "8–15天前" },
  { max: 31, label: "16–30天前" },
];

export const CATEGORIES = ["清洁", "酒店客房", "保姆家政", "护理老人院"];
const CATEGORY_RULES = [
  ["护理老人院", /护理|護理|护工|老人院|养老|養老|aged|PCA|NDIS|carer|陪护|陪護/i],
  ["保姆家政", /保姆|月嫂|育儿|育兒|住家|阿姨|钟点|鐘點|家政|nanny/i],
  ["酒店客房", /酒店|客房|宾馆|賓館|motel|hotel|housekeep|house keep|民宿|airbnb/i],
];

export const nowSec = () => Date.now() / 1000;
export const ageDays = (ts) => Math.max(0, (nowSec() - ts) / DAY);

export function bandOf(ts) {
  const d = ageDays(ts);
  const i = BANDS.findIndex((b) => d < b.max);
  return i < 0 ? BANDS.length - 1 : i;
}

export function categoryOf(job) {
  const text = `${job.title} ${job.position}`;
  return CATEGORY_RULES.find(([, re]) => re.test(text))?.[0] ?? "清洁";
}

export function ageLabel(ts) {
  const d = ageDays(ts);
  if (d < 1) return `${Math.max(1, Math.round(d * 24))}小时前`;
  return `${Math.floor(d)}天前`;
}

export function fmtDate(ts) {
  const t = new Date(ts * 1000);
  const year = t.getFullYear() < new Date().getFullYear() ? `${t.getFullYear()}年` : "";
  return `${year}${t.getMonth() + 1}月${t.getDate()}日`;
}

export const shortSuburb = (s) => (s || "未注明").replace(/,?\s*VIC\s*\d{4}$/i, "").trim();

export function prepareJobs(jobs) {
  return jobs.map((j) => ({
    ...j,
    cat: categoryOf(j),
    key: j.latlng ? j.latlng.join(",") : null,
    isNew: (nowSec() - j.posted) / DAY <= NEW_POST_DAYS,
  }));
}

export function matches(job, { days, cat, prefs }) {
  return (
    (days == null || ageDays(job.refreshed) <= days) &&
    (!cat || job.cat === cat) &&
    [...prefs].every((p) => (p === "新帖" ? job.isNew : job.tags.includes(p)))
  );
}
