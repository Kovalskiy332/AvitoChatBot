import sqlite3
from decimal import Decimal, ROUND_HALF_UP


DB_NAME = "accounting.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    # Создаём основную структуру базы данных
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            display_name TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'куплен',
            created_by_partner_id INTEGER NOT NULL,
            is_closed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            closed_at TEXT,
            FOREIGN KEY (created_by_partner_id) REFERENCES partners(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS deal_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id INTEGER NOT NULL,
            partner_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (deal_id) REFERENCES deals(id),
            FOREIGN KEY (partner_id) REFERENCES partners(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id INTEGER NOT NULL,
            from_partner_id INTEGER NOT NULL,
            to_partner_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            is_paid INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            paid_at TEXT,
            FOREIGN KEY (deal_id) REFERENCES deals(id),
            FOREIGN KEY (from_partner_id) REFERENCES partners(id),
            FOREIGN KEY (to_partner_id) REFERENCES partners(id)
        );
        """)

        conn.commit()


def money(value) -> str:
    # Красивый формат денег
    return f"{float(value):,.2f}".replace(",", " ").replace(".00", "")


def add_or_update_partner(telegram_id: int, username: str | None, first_name: str | None, last_name: str | None):
    # Добавляем или обновляем Telegram-пользователя
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

        cursor.execute("SELECT COUNT(*) FROM partners;")
        partners_count = cursor.fetchone()[0]
        is_admin = 1 if partners_count == 0 else 0

        cursor.execute("""
        INSERT INTO partners (telegram_id, username, first_name, last_name, display_name, is_admin)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_name = excluded.last_name,
            display_name = excluded.display_name;
        """, (telegram_id, username, first_name, last_name, display_name, is_admin))

        conn.commit()


def get_partner_by_telegram_id(telegram_id: int):
    # Ищем партнёра по Telegram ID
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, telegram_id, username, first_name, last_name, display_name, is_admin
        FROM partners
        WHERE telegram_id = ?;
        """, (telegram_id,))

        return cursor.fetchone()


def get_partner_by_id(partner_id: int):
    # Ищем партнёра по внутреннему ID
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, telegram_id, username, first_name, last_name, display_name, is_admin
        FROM partners
        WHERE id = ?;
        """, (partner_id,))

        return cursor.fetchone()


def get_partners():
    # Получаем всех партнёров
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, telegram_id, username, display_name, is_admin
        FROM partners
        ORDER BY id;
        """)

        return cursor.fetchall()


def create_deal(title: str, telegram_id: int):
    # Создаём новую сделку
    partner = get_partner_by_telegram_id(telegram_id)

    if partner is None:
        raise ValueError("Сначала зарегистрируйся через /join")

    partner_id = partner[0]

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO deals (title, created_by_partner_id)
        VALUES (?, ?);
        """, (title, partner_id))

        conn.commit()
        return cursor.lastrowid


def get_deal(deal_id: int):
    # Получаем сделку по ID
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            d.id,
            d.title,
            d.status,
            d.is_closed,
            d.created_at,
            d.closed_at,
            p.display_name,
            p.username
        FROM deals d
        JOIN partners p ON p.id = d.created_by_partner_id
        WHERE d.id = ?;
        """, (deal_id,))

        return cursor.fetchone()


def get_deals(only_open: bool = False):
    # Получаем список сделок
    with get_connection() as conn:
        cursor = conn.cursor()

        if only_open:
            cursor.execute("""
            SELECT id, title, status, is_closed, created_at
            FROM deals
            WHERE is_closed = 0
            ORDER BY id DESC;
            """)
        else:
            cursor.execute("""
            SELECT id, title, status, is_closed, created_at
            FROM deals
            ORDER BY id DESC
            LIMIT 30;
            """)

        return cursor.fetchall()


def update_deal_status(deal_id: int, status: str):
    # Меняем статус сделки
    deal = get_deal(deal_id)

    if deal is None:
        raise ValueError("Сделка не найдена")

    if deal[3] == 1:
        raise ValueError("Закрытую сделку нельзя менять")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        UPDATE deals
        SET status = ?
        WHERE id = ?;
        """, (status, deal_id))

        conn.commit()


def add_deal_transaction(deal_id: int, telegram_id: int, transaction_type: str, amount: int, comment: str):
    # Добавляем расход или доход в сделку
    deal = get_deal(deal_id)

    if deal is None:
        raise ValueError("Сделка не найдена")

    if deal[3] == 1:
        raise ValueError("Сделка уже закрыта")

    partner = get_partner_by_telegram_id(telegram_id)

    if partner is None:
        raise ValueError("Сначала зарегистрируйся через /join")

    partner_id = partner[0]

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO deal_transactions (deal_id, partner_id, type, amount, comment)
        VALUES (?, ?, ?, ?, ?);
        """, (deal_id, partner_id, transaction_type, amount, comment))

        conn.commit()


def get_deal_transactions(deal_id: int):
    # Получаем операции по конкретной сделке
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            dt.id,
            dt.type,
            dt.amount,
            dt.comment,
            dt.created_at,
            p.display_name,
            p.username
        FROM deal_transactions dt
        JOIN partners p ON p.id = dt.partner_id
        WHERE dt.deal_id = ?
        ORDER BY dt.id;
        """, (deal_id,))

        return cursor.fetchall()


def get_deal_totals(deal_id: int):
    # Считаем итоги по сделке
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0)
        FROM deal_transactions
        WHERE deal_id = ?;
        """, (deal_id,))

        total_expense, total_income = cursor.fetchone()
        profit = total_income - total_expense

        return {
            "expense": total_expense,
            "income": total_income,
            "profit": profit
        }


def close_deal_and_calculate_payments(deal_id: int):
    # Закрываем сделку и считаем, кто кому должен
    deal = get_deal(deal_id)

    if deal is None:
        raise ValueError("Сделка не найдена")

    if deal[3] == 1:
        raise ValueError("Сделка уже закрыта")

    partners = get_partners()

    if len(partners) == 0:
        raise ValueError("Нет партнёров")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            p.id,
            p.display_name,
            COALESCE(SUM(CASE WHEN dt.type = 'expense' THEN dt.amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dt.type = 'income' THEN dt.amount ELSE 0 END), 0)
        FROM partners p
        LEFT JOIN deal_transactions dt
            ON p.id = dt.partner_id AND dt.deal_id = ?
        GROUP BY p.id, p.display_name
        ORDER BY p.id;
        """, (deal_id,))

        rows = cursor.fetchall()

        totals = get_deal_totals(deal_id)

        total_income = Decimal(str(totals["income"]))
        total_expense = Decimal(str(totals["expense"]))
        profit = total_income - total_expense

        share = (profit / Decimal(len(partners))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        balances = []

        for partner_id, display_name, expenses_paid, income_received in rows:
            expenses_paid = Decimal(str(expenses_paid))
            income_received = Decimal(str(income_received))

            # Должен получить: свои расходы назад + долю прибыли - то, что уже получил доходами
            net = expenses_paid + share - income_received
            balances.append({
                "partner_id": partner_id,
                "display_name": display_name,
                "net": net
            })

        receivers = [
            {"partner_id": item["partner_id"], "display_name": item["display_name"], "amount": item["net"]}
            for item in balances if item["net"] > 0
        ]

        payers = [
            {"partner_id": item["partner_id"], "display_name": item["display_name"], "amount": -item["net"]}
            for item in balances if item["net"] < 0
        ]

        created_payments = []

        receiver_index = 0
        payer_index = 0

        while receiver_index < len(receivers) and payer_index < len(payers):
            receiver = receivers[receiver_index]
            payer = payers[payer_index]

            payment_amount = min(receiver["amount"], payer["amount"])
            payment_amount = payment_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if payment_amount > 0:
                cursor.execute("""
                INSERT INTO payments (deal_id, from_partner_id, to_partner_id, amount)
                VALUES (?, ?, ?, ?);
                """, (
                    deal_id,
                    payer["partner_id"],
                    receiver["partner_id"],
                    float(payment_amount)
                ))

                created_payments.append({
                    "from": payer["display_name"],
                    "to": receiver["display_name"],
                    "amount": payment_amount
                })

            receiver["amount"] -= payment_amount
            payer["amount"] -= payment_amount

            if receiver["amount"] <= Decimal("0.01"):
                receiver_index += 1

            if payer["amount"] <= Decimal("0.01"):
                payer_index += 1

        cursor.execute("""
        UPDATE deals
        SET is_closed = 1,
            status = 'закрыт',
            closed_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """, (deal_id,))

        conn.commit()

        return {
            "expense": total_expense,
            "income": total_income,
            "profit": profit,
            "share": share,
            "payments": created_payments
        }


def get_unpaid_payments():
    # Получаем неоплаченные долги
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            pay.id,
            d.id,
            d.title,
            from_p.display_name,
            from_p.username,
            to_p.display_name,
            to_p.username,
            pay.amount,
            pay.created_at
        FROM payments pay
        JOIN deals d ON d.id = pay.deal_id
        JOIN partners from_p ON from_p.id = pay.from_partner_id
        JOIN partners to_p ON to_p.id = pay.to_partner_id
        WHERE pay.is_paid = 0
        ORDER BY pay.id;
        """)

        return cursor.fetchall()


def mark_payment_paid(payment_id: int):
    # Отмечаем долг как оплаченный
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        UPDATE payments
        SET is_paid = 1,
            paid_at = CURRENT_TIMESTAMP
        WHERE id = ? AND is_paid = 0;
        """, (payment_id,))

        conn.commit()

        if cursor.rowcount == 0:
            raise ValueError("Долг не найден или уже оплачен")


def get_global_capital():
    # Считаем общий капитал по открытым сделкам
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN dt.type = 'expense' THEN dt.amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dt.type = 'income' THEN dt.amount ELSE 0 END), 0)
        FROM deal_transactions dt
        JOIN deals d ON d.id = dt.deal_id
        WHERE d.is_closed = 0;
        """)

        open_expense, open_income = cursor.fetchone()

        cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN dt.type = 'expense' THEN dt.amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dt.type = 'income' THEN dt.amount ELSE 0 END), 0)
        FROM deal_transactions dt;
        """)

        total_expense, total_income = cursor.fetchone()

        return {
            "open_expense": open_expense,
            "open_income": open_income,
            "open_frozen": open_expense - open_income,
            "total_expense": total_expense,
            "total_income": total_income,
            "total_profit": total_income - total_expense
        }


def get_report(days: int):
    # Отчёт за период
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0),
            COUNT(CASE WHEN type = 'expense' THEN 1 END),
            COUNT(CASE WHEN type = 'income' THEN 1 END)
        FROM deal_transactions
        WHERE created_at >= datetime('now', ?);
        """, (f"-{days} days",))

        expense, income, expense_count, income_count = cursor.fetchone()

        cursor.execute("""
        SELECT COUNT(*)
        FROM deals
        WHERE created_at >= datetime('now', ?);
        """, (f"-{days} days",))

        deals_created = cursor.fetchone()[0]

        cursor.execute("""
        SELECT COUNT(*)
        FROM deals
        WHERE is_closed = 1
          AND closed_at >= datetime('now', ?);
        """, (f"-{days} days",))

        deals_closed = cursor.fetchone()[0]

        return {
            "expense": expense,
            "income": income,
            "profit": income - expense,
            "expense_count": expense_count,
            "income_count": income_count,
            "deals_created": deals_created,
            "deals_closed": deals_closed
        }


def get_history(limit: int = 15):
    # Последние операции
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            dt.created_at,
            d.id,
            d.title,
            dt.type,
            dt.amount,
            dt.comment,
            p.display_name,
            p.username
        FROM deal_transactions dt
        JOIN deals d ON d.id = dt.deal_id
        JOIN partners p ON p.id = dt.partner_id
        ORDER BY dt.id DESC
        LIMIT ?;
        """, (limit,))

        return cursor.fetchall()


def get_export_data():
    # Данные для Excel-экспорта
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT id, title, status, is_closed, created_at, closed_at
        FROM deals
        ORDER BY id;
        """)
        deals = cursor.fetchall()

        cursor.execute("""
        SELECT
            dt.id,
            dt.deal_id,
            d.title,
            p.display_name,
            dt.type,
            dt.amount,
            dt.comment,
            dt.created_at
        FROM deal_transactions dt
        JOIN deals d ON d.id = dt.deal_id
        JOIN partners p ON p.id = dt.partner_id
        ORDER BY dt.id;
        """)
        transactions = cursor.fetchall()

        cursor.execute("""
        SELECT
            pay.id,
            d.title,
            from_p.display_name,
            to_p.display_name,
            pay.amount,
            pay.is_paid,
            pay.created_at,
            pay.paid_at
        FROM payments pay
        JOIN deals d ON d.id = pay.deal_id
        JOIN partners from_p ON from_p.id = pay.from_partner_id
        JOIN partners to_p ON to_p.id = pay.to_partner_id
        ORDER BY pay.id;
        """)
        payments = cursor.fetchall()

        cursor.execute("""
        SELECT id, telegram_id, username, display_name, is_admin, created_at
        FROM partners
        ORDER BY id;
        """)
        partners = cursor.fetchall()

        return {
            "deals": deals,
            "transactions": transactions,
            "payments": payments,
            "partners": partners
        }
