# 待办清单

## 数据源

- [ ] **Facebook 华人群组（通过通知邮件）**
  - 做法：群组新帖通知发到 Gmail，每小时任务用 IMAP 只读读取，解析后走同样的筛选，再加到地图和提醒邮件里。
  - 待确认：通知邮件是否发到 `GMAIL_USER` 那个 Gmail（同一个就能复用应用专用密码）。
  - 限制：邮件里通常只有部分正文和链接，常常没写区域，地图上可能没有标点。
- [ ] **英文平台提醒邮件（可选）**：Seek、Indeed、Gumtree、Jora 的 job alert 邮件，做法同上。主要找华人雇主的话，优先级低。
- [ ] **今日墨尔本 / 今日澳洲**：网站有 Cloudflare 防爬，也没找到邮件提醒，暂时没有合规的自动化办法。有了邮件或 RSS 再做。

**不做**，原因记在这里，免得以后重复调查：

| 平台 | 原因 |
|---|---|
| Seek、Indeed、Gumtree、Jora、今日澳洲（直接爬取） | 有防爬验证，返回 403 |
| Airtasker | robots.txt 禁止抓取 `/tasks/` |
| 小红书 | 搜索要登录 |
| 新足迹 | 招聘版没有清洁类帖子 |
| Employment Hero | 搜索结果拿不到 |

## 求职

- [ ] **用 Mac「信息」app 发应聘短信**
  - 待定：选哪些职位；签证要不要写进短信。
  - 首次发送前，需要在 macOS 允许终端控制「信息」app。
  - 每条短信由本人确认后才发送。
- [ ] **网站加「复制应聘短信」按钮**：自动带上岗位标题，复制后直接粘贴发送。
- [ ] **办 ABN**：很多帖子要求有 ABN；有了 ABN 才能在 Airtasker 上接单。

## 维护

- [ ] 设置 GitHub 变量 `SITE_URL`（Vercel 部署好以后），提醒邮件底部会带上网站链接。
- [ ] GitHub Actions 升级 `actions/checkout`、`actions/setup-python` 到支持 Node 24 的版本（目前只是警告）。
- [ ] 删除已暂停的云端 Routine，在 https://claude.ai/code/routines 操作：
  - 「墨尔本55-60岁女性适合职位」
  - 「yeeyi 墨尔本清洁/护理职位 hourly」
- [ ] 删除已停用的本机定时任务「yeeyi 墨尔本清洁/护理职位（每小时）」，在 Claude 侧栏的 Scheduled 里操作。
