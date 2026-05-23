import sqlite3


DB_NAME = "accounting.db"


def get_connection():
    # Подключаемся к базе данных SQLite
    return sqlite3.connect(DB_NAME)


def init_db():
    # Создаём таблицы, если их ещё нет
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (partner_id) REFERENCES partners(id)
        );
        """)

        conn.commit()


def add_partner(name: str):
    # Добавляем участника
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO partners (name) VALUES (?)",
            (name,)
        )
        conn.commit()


def get_partners():
    # Получаем всех участников
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, name
        FROM partners
        ORDER BY id;
        """)
        return cursor.fetchall()


def get_partner_id(name: str):
    # Ищем участника по имени
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM partners WHERE name = ?",
            (name,)
        )
        result = cursor.fetchone()

        if result is None:
            return None

        return result[0]


def add_transaction(partner_name: str, transaction_type: str, amount: int, comment: str):
    # Добавляем денежную операцию
    partner_id = get_partner_id(partner_name)

    if partner_id is None:
        raise ValueError("Участник не найден")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO transactions (partner_id, type, amount, comment)
        VALUES (?, ?, ?, ?);
        """, (partner_id, transaction_type, amount, comment))
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
    # Считаем статистику по каждому участнику
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            p.name,
            COALESCE(SUM(CASE WHEN t.type = 'invest' THEN t.amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END), 0)
        FROM partners p
        LEFT JOIN transactions t ON p.id = t.partner_id
        GROUP BY p.id, p.name
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
            p.name,
            t.type,
            t.amount,
            t.comment
        FROM transactions t
        JOIN partners p ON p.id = t.partner_id
        ORDER BY t.id DESC
        LIMIT ?;
        """, (limit,))

        return cursor.fetchall()