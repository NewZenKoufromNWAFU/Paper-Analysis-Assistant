"""User authentication & session management (SQLite)."""
import os
import re
import sqlite3
import hashlib
import bcrypt
from datetime import datetime
from config import BASE_DIR

DB_PATH = os.path.join(BASE_DIR, "users.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():
    """Create tables if they don't exist."""
    db = _conn()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            phone         TEXT UNIQUE,
            email         TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            nickname      TEXT DEFAULT '',
            created_at    TEXT DEFAULT (datetime('now')),
            last_login    TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS search_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            keyword    TEXT NOT NULL,
            results    TEXT,          -- JSON of paper list
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            keyword    TEXT NOT NULL,
            html_path  TEXT,
            zip_path   TEXT,
            paper_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            keyword    TEXT NOT NULL,
            active     INTEGER DEFAULT 1,
            last_checked TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    db.commit()
    db.close()


# ============================================================
# User CRUD
# ============================================================
def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _is_phone(s: str) -> bool:
    return bool(re.match(r'^1[3-9]\d{9}$', s))


def _is_email(s: str) -> bool:
    return bool(re.match(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', s))


def register(account: str, password: str, nickname: str = "") -> tuple:
    """Register a new user. account can be phone or email.

    Returns (success: bool, message: str, user: dict|None)
    """
    account = account.strip()
    if not account or not password:
        return False, "账号和密码不能为空", None
    if len(password) < 6:
        return False, "密码至少 6 位", None

    is_p = _is_phone(account)
    is_e = _is_email(account)
    if not is_p and not is_e:
        return False, "请输入有效的手机号或邮箱", None

    db = _conn()
    try:
        existing = db.execute(
            "SELECT id FROM users WHERE phone=? OR email=?", (account, account)
        ).fetchone()
        if existing:
            return False, "该账号已被注册", None

        h = _hash_pw(password)
        if is_p:
            db.execute(
                "INSERT INTO users (phone, password_hash, nickname) VALUES (?,?,?)",
                (account, h, nickname or f"用户{account[-4:]}"),
            )
        else:
            db.execute(
                "INSERT INTO users (email, password_hash, nickname) VALUES (?,?,?)",
                (account, h, nickname or account.split("@")[0]),
            )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE phone=? OR email=?", (account, account)).fetchone()
        return True, "注册成功", dict(user)
    except Exception as e:
        return False, f"注册失败: {e}", None
    finally:
        db.close()


def login(account: str, password: str) -> tuple:
    """Login with phone or email + password.

    Returns (success, message, user_dict|None)
    """
    account = account.strip()
    if not account or not password:
        return False, "账号和密码不能为空", None

    db = _conn()
    try:
        user = db.execute(
            "SELECT * FROM users WHERE phone=? OR email=?", (account, account)
        ).fetchone()
        if not user:
            return False, "账号不存在", None
        if not _check_pw(password, user["password_hash"]):
            return False, "密码错误", None
        db.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user["id"],))
        db.commit()
        return True, "登录成功", dict(user)
    except Exception as e:
        return False, f"登录失败: {e}", None
    finally:
        db.close()


def get_user(user_id: int) -> dict | None:
    db = _conn()
    try:
        u = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(u) if u else None
    finally:
        db.close()


def bind_email(user_id: int, email: str) -> tuple:
    """Bind an email to an existing user."""
    if not _is_email(email):
        return False, "邮箱格式不正确"
    db = _conn()
    try:
        existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing and existing["id"] != user_id:
            return False, "该邮箱已被其他账号绑定"
        db.execute("UPDATE users SET email=? WHERE id=?", (email, user_id))
        db.commit()
        return True, "邮箱绑定成功"
    except Exception as e:
        return False, f"绑定失败: {e}"
    finally:
        db.close()


# ============================================================
# Search history
# ============================================================
def save_search_history(user_id: int, keyword: str, results: list):
    import json
    db = _conn()
    try:
        # keep last 50 searches per user
        cnt = db.execute("SELECT COUNT(*) FROM search_history WHERE user_id=?", (user_id,)).fetchone()[0]
        if cnt >= 50:
            db.execute(
                "DELETE FROM search_history WHERE id IN (SELECT id FROM search_history WHERE user_id=? ORDER BY created_at ASC LIMIT ?)",
                (user_id, cnt - 49),
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
        db.execute(
            "INSERT INTO reports (user_id, keyword, html_path, zip_path, paper_count) VALUES (?,?,?,?,?)",
            (user_id, keyword, html_path, zip_path, paper_count),
        )
        db.commit()
    finally:
        db.close()


def get_reports(user_id: int, limit: int = 20) -> list:
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
    db = _conn()
    try:
        u = db.execute("SELECT email FROM users WHERE id=?", (user_id,)).fetchone()
        if not u or not u["email"]:
            return False, "请先绑定邮箱才能使用订阅功能"
        existing = db.execute(
            "SELECT id FROM subscriptions WHERE user_id=? AND keyword=?",
            (user_id, keyword.strip()),
        ).fetchone()
        if existing:
            return False, f"已订阅过「{keyword}」"
        db.execute(
            "INSERT INTO subscriptions (user_id, keyword) VALUES (?,?)",
            (user_id, keyword.strip()),
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
    """Return all active subscriptions with user email (for periodic checking)."""
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


# Initialize DB on import
init_db()
