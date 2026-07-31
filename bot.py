import asyncio
import logging
import os
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError as exc:
    raise RuntimeError("ADMIN_ID должен быть числом") from exc

PRODUCT_NAME = "Мука кристальная"
PRICE_PER_KG = 3000
WEIGHTS = (2, 3, 5)

router = Router()


class OrderForm(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    waiting_address = State()
    waiting_confirmation = State()


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Оформить заказ", callback_data="catalog")],
        [InlineKeyboardButton(text="ℹ️ О товаре", callback_data="about")],
    ])


def weight_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{weight} кг — {money(weight * PRICE_PER_KG)} ₽", callback_data=f"weight:{weight}")] for weight in WEIGHTS]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data="confirm_order")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")],
    ])


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Здравствуйте! Здесь можно оформить заказ.\n\n"
        f"<b>{escape(PRODUCT_NAME)}</b>\n"
        f"Цена: <b>{money(PRICE_PER_KG)} ₽ за кг</b>\n"
        "Оплата: <b>при получении</b>",
        reply_markup=main_menu(),
    )


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Заказ отменён.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Главное меню:", reply_markup=main_menu())


@router.callback_query(F.data == "home")
async def go_home(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "about")
async def about_product(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        f"<b>{escape(PRODUCT_NAME)}</b>\n\n"
        f"Цена: <b>{money(PRICE_PER_KG)} ₽ за кг</b>\n"
        "Доступный вес: <b>2, 3 или 5 кг</b>\n"
        "Оплата: <b>при получении</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Оформить заказ", callback_data="catalog")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(f"Выберите вес товара <b>«{escape(PRODUCT_NAME)}»</b>:", reply_markup=weight_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("weight:"))
async def choose_weight(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        weight = int(callback.data.split(":", maxsplit=1)[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректный вариант", show_alert=True)
        return

    if weight not in WEIGHTS:
        await callback.answer("Этот вес недоступен", show_alert=True)
        return

    await state.update_data(weight=weight)
    await state.set_state(OrderForm.waiting_name)
    await callback.message.answer(
        f"Вы выбрали: <b>{weight} кг</b>\n"
        f"Сумма: <b>{money(weight * PRICE_PER_KG)} ₽</b>\n\n"
        "Напишите имя получателя:"
    )
    await callback.answer()


@router.message(OrderForm.waiting_name, F.text)
async def get_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await message.answer("Введите имя длиной от 2 до 100 символов.")
        return

    await state.update_data(customer_name=name)
    await state.set_state(OrderForm.waiting_phone)
    phone_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер телефона", request_contact=True)],
            [KeyboardButton(text="❌ Отменить заказ")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Отправьте номер телефона кнопкой ниже или напишите его вручную:", reply_markup=phone_keyboard)


@router.message(OrderForm.waiting_phone, F.text == "❌ Отменить заказ")
async def cancel_from_keyboard(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Заказ отменён.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Главное меню:", reply_markup=main_menu())


@router.message(OrderForm.waiting_phone, F.contact)
async def get_phone_contact(message: Message, state: FSMContext) -> None:
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer("Пожалуйста, отправьте собственный контакт.")
        return
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(OrderForm.waiting_address)
    await message.answer("Напишите адрес доставки или место встречи:", reply_markup=ReplyKeyboardRemove())


@router.message(OrderForm.waiting_phone, F.text)
async def get_phone_text(message: Message, state: FSMContext) -> None:
    phone = message.text.strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        await message.answer("Введите корректный номер телефона.")
        return
    await state.update_data(phone=phone)
    await state.set_state(OrderForm.waiting_address)
    await message.answer("Напишите адрес доставки или место встречи:", reply_markup=ReplyKeyboardRemove())


@router.message(OrderForm.waiting_address, F.text)
async def get_address(message: Message, state: FSMContext) -> None:
    address = message.text.strip()
    if len(address) < 5 or len(address) > 300:
        await message.answer("Введите адрес длиной от 5 до 300 символов.")
        return
    await state.update_data(address=address)
    data = await state.get_data()
    weight = data["weight"]
    total = weight * PRICE_PER_KG
    summary = (
        "<b>Проверьте заказ:</b>\n\n"
        f"Товар: {escape(PRODUCT_NAME)}\n"
        f"Вес: {weight} кг\n"
        f"Сумма: {money(total)} ₽\n"
        "Оплата: при получении\n\n"
        f"Получатель: {escape(data['customer_name'])}\n"
        f"Телефон: {escape(data['phone'])}\n"
        f"Адрес: {escape(address)}"
    )
    await state.set_state(OrderForm.waiting_confirmation)
    await message.answer(summary, reply_markup=confirmation_keyboard())


@router.callback_query(OrderForm.waiting_confirmation, F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Заказ отменён.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(OrderForm.waiting_confirmation, F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    weight = data["weight"]
    total = weight * PRICE_PER_KG
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не указан"
    admin_text = (
        "🆕 <b>НОВЫЙ ЗАКАЗ</b>\n\n"
        f"Товар: {escape(PRODUCT_NAME)}\n"
        f"Вес: <b>{weight} кг</b>\n"
        f"Сумма: <b>{money(total)} ₽</b>\n"
        "Оплата: при получении\n\n"
        f"Получатель: {escape(data['customer_name'])}\n"
        f"Телефон: <code>{escape(data['phone'])}</code>\n"
        f"Адрес: {escape(data['address'])}\n\n"
        f"Telegram: {escape(username)}\n"
        f"ID клиента: <code>{callback.from_user.id}</code>"
    )
    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception:
        logging.exception("Не удалось отправить заказ администратору")
        await callback.answer("Не удалось передать заказ. Попробуйте позже.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "✅ <b>Заказ принят!</b>\n\n"
        "Продавец получил заявку и свяжется с вами.\n"
        "Оплата производится при получении."
    )
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await callback.answer("Заказ отправлен")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
