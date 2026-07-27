import sys
import asyncio
import logging
import math
import os
import sys
import json
import aiohttp
import asyncpg
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# Токен бота и переменные окружения
TOKEN = os.getenv("TOKEN", "8860695938:AAHlZrF2L7MQg2NGlSxTG4S1sDs3HdaNH60")
DEEPAI_API_KEY = os.getenv("DEEPAI_API_KEY", "YOUR_DEEPAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Список Telegram ID администраторов
ADMIN_IDS = [8918342054]

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Структуры данных в памяти (дублируются/синхронизируются с PostgreSQL)
DATABASE = {}
LIKES = {}  # user_id: set(liked_user_ids)
INCOMING_LIKES = {}  # user_id: [user_ids who liked them]
INACTIVE_USERS = set()  # Множество пользователей, временно скрывших анкету
USER_LANGUAGES = {}  # user_id: lang_code ('ru', 'uz', 'en')


# --- РАБОТА С POSTGRESQL ---
async def init_db():
    if not DATABASE_URL:
        logging.warning("DATABASE_URL is not set! Data will only be stored in memory.")
        return
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
                           CREATE TABLE IF NOT EXISTS users
                           (
                               user_id
                               BIGINT
                               PRIMARY
                               KEY,
                               data
                               JSONB
                           )
                           ''')
        # Загружаем существующих пользователей в оперативную память при старте
        rows = await conn.fetch('SELECT user_id, data FROM users')
        for row in rows:
            DATABASE[row['user_id']] = json.loads(row['data'])
        await conn.close()
        logging.info(f"Database initialized successfully. Loaded {len(DATABASE)} users.")
    except Exception as e:
        logging.error(f"Database initialization error: {e}")


async def save_user_to_db(user_id: int, user_data: dict):
    DATABASE[user_id] = user_data
    if not DATABASE_URL:
        return
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute(
            '''
            INSERT INTO users (user_id, data)
            VALUES ($1, $2) ON CONFLICT (user_id) DO
            UPDATE SET data = $2
            ''',
            user_id, json.dumps(user_data)
        )
        await conn.close()
    except Exception as e:
        logging.error(f"Error saving user {user_id} to DB: {e}")


async def delete_user_from_db(user_id: int):
    DATABASE.pop(user_id, None)
    if not DATABASE_URL:
        return
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('DELETE FROM users WHERE user_id = $1', user_id)
        await conn.close()
    except Exception as e:
        logging.error(f"Error deleting user {user_id} from DB: {e}")


# Переводы текстов интерфейса
TEXTS = {
    "ru": {
        "welcome": "👋 Привет! Добро пожаловать в бот знакомств.\n\nЗдесь вы сможете найти интересных людей рядом с вами, общаться и заводить новые знакомства.",
        "choose_lang": "🌐 Пожалуйста, выберите язык / Iltimos, tilni tanlang / Please choose your language:",
        "btn_ru": "🇷🇺 Русский",
        "btn_uz": "🇺🇿 O'zbekcha",
        "btn_en": "🇬🇧 English",
        "create_profile": "📝 Создать свою анкету",
        "edit_profile": "✏️ Изменить анкету",
        "search_profiles": "🔍 Искать анкеты",
        "continue_search": "🔍 Продолжить поиск",
        "rest": "🛌 Отдохнуть",
        "return_search": "🟢 Вернуться в поиск",
        "hide_profile": "👁️‍🗨️ Временно скрыть мою анкету",
        "delete_profile": "🗑️ Полностью удалить анкету",
        "back": "🔙 Назад",
        "name_prompt": "1️⃣ Как вас зовут? Введите ваше имя:",
        "name_cmd_error": "Команды не принимаются. Пожалуйста, введите ваше имя:",
        "age_prompt": "2️⃣ Сколько вам лет? (Введите число, например: 20):",
        "age_cmd_error": "Команды не принимаются. Пожалуйста, введите ваш возраст цифрами:",
        "age_error_digit": "Пожалуйста, введите возраст цифрами:",
        "age_error_range": "Возраст должен быть от 16 до 70 лет:",
        "location_prompt": "3️⃣ Пожалуйста, отправьте вашу локацию:",
        "location_btn": "📍 Отправить локацию",
        "location_fallback": "Пожалуйста, отправьте локацию с помощью кнопки 📍",
        "desc_prompt": "4️⃣ Расскажите немного о себе:",
        "desc_cmd_error": "Команды не принимаются. Пожалуйста, расскажите немного о себе:",
        "media_prompt": "5️⃣ Отправьте от 1 до 3 фото или видео. Напишите **Готово**, когда закончите.",
        "media_error": "Пожалуйста, отправьте хотя бы одно фото или видео!",
        "media_type_error": "Пожалуйста, отправьте фото/видео или напишите «Готово».",
        "nsfw_error": "⚠️ На фото обнаружен контент 18+ (NSFW). Пожалуйста, загрузите другую фотографию.",
        "media_saved": "Принято! Можете отправить еще {remaining} файл(а) или написать **Готово**.",
        "gender_prompt": "Выберите ваш пол:",
        "btn_male": "👨 Я парень",
        "btn_female": "👩 Я девушка",
        "gender_error": "Пожалуйста, выберите вариант с помощью кнопок!",
        "preference_prompt": "Кто тебе интересен?",
        "btn_pref_male": "👨 Парни",
        "btn_pref_female": "👩 Девушки",
        "btn_pref_all": "🌐 Все",
        "registration_done": "🎉 Все готово! Нажми кнопку ниже, чтобы начать поиск людей:",
        "no_profile": "Сначала создайте свою анкету!",
        "profile_hidden": "⚠️ Ваша анкета скрыта. Верните ее в активный режим через меню.",
        "search_started": "🔍 Поиск запущен!",
        "no_more_profiles": "Вы посмотрели все доступные анкеты!",
        "cancel": "❌ Отменить",
        "msg_cancelled": "Отправка сообщения отменена.",
        "msg_sent": "✅ Ваше сообщение и лайк успешно отправлены!",
        "write_msg_prompt": "Напишите текст сообщения:",
        "search_stopped": "Поиск завершен.",
        "like": "❤️ Лайк",
        "dislike": "💔 Не нравится",
        "leave_msg": "💌 Оставить сообщение",
        "stop_search": "🛑 Остановить поиск",
        "match_text": "🎉 Взаимная симпатия! Вот контакт:",
        "contact_visible": "🔗 Контакт: @{username}",
        "contact_hidden": "🔗 Контакт: Скрыт (нет юзернейма)",
        "rest_menu": "🛌 Меню отдыха. Выберите, что вы хотите сделать:",
        "profile_activated": "🟢 Ваша анкета снова активна! Открываю поиск...",
        "profile_hided": "👁️‍🗨️ Анкета временно скрыта. Чтобы снова искать людей, нажмите кнопку активации.",
        "profile_deleted": "🗑️ Ваша анкета удалена. Чтобы начать заново, введите /start.",
        "menu_fallback": "Пожалуйста, используйте кнопки меню:",
        "admin_no_rights": "У вас нет прав для использования этой команды.",
        "no_users": "В базе пока нет зарегистрированных пользователей.",
        "users_list": "📋 Список зарегистрированных пользователей:\n\n"
    },
    "uz": {
        "welcome": "👋 Salom! Tanishuv botiga xush kelibsiz.\n\nBu yerda siz o'zingizga yaqin bo'lgan qiziqarli odamlarni topishingiz, muloqot qilishingiz va yangi tanishuvlar orttirishingiz mumkin.",
        "choose_lang": "🌐 Iltimos, tilni tanlang / Пожалуйста, выберите язык / Please choose your language:",
        "btn_ru": "🇷🇺 Русский",
        "btn_uz": "🇺🇿 O'zbekcha",
        "btn_en": "🇬🇧 English",
        "create_profile": "📝 O'z anketangizni yaratish",
        "edit_profile": "✏️ Anketani o'zgartirish",
        "search_profiles": "🔍 Anketalarni qidirish",
        "continue_search": "🔍 Qidirishni davom ettirish",
        "rest": "🛌 Dam olish",
        "return_search": "🟢 Qidirishga qaytish",
        "hide_profile": "👁️‍🗨️ Anketamni vaqtincha yashirish",
        "delete_profile": "🗑️ Anketani to'liq o'chirish",
        "back": "🔙 Orqaga",
        "name_prompt": "1️⃣ Ismingiz nima? Ismingizni kiriting:",
        "name_cmd_error": "Buyruqlar qabul qilinmaydi. Iltimos, ismingizni kiriting:",
        "age_prompt": "2️⃣ Yoshingiz nechada? (Raqamda kiriting, masalan: 20):",
        "age_cmd_error": "Buyruqlar qabul qilinmaydi. Iltimos, yoshingizni raqamlar bilan kiriting:",
        "age_error_digit": "Iltimos, yoshni raqamlar bilan kiriting:",
        "age_error_range": "Yosh 16 dan 70 gacha bo'lishi kerak:",
        "location_prompt": "3️⃣ Iltimos, manzilingizni yuboring:",
        "location_btn": "📍 Manzilni yuborish",
        "location_fallback": "Iltimos, 📍 tugmasi yordamida manzilingizni yuboring",
        "desc_prompt": "4️⃣ O'zingiz haqingizda qisqacha yozing:",
        "desc_cmd_error": "Buyruqlar qabul qilinmaydi. Iltimos, o'zingiz haqingizda qisqacha yozing:",
        "media_prompt": "5️⃣ 1 tadan 3 tagacha rasm yoki video yuboring. Tugatgach, **Tayyor** deb yozing.",
        "media_error": "Iltimos, kamida bitta rasm yoki video yuboring!",
        "media_type_error": "Iltimos, rasm/video yuboring yoki «Tayyor» deb yozing.",
        "nsfw_error": "⚠️ Suratda 18+ (NSFW) kontent aniqlandi. Iltimos, boshqa surat yuklang.",
        "media_saved": "Qabul qilindi! Yana {remaining} ta fayl yuborishingiz mumkin yoki **Tayyor** deb yozing.",
        "gender_prompt": "Jinsingizni tanlang:",
        "btn_male": "👨 Men yigitman",
        "btn_female": "👩 Men qizman",
        "gender_error": "Iltimos, tugmalar yordamida tanlang!",
        "preference_prompt": "Kimlar sizni qiziqtiradi?",
        "btn_pref_male": "👨 Yigitlar",
        "btn_pref_female": "👩 Qizlar",
        "btn_pref_all": "🌐 Barchasi",
        "registration_done": "🎉 Hammasi tayyor! Odamlarni qidirishni boshlash uchun quyidagi tugmani bosing:",
        "no_profile": "Avval o'z anketangizni yarating!",
        "profile_hidden": "⚠️ Anketangiz yashirilgan. Uni menyu orqali faol holatga qaytaring.",
        "search_started": "🔍 Qidiruv boshlandi!",
        "no_more_profiles": "Siz barcha mavjud anketalarni ko'rib chiqdingiz!",
        "cancel": "❌ Bekor qilish",
        "msg_cancelled": "Xabar yuborish bekor qilindi.",
        "msg_sent": "✅ Xabaringiz va laykingiz muvaffaqiyatli yuborildi!",
        "write_msg_prompt": "Xabar matnini yozing:",
        "search_stopped": "Qidiruv yakunlandi.",
        "like": "❤️ Layk",
        "dislike": "💔 Yoqmadi",
        "leave_msg": "💌 Xabar qoldirish",
        "stop_search": "🛑 Qidiruvni to'xtatish",
        "match_text": "🎉 O'zaro simpatiya! Mana kontakt:",
        "contact_visible": "🔗 Kontakt: @{username}",
        "contact_hidden": "🔗 Kontakt: Yashiringan (username yo'q)",
        "rest_menu": "🛌 Dam olish menyusi. Nima qilmoqchisiz?",
        "profile_activated": "🟢 Anketangiz yana faol! Qidiruvni ochyapman...",
        "profile_hided": "👁️‍🗨️ Anketa vaqtincha yashirildi. Odamlarni qayta qidirish uchun faollashtirish tugmasini bosing.",
        "profile_deleted": "🗑️ Anketangiz o'chirildi. Qaytadan boshlash uchun /start yuboring.",
        "menu_fallback": "Iltimos, menyu tugmalaridan foydalaning:",
        "admin_no_rights": "Bu buyruqdan foydalanishga huquqingiz yo'q.",
        "no_users": "Bazada hali ro'yxatdan o'tgan foydalanuvchilar yo'q.",
        "users_list": "📋 Ro'yxatdan o'tgan foydalanuvchilar ro'yxati:\n\n"
    },
    "en": {
        "welcome": "👋 Hello! Welcome to the dating bot.\n\nHere you can find interesting people near you, chat, and make new connections.",
        "choose_lang": "🌐 Please choose your language / Пожалуйста, выберите язык / Iltimos, tilni tanlang:",
        "btn_ru": "🇷🇺 Русский",
        "btn_uz": "🇺🇿 O'zbekcha",
        "btn_en": "🇬🇧 English",
        "create_profile": "📝 Create profile",
        "edit_profile": "✏️ Edit profile",
        "search_profiles": "🔍 Search profiles",
        "continue_search": "🔍 Continue search",
        "rest": "🛌 Take a rest",
        "return_search": "🟢 Return to search",
        "hide_profile": "👁️‍🗨️ Hide my profile temporarily",
        "delete_profile": "🗑️ Delete profile completely",
        "back": "🔙 Back",
        "name_prompt": "1️⃣ What is your name? Enter your name:",
        "name_cmd_error": "Commands are not accepted. Please enter your name:",
        "age_prompt": "2️⃣ How old are you? (Enter a number, e.g., 20):",
        "age_cmd_error": "Commands are not accepted. Please enter your age using numbers:",
        "age_error_digit": "Please enter your age using numbers:",
        "age_error_range": "Age must be between 16 and 70 years:",
        "location_prompt": "3️⃣ Please send your location:",
        "location_btn": "📍 Send location",
        "location_fallback": "Please send your location using the 📍 button",
        "desc_prompt": "4️⃣ Tell us a little about yourself:",
        "desc_cmd_error": "Commands are not accepted. Please tell us a little about yourself:",
        "media_prompt": "5️⃣ Send 1 to 3 photos or videos. Type **Done** when finished.",
        "media_error": "Please send at least one photo or video!",
        "media_type_error": "Please send a photo/video or type «Done».",
        "nsfw_error": "⚠️ 18+ (NSFW) content detected in the photo. Please upload another picture.",
        "media_saved": "Accepted! You can send {remaining} more file(s) or type **Done**.",
        "gender_prompt": "Select your gender:",
        "btn_male": "👨 I am a guy",
        "btn_female": "👩 I am a girl",
        "gender_error": "Please select an option using the buttons!",
        "preference_prompt": "Who are you interested in?",
        "btn_pref_male": "👨 Guys",
        "btn_pref_female": "👩 Girls",
        "btn_pref_all": "🌐 Everyone",
        "registration_done": "🎉 All set! Click the button below to start searching for people:",
        "no_profile": "Please create your profile first!",
        "profile_hidden": "⚠️ Your profile is hidden. Unhide it through the menu.",
        "search_started": "🔍 Search started!",
        "no_more_profiles": "You have viewed all available profiles!",
        "cancel": "❌ Cancel",
        "msg_cancelled": "Message sending cancelled.",
        "msg_sent": "✅ Your message and like have been successfully sent!",
        "write_msg_prompt": "Write your message text:",
        "search_stopped": "Search finished.",
        "like": "❤️ Like",
        "dislike": "💔 Dislike",
        "leave_msg": "💌 Leave a message",
        "stop_search": "🛑 Stop search",
        "match_text": "🎉 Mutual match! Here is the contact:",
        "contact_visible": "🔗 Contact: @{username}",
        "contact_hidden": "🔗 Contact: Hidden (no username)",
        "rest_menu": "🛌 Rest menu. Choose what you want to do:",
        "profile_activated": "🟢 Your profile is active again! Opening search...",
        "profile_hided": "👁️‍🗨️ Profile temporarily hidden. To search again, press the activation button.",
        "profile_deleted": "🗑️ Your profile has been deleted. To start over, send /start.",
        "menu_fallback": "Please use the menu buttons:",
        "admin_no_rights": "You do not have rights to use this command.",
        "no_users": "There are no registered users in the database yet.",
        "users_list": "📋 List of registered users:\n\n"
    }
}


def get_t(user_id: int, key: str) -> str:
    lang = USER_LANGUAGES.get(user_id, "ru")
    return TEXTS.get(lang, TEXTS["ru"]).get(key, TEXTS["ru"].get(key, key))


AD_TEXT = (
    "🔥 **Новая платформа знакомств!**\n\n"
    "🌐 Не пропускай обновления! Подписывайся на наш официальный Telegram-канал, чтобы быть в курсе всех новостей.\n"
    "👉 **Подписаться:** https://t.me/kompashki_daily"
)


def calculate_distance(lat1, lon1, lat2, lon2):
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return round(R * c)


async def check_image_nsfw(file_url: str) -> bool:
    if DEEPAI_API_KEY == "YOUR_DEEPAI_API_KEY":
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    "https://api.deepai.org/api/nsfw-detector",
                    data={'image': file_url},
                    headers={'api-key': DEEPAI_API_KEY}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    nsfw_score = result.get("output", {}).get("nsfw_score", 0.0)
                    return nsfw_score > 0.65
    except Exception as e:
        logging.error(f"NSFW check error: {e}")
    return False


def add_fake_profiles():
    fake_users = {
        1001: {
            "name": "Алина",
            "age": 20,
            "city": "Ташкент",
            "latitude": 41.2995,
            "longitude": 69.2401,
            "description": "Привет! Ищу новых друзей для прогулок и общения ✨",
            "media": [("photo",
                       "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=600&auto=format&fit=crop&q=80")],
            "gender": "female",
            "preference": "all",
            "username": "alina_demo"
        },
        1002: {
            "name": "Тимур",
            "age": 22,
            "city": "Ташкент",
            "latitude": 41.3111,
            "longitude": 69.2797,
            "description": "Студент, увлекаюсь музыкой и IT. Давайте общаться! 🎧",
            "media": [("photo",
                       "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=600&auto=format&fit=crop&q=80")],
            "gender": "male",
            "preference": "all",
            "username": "timur_demo"
        }
    }
    for uid, data in fake_users.items():
        if uid not in DATABASE:
            DATABASE[uid] = data


async def send_broadcast():
    if not DATABASE:
        return
    for user_id in list(DATABASE.keys()):
        if 1000 <= user_id <= 2000:
            continue
        try:
            await bot.send_message(chat_id=user_id, text=AD_TEXT, parse_mode="Markdown")
            await asyncio.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed broadcast to {user_id}: {e}")


class RegistrationStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_name = State()
    waiting_for_age = State()
    waiting_for_location = State()
    waiting_for_description = State()
    waiting_for_media = State()
    waiting_for_gender = State()
    waiting_for_preference = State()
    active = State()


class SearchStates(StatesGroup):
    browsing = State()
    waiting_for_message = State()


class RestStates(StatesGroup):
    menu = State()


def get_language_keyboard():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🇷🇺 Русский"), types.KeyboardButton(text="🇺🇿 O'zbekcha")],
            [types.KeyboardButton(text="🇬🇧 English")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_main_menu_keyboard(user_id=None):
    has_profile = user_id is not None and user_id in DATABASE
    is_resting = user_id in INACTIVE_USERS

    if not has_profile:
        return types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text=get_t(user_id, "create_profile"))]],
            resize_keyboard=True
        )

    profile_btn = get_t(user_id, "edit_profile")
    search_btn = get_t(user_id, "search_profiles") if not is_resting else get_t(user_id, "continue_search")
    rest_btn = get_t(user_id, "rest") if not is_resting else get_t(user_id, "return_search")

    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=profile_btn), types.KeyboardButton(text=search_btn)],
            [types.KeyboardButton(text=rest_btn)]
        ],
        resize_keyboard=True
    )


def get_rest_menu_keyboard(user_id=None):
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=get_t(user_id, "hide_profile"))],
            [types.KeyboardButton(text=get_t(user_id, "delete_profile"))],
            [types.KeyboardButton(text=get_t(user_id, "back"))]
        ],
        resize_keyboard=True
    )


def get_gender_reply_keyboard(user_id=None):
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=get_t(user_id, "btn_male")),
                   types.KeyboardButton(text=get_t(user_id, "btn_female"))]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_preference_reply_keyboard(user_id=None):
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=get_t(user_id, "btn_pref_male")),
             types.KeyboardButton(text=get_t(user_id, "btn_pref_female"))],
            [types.KeyboardButton(text=get_t(user_id, "btn_pref_all"))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_location_keyboard(user_id=None):
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=get_t(user_id, "location_btn"), request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


def get_search_control_keyboard(user_id=None):
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=get_t(user_id, "like")), types.KeyboardButton(text=get_t(user_id, "dislike"))],
            [types.KeyboardButton(text=get_t(user_id, "leave_msg")),
             types.KeyboardButton(text=get_t(user_id, "stop_search"))]
        ],
        resize_keyboard=True
    )


def get_cancel_message_keyboard(user_id=None):
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=get_t(user_id, "cancel"))]],
        resize_keyboard=True
    )


async def send_profile_to_user(recipient_id: int, profile_data: dict, intro_text: str):
    name = profile_data.get("name")
    age = profile_data.get("age")
    city = profile_data.get("city", "Ташкент")
    desc = profile_data.get("description")
    username = profile_data.get("username")

    if username:
        caption_text = f"{intro_text}\n\n{name}, {age}, {city} — {desc}\n\n{get_t(recipient_id, 'contact_visible').format(username=username)}"
    else:
        caption_text = f"{intro_text}\n\n{name}, {age}, {city} — {desc}\n\n{get_t(recipient_id, 'contact_hidden')}"

    try:
        media_list = profile_data.get("media", [])
        if len(media_list) == 1:
            m_type, file_id = media_list[0]
            if m_type == "photo":
                await bot.send_photo(chat_id=recipient_id, photo=file_id, caption=caption_text)
            else:
                await bot.send_video(chat_id=recipient_id, video=file_id, caption=caption_text)
        elif len(media_list) > 1:
            album_builder = []
            for idx, (m_type, file_id) in enumerate(media_list):
                if m_type == "photo":
                    album_builder.append(types.InputMediaPhoto(media=file_id, caption=caption_text if idx == 0 else ""))
                else:
                    album_builder.append(types.InputMediaVideo(media=file_id, caption=caption_text if idx == 0 else ""))
            await bot.send_media_group(chat_id=recipient_id, media=album_builder)
        else:
            await bot.send_message(chat_id=recipient_id, text=caption_text)
    except Exception as e:
        logging.error(f"Error sending profile: {e}")


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await state.set_state(RegistrationStates.waiting_for_language)
    await message.answer(TEXTS["ru"]["choose_lang"], reply_markup=get_language_keyboard())


@dp.message(RegistrationStates.waiting_for_language)
async def process_language_selection(message: types.Message, state: FSMContext):
    text = message.text
    user_id = message.from_user.id

    if "русский" in text.lower():
        USER_LANGUAGES[user_id] = "ru"
    elif "o'zbekcha" in text.lower() or "узбекский" in text.lower():
        USER_LANGUAGES[user_id] = "uz"
    elif "english" in text.lower():
        USER_LANGUAGES[user_id] = "en"
    else:
        USER_LANGUAGES[user_id] = "ru"

    welcome_text = get_t(user_id, "welcome")
    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard(user_id))
    await state.set_state(RegistrationStates.active)


@dp.message(Command("usernames"))
async def cmd_get_usernames(message: types.Message):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        await message.answer(get_t(user_id, "admin_no_rights"))
        return

    usernames = []
    for uid, data in DATABASE.items():
        username = data.get("username")
        name = data.get("name", "Без имени")
        if username:
            usernames.append(f"@{username} (ID: {uid}, Имя: {name})")
        else:
            usernames.append(f"Без юзернейма (ID: {uid}, Имя: {name})")

    if not usernames:
        await message.answer(get_t(user_id, "no_users"))
        return

    response_text = get_t(user_id, "users_list") + "\n".join(usernames)
    await message.answer(response_text[:4000])


@dp.message(F.text.in_([
    "🛌 Отдохнуть", "🟢 Вернуться в поиск",
    "🛌 Dam olish", "🟢 Qidirishga qaytish",
    "🛌 Take a rest", "🟢 Return to search"
]))
async def process_rest_button(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in DATABASE:
        await message.answer(get_t(user_id, "no_profile"))
        return

    if user_id in INACTIVE_USERS:
        INACTIVE_USERS.remove(user_id)
        await message.answer(get_t(user_id, "profile_activated"), reply_markup=get_main_menu_keyboard(user_id))
        await cmd_search(message, state)
    else:
        await state.set_state(RestStates.menu)
        await message.answer(get_t(user_id, "rest_menu"), reply_markup=get_rest_menu_keyboard(user_id))


@dp.message(RestStates.menu)
async def process_rest_menu_actions(message: types.Message, state: FSMContext):
    text = message.text.lower()
    user_id = message.from_user.id

    if "назад" in text or "orqaga" in text or "back" in text:
        await state.set_state(RegistrationStates.active)
        await message.answer("Menu:", reply_markup=get_main_menu_keyboard(user_id))
        return

    if "скрыть" in text or "yashirish" in text or "hide" in text:
        INACTIVE_USERS.add(user_id)
        await state.set_state(RegistrationStates.active)
        await message.answer(get_t(user_id, "profile_hided"), reply_markup=get_main_menu_keyboard(user_id))
        return

    if "удалить" in text or "o'chirish" in text or "delete" in text:
        await delete_user_from_db(user_id)
        INACTIVE_USERS.discard(user_id)
        LIKES.pop(user_id, None)
        INCOMING_LIKES.pop(user_id, None)
        await state.clear()
        await message.answer(get_t(user_id, "profile_deleted"), reply_markup=types.ReplyKeyboardRemove())
        return

    await message.answer(get_t(user_id, "menu_fallback"), reply_markup=get_rest_menu_keyboard(user_id))


@dp.message(F.text.in_([
    "📝 Создать свою анкету", "✏️ Изменить анкету",
    "📝 O'z anketangizni yaratish", "✏️ Anketani o'zgartirish",
    "📝 Create profile", "✏️ Edit profile"
]))
async def process_create_or_edit_profile(message: types.Message, state: FSMContext):
    await state.set_state(RegistrationStates.waiting_for_name)
    user_id = message.from_user.id
    await message.answer(get_t(user_id, "name_prompt"), reply_markup=types.ReplyKeyboardRemove())


@dp.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith('/'):
        await message.answer(get_t(user_id, "name_cmd_error"))
        return
    await state.update_data(name=message.text)
    await state.set_state(RegistrationStates.waiting_for_age)
    await message.answer(get_t(user_id, "age_prompt"))


@dp.message(RegistrationStates.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith('/'):
        await message.answer(get_t(user_id, "age_cmd_error"))
        return
    if not message.text.isdigit():
        await message.answer(get_t(user_id, "age_error_digit"))
        return

    age = int(message.text)
    if not (16 <= age <= 70):
        await message.answer(get_t(user_id, "age_error_range"))
        return

    await state.update_data(age=age)
    await state.set_state(RegistrationStates.waiting_for_location)
    await message.answer(get_t(user_id, "location_prompt"), reply_markup=get_location_keyboard(user_id))


@dp.message(RegistrationStates.waiting_for_location, F.location)
async def process_location(message: types.Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    await state.update_data(city="Ташкент", latitude=lat, longitude=lon)
    await state.set_state(RegistrationStates.waiting_for_description)
    user_id = message.from_user.id
    await message.answer(get_t(user_id, "desc_prompt"), reply_markup=types.ReplyKeyboardRemove())


@dp.message(RegistrationStates.waiting_for_location)
async def process_location_fallback(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await message.answer(get_t(user_id, "location_fallback"))


@dp.message(RegistrationStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if message.text and message.text.startswith('/'):
        await message.answer(get_t(user_id, "desc_cmd_error"))
        return
    await state.update_data(description=message.text, media=[])
    await state.set_state(RegistrationStates.waiting_for_media)
    await message.answer(get_t(user_id, "media_prompt"))


@dp.message(RegistrationStates.waiting_for_media)
async def process_media(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    user_data = await state.get_data()
    media_list = user_data.get("media", [])

    if message.text and message.text.lower() in ["готово", "done", "tayyor"]:
        if len(media_list) == 0:
            await message.answer(get_t(user_id, "media_error"))
            return
        await finish_registration(message, state)
        return

    if message.photo:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"

        is_nsfw = await check_image_nsfw(file_url)
        if is_nsfw:
            await message.answer(get_t(user_id, "nsfw_error"))
            return

        media_list.append(("photo", photo.file_id))
    elif message.video:
        media_list.append(("video", message.video.file_id))
    else:
        await message.answer(get_t(user_id, "media_type_error"))
        return

    await state.update_data(media=media_list)
    if len(media_list) >= 3:
        await finish_registration(message, state)
    else:
        remaining = 3 - len(media_list)
        await message.answer(get_t(user_id, "media_saved").format(remaining=remaining))


async def finish_registration(message: types.Message, state: FSMContext):
    await state.set_state(RegistrationStates.waiting_for_gender)
    user_id = message.from_user.id
    await message.answer(get_t(user_id, "gender_prompt"), reply_markup=get_gender_reply_keyboard(user_id))


@dp.message(RegistrationStates.waiting_for_gender)
async def process_gender(message: types.Message, state: FSMContext):
    text = message.text.lower()
    user_id = message.from_user.id

    if "парень" in text or "yigitman" in text or "guy" in text:
        gender = "male"
    elif "девушка" in text or "qizman" in text or "girl" in text:
        gender = "female"
    else:
        await message.answer(get_t(user_id, "gender_error"))
        return

    await state.update_data(gender=gender)
    await state.set_state(RegistrationStates.waiting_for_preference)
    await message.answer(get_t(user_id, "preference_prompt"), reply_markup=get_preference_reply_keyboard(user_id))


@dp.message(RegistrationStates.waiting_for_preference)
async def process_preference(message: types.Message, state: FSMContext):
    text = message.text.lower()
    user_id = message.from_user.id

    if "парни" in text or "yigitlar" in text or "guys" in text:
        pref = "male"
    elif "девушки" in text or "qizlar" in text or "girls" in text:
        pref = "female"
    elif "все" in text or "barchasi" in text or "everyone" in text:
        pref = "all"
    else:
        await message.answer(get_t(user_id, "gender_error"))
        return

    await state.update_data(preference=pref)
    final_data = await state.get_data()
    final_data["username"] = message.from_user.username

    # Сохраняем в БД и память
    await save_user_to_db(user_id, final_data)
    INACTIVE_USERS.discard(user_id)

    await state.set_state(RegistrationStates.active)
    await message.answer(get_t(user_id, "registration_done"), reply_markup=get_main_menu_keyboard(user_id))


@dp.message(Command("search"))
@dp.message(F.text.in_([
    "🔍 Искать анкеты", "🔍 Продолжить поиск",
    "🔍 Anketalarni qidirish", "🔍 Qidirishni davom ettirish",
    "🔍 Search profiles", "🔍 Continue search"
]))
async def cmd_search(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id not in DATABASE:
        await message.answer(get_t(user_id, "no_profile"), reply_markup=get_main_menu_keyboard(user_id))
        return

    if user_id in INACTIVE_USERS:
        await message.answer(get_t(user_id, "profile_hidden"), reply_markup=get_main_menu_keyboard(user_id))
        return

    user_data = DATABASE[user_id]
    await state.set_data(user_data)

    incoming_list = INCOMING_LIKES.get(user_id, [])
    incoming_profiles = []
    for uid in incoming_list:
        if uid in DATABASE and uid not in INACTIVE_USERS:
            if uid not in LIKES.get(user_id, set()):
                incoming_profiles.append((uid, DATABASE[uid]))

    general_profiles = []
    for uid, profile in DATABASE.items():
        if uid == user_id or uid in INACTIVE_USERS:
            continue
        if any(uid == inc_id for inc_id, _ in incoming_profiles):
            continue
        if uid in LIKES.get(user_id, set()):
            continue
        general_profiles.append((uid, profile))

    await state.update_data(
        incoming_queue=incoming_profiles,
        general_queue=general_profiles,
        is_incoming_phase=len(incoming_profiles) > 0,
        search_index=0
    )
    await state.set_state(SearchStates.browsing)
    await message.answer(get_t(user_id, "search_started"))
    await show_next_profile(message, state)


async def show_next_profile(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    is_incoming = user_data.get("is_incoming_phase", True)
    incoming_queue = user_data.get("incoming_queue", [])
    general_queue = user_data.get("general_queue", [])
    index = user_data.get("search_index", 0)

    target_uid = None
    profile = None

    if is_incoming:
        if index < len(incoming_queue):
            target_uid, profile = incoming_queue[index]
        else:
            is_incoming = False
            index = 0
            await state.update_data(is_incoming_phase=False, search_index=0)
            if general_queue:
                target_uid, profile = general_queue[0]
    else:
        if index < len(general_queue):
            target_uid, profile = general_queue[index]

    user_id = message.from_user.id
    if not profile:
        await state.set_state(RegistrationStates.active)
        await message.answer(get_t(user_id, "no_more_profiles"), reply_markup=get_main_menu_keyboard(user_id))
        return

    await state.update_data(search_index=index + 1, current_profile=profile, current_target_uid=target_uid)

    name = profile.get("name")
    age = profile.get("age")
    desc = profile.get("description")
    media_list = profile.get("media", [])

    viewer_lat = DATABASE.get(user_id, {}).get("latitude")
    viewer_lon = DATABASE.get(user_id, {}).get("longitude")
    dist = calculate_distance(viewer_lat, viewer_lon, profile.get("latitude"), profile.get("longitude"))
    distance_str = f"📍 {dist} км – " if dist is not None else ""

    caption_text = f"{name}, {age}, {distance_str}{desc}"
    keyboard = get_search_control_keyboard(user_id)

    if len(media_list) > 0:
        m_type, file_id = media_list[0]
        if m_type == "photo":
            await message.answer_photo(photo=file_id, caption=caption_text, reply_markup=keyboard)
        else:
            await message.answer_video(video=file_id, caption=caption_text, reply_markup=keyboard)
    else:
        await message.answer(caption_text, reply_markup=keyboard)


@dp.message(SearchStates.waiting_for_message)
async def process_user_message_to_target(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    target_uid = user_data.get("current_target_uid")
    user_id = message.from_user.id
    text = message.text

    if text and text.lower() in ["❌ отменить", "❌ bekor qilish", "❌ cancel"]:
        await state.set_state(SearchStates.browsing)
        await message.answer(get_t(user_id, "msg_cancelled"), reply_markup=get_search_control_keyboard(user_id))
        return

    if target_uid:
        if user_id not in LIKES:
            LIKES[user_id] = set()
        LIKES[user_id].add(target_uid)

        if not (1000 <= target_uid <= 2000):
            try:
                sender_name = DATABASE.get(user_id, {}).get("name", "Пользователь")
                msg_notification = f"💌 {sender_name} оставил(а) для вас сообщение и лайк:\n\n{text}"
                await bot.send_message(chat_id=target_uid, text=msg_notification)
            except Exception as e:
                logging.error(f"Error sending message: {e}")

            if user_id in LIKES.get(target_uid, set()):
                my_profile = DATABASE.get(user_id, {})
                target_profile = DATABASE.get(target_uid, {})
                match_text = get_t(user_id, "match_text")
                await send_profile_to_user(user_id, target_profile, match_text)
                await send_profile_to_user(target_uid, my_profile, match_text)
            else:
                if target_uid not in INCOMING_LIKES:
                    INCOMING_LIKES[target_uid] = []
                if user_id not in INCOMING_LIKES[target_uid]:
                    INCOMING_LIKES[target_uid].append(user_id)

        await message.answer(get_t(user_id, "msg_sent"))

    await state.set_state(SearchStates.browsing)
    await message.answer("Следующая анкета:", reply_markup=get_search_control_keyboard(user_id))
    await show_next_profile(message, state)


@dp.message(SearchStates.browsing)
async def process_search_actions(message: types.Message, state: FSMContext):
    text = message.text.lower()
    user_data = await state.get_data()
    user_id = message.from_user.id

    if "стоп" in text or "остановить" in text or "to'xtatish" in text or "stop" in text:
        await state.set_state(RegistrationStates.active)
        await message.answer(get_t(user_id, "search_stopped"), reply_markup=get_main_menu_keyboard(user_id))
        return

    if "сообщение" in text or "оставить" in text or "xabar" in text or "message" in text:
        await state.set_state(SearchStates.waiting_for_message)
        await message.answer(get_t(user_id, "write_msg_prompt"), reply_markup=get_cancel_message_keyboard(user_id))
        return

    if "лайк" in text or "like" in text:
        target_user_id = user_data.get("current_target_uid")
        if target_user_id:
            if user_id not in LIKES:
                LIKES[user_id] = set()
            LIKES[user_id].add(target_user_id)

            if not (1000 <= target_user_id <= 2000):
                if user_id in LIKES.get(target_user_id, set()):
                    match_text = get_t(user_id, "match_text")
                    await send_profile_to_user(user_id, DATABASE.get(target_user_id, {}), match_text)
                    await send_profile_to_user(target_user_id, DATABASE.get(user_id, {}), match_text)
                else:
                    if target_user_id not in INCOMING_LIKES:
                        INCOMING_LIKES[target_user_id] = []
                    if user_id not in INCOMING_LIKES[target_user_id]:
                        INCOMING_LIKES[target_user_id].append(user_id)

            await message.answer(get_t(user_id, "like"))
        await show_next_profile(message, state)
        return

    if "не нрав" in text or "yoqmadi" in text or "dislike" in text:
        await message.answer(get_t(user_id, "dislike"))
        await show_next_profile(message, state)
        return


async def handle_ping(request):
    return web.Response(text="Bot is running!")


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    await init_db()
    add_fake_profiles()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_broadcast, "interval", hours=8)
    scheduler.start()

    asyncio.create_task(web_server())
    logging.info("Starting bot polling & scheduler...")
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())