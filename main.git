import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ---------- НАСТРОЙКИ (ЗАМЕНИ НА СВОИ) ----------
TOKEN = "8054662227:AAFCEUkLrAtk0fgBjuDAqoeTPoiq2Vu1idk"  # Взять у @BotFather
CHANNEL_ID = "@CryptoKanOffici"  # Юзернейм твоего канала (с @) или его числовой ID
CHANNEL_LINK = "https://t.me/CryptoKanOfficial"  # Публичная ссылка-приглашение
ADMIN_ID = 8343022613  # Твой Telegram ID для админ-команд

# Простая база в памяти (при перезапуске сбрасывается, но для старта сойдёт)
# Храним: user_id -> {referrals: [список id приглашённых], balance: float}
users = {}

logging.basicConfig(level=logging.INFO)

# ---------- ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ----------
async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ---------- КОМАНДЫ БОТА ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает /start и реферальные ссылки"""
    user_id = update.effective_user.id
    
    # Проверяем, есть ли реферальный параметр в ссылке
    args = context.args
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
            if referrer_id != user_id:  # Защита от саморефералов [citation:5]
                if user_id not in users:
                    users[user_id] = {"referrals": [], "balance": 0.0}
                
                # Проверяем подписку перед начислением бонуса
                if await is_subscribed(user_id, context):
                    if referrer_id in users and user_id not in users[referrer_id]["referrals"]:
                        users[referrer_id]["referrals"].append(user_id)
                        users[referrer_id]["balance"] += 0.15  # Твоя ставка
                        await context.bot.send_message(
                            referrer_id,
                            f"🎉 По твоей ссылке зашёл новый участник! Ты получил 0.15 USDT. Баланс: {users[referrer_id]['balance']:.2f} USDT"
                        )
        except:
            pass

    # Кнопки главного меню
    keyboard = [
        [InlineKeyboardButton("🔗 Моя реф-ссылка", callback_data="my_link")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton("🏆 Топ пригласивших", callback_data="top")],
        [InlineKeyboardButton("💳 Вывести USDT", callback_data="withdraw")]
    ]
    
    # Проверяем, подписан ли юзер
    if await is_subscribed(user_id, context):
        text = f"🤝 Привет! Я реферальный бот CryptoKan. Приглашай друзей и получай 0.15 USDT за каждого!"
    else:
        text = f"❌ Чтобы пользоваться ботом, подпишись на канал CryptoKan!\n👉 {CHANNEL_LINK}"
        keyboard = [[InlineKeyboardButton("🔔 Проверить подписку", callback_data="check_sub")]]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Проверка подписки
    if query.data != "check_sub" and not await is_subscribed(user_id, context):
        await query.edit_message_text(
            f"❌ Сначала подпишись на CryptoKan!\n👉 {CHANNEL_LINK}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔔 Проверить", callback_data="check_sub")]])
        )
        return

    if query.data == "check_sub":
        if await is_subscribed(user_id, context):
            await query.edit_message_text("✅ Подписка подтверждена! Нажми /start для продолжения.")
        else:
            await query.answer("❌ Ты ещё не подписан!", show_alert=True)
        return

    # --- Логика кнопок ---
    if user_id not in users:
        users[user_id] = {"referrals": [], "balance": 0.0}

    if query.data == "my_link":
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        await query.edit_message_text(
            f"🔗 Твоя персональная ссылка:\n`{link}`\n\nОтправь её друзьям и получай 0.15 USDT за каждого, кто подпишется на канал!",
            parse_mode="Markdown"
        )

    elif query.data == "my_stats":
        count = len(users[user_id]["referrals"])
        balance = users[user_id]["balance"]
        await query.edit_message_text(f"📊 Приглашено: {count} чел.\n💰 Баланс: {balance:.2f} USDT")

    elif query.data == "top":
        sorted_users = sorted(users.items(), key=lambda x: len(x[1]["referrals"]), reverse=True)[:10]
        text = "🏆 Топ-10 пригласивших:\n"
        for i, (uid, data) in enumerate(sorted_users, 1):
            try:
                user = await context.bot.get_chat(uid)
                name = user.full_name
            except:
                name = f"ID{uid}"
            text += f"{i}. {name} — {len(data['referrals'])} чел.\n"
        await query.edit_message_text(text)

    elif query.data == "withdraw":
        await query.edit_message_text("💸 Для вывода средств напиши админу: @CryptoKan_Support")

# ---------- АДМИН-КОМАНДЫ ----------
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа")
        return
    await update.message.reply_text("/users — список юзеров\n/pay ID сумма — выплатить USDT")

# ---------- ЗАПУСК ----------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Бот CryptoKan запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
