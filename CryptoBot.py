import sqlite3
import random
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== КОНФИГУРАЦИЯ ==========
# 👇 СЮДА ВСТАВЬ СВОИ ТОКЕНЫ (после отзыва старых)
BOT_TOKEN = "8780917575:AAF5QjqH2v3YZNMS1M1rs200T0nVPTY_FVY"
CRYPTOPAY_API_KEY = "556863:AAPMuBD5NBKWHSfsntXlARm1hZ52BCbQXMF"
ADMIN_ID = 8343022613  # 👈 ВСТАВЬ СВОЙ TELEGRAM ID (узнай у @userinfobot)

# Настройки
FEE_PERCENT = 1  # Комиссия 1%
MIN_LOTTERY_AMOUNT = 1  # 1 USDT за билет
CRYPTOPAY_API_URL = "https://pay.crypt.bot/api"

# ========== БАЗА ДАННЫХ ==========
DB_NAME = "wallet_bot.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount REAL, status TEXT)''')
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_balance(user_id, amount, tx_type):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
    if tx_type == "deposit":
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    elif tx_type == "withdraw":
        c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    c.execute("INSERT INTO transactions (user_id, type, amount, status) VALUES (?, ?, ?, ?)", 
              (user_id, tx_type, amount, "completed"))
    conn.commit()
    conn.close()

# ========== ФУНКЦИИ CRYPTOBOT ==========
def create_invoice(amount):
    headers = {"Crypto-Pay-API-Token": CRYPTOPAY_API_KEY}
    payload = {"asset": "USDT", "amount": str(amount)}
    try:
        r = requests.post(f"{CRYPTOPAY_API_URL}/createInvoice", headers=headers, json=payload)
        data = r.json()
        if data.get("ok"):
            return data["result"]["pay_url"], data["result"]["invoice_id"]
    except:
        pass
    return None, None

def check_invoice(invoice_id):
    headers = {"Crypto-Pay-API-Token": CRYPTOPAY_API_KEY}
    try:
        r = requests.post(f"{CRYPTOPAY_API_URL}/getInvoices", headers=headers, json={"invoice_ids": invoice_id})
        data = r.json()
        if data.get("ok") and data["result"]["items"]:
            return data["result"]["items"][0].get("status")
    except:
        pass
    return None

# ========== ХРАНИЛИЩЕ ДЛЯ ВРЕМЕННЫХ ДАННЫХ ==========
pending_invoices = {}
awaiting_state = {}

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📥 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton("🔄 Перевести", callback_data="transfer")],
        [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery")],
        [InlineKeyboardButton("📜 История", callback_data="history")]
    ]
    await update.message.reply_text(
        f"✨ *Криптокошелек* ✨\n\n"
        f"Добро пожаловать!\n"
        f"💰 Баланс: `{balance} USDT`\n\n"
        f"⚡️ Комиссия за переводы: {FEE_PERCENT}%",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = get_balance(user_id)
    keyboard = [
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📥 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton("🔄 Перевести", callback_data="transfer")],
        [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery")],
        [InlineKeyboardButton("📜 История", callback_data="history")]
    ]
    await query.edit_message_text(
        f"✨ *Криптокошелек* ✨\n\n"
        f"💰 Баланс: `{balance} USDT`\n\n"
        f"⚡️ Комиссия за переводы: {FEE_PERCENT}%",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = get_balance(user_id)
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
    await query.edit_message_text(
        f"💰 *Твой баланс:* `{balance} USDT`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "deposit"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
    await query.edit_message_text(
        f"💰 *Пополнение баланса*\n\n"
        f"Введи сумму в USDT (минимум *1 USDT*):\n\n"
        f"Пример: `10`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "transfer"
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
    await query.edit_message_text(
        f"🔄 *Перевод средств*\n\n"
        f"Введи ID получателя и сумму в формате:\n`@username 10`\n\n"
        f"Пример: `@ivan 5`\n\n"
        f"⚡️ Комиссия: *{FEE_PERCENT}%*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = get_balance(user_id)
    
    if balance < MIN_LOTTERY_AMOUNT:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(
            f"❌ Недостаточно средств!\n"
            f"Нужно: `{MIN_LOTTERY_AMOUNT} USDT`\n"
            f"Твой баланс: `{balance} USDT`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    update_balance(user_id, MIN_LOTTERY_AMOUNT, "withdraw")
    
    if random.randint(1, 10) == 1:
        prize = MIN_LOTTERY_AMOUNT * 5
        update_balance(user_id, prize, "deposit")
        keyboard = [[InlineKeyboardButton("🎲 Еще раз", callback_data="lottery"), InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(
            f"🎉 *ПОЗДРАВЛЯЮ! ТЫ ВЫИГРАЛ!* 🎉\n\n"
            f"💰 Билет: `{MIN_LOTTERY_AMOUNT} USDT`\n"
            f"🏆 Выигрыш: `{prize} USDT`\n"
            f"💎 Новый баланс: `{get_balance(user_id)} USDT`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        keyboard = [[InlineKeyboardButton("🎲 Еще раз", callback_data="lottery"), InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(
            f"😢 *К сожалению, ты проиграл*\n\n"
            f"💰 Билет: `{MIN_LOTTERY_AMOUNT} USDT`\n"
            f"💎 Твой баланс: `{get_balance(user_id)} USDT`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT type, amount, status, created_at FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT 10", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
        await query.edit_message_text(
            "📜 *История транзакций пуста*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    text = "📜 *Последние 10 транзакций:*\n\n"
    for tx in rows:
        type_icon = "📥" if tx[0] == "deposit" else "📤" if tx[0] == "withdraw" else "🔄"
        text += f"{type_icon} {tx[0]}: `{tx[1]} USDT` — {tx[2]}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="menu")]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = awaiting_state.get(user_id)
    
    if state == "deposit":
        try:
            amount = float(text)
            if amount < 1:
                await update.message.reply_text("❌ Минимальная сумма пополнения — 1 USDT")
                return
            url, inv_id = create_invoice(amount)
            if url:
                pending_invoices[inv_id] = {"user_id": user_id, "amount": amount}
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Оплатить", url=url)],
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv_id}")],
                    [InlineKeyboardButton("🔙 Главное меню", callback_data="menu")]
                ])
                await update.message.reply_text(
                    f"💰 *Счет создан на {amount} USDT*\n\n"
                    f"1️⃣ Нажми «Оплатить»\n"
                    f"2️⃣ Оплати через CryptoBot\n"
                    f"3️⃣ Нажми «Проверить оплату»\n\n"
                    f"Счет действителен 1 час.",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Ошибка создания счета. Попробуй позже.")
        except ValueError:
            await update.message.reply_text("❌ Введи корректное число")
        awaiting_state.pop(user_id, None)
    
    elif state == "transfer":
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Неверный формат. Используй: `@username 10`", parse_mode="Markdown")
            return
        
        target_name = parts[0].lstrip("@")
        try:
            amount = float(parts[1])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Сумма должна быть положительным числом")
            return
        
        from_balance = get_balance(user_id)
        fee = amount * FEE_PERCENT / 100
        total = amount + fee
        
        if from_balance < total:
            await update.message.reply_text(f"❌ Недостаточно средств. Нужно: `{total} USDT` (включая комиссию {FEE_PERCENT}%)", parse_mode="Markdown")
            return
        
        try:
            target = await context.bot.get_chat(target_name)
            target_id = target.id
        except:
            await update.message.reply_text(f"❌ Пользователь @{target_name} не найден")
            return
        
        if target_id == user_id:
            await update.message.reply_text("❌ Нельзя перевести самому себе")
            return
        
        update_balance(user_id, total, "withdraw")
        update_balance(target_id, amount, "deposit")
        update_balance(ADMIN_ID, fee, "deposit")
        
        await update.message.reply_text(
            f"✅ *Перевод выполнен!*\n\n"
            f"Кому: `@{target_name}`\n"
            f"💰 Сумма: `{amount} USDT`\n"
            f"⚡️ Комиссия: `{fee} USDT`\n"
            f"💎 Твой баланс: `{get_balance(user_id)} USDT`",
            parse_mode="Markdown"
        )
        
        try:
            await context.bot.send_message(
                target_id,
                f"💰 *Вам поступил перевод!*\n\n"
                f"От: @{update.effective_user.username or user_id}\n"
                f"Сумма: `{amount} USDT`",
                parse_mode="Markdown"
            )
        except:
            pass
        
        awaiting_state.pop(user_id, None)

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    inv_id = query.data.replace("check_", "")
    pending = pending_invoices.get(inv_id)
    
    if not pending:
        await query.edit_message_text("❌ Счет не найден или истек")
        return
    
    status = check_invoice(inv_id)
    
    if status == "paid":
        user_id = pending["user_id"]
        amount = pending["amount"]
        update_balance(user_id, amount, "deposit")
        del pending_invoices[inv_id]
        await query.edit_message_text(
            f"✅ *Пополнение успешно!*\n\n"
            f"💰 Сумма: `{amount} USDT`\n"
            f"💎 Новый баланс: `{get_balance(user_id)} USDT`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Главное меню", callback_data="menu")]])
        )
    else:
        await query.edit_message_text(
            f"⏳ Счет еще не оплачен.\n\n"
            f"Статус: `{status}`\n\n"
            f"После оплаты нажми «Проверить оплату» снова.",
            parse_mode="Markdown"
        )

# ========== ЗАПУСК ==========
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(balance, pattern="^balance$"))
    app.add_handler(CallbackQueryHandler(deposit, pattern="^deposit$"))
    app.add_handler(CallbackQueryHandler(transfer, pattern="^transfer$"))
    app.add_handler(CallbackQueryHandler(lottery, pattern="^lottery$"))
    app.add_handler(CallbackQueryHandler(history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()