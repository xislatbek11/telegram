import asyncio
import os
import sqlite3
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties

# --- Bot sozlamalari ---
BOT_TOKEN = "7604805019:AAGd-yNEea7RenSSYhWcuF73AXCzIhX3cwo"
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
ADMINS = [7227067470]

# --- SQLite ---
conn = sqlite3.connect("credit_bot_users.db")
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, interest REAL, months INTEGER, currency TEXT, timestamp TEXT)")
conn.commit()

# --- Holatlar ---
class CreditForm(StatesGroup):
    choosing_currency = State()
    entering_amount = State()
    entering_interest = State()
    entering_months = State()

user_data = {}

# --- Boshlash ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="🇺🇿 Boshlash")]
    ])
    await message.answer("Tilni tanlang / Choose language:", reply_markup=kb)

@dp.message(F.text == "🇺🇿 Boshlash")
async def start_calc(message: types.Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="UZS"), KeyboardButton(text="USD"), KeyboardButton(text="RUB")]
    ])
    await state.set_state(CreditForm.choosing_currency)
    await message.answer("Valyutani tanlang:", reply_markup=kb)

@dp.message(CreditForm.choosing_currency)
async def set_currency(message: types.Message, state: FSMContext):
    await state.update_data(currency=message.text)
    await state.set_state(CreditForm.entering_amount)
    await message.answer("Kredit summasini kiriting (masalan: 5000000):")

@dp.message(CreditForm.entering_amount)
async def set_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
    except:
        return await message.answer("Iltimos, raqam kiriting.")
    await state.update_data(amount=amount)
    await state.set_state(CreditForm.entering_interest)
    await message.answer("Yillik foiz stavkasini kiriting (masalan: 24):")

@dp.message(CreditForm.entering_interest)
async def set_interest(message: types.Message, state: FSMContext):
    try:
        interest = float(message.text)
    except:
        return await message.answer("Iltimos, foizni raqamda kiriting.")
    await state.update_data(interest=interest)
    await state.set_state(CreditForm.entering_months)
    await message.answer("Kredit muddati (oyda) kiriting (masalan: 12):")

@dp.message(CreditForm.entering_months)
async def calculate_result(message: types.Message, state: FSMContext):
    try:
        months = int(message.text)
    except:
        return await message.answer("Iltimos, oy sonini to'g'ri kiriting.")

    data = await state.get_data()
    amount = data["amount"]
    interest = data["interest"]
    currency = data["currency"]

    monthly_rate = interest / 12 / 100
    monthly_payment = round((amount * monthly_rate) / (1 - (1 + monthly_rate) ** -months), 2)
    total_payment = round(monthly_payment * months, 2)
    total_interest = round(total_payment - amount, 2)

    schedule = []
    remaining = amount
    for month in range(1, months + 1):
        interest_payment = round(remaining * monthly_rate, 2)
        principal_payment = round(monthly_payment - interest_payment, 2)
        remaining = round(remaining - principal_payment, 2)
        schedule.append((month, principal_payment, interest_payment, monthly_payment, remaining))

    user_data[message.from_user.id] = {
        "amount": amount,
        "interest": interest,
        "months": months,
        "currency": currency,
        "monthly_payment": monthly_payment,
        "total_payment": total_payment,
        "total_interest": total_interest,
        "schedule": schedule
    }

    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)", (
        message.from_user.id, message.from_user.full_name
    ))
    cursor.execute("INSERT INTO logs (user_id, amount, interest, months, currency, timestamp) VALUES (?, ?, ?, ?, ?, ?)", (
        message.from_user.id, amount, interest, months, currency, datetime.now().isoformat()
    ))
    conn.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF chiqarish", callback_data="pdf")],
        [InlineKeyboardButton(text="📢 Reklama", url="https://t.me/xislatbek_1")],
        [InlineKeyboardButton(text="🔁 Qayta hisoblash", callback_data="restart")]
    ])

    await state.clear()
    await message.answer(
        f"✅ <b>Natija</b>\n\n"
        f"💰 Kredit: {amount} {currency}\n"
        f"📈 Foiz: {interest}%\n"
        f"🗓 Muddat: {months} oy\n"
        f"💳 Oylik to‘lov: <b>{monthly_payment} {currency}</b>\n"
        f"📊 Foizdan to‘lov: {total_interest} {currency}\n"
        f"💵 Umumiy to‘lov: {total_payment} {currency}",
        reply_markup=kb
    )

@dp.callback_query(F.data == "restart")
async def restart(call: types.CallbackQuery, state: FSMContext):
    await start_calc(call.message, state)

@dp.callback_query(F.data == "pdf")
async def generate_pdf(call: types.CallbackQuery):
    data = user_data.get(call.from_user.id)
    if not data:
        return await call.message.answer("Ma'lumot topilmadi.")

    file_path = f"{call.from_user.id}_report.pdf"
    c = canvas.Canvas(file_path, pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(50, 800, f"Kredit hisobot ({data['currency']})")
    c.drawString(50, 780, f"Kredit: {data['amount']} | Foiz: {data['interest']}% | Muddat: {data['months']} oy")
    c.drawString(50, 760, f"Oylik to'lov: {data['monthly_payment']} | Jami: {data['total_payment']}")
    c.drawString(50, 740, "Jadval:")

    y = 720
    c.drawString(50, y, "Oy | Asosiy to'lov | Foiz | To'lov | Qolgan")
    for row in data["schedule"]:
        y -= 20
        if y < 50:
            c.showPage()
            y = 800
        c.drawString(50, y, f"{row[0]:>2} | {row[1]:>10} | {row[2]:>6} | {row[3]:>7} | {row[4]:>10}")

    c.save()
    await call.message.answer_document(InputFile(path=file_path))
    os.remove(file_path)

# --- Ishga tushirish ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
