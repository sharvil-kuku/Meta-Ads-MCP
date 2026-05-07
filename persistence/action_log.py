import sqlite3
import os
from typing import Optional
from config import settings


def get_db_path() -> str:
    os.makedirs(settings.data_dir, exist_ok=True)
    return os.path.join(settings.data_dir, "action_log.db")


def init_db():
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            account TEXT,
            object_id TEXT NOT NULL,
            level TEXT NOT NULL,
            name TEXT,
            action TEXT NOT NULL,
            old_budget INTEGER,
            new_budget INTEGER,
            cac_at_apply INTEGER,
            spend_at_apply INTEGER,
            result TEXT,
            dry_run INTEGER DEFAULT 0
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ts ON action_log(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_oid ON action_log(object_id)")
    conn.commit()
    conn.close()


def log_action(
    timestamp: str,
    account: Optional[str],
    object_id: str,
    level: str,
    name: Optional[str],
    action: str,
    old_budget: Optional[int],
    new_budget: Optional[int],
    cac_at_apply: Optional[int],
    spend_at_apply: Optional[int],
    result: str,
    dry_run: int = 0,
):
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO action_log (
            timestamp, account, object_id, level, name, action,
            old_budget, new_budget, cac_at_apply, spend_at_apply, result, dry_run
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            timestamp,
            account,
            object_id,
            level,
            name,
            action,
            old_budget,
            new_budget,
            cac_at_apply,
            spend_at_apply,
            result,
            dry_run,
        ),
    )
    conn.commit()
    conn.close()


def query_log(
    date: str,
    account: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    sql = "SELECT * FROM action_log WHERE timestamp LIKE ?"
    params = [f"{date}%"]

    if account:
        sql += " AND account = ?"
        params.append(account)
    if action_type:
        sql += " AND action = ?"
        params.append(action_type)

    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]