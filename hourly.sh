#!/bin/sh
# Hourly run: report new jobs (stdout), then refresh the map data and push it so Vercel redeploys.
set -u
cd "$(dirname "$0")" || exit 1

python3 yeeyi_jobs.py || exit 1

if ! python3 build_map.py >&2; then
  echo "（地图数据更新失败，下小时重试）"
  exit 0
fi
git add public/jobs.json geocode.json state.json
if ! git diff --cached --quiet; then
  git commit -q -m "data: hourly refresh" && git push -q origin main >&2 || echo "（地图数据推送失败，下小时重试）"
fi
