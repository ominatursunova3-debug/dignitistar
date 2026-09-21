import asyncio
import sqlite3
from datetime import datetime
from contextlib import closing
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ============= НАСТРОЙКИ =============
BOT_TOKEN = "8821675817:AAHBdRO60VJ21dF4zxKSiHYJeAHsnl6lfz4"
ADMIN_ID = 5385432573
STAR_RATE = 1.4
MIN_STARS = 50
DB_FILE = "orders.db"

# Реквизиты для оплаты
PAY_CARD = "2204 3203 5217 0817"
PAY_SBP = "+7 (969) 611-68-88"
PAY_BANK = "Озон"
PAY_NAME = "Ань Тхы. Х"
# =====================================


# ---------- Состояния ----------
class OrderForm(StatesGroup):
    wait_stars = State()
    wait_username = State()
    wait_photo = State()


bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# ---------- База данных ----------
def db_init():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                username    TEXT,
                target_user TEXT,
                stars       INTEGER,
                amount      REAL,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT
            )
        """)
        conn.commit()


def db_save_order(user_id, username, target_user, stars, amount):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        cur = conn.execute(
            "INSERT INTO orders (user_id, username, target_user, stars, amount, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (user_id, username, target_user, stars, amount,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        conn.commit()
        return cur.lastrowid


def db_update_status(order_id, status):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        conn.commit()


def db_get_order(order_id):
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def db_all_orders():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT 50"
        ).fetchall()


# ---------- Клавиатуры ----------
def menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 50 звёзд",   callback_data="buy_50")],
        [InlineKeyboardButton(text="⭐ 100 звёзд",  callback_data="buy_100"),
         InlineKeyboardButton(text="⭐ 250 звёзд",  callback_data="buy_250")],
        [InlineKeyboardButton(text="⭐ 500 звёзд",  callback_data="buy_500"),
         InlineKeyboardButton(text="⭐ 1000 звёзд", callback_data="buy_1000")],
        [InlineKeyboardButton(text="✏️ Своё количество", callback_data="buy_custom")],
    ])


def pay_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена",     callback_data="cancel")],
    ])


def admin_kb(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"ok_{order_id}"),
         InlineKeyboardButton(text="❌ Отклонить",   callback_data=f"no_{order_id}")],
    ])


# ---------- Хендлеры ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    text = (
        "👋 Привет! Здесь можно купить Telegram Stars.\n\n"
        f"💰 Курс: 1 звезда = {STAR_RATE} руб\n"
        f"📌 Минимум: {MIN_STARS} звёзд\n\n"
        "Выбери количество:"
    )
    await message.answer(text, reply_markup=menu_kb())


@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    data = callback.data.replace("buy_", "")

    if data == "custom":
        await callback.message.edit_text(
            f"Введи количество звёзд (от {MIN_STARS}):\n"
            "Например: 75"
        )
        await state.set_state(OrderForm.wait_stars)
        await callback.answer()
        return

    stars = int(data)
    amount = round(stars * STAR_RATE, 2)

    await state.update_data(stars=stars, amount=amount)
    await state.set_state(OrderForm.wait_username)

    await callback.message.edit_text(
        f"⭐ Заказ: {stars} звёзд\n"
        f"💰 Сумма: {amount} руб\n\n"
        "Теперь введи Telegram-username получателя (без @):\n"
        "Например: durov"
    )
    await callback.answer()


# Получаем своё количество звёзд
@dp.message(StateFilter(OrderForm.wait_stars))
async def get_custom_stars(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Введи целое число, например 75:")
        return

    stars = int(message.text)
    if stars < MIN_STARS:
        await message.answer(f"❌ Минимум {MIN_STARS} звёзд. Введи другое число:")
        return

    amount = round(stars * STAR_RATE, 2)
    await state.update_data(stars=stars, amount=amount)
    await state.set_state(OrderForm.wait_username)

    await message.answer(
        f"⭐ Количество: {stars} звёзд\n"
        f"💰 Сумма: {amount} руб\n\n"
        "Введи Telegram-username получателя (без @):\n"
        "Например: durov"
    )


# Получаем username получателя
@dp.message(StateFilter(OrderForm.wait_username))
async def get_target_username(message: types.Message, state: FSMContext):
    if not message.text:
        return

    target = message.text.strip().lstrip("@")

    # Валидация: только латиница/цифры/_  от 5 до 32 символов
    if not target.replace("_", "").isalnum() or len(target) < 5 or len(target) > 32:
        await message.answer(
            "❌ Username некорректный. Введи без @, от 5 символов, только латиница/цифры/_\n"
            "Например: durov"
        )
        return

    data = await state.get_data()
    stars = data.get("stars")
    amount = data.get("amount")
    uname = message.from_user.username or "(без ника)"

    order_id = db_save_order(message.from_user.id, uname, target, stars, amount)
    await state.clear()

    text = (
        f"🧾 Заказ #{order_id}\n"
        f"⭐ Звёзды: {stars}\n"
        f"💰 Сумма: {amount} руб\n"
        f"📨 Получатель: @{target}\n\n"
        "💳 Реквизиты для оплаты:\n\n"
        f"🏦 Банк: {PAY_BANK}\n"
        f"👤 Получатель: {PAY_NAME}\n\n"
        f"💳 Карта:\n<code>{PAY_CARD}</code>\n\n"
        f"📱 СБП:\n<code>{PAY_SBP}</code>\n\n"
        "После перевода нажми «Я оплатил» и отправь скриншот чека."
    )

    await message.answer(text, reply_markup=pay_kb(order_id), parse_mode="HTML")


@dp.callback_query(F.data.startswith("paid_"))
async def process_paid(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.replace("paid_", ""))
    await state.update_data(order_id=order_id)
    await state.set_state(OrderForm.wait_photo)

    await callback.message.edit_text(
        "Отправь скриншот чека об оплате (фото или картинку).\n"
        "Я передам его продавцу для проверки."
    )
    await callback.answer()


@dp.callback_query(F.data == "cancel")
async def process_cancel(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if "order_id" in data:
        db_update_status(data["order_id"], "cancelled")
    await state.clear()
    await callback.message.edit_text("❌ Заказ отменён.")
    await callback.answer()


# Приём скриншота
@dp.message(StateFilter(OrderForm.wait_photo), F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    await state.clear()

    if not order_id:
        await message.answer("Ошибка: заказ не найден. Начни заново /start")
        return

    order = db_get_order(order_id)
    if not order:
        await message.answer("Заказ не найден в базе. Начни заново /start")
        return

    db_update_status(order_id, "waiting_confirm")

    caption = (
        f"🔔 Новая оплата по заказу #{order_id}\n"
        f"👤 Покупатель: @{order['username']} (ID: {message.from_user.id})\n"
        f"⭐ Звёзды: {order['stars']}\n"
        f"💰 Сумма: {order['amount']} руб\n"
        f"📨 Кому: @{order['target_user']}\n\n"
        "Проверь платёж и подтверди выполнение."
    )
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=caption,
        reply_markup=admin_kb(order_id),
    )
    await message.answer("Скриншот отправлен продавцу. Ожидай подтверждения ✅")


# Если прислали фото не в том состоянии
@dp.message(F.photo)
async def photo_outside_state(message: types.Message):
    await message.answer("Сначала выбери количество и оформи заказ: /start")


# Админ: подтвердить
@dp.callback_query(F.data.startswith("ok_"))
async def admin_confirm(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    order_id = int(callback.data.replace("ok_", ""))
    order = db_get_order(order_id)
    db_update_status(order_id, "completed")

    if order:
        await bot.send_message(
            order["user_id"],
            f"✅ Заказ #{order_id} подтверждён!\n"
            f"⭐ {order['stars']} звёзд будут отправлены на @{order['target_user']}.\n"
            "Спасибо за покупку!"
        )
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ Подтверждено админом."
        )
    except Exception:
        pass
    await callback.answer("Заказ подтверждён")


# Админ: отклонить
@dp.callback_query(F.data.startswith("no_"))
async def admin_reject(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    order_id = int(callback.data.replace("no_", ""))
    order = db_get_order(order_id)
    db_update_status(order_id, "rejected")

    if order:
        await bot.send_message(
            order["user_id"],
            f"❌ Заказ #{order_id} отклонён.\n"
            "Свяжись с продавцом для уточнения."
        )
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ Отклонено админом."
        )
    except Exception:
        pass
    await callback.answer("Заказ отклонён")


@dp.message(Command("orders"))
async def cmd_orders(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    rows = db_all_orders()
    if not rows:
        await message.answer("Заказов пока нет.")
        return

    lines = ["📋 Последние 50 заказов:\n"]
    for r in rows:
        lines.append(
            f"#{r['id']} | покупатель: @{r['username']} (ID {r['user_id']})\n"
            f"   получатель: @{r['target_user']}\n"
            f"   ⭐ {r['stars']} | 💰 {r['amount']} руб | {r['status']}\n"
            f"   {r['created_at']}"
        )
    await message.answer("\n\n".join(lines))


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    is_admin = message.from_user.id == ADMIN_ID
    text = (
        "Команды:\n"
        "/start — купить звёзды\n"
        "/help — эта справка"
    )
    if is_admin:
        text += "\n/orders — история заказов"
    await message.answer(text)


# ---------- Запуск ----------
async def main():
    db_init()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())