import sqlite3


DB_NAME = "accounting.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    # Создаём таблицы для партнёров и операций
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            display_name TEXT NOT NULL
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            comment TEXT,
            chat_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (partner_id) REFERENCES partners(id)
        );
        """)

        conn.commit()


def add_or_update_partner(telegram_id: int, username: str | None, first_name: str | None, last_name: str | None):
    # Добавляем или обновляем реального Telegram-пользователя
    if first_name:
        display_name = first_name
    elif username:
        display_name = username
    else:
        display_name = f"user_{telegram_id}"

    if last_name:
        display_name = f"{display_name} {last_name}"

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO partners (telegram_id, username, first_name, last_name, display_name)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            display_name = excluded.display_name;
        """, (telegram_id, username, first_name, last_name, display_name))

        conn.commit()


def get_partner_by_telegram_id(telegram_id: int):
    # Ищем партнёра по Telegram ID
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, telegram_id, username, first_name, last_name, display_name
        FROM partners
        WHERE telegram_id = ?;
        """, (telegram_id,))

        return cursor.fetchone()


def get_partners():
    # Получаем список всех партнёров
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, telegram_id, username, display_name
        FROM partners
        ORDER BY id;
        """)

        return cursor.fetchall()


def add_transaction_by_telegram_id(
    telegram_id: int,
    transaction_type: str,
    amount: int,
    comment: str,
    chat_id: int
):
    # Добавляем операцию от имени реального Telegram-пользователя
    partner = get_partner_by_telegram_id(telegram_id)

    if partner is None:
        raise ValueError("Партнёр не зарегистрирован")

    partner_id = partner[0]

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO transactions (partner_id, type, amount, comment, chat_id)
        VALUES (?, ?, ?, ?, ?);
        """, (partner_id, transaction_type, amount, comment, chat_id))

        conn.commit()


def get_balance():
    # Считаем общий баланс
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN type = 'invest' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0)
        FROM transactions;
        """)

        total_invest, total_expense, total_income = cursor.fetchone()
        profit = total_income - total_expense

        return {
            "total_invest": total_invest,
            "total_expense": total_expense,
            "total_income": total_income,
            "profit": profit
        }


def get_partner_stats():
    # Считаем статистику по каждому партнёру
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            p.display_name,
            p.username,
            COALESCE(SUM(CASE WHEN t.type = 'invest' THEN t.amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END), 0)
        FROM partners p
        LEFT JOIN transactions t ON p.id = t.partner_id
        GROUP BY p.id, p.display_name, p.username
        ORDER BY p.id;
        """)

        return cursor.fetchall()


def get_history(limit: int = 10):
    # Получаем последние операции
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            t.created_at,
            p.display_name,
            p.username,
            t.type,
            t.amount,
            t.comment
        FROM transactions t
        JOIN partners p ON p.id = t.partner_id
        ORDER BY t.id DESC
        LIMIT ?;
        """, (limit,))

        return cursor.fetchall()
