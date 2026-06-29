"""User authentication & session management (SQLite)."""
import os
import re
import sqlite3
import bcrypt
from config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "users.db")
FREE_SEARCH_LIMIT = 5
PRO_PRICE = "4.99"


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    sql = """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE,
            phone         TEXT DEFAULT '',
            email         TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            nickname      TEXT DEFAULT '',
            role          TEXT DEFAULT '',
            created_at    TEXT DEFAULT (datetime('now','localtime')),
            last_login    TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS search_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            keyword    TEXT NOT NULL,
            results    TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            keyword    TEXT NOT NULL,
            html_path  TEXT,
            zip_path   TEXT,
            paper_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            keyword    TEXT NOT NULL,
            active     INTEGER DEFAULT 1,
            last_checked TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """
    db = _conn()
    db.executescript(sql)
    # Migration: add columns if missing from older DB
    for col, typ in [("is_pro", "INTEGER DEFAULT 0"), ("search_count", "INTEGER DEFAULT 0")]:
        try:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        except Exception:
            pass
    db.commit()
    db.close()


# ============================================================
# User CRUD
# ============================================================
def _hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def _check_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def _is_email(s: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', s))


def register(username: str, email: str, password: str, role: str = "") -> tuple:
    """Register: username + email + password (all required).
    Returns (success, message, user|None).
    """
    username = username.strip()
    email = email.strip()
    if not username or not email or not password:
        return False, "用户名、邮箱、密码不能为空", None
    if len(username) < 2:
        return False, "用户名至少 2 位", None
    if len(password) < 6:
        return False, "密码至少 6 位", None
    if not _is_email(email):
        return False, "邮箱格式不正确", None

    db = _conn()
    try:
        if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return False, "该用户名已被注册", None
        if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            return False, "该邮箱已被注册", None

        h = _hash_pw(password)
        db.execute(
            "INSERT INTO users (username, email, password_hash, nickname, role, is_pro, search_count) VALUES (?,?,?,?,?,0,0)",
            (username, email, h, username, role),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return True, "注册成功", dict(user)
    except Exception as e:
        return False, f"注册失败: {e}", None
    finally:
        db.close()


def login(username: str, password: str) -> tuple:
    """Login: username + password.
    Returns (success, message, user|None).
    """
    username = username.strip()
    if not username or not password:
        return False, "用户名和密码不能为空", None

    db = _conn()
    try:
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            return False, "用户名不存在", None
        if not _check_pw(password, user["password_hash"]):
            return False, "密码错误", None
        db.execute("UPDATE users SET last_login=datetime('now','localtime') WHERE id=?", (user["id"],))
        db.commit()
        return True, "登录成功", dict(user)
    except Exception as e:
        return False, f"登录失败: {e}", None
    finally:
        db.close()


def update_profile(user_id: int, nickname: str = "", role: str = "", email: str = "") -> tuple:
    """Update user profile fields."""
    db = _conn()
    try:
        if nickname:
            db.execute("UPDATE users SET nickname=? WHERE id=?", (nickname, user_id))
        if role:
            db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        if email and _is_email(email):
            existing = db.execute("SELECT id FROM users WHERE email=? AND id!=?", (email, user_id)).fetchone()
            if existing:
                return False, "该邮箱已被其他账号使用", None
            db.execute("UPDATE users SET email=? WHERE id=?", (email, user_id))
        db.commit()
        u = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return True, "已更新", dict(u)
    except Exception as e:
        return False, f"更新失败: {e}", None
    finally:
        db.close()


# ============================================================
# Search history
# ============================================================
def save_search_history(user_id: int, keyword: str, results: list):
    import json
    db = _conn()
    try:
        cnt = db.execute("SELECT COUNT(*) FROM search_history WHERE user_id=?", (user_id,)).fetchone()[0]
        if cnt >= 20:
            db.execute(
                "DELETE FROM search_history WHERE id IN (SELECT id FROM search_history WHERE user_id=? ORDER BY created_at ASC LIMIT ?)",
                (user_id, cnt - 19),
            )
        db.execute(
            "INSERT INTO search_history (user_id, keyword, results) VALUES (?,?,?)",
            (user_id, keyword, json.dumps(results, ensure_ascii=False)[:8000]),
        )
        db.commit()
    finally:
        db.close()


def get_search_history(user_id: int, limit: int = 20) -> list:
    db = _conn()
    try:
        rows = db.execute(
            "SELECT keyword, created_at FROM search_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


# ============================================================
# Reports
# ============================================================
def save_report(user_id: int, keyword: str, html_path: str, zip_path: str, paper_count: int):
    db = _conn()
    try:
        # Keep only last 10 reports
        cnt = db.execute("SELECT COUNT(*) FROM reports WHERE user_id=?", (user_id,)).fetchone()[0]
        if cnt >= 10:
            db.execute(
                "DELETE FROM reports WHERE id IN (SELECT id FROM reports WHERE user_id=? ORDER BY created_at ASC LIMIT ?)",
                (user_id, cnt - 9),
            )
        db.execute(
            "INSERT INTO reports (user_id, keyword, html_path, zip_path, paper_count) VALUES (?,?,?,?,?)",
            (user_id, keyword, html_path, zip_path, paper_count),
        )
        db.commit()
    finally:
        db.close()


def get_reports(user_id: int, limit: int = 10) -> list:
    db = _conn()
    try:
        rows = db.execute(
            "SELECT * FROM reports WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


# ============================================================
# Subscriptions
# ============================================================
def subscribe(user_id: int, keyword: str) -> tuple:
    """Subscribe to a keyword. Validates keyword is a legitimate research term (>= 3 chars, alphanumeric/Chinese)."""
    keyword = keyword.strip()
    if not keyword or len(keyword) < 3:
        return False, "订阅关键词至少 3 个字符"
    if len(keyword) > 80:
        return False, "订阅关键词不能超过 80 个字符"
    # Must contain at least some letter or Chinese char, not just symbols/numbers
    import re
    if not re.search(r'[a-zA-Z一-鿿]', keyword):
        return False, "关键词需包含字母或中文"
    db = _conn()
    try:
        u = db.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
        if not u or not u["email"]:
            return False, "请先绑定邮箱才能使用订阅功能"
        existing = db.execute(
            "SELECT id FROM subscriptions WHERE user_id=? AND keyword=?",
            (user_id, keyword),
        ).fetchone()
        if existing:
            return False, f"已订阅过「{keyword}」"
        db.execute(
            "INSERT INTO subscriptions (user_id, keyword) VALUES (?,?)",
            (user_id, keyword),
        )
        db.commit()
        return True, f"已订阅「{keyword}」，有新论文将推送到 {u['email']}"
    finally:
        db.close()


def unsubscribe(user_id: int, keyword: str) -> tuple:
    db = _conn()
    try:
        db.execute(
            "DELETE FROM subscriptions WHERE user_id=? AND keyword=?",
            (user_id, keyword.strip()),
        )
        db.commit()
        return True, f"已取消订阅「{keyword}」"
    finally:
        db.close()


def get_subscriptions(user_id: int) -> list:
    db = _conn()
    try:
        rows = db.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND active=1 ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


def get_all_active_subscriptions() -> list:
    db = _conn()
    try:
        rows = db.execute("""
            SELECT s.keyword, s.id as sub_id, u.email, u.id as user_id
            FROM subscriptions s JOIN users u ON s.user_id = u.id
            WHERE s.active=1 AND u.email IS NOT NULL AND u.email != ''
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


# ============================================================
# Pro membership
# ============================================================
def check_search_limit(user_id: int) -> tuple:
    """Check if user has remaining free searches. Returns (can_search: bool, remaining: int, is_pro: bool)."""
    db = _conn()
    try:
        u = db.execute("SELECT is_pro, search_count FROM users WHERE id=?", (user_id,)).fetchone()
        if not u: return False, 0, False
        if u["is_pro"]: return True, -1, True
        remaining = max(0, FREE_SEARCH_LIMIT - (u["search_count"] or 0))
        return remaining > 0, remaining, False
    finally:
        db.close()


def increment_search_count(user_id: int):
    db = _conn()
    try:
        db.execute("UPDATE users SET search_count=COALESCE(search_count,0)+1 WHERE id=?", (user_id,))
        db.commit()
    finally:
        db.close()


def upgrade_to_pro(user_id: int) -> dict:
    """Upgrade user to Pro. Returns updated user dict."""
    db = _conn()
    try:
        db.execute("UPDATE users SET is_pro=1 WHERE id=?", (user_id,))
        db.commit()
        u = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(u) if u else {}
    finally:
        db.close()


def activate_pro(user_id: int) -> bool:
    db = _conn()
    try:
        db.execute("UPDATE users SET is_pro=1 WHERE id=?", (user_id,))
        db.commit()
        return True
    except Exception:
        return False
    finally:
        db.close()


init_db()
