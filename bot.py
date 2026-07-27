import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8860695938:AAG7aXjkOW3iiin-41jp2gqAeA8e-pGmgn4"

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Глобальные структуры данных в памяти:
DATABASE = {}
LIKES = {}  # user_id: set(liked_user_ids)
INCOMING_LIKES = {}  # user_id: [user_ids who liked them]


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


def get_language_keyboard():
  return types.InlineKeyboardMarkup(
      inline_keyboard=[
          [
              types.InlineKeyboardButton(
                  text="🇷🇺 Русский", callback_data="lang_ru"
              ),
              types.InlineKeyboardButton(
                  text="🇺🇿 O'zbekcha", callback_data="lang_uz"
              ),
          ],
          [
              types.InlineKeyboardButton(
                  text="🇬🇧 English", callback_data="lang_en"
              )
          ],
      ]
  )


def get_gender_reply_keyboard(lang):
  if lang == "uz":
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="👨 Yigitman"),
                types.KeyboardButton(text="👩 Qizman"),
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
  elif lang == "en":
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="👨 I'm a guy"),
                types.KeyboardButton(text="👩 I'm a girl"),
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
  else:
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="👨 Я парень"),
                types.KeyboardButton(text="👩 Я девушка"),
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_preference_reply_keyboard(lang):
  if lang == "uz":
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="👨 Yigitlar"),
                types.KeyboardButton(text="👩 Qizlar"),
            ],
            [types.KeyboardButton(text="🌐 Farqi yo'q (Barchasi)")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
  elif lang == "en":
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="👨 Guys"),
                types.KeyboardButton(text="👩 Girls"),
            ],
            [types.KeyboardButton(text="🌐 Everyone")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
  else:
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="👨 Парни"),
                types.KeyboardButton(text="👩 Девушки"),
            ],
            [types.KeyboardButton(text="🌐 Все")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_profile_reply_keyboard(lang):
  if lang == "uz":
    btn_text = "📝 Anketani yaratish"
  elif lang == "en":
    btn_text = "📝 Create profile"
  else:
    btn_text = "📝 Создать свою анкету"

  return types.ReplyKeyboardMarkup(
      keyboard=[[types.KeyboardButton(text=btn_text)]],
      resize_keyboard=True,
      is_persistent=True,
  )


def get_location_keyboard(lang):
  if lang == "uz":
    btn_text = "📍 Joylashuvni yuborish"
  elif lang == "en":
    btn_text = "📍 Send location"
  else:
    btn_text = "📍 Отправить локацию"

  return types.ReplyKeyboardMarkup(
      keyboard=[[types.KeyboardButton(text=btn_text, request_location=True)]],
      resize_keyboard=True,
      one_time_keyboard=True,
  )


def get_search_control_keyboard(lang, profile_gender):
  is_female = profile_gender == "female"

  if lang == "uz":
    like_text = "❤️ Yoqdi (Qiz)" if is_female else "❤️ Yoqdi (Yigit)"
    dislike_text = "💔 Yoqmadi"
    msg_text = "💌 Xabar qoldirish"
    stop_text = "🛑 Qidiruvni to'xtatish"
  elif lang == "en":
    like_text = "❤️ Like"
    dislike_text = "💔 Dislike"
    msg_text = "💌 Leave message"
    stop_text = "🛑 Stop search"
  else:
    if is_female:
      like_text = "❤️ Понравилась"
      dislike_text = "💔 Не понравилась"
    else:
      like_text = "❤️ Понравился"
      dislike_text = "💔 Не понравился"
    msg_text = "💌 Оставить сообщение"
    stop_text = "🛑 Остановить поиск"

  return types.ReplyKeyboardMarkup(
      keyboard=[
          [
              types.KeyboardButton(text=like_text),
              types.KeyboardButton(text=dislike_text),
          ],
          [types.KeyboardButton(text=msg_text)],
          [types.KeyboardButton(text=stop_text)],
      ],
      resize_keyboard=True,
  )


def get_cancel_message_keyboard(lang):
  if lang == "uz":
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True,
    )
  elif lang == "en":
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ Cancel")]], resize_keyboard=True
    )
  else:
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="❌ Отменить")]], resize_keyboard=True
    )


async def send_profile_to_user(
    recipient_id: int, profile_data: dict, intro_text: str
):
  name = profile_data.get("name")
  age = profile_data.get("age")
  city = profile_data.get("city", "Ташкент")
  desc = profile_data.get("description")
  media_list = profile_data.get("media", [])
  username = profile_data.get("username")

  if username:
    caption_text = (
        f"{intro_text}\n\n{name}, {age}, {city} —"
        f" {desc}\n\n🔗 Контакт: @{username}"
    )
  else:
    caption_text = (
        f"{intro_text}\n\n{name}, {age}, {city} — {desc}\n\n🔗 Контакт: Скрыт"
        " (нет юзернейма)"
    )

  try:
    if len(media_list) == 1:
      m_type, file_id = media_list[0]
      if m_type == "photo":
        await bot.send_photo(
            chat_id=recipient_id, photo=file_id, caption=caption_text
        )
      else:
        await bot.send_video(
            chat_id=recipient_id, video=file_id, caption=caption_text
        )
    elif len(media_list) > 1:
      album_builder = []
      for idx, (m_type, file_id) in enumerate(media_list):
        if m_type == "photo":
          if idx == 0:
            album_builder.append(
                types.InputMediaPhoto(media=file_id, caption=caption_text)
            )
          else:
            album_builder.append(types.InputMediaPhoto(media=file_id))
        else:
          if idx == 0:
            album_builder.append(
                types.InputMediaVideo(media=file_id, caption=caption_text)
            )
          else:
            album_builder.append(types.InputMediaVideo(media=file_id))
      await bot.send_media_group(chat_id=recipient_id, media=album_builder)
    else:
      await bot.send_message(chat_id=recipient_id, text=caption_text)
  except Exception as e:
    logging.error(f"Error sending profile to {recipient_id}: {e}")


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
  await state.clear()
  await state.set_state(RegistrationStates.waiting_for_language)
  await message.answer(
      "Привет! Пожалуйста, выберите язык:\nTilni tanlang:\nPlease choose your"
      " language:",
      reply_markup=get_language_keyboard(),
  )


@dp.message(Command("language"))
async def cmd_language(message: types.Message, state: FSMContext):
  await state.set_state(RegistrationStates.waiting_for_language)
  await message.answer(
      "Выберите язык / Tilni tanlang / Choose language:",
      reply_markup=types.ReplyKeyboardRemove(),
  )
  await message.answer(
      "⬇️ Выберите язык ниже:", reply_markup=get_language_keyboard()
  )


@dp.callback_query(F.data.startswith("lang_"))
async def process_language(callback: types.CallbackQuery, state: FSMContext):
  lang = callback.data.split("_")[1]
  await state.update_data(language=lang)

  if lang == "ru":
    text = (
        "Новая платформа знакомств в Узбекистане 🔥\nУспей найти своих"
        " компашек 💁\n\nДавай начнем! Нажми кнопку внизу, чтобы создать"
        " анкету."
    )
  elif lang == "uz":
    text = (
        "O'zbekistonda yangi tanishuv platformasi 🔥\nO'z kompaniyangizni"
        " topishga shoshiling 💁\n\nBoshladik! Anketani yaratish uchun"
        " pastdagi tugmani bosing."
    )
  elif lang == "en":
    text = (
        "New dating platform in Uzbekistan 🔥\nHurry up to find your company"
        " 💁\n\nLet's start! Click the button below to create your profile."
    )
  else:
    text = "Language selected!"

  await callback.message.answer(
      text, reply_markup=get_profile_reply_keyboard(lang)
  )
  await callback.answer()


@dp.message(
    F.text.in_(
        ["📝 Создать свою анкету", "📝 Anketani yaratish", "📝 Create profile"]
    )
)
async def process_create_profile(message: types.Message, state: FSMContext):
  await state.set_state(RegistrationStates.waiting_for_name)
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  if lang == "uz":
    await message.answer(
        "1️⃣ Ismingizni kiriting:", reply_markup=types.ReplyKeyboardRemove()
    )
  elif lang == "en":
    await message.answer(
        "1️⃣ Please enter your name:", reply_markup=types.ReplyKeyboardRemove()
    )
  else:
    await message.answer(
        "1️⃣ Как вас зовут? Введите ваше имя:",
        reply_markup=types.ReplyKeyboardRemove(),
    )


@dp.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
  await state.update_data(name=message.text)
  await state.set_state(RegistrationStates.waiting_for_age)
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  if lang == "uz":
    await message.answer("2️⃣ Yoshingiz nechida? (Masalan: 20):")
  elif lang == "en":
    await message.answer("2️⃣ How old are you? (e.g. 20):")
  else:
    await message.answer("2️⃣ Сколько вам лет? (Введите число, например: 20):")


@dp.message(RegistrationStates.waiting_for_age)
async def process_age(message: types.Message, state: FSMContext):
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  if not message.text.isdigit():
    if lang == "uz":
      await message.answer(
          "Iltimos, yoshingizni faqat raqamlarda kiriting (masalan: 20):"
      )
    elif lang == "en":
      await message.answer(
          "Please enter your age using numbers only (e.g. 20):"
      )
    else:
      await message.answer(
          "Пожалуйста, введите возраст цифрами (например: 20):"
      )
    return

  age = int(message.text)

  if not (16 <= age <= 70):
    if lang == "uz":
      await message.answer(
          "Yoshingiz 16 dan 70 gacha bo'lishi kerak. Qaytadan kiriting:"
      )
    elif lang == "en":
      await message.answer(
          "Age must be between 16 and 70. Please enter again:"
      )
    else:
      await message.answer(
          "Возраст должен быть от 16 до 70 лет. Пожалуйста, введите"
          " корректное число:"
      )
    return

  await state.update_data(age=age)
  await state.set_state(RegistrationStates.waiting_for_location)

  if lang == "uz":
    text = (
        "3️⃣ Yashashingiz hududni aniqlash uchun lokatsiyatingizni yuboring:"
    )
  elif lang == "en":
    text = "3️⃣ Please send your location to determine your city:"
  else:
    text = (
        "3️⃣ Пожалуйста, отправьте вашу локацию, чтобы указать город в"
        " анкете:"
    )

  await message.answer(text, reply_markup=get_location_keyboard(lang))


@dp.message(RegistrationStates.waiting_for_location, F.location)
async def process_location(message: types.Message, state: FSMContext):
  city = "Ташкент"
  await state.update_data(city=city)
  await state.set_state(RegistrationStates.waiting_for_description)
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  if lang == "uz":
    await message.answer(
        "4️⃣ O'zingiz haqingizda qisqacha yozing (Opisaniya):",
        reply_markup=types.ReplyKeyboardRemove(),
    )
  elif lang == "en":
    await message.answer(
        "4️⃣ Write a short description about yourself:",
        reply_markup=types.ReplyKeyboardRemove(),
    )
  else:
    await message.answer(
        "4️⃣ Расскажите немного о себе (Напишите описание):",
        reply_markup=types.ReplyKeyboardRemove(),
    )


@dp.message(RegistrationStates.waiting_for_location)
async def process_location_fallback(message: types.Message, state: FSMContext):
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")
  if lang == "uz":
    await message.answer("Iltimos, tugmani bosib lokatsiya yuboring 📍")
  elif lang == "en":
    await message.answer("Please send your location using the button 📍")
  else:
    await message.answer("Пожалуйста, отправьте локацию с помощью кнопки 📍")


@dp.message(RegistrationStates.waiting_for_description)
async def process_description(message: types.Message, state: FSMContext):
  await state.update_data(description=message.text)
  await state.update_data(media=[])
  await state.set_state(RegistrationStates.waiting_for_media)
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  if lang == "uz":
    await message.answer(
        "5️⃣ Endi 1 tadan 3 tagacha rasm yoki video yuboring.\n"
        "Barchasini yuborib bo'lgach, **Tayyor** deb yozing."
    )
  elif lang == "en":
    await message.answer(
        "5️⃣ Now send from 1 to 3 photos or videos.\n"
        "When you are finished, type **Ready**."
    )
  else:
    await message.answer(
        "5️⃣ Теперь отправьте от 1 до 3 фото или видео.\n"
        "Когда закончите отправку файлов, напишите слово **Готово**."
    )


async def finish_registration(message: types.Message, state: FSMContext):
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  name = user_data.get("name")
  age = user_data.get("age")
  city = user_data.get("city", "Ташкент")
  desc = user_data.get("description")
  media_list = user_data.get("media", [])

  caption_text = f"{name}, {age}, {city} — {desc}"

  if len(media_list) == 1:
    m_type, file_id = media_list[0]
    if m_type == "photo":
      await message.answer_photo(photo=file_id, caption=caption_text)
    else:
      await message.answer_video(video=file_id, caption=caption_text)
  elif len(media_list) > 1:
    album_builder = []
    for idx, (m_type, file_id) in enumerate(media_list):
      if m_type == "photo":
        if idx == 0:
          album_builder.append(
              types.InputMediaPhoto(media=file_id, caption=caption_text)
          )
        else:
          album_builder.append(types.InputMediaPhoto(media=file_id))
      else:
        if idx == 0:
          album_builder.append(
              types.InputMediaVideo(media=file_id, caption=caption_text)
          )
        else:
          album_builder.append(types.InputMediaVideo(media=file_id))

    await message.answer_media_group(media=album_builder)

  if lang == "uz":
    await message.answer(
        "✅ Anketangiz muvaffaqiyatli yaratildi!\n\nEndi davom"
        " etamiz. Jinsingizni tanlang:"
    )
  elif lang == "en":
    await message.answer(
        "✅ Your profile has been successfully created!\n\nLet's continue."
        " Select your gender:"
    )
  else:
    await message.answer(
        "✅ Ваша анкета успешно создана!\n\nИдем дальше. Определимся с полом:"
    )

  await state.set_state(RegistrationStates.waiting_for_gender)
  await message.answer(
      "Выберите ваш пол:"
      if lang == "ru"
      else ("Jinsingizni tanlang:" if lang == "uz" else "Select your gender:"),
      reply_markup=get_gender_reply_keyboard(lang),
  )


@dp.message(RegistrationStates.waiting_for_gender)
async def process_gender(message: types.Message, state: FSMContext):
  text = message.text.lower()
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  if "парень" in text or "guy" in text or "yigitman" in text:
    gender = "male"
  elif "девушка" in text or "girl" in text or "qizman" in text:
    gender = "female"
  else:
    if lang == "uz":
      await message.answer("Iltimos, tugmalardan birini bosing!")
    elif lang == "en":
      await message.answer("Please use the buttons below!")
    else:
      await message.answer("Пожалуйста, выберите вариант с помощью кнопок!")
    return

  await state.update_data(gender=gender)
  await state.set_state(RegistrationStates.waiting_for_preference)

  if lang == "uz":
    pref_text = "Kimlar sizni qiziqtiradi?"
  elif lang == "en":
    pref_text = "Who are you interested in?"
  else:
    pref_text = "Кто тебе интересен?"

  await message.answer(
      pref_text, reply_markup=get_preference_reply_keyboard(lang)
  )


@dp.message(RegistrationStates.waiting_for_preference)
async def process_preference(message: types.Message, state: FSMContext):
  text = message.text.lower()
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")

  if "парни" in text or "guys" in text or "yigitlar" in text:
    pref = "male"
  elif "девушки" in text or "girls" in text or "qizlar" in text:
    pref = "female"
  elif (
      "все" in text
      or "everyone" in text
      or "farqi" in text
      or "barchasi" in text
  ):
    pref = "all"
  else:
    if lang == "uz":
      await message.answer("Iltimos, tugmalardan birini bosing!")
    elif lang == "en":
      await message.answer("Please use the buttons below!")
    else:
      await message.answer("Пожалуйста, выберите вариант с помощью кнопок!")
    return

  await state.update_data(preference=pref)

  final_data = await state.get_data()
  user_id = message.from_user.id
  final_data["username"] = message.from_user.username
  DATABASE[user_id] = final_data

  await state.set_state(RegistrationStates.active)

  if lang == "uz":
    final_text = "🎉 Hammasi tayyor! Odamlarni qidirishni boshlash uchun /search buyrug'ini yuboring."
  elif lang == "en":
    final_text = "🎉 All set! Send /search to start searching for people."
  else:
    final_text = "🎉 Все готово! Нажми /search, чтобы начать поиск людей."

  await message.answer(final_text, reply_markup=types.ReplyKeyboardRemove())


@dp.message(RegistrationStates.waiting_for_media)
async def process_media(message: types.Message, state: FSMContext):
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")
  media_list = user_data.get("media", [])

  if message.text and message.text.lower() in [
      "готово",
      "tayyor",
      "ready",
      "done",
  ]:
    if len(media_list) == 0:
      if lang == "uz":
        await message.answer("Iltimos, kamida bitta rasm yoki video yuboring!")
      elif lang == "en":
        await message.answer("Please send at least one photo or video!")
      else:
        await message.answer(
            "Пожалуйста, отправьте хотя бы одно фото или видео!"
        )
      return

    await finish_registration(message, state)
    return

  if message.photo:
    file_id = message.photo[-1].file_id
    media_list.append(("photo", file_id))
  elif message.video:
    file_id = message.video.file_id
    media_list.append(("video", file_id))
  else:
    if lang == "uz":
      await message.answer(
          "Iltimos, rasm/video yuboring yoki 'Tayyor' deb yozing."
      )
    elif lang == "en":
      await message.answer("Please send a photo/video or type 'Ready'.")
    else:
      await message.answer(
          "Пожалуйста, отправьте фото или видео, либо напишите «Готово»."
      )
    return

  await state.update_data(media=media_list)

  if len(media_list) >= 3:
    await finish_registration(message, state)
  else:
    remaining = 3 - len(media_list)
    if lang == "uz":
      await message.answer(
          f"Qabul qilindi! Yana {remaining} ta rasm/video yuborishingiz"
          " mumkin yoki **Tayyor** deb yozing."
      )
    elif lang == "en":
      await message.answer(
          f"Received! You can send {remaining} more photo/video or type"
          " **Ready**."
      )
    else:
      await message.answer(
          f"Принято! Можете отправить еще {remaining} файл(а) или написать"
          " **Готово**."
      )


@dp.message(Command("search"))
async def cmd_search(message: types.Message, state: FSMContext):
  user_id = message.from_user.id

  if user_id not in DATABASE:
    await message.answer("Сначала создайте свою анкету! Нажмите /start")
    return

  user_data = DATABASE[user_id]
  await state.set_data(user_data)
  lang = user_data.get("language", "ru")

  incoming_list = INCOMING_LIKES.get(user_id, [])
  incoming_profiles = []
  for uid in incoming_list:
    if uid in DATABASE:
      my_liked_set = LIKES.get(user_id, set())
      if uid not in my_liked_set:
        incoming_profiles.append((uid, DATABASE[uid]))

  general_profiles = []
  for uid, profile in DATABASE.items():
    if uid == user_id:
      continue

    if any(uid == inc_id for inc_id, _ in incoming_profiles):
      continue

    my_liked_set = LIKES.get(user_id, set())
    if uid in my_liked_set:
      continue

    general_profiles.append((uid, profile))

  await state.update_data(
      incoming_queue=incoming_profiles,
      general_queue=general_profiles,
      is_incoming_phase=len(incoming_profiles) > 0,
      search_index=0,
  )
  await state.set_state(SearchStates.browsing)

  if lang == "uz":
    await message.answer("🔍 Qidiruv boshlandi!")
  elif lang == "en":
    await message.answer("🔍 Search started!")
  else:
    await message.answer("🔍 Поиск запущен!")

  if incoming_profiles:
    if lang == "uz":
      await message.answer(
          "💖 Kimdir sizga qiziqish bildirgan! Mana uning anketasi:"
      )
    elif lang == "en":
      await message.answer(
          "💖 Someone showed interest in you! Here is their profile:"
      )
    else:
      await message.answer(
          "💖 Кто-то заинтересовался вашей анкетой! Посмотрите:"
      )

  await show_next_profile(message, state)


async def show_next_profile(message: types.Message, state: FSMContext):
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")
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

  if not profile:
    await state.set_state(RegistrationStates.active)
    if lang == "uz":
      await message.answer(
          "Barcha anketalar ko'rib chiqildi!",
          reply_markup=types.ReplyKeyboardRemove(),
      )
    elif lang == "en":
      await message.answer(
          "All profiles have been viewed!",
          reply_markup=types.ReplyKeyboardRemove(),
      )
    else:
      await message.answer(
          "Вы посмотрели все доступные анкеты!",
          reply_markup=types.ReplyKeyboardRemove(),
      )
    return

  await state.update_data(
      search_index=index + 1,
      current_profile=profile,
      current_target_uid=target_uid,
  )

  name = profile.get("name")
  age = profile.get("age")
  city = profile.get("city", "Ташкент")
  desc = profile.get("description")
  media_list = profile.get("media", [])
  profile_gender = profile.get("gender", "male")

  caption_text = f"{name}, {age}, {city} — {desc}"
  keyboard = get_search_control_keyboard(lang, profile_gender)

  if len(media_list) > 0:
    m_type, file_id = media_list[0]
    if m_type == "photo":
      await message.answer_photo(
          photo=file_id, caption=caption_text, reply_markup=keyboard
      )
    else:
      await message.answer_video(
          video=file_id, caption=caption_text, reply_markup=keyboard
      )
  else:
    await message.answer(caption_text, reply_markup=keyboard)


@dp.message(SearchStates.browsing)
async def process_search_actions(message: types.Message, state: FSMContext):
  text = message.text.lower()
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")
  user_id = message.from_user.id

  if (
      "стоп" in text
      or "stop" in text
      or "to'xtatish" in text
      or "остановить" in text
  ):
    await state.set_state(RegistrationStates.active)
    if lang == "uz":
      await message.answer(
          "Qidiruv to'xtatildi.", reply_markup=types.ReplyKeyboardRemove()
      )
    elif lang == "en":
      await message.answer(
          "Search stopped.", reply_markup=types.ReplyKeyboardRemove()
      )
    else:
      await message.answer(
          "Поиск завершен.", reply_markup=types.ReplyKeyboardRemove()
      )
    return

  if (
      "сообщение" in text
      or "message" in text
      or "xabar" in text
      or "оставить" in text
  ):
    await state.set_state(SearchStates.waiting_for_message)
    if lang == "uz":
      await message.answer(
          "Iltimos, ushbu foydalanuvchiga yubormoqchi bo'lgan xabaringizni"
          " yozing:",
          reply_markup=get_cancel_message_keyboard(lang),
      )
    elif lang == "en":
      await message.answer(
          "Please write the message you want to send to this user:",
          reply_markup=get_cancel_message_keyboard(lang),
      )
    else:
      await message.answer(
          "Напишите текст сообщения, которое хотите отправить этому"
          " пользователю:",
          reply_markup=get_cancel_message_keyboard(lang),
      )
    return

  if any(word in text for word in ["лайк", "like", "yoqdi", "понрав"]):
    target_user_id = user_data.get("current_target_uid")

    print(
        f"\n[DEBUG] Пользователь {user_id} ставит лайк на цель {target_user_id}"
    )

    if target_user_id:
      if user_id not in LIKES:
        LIKES[user_id] = set()
      LIKES[user_id].add(target_user_id)

      target_liked_set = LIKES.get(target_user_id, set())
      is_mutual = user_id in target_liked_set

      print(f"[DEBUG] Лайки пользователя {user_id}: {LIKES[user_id]}")
      print(f"[DEBUG] Лайки цели {target_user_id}: {target_liked_set}")
      print(f"[DEBUG] Взаимность (is_mutual): {is_mutual}")

      if is_mutual:
        print(f"[DEBUG] СРАБОТАЛ MATCH МЕЖДУ {user_id} И {target_user_id}!")
        my_profile = DATABASE.get(user_id, {})
        target_profile = DATABASE.get(target_user_id, {})
        target_lang = target_profile.get("language", "ru")

        if lang == "uz":
          my_intro = "💖 O'zaro taassurot!"
        elif lang == "en":
          my_intro = "💖 It's a match!"
        else:
          my_intro = "💖 Это взаимно!"

        if target_lang == "uz":
          target_intro = "💖 O'zaro taassurot!"
        elif target_lang == "en":
          target_intro = "💖 It's a match!"
        else:
          target_intro = "💖 Это взаимно!"

        await send_profile_to_user(user_id, target_profile, my_intro)
        await send_profile_to_user(target_user_id, my_profile, target_intro)
      else:
        if target_user_id not in INCOMING_LIKES:
          INCOMING_LIKES[target_user_id] = []
        if user_id not in INCOMING_LIKES[target_user_id]:
          INCOMING_LIKES[target_user_id].append(user_id)

        if lang == "uz":
          await message.answer("❤️ Sizga bu anketa yoqdi!")
        elif lang == "en":
          await message.answer("❤️ You liked this profile!")
        else:
          await message.answer("❤️ Вы поставили лайк!")

        try:
          target_profile = DATABASE.get(target_user_id, {})
          target_lang = target_profile.get("language", "ru")

          if target_lang == "uz":
            notif_text = "❤️ Kimdir sizga yoqdi! Kimligini ko'rish uchun /search buyrug'ini yuboring."
          elif target_lang == "en":
            notif_text = "❤️ Someone liked you! Send /search to see who it is."
          else:
            notif_text = "❤️ Кому-то понравилась ваша анкета! Нажмите /search, чтобы посмотреть."

          await bot.send_message(target_user_id, notif_text)
        except Exception as e:
          print(f"[DEBUG ERROR] Ошибка отправки уведомления: {e}")

  elif any(word in text for word in ["не понрав", "dislike", "yoqmadi"]):
    if lang == "uz":
      await message.answer("💔 Keyingi anketa:")
    elif lang == "en":
      await message.answer("💔 Next profile:")
    else:
      await message.answer("💔 Пропускаем анкету:")

  await show_next_profile(message, state)


@dp.message(SearchStates.waiting_for_message)
async def process_user_message(message: types.Message, state: FSMContext):
  user_data = await state.get_data()
  lang = user_data.get("language", "ru")
  text = message.text

  if (
      "отменить" in text.lower()
      or "cancel" in text.lower()
      or "bekor" in text.lower()
  ):
    await state.set_state(SearchStates.browsing)
    if lang == "uz":
      await message.answer("Xabar yuborish bekor qilindi.")
    elif lang == "en":
      await message.answer("Message sending cancelled.")
    else:
      await message.answer("Отправка сообщения отменена.")

    profile = user_data.get("current_profile", {})
    profile_gender = profile.get("gender", "male")
    await message.answer(
        "Продолжаем просмотр:",
        reply_markup=get_search_control_keyboard(lang, profile_gender),
    )
    return

  target_user_id = user_data.get("current_target_uid")
  if target_user_id:
    try:
      my_name = user_data.get("name", "Пользователь")
      await bot.send_message(
          target_user_id,
          f"💌 У вас новое сообщение от пользователя {my_name}:\n\n{text}",
      )
    except Exception as e:
      logging.error(f"Не удалось отправить личное сообщение: {e}")

  if lang == "uz":
    await message.answer("✅ Xabaringiz egasiga yuborildi!")
  elif lang == "en":
    await message.answer("✅ Your message has been sent!")
  else:
    await message.answer("✅ Ваше сообщение успешно отправлено!")

  await state.set_state(SearchStates.browsing)
  profile = user_data.get("current_profile", {})
  profile_gender = profile.get("gender", "male")

  await message.answer(
      "Следующая анкета:",
      reply_markup=get_search_control_keyboard(lang, profile_gender),
  )
  await show_next_profile(message, state)


@dp.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext):
  user_id = message.from_user.id

  if user_id in DATABASE:
    user_data = DATABASE[user_id]
  else:
    user_data = await state.get_data()

  if "name" in user_data and "media" in user_data and user_data["media"]:
    name = user_data.get("name")
    age = user_data.get("age")
    city = user_data.get("city", "Ташкент")
    desc = user_data.get("description")
    media_list = user_data.get("media", [])

    caption_text = f"{name}, {age}, {city} — {desc}"

    if len(media_list) == 1:
      m_type, file_id = media_list[0]
      if m_type == "photo":
        await message.answer_photo(photo=file_id, caption=caption_text)
      else:
        await message.answer_video(video=file_id, caption=caption_text)
    else:
      album_builder = []
      for idx, (m_type, file_id) in enumerate(media_list):
        if m_type == "photo":
          if idx == 0:
            album_builder.append(
                types.InputMediaPhoto(media=file_id, caption=caption_text)
            )
          else:
            album_builder.append(types.InputMediaPhoto(media=file_id))
        else:
          if idx == 0:
            album_builder.append(
                types.InputMediaVideo(media=file_id, caption=caption_text)
            )
          else:
            album_builder.append(types.InputMediaVideo(media=file_id))

      await message.answer_media_group(media=album_builder)
  else:
    lang = user_data.get("language", "ru")
    if lang == "uz":
      await message.answer("Sizda hali anketa yo'q. /start")
    elif lang == "en":
      await message.answer("You don't have a profile yet. /start")
    else:
      await message.answer("У вас еще нет анкеты. Нажмите /start")


async def main():
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())