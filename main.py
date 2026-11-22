import asyncio
import json
import os
import re

from aiogram import Bot
from aiogram.dispatcher.dispatcher import Dispatcher
from aiogram.types import (URLInputFile, InlineKeyboardMarkup, InlineKeyboardButton,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton)
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from parser import getSoup, getDefinition, otherDefinitions, getImage

token = ""

bot = Bot(token=token)
dp = Dispatcher()

languages = {
    "ru": "русский",
    "en": "английский"
}

my_headers = {
    "User-Agent": "MyTelegramWikiBot/1.0 (https://t.me/ex ex@gmail.com)"
}

SETTINGS_FILE = "users_settings.json"

def default_settings():
    return {
        "search_language": "ru",
        "bot_language": "ru",
        "main_url": "https://ru.wikipedia.org",
        "last_url": "",
        "last_od_url": "",
    }


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Загружаем один раз при старте
users_settings = load_settings()

def get_user_settings(user_id):
    key = str(user_id)
    if key not in users_settings:
        users_settings[key] = default_settings()
    else:
        # на случай старых/неполных файлов
        base = default_settings()
        base.update(users_settings[key])
        users_settings[key] = base
    return users_settings[key]


@dp.message(Command("start"))
async def start(msg):
    get_user_settings(msg.from_user.id)
    save_settings(users_settings)

    await msg.answer("В случае некорретного вывода определения, "
                     "используйте /link, чтобы получить ссылку на страницу в Википедии по последнему запросу ")
    await msg.answer("Используйте /settings, чтобы открыть настройки поиска")
    await msg.answer("Напишите, что вы хотите найти в Википедии: ")


@dp.message(Command("link"))
async def get_last_link(msg):
    user_data = get_user_settings(msg.from_user.id)
    last = user_data.get("last_url") or "—"
    await msg.answer(f"Последняя запрошенная страница: {last}")


@dp.message(Command("settings"))
async def settings(msg):
    get_user_settings(msg.from_user.id)

    settings_markup = InlineKeyboardMarkup(inline_keyboard=[[]])
    lang_btn = InlineKeyboardButton(text="Язык поиска", callback_data="lang_btn")
    settings_markup.inline_keyboard[0].append(lang_btn)

    await msg.answer("Настройки бота:", reply_markup=settings_markup)


@dp.callback_query()
async def click_inline_button(call):
    user_id = call.from_user.id
    user_data = get_user_settings(user_id)

    if call.data == "lang_btn":
        lang_markup = InlineKeyboardMarkup(inline_keyboard=[[]])
        en_btn = InlineKeyboardButton(text="Английский", callback_data="en")
        lang_markup.inline_keyboard[0].append(en_btn)
        ru_btn = InlineKeyboardButton(text="Русский", callback_data="ru")
        lang_markup.inline_keyboard[0].append(ru_btn)

        await bot.edit_message_text("Выберите язык поиска: ",
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    reply_markup=lang_markup)

    if call.data in ("en", "ru"):
        user_data["search_language"] = call.data
        user_data["main_url"] = f"https://{call.data}.wikipedia.org"
        save_settings(users_settings)

        await bot.edit_message_text(f"Язык поиска сменён на {languages[call.data]}",
                                    chat_id=call.message.chat.id,
                                    message_id=call.message.message_id)


@dp.message()
async def find(msg):
    user_data = get_user_settings(msg.from_user.id)

    word = msg.text.replace(" ", "_")
    wiki_url = f"{user_data['main_url']}/wiki/{word}"

    soup = getSoup(word, f"{user_data['main_url']}/wiki/", my_headers)
    if soup is None:
        await msg.answer("Не удалось получить страницу из Википедии. Попробуйте позже.")
        return

    user_data["last_url"] = wiki_url
    save_settings(users_settings)

    raw_image = getImage(soup)
    image_url = None
    if raw_image:
        if raw_image.startswith("//"):
            image_url = "https:" + raw_image
        elif raw_image.startswith("http"):
            image_url = raw_image
        else:
            image_url = "https://" + raw_image.lstrip("/")

    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Ссылка на статью", url=wiki_url)
    ]])

    if otherDefinitions(soup):
        hatnote = soup.find("div", class_=re.compile("hatnote"))
        od_a = hatnote.find("a") if hatnote else None
        if od_a and od_a.get("href"):
            od_url = od_a.get("href")
            if od_url.startswith("//"):
                od_url = "https:" + od_url
            elif od_url.startswith("/"):
                od_url = f"{user_data['main_url']}{od_url}"
            markup.inline_keyboard[0].append(
                InlineKeyboardButton(text="Другие значения", url=od_url))

    # Многозначный термин
    if image_url and "Disambig.svg" in image_url:
        buttons = get_od_Keyboard(soup)
        if buttons:
            markup = ReplyKeyboardMarkup(
                keyboard=[buttons[0:2], buttons[2:4]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        else:
            markup = ReplyKeyboardRemove()

    # Нет статьи / нет картинки / словарная заглушка
    elif (not image_url) or ("Wiki_letter_w_dashed.svg" in image_url) \
            or ("Wiktionary-logo" in image_url):
        pass

    else:
        image = URLInputFile(url=image_url, headers=my_headers)
        await bot.send_photo(msg.chat.id, image)

    try:
        text = getDefinition(soup)[:4000] or "..."
        await msg.answer(text, reply_markup=markup)
    except TelegramBadRequest:
        await msg.answer("...", reply_markup=markup)


def get_od_Keyboard(soup):
    buttons = []
    container = soup.find("div", class_="vector-body")
    if container is None:
        return buttons

    uls = container.find_all("ul")
    for ul in uls:
        li = ul.find_all("li")
        for l in li:
            if l.get("class") is not None:
                break
            a = l.find("a")
            if len(buttons) < 4 and a is not None:
                buttons.append(KeyboardButton(text=a.text))
            else:
                break
        if len(buttons) >= 4:
            break

    return buttons


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())