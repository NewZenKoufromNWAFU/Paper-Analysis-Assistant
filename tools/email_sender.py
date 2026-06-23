
import os
import smtplib
import zipfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from config import EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, PAPERS_DIR, OUTPUT_DIR

def create_zip(papers, report_path):
    zip_p = os.path.join(OUTPUT_DIR, "learning_papers.zip")
    with zipfile.ZipFile(zip_p, "w", zipfile.ZIP_DEFLATED) as zf:
        for pp in papers:
            lp = pp.get("local_path", "")
            if lp and os.path.exists(lp):
                zf.write(lp, os.path.basename(lp))
        if os.path.exists(report_path):
            zf.write(report_path, os.path.basename(report_path))
    return zip_p

def send_email(subject, body_html, zip_path, recipient=EMAIL_RECIPIENT):
    if not EMAIL_PASSWORD:
        return False
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    with open(zip_path, "rb") as f:
        part = MIMEBase("application", "zip")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(zip_path)}")
        msg.attach(part)
    try:
        with smtplib.SMTP_SSL(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipient, msg.as_string())
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False
