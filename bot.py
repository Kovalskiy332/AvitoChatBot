import asyncio
import os
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from db import (
    init_db,
    add_partner,
    get_partners,
    add_transaction,
    get_balance,
    get_partner_stats,
    get_history
)


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if BOT_TOKEN is None:
    raise ValueError("Не найден BOT_TOKEN в файле .env")


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я бот-бухгалтер для перепродажи техники.\n\n"
        "Команды:\n\n"
        "/add_partner Иван — добавить участника\n"
        "/partners — список участников\n\n"
        "/invest Иван 20000 стартовый вклад — добавить вложение\n"
        "/expense Иван 25000 купили iPhone 12 — добавить расход\n"
        "/income Иван 35000 продали iPhone 12 — добавить доход\n\n"
        "/balance — общий баланс\n"
        "/debts — расчёт по участникам\n"
        "/history — последние операции"
    )


@dp.message(Command("add_partner"))
async def add_partner_handler(message: Message):
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer("Пример: /add_partner Иван")
        return

    name = parts[1].strip()

    try:
        add_partner(name)
        await message.answer(f"Участник {name} добавлен.")
    except sqlite3.IntegrityError:
        await message.answer("Такой участник уже есть.")
    except Exception:
        await message.answer("Не удалось добавить участника.")


@dp.message(Command("partners"))
async def partners_handler(message: Message):
    partners = get_partners()

    if not partners:
        await message.answer("Пока нет участников.")
        return

    text = "Участники:\n\n"

    for partner_id, name in partners:
        text += f"{partner_id}. {name}\n"

    await message.answer(text)


async def transaction_handler(message: Message, transaction_type: str):
    parts = message.text.split(maxsplit=3)

    if len(parts) < 3:
        await message.answer(
            "Формат команды:\n\n"
            "/invest Иван 20000 комментарий\n"
            "/expense Иван 25000 комментарий\n"
            "/income Иван 35000 комментарий"
        )
        return

    partner_name = parts[1]

    try:
        amount = int(parts[2])
    except ValueError:
        await message.answer("Сумма должна быть числом. Например: 25000")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше нуля.")
        return

    comment = parts[3] if len(parts) > 3 else ""

    try:
        add_transaction(partner_name, transaction_type, amount, comment)
        await message.answer("Операция добавлена.")
    except ValueError:
        await message.answer("Участник не найден. Сначала добавь его через /add_partner.")
    except Exception as error:
        await message.answer(f"Ошибка: {error}")


@dp.message(Command("invest"))
async def invest_handler(message: Message):
    await transaction_handler(message, "invest")


@dp.message(Command("expense"))
async def expense_handler(message: Message):
    await transaction_handler(message, "expense")


@dp.message(Command("income"))
async def income_handler(message: Message):
    await transaction_handler(message, "income")


@dp.message(Command("balance"))
async def balance_handler(message: Message):
    balance = get_balance()

    text = (
        "Общий баланс:\n\n"
        f"Вложения: {balance['total_invest']} ₽\n"
        f"Расходы: {balance['total_expense']} ₽\n"
        f"Доходы: {balance['total_income']} ₽\n"
        f"Чистая прибыль: {balance['profit']} ₽"
    )

    await message.answer(text)


@dp.message(Command("debts"))
async def debts_handler(message: Message):
    stats = get_partner_stats()

    if not stats:
        await message.answer("Пока нет участников.")
        return

    balance = get_balance()
    partners_count = len(stats)

    if partners_count == 0:
        await message.answer("Нет участников для расчёта.")
        return

    profit_per_person = balance["profit"] / partners_count

    text = "Расчёт по участникам:\n\n"

    for name, invested, expenses_paid, income_received in stats:
        text += (
            f"{name}:\n"
            f"Вложил: {invested} ₽\n"
            f"Оплатил расходов: {expenses_paid} ₽\n"
            f"Получил доходов: {income_received} ₽\n\n"
        )

    text += (
        "Итог:\n\n"
        f"Общая прибыль: {balance['profit']} ₽\n"
        f"Количество участников: {partners_count}\n"
        f"Прибыль на человека: {profit_per_person:.2f} ₽\n\n"
        "Это базовый расчёт. Следующим шагом можно сделать точный расчёт долгов: "
        "кто кому сколько должен перевести."
    )

    await message.answer(text)


@dp.message(Command("history"))
async def history_handler(message: Message):
    rows = get_history()

    if not rows:
        await message.answer("История пока пустая.")
        return

    type_names = {
        "invest": "Вложение",
        "expense": "Расход",
        "income": "Доход"
    }

    text = "Последние операции:\n\n"

    for created_at, name, transaction_type, amount, comment in rows:
        text += (
            f"{created_at}\n"
            f"{type_names.get(transaction_type, transaction_type)} — {amount} ₽\n"
            f"Участник: {name}\n"
            f"Комментарий: {comment or '-'}\n\n"
        )

    await message.answer(text)


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())