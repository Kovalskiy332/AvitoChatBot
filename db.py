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

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS profit_shares (
            partner_id INTEGER PRIMARY KEY,
            percent REAL NOT NULL,
            FOREIGN KEY (partner_id) REFERENCES partners(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS profit_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            common_percent REAL NOT NULL DEFAULT 0
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS common_fund (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (deal_id) REFERENCES deals(id)
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS common_contributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (partner_id) REFERENCES partners(id)
        );
        """)

        cursor.execute("""
        INSERT OR IGNORE INTO profit_settings (id, common_percent)
        VALUES (1, 0);
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
        raise ValueError("Сначала зарегистрируйся через /bb_join")

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
        raise ValueError("Сначала зарегистрируйся через /bb_join")

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


def get_profit_shares():
    # Получаем настройки распределения прибыли
    partners = get_partners()

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT common_percent FROM profit_settings WHERE id = 1;")
        row = cursor.fetchone()
        common_percent = row[0] if row else 0

        cursor.execute("""
        SELECT
            p.id,
            p.display_name,
            p.username,
            COALESCE(ps.percent, 0)
        FROM partners p
        LEFT JOIN profit_shares ps ON ps.partner_id = p.id
        ORDER BY p.id;
        """)

        rows = cursor.fetchall()

    total_partner_percent = sum(row[3] for row in rows)

    # Если доли ещё не настроены, делим 100% между партнёрами поровну
    if partners and total_partner_percent == 0 and common_percent == 0:
        equal_percent = round(100 / len(partners), 2)

        rows = [
            (partner_id, display_name, username, equal_percent)
            for partner_id, telegram_id, username, display_name, is_admin in partners
        ]

    return {
        "common_percent": common_percent,
        "partners": rows
    }


def set_profit_shares(shares: dict[int, float], common_percent: float):
    # Настраиваем проценты выплат партнёрам и процент в общий счёт
    if common_percent < 0:
        raise ValueError("Процент общего счёта не может быть меньше 0")

    partners = get_partners()
    partner_ids = [partner[0] for partner in partners]

    for partner_id in shares:
        if partner_id not in partner_ids:
            raise ValueError(f"Партнёр с ID {partner_id} не найден")

        if shares[partner_id] < 0:
            raise ValueError("Процент партнёра не может быть меньше 0")

    total_percent = common_percent + sum(shares.values())

    if round(total_percent, 2) != 100:
        raise ValueError(f"Сумма процентов должна быть 100%. Сейчас: {total_percent}%")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT OR REPLACE INTO profit_settings (id, common_percent)
        VALUES (1, ?);
        """, (common_percent,))

        cursor.execute("DELETE FROM profit_shares;")

        for partner_id, percent in shares.items():
            cursor.execute("""
            INSERT INTO profit_shares (partner_id, percent)
            VALUES (?, ?);
            """, (partner_id, percent))

        conn.commit()


def close_deal_and_calculate_payments(deal_id: int):
    # Закрываем сделку и считаем, кто кому должен, с учётом долей и общего счёта
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

        shares_data = get_profit_shares()
        common_percent = Decimal(str(shares_data["common_percent"]))

        partner_percent_map = {
            partner_id: Decimal(str(percent))
            for partner_id, display_name, username, percent in shares_data["partners"]
        }

        common_amount = Decimal("0")

        # Общий счёт пополняется только при положительной прибыли
        if profit > 0 and common_percent > 0:
            common_amount = (profit * common_percent / Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )

        partner_total_percent = sum(partner_percent_map.values())

        if partner_total_percent <= 0:
            raise ValueError("Не настроены проценты партнёров")

        balances = []

        for partner_id, display_name, expenses_paid, income_received in rows:
            expenses_paid = Decimal(str(expenses_paid))
            income_received = Decimal(str(income_received))

            partner_percent = partner_percent_map.get(partner_id, Decimal("0"))

            if profit >= 0:
                partner_profit = (profit * partner_percent / Decimal("100")).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )
            else:
                # Убыток делим между партнёрами по их долям, общий счёт не трогаем
                partner_profit = (profit * partner_percent / partner_total_percent).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP
                )

            # Должен получить: свои расходы назад + доля прибыли - то, что уже получил доходом
            net = expenses_paid + partner_profit - income_received

            balances.append({
                "partner_id": partner_id,
                "display_name": display_name,
                "net": net,
                "partner_profit": partner_profit,
                "percent": partner_percent
            })

        receivers = [
            {
                "partner_id": item["partner_id"],
                "display_name": item["display_name"],
                "amount": item["net"]
            }
            for item in balances if item["net"] > 0
        ]

        payers = [
            {
                "partner_id": item["partner_id"],
                "display_name": item["display_name"],
                "amount": -item["net"]
            }
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

        if common_amount > 0:
            cursor.execute("""
            INSERT INTO common_fund (deal_id, amount, comment)
            VALUES (?, ?, ?);
            """, (
                deal_id,
                float(common_amount),
                "Доля прибыли в общий счёт"
            ))

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
            "common_percent": common_percent,
            "common_amount": common_amount,
            "partner_profits": balances,
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


def get_common_fund_total():
    # Считаем общий бюджет: проценты со сделок + ручные пополнения
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM common_fund;
        """)
        deal_common_total = cursor.fetchone()[0]

        cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM common_contributions;
        """)
        manual_total = cursor.fetchone()[0]

        return {
            "deal_common_total": deal_common_total,
            "manual_total": manual_total,
            "total": deal_common_total + manual_total
        }


def add_common_contribution(telegram_id: int, amount: float, comment: str):
    # Партнёр вручную вносит деньги в общий бюджет
    partner = get_partner_by_telegram_id(telegram_id)

    if partner is None:
        raise ValueError("Сначала зарегистрируйся через /bb_join")

    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")

    partner_id = partner[0]

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO common_contributions (partner_id, amount, comment)
        VALUES (?, ?, ?);
        """, (partner_id, amount, comment))

        conn.commit()


def get_common_contributions(limit: int = 15):
    # История ручных пополнений общего бюджета
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            cc.id,
            p.display_name,
            p.username,
            cc.amount,
            cc.comment,
            cc.created_at
        FROM common_contributions cc
        JOIN partners p ON p.id = cc.partner_id
        ORDER BY cc.id DESC
        LIMIT ?;
        """, (limit,))

        return cursor.fetchall()


def get_global_capital():
    # Считаем общий капитал по открытым сделкам
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN dt.type = 'expense' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dt.type = 'income' THEN amount ELSE 0 END), 0)
        FROM deal_transactions dt
        JOIN deals d ON d.id = dt.deal_id
        WHERE d.is_closed = 0;
        """)

        open_expense, open_income = cursor.fetchone()

        cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN dt.type = 'expense' THEN amount ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN dt.type = 'income' THEN amount ELSE 0 END), 0)
        FROM deal_transactions dt;
        """)

        total_expense, total_income = cursor.fetchone()

        common_data = get_common_fund_total()

        return {
            "open_expense": open_expense,
            "open_income": open_income,
            "open_frozen": open_expense - open_income,
            "total_expense": total_expense,
            "total_income": total_income,
            "total_profit": total_income - total_expense,
            "common_total": common_data["total"]
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

        cursor.execute("""
        SELECT id, deal_id, amount, comment, created_at
        FROM common_fund
        ORDER BY id;
        """)
        common_fund = cursor.fetchall()

        cursor.execute("""
        SELECT
            cc.id,
            p.display_name,
            cc.amount,
            cc.comment,
            cc.created_at
        FROM common_contributions cc
        JOIN partners p ON p.id = cc.partner_id
        ORDER BY cc.id;
        """)
        common_contributions = cursor.fetchall()

        return {
            "deals": deals,
            "transactions": transactions,
            "payments": payments,
            "partners": partners,
            "common_fund": common_fund,
            "common_contributions": common_contributions
        }


def clear_test_data():
    # Удаляем сделки, операции и долги, но оставляем партнёров и настройки долей
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM payments;")
        cursor.execute("DELETE FROM deal_transactions;")
        cursor.execute("DELETE FROM deals;")
        cursor.execute("DELETE FROM common_fund;")
        cursor.execute("DELETE FROM common_contributions;")

        cursor.execute("""
        DELETE FROM sqlite_sequence
        WHERE name IN ('payments', 'deal_transactions', 'deals', 'common_fund', 'common_contributions');
        """)

        conn.commit()


def reset_all_data():
    # Полностью очищаем всю базу
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM payments;")
        cursor.execute("DELETE FROM deal_transactions;")
        cursor.execute("DELETE FROM deals;")
        cursor.execute("DELETE FROM common_fund;")
        cursor.execute("DELETE FROM common_contributions;")
        cursor.execute("DELETE FROM profit_shares;")
        cursor.execute("DELETE FROM profit_settings;")
        cursor.execute("DELETE FROM partners;")

        cursor.execute("""
        DELETE FROM sqlite_sequence
        WHERE name IN (
            'payments',
            'deal_transactions',
            'deals',
            'partners',
            'common_fund',
            'common_contributions'
        );
        """)

        cursor.execute("""
        INSERT OR IGNORE INTO profit_settings (id, common_percent)
        VALUES (1, 0);
        """)

        conn.commit()


def delete_deal_by_id(deal_id: int):
    # Удаляем конкретную сделку вместе с операциями и долгами
    deal = get_deal(deal_id)

    if deal is None:
        raise ValueError("Сделка не найдена")

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("DELETE FROM payments WHERE deal_id = ?;", (deal_id,))
        cursor.execute("DELETE FROM deal_transactions WHERE deal_id = ?;", (deal_id,))
        cursor.execute("DELETE FROM common_fund WHERE deal_id = ?;", (deal_id,))
        cursor.execute("DELETE FROM deals WHERE id = ?;", (deal_id,))

        conn.commit()
