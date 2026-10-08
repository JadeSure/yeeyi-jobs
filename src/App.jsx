import { Fragment, useEffect, useMemo, useState } from "react";
import JobMap from "./JobMap.jsx";
import {
  BANDS, CATEGORIES, WINDOW_PRESETS,
  ageDays, ageLabel, bandOf, fmtDate, matches, prepareJobs, shortSuburb,
} from "./lib.js";

const PREFS = ["兼职/灵活", "华人友好", "新帖"];

function useDarkMode() {
  const query = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const mq = matchMedia(query);
    const onChange = (e) => setDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return dark;
}

function Chip({ pressed, onClick, children }) {
  return (
    <button className="chip" aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

function Timeline({ jobs, days, setDays, windowCount }) {
  const counts = useMemo(() => {
    const c = new Array(30).fill(0);
    for (const j of jobs) {
      const d = Math.floor(ageDays(j.refreshed));
      if (d < 30) c[d]++;
    }
    return c;
  }, [jobs]);
  const max = Math.max(1, ...counts);
  const marks = { 0: "今天", 6: "7天", 14: "15天", 29: "30天" };

  return (
    <section className="timeline" aria-label="每天刷新的职位数">
      <div className="tl-head">
        <div className="tl-title">
          每天刷新的职位 · 当前显示 <span className="count">{windowCount}</span> 个
        </div>
        <div className="group" role="group" aria-label="刷新时间">
          {WINDOW_PRESETS.map((d) => (
            <Chip key={d} pressed={days === d} onClick={() => setDays(d)}>
              {d === 1 ? "24小时" : `${d}天`}
            </Chip>
          ))}
        </div>
      </div>
      <div className="bars">
        {counts.map((n, d) => {
          const band = BANDS.findIndex((b) => d < b.max);
          const day = d === 0 ? "24小时内" : `${d}天前`;
          return (
            <button
              key={d}
              className={`bar b${band}${d >= days ? " out" : ""}`}
              style={{ height: n ? `${Math.max(6, Math.round((n / max) * 100))}%` : "2px" }}
              title={`${day}：${n}个职位（点击显示最近${d + 1}天）`}
              aria-label={`${day} ${n}个职位`}
              onClick={() => setDays(d + 1)}
            />
          );
        })}
      </div>
      <div className="axis">
        {counts.map((_, d) => <span key={d}>{marks[d] || ""}</span>)}
      </div>
      <div className="bands">
        {BANDS.map((b, i) => (
          <span key={b.label}><i className={`b${i}`} />{b.label}</span>
        ))}
      </div>
    </section>
  );
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  const copy = () =>
    navigator.clipboard?.writeText(text).then(() => {
      setDone(true);
      setTimeout(() => setDone(false), 1500);
    });
  return <button className="btn" onClick={copy}>{done ? "已复制" : "复制联系方式"}</button>;
}

// Extra post fields from build_map.py EXTRA_FIELDS, with short card labels.
const FIELD_LABELS = [
  ["公司名称", "公司"], ["招聘类型", "性质"], ["招聘人数", "人数"], ["签证要求", "签证"],
  ["语言要求", "语言"], ["工作经验", "经验"], ["最低学历", "学历"], ["行业类型", "行业"],
];
const LONG_DESCRIPTION = 600; // characters; only ~5% of posts are longer

function Description({ text }) {
  const [open, setOpen] = useState(false);
  const long = text.length > LONG_DESCRIPTION;
  return (
    <div className="desc">
      <p className={long && !open ? "clamped" : undefined}>{text}</p>
      {long && (
        <button className="link" onClick={() => setOpen(!open)}>{open ? "收起" : "展开全文"}</button>
      )}
    </div>
  );
}

function JobCard({ job, highlighted }) {
  const band = bandOf(job.refreshed);
  return (
    <article className={`job b${band}${band >= 4 ? " old" : ""}${highlighted ? " hl" : ""}`}>
      <div className="job-top">
        <h3>{job.title}</h3>
        <div className="age">
          <b>{ageLabel(job.refreshed)}</b>
          <small>{fmtDate(job.refreshed)}刷新</small>
        </div>
      </div>
      <div className="tags">
        {job.isNew ? <span className="tag new">新帖</span> : <span className="tag">老帖刷新</span>}
        <span className="tag">{job.cat}</span>
        {job.tags.map((t) => (
          <span key={t} className={`tag ${t === "体力偏重" ? "heavy" : "good"}`}>{t}</span>
        ))}
      </div>
      <dl className="meta">
        <dt>区域</dt><dd>{shortSuburb(job.suburb)}</dd>
        <dt>薪资</dt><dd>{job.salary}</dd>
        <dt>工时</dt><dd>{job.hours}</dd>
        <dt>首发</dt><dd>{fmtDate(job.posted)}</dd>
        <dt>联系</dt><dd><span className="contact">{job.contact}</span></dd>
        {FIELD_LABELS.filter(([key]) => job.fields?.[key]).map(([key, label]) => (
          <Fragment key={key}><dt>{label}</dt><dd>{job.fields[key]}</dd></Fragment>
        ))}
      </dl>
      {job.description && <Description text={job.description} />}
      <div className="actions">
        <a className="btn primary" href={job.url} target="_blank" rel="noopener noreferrer">查看原帖</a>
        <CopyButton text={job.contact} />
      </div>
    </article>
  );
}

function JobList({ jobs, selected }) {
  if (!jobs.length) {
    return <p className="empty">没有符合条件的职位。试试把时间放宽到 30 天，或取消偏好筛选。</p>;
  }
  const out = [];
  let current = -1;
  for (const j of jobs) {
    const band = bandOf(j.refreshed);
    if (band !== current) {
      current = band;
      const n = jobs.filter((x) => bandOf(x.refreshed) === band).length;
      out.push(
        <div key={`band-${band}`} className="band-head">
          <i className={`b${band}`} />{BANDS[band].label}<span>{n}个</span>
        </div>,
      );
    }
    out.push(<JobCard key={j.tid} job={j} highlighted={selected === j.key} />);
  }
  return <div className="list">{out}</div>;
}

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(30);
  const [cat, setCat] = useState("");
  const [prefs, setPrefs] = useState(new Set());
  const [selected, setSelected] = useState(null);
  const dark = useDarkMode();

  useEffect(() => {
    fetch("/jobs.json", { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => setData({ built: d.built, jobs: prepareJobs(d.jobs) }))
      .catch((e) => setError(e.message));
  }, []);

  const jobs = data?.jobs ?? [];
  const filters = { days, cat, prefs };
  const forTimeline = useMemo(() => jobs.filter((j) => matches(j, { ...filters, days: null })), [jobs, cat, prefs]); // eslint-disable-line
  const inWindow = useMemo(() => forTimeline.filter((j) => matches(j, filters)), [forTimeline, days]); // eslint-disable-line
  const activeSuburb = selected && inWindow.some((j) => j.key === selected) ? selected : null;
  const shown = activeSuburb ? inWindow.filter((j) => j.key === activeSuburb) : inWindow;

  const togglePref = (p) =>
    setPrefs((prev) => {
      const next = new Set(prev);
      next.has(p) ? next.delete(p) : next.add(p);
      return next;
    });

  return (
    <div className="wrap">
      <header>
        <h1>墨尔本 清洁 · 客房 · 保姆 · 护理 职位地图</h1>
        <div className="stamp">
          yeeyi 墨尔本招聘 · 近30天刷新过的帖子
          {data && <> · 数据更新于 <b>{new Date(data.built * 1000).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</b></>}
        </div>
      </header>

      {error && <p className="empty">数据加载失败（{error}），请刷新页面重试。</p>}

      <Timeline jobs={forTimeline} days={days} setDays={setDays} windowCount={inWindow.length} />

      <div className="filters">
        <div className="group" role="group" aria-label="类型">
          <span className="group-label">类型</span>
          <Chip pressed={!cat} onClick={() => setCat("")}>全部</Chip>
          {CATEGORIES.map((c) => (
            <Chip key={c} pressed={cat === c} onClick={() => setCat(c)}>{c}</Chip>
          ))}
        </div>
        <div className="group" role="group" aria-label="偏好">
          <span className="group-label">偏好</span>
          {PREFS.map((p) => (
            <Chip key={p} pressed={prefs.has(p)} onClick={() => togglePref(p)}>
              {p === "新帖" ? "只看新帖" : p}
            </Chip>
          ))}
        </div>
      </div>

      <main>
        <div className="map-pane">
          <JobMap
            jobs={inWindow}
            selected={activeSuburb}
            onSelect={setSelected}
            dark={dark}
            fitKey={`${jobs.length}|${days}|${cat}|${[...prefs].join()}`}
          />
          <p className="map-note">圆点 = 一个区，数字 = 职位数，颜色 = 该区最新一条的刷新时间（越深越新）。点圆点只看这个区。</p>
        </div>
        <section className="list-pane" aria-live="polite">
          <div className="list-head">
            <h2><span className="count">{shown.length}</span> 个职位，越新越靠前</h2>
            {activeSuburb && (
              <span className="where">
                {shortSuburb(shown[0]?.suburb)}
                <button onClick={() => setSelected(null)} aria-label="显示全部区域">✕</button>
              </span>
            )}
          </div>
          <p className="note">
            “新帖”= 首次发布在7天内；其他是老帖重新刷新，说明可能还缺人。很多帖子地址只写 “Melbourne 3000”，会堆在 CBD，实际区域看标题。
            已排除：年龄上限低于60岁、先交押金或费用、已招满。
          </p>
          {data ? <JobList jobs={shown} selected={activeSuburb} /> : !error && <p className="empty">加载中…</p>}
        </section>
      </main>
    </div>
  );
}
