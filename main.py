import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import FastAPI, HTTPException, Query
from supabase import create_client, Client

# === НАСТРОЙКИ SUPABASE ===
# Замени строки ниже на свои реальные URL и ключ из панели Supabase (Project Settings -> API)
SUPABASE_URL = "https://sgxawwxfaotrrgltjstg.supabase.co"
SUPABASE_KEY = "sb_publishable_DlUmmtGRunZBsWZmijKtjw_pPom7xKN"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# === ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЙ ===
app = FastAPI()

# === ВСТАВЬ СВОЙ ТОКЕН ОТ BOTFATHER В КАВЫЧКАХ ===
BOT_TOKEN = "8860695938:AAG7aXjkOW3Iiin-41jp2gqAeA8e-p6mgn4"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния для регистрации
class Registration(StatesGroup):
    language = State()
    name = State()
    age = State()

# Клавиатура выбора языка
lang_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="uz O'zbekcha", callback_data="lang_uz")],
    [InlineKeyboardButton(text="ru Русский", callback_data="lang_ru")],
    [InlineKeyboardButton(text="gb English", callback_data="lang_en")]
])

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.set_state(Registration.language)
    await message.answer(
        "Привет! Выберите язык / Tilni tanlang / Choose your language:",
        reply_markup=lang_keyboard
    )

@dp.callback_query(Registration.language)
async def process_language(callback: types.CallbackQuery, state: FSMContext):
    lang = callback.data.split('_')[1]
    await state.update_data(chosen_language=lang)
    await state.set_state(Registration.name)
    # Здесь можно добавить логику дальше...


# === ЭНДПОИНТ ГЕОЛОКАЦИИ (ДЛЯ TELEGRAM MINI APP) ===
@app.get("/api/events/nearby")
async def get_nearby_events(
    lat: float = Query(..., description="Широта пользователя"),
    lon: float = Query(..., description="Долгота пользователя"),
    max_distance: int = Query(50000, description="Максимальный радиус поиска в метрах")
):
    try:
        # Вызываем функцию get_nearby_events в Supabase
        response = supabase.rpc(
            "get_nearby_events",
            {
                "user_lat": lat,
                "user_lon": lon,
                "max_distance_meters": max_distance
            }
        ).execute()

        return {
            "status": "success",
            "count": len(response.data),
            "data": response.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))