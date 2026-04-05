import json
import sqlite3
import random
import urllib.request
import threading
import time
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
    ADMIN_ID: int = 8780917575
    BOT_USERNAME: str = "CryptoKanS1x_bot"
    
    WITHDRAW_FEE: int = 5
    REFERRAL_PERCENT: int = 5
    REGISTRATION_BONUS: float = 100
    REFERRAL_BONUS: float = 50
    LOTTERY_COST: float = 100
    
    MKN_TO_USDT: float = 0.001
    EXCHANGE_FEE: float = 2
    MIN_EXCHANGE: float = 100
    MIN_WITHDRAW: float = 1.1
    P2P_FEE: float = 2
    P2P_TIMEOUT_MINUTES: int = 30
    
    FIRST_DEPOSIT_BONUS: Dict[float, float] = None
    CASES: Dict[str, Dict] = None
    INVEST_PACKAGES: Dict[str, Dict] = None
    LEVELS: Dict[float, int] = None
    ROULETTE_REWARDS: Dict[int, float] = None
    LOTTERY_MULTIPLIERS: Dict[int, int] = None
    RATES: Dict[str, float] = None
    
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
        
        if self.ROULETTE_REWARDS is None:
            self.ROULETTE_REWARDS = {10: 40, 25: 25, 50: 15, 100: 10, 200: 5, 500: 3, 1000: 1.5, 5000: 0.5}
        
        if self.LOTTERY_MULTIPLIERS is None:
            self.LOTTERY_MULTIPLIERS = {2: 15, 5: 5, 10: 1}
        
        if self.RATES is None:
            self.RATES = {"USDT": 1.0, "TON": 5.2, "BTC": 65000, "ETH": 3500, "SOL": 180}
        
        if self.ACHIEVEMENTS is None:
            self.ACHIEVEMENTS = {
                "first_step": {"name": "🎉 Первый шаг", "desc": "Зарегистрироваться", "reward": 10, "condition": "register"},
                "lucky": {"name": "🍀 Везунчик", "desc": "Выиграть x10 в лотерее", "reward": 200, "condition": "lottery_x10"},
                "sponsor": {"name": "💰 Спонсор", "desc": "Пополнить 100+ USDT", "reward": 500, "condition": "deposit_100"},
                "legend": {"name": "👑 Легенда", "desc": "Пополнить 1000+ USDT", "reward": 2000, "condition": "deposit_1000"},
                "referral_king": {"name": "🤝 Король рефералов", "desc": "Пригласить 20 друзей", "reward": 500, "condition": "referrals_20"},
                "gambler": {"name": "🎲 Азартный", "desc": "Открыть 50 кейсов", "reward": 300, "condition": "cases_50"},
                "millionaire": {"name": "💎 Миллионер", "desc": "Баланс 1M+ MKN", "reward": 5000, "condition": "mkn_1000000"},
                "collector": {"name": "📦 Коллекционер", "desc": "Открыть 100 кейсов", "reward": 1000, "condition": "cases_100"},
                "fortune": {"name": "🎡 Фортуна", "desc": "Выиграть в рулетке 5000+ MKN", "reward": 500, "condition": "roulette_5000"},
                "investor": {"name": "💼 Инвестор", "desc": "Вложить 500+ USDT в инвестиции", "reward": 1000, "condition": "invest_500"}
            }


CONFIG = Config()
CURRENCIES = ["USDT", "TON", "BTC", "ETH", "SOL", "MKN"]

# ============================================================================
# БАЗА ДАННЫХ (РАСШИРЕННАЯ)
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
            # Основная таблица пользователей
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
                total_lost REAL DEFAULT 0,
                cases_opened INTEGER DEFAULT 0,
                roulette_max_win REAL DEFAULT 0,
                daily_streak INTEGER DEFAULT 0,
                last_daily DATE,
                last_roulette DATE,
                first_deposit_bonus INTEGER DEFAULT 0,
                cashback_pending REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Инвестиции
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
            
            # Промокоды
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
            
            # Ачивки
            c.execute('''CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                achievement TEXT,
                earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Рекорды лотереи
            c.execute('''CREATE TABLE IF NOT EXISTS lottery_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                amount REAL,
                multiplier INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Транзакции
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
            
            # Рефералы
            c.execute('''CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                amount REAL,
                earned REAL,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Заявки на вывод
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
            
            # P2P объявления
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
            
            # P2P сделки
            c.execute('''CREATE TABLE IF NOT EXISTS p2p_deals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                seller_id INTEGER,
                buyer_id INTEGER,
                amount REAL,
                price REAL,
                total REAL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            conn.commit()
    
    # ========== USER METHODS ==========
    
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
    
    def get_user_level(self, user_id: int) -> int:
        user = self.get_user(user_id)
        if not user:
            return 0
        deposited = user.get('total_deposited', 0)
        level_bonus = 0
        for threshold, bonus in sorted(CONFIG.LEVELS.items()):
            if deposited >= threshold:
                level_bonus = bonus
        return level_bonus
    
    # ========== BALANCE METHODS ==========
    
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
    
    # ========== ACHIEVEMENTS ==========
    
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
    
    def check_all_achievements(self, user_id: int, context=None):
        user = self.get_user(user_id)
        if not user:
            return
        
        # Первый шаг
        if not self.check_achievement(user_id, "first_step"):
            self.add_achievement(user_id, "first_step", CONFIG.ACHIEVEMENTS["first_step"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n🎉 {CONFIG.ACHIEVEMENTS['first_step']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['first_step']['reward']} MKN", parse_mode="Markdown"))
        
        # Спонсор и Легенда
        deposited = user.get('total_deposited', 0)
        if deposited >= 100 and not self.check_achievement(user_id, "sponsor"):
            self.add_achievement(user_id, "sponsor", CONFIG.ACHIEVEMENTS["sponsor"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n💰 {CONFIG.ACHIEVEMENTS['sponsor']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['sponsor']['reward']} MKN", parse_mode="Markdown"))
        if deposited >= 1000 and not self.check_achievement(user_id, "legend"):
            self.add_achievement(user_id, "legend", CONFIG.ACHIEVEMENTS["legend"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n👑 {CONFIG.ACHIEVEMENTS['legend']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['legend']['reward']} MKN", parse_mode="Markdown"))
        
        # Рефералы
        referrals = self.get_referral_count(user_id)
        if referrals >= 20 and not self.check_achievement(user_id, "referral_king"):
            self.add_achievement(user_id, "referral_king", CONFIG.ACHIEVEMENTS["referral_king"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n🤝 {CONFIG.ACHIEVEMENTS['referral_king']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['referral_king']['reward']} MKN", parse_mode="Markdown"))
        
        # Кейсы
        cases_opened = user.get('cases_opened', 0)
        if cases_opened >= 50 and not self.check_achievement(user_id, "gambler"):
            self.add_achievement(user_id, "gambler", CONFIG.ACHIEVEMENTS["gambler"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n🎲 {CONFIG.ACHIEVEMENTS['gambler']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['gambler']['reward']} MKN", parse_mode="Markdown"))
        if cases_opened >= 100 and not self.check_achievement(user_id, "collector"):
            self.add_achievement(user_id, "collector", CONFIG.ACHIEVEMENTS["collector"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n📦 {CONFIG.ACHIEVEMENTS['collector']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['collector']['reward']} MKN", parse_mode="Markdown"))
        
        # Миллионер MKN
        mkn_balance = user.get('balance_mkn', 0)
        if mkn_balance >= 1000000 and not self.check_achievement(user_id, "millionaire"):
            self.add_achievement(user_id, "millionaire", CONFIG.ACHIEVEMENTS["millionaire"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n💎 {CONFIG.ACHIEVEMENTS['millionaire']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['millionaire']['reward']} MKN", parse_mode="Markdown"))
        
        # Рулетка
        roulette_max = user.get('roulette_max_win', 0)
        if roulette_max >= 5000 and not self.check_achievement(user_id, "fortune"):
            self.add_achievement(user_id, "fortune", CONFIG.ACHIEVEMENTS["fortune"]["reward"])
            if context:
                asyncio.create_task(context.bot.send_message(user_id, f"🏆 *Ачивка получена!*\n🎡 {CONFIG.ACHIEVEMENTS['fortune']['name']}\n💰 +{CONFIG.ACHIEVEMENTS['fortune']['reward']} MKN", parse_mode="Markdown"))
    
    # ========== DAILY BONUS ==========
    
    def can_claim_daily(self, user_id: int) -> Tuple[bool, int]:
        user = self.get_user(user_id)
        if not user:
            return True, 0
        last = user.get('last_daily')
        streak = user.get('daily_streak', 0)
        today = date.today()
        if not last:
            return True, 0
        last_date = datetime.strptime(last, "%Y-%m-%d").date() if isinstance(last, str) else last
        diff = (today - last_date).days
        if diff == 0:
            return False, streak
        elif diff == 1:
            return True, streak + 1
        else:
            return True, 1
    
    def claim_daily(self, user_id: int, streak: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET daily_streak = ?, last_daily = ? WHERE user_id = ?",
                      (streak, date.today().isoformat(), user_id))
            conn.commit()
    
    # ========== ROULETTE ==========
    
    def can_claim_roulette(self, user_id: int) -> bool:
        user = self.get_user(user_id)
        if not user:
            return True
        last = user.get('last_roulette')
        if not last:
            return True
        last_date = datetime.strptime(last, "%Y-%m-%d").date() if isinstance(last, str) else last
        return date.today() > last_date
    
    def claim_roulette(self, user_id: int, win_amount: float):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET last_roulette = ? WHERE user_id = ?",
                      (date.today().isoformat(), user_id))
            c.execute("UPDATE users SET roulette_max_win = MAX(roulette_max_win, ?) WHERE user_id = ?",
                      (win_amount, user_id))
            conn.commit()
    
    # ========== CASHBACK ==========
    
    def add_cashback(self, user_id: int, amount: float):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET cashback_pending = cashback_pending + ? WHERE user_id = ?",
                      (amount, user_id))
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
    
    # ========== LOTTERY RECORDS ==========
    
    def add_lottery_record(self, user_id: int, username: str, amount: float, multiplier: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO lottery_records (user_id, username, amount, multiplier)
                         VALUES (?, ?, ?, ?)''', (user_id, username, amount, multiplier))
            conn.commit()
    
    def get_top_lottery_wins(self, limit: int = 10) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''SELECT username, amount, multiplier, created_at
                         FROM lottery_records ORDER BY amount DESC LIMIT ?''', (limit,))
            rows = c.fetchall()
            return [{"username": r[0], "amount": r[1], "multiplier": r[2], "date": r[3][:10]} for r in rows]
    
    # ========== INVESTMENTS ==========
    
    def add_investment(self, user_id: int, package: str, amount: float, days: int, percent: int):
        end_date = date.today() + timedelta(days=days)
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO investments (user_id, package, amount, start_date, end_date, percent)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (user_id, package, amount, date.today().isoformat(), end_date.isoformat(), percent))
            conn.commit()
            return c.lastrowid
    
    def get_active_investments(self, user_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM investments WHERE user_id = ? AND status = 'active'", (user_id,))
            rows = c.fetchall()
            columns = [d[0] for d in c.description]
            return [dict(zip(columns, row)) for row in rows]
    
    def check_completed_investments(self, user_id: int, context=None) -> float:
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
    
    # ========== PROMO CODES ==========
    
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
    
    # ========== REFERRALS ==========
    
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
    
    # ========== WITHDRAW REQUESTS ==========
    
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
    
    # ========== P2P METHODS ==========
    
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
    
    def create_p2p_deal(self, order_id: int, buyer_id: int, buyer_name: str, amount: float, price: float, total: float) -> int:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO p2p_deals (order_id, seller_id, buyer_id, amount, price, total)
                         VALUES (?, (SELECT user_id FROM p2p_orders WHERE id = ?), ?, ?, ?, ?)''',
                      (order_id, order_id, buyer_id, amount, price, total))
            conn.commit()
            return c.lastrowid
    
    def get_pending_deal(self, deal_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM p2p_deals WHERE id = ? AND status = 'pending'", (deal_id,))
            row = c.fetchone()
            if row:
                columns = [d[0] for d in c.description]
                return dict(zip(columns, row))
        return None
    
    def confirm_p2p_deal(self, deal_id: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE p2p_deals SET status = 'completed' WHERE id = ?", (deal_id,))
            conn.commit()
    
    def cancel_p2p_deal(self, deal_id: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE p2p_deals SET status = 'cancelled' WHERE id = ?", (deal_id,))
            conn.commit()
    
    def get_user_p2p_orders(self, user_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM p2p_orders WHERE user_id = ? AND status = 'active'", (user_id,))
            rows = c.fetchall()
            columns = [d[0] for d in c.description]
            return [dict(zip(columns, row)) for row in rows]
    
    # ========== STATS ==========
    
    def get_all_users(self) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT user_id, username, balance_usdt, balance_mkn, total_deposited, created_at FROM users ORDER BY total_deposited DESC")
            rows = c.fetchall()
            columns = ['user_id', 'username', 'balance_usdt', 'balance_mkn', 'total_deposited', 'created_at']
            return [dict(zip(columns, row)) for row in rows]
    
    def get_top_donators(self, limit: int = 10) -> List[Dict]:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT username, total_deposited FROM users WHERE total_deposited > 0 ORDER BY total_deposited DESC LIMIT ?", (limit,))
            rows = c.fetchall()
            return [{"username": r[0] or str(r[1]), "amount": r[1]} for r in rows]
    
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
    
    def increment_cases_opened(self, user_id: int):
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET cases_opened = cases_opened + 1 WHERE user_id = ?", (user_id,))
            conn.commit()


# ============================================================================
# БОТ
# ============================================================================

import asyncio

db = Database()
awaiting_state = {}

# Клавиатуры
main_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏦 Кошелек", callback_data="wallet")],
    [InlineKeyboardButton("💱 Обменник", callback_data="exchange_menu")],
    [InlineKeyboardButton("🎲 Лотерея", callback_data="lottery")],
    [InlineKeyboardButton("🎁 Кейсы", callback_data="cases_menu")],
    [InlineKeyboardButton("👥 Рефералы", callback_data="referral")],
    [InlineKeyboardButton("📜 История", callback_data="history")],
    [InlineKeyboardButton("🏆 Рекорды", callback_data="records")],
    [InlineKeyboardButton("🎡 Рулетка", callback_data="roulette")],
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
    [InlineKeyboardButton("➕ Пополнить пользователя", callback_data="admin_add_balance")],
    [InlineKeyboardButton("🎁 Массовый подарок", callback_data="admin_gift")],
    [InlineKeyboardButton("🔑 Создать промокод", callback_data="admin_create_promo")],
    [InlineKeyboardButton("🔙 Главное меню", callback_data="menu")]
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
    
    # Проверка завершенных инвестиций
    invest_return = db.check_completed_investments(user_id, context)
    if invest_return > 0:
        db.update_balance(user_id, "USDT", invest_return, "add")
        await update.message.reply_text(f"💰 *Инвестиция завершена!*\nТы получил {invest_return:.2f} USDT с процентами!", parse_mode="Markdown")
    
    # Проверка кэшбэка
    cashback = db.claim_cashback(user_id)
    if cashback > 0:
        db.update_balance(user_id, "MKN", cashback, "add")
        await update.message.reply_text(f"💰 *Кэшбэк начислен!*\nТы получил {cashback:.1f} MKN за вчерашние проигрыши в лотерее!", parse_mode="Markdown")
    
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
    
    # Проверка ачивок
    db.check_all_achievements(user_id, context)
    
    balances = db.get_all_balances(user_id)
    level_bonus = db.get_user_level(user_id)
    balance_text = "🏦 *CryptoKan 2.0*\n\n"
    for c in CURRENCIES:
        if c == "MKN":
            balance_text += f"💎 {c}: `{balances[c]:.2f}`\n"
        else:
            balance_text += f"💰 {c}: `{balances[c]:.4f}`\n"
    balance_text += f"\n👥 Рефералов: {db.get_referral_count(user_id)}"
    balance_text += f"\n🎚 Уровень: +{level_bonus}% к лотерее"
    balance_text += f"\n💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT"
    balance_text += f"\n📤 Мин. вывод: {CONFIG.MIN_WITHDRAW} USDT (комиссия 5%)"
    
    await update.message.reply_text(
        f"✨ *Добро пожаловать в CryptoKan 2.0* ✨\n\n{balance_text}",
        reply_markup=main_keyboard,
        parse_mode="Markdown"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    # Проверка завершенных инвестиций
    invest_return = db.check_completed_investments(user_id, context)
    if invest_return > 0:
        db.update_balance(user_id, "USDT", invest_return, "add")
        await query.edit_message_text(f"💰 *Инвестиция завершена!*\nТы получил {invest_return:.2f} USDT с процентами!\n\nВозвращаемся в меню...", parse_mode="Markdown")
        await asyncio.sleep(2)
    
    # Проверка кэшбэка
    cashback = db.claim_cashback(user_id)
    if cashback > 0:
        db.update_balance(user_id, "MKN", cashback, "add")
        await query.edit_message_text(f"💰 *Кэшбэк начислен!*\nТы получил {cashback:.1f} MKN за вчерашние проигрыши!\n\nВозвращаемся в меню...", parse_mode="Markdown")
        await asyncio.sleep(2)
    
    db.check_all_achievements(user_id, context)
    
    balances = db.get_all_balances(user_id)
    level_bonus = db.get_user_level(user_id)
    balance_text = "🏦 *CryptoKan 2.0*\n\n"
    for c in CURRENCIES:
        if c == "MKN":
            balance_text += f"💎 {c}: `{balances[c]:.2f}`\n"
        else:
            balance_text += f"💰 {c}: `{balances[c]:.4f}`\n"
    balance_text += f"\n👥 Рефералов: {db.get_referral_count(user_id)}"
    balance_text += f"\n🎚 Уровень: +{level_bonus}% к лотерее"
    await query.edit_message_text(
        f"✨ *CryptoKan 2.0* ✨\n\n{balance_text}",
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
    text = "🏦 *Твой кошелек CryptoKan 2.0*\n\n"
    for c in CURRENCIES:
        if c == "MKN":
            text += f"💎 {c}: `{balances[c]:.2f}`\n"
        else:
            text += f"💰 {c}: `{balances[c]:.6f}`\n"
    text += f"\n💸 Комиссия на вывод: 5% (вычитается из суммы)"
    text += f"\n💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT"
    text += f"\n📤 Мин. вывод: {CONFIG.MIN_WITHDRAW} USDT"
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
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет доступа к админ-панели!", reply_markup=back_keyboard)
        return
    
    stats = db.get_stats()
    text = "👑 *Админ-панель CryptoKan 2.0*\n\n"
    text += f"📊 Пользователей: {stats['users']}\n"
    text += f"💰 Всего депозитов: {stats['deposits']:.2f} USDT\n"
    text += f"📤 Всего выводов: {stats['withdraws']:.2f} USDT\n"
    text += f"💎 MKN в обращении: {stats['mkn_supply']:.2f}\n"
    text += f"🎲 Всего выиграно: {stats['total_won']:.0f} MKN"
    
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    stats = db.get_stats()
    text = "📊 *Статистика*\n\n"
    text += f"👥 Пользователей: {stats['users']}\n"
    text += f"💰 Депозитов: {stats['deposits']:.2f} USDT\n"
    text += f"📤 Выводов: {stats['withdraws']:.2f} USDT\n"
    text += f"💎 MKN в обращении: {stats['mkn_supply']:.2f}\n"
    text += f"🎲 Всего выиграно: {stats['total_won']:.0f} MKN"
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    users = db.get_all_users()
    if not users:
        await query.edit_message_text("Нет пользователей", reply_markup=admin_keyboard)
        return
    text = "👥 *Пользователи CryptoKan 2.0*\n\n"
    for u in users[:20]:
        text += f"🆔 `{u['user_id']}` | @{u['username'] or 'no_username'}\n"
        text += f"   💰 USDT: {u['balance_usdt']:.2f} | 💎 MKN: {u['balance_mkn']:.0f}\n"
        text += f"   📥 Депозитов: {u['total_deposited']:.2f} USDT\n\n"
    if len(users) > 20:
        text += f"... и еще {len(users) - 20} пользователей"
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_withdraws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
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
        text += f"⚡️ Комиссия ({w['fee']}%): {w['amount'] * w['fee'] / 100:.4f}\n"
        text += f"📤 Пользователь получит: {user_gets:.4f}\n"
        text += f"📤 Адрес: `{w['address'][:30]}...`\n"
        text += f"✅ `/approve_{w['id']}` - подтвердить\n"
        text += f"❌ `/reject_{w['id']}` - отклонить\n\n"
    await query.edit_message_text(text, reply_markup=admin_keyboard, parse_mode="Markdown")

async def admin_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    awaiting_state[query.from_user.id] = "admin_add"
    await query.edit_message_text(
        "➕ *Пополнение пользователя*\n\nВведи ID пользователя, валюту и сумму через пробел:\nПример: `123456789 USDT 100`\nПример: `987654321 MKN 500`",
        reply_markup=admin_keyboard,
        parse_mode="Markdown"
    )

async def admin_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    awaiting_state[query.from_user.id] = "admin_gift"
    await query.edit_message_text(
        "🎁 *Массовый подарок*\n\nВведи валюту и сумму через пробел:\nПример: `MKN 100`\nПример: `USDT 5`\n\nПодарок получат ВСЕ пользователи бота.",
        reply_markup=admin_keyboard,
        parse_mode="Markdown"
    )

async def admin_create_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    awaiting_state[query.from_user.id] = "admin_promo"
    await query.edit_message_text(
        "🔑 *Создание промокода*\n\nФормат: `КОД ВАЛЮТА СУММА КОЛИЧЕСТВО`\nПример: `HELLO MKN 100 50`\n\nВАЛЮТА: MKN или USDT\nКОЛИЧЕСТВО: сколько раз можно использовать",
        reply_markup=admin_keyboard,
        parse_mode="Markdown"
    )

# ============================================================================
# ОБМЕННИК
# ============================================================================

async def exchange_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💱 *Обменник CryptoKan 2.0*\n\n"
    text += f"💎 1 MKN = {CONFIG.MKN_TO_USDT} USDT\n"
    text += f"💰 1 USDT = {int(1 / CONFIG.MKN_TO_USDT)} MKN\n"
    text += f"⚡️ Комиссия: {CONFIG.EXCHANGE_FEE}% (при обмене MKN→USDT)\n"
    text += f"🔄 Мин. сумма: {CONFIG.MIN_EXCHANGE} MKN\n\n"
    text += "Используй команды:\n"
    text += "`/buy 500` - купить 500 MKN за USDT\n"
    text += "`/sell 500` - продать 500 MKN за USDT"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Купить MKN", callback_data="buy_mkn")],
        [InlineKeyboardButton("💎 Продать MKN", callback_data="sell_mkn")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def buy_mkn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "buy_mkn"
    await query.edit_message_text(
        f"💎 *Покупка MKN*\n\nКурс: 1 USDT = {int(1 / CONFIG.MKN_TO_USDT)} MKN\n"
        f"Комиссия: 0%\n"
        f"Минимум: {CONFIG.MIN_EXCHANGE} MKN\n\n"
        f"Введи сумму MKN, которую хочешь купить:\nПример: `500`",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def sell_mkn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "sell_mkn"
    await query.edit_message_text(
        f"💎 *Продажа MKN*\n\nКурс: 1000 MKN = {1000 * CONFIG.MKN_TO_USDT * (1 - CONFIG.EXCHANGE_FEE/100):.4f} USDT\n"
        f"Комиссия: {CONFIG.EXCHANGE_FEE}%\n"
        f"Минимум: {CONFIG.MIN_EXCHANGE} MKN\n\n"
        f"Введи сумму MKN, которую хочешь продать:\nПример: `500`",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

# ============================================================================
# КЕЙСЫ
# ============================================================================

async def cases_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🎁 *Кейсы CryptoKan 2.0*\n\n"
    for case_name, case_data in CONFIG.CASES.items():
        text += f"📦 *{case_name.upper()} кейс* — {case_data['price']} MKN\n"
        text += f"   Шансы: "
        for reward, chance in case_data['rewards'][:3]:
            text += f"{reward}MKN({chance}%) "
        text += f"...\n\n"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Обычный (100 MKN)", callback_data="case_normal")],
        [InlineKeyboardButton("📦 Золотой (500 MKN)", callback_data="case_gold")],
        [InlineKeyboardButton("📦 Алмазный (2000 MKN)", callback_data="case_diamond")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def open_case(update: Update, context: ContextTypes.DEFAULT_TYPE, case_type: str):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    case = CONFIG.CASES[case_type]
    price = case['price']
    balance = db.get_balance(user_id, "MKN")
    if balance < price:
        await query.edit_message_text(f"❌ Недостаточно MKN! Нужно: {price} MKN", reply_markup=back_keyboard)
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
    db.add_transaction(user_id, "case_open", "MKN", price, "completed", details=f"Кейс: {case_type}, выигрыш: {reward} MKN")
    
    # Проверка ачивок
    db.check_all_achievements(user_id, context)
    
    if reward > price:
        text = f"🎉 *ПОЗДРАВЛЯЮ!*\nТы открыл {case_type} кейс и выиграл {reward} MKN!\n💰 Профит: +{reward - price} MKN"
    elif reward == price:
        text = f"🔄 *Возврат!*\nТы открыл {case_type} кейс и вернул {reward} MKN.\n💰 Убыток: 0 MKN"
    else:
        text = f"😢 *Не повезло...*\nТы открыл {case_type} кейс и получил {reward} MKN.\n💰 Убыток: -{price - reward} MKN"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Открыть еще", callback_data=f"case_{case_type}")],
        [InlineKeyboardButton("🔙 Меню кейсов", callback_data="cases_menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def case_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_case(update, context, "обычный")

async def case_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_case(update, context, "золотой")

async def case_diamond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await open_case(update, context, "алмазный")

# ============================================================================
# ЛОТЕРЕЯ
# ============================================================================

async def lottery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = db.get_balance(user_id, "MKN")
    if balance < CONFIG.LOTTERY_COST:
        await query.edit_message_text(f"❌ Недостаточно MKN! Нужно: {CONFIG.LOTTERY_COST} MKN", reply_markup=back_keyboard)
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
    
    level_bonus = db.get_user_level(user_id)
    if win:
        prize = CONFIG.LOTTERY_COST * multiplier
        bonus_prize = int(prize * level_bonus / 100)
        total_prize = prize + bonus_prize
        db.update_balance(user_id, "MKN", total_prize, "add")
        db.add_transaction(user_id, "lottery_win", "MKN", total_prize, "completed")
        
        username = query.from_user.username or str(user_id)
        db.add_lottery_record(user_id, username, total_prize, multiplier)
        
        # Проверка ачивок
        if multiplier == 10:
            db.check_all_achievements(user_id, context)
        
        text = f"🎉 *ВЫИГРЫШ x{multiplier}!*\n"
        text += f"💰 {prize} MKN (база)\n"
        if bonus_prize > 0:
            text += f"🎚 +{level_bonus}% от уровня: +{bonus_prize} MKN\n"
        text += f"💎 Итого: +{total_prize} MKN\n"
        text += f"💎 Баланс MKN: {db.get_balance(user_id, 'MKN'):.2f}"
    else:
        cashback = CONFIG.LOTTERY_COST * 0.1
        db.add_cashback(user_id, cashback)
        text = f"😢 *Проигрыш* -{CONFIG.LOTTERY_COST} MKN\n"
        text += f"💰 Кэшбэк 10%: +{cashback:.1f} MKN (начислится завтра)\n"
        text += f"💎 Баланс MKN: {db.get_balance(user_id, 'MKN'):.2f}"
    
    lottery_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Еще раз", callback_data="lottery")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=lottery_keyboard, parse_mode="Markdown")

# ============================================================================
# РЕКОРДЫ ЛОТЕРЕИ
# ============================================================================

async def records(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    records = db.get_top_lottery_wins(10)
    if not records:
        text = "🏆 *Рекорды лотереи*\n\nПока нет рекордов. Стань первым!"
    else:
        text = "🏆 *Топ-10 выигрышей в лотерее*\n\n"
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
    can_claim, streak = db.can_claim_daily(user_id)
    if not can_claim:
        await query.edit_message_text(
            f"🎁 *Ежедневный бонус*\n\nТы уже получил бонус сегодня!\n🔥 Текущая серия: {streak} дней",
            reply_markup=back_keyboard,
            parse_mode="Markdown"
        )
        return
    
    bonus = 100 if streak < 6 else 500
    db.update_balance(user_id, "MKN", bonus, "add")
    db.claim_daily(user_id, streak + 1 if streak > 0 else 1)
    db.add_transaction(user_id, "daily_bonus", "MKN", bonus, "completed")
    
    text = f"🎁 *Ежедневный бонус получен!*\n\n"
    if streak == 6:
        text += f"🔥 *ЮБИЛЕЙ! 7 ДНЕЙ ПОДРЯД!*\n"
        text += f"💰 +{bonus} MKN\n"
        text += f"💎 Ты получил максимальный бонус!"
    else:
        text += f"💰 +{bonus} MKN\n"
        text += f"🔥 Серия: {streak + 1} дней\n"
        text += f"💎 Баланс MKN: {db.get_balance(user_id, 'MKN'):.2f}"
        if streak + 1 < 7:
            text += f"\n\n⭐ Осталось дней до юбилея: {7 - (streak + 1)}"
    
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# БЕСПЛАТНАЯ РУЛЕТКА
# ============================================================================

async def roulette(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if not db.can_claim_roulette(user_id):
        await query.edit_message_text(
            "🎡 *Бесплатная рулетка*\n\nТы уже крутил рулетку сегодня!\nЗаходи завтра снова!",
            reply_markup=back_keyboard,
            parse_mode="Markdown"
        )
        return
    
    rand = random.randint(1, 100)
    cumulative = 0
    reward = 0
    for r, chance in CONFIG.ROULETTE_REWARDS.items():
        cumulative += chance
        if rand <= cumulative:
            reward = r
            break
    
    db.update_balance(user_id, "MKN", reward, "add")
    db.claim_roulette(user_id, reward)
    db.add_transaction(user_id, "roulette", "MKN", reward, "completed")
    
    # Проверка ачивок
    db.check_all_achievements(user_id, context)
    
    if reward >= 500:
        text = f"🎡 *ПОЗДРАВЛЯЮ!*\nТы выиграл {reward} MKN в бесплатной рулетке! 🎉"
    else:
        text = f"🎡 *Бесплатная рулетка*\n\nТебе выпало: +{reward} MKN\n💎 Баланс MKN: {db.get_balance(user_id, 'MKN'):.2f}"
    
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

# ============================================================================
# ИНВЕСТИЦИИ
# ============================================================================

async def invest_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "💼 *Инвестиционные пакеты CryptoKan 2.0*\n\n"
    for name, pkg in CONFIG.INVEST_PACKAGES.items():
        text += f"📦 *{name}* — от {pkg['min']} до {pkg['max']} USDT\n"
        text += f"   Доходность: +{pkg['percent']}% через {pkg['days']} дней\n\n"
    text += "💰 После окончания срока ты получишь обратно вложенную сумму + проценты!\n"
    text += "⚡️ Вложенные средства замораживаются на указанный срок."
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 7 дней (5%)", callback_data="invest_7")],
        [InlineKeyboardButton("📦 14 дней (8%)", callback_data="invest_14")],
        [InlineKeyboardButton("📦 30 дней (12%)", callback_data="invest_30")],
        [InlineKeyboardButton("📋 Мои инвестиции", callback_data="my_investments")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def invest_package(update: Update, context: ContextTypes.DEFAULT_TYPE, days_key: str):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = f"invest_{days_key}"
    pkg = CONFIG.INVEST_PACKAGES[days_key]
    await query.edit_message_text(
        f"📦 *Инвестиция {days_key}*\n\n"
        f"Доходность: +{pkg['percent']}% через {pkg['days']} дней\n"
        f"Сумма: от {pkg['min']} до {pkg['max']} USDT\n\n"
        f"Введи сумму в USDT для инвестирования:",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def my_investments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    investments = db.get_active_investments(user_id)
    if not investments:
        text = "📋 *Мои инвестиции*\n\nУ тебя нет активных инвестиций."
    else:
        text = "📋 *Мои инвестиции*\n\n"
        for inv in investments:
            text += f"📦 {inv['package']}\n"
            text += f"💰 Сумма: {inv['amount']} USDT\n"
            text += f"📈 Доход: +{inv['percent']}%\n"
            text += f"📅 Завершение: {inv['end_date']}\n\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")
    
    async def invest_7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await invest_package(update, context, "7 дней")

async def invest_14(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await invest_package(update, context, "14 дней")

async def invest_30(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await invest_package(update, context, "30 дней")

# ============================================================================
# P2P РЫНОК (ПОЛНОСТЬЮ РАБОЧИЙ)
# ============================================================================

async def p2p_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Показываем активные объявления
    buy_orders = db.get_active_p2p_orders("buy")
    sell_orders = db.get_active_p2p_orders("sell")
    
    text = "🔄 *P2P Рынок CryptoKan 2.0*\n\n"
    text += f"🟢 *Продажа MKN:*\n"
    if sell_orders:
        for o in sell_orders[:5]:
            text += f"   @{o['username']} | {o['amount']} MKN | {o['price']} USDT/1000\n"
    else:
        text += "   Нет активных объявлений\n"
    
    text += f"\n🔴 *Покупка MKN:*\n"
    if buy_orders:
        for o in buy_orders[:5]:
            text += f"   @{o['username']} | {o['amount']} MKN | {o['price']} USDT/1000\n"
    else:
        text += "   Нет активных объявлений\n"
    
    text += f"\n⚡️ Комиссия платформы: {CONFIG.P2P_FEE}% (с продавца)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Купить MKN", callback_data="p2p_buy_orders")],
        [InlineKeyboardButton("🔴 Продать MKN", callback_data="p2p_sell_orders")],
        [InlineKeyboardButton("📋 Мои объявления", callback_data="p2p_my_orders")],
        [InlineKeyboardButton("➕ Создать объявление", callback_data="p2p_create")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def p2p_buy_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sell_orders = db.get_active_p2p_orders("sell")
    if not sell_orders:
        await query.edit_message_text("❌ Нет активных объявлений о продаже MKN", reply_markup=back_keyboard)
        return
    
    text = "🟢 *Доступные предложения (покупка MKN)*\n\n"
    for o in sell_orders:
        text += f"🆔 #{o['id']} | @{o['username']}\n"
        text += f"💰 {o['amount']} MKN | {o['price']} USDT/1000\n"
        text += f"💵 Итого: {o['amount'] * o['price'] / 1000:.4f} USDT\n"
        text += f"✅ `/buy_mkn {o['id']}` - купить\n\n"
    
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def p2p_sell_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buy_orders = db.get_active_p2p_orders("buy")
    if not buy_orders:
        await query.edit_message_text("❌ Нет активных объявлений о покупке MKN", reply_markup=back_keyboard)
        return
    
    text = "🔴 *Доступные предложения (продажа MKN)*\n\n"
    for o in buy_orders:
        text += f"🆔 #{o['id']} | @{o['username']}\n"
        text += f"💰 {o['amount']} MKN | {o['price']} USDT/1000\n"
        text += f"💵 Итого: {o['amount'] * o['price'] / 1000:.4f} USDT\n"
        text += f"✅ `/sell_mkn {o['id']}` - продать\n\n"
    
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def p2p_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    orders = db.get_user_p2p_orders(user_id)
    if not orders:
        await query.edit_message_text("📋 *Мои объявления*\n\nУ тебя нет активных объявлений.", reply_markup=back_keyboard, parse_mode="Markdown")
        return
    text = "📋 *Мои объявления*\n\n"
    for o in orders:
        text += f"🆔 #{o['id']} | {o['type'].upper()} | {o['amount']} MKN | {o['price']} USDT/1000\n"
        text += f"❌ `/cancel_p2p {o['id']}` - отменить\n\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def p2p_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "p2p_create"
    await query.edit_message_text(
        "🔄 *Создание P2P объявления*\n\n"
        "Введи тип (buy/sell), количество MKN и цену за 1000 MKN через пробел\n"
        "Пример: `sell 1000 0.95` (продажа 1000 MKN за 0.95 USDT за 1000)\n"
        "Пример: `buy 500 0.90` (покупка 500 MKN по 0.90 USDT за 1000)\n\n"
        f"💡 Текущий курс: 1000 MKN = {1000 * CONFIG.MKN_TO_USDT:.4f} USDT",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

# ============================================================================
# АЧИВКИ
# ============================================================================

async def achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    text = "🏅 *Ачивки CryptoKan 2.0*\n\n"
    for ach_key, ach_data in CONFIG.ACHIEVEMENTS.items():
        completed = db.check_achievement(user_id, ach_key)
        status = "✅" if completed else "❌"
        text += f"{status} *{ach_data['name']}*\n"
        text += f"   {ach_data['desc']} | +{ach_data['reward']} MKN\n\n"
    
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
    text = f"👥 *Реферальная программа*\n\nТвоя ссылка:\n`{ref_link}`\n\n📊 Приглашено: {count}\n💰 Заработано: {earnings:.2f} MKN\n🎁 Бонус: {CONFIG.REFERRAL_BONUS} MKN за друга"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    transactions = db.get_user_transactions(user_id, 15)
    if not transactions:
        await query.edit_message_text("📜 *История транзакций пуста*", reply_markup=back_keyboard, parse_mode="Markdown")
        return
    text = "📜 *Последние транзакции:*\n\n"
    emoji_map = {"deposit": "📥", "withdraw": "📤", "exchange": "💱", "lottery_ticket": "🎲", "lottery_win": "🎉", 
                 "referral_bonus": "👥", "transfer_send": "📤", "transfer_receive": "📥", "admin_add": "👑",
                 "daily_bonus": "🎁", "roulette": "🎡", "invest": "💼", "case_open": "📦", "gift": "🎁", "promo_code": "🔑",
                 "achievement": "🏅", "invest_return": "💰"}
    for tx in transactions:
        emoji = emoji_map.get(tx['type'], "📝")
        sign = "+" if tx['type'] in ['deposit', 'lottery_win', 'referral_bonus', 'transfer_receive', 'admin_add', 'daily_bonus', 'roulette', 'gift', 'promo_code', 'achievement', 'invest_return'] else "-"
        text += f"{emoji} {tx['type']}: {sign}{tx['amount']:.4f} {tx['currency']}\n"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "ℹ️ *CryptoKan 2.0 - Помощь*\n\n"
    text += "📥 *Пополнение:* Кошелек → Пополнить → введи сумму\n"
    text += f"📤 *Вывод:* Кошелек → Вывести → адрес и сумма (мин {CONFIG.MIN_WITHDRAW} USDT, комиссия 5%)\n"
    text += "🔄 *Перевод:* Кошелек → Перевести → @username сумма USDT\n"
    text += "💱 *Обмен:* Обменник → купить/продать MKN (комиссия 2%)\n"
    text += "🎲 *Лотерея:* Билет 100 MKN, шанс выигрыша 21% + кэшбэк 10%\n"
    text += "🎁 *Кейсы:* 3 типа кейсов с разными шансами\n"
    text += "🎡 *Рулетка:* Бесплатно раз в день\n"
    text += "💼 *Инвестиции:* Вкладывай USDT и получай проценты\n"
    text += "🔄 *P2P:* Покупай/продавай MKN у других (комиссия 2%)\n"
    text += "🏅 *Ачивки:* Получай награды за достижения\n"
    text += "👥 *Рефералы:* Приглашай друзей и получай 50 MKN за каждого!\n"
    text += "🔑 *Промокоды:* Вводи `/code КОД` для получения бонусов"
    await query.edit_message_text(text, reply_markup=back_keyboard, parse_mode="Markdown")

async def deposit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "deposit"
    await query.edit_message_text(
        "💰 *Пополнение CryptoKan 2.0*\n\n"
        "Введи сумму в USDT (мин 1):\n"
        "Пример: `10`\n\n"
        "💰 После ввода суммы администратор обработает заявку.",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def withdraw_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "withdraw"
    await query.edit_message_text(
        f"📤 *Вывод из CryptoKan 2.0*\n\n"
        f"Введи адрес кошелька USDT (TRC20) и сумму через пробел\n"
        f"Мин. сумма: {CONFIG.MIN_WITHDRAW} USDT\n"
        f"Комиссия: {CONFIG.WITHDRAW_FEE}% (вычитается из суммы)\n"
        f"Пример: `TVqP8Ur8f1DUUM3k4QxVxz1Qn1Gddq4VFT 10`\n\n"
        f"*Пример расчета:* при выводе 10 USDT ты получишь 9.5 USDT",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def transfer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    awaiting_state[query.from_user.id] = "transfer"
    await query.edit_message_text(
        "🔄 *Перевод в CryptoKan 2.0*\n\n"
        "Формат: `@username 10 USDT`\n"
        "Пример: `@ivan 5 USDT`\n\n"
        "Доступные валюты: USDT, TON, BTC, ETH, SOL, MKN",
        reply_markup=back_keyboard,
        parse_mode="Markdown"
    )

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Проверка...", reply_markup=back_keyboard)

# ============================================================================
# АДМИН-КОМАНДЫ
# ============================================================================

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
                    f"Средства возвращены на ваш баланс.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            await update.message.reply_text(f"✅ Заявка #{request_id} отклонена. Баланс пользователя восстановлен.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_deposit_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Нет доступа")
        return
    
    text = update.message.text.strip()
    if text.startswith("/deposit_confirm"):
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: /deposit_confirm USER_ID СУММА")
            return
        try:
            target_id = int(parts[1])
            amount = float(parts[2])
            
            user = db.get_user(target_id)
            is_first = user.get('first_deposit_bonus', 0) == 0 and user.get('total_deposited', 0) == 0
            
            db.update_balance(target_id, "USDT", amount, "add")
            db.add_transaction(target_id, "deposit", "USDT", amount, "completed")
            
            with db._get_connection() as conn:
                c = conn.cursor()
                c.execute("UPDATE users SET total_deposited = total_deposited + ? WHERE user_id = ?", (amount, target_id))
                if is_first:
                    c.execute("UPDATE users SET first_deposit_bonus = 1 WHERE user_id = ?", (target_id,))
                conn.commit()
            
            if is_first:
                bonus = 0
                for threshold, b in sorted(CONFIG.FIRST_DEPOSIT_BONUS.items()):
                    if amount >= threshold:
                        bonus = b
                if bonus > 0:
                    db.update_balance(target_id, "MKN", bonus, "add")
                    db.add_transaction(target_id, "deposit_bonus", "MKN", bonus, "completed", details="Бонус за первый депозит")
                    await context.bot.send_message(target_id, f"🎉 *Бонус за первый депозит!*\nТы получил {bonus} MKN!", parse_mode="Markdown")
            
            await context.bot.send_message(
                target_id,
                f"✅ *Ваше пополнение на {amount} USDT подтверждено!*\n\n"
                f"💰 Баланс USDT: {db.get_balance(target_id, 'USDT'):.4f}\n"
                f"💎 Баланс MKN: {db.get_balance(target_id, 'MKN'):.2f}",
                parse_mode="Markdown"
            )
            
            await update.message.reply_text(f"✅ Пополнение {amount} USDT пользователю {target_id} подтверждено!")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_buy_mkn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/buy_mkn "):
        try:
            order_id = int(text.replace("/buy_mkn ", ""))
            order = db.get_p2p_order(order_id)
            if not order or order['status'] != 'active' or order['type'] != 'sell':
                await update.message.reply_text("❌ Объявление не найдено или уже неактивно")
                return
            
            seller_id = order['user_id']
            if seller_id == user_id:
                await update.message.reply_text("❌ Нельзя купить у самого себя")
                return
            
            buyer = db.get_user(user_id)
            if not buyer:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            total_usdt = order['amount'] * order['price'] / 1000
            balance = db.get_balance(user_id, "USDT")
            if balance < total_usdt:
                await update.message.reply_text(f"❌ Недостаточно USDT. Нужно: {total_usdt:.4f} USDT")
                return
            
            # Резервируем средства (списываем USDT у покупателя)
            db.update_balance(user_id, "USDT", total_usdt, "subtract")
            
            # Создаем сделку
            deal_id = db.create_p2p_deal(order_id, user_id, update.effective_user.username or str(user_id), 
                                         order['amount'], order['price'], total_usdt)
            
            # Уведомляем продавца
            await context.bot.send_message(
                seller_id,
                f"🔄 *Новая P2P сделка!*\n\n"
                f"Покупатель: @{update.effective_user.username or user_id}\n"
                f"💰 Количество: {order['amount']} MKN\n"
                f"💵 Сумма: {total_usdt:.4f} USDT\n\n"
                f"✅ `/confirm_deal {deal_id}` - подтвердить получение USDT\n"
                f"❌ `/cancel_deal {deal_id}` - отменить сделку\n\n"
                f"⚠️ У вас есть {CONFIG.P2P_TIMEOUT_MINUTES} минут на подтверждение!",
                parse_mode="Markdown"
            )
            
            await update.message.reply_text(
                f"✅ *Заявка на покупку отправлена!*\n\n"
                f"💰 Количество: {order['amount']} MKN\n"
                f"💵 Сумма: {total_usdt:.4f} USDT\n"
                f"👤 Продавец: @{order['username']}\n\n"
                f"⏳ Ожидайте подтверждения от продавца. У него есть {CONFIG.P2P_TIMEOUT_MINUTES} минут.",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_sell_mkn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/sell_mkn "):
        try:
            order_id = int(text.replace("/sell_mkn ", ""))
            order = db.get_p2p_order(order_id)
            if not order or order['status'] != 'active' or order['type'] != 'buy':
                await update.message.reply_text("❌ Объявление не найдено или уже неактивно")
                return
            
            buyer_id = order['user_id']
            if buyer_id == user_id:
                await update.message.reply_text("❌ Нельзя продать самому себе")
                return
            
            seller = db.get_user(user_id)
            if not seller:
                await update.message.reply_text("❌ Пользователь не найден")
                return
            
            # Проверяем баланс MKN у продавца
            balance_mkn = db.get_balance(user_id, "MKN")
            if balance_mkn < order['amount']:
                await update.message.reply_text(f"❌ Недостаточно MKN. Нужно: {order['amount']} MKN")
                return
            
            total_usdt = order['amount'] * order['price'] / 1000
            
            # Резервируем MKN у продавца
            db.update_balance(user_id, "MKN", order['amount'], "subtract")
            
            # Создаем сделку
            deal_id = db.create_p2p_deal(order_id, user_id, update.effective_user.username or str(user_id), 
                                         order['amount'], order['price'], total_usdt)
            
            # Уведомляем покупателя
            await context.bot.send_message(
                buyer_id,
                f"🔄 *Новая P2P сделка!*\n\n"
                f"Продавец: @{update.effective_user.username or user_id}\n"
                f"💰 Количество: {order['amount']} MKN\n"
                f"💵 Сумма: {total_usdt:.4f} USDT\n\n"
                f"💰 Пожалуйста, отправьте USDT на кошелек продавца и нажмите подтверждение.\n\n"
                f"✅ `/confirm_payment {deal_id}` - подтвердить оплату\n"
                f"❌ `/cancel_deal {deal_id}` - отменить сделку\n\n"
                f"⚠️ У вас есть {CONFIG.P2P_TIMEOUT_MINUTES} минут на оплату!",
                parse_mode="Markdown"
            )
            
            await update.message.reply_text(
                f"✅ *Заявка на продажу отправлена!*\n\n"
                f"💰 Количество: {order['amount']} MKN\n"
                f"💵 Сумма: {total_usdt:.4f} USDT\n"
                f"👤 Покупатель: @{order['username']}\n\n"
                f"⏳ Ожидайте подтверждения оплаты от покупателя.",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_confirm_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/confirm_deal "):
        try:
            deal_id = int(text.replace("/confirm_deal ", ""))
            deal = db.get_pending_deal(deal_id)
            if not deal:
                await update.message.reply_text("❌ Сделка не найдена или уже завершена")
                return
            
            order = db.get_p2p_order(deal['order_id'])
            if not order:
                await update.message.reply_text("❌ Объявление не найдено")
                return
            
            if order['type'] == 'sell':
                # Продавец подтверждает получение USDT
                if deal['seller_id'] != user_id:
                    await update.message.reply_text("❌ Только продавец может подтвердить сделку")
                    return
                
                # Начисляем MKN покупателю (они уже зарезервированы у продавца)
                db.update_balance(deal['buyer_id'], "MKN", deal['amount'], "add")
                
                # Начисляем USDT продавцу с комиссией
                total_with_fee = deal['total'] * (1 - CONFIG.P2P_FEE / 100)
                db.update_balance(deal['seller_id'], "USDT", total_with_fee, "add")
                db.add_transaction(deal['seller_id'], "p2p_sale", "USDT", total_with_fee, "completed", 
                                  fee=deal['total'] * CONFIG.P2P_FEE / 100, details=f"Продажа {deal['amount']} MKN")
                db.add_transaction(deal['buyer_id'], "p2p_purchase", "MKN", deal['amount'], "completed", 
                                  details=f"Покупка {deal['amount']} MKN за {deal['total']:.4f} USDT")
                
                db.confirm_p2p_deal(deal_id)
                db.delete_p2p_order(order['id'])
                
                await context.bot.send_message(deal['buyer_id'], 
                    f"✅ *Сделка завершена!*\n\n"
                    f"💰 Вы купили {deal['amount']} MKN\n"
                    f"💵 Оплачено: {deal['total']:.4f} USDT\n"
                    f"💎 MKN зачислены на ваш баланс!",
                    parse_mode="Markdown")
                
                await update.message.reply_text(f"✅ Сделка #{deal_id} завершена! MKN переведены покупателю, USDT с комиссией зачислены вам.")
                
            else:  # type == 'buy'
                # Покупатель подтверждает оплату
                if deal['buyer_id'] != user_id:
                    await update.message.reply_text("❌ Только покупатель может подтвердить оплату")
                    return
                
                # Начисляем MKN покупателю
                db.update_balance(deal['buyer_id'], "MKN", deal['amount'], "add")
                
                # Начисляем USDT продавцу с комиссией
                total_with_fee = deal['total'] * (1 - CONFIG.P2P_FEE / 100)
                db.update_balance(deal['seller_id'], "USDT", total_with_fee, "add")
                db.add_transaction(deal['seller_id'], "p2p_sale", "USDT", total_with_fee, "completed",
                                  fee=deal['total'] * CONFIG.P2P_FEE / 100, details=f"Продажа {deal['amount']} MKN")
                db.add_transaction(deal['buyer_id'], "p2p_purchase", "MKN", deal['amount'], "completed",
                                  details=f"Покупка {deal['amount']} MKN за {deal['total']:.4f} USDT")
                
                db.confirm_p2p_deal(deal_id)
                db.delete_p2p_order(order['id'])
                
                await context.bot.send_message(deal['seller_id'],
                    f"✅ *Сделка завершена!*\n\n"
                    f"💰 Вы продали {deal['amount']} MKN\n"
                    f"💵 Получено: {total_with_fee:.4f} USDT (с учетом комиссии {CONFIG.P2P_FEE}%)\n"
                    f"💰 USDT зачислены на ваш баланс!",
                    parse_mode="Markdown")
                
                await update.message.reply_text(f"✅ Сделка #{deal_id} завершена! MKN переведены покупателю, USDT с комиссией зачислены продавцу.")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_cancel_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/cancel_deal "):
        try:
            deal_id = int(text.replace("/cancel_deal ", ""))
            deal = db.get_pending_deal(deal_id)
            if not deal:
                await update.message.reply_text("❌ Сделка не найдена или уже завершена")
                return
            
            order = db.get_p2p_order(deal['order_id'])
            
            # Возвращаем средства
            if order['type'] == 'sell':
                # Возвращаем USDT покупателю
                db.update_balance(deal['buyer_id'], "USDT", deal['total'], "add")
                # Возвращаем MKN продавцу
                db.update_balance(deal['seller_id'], "MKN", deal['amount'], "add")
            else:
                # Возвращаем MKN продавцу
                db.update_balance(deal['seller_id'], "MKN", deal['amount'], "add")
                # Возвращаем USDT покупателю
                db.update_balance(deal['buyer_id'], "USDT", deal['total'], "add")
            
            db.cancel_p2p_deal(deal_id)
            
            await context.bot.send_message(deal['buyer_id'], f"❌ *Сделка отменена*\n\nСредства возвращены на ваш баланс.", parse_mode="Markdown")
            await context.bot.send_message(deal['seller_id'], f"❌ *Сделка отменена*\n\nСредства возвращены на ваш баланс.", parse_mode="Markdown")
            await update.message.reply_text(f"✅ Сделка #{deal_id} отменена. Средства возвращены.")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

async def handle_cancel_p2p_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/cancel_p2p "):
        try:
            order_id = int(text.replace("/cancel_p2p ", ""))
            order = db.get_p2p_order(order_id)
            if not order or order['user_id'] != user_id:
                await update.message.reply_text("❌ Объявление не найдено или не принадлежит вам")
                return
            db.delete_p2p_order(order_id)
            await update.message.reply_text(f"✅ Объявление #{order_id} отменено.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

# ============================================================================
# ОБРАБОТЧИК ТЕКСТА
# ============================================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = awaiting_state.get(user_id)
    
    # Обновляем username
    user = db.get_user(user_id)
    username = update.effective_user.username or str(user_id)
    if user and user.get('username') != username:
        db.update_username(user_id, username)
    
    # ========== АДМИН-КОМАНДЫ ==========
    
    if state == "admin_add" and is_admin(user_id):
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: ID ВАЛЮТА СУММА")
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
    
    elif state == "admin_gift" and is_admin(user_id):
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Формат: ВАЛЮТА СУММА\nПример: `MKN 100`")
            return
        currency = parts[0].upper()
        try:
            amount = float(parts[1])
        except:
            await update.message.reply_text("❌ Неверная сумма")
            return
        if currency not in ["MKN", "USDT"]:
            await update.message.reply_text("❌ Доступны: MKN или USDT")
            return
        
        users = db.get_all_users()
        count = 0
        for u in users:
            db.update_balance(u['user_id'], currency, amount, "add")
            db.add_transaction(u['user_id'], "gift", currency, amount, "completed", details="Массовый подарок от администратора")
            count += 1
            try:
                await context.bot.send_message(u['user_id'], f"🎁 *Подарок от администратора!*\nТы получил {amount} {currency}", parse_mode="Markdown")
            except:
                pass
        await update.message.reply_text(f"✅ Подарок отправлен {count} пользователям!")
        awaiting_state.pop(user_id, None)
    
    elif state == "admin_promo" and is_admin(user_id):
        parts = text.split()
        if len(parts) != 4:
            await update.message.reply_text("❌ Формат: КОД ВАЛЮТА СУММА КОЛИЧЕСТВО\nПример: `HELLO MKN 100 50`")
            return
        code, currency, amount_str, uses_str = parts
        try:
            amount = float(amount_str)
            uses = int(uses_str)
        except:
            await update.message.reply_text("❌ Неверная сумма или количество")
            return
        if currency not in ["MKN", "USDT"]:
            await update.message.reply_text("❌ Доступны: MKN или USDT")
            return
        if db.create_promo_code(code, currency, amount, uses, user_id):
            await update.message.reply_text(f"✅ Промокод `{code.upper()}` создан!\n💰 Награда: {amount} {currency}\n📊 Доступен: {uses} раз", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Такой промокод уже существует")
        awaiting_state.pop(user_id, None)
    
    # ========== ПОПОЛНЕНИЕ ==========
    elif state == "deposit":
        try:
            amount = float(text)
            if amount < 1:
                await update.message.reply_text("❌ Минимум 1 USDT")
                return
            
            db.add_transaction(user_id, "deposit_request", "USDT", amount, "pending")
            
            await update.message.reply_text(
                f"💰 *Заявка на пополнение {amount} USDT создана!*\n\n"
                f"⏳ Ожидай подтверждения от администратора.\n"
                f"💰 После подтверждения средства поступят на баланс.\n\n"
                f"💡 *Для быстрого пополнения:* переведи USDT на кошелек и напиши админу.",
                parse_mode="Markdown"
            )
            
            await context.bot.send_message(
                CONFIG.ADMIN_ID,
                f"🔔 *ЗАЯВКА НА ПОПОЛНЕНИЕ*\n"
                f"👤 @{update.effective_user.username or user_id}\n"
                f"💰 Сумма: {amount} USDT\n"
                f"✅ `/deposit_confirm {user_id} {amount}` - подтвердить",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    # ========== ВЫВОД ==========
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
        
        if amount < CONFIG.MIN_WITHDRAW:
            await update.message.reply_text(f"❌ Минимальная сумма вывода: {CONFIG.MIN_WITHDRAW} USDT")
            return
        
        balance = db.get_balance(user_id, "USDT")
        fee = amount * CONFIG.WITHDRAW_FEE / 100
        if balance < amount:
            await update.message.reply_text(f"❌ Недостаточно. Нужно: {amount:.4f} USDT")
            return
        
        db.update_balance(user_id, "USDT", amount, "subtract")
        username = update.effective_user.username or str(user_id)
        request_id = db.add_withdraw_request(user_id, username, amount, address, CONFIG.WITHDRAW_FEE)
        db.add_transaction(user_id, "withdraw", "USDT", amount, "pending", fee=fee)
        
        await update.message.reply_text(
            f"✅ *Заявка на вывод создана!*\n\n"
            f"💰 Сумма: {amount} USDT\n"
            f"⚡️ Комиссия (5%): {fee:.4f} USDT\n"
            f"📤 Ты получишь: {amount - fee:.4f} USDT\n"
            f"⏳ Ожидай подтверждения.",
            parse_mode="Markdown"
        )
        
        await context.bot.send_message(
            CONFIG.ADMIN_ID,
            f"🔔 *ЗАЯВКА НА ВЫВОД #{request_id}*\n"
            f"👤 @{username}\n"
            f"💰 Сумма: {amount} USDT\n"
            f"📤 Получит: {amount - fee:.4f} USDT\n"
            f"📤 Адрес: `{address}`\n\n"
            f"✅ `/approve_{request_id}`\n"
            f"❌ `/reject_{request_id}`",
            parse_mode="Markdown"
        )
        awaiting_state.pop(user_id, None)
    
    # ========== ПЕРЕВОД ==========
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
    
    # ========== ОБМЕН MKN ==========
    elif state == "buy_mkn":
        try:
            mkn_amount = float(text)
            if mkn_amount < CONFIG.MIN_EXCHANGE:
                await update.message.reply_text(f"❌ Минимальная покупка: {CONFIG.MIN_EXCHANGE} MKN")
                return
            usd_needed = mkn_amount * CONFIG.MKN_TO_USDT
            balance = db.get_balance(user_id, "USDT")
            if balance < usd_needed:
                await update.message.reply_text(f"❌ Недостаточно USDT. Нужно: {usd_needed:.4f} USDT")
                return
            db.update_balance(user_id, "USDT", usd_needed, "subtract")
            db.update_balance(user_id, "MKN", mkn_amount, "add")
            db.add_transaction(user_id, "exchange", "MKN", mkn_amount, "completed", details=f"Покупка за {usd_needed:.4f} USDT")
            await update.message.reply_text(f"✅ *Покупка MKN!*\n\nОтдано: {usd_needed:.4f} USDT\nПолучено: {mkn_amount:.2f} MKN", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    elif state == "sell_mkn":
        try:
            mkn_amount = float(text)
            if mkn_amount < CONFIG.MIN_EXCHANGE:
                await update.message.reply_text(f"❌ Минимальная продажа: {CONFIG.MIN_EXCHANGE} MKN")
                return
            balance = db.get_balance(user_id, "MKN")
            if balance < mkn_amount:
                await update.message.reply_text(f"❌ Недостаточно MKN. Баланс: {balance:.2f}")
                return
            usd_received = mkn_amount * CONFIG.MKN_TO_USDT * (1 - CONFIG.EXCHANGE_FEE / 100)
            db.update_balance(user_id, "MKN", mkn_amount, "subtract")
            db.update_balance(user_id, "USDT", usd_received, "add")
            db.add_transaction(user_id, "exchange", "USDT", usd_received, "completed", 
                              fee=mkn_amount * CONFIG.MKN_TO_USDT * CONFIG.EXCHANGE_FEE / 100,
                              details=f"Продажа {mkn_amount} MKN")
            await update.message.reply_text(
                f"✅ *Продажа MKN!*\n\nОтдано: {mkn_amount} MKN\n"
                f"Получено: {usd_received:.4f} USDT\n"
                f"⚡️ Комиссия: {CONFIG.EXCHANGE_FEE}%",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    # ========== ИНВЕСТИЦИИ ==========
    elif state and state.startswith("invest_"):
        days_key = state.replace("invest_", "")
        pkg = CONFIG.INVEST_PACKAGES.get(days_key)
        if not pkg:
            await update.message.reply_text("❌ Неверный пакет")
            awaiting_state.pop(user_id, None)
            return
        try:
            amount = float(text)
            if amount < pkg['min'] or amount > pkg['max']:
                await update.message.reply_text(f"❌ Сумма должна быть от {pkg['min']} до {pkg['max']} USDT")
                return
            balance = db.get_balance(user_id, "USDT")
            if balance < amount:
                await update.message.reply_text(f"❌ Недостаточно USDT. Баланс: {balance:.2f} USDT")
                return
            db.update_balance(user_id, "USDT", amount, "subtract")
            db.add_investment(user_id, days_key, amount, pkg['days'], pkg['percent'])
            db.add_transaction(user_id, "invest", "USDT", amount, "completed", details=f"Пакет: {days_key}, {pkg['days']} дней, +{pkg['percent']}%")
            
            # Проверка ачивки инвестора
            user = db.get_user(user_id)
            total_invested = sum([inv['amount'] for inv in db.get_active_investments(user_id)]) + amount
            if total_invested >= 500:
                db.check_all_achievements(user_id, context)
            
            await update.message.reply_text(
                f"✅ *Инвестиция оформлена!*\n\n"
                f"📦 Пакет: {days_key}\n"
                f"💰 Сумма: {amount} USDT\n"
                f"📈 Доход: +{pkg['percent']}% через {pkg['days']} дней\n"
                f"💎 Ты получишь: {amount * (1 + pkg['percent']/100):.2f} USDT",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ Введи число")
        awaiting_state.pop(user_id, None)
    
    # ========== P2P СОЗДАНИЕ ОБЪЯВЛЕНИЯ ==========
    elif state == "p2p_create":
        parts = text.split()
        if len(parts) != 3:
            await update.message.reply_text("❌ Формат: ТИП КОЛИЧЕСТВО ЦЕНА\nПример: `sell 1000 0.95`")
            awaiting_state.pop(user_id, None)
            return
        order_type, amount_str, price_str = parts
        if order_type not in ['buy', 'sell']:
            await update.message.reply_text("❌ Тип должен быть buy или sell")
            awaiting_state.pop(user_id, None)
            return
        try:
            amount = float(amount_str)
            price = float(price_str)
            if amount <= 0 or price <= 0:
                raise ValueError
            if order_type == 'sell':
                balance = db.get_balance(user_id, "MKN")
                if balance < amount:
                    await update.message.reply_text(f"❌ Недостаточно MKN. Баланс: {balance:.2f} MKN")
                    return
            db.add_p2p_order(user_id, update.effective_user.username or str(user_id), order_type, amount, price)
            await update.message.reply_text(
                f"✅ *Объявление создано!*\n\n"
                f"🔄 Тип: {order_type} MKN\n"
                f"💰 Количество: {amount} MKN\n"
                f"💵 Цена: {price} USDT за 1000 MKN\n\n"
                f"Твое объявление появилось в P2P-маркете.",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text("❌ Неверный формат")
        awaiting_state.pop(user_id, None)
    
    # ========== ПРОМОКОД ==========
    elif text.startswith("/code "):
        code = text.replace("/code ", "").strip().upper()
        promo = db.use_promo_code(code, user_id)
        if not promo:
            await update.message.reply_text("❌ Неверный или уже использованный промокод")
            return
        if promo['reward_type'] == "MKN":
            db.update_balance(user_id, "MKN", promo['reward_amount'], "add")
        else:
            db.update_balance(user_id, "USDT", promo['reward_amount'], "add")
        db.add_transaction(user_id, "promo_code", promo['reward_type'], promo['reward_amount'], "completed", details=f"Промокод: {code}")
        await update.message.reply_text(f"✅ *Промокод активирован!*\nТы получил {promo['reward_amount']} {promo['reward_type']}", parse_mode="Markdown")

# ============================================================================
# ЗАПУСК
# ============================================================================

def main():
    app = Application.builder().token(CONFIG.BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve_", handle_approve_command, block=False))
    app.add_handler(CommandHandler("reject_", handle_reject_command, block=False))
    app.add_handler(CommandHandler("deposit_confirm", handle_deposit_confirm, block=False))
    app.add_handler(CommandHandler("buy_mkn", handle_buy_mkn_command, block=False))
    app.add_handler(CommandHandler("sell_mkn", handle_sell_mkn_command, block=False))
    app.add_handler(CommandHandler("confirm_deal", handle_confirm_deal, block=False))
    app.add_handler(CommandHandler("cancel_deal", handle_cancel_deal, block=False))
    app.add_handler(CommandHandler("cancel_p2p", handle_cancel_p2p_order, block=False))
    
    # Кнопки главного меню
    app.add_handler(CallbackQueryHandler(menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(show_user_wallet, pattern="^wallet_user$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_withdraws, pattern="^admin_withdraws$"))
    app.add_handler(CallbackQueryHandler(admin_add_balance, pattern="^admin_add_balance$"))
    app.add_handler(CallbackQueryHandler(admin_gift, pattern="^admin_gift$"))
    app.add_handler(CallbackQueryHandler(admin_create_promo, pattern="^admin_create_promo$"))
    
    # Обменник
    app.add_handler(CallbackQueryHandler(exchange_menu, pattern="^exchange_menu$"))
    app.add_handler(CallbackQueryHandler(buy_mkn, pattern="^buy_mkn$"))
    app.add_handler(CallbackQueryHandler(sell_mkn, pattern="^sell_mkn$"))
    
    # Кейсы
    app.add_handler(CallbackQueryHandler(cases_menu, pattern="^cases_menu$"))
    app.add_handler(CallbackQueryHandler(case_normal, pattern="^case_normal$"))
    app.add_handler(CallbackQueryHandler(case_gold, pattern="^case_gold$"))
    app.add_handler(CallbackQueryHandler(case_diamond, pattern="^case_diamond$"))
    
    # Лотерея и рекорды
    app.add_handler(CallbackQueryHandler(lottery, pattern="^lottery$"))
    app.add_handler(CallbackQueryHandler(records, pattern="^records$"))
    
    # Ежедневный бонус и рулетка
    app.add_handler(CallbackQueryHandler(daily, pattern="^daily$"))
    app.add_handler(CallbackQueryHandler(roulette, pattern="^roulette$"))
    
    # Инвестиции
    app.add_handler(CallbackQueryHandler(invest_menu, pattern="^invest_menu$"))
    app.add_handler(CallbackQueryHandler(invest_7, pattern="^invest_7$"))
    app.add_handler(CallbackQueryHandler(invest_14, pattern="^invest_14$"))
    app.add_handler(CallbackQueryHandler(invest_30, pattern="^invest_30$"))
    app.add_handler(CallbackQueryHandler(my_investments, pattern="^my_investments$"))
    
    # P2P
    app.add_handler(CallbackQueryHandler(p2p_menu, pattern="^p2p_menu$"))
    app.add_handler(CallbackQueryHandler(p2p_buy_orders, pattern="^p2p_buy_orders$"))
    app.add_handler(CallbackQueryHandler(p2p_sell_orders, pattern="^p2p_sell_orders$"))
    app.add_handler(CallbackQueryHandler(p2p_my_orders, pattern="^p2p_my_orders$"))
    app.add_handler(CallbackQueryHandler(p2p_create, pattern="^p2p_create$"))
    
    # Ачивки
    app.add_handler(CallbackQueryHandler(achievements, pattern="^achievements$"))
    
    # Остальное
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(help_command, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(deposit_handler, pattern="^deposit$"))
    app.add_handler(CallbackQueryHandler(withdraw_handler, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(transfer_handler, pattern="^transfer$"))
    app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_"))
    
    # Обработчик текста
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("🤖 CryptoKan 2.0 ФИНАЛ запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
