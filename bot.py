import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from db import (
    init_db,
    add_or_update_partner,
    get_partner_by_telegram_id,
    get_partners,
    add_transaction_by_telegram_id,
    get_balance,
    get_partner_stats,
    get_history
)


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if BOT_TOKEN is None:
    raise ValueError("Не найден BOT_TOKEN в файле .env или в переменных окружения")


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def get_user_data(message: Message):
    # Получаем данные реального Telegram-пользователя
    user = message.from_user

    return {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name
    }


def format_user(display_name: str, username: str | None):
    # Красивое отображение пользователя
    if username:
        return f"{display_name} (@{username})"

    return display_name


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я бот-бухгалтер для перепродажи техники.\n\n"
        "Я работаю и в личке, и в группе.\n\n"
        "Сначала каждый партнёр должен написать:\n"
        "/join\n\n"
        "Команды:\n\n"
        "/join — зарегистрироваться как партнёр\n"
        "/me — мой профиль\n"
        "/partners — список партнёров\n\n"
        "/invest 20000 стартовый вклад — добавить вложение\n"
        "/expense 25000 купили iPhone 12 — добавить расход\n"
        "/income 35000 продали iPhone 12 — добавить доход\n\n"
        "/balance — общий баланс\n"
        "/debts — расчёт по партнёрам\n"
        "/history — последние операции"
    )


@dp.message(Command("join"))
async def join_handler(message: Message):
    user_data = get_user_data(message)

    add_or_update_partner(
        telegram_id=user_data["telegram_id"],
        username=user_data["username"],
        first_name=user_data["first_name"],
        last_name=user_data["last_name"]
    )

    username_text = f"@{user_data['username']}" if user_data["username"] else "не указан"
    first_name_text = user_data["first_name"] if user_data["first_name"] else "не указано"

    await message.answer(
        "Ты зарегистрирован как партнёр.\n\n"
        f"Имя: {first_name_text}\n"
        f"Username: {username_text}"
    )


@dp.message(Command("me"))
async def me_handler(message: Message):
    user_data = get_user_data(message)
    partner = get_partner_by_telegram_id(user_data["telegram_id"])

    if partner is None:
        await message.answer("Ты ещё не зарегистрирован. Напиши /join")
        return

    _, telegram_id, username, first_name, last_name, display_name = partner

    username_text = f"@{username}" if username else "не указан"

    await message.answer(
        "Твой профиль партнёра:\n\n"
        f"Telegram ID: {telegram_id}\n"
        f"Имя: {display_name}\n"
        f"Username: {username_text}"
    )


@dp.message(Command("partners"))
async def partners_handler(message: Message):
    partners = get_partners()

    if not partners:
        await message.answer("Пока нет партнёров. Каждый должен написать /join")
        return

    text = "Партнёры:\n\n"

    for partner_id, telegram_id, username, display_name in partners:
        text += f"{partner_id}. {format_user(display_name, username)}\n"

    await message.answer(text)


async def transaction_handler(message: Message, transaction_type: str):
    user_data = get_user_data(message)

    partner = get_partner_by_telegram_id(user_data["telegram_id"])

    if partner is None:
        await message.answer("Сначала зарегистрируйся как партнёр: /join")
        return

    parts = message.text.split(maxsplit=2)

    if len(parts) < 2:
        await message.answer(
            "Формат команды:\n\n"
            "/invest 20000 комментарий\n"
            "/expense 25000 комментарий\n"
            "/income 35000 комментарий"
        )
        return

    try:
        amount = int(parts[1])
    except ValueError:
        await message.answer("Сумма должна быть числом. Например: /expense 25000 купили iPhone 12")
        return

    if amount <= 0:
        await message.answer("Сумма должна быть больше нуля.")
        return

    comment = parts[2] if len(parts) > 2 else ""

    add_transaction_by_telegram_id(
        telegram_id=user_data["telegram_id"],
        transaction_type=transaction_type,
        amount=amount,
        comment=comment,
        chat_id=message.chat.id
    )

    type_names = {
        "invest": "Вложение",
        "expense": "Расход",
        "income": "Доход"
    }

    await message.answer(
        f"{type_names.get(transaction_type, 'Операция')} добавлен(а).\n\n"
        f"Сумма: {amount} ₽\n"
        f"Комментарий: {comment or '-'}"
    )


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
        await message.answer("Пока нет партнёров.")
        return

    balance = get_balance()
    partners_count = len(stats)

    if partners_count == 0:
        await message.answer("Нет партнёров для расчёта.")
        return

    profit_per_person = balance["profit"] / partners_count

    text = "Расчёт по партнёрам:\n\n"

    for display_name, username, invested, expenses_paid, income_received in stats:
        text += (
            f"{format_user(display_name, username)}:\n"
            f"Вложил: {invested} ₽\n"
            f"Оплатил расходов: {expenses_paid} ₽\n"
            f"Получил доходов: {income_received} ₽\n\n"
        )

    text += (
        "Итог:\n\n"
        f"Общая прибыль: {balance['profit']} ₽\n"
        f"Количество партнёров: {partners_count}\n"
        f"Прибыль на человека: {profit_per_person:.2f} ₽\n\n"
        "Пока это базовая статистика. Следующий уровень — сделки, где бот будет точно считать, кто кому должен."
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

    for created_at, display_name, username, transaction_type, amount, comment in rows:
        text += (
            f"{created_at}\n"
            f"{type_names.get(transaction_type, transaction_type)} — {amount} ₽\n"
            f"Партнёр: {format_user(display_name, username)}\n"
            f"Комментарий: {comment or '-'}\n\n"
        )

    await message.answer(text)


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
