"""Periodic subscription check: search each subscribed keyword, pick top 1 paper, email user.

Run via cron every 3 days:
  0 8 */3 * * cd /root/paper-assistant && python3 tools/subscription_check.py >> /tmp/sub_check.log 2>&1
"""

import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.academic_search import search_papers
from tools.paper_validator import batch_enrich
from tools.email_sender import send_email
from tools.auth import get_all_active_subscriptions, _conn


def run_check():
    subs = get_all_active_subscriptions()
    if not subs:
        print(f"[{datetime.now()}] No active subscriptions found.")
        return

    sent = 0
    for s in subs:
        keyword = s["keyword"]
        email = s["email"]
        user_id = s["user_id"]
        sub_id = s["sub_id"]

        print(f"[{datetime.now()}] Checking '{keyword}' for {email}...")

        try:
            # Search recent papers (last 6 months)
            yr = datetime.now().year
            results = search_papers(
                keyword, count=3,
                year_from=yr if datetime.now().month > 6 else yr - 1,
                authoritative_only=True,
            )
            if not results:
                print(f"  No results for '{keyword}'")
                continue

            batch_enrich(results)

            # Pick the best paper (by citation count)
            best = max(results, key=lambda r: r.get("citation_count") or 0)

            # Build email content
            title = best.get("title", "N/A")
            authors = best.get("authors", "N/A")
            year = best.get("year", "N/A")
            venue = best.get("real_venue", "") or best.get("venue", "N/A")
            cites = best.get("citation_count") or 0
            abstract = best.get("abstract", "(无)")[:300]
            arxiv_id = best.get("arxiv_id", "")
            arxiv_link = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""

            subject = f"[论文订阅] {keyword} — {title[:50]}"
            html_body = (
                f"<h2>📬 论文订阅推送</h2>"
                f"<p>你订阅的关键词 <b>「{keyword}」</b> 有新论文：</p>"
                f"<hr>"
                f"<h3>{title}</h3>"
                f"<p><b>作者:</b> {authors} | <b>年份:</b> {year} | <b>期刊:</b> {venue} | <b>引用:</b> {cites}</p>"
                f"<p>{abstract}…</p>"
                f"{f'<p><a href=\"{arxiv_link}\">📎 {arxiv_link}</a></p>' if arxiv_link else ''}"
                f"<hr>"
                f"<p><small>由论文学习路径生成器自动推送 | 每 3 天推送一篇 | "
                f"<a href=\"http://120.26.95.18:8501\">登录查看</a></small></p>"
            )

            # Send via existing email function
            # We need a minimal zip or pass None — send_email needs a zip_path
            # Workaround: send plain email without attachment
            sent_ok, msg = _send_html_only(subject, html_body, email)

            if sent_ok:
                print(f"  Sent '{title[:50]}' to {email}")
                sent += 1
                # Update last_checked
                db = _conn()
                db.execute(
                    "UPDATE subscriptions SET last_checked=datetime('now','localtime') WHERE id=?",
                    (sub_id,),
                )
                db.commit()
                db.close()
            else:
                print(f"  FAILED: {msg}")

            # Rate limit: 1 email / 3 seconds
            time.sleep(3)

        except Exception as e:
            print(f"  Error checking '{keyword}': {e}")

    print(f"[{datetime.now()}] Done. Sent {sent}/{len(subs)} emails.")


def _send_html_only(subject: str, html_body: str, recipient: str) -> tuple:
    """Send an HTML-only email (no attachment) via the configured SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from config import EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD

    if not EMAIL_PASSWORD or not EMAIL_SENDER:
        return False, "email not configured"

    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=30) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, recipient, msg.as_string())
        return True, "ok"
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    run_check()
