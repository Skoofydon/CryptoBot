import os
import json
import sqlite3
import random
import urllib.request
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "8780917575:AAF5QjqH2v3YZNMS1M1rs200T0nVPTY_FVY")
    CRYPTOPAY_API_KEY: str = os.getenv("CRYPTOPAY_API_KEY", "556863:AAPMuBD5NBKWHSfsntXlARm1hZ52BCbQXMF")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "8780917575"))
    MINI_APP_URL: str = os.getenv("MINI_APP_URL", "https://your-domain.com")
    
    WITHDRAW_FEE: int = 5
    REFERRAL_PERCENT: int = 5
    REFERRAL_BONUS: float = 0.5
    LOTTERY_COST: float = 1.0
    LOTTERY_MULTIPLIERS: Dict[int, int] = None
    RATES: Dict[str, float] = None
    
    def __post_init__(self):
        if self.LOTTERY_MULTIPLIERS is None:
            self.LOTTERY_MULTIPLIERS = {2: 15, 5: 5, 10: 1}
        if self.RATES is None:
            self.RATES = {"USDT": 1.0, "TON": 5.2, "BTC": 65000, "ETH": 3500, "SOL": 180}


CONFIG = Config()
CURRENCIES = ["USDT", "TON", "BTC", "ETH", "SOL"]

# ============================================================================
# ОБНОВЛЕНИЕ КУРСОВ (без ccxt)
# ============================================================================

def fetch_binance_price(symbol: str) -> Optional[float]:
    """Получает цену с Binance"""
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            return float(data["price"])
    except Exception as e:
        print(f"Ошибка получения {symbol}: {e}")
        return None

def update_rates():
    """Обновляет курсы валют"""
    try:
        btc_price = fetch_binance_price("BTCUSDT")
        if btc_price:
            CONFIG.RATES["BTC"] = btc_price
        
        eth_price = fetch_binance_price("ETHUSDT")
        if eth_price:
            CONFIG.RATES["ETH"] = eth_price
        
        sol_price = fetch_binance_price("SOLUSDT")
        if sol_price:
            CONFIG.RATES["SOL"] = sol_price
        
        ton_price = fetch_binance_price("TONUSDT")
        if ton_price:
            CONFIG.RATES["TON"] = ton_price
        
        print(f"🔄 Курсы обновлены: BTC={CONFIG.RATES['BTC']:.0f}, ETH={CONFIG.RATES['ETH']:.0f}, SOL={CONFIG.RATES['SOL']:.2f}, TON={CONFIG.RATES['TON']:.2f}")
    except Exception as e:
        print(f"❌ Ошибка обновления курсов: {e}")
    
    # Запускаем следующее обновление через 5 минут
    threading.Timer(300, update_rates).start()

# ============================================================================
# БАЗА ДАННЫХ
# ============================================================================

class Database:
    def __init__(self, db_path: str = "crypto_wallet.db"):
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance_usdt REAL DEFAULT 0,
                balance_ton REAL DEFAULT 0,
                balance_btc REAL DEFAULT 0,
                balance_eth REAL DEFAULT 0,
                balance_sol REAL DEFAULT 0,
                referrer_id INTEGER,
                total_deposited REAL DEFAULT 0,
                total_withdrawn REAL DEFAULT 0,
                total_won REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                currency TEXT,
                amount REAL,
                fee REAL DEFAULT 0,
                status TEXT,
                reference_id TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                amount REAL,
                earned REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS pending_invoices (
                invoice_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                currency TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            conn.commit()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if row:
                columns = [d[0] for d in c.description]
                return dict(zip(columns, row))
        return None
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None,
                    last_name: str = None, referrer_id: int = None) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute('''INSERT INTO users (user_id, username, first_name, last_name, referrer_id)
                             VALUES (?, ?, ?, ?, ?)''', (user_id, username, first_name, last_name, referrer_id))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def get_balance(self, user_id: int, currency: str) -> float:
        col = f"balance_{currency.lower()}"
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute(f"SELECT {col} FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return row[0] if row else 0.0
    
    def get_all_balances(self, user_id: int) -> Dict[str, float]:
        return {c: self.get_balance(user_id, c) for c in CURRENCIES}
    
    def update_balance(self, user_id: int, currency: str, amount: float, operation: str = "add") -> bool:
        col = f"balance_{currency.lower()}"
        with self._get_connection() as conn:
            c = conn.cursor()
            if operation == "add":
                c.execute(f"UPDATE users SET {col} = {col} + ? WHERE user_id = ?", (amount, user_id))
            elif operation == "subtract":
                c.execute(f"UPDATE users SET {col} = {col} - ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            return c.rowcount > 0
    
    def add_transaction(self, user_id: int, tx_type: str, currency: str, amount: float,
                        status: str = "completed", fee: float = 0, reference_id: str = None,
                        details: str = None) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO transactions (user_id, type, currency, amount, fee, status, reference_id, details)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, tx_type, currency, amount, fee, status, reference_id, details))
            conn.commit()
            return c.lastrowid
    
    def get_user_transactions(self, user_id: int, limit: int = 20) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''SELECT type, currency, amount, fee, status, created_at, details
                         FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?''', (user_id, limit))
            rows = c.fetchall()
            columns = ['type', 'currency', 'amount', 'fee', 'status', 'created_at', 'details']
            return [dict(zip(columns, row)) for row in rows]
    
    def get_referral_count(self, user_id: int) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
            row = c.fetchone()
            return row[0] if row else 0
    
    def get_referral_earnings(self, user_id: int) -> float:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT SUM(earned) FROM referrals WHERE referrer_id = ? AND status = 'completed'", (user_id,))
            row = c.fetchone()
            return row[0] if row[0] else 0.0
    
    def add_referral_earning(self, referrer_id: int, referred_id: int, amount: float, earned: float):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO referrals (referrer_id, referred_id, amount, earned, status)
                         VALUES (?, ?, ?, ?, 'completed')''', (referrer_id, referred_id, amount, earned))
            conn.commit()
    
    def add_pending_invoice(self, invoice_id: str, user_id: int, amount: float, currency: str = "USDT"):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT OR REPLACE INTO pending_invoices (invoice_id, user_id, amount, currency)
                         VALUES (?, ?, ?, ?)''', (invoice_id, user_id, amount, currency))
            conn.commit()
    
    def get_pending_invoice(self, invoice_id: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, amount, currency FROM pending_invoices WHERE invoice_id = ?", (invoice_id,))
            row = c.fetchone()
            if row:
                return {"user_id": row[0], "amount": row[1], "currency": row[2]}
        return None
    
    def delete_pending_invoice(self, invoice_id: str):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM pending_invoices WHERE invoice_id = ?", (invoice_id,))
            conn.commit()


# ============================================================================
# CRYPTOBOT API
# ============================================================================

CRYPTOPAY_API_URL = "https://pay.crypt.bot/api"

def create_invoice(amount: float, user_id: int, currency: str = "USDT") -> Tuple[Optional[str], Optional[str]]:
    """Создает счет в CryptoBot"""
    try:
        data = {
            "asset": currency,
            "amount": str(amount),
            "description": f"Deposit for user {user_id}",
            "payload": str(user_id)
        }
        req = urllib.request.Request(
            f"{CRYPTOPAY_API_URL}/createInvoice",
            data=json.dumps(data).encode(),
            headers={"Crypto-Pay-API-Token": CONFIG.CRYPTOPAY_API_KEY, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            if result.get("ok"):
                return result["result"]["pay_url"], str(result["result"]["invoice_id"])
    except Exception as e:
        print(f"Create invoice error: {e}")
    return None, None

def check_invoice_status(invoice_id: str) -> Optional[str]:
    """Проверяет статус счета"""
    try:
        url = f"{CRYPTOPAY_API_URL}/getInvoices?invoice_ids={invoice_id}"
        req = urllib.request.Request(url, headers={"Crypto-Pay-API-Token": CONFIG.CRYPTOPAY_API_KEY})
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode())
            if result.get("ok") and result["result"]["items"]:
                return result["result"]["items"][0].get("status")
    except Exception as e:
        print(f"Check invoice error: {e}")
    return None


# ============================================================================
# БОТ
# ============================================================================

db = Database()
awaiting_state = {}

main_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏦 Мой кошелек", callback_data="wallet")],
    [InlineKeyboardButton("💱 Обменник", callback_data="exchange")],
    [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery")],
    [InlineKeyboardButton("👥 Рефералы", callback_data="referral")],
    [InlineKeyboardButton("📜 История", callback_data="history")]
])

back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu")]])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    first_name = update.effective_user.first_name
    
    args = context.args
    referrer_id = None
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, username, first_name, None, referrer_id)
        if referrer_id:
            db.update_balance(referrer_id, "USDT", CONFIG.REFERRAL_BONUS, "add")
            db.add_transaction(referrer_id, "referral_bonus", "USDT", CONFIG.REFERRAL_BONUS, "completed", details=f"За регистрацию {username}")
            db.add_referral_earning(referrer_id, user_id, 0, CONFIG.REFERRAL_BONUS)
    
    balances = db.get_all_balances(user_id)
    balance_text = "🏦 *Твои балансы:*\n\n" + "\n".join([f"💰 {c}: `{balances[c]:.4f}`" for c in CURRENCIES])
    balance_text += f"\n\n👥 Рефералов: {db.get_referral_count(user_id)}"
    balance_text += f"\n💸 Комиссия на вывод: {CONFIG.WITHDRAW_FEE}%"
    
    await update.message.reply_text(f"✨ *Криптокошелек* ✨\n\n{balance_text}", reply_markup=main_keyboard, parse_mode="Markdown")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balances = db.get_all_balances(user_id)
    balance_text = "🏦 *Твои балансы:*\n\n" + "\n".join([f"💰 {c}: `{balances[c]:.4f}`" for c in CURRENCIES])
    balance_text += f"\n\n👥 Рефералов: {db.get_referral_count(user_id)}"
    await query.edit_message_text(f"✨ *Криптокошелек* ✨\n\n{balance_text}", reply_markup=main_keyboard, parse_mode="Markdown")

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balances = db.get_all_balances(user_id)
    text = "🏦 *Твой кошелек*\n\n"
    for c in CURRENCIES:
        text += f"💰 {c}: `{balances[c]:.6f}`\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Пополнить", callback_data="deposit"), InlineKeyboardButton("📤 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton("🔄 Перевести", callback_data="transfer")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💱 *Обменник*\n\nДоступные валюты:\n" + "\n".join([f"💰 1 {c} = {CONFIG.RATES[c]:.2f} USDT" for c in CURRENCIES])
    text += "\n\nИспользуй команду:\n/swap USDT TON 10"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def swap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("❌ Используй: /swap FROM TO AMOUNT\nПример: /swap USDT TON 10")
        return
    from_cur = args[0].upper()
    to_cur = args[1].upper()
    try:
        amount = float(args[2])
    except:
        await update.message.reply_text("❌ Неверная сумма")
        return
    if from_cur not in CURRENCIES or to_cur not in CURRENCIES:
        await update.message.reply_text("❌ Неподдерживаемая валюта")
        return
    balance = db.get_balance(user_id, from_cur)
    if balance < amount:
        await update.message.reply_text(f"❌ Недостаточно {from_cur}. Баланс: {balance:.4f}")
        return
    usd_value = amount * CONFIG.RATES[from_cur]
    to_amount = usd_value / CONFIG.RATES[to_cur]
    db.update_balance(user_id, from_cur, amount, "subtract")
    db.update_balance(user_id, to_cur, to_amount, "add")
    db.add_transaction(user_id, "swap", f"{from_cur}->{to_cur}", amount, "completed", details=f"Получено: {to_amount:.4f} {to_cur}")
    await update.message.reply_text(f"✅ *Обмен выполнен!*\n\nОтдано: {amount} {from_cur}\nПолучено: {to_amount:.4f} {to_cur}", parse_mode="Markdown")

async def lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = db.get_balance(user_id, "USDT")
    if balance < CONFIG.LOTTERY_COST:
        await query.edit_message_text(f"❌ Недостаточно! Нужно: {CONFIG.LOTTERY_COST} USDT", reply_markup=back_keyboard)
        return
    db.update_balance(user_id, "USDT", CONFIG.LOTTERY_COST, "subtract")
    db.add_transaction(user_id, "lottery_ticket", "USDT", CONFIG.LOTTERY_COST, "completed")
    rand = random.randint(1, 100)
    multiplier = 1
    win = False
    for mult, chance in CONFIG.LOTTERY_MULTIPLIERS.items():
        if rand <= chance:
            multiplier = mult
            win = True
            break
    if win:
        prize = CONFIG.LOTTERY_COST * multiplier
        db.update_balance(user_id, "USDT", prize, "add")
        db.add_transaction(user_id, "lottery_win", "USDT", prize, "completed")
        text = f"🎉 *ВЫИГРЫШ x{multiplier}!* +{prize} USDT\n💰 Баланс: {db.get_balance(user_id, 'USDT'):.4f} USDT"
    else:
        text = f"😢 *Проигрыш* -{CONFIG.LOTTERY_COST} USDT\n💰 Баланс: {db.get_balance(user_id, 'USDT'):.4f} USDT"
    lottery_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎲 Еще раз", callback_data="lottery")], [InlineKeyboardButton("🔙 Назад", callback_data="menu")]])
    await query.edit_message_text(text, reply_markup=lottery_keyboard, parse_mode="Markdown")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    count = db.get_referral_count(user_id)
    earnings = db.get_referral_earnings(user_id)
    text = f"👥 *Реферальная программа*\n\nСсылка:\n`{ref_link}`\n\n📊 Приглашено: {count}\n💰 Заработано: {earnings:.4f} USDT\n🎁 Бонус: {CONFIG.REFERRAL_BONUS} USDT за друга\n💸 {CONFIG.REFERRAL_PERCENT}% от пополнений"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    transactions = db.get_user_transactions(user_id, 15)
    if not transactions:
        await query.edit_message_text("📜 *История пуста*", reply_markup=back_keyboard, parse_mode="Markdown")
        return
    text = "📜 *Последние транзакции:*\n\n"
    emoji_map = {"deposit": "📥", "withdraw": "📤", "swap": "🔄", "lottery_ticket": "🎲", "lottery_win": "🎉", "referral_bonus": "👥"}
    for tx in transactions:
        emoji = emoji_map.get(tx['type'], "📝")
        sign = "+" if tx['type'] in ['deposit', 'lottery_win', 'referral_bonus'] else "-"
        text += f"{emoji} {tx['type']}: {sign}{tx['amount']:.4f} {tx['currency']}\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def deposit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "deposit"
    await query.edit_message_text("💰 *Пополнение*\n\nВведи сумму в USDT (мин 1):\nПример: `10`", reply_markup=back_keyboard, parse_mode="Markdown")

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "withdraw"
    await query.edit_message_text("📤 *Вывод USDT*\n\nВведи адрес кошелька и сумму через пробел:\nПример: `TVqP8Ur8f1DUUM3k4QxVxz1Qn1Gddq4VFT 10`", reply_markup=back_keyboard, parse_mode="Markdown")

async def transfer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "transfer"
    await query.edit_message_text("🔄 *Перевод*\n\nФормат: `@username 10 USDT`\nПример: `@ivan 5 USDT`", reply_markup=back_keyboard, parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = awaiting_state.get(user_id)
    
    if state == "deposit":
        try:
            amount = float(text)
            if amount < 1:
                await update.message.reply_text("❌ Минимум 1 USDT")
                return
            pay_url, invoice_id = create_invoice(amount, user_id)
            if pay_url and invoice_id:
                db.add_pending_invoice(invoice_id, user_id, amount)
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Оплатить", url=pay_url)],
                    [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{invoice_id}")],
                    [InlineKeyboardButton("🔙 Меню", callback_data="menu")]
                ])
                await update.message.reply_text(f"💰 *Счет на {amount} USDT*\n\nНажми «Оплатить» → оплати → «Проверить оплату»", reply_markup=keyboard, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Ошибка создания счета. Убедись, что API ключ CryptoBot настроен.")
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state == "transfer":
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: @username 10 USDT")
            return
        target_name = parts[0].lstrip("@")
        try:
            amount = float(parts[1])
        except:
            await update.message.reply_text("❌ Неверная сумма")
            return
        currency = parts[2].upper()
        if currency not in CURRENCIES:
            await update.message.reply_text(f"❌ Доступны: {', '.join(CURRENCIES)}")
            return
        balance = db.get_balance(user_id, currency)
        if balance < amount:
            await update.message.reply_text(f"❌ Недостаточно {currency}. Баланс: {balance:.4f}")
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
        db.update_balance(user_id, currency, amount, "subtract")
        db.update_balance(target_id, currency, amount, "add")
        db.add_transaction(user_id, "transfer_send", currency, amount, "completed", details=f"Кому: @{target_name}")
        db.add_transaction(target_id, "transfer_receive", currency, amount, "completed", details=f"От: @{update.effective_user.username}")
        await update.message.reply_text(f"✅ Переведено {amount} {currency} пользователю @{target_name}")
        await context.bot.send_message(target_id, f"💰 Перевод {amount} {currency} от @{update.effective_user.username}")
        awaiting_state.pop(user_id, None)
    
    elif state == "withdraw":
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Формат: АДРЕС СУММА")
            return
        address, amount_str = parts
        try:
            amount = float(amount_str)
        except:
            await update.message.reply_text("❌ Неверная сумма")
            return
        balance = db.get_balance(user_id, "USDT")
        fee = amount * CONFIG.WITHDRAW_FEE / 100
        total = amount + fee
        if balance < total:
            await update.message.reply_text(f"❌ Недостаточно. Нужно: {total:.4f} USDT (включая комиссию {CONFIG.WITHDRAW_FEE}%)")
            return
        db.update_balance(user_id, "USDT", total, "subtract")
        db.add_transaction(user_id, "withdraw", "USDT", amount, "pending", fee=fee, details=f"Адрес: {address}")
        await update.message.reply_text(f"✅ Заявка на вывод {amount} USDT создана!\n💰 Комиссия: {fee:.4f} USDT\n⏳ Ожидайте обработки.")
        await context.bot.send_message(CONFIG.ADMIN_ID, f"🔔 Заявка на вывод\nПользователь: {user_id}\nСумма: {amount} USDT\nАдрес: {address}")
        awaiting_state.pop(user_id, None)

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    inv_id = query.data.replace("check_", "")
    pending = db.get_pending_invoice(inv_id)
    if not pending:
        await query.edit_message_text("❌ Счет не найден")
        return
    status = check_invoice_status(inv_id)
    if status == "paid":
        db.update_balance(pending["user_id"], pending["currency"], pending["amount"], "add")
        db.add_transaction(pending["user_id"], "deposit", pending["currency"], pending["amount"], "completed", reference_id=inv_id)
        db.delete_pending_invoice(inv_id)
        await query.edit_message_text(f"✅ Пополнено {pending['amount']} {pending['currency']}!", reply_markup=back_keyboard)
    else:
        await query.edit_message_text(f"⏳ Не оплачено. Статус: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Проверить снова", callback_data=f"check_{inv_id}")]]))

def main():
    # Запускаем обновление курсов в фоновом потоке
    threading.Thread(target=update_rates, daemon=True).start()
    
    app = Application.builder().token(CONFIG.BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("swap", swap_command))
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(exchange, pattern="^exchange$"))
    app.add_handler(CallbackQueryHandler(lottery, pattern="^lottery$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(deposit_handler, pattern="^deposit$"))
    app.add_handler(CallbackQueryHandler(withdraw_handler, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(transfer_handler, pattern="^transfer$"))
    app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 Криптокошелек запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
