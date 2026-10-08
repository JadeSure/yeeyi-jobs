#!/usr/bin/env python3
"""Email the hourly report via Gmail SMTP when it lists new jobs.

Env: GMAIL_USER, GMAIL_APP_PASSWORD (a Gmail app password, not the account password),
     NOTIFY_TO (optional, comma-separated; defaults to GMAIL_USER), SITE_URL (optional).
Usage: python3 notify_email.py report.txt [--test]   (--test sends even when nothing is new)
"""
import os
import smtplib
import sys
from email.message import EmailMessage

NO_NEW_JOBS = "本小时无新增职位"


def build_message(report, sender, recipients, site_url, test):
    first_line = report.splitlines()[0] if report else NO_NEW_JOBS
    subject = first_line if first_line != NO_NEW_JOBS else "yeeyi 职位提醒"
    msg = EmailMessage()
    msg["Subject"] = ("[测试] " if test else "") + subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    footer = f"\n\n地图和全部职位：{site_url}" if site_url else ""
    msg.set_content(report + footer + "\n\n— yeeyi 墨尔本职位提醒（GitHub Actions 每小时自动发送）")
    return msg


def main():
    args = sys.argv[1:]
    test = "--test" in args
    report = open(args[0], encoding="utf-8").read().strip()
    if not test and (not report or report.startswith(NO_NEW_JOBS)):
        print("No new jobs, no email.")
        return
    sender = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not sender or not password:
        print("GMAIL_USER / GMAIL_APP_PASSWORD secrets not set, skipping email.")
        return
    recipients = [a.strip() for a in (os.environ.get("NOTIFY_TO") or sender).split(",") if a.strip()]
    msg = build_message(report, sender, recipients, os.environ.get("SITE_URL", "").strip(), test)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    print(f"Emailed {len(recipients)} recipient(s): {msg['Subject']}")


def selftest():
    report = "yeeyi 墨尔本新增职位 2 条\n\n## 近15天内刷新\n1. 招清洁"
    msg = build_message(report, "a@gmail.com", ["b@x.com", "c@x.com"], "https://example.vercel.app", False)
    assert msg["Subject"] == "yeeyi 墨尔本新增职位 2 条"
    assert msg["To"] == "b@x.com, c@x.com"
    assert "example.vercel.app" in msg.get_content()
    assert build_message(NO_NEW_JOBS, "a", ["a"], "", True)["Subject"] == "[测试] yeeyi 职位提醒"
    print("selftest ok")


if __name__ == "__main__":
    selftest() if sys.argv[1:] == ["--selftest"] else main()
