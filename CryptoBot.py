import json
import sqlite3
import random
import urllib.request
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

@dataclass
class Config:
    BOT_TOKEN: str = "8780917575:AAF5QjqH2v3YZNMS1M1rs200T0nVPTY_FVY"
    CRYPTOPAY_API_KEY: str = "562330:AAEmCmEd1QJks9H1I88KCIVyQdj93Z16EAe"
    ADMIN_ID: int = 8343022613
    BOT_USERNAME: str = "CryptoKanS1x_bot"
    
    WITHDRAW_FEE: int = 5
    REFERRAL_PERCENT: int = 5
    REGISTRATION_BONUS: float = 100
    REFERRAL_BONUS: float = 50
    LOTTERY_COST: float = 100
    
    MKN_TO_USDT: float = 0.001
    MIN_MKN_SWAP: float = 500
    MIN_WITHDRAW: float = 1.1
    
    LOTTERY_MULTIPLIERS: Dict[int, int] = None
    RATES: Dict[str, float] = None
    
    def __post_init__(self):
        if self.LOTTERY_MULTIPLIERS is None:
            self.LOTTERY_MULTIPLIERS = {2: 15, 5: 5, 10: 1}
        if self.RATES is None:
            self.RATES = {"USDT": 1.0, "TON": 5.2, "BTC": 65000, "ETH": 3500, "SOL": 180}


CONFIG = Config()
CURRENCIES = ["USDT", "TON", "BTC", "ETH", "SOL", "MKN"]

# ============================================================================
# БАЗА ДАННЫХ
# ============================================================================

class Database:
    def __init__(self, db_path: str = "CryptoKan.db"):
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
                balance_usdt REAL DEFAULT 0,
                balance_ton REAL DEFAULT 0,
                balance_btc REAL DEFAULT 0,
                balance_eth REAL DEFAULT 0,
                balance_sol REAL DEFAULT 0,
                balance_mkn REAL DEFAULT 0,
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
            c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                amount REAL,
                address TEXT,
                fee REAL,
                currency TEXT DEFAULT 'USDT',
                status TEXT DEFAULT 'pending',
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
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = c.fetchone()
            if row:
                columns = [d[0] for d in c.description]
                return dict(zip(columns, row))
        return None
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None,
                    referrer_id: int = None) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute('''INSERT INTO users (user_id, username, first_name, referrer_id, balance_mkn)
                             VALUES (?, ?, ?, ?, ?)''', 
                          (user_id, username, first_name, referrer_id, CONFIG.REGISTRATION_BONUS))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def update_username(self, user_id: int, username: str):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            conn.commit()
    
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
    
    def add_withdraw_request(self, user_id: int, username: str, amount: float, address: str, fee: float, currency: str = "USDT") -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO withdraw_requests (user_id, username, amount, address, fee, currency)
                         VALUES (?, ?, ?, ?, ?, ?)''', (user_id, username, amount, address, fee, currency))
            conn.commit()
            return c.lastrowid
    
    def get_pending_withdraws(self) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM withdraw_requests WHERE status = 'pending' ORDER BY created_at ASC")
            rows = c.fetchall()
            columns = [d[0] for d in c.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def get_withdraw_request(self, request_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM withdraw_requests WHERE id = ?", (request_id,))
            row = c.fetchone()
            if row:
                columns = [d[0] for d in c.description]
                return dict(zip(columns, row))
        return None
    
    def approve_withdraw(self, request_id: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE withdraw_requests SET status = 'approved' WHERE id = ?", (request_id,))
            conn.commit()
    
    def reject_withdraw(self, request_id: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (request_id,))
            conn.commit()
    
    def get_all_users(self) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, username, balance_usdt, balance_mkn, created_at FROM users ORDER BY created_at DESC")
            rows = c.fetchall()
            columns = ['user_id', 'username', 'balance_usdt', 'balance_mkn', 'created_at']
            return [dict(zip(columns, row)) for row in rows]
    
    def get_stats(self) -> Dict:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            c.execute("SELECT SUM(total_deposited) FROM users")
            deposits = c.fetchone()[0] or 0
            c.execute("SELECT SUM(total_withdrawn) FROM users")
            withdraws = c.fetchone()[0] or 0
            c.execute("SELECT SUM(balance_mkn) FROM users")
            mkn_supply = c.fetchone()[0] or 0
            return {"users": users, "deposits": deposits, "withdraws": withdraws, "mkn_supply": mkn_supply}
    
    def admin_add_balance(self, user_id: int, currency: str, amount: float):
        with self._get_connection() as conn:
            c = conn.cursor()
            col = f"balance_{currency.lower()}"
            c.execute(f"UPDATE users SET {col} = {col} + ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            self.add_transaction(user_id, "admin_add", currency, amount, "completed", details="Пополнение от администратора")


# ============================================================================
# ОБНОВЛЕНИЕ КУРСОВ
# ============================================================================

def fetch_binance_price(symbol: str) -> Optional[float]:
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            return float(data["price"])
    except Exception as e:
        print(f"Ошибка получения {symbol}: {e}")
        return None

def update_rates():
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
        print(f"🔄 CryptoKan | Курсы обновлены")
    except Exception as e:
        print(f"❌ CryptoKan | Ошибка обновления курсов: {e}")
    threading.Timer(300, update_rates).start()


# ============================================================================
# CRYPTOBOT API
# ============================================================================

CRYPTOPAY_API_URL = "https://pay.crypt.bot/api"

def create_invoice(amount: float, user_id: int, currency: str = "USDT") -> Tuple[Optional[str], Optional[str]]:
    try:
        data = {
            "asset": currency,
            "amount": str(amount),
            "description": f"CryptoKan Deposit | User {user_id}",
            "payload": str(user_id)
        }
        req = urllib.request.Request(
            f"{CRYPTOPAY_API_URL}/createInvoice",
            data=json.dumps(data).encode(),
            headers={"Crypto-Pay-API-Token": CONFIG.CRYPTOPAY_API_KEY, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode())
            if result.get("ok"):
                return result["result"]["pay_url"], str(result["result"]["invoice_id"])
            else:
                print(f"CryptoBot error: {result}")
                return None, None
    except Exception as e:
        print(f"Create invoice error: {e}")
        return None, None

def check_invoice_status(invoice_id: str) -> Optional[str]:
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
    [InlineKeyboardButton("🏦 Кошелек", callback_data="wallet")],
    [InlineKeyboardButton("💱 Обменник", callback_data="exchange")],
    [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery")],
    [InlineKeyboardButton("👥 Рефералы", callback_data="referral")],
    [InlineKeyboardButton("📜 История", callback_data="history")],
    [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
])

back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu")]])

admin_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
    [InlineKeyboardButton("👥 Все пользователи", callback_data="admin_users")],
    [InlineKeyboardButton("💸 Заявки на вывод", callback_data="admin_withdraws")],
    [InlineKeyboardButton("➕ Пополнить пользователя", callback_data="admin_add_balance")],
    [InlineKeyboardButton("🔙 Главное меню", callback_data="menu")]
])

def is_admin(user_id: int) -> bool:
    return user_id == CONFIG.ADMIN_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    first_name = update.effective_user.first_name
    
    user = db.get_user(user_id)
    if user and user.get('username') != username:
        db.update_username(user_id, username)
    
    args = context.args
    referrer_id = None
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    if not user:
        db.create_user(user_id, username, first_name, referrer_id)
        if referrer_id:
            db.update_balance(referrer_id, "MKN", CONFIG.REFERRAL_BONUS, "add")
            db.add_transaction(referrer_id, "referral_bonus", "MKN", CONFIG.REFERRAL_BONUS, "completed", details=f"За регистрацию {username}")
            db.add_referral_earning(referrer_id, user_id, 0, CONFIG.REFERRAL_BONUS)
            try:
                await context.bot.send_message(referrer_id, f"🎉 *Новый реферал!*\n@{username} зарегистрировался!\n💰 Ты получил {CONFIG.REFERRAL_BONUS} MKN", parse_mode="Markdown")
            except:
                pass
    
    balances = db.get_all_balances(user_id)
    balance_text = "🏦 *CryptoKan*\n\n"
    for c in CURRENCIES:
        if c == "MKN":
            balance_text += f"💎 {c}: `{balances[c]:.2f}`\n"
        else:
            balance_text += f"💰 {c}: `{balances[c]:.4f}`\n"
    balance_text += f"\n👥 Рефералов: {db.get_referral_count(user_id)}"
    balance_text += f"\n💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT"
    balance_text += f"\n📤 Мин. вывод: {CONFIG.MIN_WITHDRAW} USDT (комиссия 5%)"
    
    await update.message.reply_text(
        f"✨ *Добро пожаловать в CryptoKan* ✨\n\n{balance_text}",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balances = db.get_all_balances(user_id)
    balance_text = "🏦 *CryptoKan*\n\n"
    for c in CURRENCIES:
        if c == "MKN":
            balance_text += f"💎 {c}: `{balances[c]:.2f}`\n"
        else:
            balance_text += f"💰 {c}: `{balances[c]:.4f}`\n"
    balance_text += f"\n👥 Рефералов: {db.get_referral_count(user_id)}"
    await query.edit_message_text(
        f"✨ *CryptoKan* ✨\n\n{balance_text}",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if is_admin(user_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏦 Кошелек", callback_data="wallet_user")],
            [InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
        ])
        await query.edit_message_text(
            "👑 *Добро пожаловать, Администратор!*\n\nВыберите режим:",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await show_user_wallet(update, context)

async def show_user_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balances = db.get_all_balances(user_id)
    text = "🏦 *Твой кошелек CryptoKan*\n\n"
    for c in CURRENCIES:
        if c == "MKN":
            text += f"💎 {c}: `{balances[c]:.2f}`\n"
        else:
            text += f"💰 {c}: `{balances[c]:.6f}`\n"
    text += f"\n💸 Комиссия на вывод: {CONFIG.WITHDRAW_FEE}% (вычитается из суммы)"
    text += f"\n💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT"
    text += f"\n📤 Мин. вывод: {CONFIG.MIN_WITHDRAW} USDT"
    text += f"\n🔄 Мин. обмен MKN: {CONFIG.MIN_MKN_SWAP} MKN"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Пополнить", callback_data="deposit"), InlineKeyboardButton("📤 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton("🔄 Перевести", callback_data="transfer")],
        [InlineKeyboardButton("💎 Купить MKN", callback_data="buy_mkn"), InlineKeyboardButton("💎 Продать MKN", callback_data="sell_mkn")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет доступа к админ-панели!", reply_markup=back_keyboard)
        return
    
    stats = db.get_stats()
    text = "👑 *Админ-панель CryptoKan*\n\n"
    text += f"📊 Пользователей: {stats['users']}\n"
    text += f"💰 Всего депозитов: {stats['deposits']:.2f} USDT\n"
    text += f"📤 Всего выводов: {stats['withdraws']:.2f} USDT\n"
    text += f"💎 MKN в обращении: {stats['mkn_supply']:.2f}"
    
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        return
    
    stats = db.get_stats()
    text = "📊 *Статистика*\n\n"
    text += f"👥 Пользователей: {stats['users']}\n"
    text += f"💰 Депозитов: {stats['deposits']:.2f} USDT\n"
    text += f"📤 Выводов: {stats['withdraws']:.2f} USDT\n"
    text += f"💎 MKN в обращении: {stats['mkn_supply']:.2f}"
    
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        return
    
    users = db.get_all_users()
    if not users:
        await query.edit_message_text("Нет пользователей", reply_markup=admin_keyboard)
        return
    
    text = "👥 *Пользователи CryptoKan*\n\n"
    for u in users[:20]:
        text += f"🆔 `{u['user_id']}` | @{u['username'] or 'no_username'}\n"
        text += f"   💰 USDT: {u['balance_usdt']:.2f} | 💎 MKN: {u['balance_mkn']:.0f}\n"
        text += f"   📅 {u['created_at'][:10]}\n\n"
    
    if len(users) > 20:
        text += f"... и еще {len(users) - 20} пользователей"
    
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        return
    
    withdraws = db.get_pending_withdraws()
    if not withdraws:
        await query.edit_message_text("Нет активных заявок на вывод", reply_markup=admin_keyboard)
        return
    
    text = "💸 *Заявки на вывод*\n\n"
    for w in withdraws:
        user_gets = w['amount'] - (w['amount'] * w['fee'] / 100)
        text += f"🆔 *Заявка #{w['id']}*\n"
        text += f"👤 Пользователь: @{w['username'] or w['user_id']} | `{w['user_id']}`\n"
        text += f"💰 Сумма вывода: {w['amount']} {w['currency']}\n"
        text += f"⚡️ Комиссия ({w['fee']}%): {w['amount'] * w['fee'] / 100:.4f} {w['currency']}\n"
        text += f"📤 Пользователь получит: {user_gets:.4f} {w['currency']}\n"
        text += f"📤 Адрес: `{w['address'][:30]}...`\n"
        text += f"📅 {w['created_at'][:10]}\n"
        text += f"✅ `/approve_{w['id']}` - подтвердить (отправь {user_gets:.4f} USDT)\n"
        text += f"❌ `/reject_{w['id']}` - отклонить\n\n"
    
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        return
    
    awaiting_state[user_id] = "admin_add"
    await query.edit_message_text(
        "➕ *Пополнение пользователя*\n\nВведи ID пользователя, валюту и сумму через пробел:\nПример: `123456789 USDT 100`\nПример: `987654321 MKN 500`\n\n*Где взять ID?* В разделе 👥 Все пользователи",
        reply_markup=admin_keyboard,
        parse_mode="Markdown"
    )

async def deposit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "deposit"
    await query.edit_message_text(
        "💰 *Пополнение CryptoKan*\n\nВведи сумму в USDT (мин 1):\nПример: `10`",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "withdraw"
    await query.edit_message_text(
        f"📤 *Вывод из CryptoKan*\n\n"
        f"Введи адрес кошелька USDT (TRC20) и сумму через пробел\n"
        f"Мин. сумма: {CONFIG.MIN_WITHDRAW} USDT\n"
        f"Комиссия: {CONFIG.WITHDRAW_FEE}% (вычитается из суммы)\n"
        f"Пример: `TVqP8Ur8f1DUUM3k4QxVxz1Qn1Gddq4VFT 10`\n\n"
        f"*Пример расчета:* при выводе 10 USDT ты получишь 9.5 USDT, комиссия 0.5 USDT",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def transfer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "transfer"
    await query.edit_message_text(
        "🔄 *Перевод в CryptoKan*\n\nФормат: `@username 10 USDT`\nПример: `@ivan 5 USDT`\n\nДоступные валюты: USDT, TON, BTC, ETH, SOL, MKN",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def buy_mkn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "buy_mkn"
    await query.edit_message_text(
        f"💎 *Покупка MKN*\n\nКурс: 1 MKN = {CONFIG.MKN_TO_USDT} USDT\nМинимум: {CONFIG.MIN_MKN_SWAP} MKN ({CONFIG.MIN_MKN_SWAP * CONFIG.MKN_TO_USDT} USDT)\n\nВведи сумму MKN, которую хочешь купить:\nПример: `500`",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def sell_mkn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "sell_mkn"
    await query.edit_message_text(
        f"💎 *Продажа MKN*\n\nКурс: 1 MKN = {CONFIG.MKN_TO_USDT} USDT\nМинимум: {CONFIG.MIN_MKN_SWAP} MKN\n\nВведи сумму MKN, которую хочешь продать:\nПример: `500`",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💱 *Обменник CryptoKan*\n\n*Текущие курсы (USDT):*\n"
    for c in ["USDT", "TON", "BTC", "ETH", "SOL"]:
        text += f"💰 1 {c} = {CONFIG.RATES[c]:.2f} USDT\n"
    text += f"💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT (мин. {CONFIG.MIN_MKN_SWAP} MKN)\n"
    text += "\n*Команды:*\n`/swap USDT TON 10` - обмен валют\n`/swap USDT MKN 500` - покупка MKN\n`/swap MKN USDT 500` - продажа MKN"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def swap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("❌ Используй: /swap FROM TO AMOUNT\nПример: /swap USDT MKN 500")
        return
    from_cur = args[0].upper()
    to_cur = args[1].upper()
    try:
        amount = float(args[2])
    except:
        await update.message.reply_text("❌ Неверная сумма")
        return
    if from_cur not in CURRENCIES or to_cur not in CURRENCIES:
        await update.message.reply_text(f"❌ Неподдерживаемая валюта. Доступны: {', '.join(CURRENCIES)}")
        return
    
    if from_cur == "MKN" and to_cur == "USDT":
        if amount < CONFIG.MIN_MKN_SWAP:
            await update.message.reply_text(f"❌ Минимальная продажа MKN: {CONFIG.MIN_MKN_SWAP} MKN")
            return
        balance = db.get_balance(user_id, "MKN")
        if balance < amount:
            await update.message.reply_text(f"❌ Недостаточно MKN. Баланс: {balance:.2f}")
            return
        usd_amount = amount * CONFIG.MKN_TO_USDT
        db.update_balance(user_id, "MKN", amount, "subtract")
        db.update_balance(user_id, "USDT", usd_amount, "add")
        db.add_transaction(user_id, "swap", f"MKN->USDT", amount, "completed", details=f"Получено: {usd_amount:.4f} USDT")
        await update.message.reply_text(f"✅ *Продажа MKN!*\n\nОтдано: {amount} MKN\nПолучено: {usd_amount:.4f} USDT", parse_mode="Markdown")
    elif from_cur == "USDT" and to_cur == "MKN":
        mkn_amount = amount / CONFIG.MKN_TO_USDT
        if mkn_amount < CONFIG.MIN_MKN_SWAP:
            await update.message.reply_text(f"❌ Минимальная покупка MKN: {CONFIG.MIN_MKN_SWAP} MKN (нужно {CONFIG.MIN_MKN_SWAP * CONFIG.MKN_TO_USDT} USDT)")
            return
        balance = db.get_balance(user_id, "USDT")
        if balance < amount:
            await update.message.reply_text(f"❌ Недостаточно USDT. Баланс: {balance:.4f}")
            return
        db.update_balance(user_id, "USDT", amount, "subtract")
        db.update_balance(user_id, "MKN", mkn_amount, "add")
        db.add_transaction(user_id, "swap", f"USDT->MKN", amount, "completed", details=f"Получено: {mkn_amount:.2f} MKN")
        await update.message.reply_text(f"✅ *Покупка MKN!*\n\nОтдано: {amount} USDT\nПолучено: {mkn_amount:.2f} MKN", parse_mode="Markdown")
    else:
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
    balance = db.get_balance(user_id, "MKN")
    if balance < CONFIG.LOTTERY_COST:
        await query.edit_message_text(f"❌ Недостаточно MKN! Нужно: {CONFIG.LOTTERY_COST} MKN\n💎 Купить MKN можно в кошельке", reply_markup=back_keyboard)
        return
    db.update_balance(user_id, "MKN", CONFIG.LOTTERY_COST, "subtract")
    db.add_transaction(user_id, "lottery_ticket", "MKN", CONFIG.LOTTERY_COST, "completed")
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
        db.update_balance(user_id, "MKN", prize, "add")
        db.add_transaction(user_id, "lottery_win", "MKN", prize, "completed")
        text = f"🎉 *ВЫИГРЫШ x{multiplier}!* +{prize} MKN\n💎 Баланс MKN: {db.get_balance(user_id, 'MKN'):.2f}"
    else:
        text = f"😢 *Проигрыш* -{CONFIG.LOTTERY_COST} MKN\n💎 Баланс MKN: {db.get_balance(user_id, 'MKN'):.2f}"
    lottery_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎲 Еще раз", callback_data="lottery")], [InlineKeyboardButton("🔙 Назад", callback_data="menu")]])
    await query.edit_message_text(text, reply_markup=lottery_keyboard, parse_mode="Markdown")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ref_link = f"https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{user_id}"
    count = db.get_referral_count(user_id)
    earnings = db.get_referral_earnings(user_id)
    text = f"👥 *Реферальная программа CryptoKan*\n\nТвоя ссылка:\n`{ref_link}`\n\n📊 Приглашено: {count}\n💰 Заработано: {earnings:.2f} MKN\n🎁 Бонус: {CONFIG.REFERRAL_BONUS} MKN за друга\n💸 {CONFIG.REFERRAL_PERCENT}% от пополнений рефералов"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    transactions = db.get_user_transactions(user_id, 15)
    if not transactions:
        await query.edit_message_text("📜 *История транзакций пуста*", reply_markup=back_keyboard, parse_mode="Markdown")
        return
    text = "📜 *Последние транзакции CryptoKan:*\n\n"
    emoji_map = {"deposit": "📥", "withdraw": "📤", "swap": "🔄", "lottery_ticket": "🎲", "lottery_win": "🎉", "referral_bonus": "👥", "transfer_send": "📤", "transfer_receive": "📥", "admin_add": "👑"}
    for tx in transactions:
        emoji = emoji_map.get(tx['type'], "📝")
        sign = "+" if tx['type'] in ['deposit', 'lottery_win', 'referral_bonus', 'transfer_receive', 'admin_add'] else "-"
        text += f"{emoji} {tx['type']}: {sign}{tx['amount']:.4f} {tx['currency']}\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "ℹ️ *CryptoKan - Помощь*\n\n"
    text += "📥 *Пополнение:* Кошелек → Пополнить → введи сумму → оплати через CryptoBot\n"
    text += f"📤 *Вывод:* Кошелек → Вывести → адрес и сумма (мин {CONFIG.MIN_WITHDRAW} USDT, комиссия 5% вычитается)\n"
    text += "🔄 *Перевод:* Кошелек → Перевести → @username сумма USDT\n"
    text += f"💎 *MKN:* 1 MKN = {CONFIG.MKN_TO_USDT} USDT, мин. обмен {CONFIG.MIN_MKN_SWAP} MKN\n"
    text += "💱 *Обмен:* /swap FROM TO AMOUNT\n"
    text += "🎲 *Лотерея:* Билет 100 MKN, шанс выигрыша 21%\n"
    text += "👥 *Рефералы:* Приглашай друзей и получай 50 MKN за каждого!"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = awaiting_state.get(user_id)
    
    user = db.get_user(user_id)
    username = update.effective_user.username or str(user_id)
    if user and user.get('username') != username:
        db.update_username(user_id, username)
    
    if state == "admin_add" and is_admin(user_id):
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: ID ВАЛЮТА СУММА\nПример: `123456789 USDT 100`")
            return
        try:
            target_id = int(parts[0])
            currency = parts[1].upper()
            amount = float(parts[2])
            if currency not in CURRENCIES:
                await update.message.reply_text(f"❌ Доступны: {', '.join(CURRENCIES)}")
                return
            db.admin_add_balance(target_id, currency, amount)
            await update.message.reply_text(f"✅ Пользователю {target_id} начислено {amount} {currency}")
            try:
                await context.bot.send_message(target_id, f"👑 *Администратор начислил вам {amount} {currency}*", parse_mode="Markdown")
            except:
                pass
        except:
            await update.message.reply_text("❌ Неверный формат")
        awaiting_state.pop(user_id, None)
    
    elif state == "deposit":
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
                await update.message.reply_text("❌ Ошибка создания счета. Проверь настройки CryptoBot (баланс и права API)")
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
            await update.message.reply_text("❌ Формат: АДРЕС СУММА\nПример: `TVqP8Ur8f1DUUM3k4QxVxz1Qn1Gddq4VFT 10`", parse_mode="Markdown")
            return
        address, amount_str = parts
        try:
            amount = float(amount_str)
        except:
            await update.message.reply_text("❌ Неверная сумма")
            return
        
        if amount < CONFIG.MIN_WITHDRAW:
            await update.message.reply_text(f"❌ Минимальная сумма вывода: {CONFIG.MIN_WITHDRAW} USDT")
            return
        
        balance = db.get_balance(user_id, "USDT")
        fee = amount * CONFIG.WITHDRAW_FEE / 100
        user_receives = amount - fee
        
        if balance < amount:
            await update.message.reply_text(f"❌ Недостаточно средств. Нужно: {amount:.4f} USDT\n💰 Твой баланс: {balance:.4f} USDT")
            return
        
        db.update_balance(user_id, "USDT", amount, "subtract")
        
        username = update.effective_user.username or str(user_id)
        request_id = db.add_withdraw_request(user_id, username, amount, address, CONFIG.WITHDRAW_FEE)
        db.add_transaction(user_id, "withdraw", "USDT", amount, "pending", fee=fee, details=f"Адрес: {address}")
        
        await update.message.reply_text(
            f"✅ *Заявка на вывод создана!*\n\n"
            f"💰 Сумма: {amount} USDT\n"
            f"⚡️ Комиссия (5%): {fee:.4f} USDT\n"
            f"📤 Ты получишь: {user_receives:.4f} USDT\n"
            f"📤 Адрес: `{address}`\n\n"
            f"⏳ Ожидай подтверждения администратора.",
            parse_mode="Markdown"
        )
        
        await context.bot.send_message(
            CONFIG.ADMIN_ID,
            f"🔔 *НОВАЯ ЗАЯВКА НА ВЫВОД #{request_id}*\n\n"
            f"👤 Пользователь: @{username}\n"
            f"🆔 ID: `{user_id}`\n"
            f"💰 Сумма вывода: {amount} USDT\n"
            f"⚡️ Комиссия 5%: {fee:.4f} USDT\n"
            f"📤 Пользователь получит: {user_receives:.4f} USDT\n"
            f"📤 Адрес: `{address}`\n\n"
            f"✅ `/approve_{request_id}` - подтвердить (отправь {user_receives:.4f} USDT)\n"
            f"❌ `/reject_{request_id}` - отклонить",
            parse_mode="Markdown"
        )
        
        awaiting_state.pop(user_id, None)
    
    elif state == "buy_mkn":
        try:
            mkn_amount = float(text)
            if mkn_amount < CONFIG.MIN_MKN_SWAP:
                await update.message.reply_text(f"❌ Минимальная покупка: {CONFIG.MIN_MKN_SWAP} MKN")
                return
            usd_needed = mkn_amount * CONFIG.MKN_TO_USDT
            balance = db.get_balance(user_id, "USDT")
            if balance < usd_needed:
                await update.message.reply_text(f"❌ Недостаточно USDT. Нужно: {usd_needed:.4f} USDT")
                return
            db.update_balance(user_id, "USDT", usd_needed, "subtract")
            db.update_balance(user_id, "MKN", mkn_amount, "add")
            db.add_transaction(user_id, "swap", "USDT->MKN", usd_needed, "completed", details=f"Получено: {mkn_amount:.2f} MKN")
            await update.message.reply_text(f"✅ *Покупка MKN!*\n\nОтдано: {usd_needed:.4f} USDT\nПолучено: {mkn_amount:.2f} MKN", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state == "sell_mkn":
        try:
            mkn_amount = float(text)
            if mkn_amount < CONFIG.MIN_MKN_SWAP:
                await update.message.reply_text(f"❌ Минимальная продажа: {CONFIG.MIN_MKN_SWAP} MKN")
                return
            usd_received = mkn_amount * CONFIG.MKN_TO_USDT
            balance = db.get_balance(user_id, "MKN")
            if balance < mkn_amount:
                await update.message.reply_text(f"❌ Недостаточно MKN. Баланс: {balance:.2f}")
                return
            db.update_balance(user_id, "MKN", mkn_amount, "subtract")
            db.update_balance(user_id, "USDT", usd_received, "add")
            db.add_transaction(user_id, "swap", "MKN->USDT", mkn_amount, "completed", details=f"Получено: {usd_received:.4f} USDT")
            await update.message.reply_text(f"✅ *Продажа MKN!*\n\nОтдано: {mkn_amount} MKN\nПолучено: {usd_received:.4f} USDT", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Введи число")
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

async def handle_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Нет доступа")
        return
    
    text = update.message.text.strip()
    if text.startswith("/approve_"):
        try:
            request_id = int(text.replace("/approve_", ""))
            request = db.get_withdraw_request(request_id)
            if not request:
                await update.message.reply_text(f"❌ Заявка #{request_id} не найдена")
                return
            if request['status'] != 'pending':
                await update.message.reply_text(f"❌ Заявка #{request_id} уже {request['status']}")
                return
            
            db.approve_withdraw(request_id)
            user_gets = request['amount'] - (request['amount'] * request['fee'] / 100)
            
            try:
                await context.bot.send_message(
                    request['user_id'],
                    f"✅ *Ваша заявка на вывод {request['amount']} USDT подтверждена!*\n\n"
                    f"💰 Сумма к получению: {user_gets:.4f} USDT\n"
                    f"📤 Адрес: `{request['address']}`\n\n"
                    f"Средства будут отправлены в ближайшее время.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            await update.message.reply_text(f"✅ Заявка #{request_id} подтверждена! Пользователь уведомлен.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Нет доступа")
        return
    
    text = update.message.text.strip()
    if text.startswith("/reject_"):
        try:
            request_id = int(text.replace("/reject_", ""))
            request = db.get_withdraw_request(request_id)
            if not request:
                await update.message.reply_text(f"❌ Заявка #{request_id} не найдена")
                return
            if request['status'] != 'pending':
                await update.message.reply_text(f"❌ Заявка #{request_id} уже {request['status']}")
                return
            
            db.update_balance(request['user_id'], "USDT", request['amount'], "add")
            db.reject_withdraw(request_id)
            
            try:
                await context.bot.send_message(
                    request['user_id'],
                    f"❌ *Ваша заявка на вывод {request['amount']} USDT отклонена!*\n\n"
                    f"Средства возвращены на ваш баланс.\n"
                    f"💰 Баланс: {db.get_balance(request['user_id'], 'USDT'):.4f} USDT",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            await update.message.reply_text(f"✅ Заявка #{request_id} отклонена. Баланс пользователя восстановлен.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    update_rates()
    app = Application.builder().token(CONFIG.BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("swap", swap_command))
    app.add_handler(CommandHandler("approve_", handle_approve_command, block=False))
    app.add_handler(CommandHandler("reject_", handle_reject_command, block=False))
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(show_user_wallet, pattern="^wallet_user$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_withdraws, pattern="^admin_withdraws$"))
    app.add_handler(CallbackQueryHandler(admin_add_balance, pattern="^admin_add_balance$"))
    app.add_handler(CallbackQueryHandler(exchange, pattern="^exchange$"))
    app.add_handler(CallbackQueryHandler(lottery, pattern="^lottery$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(help_command, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(deposit_handler, pattern="^deposit$"))
    app.add_handler(CallbackQueryHandler(withdraw_handler, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(transfer_handler, pattern="^transfer$"))
    app.add_handler(CallbackQueryHandler(buy_mkn, pattern="^buy_mkn$"))
    app.add_handler(CallbackQueryHandler(sell_mkn, pattern="^sell_mkn$"))
    app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 CryptoKan запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
