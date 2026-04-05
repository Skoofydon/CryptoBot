import json
import sqlite3
import random
import asyncio
from datetime import datetime, date, timedelta
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
    ADMIN_ID: int = 8343022613
    BOT_USERNAME: str = "CryptoKanS1x_bot"
    
    WITHDRAW_FEE: int = 5
    REFERRAL_PERCENT: int = 5
    REGISTRATION_BONUS: float = 100
    REFERRAL_BONUS: float = 50
    MIN_LOTTERY_BET: float = 100
    
    MKN_TO_USDT: float = 0.001
    EXCHANGE_FEE: float = 2
    MIN_EXCHANGE: float = 100
    MIN_WITHDRAW: float = 1.1
    P2P_FEE: float = 2
    
    FIRST_DEPOSIT_BONUS: Dict[float, float] = None
    CASES: Dict[str, Dict] = None
    INVEST_PACKAGES: Dict[str, Dict] = None
    LEVELS: Dict[float, int] = None
    LOTTERY_MULTIPLIERS: Dict[int, Dict] = None
    ACHIEVEMENTS: Dict[str, Dict] = None
    
    def __post_init__(self):
        if self.FIRST_DEPOSIT_BONUS is None:
            self.FIRST_DEPOSIT_BONUS = {5: 50, 10: 150, 25: 400, 50: 1000}
        
        if self.CASES is None:
            self.CASES = {
                "обычный": {"price": 100, "rewards": [(50,30),(75,25),(100,20),(150,12),(200,8),(300,4),(500,1)]},
                "золотой": {"price": 500, "rewards": [(250,25),(350,20),(500,18),(700,15),(900,10),(1200,7),(2000,4),(5000,1)]},
                "алмазный": {"price": 2000, "rewards": [(1000,20),(1500,18),(2000,15),(3000,12),(4000,10),(6000,8),(10000,5),(20000,2),(50000,0.5)]}
            }
        
        if self.INVEST_PACKAGES is None:
            self.INVEST_PACKAGES = {
                "7 дней": {"days": 7, "percent": 5, "min": 10, "max": 50},
                "14 дней": {"days": 14, "percent": 8, "min": 51, "max": 200},
                "30 дней": {"days": 30, "percent": 12, "min": 201, "max": 1000}
            }
        
        if self.LEVELS is None:
            self.LEVELS = {0: 0, 10: 2, 50: 4, 200: 6, 500: 8, 1000: 10}
        
        if self.LOTTERY_MULTIPLIERS is None:
            self.LOTTERY_MULTIPLIERS = {
                2: {"name": "x2", "chance": 15, "multiplier": 2},
                5: {"name": "x5", "chance": 5, "multiplier": 5},
                10: {"name": "x10", "chance": 1, "multiplier": 10}
            }
        
        if self.ACHIEVEMENTS is None:
            self.ACHIEVEMENTS = {
                "first_step": {"name": "🎉 Первый шаг", "desc": "Зарегистрироваться", "reward": 10},
                "lucky": {"name": "🍀 Везунчик", "desc": "Выиграть x10 в лотерее", "reward": 200},
                "sponsor": {"name": "💰 Спонсор", "desc": "Пополнить 100+ USDT", "reward": 500},
                "legend": {"name": "👑 Легенда", "desc": "Пополнить 1000+ USDT", "reward": 2000},
                "referral_king": {"name": "🤝 Король рефералов", "desc": "Пригласить 20 друзей", "reward": 500},
                "gambler": {"name": "🎲 Азартный", "desc": "Открыть 50 кейсов", "reward": 300},
                "millionaire": {"name": "💎 Миллионер", "desc": "Баланс 1M+ MKN", "reward": 5000},
                "collector": {"name": "📦 Коллекционер", "desc": "Открыть 100 кейсов", "reward": 1000},
                "fortune": {"name": "🎡 Фортуна", "desc": "Выиграть в рулетке 5000+ MKN", "reward": 500},
                "investor": {"name": "💼 Инвестор", "desc": "Вложить 500+ USDT", "reward": 1000}
            }


CONFIG = Config()
CURRENCIES = ["USDT", "MKN"]

db = None
awaiting_state = {}

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
                balance_mkn REAL DEFAULT 0,
                referrer_id INTEGER,
                total_deposited REAL DEFAULT 0,
                total_withdrawn REAL DEFAULT 0,
                total_won REAL DEFAULT 0,
                cases_opened INTEGER DEFAULT 0,
                roulette_max_win REAL DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_daily DATE,
                first_deposit_bonus INTEGER DEFAULT 0,
                cashback_pending REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                package TEXT,
                amount REAL,
                start_date DATE,
                end_date DATE,
                percent INTEGER,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                reward_type TEXT,
                reward_amount REAL,
                uses_left INTEGER,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS promo_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                user_id INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                achievement TEXT,
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS lottery_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                amount REAL,
                bet REAL,
                multiplier INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                currency TEXT,
                amount REAL,
                fee REAL DEFAULT 0,
                status TEXT,
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
            c.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                amount REAL,
                address TEXT,
                fee REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS p2p_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                type TEXT,
                amount REAL,
                price REAL,
                status TEXT DEFAULT 'active',
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
    
    def create_user(self, user_id: int, username: str = None, first_name: str = None, referrer_id: int = None) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute('''INSERT INTO users (user_id, username, first_name, referrer_id, balance_mkn)
                             VALUES (?, ?, ?, ?, ?)''', (user_id, username, first_name, referrer_id, CONFIG.REGISTRATION_BONUS))
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
            else:
                c.execute(f"UPDATE users SET {col} = {col} - ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            return c.rowcount > 0
    
    def add_transaction(self, user_id: int, tx_type: str, currency: str, amount: float,
                        status: str = "completed", fee: float = 0, details: str = None) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO transactions (user_id, type, currency, amount, fee, status, details)
                         VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, tx_type, currency, amount, fee, status, details))
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
    
    def add_cashback(self, user_id: int, amount: float):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET cashback_pending = cashback_pending + ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
    
    def claim_cashback(self, user_id: int) -> float:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT cashback_pending FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            cashback = row[0] if row else 0
            c.execute("UPDATE users SET cashback_pending = 0 WHERE user_id = ?", (user_id,))
            conn.commit()
            return cashback
    
    def can_claim_daily(self, user_id: int) -> Tuple[bool, int]:
        user = self.get_user(user_id)
        if not user:
            return True, 0
        last = user.get('last_daily')
        streak = user.get('daily_streak', 0)
        today = date.today()
        if not last:
            return True, 0
        last_date = datetime.strptime(last, "%Y-%m-%d").date()
        diff = (today - last_date).days
        if diff == 0:
            return False, streak
        elif diff == 1:
            return True, streak + 1
        return True, 1
    
    def claim_daily(self, user_id: int, streak: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
                      (streak, date.today().isoformat(), user_id))
            conn.commit()
    
    def increment_cases_opened(self, user_id: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET cases_opened = cases_opened + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
    
    def add_lottery_record(self, user_id: int, username: str, bet: float, multiplier: int, win: float):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO lottery_records (user_id, username, bet, multiplier, amount)
                         VALUES (?, ?, ?, ?, ?)''', (user_id, username, bet, multiplier, win))
            conn.commit()
    
    def get_top_lottery_wins(self, limit: int = 10) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''SELECT username, amount, multiplier, created_at
                         FROM lottery_records ORDER BY amount DESC LIMIT ?''', (limit,))
            rows = c.fetchall()
            return [{"username": r[0], "amount": r[1], "multiplier": r[2], "date": r[3][:10]} for r in rows]
    
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
    
    def add_withdraw_request(self, user_id: int, username: str, amount: float, address: str, fee: float) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO withdraw_requests (user_id, username, amount, address, fee)
                         VALUES (?, ?, ?, ?, ?)''', (user_id, username, amount, address, fee))
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
    
    def add_investment(self, user_id: int, package: str, amount: float, days: int, percent: int):
        end_date = date.today() + timedelta(days=days)
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO investments (user_id, package, amount, start_date, end_date, percent)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (user_id, package, amount, date.today().isoformat(), end_date.isoformat(), percent))
            conn.commit()
            return c.lastrowid
    
    def get_active_investments(self, user_id: int = None) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            if user_id:
                c.execute("SELECT * FROM investments WHERE user_id = ? AND status = 'active'", (user_id,))
            else:
                c.execute("SELECT * FROM investments WHERE status = 'active' ORDER BY end_date ASC")
            rows = c.fetchall()
            columns = [d[0] for d in c.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def check_completed_investments(self, user_id: int) -> float:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM investments WHERE user_id = ? AND status = 'active' AND end_date <= ?", 
                      (user_id, date.today().isoformat()))
            rows = c.fetchall()
            columns = [d[0] for d in c.description]
            investments = [dict(zip(columns, row)) for row in rows]
            total_return = 0
            for inv in investments:
                profit = inv['amount'] * inv['percent'] / 100
                total_return += inv['amount'] + profit
                c.execute("UPDATE investments SET status = 'completed' WHERE id = ?", (inv['id'],))
                self.add_transaction(user_id, "invest_return", "USDT", inv['amount'] + profit, "completed", 
                                    details=f"Возврат инвестиции {inv['package']}")
            conn.commit()
            return total_return
    
    def create_promo_code(self, code: str, reward_type: str, reward_amount: float, uses: int, admin_id: int) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            try:
                c.execute('''INSERT INTO promo_codes (code, reward_type, reward_amount, uses_left, created_by)
                             VALUES (?, ?, ?, ?, ?)''', (code.upper(), reward_type, reward_amount, uses, admin_id))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False
    
    def use_promo_code(self, code: str, user_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM promo_codes WHERE code = ? AND uses_left > 0", (code.upper(),))
            row = c.fetchone()
            if not row:
                return None
            c.execute("SELECT COUNT(*) FROM promo_uses WHERE code = ? AND user_id = ?", (code.upper(), user_id))
            if c.fetchone()[0] > 0:
                return None
            columns = [d[0] for d in c.description]
            promo = dict(zip(columns, row))
            c.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code.upper(),))
            c.execute("INSERT INTO promo_uses (code, user_id) VALUES (?, ?)", (code.upper(), user_id))
            conn.commit()
            return promo
    
    def add_p2p_order(self, user_id: int, username: str, order_type: str, amount: float, price: float) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO p2p_orders (user_id, username, type, amount, price)
                         VALUES (?, ?, ?, ?, ?)''', (user_id, username, order_type, amount, price))
            conn.commit()
            return c.lastrowid
    
    def get_active_p2p_orders(self, order_type: str = None) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            if order_type:
                c.execute("SELECT * FROM p2p_orders WHERE status = 'active' AND type = ? ORDER BY price ASC", (order_type,))
            else:
                c.execute("SELECT * FROM p2p_orders WHERE status = 'active' ORDER BY price ASC")
            rows = c.fetchall()
            columns = [d[0] for d in c.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def get_p2p_order(self, order_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM p2p_orders WHERE id = ?", (order_id,))
            row = c.fetchone()
            if row:
                columns = [d[0] for d in c.description]
                return dict(zip(columns, row))
        return None
    
    def delete_p2p_order(self, order_id: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE p2p_orders SET status = 'cancelled' WHERE id = ?", (order_id,))
            conn.commit()
    
    def get_user_p2p_orders(self, user_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM p2p_orders WHERE user_id = ? AND status = 'active'", (user_id,))
            rows = c.fetchall()
            columns = [d[0] for d in c.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def get_all_users(self) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, username, balance_usdt, balance_mkn, total_deposited, created_at FROM users ORDER BY created_at DESC")
            rows = c.fetchall()
            columns = ['user_id', 'username', 'balance_usdt', 'balance_mkn', 'total_deposited', 'created_at']
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
            c.execute("SELECT SUM(total_won) FROM users")
            total_won = c.fetchone()[0] or 0
            return {"users": users, "deposits": deposits, "withdraws": withdraws, "mkn_supply": mkn_supply, "total_won": total_won}
    
    def admin_add_balance(self, user_id: int, currency: str, amount: float):
        with self._get_connection() as conn:
            c = conn.cursor()
            col = f"balance_{currency.lower()}"
            c.execute(f"UPDATE users SET {col} = {col} + ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            self.add_transaction(user_id, "admin_add", currency, amount, "completed", details="Пополнение от администратора")
    
    def get_user_level(self, user_id: int) -> int:
        user = self.get_user(user_id)
        if not user:
            return 0
        deposited = user.get('total_deposited', 0)
        for threshold, bonus in sorted(CONFIG.LEVELS.items()):
            if deposited >= threshold:
                return bonus
        return 0
    
    def check_achievement(self, user_id: int, achievement: str) -> bool:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM achievements WHERE user_id = ? AND achievement = ?", (user_id, achievement))
            return c.fetchone() is not None
    
    def add_achievement(self, user_id: int, achievement: str, reward: int):
        if self.check_achievement(user_id, achievement):
            return False
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO achievements (user_id, achievement) VALUES (?, ?)", (user_id, achievement))
            conn.commit()
        self.update_balance(user_id, "MKN", reward, "add")
        self.add_transaction(user_id, "achievement", "MKN", reward, "completed", details=f"Ачивка: {achievement}")
        return True
    
    def check_all_achievements(self, user_id: int):
        user = self.get_user(user_id)
        if not user:
            return
        
        if not self.check_achievement(user_id, "first_step"):
            self.add_achievement(user_id, "first_step", CONFIG.ACHIEVEMENTS["first_step"]["reward"])
        
        deposited = user.get('total_deposited', 0)
        if deposited >= 100 and not self.check_achievement(user_id, "sponsor"):
            self.add_achievement(user_id, "sponsor", CONFIG.ACHIEVEMENTS["sponsor"]["reward"])
        if deposited >= 1000 and not self.check_achievement(user_id, "legend"):
            self.add_achievement(user_id, "legend", CONFIG.ACHIEVEMENTS["legend"]["reward"])
        
        referrals = self.get_referral_count(user_id)
        if referrals >= 20 and not self.check_achievement(user_id, "referral_king"):
            self.add_achievement(user_id, "referral_king", CONFIG.ACHIEVEMENTS["referral_king"]["reward"])
        
        cases_opened = user.get('cases_opened', 0)
        if cases_opened >= 50 and not self.check_achievement(user_id, "gambler"):
            self.add_achievement(user_id, "gambler", CONFIG.ACHIEVEMENTS["gambler"]["reward"])
        if cases_opened >= 100 and not self.check_achievement(user_id, "collector"):
            self.add_achievement(user_id, "collector", CONFIG.ACHIEVEMENTS["collector"]["reward"])
        
        mkn_balance = user.get('balance_mkn', 0)
        if mkn_balance >= 1000000 and not self.check_achievement(user_id, "millionaire"):
            self.add_achievement(user_id, "millionaire", CONFIG.ACHIEVEMENTS["millionaire"]["reward"])


db = Database()

# ============================================================================
# КЛАВИАТУРЫ
# ============================================================================

main_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏦 Кошелек", callback_data="wallet")],
    [InlineKeyboardButton("💱 Обменник", callback_data="exchange_menu")],
    [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery_menu")],
    [InlineKeyboardButton("🎁 Кейсы", callback_data="cases_menu")],
    [InlineKeyboardButton("👥 Рефералы", callback_data="referral")],
    [InlineKeyboardButton("📜 История", callback_data="history")],
    [InlineKeyboardButton("🏆 Рекорды", callback_data="records")],
    [InlineKeyboardButton("💼 Инвестиции", callback_data="invest_menu")],
    [InlineKeyboardButton("🔄 P2P", callback_data="p2p_menu")],
    [InlineKeyboardButton("🏅 Ачивки", callback_data="achievements")],
    [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
])

back_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="menu")]])

admin_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
    [InlineKeyboardButton("👥 Все пользователи", callback_data="admin_users")],
    [InlineKeyboardButton("💸 Заявки на вывод", callback_data="admin_withdraws")],
    [InlineKeyboardButton("📊 Инвестиции", callback_data="admin_investments")],
    [InlineKeyboardButton("➕ Пополнить", callback_data="admin_add_balance")],
    [InlineKeyboardButton("🎁 Подарок", callback_data="admin_gift")],
    [InlineKeyboardButton("🔑 Промокод", callback_data="admin_create_promo")],
    [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
])

def is_admin(user_id: int) -> bool:
    return user_id == CONFIG.ADMIN_ID

# ============================================================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    first_name = update.effective_user.first_name
    
    user = db.get_user(user_id)
    if user and user.get('username') != username:
        db.update_username(user_id, username)
    
    invest_return = db.check_completed_investments(user_id)
    if invest_return > 0:
        db.update_balance(user_id, "USDT", invest_return, "add")
        await update.message.reply_text(f"💰 Инвестиция завершена! +{invest_return:.2f} USDT", parse_mode="Markdown")
    
    cashback = db.claim_cashback(user_id)
    if cashback > 0:
        db.update_balance(user_id, "MKN", cashback, "add")
        await update.message.reply_text(f"💰 Кэшбэк: +{cashback:.1f} MKN", parse_mode="Markdown")
    
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
                await context.bot.send_message(referrer_id, f"🎉 Новый реферал! +{CONFIG.REFERRAL_BONUS} MKN", parse_mode="Markdown")
            except:
                pass
    
    db.check_all_achievements(user_id)
    
    balances = db.get_all_balances(user_id)
    level_bonus = db.get_user_level(user_id)
    text = f"✨ *CryptoKan* ✨\n\n💰 USDT: {balances['USDT']:.4f}\n💎 MKN: {balances['MKN']:.2f}\n\n👥 Рефералов: {db.get_referral_count(user_id)}\n🎚 Уровень: +{level_bonus}%\n💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT"
    await update.message.reply_text(text, reply_markup=main_keyboard, parse_mode="Markdown")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    invest_return = db.check_completed_investments(user_id)
    if invest_return > 0:
        db.update_balance(user_id, "USDT", invest_return, "add")
        await query.edit_message_text(f"💰 Инвестиция завершена! +{invest_return:.2f} USDT", parse_mode="Markdown")
        await asyncio.sleep(1)
    
    cashback = db.claim_cashback(user_id)
    if cashback > 0:
        db.update_balance(user_id, "MKN", cashback, "add")
        await query.edit_message_text(f"💰 Кэшбэк: +{cashback:.1f} MKN", parse_mode="Markdown")
        await asyncio.sleep(1)
    
    db.check_all_achievements(user_id)
    
    balances = db.get_all_balances(user_id)
    level_bonus = db.get_user_level(user_id)
    text = f"✨ *CryptoKan* ✨\n\n💰 USDT: {balances['USDT']:.4f}\n💎 MKN: {balances['MKN']:.2f}\n\n👥 Рефералов: {db.get_referral_count(user_id)}\n🎚 Уровень: +{level_bonus}%"
    await query.edit_message_text(text, reply_markup=main_keyboard, parse_mode="Markdown")

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
        await query.edit_message_text("👑 Администратор", reply_markup=keyboard, parse_mode="Markdown")
    else:
        await show_user_wallet(update, context)

async def show_user_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balances = db.get_all_balances(user_id)
    text = f"🏦 *Кошелек*\n\n💰 USDT: {balances['USDT']:.4f}\n💎 MKN: {balances['MKN']:.2f}\n\n💸 Комиссия вывода: 5%\n💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Пополнить", callback_data="deposit"), InlineKeyboardButton("📤 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton("🔄 Перевести", callback_data="transfer")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

# ============================================================================
# АДМИН-ПАНЕЛЬ
# ============================================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ Нет доступа", reply_markup=back_keyboard)
        return
    stats = db.get_stats()
    text = f"👑 *Админ-панель*\n\n📊 Пользователей: {stats['users']}\n💰 Депозитов: {stats['deposits']:.2f} USDT\n📤 Выводов: {stats['withdraws']:.2f} USDT\n💎 MKN: {stats['mkn_supply']:.2f}"
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    stats = db.get_stats()
    text = f"📊 *Статистика*\n\n👥 Пользователей: {stats['users']}\n💰 Депозитов: {stats['deposits']:.2f} USDT\n📤 Выводов: {stats['withdraws']:.2f} USDT\n💎 MKN в обращении: {stats['mkn_supply']:.2f}\n🎲 Всего выиграно: {stats['total_won']:.0f} MKN"
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    
    users = db.get_all_users()
    if not users:
        await query.edit_message_text("📭 Нет пользователей", reply_markup=admin_keyboard)
        return
    
    text = "👥 *Все пользователи*\n\n"
    for u in users[:30]:
        text += f"🆔 `{u['user_id']}` | @{u['username'] or 'нет'}\n"
        text += f"   💰 USDT: {u['balance_usdt']:.2f} | 💎 MKN: {u['balance_mkn']:.0f}\n"
        text += f"   📥 Депозитов: {u['total_deposited']:.2f} USDT\n"
        text += f"   📅 {u['created_at'][:10]}\n\n"
    
    if len(users) > 30:
        text += f"... и еще {len(users) - 30} пользователей"
    
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    withdraws = db.get_pending_withdraws()
    if not withdraws:
        await query.edit_message_text("📭 Нет активных заявок на вывод", reply_markup=admin_keyboard)
        return
    text = "💸 *Заявки на вывод*\n\n"
    for w in withdraws:
        user_gets = w['amount'] - (w['amount'] * w['fee'] / 100)
        text += f"🆔 *Заявка #{w['id']}*\n"
        text += f"👤 Пользователь: @{w['username'] or w['user_id']} | `{w['user_id']}`\n"
        text += f"💰 Сумма вывода: {w['amount']} USDT\n"
        text += f"⚡️ Комиссия 5%: {w['amount'] * w['fee'] / 100:.4f} USDT\n"
        text += f"📤 Пользователь получит: {user_gets:.4f} USDT\n"
        text += f"✅ `/approve_{w['id']}` - подтвердить\n"
        text += f"❌ `/reject_{w['id']}` - отклонить\n\n"
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_investments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    
    invs = db.get_active_investments()
    if not invs:
        await query.edit_message_text("📭 Нет активных инвестиций", reply_markup=admin_keyboard)
        return
    
    text = "📊 *Активные инвестиции*\n\n"
    for inv in invs:
        user = db.get_user(inv['user_id'])
        username = user.get('username') if user else str(inv['user_id'])
        text += f"🆔 @{username}\n"
        text += f"📦 {inv['package']} | {inv['amount']} USDT | +{inv['percent']}%\n"
        text += f"📅 Завершение: {inv['end_date']}\n\n"
    
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    awaiting_state[query.from_user.id] = "admin_add"
    await query.edit_message_text(
        "➕ *Пополнение пользователя*\n\n"
        "Введи ID пользователя, валюту и сумму через пробел:\n"
        "Пример: `123456789 USDT 100`\n"
        "Пример: `987654321 MKN 500`\n\n"
        "*Где взять ID?* В разделе 👥 Все пользователи",
        reply_markup=admin_keyboard,
        parse_mode="Markdown"
    )

async def admin_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    awaiting_state[query.from_user.id] = "admin_gift"
    await query.edit_message_text(
        "🎁 *Массовый подарок*\n\n"
        "Введи валюту и сумму через пробел:\n"
        "Пример: `MKN 100`\n"
        "Пример: `USDT 5`\n\n"
        "Подарок получат ВСЕ пользователи бота.",
        reply_markup=admin_keyboard,
        parse_mode="Markdown"
    )

async def admin_create_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id): return
    awaiting_state[query.from_user.id] = "admin_promo"
    await query.edit_message_text(
        "🔑 *Создание промокода*\n\n"
        "Формат: `КОД ВАЛЮТА СУММА КОЛИЧЕСТВО`\n"
        "Пример: `HELLO MKN 100 50`\n\n"
        "ВАЛЮТА: MKN или USDT\n"
        "КОЛИЧЕСТВО: сколько раз можно использовать",
        reply_markup=admin_keyboard,
        parse_mode="Markdown"
    )

# ============================================================================
# РАССЫЛКА ОТ АДМИНА
# ============================================================================

async def sendall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет сообщение всем пользователям бота (только админ)"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа")
        return
    
    text = update.message.text.replace("/sendall", "").strip()
    if not text:
        await update.message.reply_text(
            "❌ *Как использовать:*\n"
            "`/sendall Текст сообщения`\n\n"
            "📌 *Пример:*\n"
            "`/sendall Привет! У нас новый розыгрыш!`",
            parse_mode="Markdown"
        )
        return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, отправить", callback_data="confirm_sendall")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data="menu")]
    ])
    
    context.user_data['sendall_text'] = text
    
    await update.message.reply_text(
        f"📢 *Подтверждение рассылки*\n\n"
        f"Текст сообщения:\n"
        f"`{text}`\n\n"
        f"⚠️ Сообщение получат ВСЕ пользователи бота.\n"
        f"Отправить?",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def confirm_sendall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение отправки рассылки"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ Нет доступа")
        return
    
    text = context.user_data.get('sendall_text')
    if not text:
        await query.edit_message_text("❌ Текст не найден")
        return
    
    with db._get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
    
    if not users:
        await query.edit_message_text("❌ Нет пользователей для рассылки")
        return
    
    await query.edit_message_text(f"⏳ Начинаю рассылку {len(users)} пользователям...")
    
    success = 0
    fail = 0
    
    for user in users:
        try:
            await context.bot.send_message(
                user[0],
                f"📢 *Сообщение от администратора*\n\n{text}",
                parse_mode="Markdown"
            )
            success += 1
            await asyncio.sleep(0.05)
        except:
            fail += 1
    
    await query.edit_message_text(
        f"✅ *Рассылка завершена!*\n\n"
        f"📨 Доставлено: {success}\n"
        f"❌ Ошибок: {fail}",
        parse_mode="Markdown"
    )
    
    context.user_data.pop('sendall_text', None)

# ============================================================================
# ОБМЕННИК
# ============================================================================

async def exchange_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = f"💱 *Обменник*\n\n1 MKN = {CONFIG.MKN_TO_USDT} USDT\n1 USDT = {int(1/CONFIG.MKN_TO_USDT)} MKN\nКомиссия: {CONFIG.EXCHANGE_FEE}%\nМин: {CONFIG.MIN_EXCHANGE} MKN\n\n/buy 500 - купить MKN\n/sell 500 - продать MKN"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Купить", callback_data="buy_mkn"), InlineKeyboardButton("💎 Продать", callback_data="sell_mkn")], [InlineKeyboardButton("🔙 Назад", callback_data="menu")]])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def buy_mkn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "buy_mkn"
    await query.edit_message_text(f"💎 Введи сумму MKN (мин {CONFIG.MIN_EXCHANGE}):", reply_markup=back_keyboard, parse_mode="Markdown")

async def sell_mkn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "sell_mkn"
    await query.edit_message_text(f"💎 Введи сумму MKN (мин {CONFIG.MIN_EXCHANGE}):", reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# КЕЙСЫ
# ============================================================================

async def cases_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🎁 *Кейсы*\n📦 Обычный - 100 MKN\n📦 Золотой - 500 MKN\n📦 Алмазный - 2000 MKN"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Обычный", callback_data="case_normal")],
        [InlineKeyboardButton("📦 Золотой", callback_data="case_gold")],
        [InlineKeyboardButton("📦 Алмазный", callback_data="case_diamond")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def open_case(update: Update, context: ContextTypes.DEFAULT_TYPE, case_type: str):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    case = CONFIG.CASES[case_type]
    price = case['price']
    if db.get_balance(user_id, "MKN") < price:
        await query.edit_message_text(f"❌ Нужно {price} MKN", reply_markup=back_keyboard)
        return
    db.update_balance(user_id, "MKN", price, "subtract")
    db.increment_cases_opened(user_id)
    rand = random.randint(1, 100)
    cumulative = 0
    reward = 0
    for r, chance in case['rewards']:
        cumulative += chance
        if rand <= cumulative:
            reward = r
            break
    db.update_balance(user_id, "MKN", reward, "add")
    db.add_transaction(user_id, "case_open", "MKN", price, "completed", details=f"Кейс {case_type}, выигрыш {reward}")
    db.check_all_achievements(user_id)
    if reward > price:
        text = f"🎉 ВЫИГРЫШ {reward} MKN! +{reward - price} MKN"
    elif reward == price:
        text = f"🔄 ВОЗВРАТ! {reward} MKN"
    else:
        text = f"😢 Выпало {reward} MKN, убыток {price - reward} MKN"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎲 Еще", callback_data=f"case_{case_type}"), InlineKeyboardButton("🔙 Назад", callback_data="cases_menu")]])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def case_normal(update: Update, context: ContextTypes.DEFAULT_TYPE): await open_case(update, context, "обычный")
async def case_gold(update: Update, context: ContextTypes.DEFAULT_TYPE): await open_case(update, context, "золотой")
async def case_diamond(update: Update, context: ContextTypes.DEFAULT_TYPE): await open_case(update, context, "алмазный")

# ============================================================================
# ЛОТЕРЕЯ
# ============================================================================

async def lottery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = f"🎲 *Лотерея*\n\n"
    text += f"💰 *Шансы выигрыша:*\n"
    for mult, data in CONFIG.LOTTERY_MULTIPLIERS.items():
        text += f"  • x{mult} — {data['chance']}%\n"
    text += f"\n📊 *Кэшбэк:* 10% от проигрыша (начислится завтра)\n"
    text += f"🎚 *Уровень:* +{db.get_user_level(query.from_user.id)}% к выигрышу\n"
    text += f"\n⚡️ Введи сумму ставки (мин {CONFIG.MIN_LOTTERY_BET} MKN):"
    awaiting_state[query.from_user.id] = "lottery_bet"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def lottery_play(update: Update, context: ContextTypes.DEFAULT_TYPE, bet: float):
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)
    
    if db.get_balance(user_id, "MKN") < bet:
        await update.message.reply_text(f"❌ Недостаточно MKN. Нужно: {bet:.0f} MKN", parse_mode="Markdown")
        return
    
    db.update_balance(user_id, "MKN", bet, "subtract")
    db.add_transaction(user_id, "lottery_ticket", "MKN", bet, "completed", details=f"Ставка {bet} MKN")
    
    rand = random.randint(1, 100)
    multiplier = 1
    
    for mult, data in CONFIG.LOTTERY_MULTIPLIERS.items():
        if rand <= data['chance']:
            multiplier = data['multiplier']
            break
    
    level_bonus = db.get_user_level(user_id)
    
    if multiplier > 1:
        prize = bet * multiplier
        bonus = int(prize * level_bonus / 100)
        total = prize + bonus
        db.update_balance(user_id, "MKN", total, "add")
        db.add_transaction(user_id, "lottery_win", "MKN", total, "completed", details=f"Выигрыш x{multiplier} со ставки {bet}")
        db.add_lottery_record(user_id, username, bet, multiplier, total)
        if multiplier == 10:
            db.check_all_achievements(user_id)
        text = f"🎉 *ВЫИГРЫШ!*\n"
        text += f"💰 Ставка: {bet:.0f} MKN\n"
        text += f"🎲 Множитель: x{multiplier}\n"
        text += f"💎 Выигрыш: {prize:.0f} MKN"
        if bonus > 0:
            text += f"\n🎚 +{level_bonus}% от уровня: +{bonus} MKN"
        text += f"\n\n💰 Итого: +{total:.0f} MKN"
    else:
        cashback = bet * 0.1
        db.add_cashback(user_id, cashback)
        text = f"😢 *ПРОИГРЫШ*\n"
        text += f"💰 Ставка: {bet:.0f} MKN\n"
        text += f"🎲 Кэшбэк 10%: +{cashback:.1f} MKN (завтра)\n"
        text += f"💎 Баланс MKN: {db.get_balance(user_id, 'MKN'):.2f}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Сыграть еще", callback_data="lottery_menu")],
        [InlineKeyboardButton("🔙 Главное меню", callback_data="menu")]
    ])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

# ============================================================================
# РЕКОРДЫ
# ============================================================================

async def records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    records = db.get_top_lottery_wins(10)
    if not records:
        text = "🏆 Рекордов пока нет"
    else:
        text = "🏆 *Топ выигрышей*\n\n"
        for i, r in enumerate(records, 1):
            text += f"{i}. @{r['username']} — {r['amount']:.0f} MKN (x{r['multiplier']}) — {r['date']}\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# ЕЖЕДНЕВНЫЙ БОНУС
# ============================================================================

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    can, streak = db.can_claim_daily(user_id)
    if not can:
        await query.edit_message_text(f"🎁 Уже получал сегодня! Серия: {streak} дней", reply_markup=back_keyboard)
        return
    bonus = 100 if streak < 6 else 500
    db.update_balance(user_id, "MKN", bonus, "add")
    db.claim_daily(user_id, streak + 1 if streak > 0 else 1)
    db.add_transaction(user_id, "daily_bonus", "MKN", bonus, "completed")
    text = f"🎁 +{bonus} MKN! Серия: {streak+1} дней" + (" 🔥 ЮБИЛЕЙ!" if streak == 6 else "")
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# ИНВЕСТИЦИИ
# ============================================================================

async def invest_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💼 *Инвестиции*\n📦 7 дней - 5% (10-50 USDT)\n📦 14 дней - 8% (51-200 USDT)\n📦 30 дней - 12% (201-1000 USDT)"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 7 дней", callback_data="invest_7")],
        [InlineKeyboardButton("📦 14 дней", callback_data="invest_14")],
        [InlineKeyboardButton("📦 30 дней", callback_data="invest_30")],
        [InlineKeyboardButton("📋 Мои", callback_data="my_investments")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def invest_package(update: Update, context: ContextTypes.DEFAULT_TYPE, days_key: str):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = f"invest_{days_key}"
    pkg = CONFIG.INVEST_PACKAGES[days_key]
    await query.edit_message_text(f"📦 Введи сумму USDT (от {pkg['min']} до {pkg['max']}):", reply_markup=back_keyboard, parse_mode="Markdown")

async def invest_7(update: Update, context: ContextTypes.DEFAULT_TYPE): await invest_package(update, context, "7 дней")
async def invest_14(update: Update, context: ContextTypes.DEFAULT_TYPE): await invest_package(update, context, "14 дней")
async def invest_30(update: Update, context: ContextTypes.DEFAULT_TYPE): await invest_package(update, context, "30 дней")

async def my_investments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    invs = db.get_active_investments(user_id)
    if not invs:
        text = "📋 Активных инвестиций нет"
    else:
        text = "📋 *Мои инвестиции*\n\n"
        for inv in invs:
            text += f"📦 {inv['package']}\n💰 {inv['amount']} USDT\n📈 +{inv['percent']}%\n📅 до {inv['end_date']}\n\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# P2P
# ============================================================================

async def p2p_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🔄 *P2P Рынок*\nКомиссия: 2%\n\n/buy_mkn ID - купить\n/sell_mkn ID - продать\n/cancel_p2p ID - отменить"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Купить MKN", callback_data="p2p_buy_orders")],
        [InlineKeyboardButton("🔴 Продать MKN", callback_data="p2p_sell_orders")],
        [InlineKeyboardButton("📋 Мои", callback_data="p2p_my_orders")],
        [InlineKeyboardButton("➕ Создать", callback_data="p2p_create")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def p2p_buy_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_active_p2p_orders("sell")
    if not orders:
        await query.edit_message_text("❌ Нет объявлений о продаже", reply_markup=back_keyboard)
        return
    text = "🟢 *Покупка MKN*\n\n"
    for o in orders:
        total = o['amount'] * o['price'] / 1000
        text += f"🆔 #{o['id']} | @{o['username']}\n💰 {o['amount']:.0f} MKN | {o['price']} USDT/1000\n💵 Итого: {total:.4f} USDT\n✅ /buy_mkn {o['id']}\n\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def p2p_sell_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_active_p2p_orders("buy")
    if not orders:
        await query.edit_message_text("❌ Нет объявлений о покупке", reply_markup=back_keyboard)
        return
    text = "🔴 *Продажа MKN*\n\n"
    for o in orders:
        total = o['amount'] * o['price'] / 1000
        text += f"🆔 #{o['id']} | @{o['username']}\n💰 {o['amount']:.0f} MKN | {o['price']} USDT/1000\n💵 Итого: {total:.4f} USDT\n✅ /sell_mkn {o['id']}\n\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def p2p_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    orders = db.get_user_p2p_orders(user_id)
    if not orders:
        await query.edit_message_text("📋 У вас нет активных объявлений", reply_markup=back_keyboard)
        return
    text = "📋 *Мои объявления*\n\n"
    for o in orders:
        text += f"🆔 #{o['id']} | {o['type'].upper()}\n💰 {o['amount']:.0f} MKN | {o['price']} USDT/1000\n❌ /cancel_p2p {o['id']}\n\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def p2p_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "p2p_create"
    await query.edit_message_text("🔄 Формат: ТИП КОЛИЧЕСТВО ЦЕНА\nПример: `sell 1000 0.95`\nТип: buy или sell", reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# АЧИВКИ
# ============================================================================

async def achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    text = "🏅 *Ачивки*\n\n"
    for key, ach in CONFIG.ACHIEVEMENTS.items():
        status = "✅" if db.check_achievement(user_id, key) else "❌"
        text += f"{status} *{ach['name']}* +{ach['reward']} MKN\n   {ach['desc']}\n\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# ОСТАЛЬНЫЕ ОБРАБОТЧИКИ
# ============================================================================

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ref_link = f"https://t.me/{CONFIG.BOT_USERNAME}?start=ref_{user_id}"
    count = db.get_referral_count(user_id)
    earnings = db.get_referral_earnings(user_id)
    text = f"👥 *Рефералы*\n\nСсылка: `{ref_link}`\nПриглашено: {count}\nЗаработано: {earnings:.2f} MKN"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    txns = db.get_user_transactions(user_id, 15)
    if not txns:
        await query.edit_message_text("📜 История пуста", reply_markup=back_keyboard)
        return
    text = "📜 *Последние транзакции*\n\n"
    for tx in txns:
        sign = "+" if tx['type'] in ['deposit', 'lottery_win', 'referral_bonus', 'admin_add', 'daily_bonus', 'achievement', 'invest_return'] else "-"
        text += f"{tx['type']}: {sign}{tx['amount']:.2f} {tx['currency']}\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "ℹ️ *Помощь*\n\n📥 Пополнение: вручную через админа\n📤 Вывод: кошелек → вывести (чек в @CryptoBot)\n🔄 Перевод: @username 10 USDT\n💱 Обмен: /buy или /sell\n🎲 Лотерея: введи сумму → выигрывай\n🎁 Кейсы: 3 типа\n🎡 Рулетка: бесплатно раз в день\n💼 Инвестиции: заморозка USDT\n🔄 P2P: купить/продать MKN\n🏅 Ачивки: награды за действия\n🔑 Промокод: /code КОД"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def deposit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "deposit"
    await query.edit_message_text("💰 Введи сумму в USDT (мин 1):", reply_markup=back_keyboard, parse_mode="Markdown")

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "withdraw"
    await query.edit_message_text(
        f"📤 *Вывод средств*\n\n"
        f"Введи сумму в USDT (мин {CONFIG.MIN_WITHDRAW} USDT)\n"
        f"Комиссия: {CONFIG.WITHDRAW_FEE}% (вычитается из суммы)\n"
        f"Пример: `10`\n\n"
        f"*После создания заявки админ отправит вам чек в @CryptoBot*",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def transfer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "transfer"
    await query.edit_message_text("🔄 Формат: @username 10 USDT\nПример: `@ivan 5 USDT`", reply_markup=back_keyboard, parse_mode="Markdown")

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Проверка...", reply_markup=back_keyboard)

# ============================================================================
# АДМИН-КОМАНДЫ
# ============================================================================

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа")
        return
    text = update.message.text.strip()
    if not text.startswith("/approve_"):
        return
    try:
        req_id = int(text.replace("/approve_", ""))
        req = db.get_withdraw_request(req_id)
        if not req or req['status'] != 'pending':
            await update.message.reply_text(f"❌ Заявка #{req_id} не найдена или уже обработана")
            return
        db.approve_withdraw(req_id)
        user_gets = req['amount'] - (req['amount'] * req['fee'] / 100)
        await context.bot.send_message(
            req['user_id'], 
            f"✅ *Ваша заявка на вывод {req['amount']} USDT обработана!*\n\n"
            f"💰 Получено: {user_gets:.4f} USDT\n"
            f"📤 Чек отправлен в @CryptoBot\n\n"
            f"Проверьте диалог с @CryptoBot",
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"✅ Заявка #{req_id} подтверждена. Чек отправлен пользователю.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа")
        return
    text = update.message.text.strip()
    if not text.startswith("/reject_"):
        return
    try:
        req_id = int(text.replace("/reject_", ""))
        req = db.get_withdraw_request(req_id)
        if not req or req['status'] != 'pending':
            await update.message.reply_text(f"❌ Заявка #{req_id} не найдена или уже обработана")
            return
        db.update_balance(req['user_id'], "USDT", req['amount'], "add")
        db.reject_withdraw(req_id)
        await context.bot.send_message(req['user_id'], f"❌ Заявка на вывод {req['amount']} USDT отклонена. Средства возвращены.", parse_mode="Markdown")
        await update.message.reply_text(f"✅ Заявка #{req_id} отклонена")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def deposit_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Нет доступа")
        return
    text = update.message.text.strip()
    if text.startswith("/deposit_confirm"):
        parts = text.split()
        if len(parts) == 3:
            try:
                target_id = int(parts[1])
                amount = float(parts[2])
                db.update_balance(target_id, "USDT", amount, "add")
                db.add_transaction(target_id, "deposit", "USDT", amount, "completed")
                with db._get_connection() as conn:
                    c = conn.cursor()
                    c.execute("UPDATE users SET total_deposited = total_deposited + ? WHERE user_id = ?", (amount, target_id))
                    conn.commit()
                await context.bot.send_message(target_id, f"✅ Пополнение {amount} USDT подтверждено!", parse_mode="Markdown")
                await update.message.reply_text(f"✅ Пополнение {amount} USDT пользователю {target_id}")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")

async def buy_mkn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/buy_mkn "):
        try:
            order_id = int(text.replace("/buy_mkn ", ""))
            order = db.get_p2p_order(order_id)
            if not order or order['status'] != 'active' or order['type'] != 'sell':
                await update.message.reply_text("❌ Объявление не найдено")
                return
            total = order['amount'] * order['price'] / 1000
            if db.get_balance(update.effective_user.id, "USDT") < total:
                await update.message.reply_text("❌ Недостаточно USDT")
                return
            db.update_balance(update.effective_user.id, "USDT", total, "subtract")
            db.update_balance(update.effective_user.id, "MKN", order['amount'], "add")
            await update.message.reply_text(f"✅ Вы купили {order['amount']:.0f} MKN за {total:.4f} USDT")
            await context.bot.send_message(order['user_id'], f"🔔 Пользователь @{update.effective_user.username} купил {order['amount']:.0f} MKN")
            db.delete_p2p_order(order_id)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def sell_mkn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/sell_mkn "):
        try:
            order_id = int(text.replace("/sell_mkn ", ""))
            order = db.get_p2p_order(order_id)
            if not order or order['status'] != 'active' or order['type'] != 'buy':
                await update.message.reply_text("❌ Объявление не найдено")
                return
            if db.get_balance(update.effective_user.id, "MKN") < order['amount']:
                await update.message.reply_text("❌ Недостаточно MKN")
                return
            db.update_balance(update.effective_user.id, "MKN", order['amount'], "subtract")
            total = order['amount'] * order['price'] / 1000
            db.update_balance(update.effective_user.id, "USDT", total, "add")
            await update.message.reply_text(f"✅ Вы продали {order['amount']:.0f} MKN за {total:.4f} USDT")
            await context.bot.send_message(order['user_id'], f"🔔 Пользователь @{update.effective_user.username} продал {order['amount']:.0f} MKN")
            db.delete_p2p_order(order_id)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def cancel_p2p_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/cancel_p2p "):
        try:
            order_id = int(text.replace("/cancel_p2p ", ""))
            order = db.get_p2p_order(order_id)
            if not order:
                await update.message.reply_text("❌ Объявление не найдено")
                return
            if order['user_id'] != update.effective_user.id and not is_admin(update.effective_user.id):
                await update.message.reply_text("❌ Не ваше объявление")
                return
            db.delete_p2p_order(order_id)
            await update.message.reply_text(f"✅ Объявление #{order_id} отменено")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

# ============================================================================
# ОБРАБОТЧИК ТЕКСТА
# ============================================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = awaiting_state.get(user_id)
    
    user = db.get_user(user_id)
    username = update.effective_user.username or str(user_id)
    if user and user.get('username') != username:
        db.update_username(user_id, username)
    
    # Лотерея - ввод ставки
    if state == "lottery_bet":
        try:
            bet = float(text)
            if bet < CONFIG.MIN_LOTTERY_BET:
                await update.message.reply_text(f"❌ Минимальная ставка: {CONFIG.MIN_LOTTERY_BET} MKN")
                return
            if bet > db.get_balance(user_id, "MKN"):
                await update.message.reply_text(f"❌ Недостаточно MKN. Баланс: {db.get_balance(user_id, 'MKN'):.2f} MKN")
                return
            await lottery_play(update, context, bet)
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
        return
    
    # Админ-команды
    if state == "admin_add" and is_admin(user_id):
        parts = text.split()
        if len(parts) == 3:
            try:
                target_id = int(parts[0])
                currency = parts[1].upper()
                amount = float(parts[2])
                if currency not in CURRENCIES:
                    await update.message.reply_text(f"❌ Доступны: USDT, MKN")
                    return
                db.admin_add_balance(target_id, currency, amount)
                await update.message.reply_text(f"✅ Начислено {amount} {currency} пользователю {target_id}")
                await context.bot.send_message(target_id, f"👑 Администратор начислил вам {amount} {currency}!", parse_mode="Markdown")
            except:
                await update.message.reply_text("❌ Ошибка")
        awaiting_state.pop(user_id, None)
    
    elif state == "admin_gift" and is_admin(user_id):
        parts = text.split()
        if len(parts) == 2:
            currency = parts[0].upper()
            try:
                amount = float(parts[1])
                users = db.get_all_users()
                count = 0
                for u in users:
                    db.update_balance(u['user_id'], currency, amount, "add")
                    count += 1
                await update.message.reply_text(f"✅ Подарок {amount} {currency} отправлен {count} пользователям")
            except:
                await update.message.reply_text("❌ Ошибка")
        awaiting_state.pop(user_id, None)
    
    elif state == "admin_promo" and is_admin(user_id):
        parts = text.split()
        if len(parts) == 4:
            code, currency, amount_str, uses_str = parts
            try:
                amount = float(amount_str)
                uses = int(uses_str)
                if db.create_promo_code(code, currency, amount, uses, user_id):
                    await update.message.reply_text(f"✅ Промокод {code.upper()} создан на {amount} {currency} ({uses} использований)")
                else:
                    await update.message.reply_text("❌ Такой код уже есть")
            except:
                await update.message.reply_text("❌ Ошибка")
        awaiting_state.pop(user_id, None)
    
    # Пользовательские команды
    elif state == "deposit":
        try:
            amount = float(text)
            if amount >= 1:
                await update.message.reply_text(f"💰 Заявка на пополнение {amount} USDT отправлена админу")
                await context.bot.send_message(CONFIG.ADMIN_ID, f"🔔 Заявка на пополнение {amount} USDT от @{update.effective_user.username}\n✅ /deposit_confirm {user_id} {amount}")
            else:
                await update.message.reply_text("❌ Минимум 1 USDT")
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state == "withdraw":
        try:
            amount = float(text)
            if amount < CONFIG.MIN_WITHDRAW:
                await update.message.reply_text(f"❌ Минимальная сумма вывода: {CONFIG.MIN_WITHDRAW} USDT")
                return
            
            fee = amount * CONFIG.WITHDRAW_FEE / 100
            user_gets = amount - fee
            
            if db.get_balance(user_id, "USDT") < amount:
                await update.message.reply_text(f"❌ Недостаточно USDT. Нужно: {amount:.2f} USDT")
                return
            
            db.update_balance(user_id, "USDT", amount, "subtract")
            req_id = db.add_withdraw_request(user_id, update.effective_user.username or str(user_id), amount, "ЧЕК", CONFIG.WITHDRAW_FEE)
            db.add_transaction(user_id, "withdraw", "USDT", amount, "pending", fee=fee, details="Вывод через чек")
            
            await update.message.reply_text(
                f"✅ *Заявка на вывод #{req_id} создана!*\n\n"
                f"💰 Сумма вывода: {amount} USDT\n"
                f"⚡️ Комиссия (5%): {fee:.4f} USDT\n"
                f"📤 Вы получите: {user_gets:.4f} USDT\n\n"
                f"⏳ Администратор обработает заявку и отправит вам чек в @CryptoBot",
                parse_mode="Markdown"
            )
            
            await context.bot.send_message(
                CONFIG.ADMIN_ID,
                f"🔔 *НОВАЯ ЗАЯВКА НА ВЫВОД #{req_id}*\n\n"
                f"👤 Пользователь: @{update.effective_user.username or user_id}\n"
                f"🆔 ID: `{user_id}`\n"
                f"💰 Сумма вывода: {amount} USDT\n"
                f"⚡️ Комиссия 5%: {fee:.4f} USDT\n"
                f"📤 Пользователь получит: {user_gets:.4f} USDT\n\n"
                f"✅ Для отправки чека:\n"
                f"1. Открой @CryptoBot → Создать чек\n"
                f"2. Введи сумму {user_gets:.4f} USDT\n"
                f"3. Отправь чек пользователю @{update.effective_user.username or user_id}\n"
                f"4. После отправки введи: `/approve_{req_id}`",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state == "transfer":
        parts = text.split()
        if len(parts) == 3:
            target_name = parts[0].lstrip("@")
            try:
                amount = float(parts[1])
                currency = parts[2].upper()
                if currency not in CURRENCIES:
                    await update.message.reply_text(f"❌ Доступны: USDT, MKN")
                    return
                if db.get_balance(user_id, currency) >= amount:
                    try:
                        target = await context.bot.get_chat(target_name)
                        db.update_balance(user_id, currency, amount, "subtract")
                        db.update_balance(target.id, currency, amount, "add")
                        await update.message.reply_text(f"✅ Переведено {amount} {currency} @{target_name}")
                    except:
                        await update.message.reply_text("❌ Пользователь не найден")
                else:
                    await update.message.reply_text("❌ Недостаточно средств")
            except:
                await update.message.reply_text("❌ Ошибка")
        awaiting_state.pop(user_id, None)
    
    elif state == "buy_mkn":
        try:
            mkn = float(text)
            if mkn >= CONFIG.MIN_EXCHANGE:
                usd = mkn * CONFIG.MKN_TO_USDT
                if db.get_balance(user_id, "USDT") >= usd:
                    db.update_balance(user_id, "USDT", usd, "subtract")
                    db.update_balance(user_id, "MKN", mkn, "add")
                    await update.message.reply_text(f"✅ Куплено {mkn:.0f} MKN за {usd:.4f} USDT")
                else:
                    await update.message.reply_text("❌ Недостаточно USDT")
            else:
                await update.message.reply_text(f"❌ Минимум {CONFIG.MIN_EXCHANGE} MKN")
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state == "sell_mkn":
        try:
            mkn = float(text)
            if mkn >= CONFIG.MIN_EXCHANGE:
                if db.get_balance(user_id, "MKN") >= mkn:
                    usd = mkn * CONFIG.MKN_TO_USDT * (1 - CONFIG.EXCHANGE_FEE / 100)
                    db.update_balance(user_id, "MKN", mkn, "subtract")
                    db.update_balance(user_id, "USDT", usd, "add")
                    await update.message.reply_text(f"✅ Продано {mkn:.0f} MKN за {usd:.4f} USDT (комиссия {CONFIG.EXCHANGE_FEE}%)")
                else:
                    await update.message.reply_text("❌ Недостаточно MKN")
            else:
                await update.message.reply_text(f"❌ Минимум {CONFIG.MIN_EXCHANGE} MKN")
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state and state.startswith("invest_"):
        days_key = state.replace("invest_", "")
        pkg = CONFIG.INVEST_PACKAGES.get(days_key)
        if pkg:
            try:
                amount = float(text)
                if pkg['min'] <= amount <= pkg['max']:
                    if db.get_balance(user_id, "USDT") >= amount:
                        db.update_balance(user_id, "USDT", amount, "subtract")
                        db.add_investment(user_id, days_key, amount, pkg['days'], pkg['percent'])
                        await update.message.reply_text(f"✅ Инвестиция {days_key} на {amount} USDT оформлена! Доход +{pkg['percent']}% через {pkg['days']} дней")
                        await context.bot.send_message(CONFIG.ADMIN_ID, f"📊 Новая инвестиция от @{update.effective_user.username}\n📦 {days_key} | {amount} USDT | +{pkg['percent']}%")
                    else:
                        await update.message.reply_text("❌ Недостаточно USDT")
                else:
                    await update.message.reply_text(f"❌ Сумма от {pkg['min']} до {pkg['max']} USDT")
            except:
                await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state == "p2p_create":
        parts = text.split()
        if len(parts) == 3:
            otype, amount_str, price_str = parts
            if otype in ['buy', 'sell']:
                try:
                    amount = float(amount_str)
                    price = float(price_str)
                    if otype == 'sell' and db.get_balance(user_id, "MKN") < amount:
                        await update.message.reply_text(f"❌ Недостаточно MKN. Баланс: {db.get_balance(user_id, 'MKN'):.2f}")
                        return
                    db.add_p2p_order(user_id, update.effective_user.username or str(user_id), otype, amount, price)
                    await update.message.reply_text(f"✅ Объявление {otype} {amount:.0f} MKN по {price} USDT/1000 создано")
                except:
                    await update.message.reply_text("❌ Ошибка")
            else:
                await update.message.reply_text("❌ Тип: buy или sell")
        else:
            await update.message.reply_text("❌ Формат: buy 1000 0.95")
        awaiting_state.pop(user_id, None)
    
    elif text.startswith("/code "):
        code = text.replace("/code ", "").strip().upper()
        promo = db.use_promo_code(code, user_id)
        if promo:
            if promo['reward_type'] == "MKN":
                db.update_balance(user_id, "MKN", promo['reward_amount'], "add")
            else:
                db.update_balance(user_id, "USDT", promo['reward_amount'], "add")
            await update.message.reply_text(f"✅ Промокод активирован! +{promo['reward_amount']} {promo['reward_type']}")
        else:
            await update.message.reply_text("❌ Неверный или уже использованный код")

# ============================================================================
# ЗАПУСК
# ============================================================================

def main():
    app = Application.builder().token(CONFIG.BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sendall", sendall_command))
    app.add_handler(CommandHandler("approve_", approve_command))
    app.add_handler(CommandHandler("reject_", reject_command))
    app.add_handler(CommandHandler("deposit_confirm", deposit_confirm_command))
    app.add_handler(CommandHandler("buy_mkn", buy_mkn_command))
    app.add_handler(CommandHandler("sell_mkn", sell_mkn_command))
    app.add_handler(CommandHandler("cancel_p2p", cancel_p2p_command))
    
    app.add_handler(CallbackQueryHandler(confirm_sendall, pattern="^confirm_sendall$"))
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(show_user_wallet, pattern="^wallet_user$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_withdraws, pattern="^admin_withdraws$"))
    app.add_handler(CallbackQueryHandler(admin_investments, pattern="^admin_investments$"))
    app.add_handler(CallbackQueryHandler(admin_add_balance, pattern="^admin_add_balance$"))
    app.add_handler(CallbackQueryHandler(admin_gift, pattern="^admin_gift$"))
    app.add_handler(CallbackQueryHandler(admin_create_promo, pattern="^admin_create_promo$"))
    
    app.add_handler(CallbackQueryHandler(exchange_menu, pattern="^exchange_menu$"))
    app.add_handler(CallbackQueryHandler(buy_mkn, pattern="^buy_mkn$"))
    app.add_handler(CallbackQueryHandler(sell_mkn, pattern="^sell_mkn$"))
    
    app.add_handler(CallbackQueryHandler(cases_menu, pattern="^cases_menu$"))
    app.add_handler(CallbackQueryHandler(case_normal, pattern="^case_normal$"))
    app.add_handler(CallbackQueryHandler(case_gold, pattern="^case_gold$"))
    app.add_handler(CallbackQueryHandler(case_diamond, pattern="^case_diamond$"))
    
    app.add_handler(CallbackQueryHandler(lottery_menu, pattern="^lottery_menu$"))
    app.add_handler(CallbackQueryHandler(records, pattern="^records$"))
    app.add_handler(CallbackQueryHandler(daily, pattern="^daily$"))
    
    app.add_handler(CallbackQueryHandler(invest_menu, pattern="^invest_menu$"))
    app.add_handler(CallbackQueryHandler(invest_7, pattern="^invest_7$"))
    app.add_handler(CallbackQueryHandler(invest_14, pattern="^invest_14$"))
    app.add_handler(CallbackQueryHandler(invest_30, pattern="^invest_30$"))
    app.add_handler(CallbackQueryHandler(my_investments, pattern="^my_investments$"))
    
    app.add_handler(CallbackQueryHandler(p2p_menu, pattern="^p2p_menu$"))
    app.add_handler(CallbackQueryHandler(p2p_buy_orders, pattern="^p2p_buy_orders$"))
    app.add_handler(CallbackQueryHandler(p2p_sell_orders, pattern="^p2p_sell_orders$"))
    app.add_handler(CallbackQueryHandler(p2p_my_orders, pattern="^p2p_my_orders$"))
    app.add_handler(CallbackQueryHandler(p2p_create, pattern="^p2p_create$"))
    
    app.add_handler(CallbackQueryHandler(achievements, pattern="^achievements$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(help_command, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(deposit_handler, pattern="^deposit$"))
    app.add_handler(CallbackQueryHandler(withdraw_handler, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(transfer_handler, pattern="^transfer$"))
    app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 CryptoKan 2.0 запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
