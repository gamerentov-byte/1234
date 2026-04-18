import os
import logging
import json
import sqlite3
from dotenv import load_dotenv
import telebot
from telebot import types
from telebot.apihelper import ApiTelegramException
import requests
import uuid

load_dotenv()

if not all([os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("ADMIN_ID"), os.getenv("FRAGMENT_API_KEY")]):
    print("❌ Создай .env!")
    raise SystemExit(1)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
SUPPORT_USERNAME = "@lacostest_support"
REQUIRED_CHANNEL = "@lacostest_shop"
FRAGMENT_API_URL = "https://api.fragment-api.com/v1"
FRAGMENT_API_KEY = os.getenv("FRAGMENT_API_KEY")
FRAGMENT_PHONE = os.getenv("FRAGMENT_PHONE")
FRAGMENT_MNEMONICS = os.getenv("FRAGMENT_MNEMONICS")
STAR_PRICE_RUB = 1.3
REF_BONUS_PERCENT = 0.10
BOT_USERNAME = "Lacostest_shop_bot"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN_FILE = "fragment_token.json"
DB_FILE = "stars_bot.db"
CONFIG_FILE = "bot_config.json"
FRAGMENT_TOKEN = None
user_states = {}

STARS_IN_STOCK = True
MIN_STARS = 50

ABOUT_BOT_TEXT = (
    "📋 *Правила сервиса*\n\n"
    "🔒 *Правила использования сервиса:*\n\n"
    "Используя данного бота, вы подтверждаете, что ознакомлены с пользовательским соглашением, "
    "а также политикой конфиденциальности.\n\n"
    "Настоятельно напоминаем, что за нарушение правил пользования сервисом/вред сервису/"
    "незаконные действия — ваш аккаунт будет заблокирован❗️\n"
    "Окончательное решение принимает поддержка проекта и оспариванию не подлежит.\n\n"
    "Приятного использования🔥"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")

START_IMAGE = os.path.join(IMAGES_DIR, "start.jpg")
REFERRALS_IMAGE = os.path.join(IMAGES_DIR, "referrals.jpg")
SHOP_IMAGE = os.path.join(IMAGES_DIR, "shop.jpg")
CABINET_IMAGE = os.path.join(IMAGES_DIR, "cabinet.jpg")
OBOTE_IMAGE = os.path.join(IMAGES_DIR, "obote.jpg")


def load_config():
    global STARS_IN_STOCK, STAR_PRICE_RUB, MIN_STARS
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            STARS_IN_STOCK = config.get("stars_in_stock", True)
            STAR_PRICE_RUB = config.get("star_price", 1.3)
            MIN_STARS = config.get("min_stars", 50)


def save_config():
    config = {
        "stars_in_stock": STARS_IN_STOCK,
        "star_price": STAR_PRICE_RUB,
        "min_stars": MIN_STARS
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


load_config()


def safe_delete_message(chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def send_photo_or_message(chat_id, image_path, caption, reply_markup=None, parse_mode='Markdown', disable_web_page_preview=True):
    try:
        if image_path and os.path.isfile(image_path):
            file_size = os.path.getsize(image_path)
            logger.info(f"Проверка изображения: {image_path} | размер: {file_size} байт")

            if file_size > 0:
                with open(image_path, 'rb') as photo:
                    bot.send_photo(
                        chat_id=chat_id,
                        photo=photo,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                return
            else:
                logger.error(f"Файл пустой: {image_path}")
        else:
            logger.error(f"Файл не найден: {image_path}")

        bot.send_message(
            chat_id,
            caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )

    except Exception as e:
        logger.error(f"Ошибка отправки изображения {image_path}: {e}")
        bot.send_message(
            chat_id,
            caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )


def is_subscribed(user_id):
    if user_id == ADMIN_ID:
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except ApiTelegramException as e:
        logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
        err = str(e).lower()
        if "member list is inaccessible" in err:
            return None
        if "chat not found" in err:
            return None
        if "user not found" in err:
            return False
        return None
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return None


def show_subscription_prompt(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Подписаться", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}"))
    markup.add(types.InlineKeyboardButton("🔄 Проверить подписку", callback_data="check_subscription"))
    text = (
        f"🔒 *ПОДПИСКА ОБЯЗАТЕЛЬНА!* 🔒\n\n"
        f"📢 Подпишитесь на официальный канал:\n"
        f"👉 `{REQUIRED_CHANNEL}`\n\n"
        f"⚡ После подписки нажмите *«Проверить подписку»*\n\n"
        f"🎁 Только для подписчиков!"
    )
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='Markdown', disable_web_page_preview=True)


def show_about_menu(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("📄 Пользовательское соглашение", url="https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"),
        types.InlineKeyboardButton("🔐 Политика конфиденциальности", url="https://telegra.ph/Politika-konfidencialnosti-04-01-26")
    )
    markup.row(
        types.InlineKeyboardButton("💬 Тех.поддержка", url=f"https://t.me/{SUPPORT_USERNAME[1:]}"),
        types.InlineKeyboardButton("📢 Telegram канал", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")
    )
    markup.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"))

    send_photo_or_message(
        chat_id,
        OBOTE_IMAGE,
        ABOUT_BOT_TEXT,
        reply_markup=markup,
        parse_mode='Markdown'
    )


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance REAL DEFAULT 0,
        total_stars INTEGER DEFAULT 0,
        ref_code TEXT UNIQUE,
        referrer_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ref_count INTEGER DEFAULT 0,
        ref_bonus_total REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        referred_username TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        type TEXT,
        stars INTEGER,
        amount REAL,
        ref_bonus REAL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user


def user_exists(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def create_user(user_id, username, ref_code=None, referrer_id=None):
    if user_exists(user_id):
        return get_user_ref_code(user_id)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    code = ref_code or str(uuid.uuid4())[:8].upper()
    c.execute(
        'INSERT INTO users (user_id, username, ref_code, referrer_id, ref_count) VALUES (?, ?, ?, ?, 0)',
        (user_id, username, code, referrer_id)
    )

    if referrer_id and referrer_id != user_id:
        try:
            c.execute('SELECT user_id FROM users WHERE user_id = ?', (referrer_id,))
            if c.fetchone():
                c.execute(
                    'INSERT INTO referrals (referrer_id, referred_id, referred_username) VALUES (?, ?, ?)',
                    (referrer_id, user_id, username)
                )
                c.execute('UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?', (referrer_id,))
                try:
                    bot.send_message(
                        referrer_id,
                        f"🎉 *НОВЫЙ РЕФЕРАЛ!* ✨\n\n"
                        f"👤 *{username}* (ID: `{user_id}`)\n"
                        f"🔗 Присоединился по вашей ссылке!\n"
                        f"💎 *Приводите друзей → получайте 10%* от их пополнений!\n\n"
                        f"📊 Ваши рефералы: `/referrals`",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление рефереру {referrer_id}: {e}")
        except Exception as e:
            logger.error(f"Ошибка регистрации реферала: {e}")

    conn.commit()
    conn.close()
    return code


def add_admin_referral(referrer_id, referred_id, referred_username=None):
    if not user_exists(referrer_id) or not user_exists(referred_id):
        return False, "Один из пользователей не существует"

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id FROM referrals WHERE referrer_id = ? AND referred_id = ?', (referrer_id, referred_id))
    if c.fetchone():
        conn.close()
        return False, "Связь уже существует"

    c.execute(
        'INSERT INTO referrals (referrer_id, referred_id, referred_username) VALUES (?, ?, ?)',
        (referrer_id, referred_id, referred_username or "Unknown")
    )
    c.execute('UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?', (referrer_id,))

    try:
        bot.send_message(
            referrer_id,
            f"🎉 *НОВЫЙ РЕФЕРАЛ (АДМИН)!* ✨\n\n"
            f"👤 *{referred_username or 'Unknown'}* (ID: `{referred_id}`)\n"
            f"🔗 Добавлен администратором!\n"
            f"💎 Получайте 10% от пополнений!",
            parse_mode='Markdown'
        )
    except Exception:
        pass

    conn.commit()
    conn.close()
    return True, "Реферал добавлен!"


def get_user_ref_code(user_id):
    user = get_user(user_id)
    return user[4] if user and len(user) > 4 else None


def get_user_by_ref(code):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT user_id FROM users WHERE ref_code = ?', (code,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def get_user_referrals(user_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''SELECT r.referred_id, r.referred_username, r.created_at,
                        COALESCE(SUM(t.ref_bonus), 0) as total_bonus
                 FROM referrals r
                 LEFT JOIN transactions t ON t.user_id = r.referrer_id
                    AND t.type = 'REF_BONUS'
                    AND t.username LIKE ?
                 WHERE r.referrer_id = ?
                 GROUP BY r.referred_id, r.referred_username, r.created_at
                 ORDER BY r.created_at DESC''',
              (f'%REF_BONUS_{user_id}%', user_id))
    referrals = c.fetchall()
    conn.close()
    return referrals


def get_user_stats(user_id):
    user = get_user(user_id)
    if not user:
        return 0, 0, 0, 0
    return (user[2], user[3], user[7], user[8])


def get_user_ref_info(user_id):
    user = get_user(user_id)
    if not user:
        return {'code': 'ERROR', 'balance': 0, 'stars': 0, 'ref_count': 0, 'ref_bonus_total': 0}
    return {
        'code': user[4],
        'balance': user[2],
        'stars': user[3],
        'ref_count': user[7],
        'ref_bonus_total': user[8] if len(user) > 8 else 0
    }


def update_balance(user_id, amount, stars=0, ref_bonus=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if ref_bonus > 0:
        c.execute(
            'UPDATE users SET balance = balance + ?, total_stars = total_stars + ?, ref_bonus_total = ref_bonus_total + ? WHERE user_id = ?',
            (amount + ref_bonus, stars, ref_bonus, user_id)
        )
    else:
        c.execute(
            'UPDATE users SET balance = balance + ?, total_stars = total_stars + ? WHERE user_id = ?',
            (amount + ref_bonus, stars, user_id)
        )
    conn.commit()
    conn.close()


def add_transaction(user_id, username, trans_type, stars, amount, ref_bonus=0):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        'INSERT INTO transactions (user_id, username, type, stars, amount, ref_bonus) VALUES (?, ?, ?, ?, ?, ?)',
        (user_id, username, trans_type, stars, amount, ref_bonus)
    )
    conn.commit()
    conn.close()


def get_user_balance(user_id):
    user = get_user(user_id)
    return user[2] if user else 0


def give_ref_bonus(referrer_id, bonus_amount, ref_user_id, ref_username):
    if referrer_id and referrer_id != ref_user_id:
        update_balance(referrer_id, 0, ref_bonus=bonus_amount)
        add_transaction(referrer_id, f"REF_BONUS_{ref_user_id}", "REF_BONUS", 0, bonus_amount, bonus_amount)
        try:
            bot.send_message(
                referrer_id,
                f"🎁 *РЕФЕРАЛЬНЫЙ БОНУС!* +{bonus_amount:.2f}₽\n"
                f"👤 Ваш реферал *{ref_username}* пополнил баланс!\n"
                f"💎 *10%* от пополнений друзей → ваш баланс",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления о бонусе: {e}")


def authenticate_fragment():
    global FRAGMENT_TOKEN
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            FRAGMENT_TOKEN = json.load(f).get("token")
            return FRAGMENT_TOKEN
    try:
        mnemonics = FRAGMENT_MNEMONICS.strip().split()
        payload = {
            "api_key": FRAGMENT_API_KEY,
            "phone_number": FRAGMENT_PHONE,
            "mnemonics": mnemonics,
            "version": "V4R2"
        }
        resp = requests.post(f"{FRAGMENT_API_URL}/auth/authenticate/", json=payload, timeout=30)
        if resp.status_code == 200:
            FRAGMENT_TOKEN = resp.json().get("token")
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": FRAGMENT_TOKEN}, f, ensure_ascii=False, indent=2)
            return FRAGMENT_TOKEN
    except Exception as e:
        logger.error(f"Fragment: {e}")
    return None


def send_stars(token, username, quantity):
    try:
        clean_user = username.lstrip('@').strip()
        data = {"username": clean_user, "quantity": quantity, "show_sender": "false"}
        headers = {"Authorization": f"JWT {token}", "Content-Type": "application/json"}
        resp = requests.post(f"{FRAGMENT_API_URL}/order/stars/", json=data, headers=headers, timeout=60)
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)


def show_main_menu(chat_id, user_id):
    stock_status = "✅ В наличии" if STARS_IN_STOCK else "❌ Нет в наличии"
    my_ref_code = get_user_ref_code(user_id)

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton("👤 Кабинет", callback_data="cabinet"),
        types.InlineKeyboardButton("🛒 Магазин", callback_data="shop")
    )
    markup.row(
        types.InlineKeyboardButton("👥 Рефералы", callback_data="referrals"),
        types.InlineKeyboardButton("💳 Пополнить", callback_data="topup")
    )
    markup.row(types.InlineKeyboardButton("ℹ️ О боте", callback_data="about"))
    markup.add(types.InlineKeyboardButton("📢 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME[1:]}"))

    caption = (
        f"🌟 *Добро пожаловать в Lacostest Shop!* ✨\n\n"
        f"💎 *Курс:* 1⭐ = {STAR_PRICE_RUB:.1f}₽\n"
        f"✅ *Минимум:* {MIN_STARS}⭐\n"
        f"⭐ *Звёзды:* {stock_status}\n\n"
        f"🎁 *Рефка:* `t.me/{BOT_USERNAME}?start={my_ref_code}`\n"
        f"💰 *Баланс:* `{get_user_balance(user_id):.2f}₽`\n\n"
        f"Выберите:"
    )

    send_photo_or_message(chat_id, START_IMAGE, caption, reply_markup=markup, parse_mode='Markdown')


@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    username = message.from_user.username or "NoUsername"
    args = message.text.split()
    ref_code = args[-1] if len(args) > 1 else None
    referrer_id = get_user_by_ref(ref_code) if ref_code else None

    create_user(uid, username, None, referrer_id)

    sub_status = is_subscribed(uid)
    if uid != ADMIN_ID:
        if sub_status is False:
            show_subscription_prompt(message.chat.id)
            return
        if sub_status is None:
            bot.send_message(
                message.chat.id,
                "⚠️ Сейчас не удаётся проверить подписку на канал.\n"
                "Проверь, что бот добавлен в канал как администратор, и попробуй позже."
            )
            return

    show_main_menu(message.chat.id, uid)


@bot.message_handler(commands=['help_admin'])
def help_admin(message):
    if message.from_user.id != ADMIN_ID:
        return
    help_text = """
🔧 *АДМИН ПАНЕЛЬ*

/set_balance ID сумма - выдать баланс
/what_id @username - узнать ID
/add_referrals REFERRER_ID REFERRED_ID - добавить реферала
/change_stock да/нет - наличие звёзд
/set_price ЦЕНА - курс звёзд
/set_min КОЛ-ВО - минимум звёзд
/stats - статистика бота
/msg ТЕКСТ - рассылка всем
"""
    bot.reply_to(message, help_text, parse_mode='Markdown')


@bot.message_handler(commands=['add_referrals'])
def add_referrals(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ Нет прав!")
        return
    try:
        _, referrer_id, referred_id = message.text.split()
        referrer_id, referred_id = int(referrer_id), int(referred_id)
        referred_user = get_user(referred_id)
        referred_username = referred_user[1] if referred_user else "Unknown"
        success, msg = add_admin_referral(referrer_id, referred_id, referred_username)
        if success:
            bot.reply_to(
                message,
                f"✅ *Реферал добавлен!*\n\n👤 Реферер: `{referrer_id}`\n👤 Реферал: `{referred_id}` (`{referred_username}`)",
                parse_mode='Markdown'
            )
        else:
            bot.reply_to(message, f"❌ {msg}")
    except Exception:
        bot.reply_to(message, "❌ /add_referrals REFERRER_ID REFERRED_ID\nПример: `/add_referrals 123 456`")


@bot.message_handler(commands=['set_balance'])
def set_balance(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, tid, amount = message.text.split()
        tid, amount = int(tid), float(amount)
        user = get_user(tid)
        if not user:
            bot.reply_to(message, f"❌ Пользователь {tid} не найден")
            return
        uname = user[1]
        referrer_id = user[5]
        ref_bonus = amount * REF_BONUS_PERCENT
        if referrer_id:
            give_ref_bonus(referrer_id, ref_bonus, tid, uname)
        update_balance(tid, amount)
        add_transaction(tid, uname, 'ADMIN_TOPUP', 0, amount)
        bot.reply_to(message, f"✅ @{uname} (ID:{tid}) +{amount}₽\n🎁 Рефералу: +{ref_bonus:.2f}₽")
    except Exception as e:
        bot.reply_to(message, f"❌ /set_balance ID сумма\nОшибка: {e}")


@bot.message_handler(commands=['what_id'])
def what_id(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, uname = message.text.split()
        uname = uname.lstrip('@')
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT user_id FROM users WHERE username = ?', (uname,))
        uid = c.fetchone()
        conn.close()
        bot.reply_to(message, f"✅ @{uname} → `{uid[0]}`" if uid else f"❌ @{uname} нет", parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "❌ /what_id @username")


@bot.message_handler(commands=['change_stock'])
def change_stock(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, status = message.text.split()
        global STARS_IN_STOCK
        STARS_IN_STOCK = status.lower() in ['да', 'yes', 'true', '1']
        save_config()
        new_status = "✅ В наличии" if STARS_IN_STOCK else "❌ Нет в наличии"
        bot.reply_to(message, f"⭐ *Статус звёзд:* {new_status}", parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "❌ /change_stock да/нет")


@bot.message_handler(commands=['set_price'])
def set_price(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, price = message.text.split()
        global STAR_PRICE_RUB
        STAR_PRICE_RUB = float(price)
        save_config()
        bot.reply_to(message, f"💎 *Новый курс:* 1⭐ = {STAR_PRICE_RUB}₽", parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "❌ /set_price ЦЕНА")


@bot.message_handler(commands=['set_min'])
def set_min(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, min_stars = message.text.split()
        global MIN_STARS
        MIN_STARS = int(min_stars)
        save_config()
        bot.reply_to(message, f"✅ *Минимум:* {MIN_STARS}⭐", parse_mode='Markdown')
    except Exception:
        bot.reply_to(message, "❌ /set_min КОЛ-ВО")


@bot.message_handler(commands=['stats'])
def stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT COUNT(*), SUM(balance), SUM(total_stars), SUM(ref_bonus_total) FROM users')
    total_users, total_balance, total_stars, total_ref_bonus = c.fetchone() or (0, 0, 0, 0)
    c.execute('SELECT COUNT(*) FROM referrals')
    total_refs = c.fetchone()[0]
    conn.close()
    bot.reply_to(
        message,
        f"📊 *СТАТИСТИКА*\n\n"
        f"👥 Пользователей: `{total_users}`\n"
        f"🔗 Рефералов: `{total_refs}`\n"
        f"💰 Общий баланс: `{total_balance or 0:.2f}₽`\n"
        f"⭐ Куплено звёзд: `{total_stars or 0}`\n"
        f"🎁 Реф. бонусы: `{total_ref_bonus or 0:.2f}₽`",
        parse_mode='Markdown'
    )


@bot.message_handler(commands=['msg'])
def broadcast_message(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав для этой команды!")
        return
    try:
        broadcast_text = message.text[5:].strip()
        if not broadcast_text:
            bot.reply_to(
                message,
                "❌ Напишите текст после /msg!\nПример: `/msg Привет всем! Акция до завтра!`",
                parse_mode='Markdown'
            )
            return

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT user_id FROM users')
        users = c.fetchall()
        conn.close()

        total_users = len(users)
        sent_count = 0

        for (user_id,) in users:
            try:
                bot.send_message(user_id, broadcast_text, parse_mode='Markdown')
                sent_count += 1
            except Exception:
                pass

        bot.reply_to(
            message,
            f"📢 *РАССЫЛКА ОКОНЧЕНА* ✅\n\n"
            f"👥 Всего пользователей: `{total_users}`\n"
            f"✅ Отправлено: `{sent_count}`\n"
            f"❌ Ошибок: `{total_users - sent_count}`",
            parse_mode='Markdown'
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка рассылки: {e}")


@bot.message_handler(commands=['referrals'])
def cmd_referrals(message):
    uid = message.from_user.id
    sub_status = is_subscribed(uid)
    if uid != ADMIN_ID and sub_status is False:
        show_subscription_prompt(message.chat.id)
        return
    if uid != ADMIN_ID and sub_status is None:
        bot.send_message(message.chat.id, "⚠️ Не удалось проверить подписку на канал.")
        return

    ref_info = get_user_ref_info(uid)
    referrals = get_user_referrals(uid)

    ref_text = f"👥 *ВАШИ РЕФЕРАЛЫ* ✨\n\n"
    ref_text += f"🎁 *Приведи друга → +10%* от пополнений!\n"
    ref_text += f"💎 *Всего бонусов:* `{ref_info['ref_bonus_total']:.2f}₽`\n\n"
    ref_text += f"🔗 *Ссылка:*\n`t.me/{BOT_USERNAME}?start={ref_info['code']}`\n\n"

    if referrals:
        ref_text += f"📋 *Ваши рефералы* ({len(referrals)}):\n\n"
        total_bonus = 0
        for i, (ref_id, ref_username, ref_date, bonus) in enumerate(referrals[:10], 1):
            total_bonus += bonus
            ref_text += f"{i}. *{ref_username}* (ID: `{ref_id}`) — *+{bonus:.2f}₽*\n"
        if len(referrals) > 10:
            ref_text += f"... и ещё {len(referrals) - 10}"
        ref_text += f"\n\n💰 *Итого с них:* `{total_bonus:.2f}₽`"
    else:
        ref_text += "📭 Пока нет рефералов\n💎 Приглашайте друзей!"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"))

    send_photo_or_message(message.chat.id, REFERRALS_IMAGE, ref_text, reply_markup=markup, parse_mode='Markdown')


@bot.message_handler(func=lambda m: True)
def handle_text(message):
    uid = message.from_user.id
    text = message.text.strip()

    sub_status = is_subscribed(uid)
    if uid != ADMIN_ID and (sub_status is False or sub_status is None):
        return

    if uid not in user_states:
        return

    state = user_states[uid]

    if state['step'] == 'waiting_username':
        if text.startswith('@'):
            state['target_username'] = text
            bot.reply_to(message, f"✅ *Получатель:* `{text}`\n📝 *Количество* (мин {MIN_STARS}):", parse_mode='Markdown')
            state['step'] = 'waiting_stars'
        else:
            bot.reply_to(message, "❌ С @!")
        return

    if state['step'] == 'waiting_stars':
        try:
            stars = int(text)
            if stars < MIN_STARS:
                bot.reply_to(message, f"❌ *Минимум {MIN_STARS}!*", parse_mode='Markdown')
                return

            target_username = state['target_username']
            cost = stars * STAR_PRICE_RUB
            balance = get_user_balance(uid)

            if balance < cost:
                bot.reply_to(message, f"❌ *Нужно:* `{cost:.2f}₽`\n*Есть:* `{balance:.2f}₽`", parse_mode='Markdown')
                return

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Отправить", callback_data=f"buy_{stars}_{target_username}"))
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="main_menu"))

            bot.send_message(
                message.chat.id,
                f"🛒 *Подтверждение* ✨\n\n"
                f"👤 `{target_username}`\n"
                f"⭐ `{stars}`\n"
                f"💰 `{cost:.2f}₽`\n\n"
                f"*Отправить звёзды?*",
                reply_markup=markup,
                parse_mode='Markdown'
            )

            del user_states[uid]
        except Exception:
            bot.reply_to(message, "❌ *ЧИСЛО!*", parse_mode='Markdown')


@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    uid = call.from_user.id
    data = call.data

    if data != "check_subscription" and uid != ADMIN_ID:
        sub_status = is_subscribed(uid)
        if sub_status is False:
            bot.answer_callback_query(call.id, "🔒 Сначала подпишитесь на канал!")
            return
        if sub_status is None:
            bot.answer_callback_query(call.id, "⚠️ Не удалось проверить подписку.")
            return

    if data == "check_subscription":
        sub_status = is_subscribed(uid)
        if sub_status is True:
            safe_delete_message(call.message.chat.id, call.message.message_id)
            show_main_menu(call.message.chat.id, uid)
            bot.answer_callback_query(call.id, "✅ Подписка подтверждена! Добро пожаловать!")
        elif sub_status is False:
            bot.answer_callback_query(call.id, "❌ Вы ещё не подписаны на канал!")
        else:
            bot.answer_callback_query(call.id, "⚠️ Не удалось проверить подписку.")
        return

    if data == "about":
        show_about_menu(call.message.chat.id)
        safe_delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "main_menu":
        show_main_menu(call.message.chat.id, uid)
        safe_delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "cabinet":
        balance, stars, ref_count, ref_bonus_total = get_user_stats(uid)
        ref_info = get_user_ref_info(uid)
        stock_status = "✅ В наличии" if STARS_IN_STOCK else "❌ Нет в наличии"

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton("🛒 Магазин", callback_data="shop"),
            types.InlineKeyboardButton("👥 Рефералы", callback_data="referrals")
        )
        markup.row(
            types.InlineKeyboardButton("💳 Пополнить", callback_data="topup"),
            types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        )

        caption = (
            f"👤 *ЛИЧНЫЙ КАБИНЕТ* ✨\n\n"
            f"🆔 *ID:* `{uid}`\n"
            f"💰 *Баланс:* `{balance:.2f}₽`\n"
            f"⭐ *Куплено:* `{stars}`\n"
            f"👥 *Рефералов:* `{ref_count}`\n"
            f"🎁 *Бонусы:* `{ref_bonus_total:.2f}₽`\n\n"
            f"🔗 *Рефка:* `{ref_info['code']}`\n"
            f"⭐ *Статус:* {stock_status}"
        )

        send_photo_or_message(call.message.chat.id, CABINET_IMAGE, caption, reply_markup=markup, parse_mode='Markdown')
        safe_delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "referrals":
        ref_info = get_user_ref_info(uid)
        referrals = get_user_referrals(uid)

        ref_text = f"👥 *ВАШИ РЕФЕРАЛЫ* ✨\n\n"
        ref_text += f"🎁 *Приведи друга → +10%* от пополнений!\n"
        ref_text += f"💎 *Всего бонусов:* `{ref_info['ref_bonus_total']:.2f}₽`\n\n"
        ref_text += f"🔗 *Ссылка:*\n`t.me/{BOT_USERNAME}?start={ref_info['code']}`\n\n"

        if referrals:
            ref_text += f"📋 *Ваши рефералы* ({len(referrals)}):\n\n"
            total_bonus = 0
            for i, (ref_id, ref_username, ref_date, bonus) in enumerate(referrals[:10], 1):
                total_bonus += bonus
                ref_text += f"{i}. *{ref_username}* (ID: `{ref_id}`) — *+{bonus:.2f}₽*\n"
            if len(referrals) > 10:
                ref_text += f"... и ещё {len(referrals) - 10}"
            ref_text += f"\n\n💰 *Итого с них:* `{total_bonus:.2f}₽`"
        else:
            ref_text += "📭 Пока нет рефералов\n💎 Приглашайте друзей!"

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton("🔗 Копировать ссылку", callback_data="referrals_copy"),
            types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        )

        send_photo_or_message(call.message.chat.id, REFERRALS_IMAGE, ref_text, reply_markup=markup, parse_mode='Markdown')
        safe_delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data in ["shop", "buy_stars"]:
        if not STARS_IN_STOCK:
            bot.answer_callback_query(call.id, "❌ Звёзд нет в наличии!")
            return

        user_states[uid] = {'step': 'waiting_username'}

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"))

        caption = (
            f"🛒 *МАГАЗИН ЗВЁЗД* ✨\n"
            f"💎 *1⭐ = {STAR_PRICE_RUB}₽*\n"
            f"✅ *Мин. {MIN_STARS}⭐*\n\n"
            f"📝 После этого отправьте username получателя (с @)."
        )

        send_photo_or_message(call.message.chat.id, SHOP_IMAGE, caption, reply_markup=markup, parse_mode='Markdown')
        bot.send_message(call.message.chat.id, "📝 *ШАГ 1:* Username получателя (с @)", parse_mode='Markdown')
        safe_delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "topup":
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.row(
            types.InlineKeyboardButton("📢 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME[1:]}"),
            types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
        )
        bot.send_message(
            call.message.chat.id,
            f"💳 *ПОПОЛНЕНИЕ* ✨\n\n"
            f"💰 *Баланс:* `{get_user_balance(uid):.2f}₽`\n\n"
            f"📢 *Пиши:* {SUPPORT_USERNAME}\n"
            f"⚡ *Моментально!*",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        safe_delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "referrals_copy":
        ref_info = get_user_ref_info(uid)
        bot.answer_callback_query(
            call.id,
            text=f"Ваша ссылка: t.me/{BOT_USERNAME}?start={ref_info['code']}",
            show_alert=True
        )
        return

    if data.startswith('buy_'):
        try:
            parts = data.split('_', 2)
            stars = int(parts[1])
            target_username = parts[2]
            cost = stars * STAR_PRICE_RUB

            if get_user_balance(uid) < cost:
                bot.answer_callback_query(call.id, "❌ Недостаточно средств!")
                return

            update_balance(uid, -cost, stars)
            success, error_msg = send_stars(FRAGMENT_TOKEN, target_username, stars)
            add_transaction(uid, target_username or "Unknown", 'purchase', stars, -cost)

            if success:
                balance = get_user_balance(uid)
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"))
                bot.send_message(
                    call.message.chat.id,
                    f"✅ *ЗВЁЗДЫ ОТПРАВЛЕНЫ!* ✨\n\n"
                    f"👤 `{target_username}`\n"
                    f"⭐ `{stars}`\n"
                    f"💰 `-{cost:.2f}₽`\n"
                    f"💳 *Остаток:* `{balance:.2f}₽`",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                safe_delete_message(call.message.chat.id, call.message.message_id)
                bot.send_message(ADMIN_ID, f"🛒 {target_username} ← {stars}⭐ | ID:{uid}")
            else:
                update_balance(uid, cost)
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu"))
                bot.send_message(
                    call.message.chat.id,
                    f"❌ *Ошибка Fragment!*\n{error_msg}\n\n💰 Деньги возвращены",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
                safe_delete_message(call.message.chat.id, call.message.message_id)
        except Exception as e:
            try:
                cost = stars * STAR_PRICE_RUB if 'stars' in locals() else 0
                if cost > 0:
                    update_balance(uid, cost)
            except Exception:
                pass
            bot.answer_callback_query(call.id, "❌ Ошибка обработки!")
            logger.error(f"Buy error: {e}")

        bot.answer_callback_query(call.id)


if __name__ == "__main__":
    try:
        init_db()
        authenticate_fragment()

        print("🚀 Lacostest Stars Bot запущен!")
        print(f"🔧 Админ: {ADMIN_ID}")
        print(f"⭐ Звёзды в наличии: {'✅' if STARS_IN_STOCK else '❌'}")
        print(f"📢 Обязательная подписка: {REQUIRED_CHANNEL}")

        print("Пути к изображениям:")
        print("START_IMAGE =", START_IMAGE, "| exists =", os.path.isfile(START_IMAGE), "| size =", os.path.getsize(START_IMAGE) if os.path.isfile(START_IMAGE) else "NO FILE")
        print("REFERRALS_IMAGE =", REFERRALS_IMAGE, "| exists =", os.path.isfile(REFERRALS_IMAGE), "| size =", os.path.getsize(REFERRALS_IMAGE) if os.path.isfile(REFERRALS_IMAGE) else "NO FILE")
        print("SHOP_IMAGE =", SHOP_IMAGE, "| exists =", os.path.isfile(SHOP_IMAGE), "| size =", os.path.getsize(SHOP_IMAGE) if os.path.isfile(SHOP_IMAGE) else "NO FILE")
        print("CABINET_IMAGE =", CABINET_IMAGE, "| exists =", os.path.isfile(CABINET_IMAGE), "| size =", os.path.getsize(CABINET_IMAGE) if os.path.isfile(CABINET_IMAGE) else "NO FILE")
        print("OBOTE_IMAGE =", OBOTE_IMAGE, "| exists =", os.path.isfile(OBOTE_IMAGE), "| size =", os.path.getsize(OBOTE_IMAGE) if os.path.isfile(OBOTE_IMAGE) else "NO FILE")

        bot.infinity_polling(none_stop=True)
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logger.error(f"Critical error: {e}")