import os
import re
import smtplib
import time
import zipfile
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from config import (
    EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT,
    OUTPUT_DIR,
)

# --- Constants ---
MAX_ATTACHMENT_SIZE_MB = 45  # QQ邮箱限制约 50MB，留余量
MAX_RETRIES = 3
RETRY_DELAY_SEC = 2


def _is_valid_email(email_str: str) -> bool:
    """Validate an email address format."""
    if not email_str or not isinstance(email_str, str):
        return False
    # 基础的正则匹配，覆盖常见邮箱格式
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email_str.strip()))


def create_zip(selected_papers, report_path):
    """Create a zip archive of user-selected papers and the HTML learning path report.

    Args:
        selected_papers: list of paper dicts (already filtered by user selection),
                         each must contain 'local_path'.
        report_path: path to the generated HTML report file.

    Returns:
        Absolute path to the created zip file, or None if nothing to pack.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_p = os.path.join(OUTPUT_DIR, f"learning_papers_{timestamp}.zip")
    added = 0

    with zipfile.ZipFile(zip_p, "w", zipfile.ZIP_DEFLATED) as zf:
        for pp in selected_papers:
            lp = pp.get("local_path", "")
            if lp and os.path.exists(lp):
                zf.write(lp, os.path.basename(lp))
                added += 1

        if report_path and os.path.exists(report_path):
            zf.write(report_path, os.path.basename(report_path))
            added += 1

    if added == 0:
        try:
            os.remove(zip_p)
        except OSError:
            pass
        return None

    return zip_p


def send_email(subject, body_html, zip_path, recipient=EMAIL_RECIPIENT):
    """Send an email with the learning path report and papers attached as a zip.

    Args:
        subject: email subject line.
        body_html: HTML body content.
        zip_path: path to the zip file to attach.
        recipient: recipient email address.

    Returns:
        Tuple of (success: bool, message: str).
    """
    # --- 1. 前置校验 ---
    if not EMAIL_PASSWORD:
        return False, "邮箱授权码未配置（EMAIL_PASSWORD 为空）"
    if not EMAIL_SENDER:
        return False, "发件人邮箱未配置（EMAIL_SENDER 为空）"

    if not _is_valid_email(recipient):
        return False, f"收件人邮箱格式不合法: {recipient}"
    if not _is_valid_email(EMAIL_SENDER):
        return False, f"发件人邮箱格式不合法: {EMAIL_SENDER}"

    if not zip_path or not os.path.exists(zip_path):
        return False, f"附件文件不存在: {zip_path}"

    # 附件大小检查
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    if size_mb > MAX_ATTACHMENT_SIZE_MB:
        return False, (
            f"附件过大 ({size_mb:.1f} MB)，超过限制 ({MAX_ATTACHMENT_SIZE_MB} MB)。"
            f"请减少论文数量或降低 PDF 质量。"
        )

    if not subject:
        return False, "邮件主题不能为空"

    # --- 2. 构建邮件 ---
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html or "<p>(无内容)</p>", "html", "utf-8"))

    with open(zip_path, "rb") as f:
        part = MIMEBase("application", "zip")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{os.path.basename(zip_path)}"'
        )
        msg.attach(part)

    # --- 3. 发送（含重试） ---
    last_error = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with smtplib.SMTP_SSL(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=30) as server:
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.sendmail(EMAIL_SENDER, recipient, msg.as_string())
            return True, f"邮件已成功发送至 {recipient}"
        except smtplib.SMTPAuthenticationError:
            # 认证失败不重试
            return False, "邮箱认证失败，请检查 EMAIL_SENDER 和 EMAIL_PASSWORD 是否正确"
        except smtplib.SMTPRecipientsRefused:
            return False, f"收件人地址被拒收: {recipient}"
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)
            else:
                return False, f"邮件发送失败（已重试 {MAX_RETRIES} 次）: {last_error}"

    return False, f"邮件发送失败: {last_error}"
