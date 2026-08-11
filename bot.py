"""
============================================================
SECURE BSC TRADING BOT v15 (RENDER WEB SERVICE READY)
SECURITY-FIRST EXECUTION ENGINE
============================================================

IMPORTANT:
1. Use a NEW wallet for this bot.
2. Never reuse a wallet whose private key may have leaked.
3. LIVE_TRADING defaults to OFF.
4. Telegram is notification-only.
5. No arbitrary transfer function exists.
6. No unlimited ERC20 approvals.
7. Every transaction passes a final firewall before signing.
============================================================
"""

import os
import sys
import time
import json
import sqlite3
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv
from web3 import Web3
from web3.exceptions import ContractLogicError

# ============================================================
# RENDER WEB SERVICE KEEP-ALIVE DUMMY SERVER
# ============================================================

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    class SimpleHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running successfully")
        def log_message(self, format, *args):
            return # إخفاء سجلات البورت الزائدة للحفاظ على نظافة السجلات
            
    try:
        server = HTTPServer(('0.0.0.0', port), SimpleHandler)
        server.serve_forever()
    except Exception as exc:
        print(f"Dummy server error: {exc}")

# تشغيل خادم الويب الوهمي في الخلفية ليناسب متطلبات Render المجانية
threading.Thread(target=run_dummy_server, daemon=True).start()

# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PRIVATE_KEY = os.getenv("BOT_PRIVATE_KEY")
WALLET_ADDRESS_RAW = os.getenv("BOT_WALLET_ADDRESS")

RPC_URL = os.getenv(
    "BNB_RPC_URL",
    "https://bsc-dataseed.binance.org/"
)

TOKEN_ADDRESS_RAW = os.getenv("TOKEN_ADDRESS")

LIVE_TRADING = os.getenv("LIVE_TRADING", "0") == "1"

# ============================================================
# ABSOLUTE SECURITY LIMITS
# ============================================================

CHAIN_ID = 56

MAX_TRADE_BNB = float(
    os.getenv("MAX_TRADE_BNB", "0.0015")
)

MAX_TRADE_USD = float(
    os.getenv("MAX_TRADE_USD", "5.0")
)

MIN_BNB_RESERVE = float(
    os.getenv("MIN_BNB_RESERVE", "0.003")
)

MAX_GAS_LIMIT = int(
    os.getenv("MAX_GAS_LIMIT", "350000")
)

MAX_GAS_PRICE_GWEI = float(
    os.getenv("MAX_GAS_PRICE_GWEI", "3.0")
)

MAX_SLIPPAGE_PCT = float(
    os.getenv("MAX_SLIPPAGE_PCT", "1.0")
)

TX_DEADLINE_SECONDS = 120
LOOP_SECONDS = 30

# ============================================================
# PANCAKESWAP V2 MAINNET BSC
# ============================================================

PANCAKESWAP_ROUTER = Web3.to_checksum_address(
    "0x10ED43C718714eb63d5aA57B78B54704E256024E"
)

WBNB = Web3.to_checksum_address(
    "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
)

USDT = Web3.to_checksum_address(
    "0x55d398326f99059fF775485246999027B3197955"
)

ALLOWED_CONTRACTS = {
    PANCAKESWAP_ROUTER,
}

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            "secure_bot_v15.log",
            encoding="utf-8"
        )
    ]
)

logger = logging.getLogger("SECURE-BOT-V15")

# ============================================================
# WEB3
# ============================================================

web3 = Web3(
    Web3.HTTPProvider(
        RPC_URL,
        request_kwargs={"timeout": 10}
    )
)

# ============================================================
# ABI
# ============================================================

ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokens",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETH",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"}
        ],
        "name": "getAmountsOut",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [
            {"name": "", "type": "bool"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [
            {"name": "", "type": "uint256"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"}
        ],
        "name": "balanceOf",
        "outputs": [
            {"name": "balance", "type": "uint256"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [
            {"name": "", "type": "uint8"}
        ],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [
            {"name": "", "type": "string"}
        ],
        "type": "function"
    }
]

router = web3.eth.contract(
    address=PANCAKESWAP_ROUTER,
    abi=ROUTER_ABI
)

# ============================================================
# DATABASE
# ============================================================

DB_FILE = "secure_bot_v15.db"

def db():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=15
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_hash TEXT,
            action TEXT,
            value_bnb REAL,
            gas_bnb REAL,
            status INTEGER,
            timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT,
            details TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

def security_event(event, details=""):
    logger.critical(
        "SECURITY EVENT | %s | %s",
        event,
        details
    )
    try:
        conn = db()
        conn.execute(
            """
            INSERT INTO security_events
            (event, details, timestamp)
            VALUES (?, ?, ?)
            """,
            (
                event,
                details,
                datetime.now(timezone.utc).isoformat()
            )
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def record_transaction(
    tx_hash,
    action,
    value_bnb,
    gas_bnb,
    status
):
    conn = db()
    conn.execute(
        """
        INSERT INTO transactions
        (tx_hash, action, value_bnb, gas_bnb, status, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            tx_hash,
            action,
            value_bnb,
            gas_bnb,
            status,
            datetime.now(timezone.utc).isoformat()
        )
    )
    conn.commit()
    conn.close()

# ============================================================
# CONFIGURATION VALIDATION
# ============================================================

def fail(message):
    security_event(
        "STARTUP FAILURE",
        message
    )
    raise RuntimeError(message)

if not WALLET_ADDRESS_RAW:
    fail("BOT_WALLET_ADDRESS is missing.")

if LIVE_TRADING and not PRIVATE_KEY:
    fail(
        "LIVE_TRADING=1 but BOT_PRIVATE_KEY is missing."
    )

if not TOKEN_ADDRESS_RAW:
    fail("TOKEN_ADDRESS is missing.")

try:
    WALLET = Web3.to_checksum_address(
        WALLET_ADDRESS_RAW
    )
    TOKEN = Web3.to_checksum_address(
        TOKEN_ADDRESS_RAW
    )
except Exception as exc:
    fail(
        f"Invalid wallet/token address: {exc}"
    )

# ============================================================
# RPC / CHAIN SECURITY
# ============================================================

def verify_chain():
    if not web3.is_connected():
        fail("RPC connection failed.")
    actual_chain = web3.eth.chain_id
    if actual_chain != CHAIN_ID:
        fail(
            f"Wrong chain. Expected {CHAIN_ID}, got {actual_chain}"
        )

def verify_private_key():
    if not LIVE_TRADING:
        return
    try:
        account = web3.eth.account.from_key(
            PRIVATE_KEY
        )
        derived = Web3.to_checksum_address(
            account.address
        )
        if derived != WALLET:
            fail(
                "PRIVATE KEY DOES NOT MATCH BOT_WALLET_ADDRESS."
            )
    except Exception as exc:
        fail(
            f"Private key validation failed: {exc}"
        )

# ============================================================
# TELEGRAM — NOTIFICATION ONLY
# ============================================================

def telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "disable_web_page_preview": True
            },
            timeout=8
        )
    except Exception as exc:
        logger.error(
            "Telegram error: %s",
            exc
        )

# ============================================================
# WALLET
# ============================================================

def bnb_balance():
    return float(
        web3.from_wei(
            web3.eth.get_balance(WALLET),
            "ether"
        )
    )

def token_contract(address):
    return web3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=ERC20_ABI
    )

def token_balance(address):
    return token_contract(
        address
    ).functions.balanceOf(
        WALLET
    ).call()

# ============================================================
# HARD LIMIT ENGINE
# ============================================================

class HardLimit:

    @staticmethod
    def check_buy(
        bnb_amount_wei,
        estimated_gas_bnb
    ):
        amount_bnb = float(
            web3.from_wei(
                bnb_amount_wei,
                "ether"
            )
        )

        if amount_bnb > MAX_TRADE_BNB:
            return False, (
                f"Trade BNB limit exceeded: "
                f"{amount_bnb} > {MAX_TRADE_BNB}"
            )

        if amount_bnb + estimated_gas_bnb + MIN_BNB_RESERVE > bnb_balance():
            return False, (
                "Wallet reserve protection triggered."
            )

        gas_price = web3.eth.gas_price
        max_gas_price = web3.to_wei(
            MAX_GAS_PRICE_GWEI,
            "gwei"
        )

        if gas_price > max_gas_price:
            return False, (
                f"Gas price too high: "
                f"{web3.from_wei(gas_price, 'gwei')} Gwei"
            )

        return True, "OK"

# ============================================================
# TRANSACTION FIREWALL
# ============================================================

class TransactionFirewall:

    @staticmethod
    def validate(
        tx,
        expected_action,
        expected_value_wei=0
    ):
        try:
            if Web3.to_checksum_address(
                tx["from"]
            ) != WALLET:
                return False, "Invalid transaction sender."

            if tx.get("chainId") != CHAIN_ID:
                return False, "Invalid chain ID."

            destination = Web3.to_checksum_address(
                tx["to"]
            )

            if destination not in ALLOWED_CONTRACTS:
                return False, (
                    f"Destination not whitelisted: "
                    f"{destination}"
                )

            value = int(
                tx.get("value", 0)
            )

            if value != expected_value_wei:
                return False, (
                    "Transaction value mismatch."
                )

            if value > web3.to_wei(
                MAX_TRADE_BNB,
                "ether"
            ):
                return False, (
                    "Absolute BNB limit exceeded."
                )

            gas = int(
                tx.get("gas", 0)
            )

            if gas <= 0 or gas > MAX_GAS_LIMIT:
                return False, (
                    f"Gas limit rejected: {gas}"
                )

            gas_price = int(
                tx.get(
                    "gasPrice",
                    web3.eth.gas_price
                )
            )

            if gas_price > web3.to_wei(
                MAX_GAS_PRICE_GWEI,
                "gwei"
            ):
                return False, (
                    "Gas price exceeds absolute limit."
                )

            pending_nonce = (
                web3.eth.get_transaction_count(
                    WALLET,
                    "pending"
                )
            )

            if int(tx["nonce"]) != pending_nonce:
                return False, (
                    "Nonce changed before signing."
                )

            data = tx.get("data", b"")
            if not data:
                return False, (
                    "Contract transaction without calldata."
                )

            try:
                decoded = router.decode_function_input(
                    data
                )
                function = decoded[0].fn_name
                args = decoded[1]
            except Exception as exc:
                return False, (
                    f"Unable to decode router calldata: {exc}"
                )

            if function != expected_action:
                return False, (
                    f"Unexpected function: {function}"
                )

            if function == "swapExactETHForTokens":
                path = args["path"]
                recipient = Web3.to_checksum_address(
                    args["to"]
                )
                if recipient != WALLET:
                    return False, (
                        "BUY recipient is not the bot wallet."
                    )
                if path[0] != WBNB:
                    return False, (
                        "BUY must start with WBNB."
                    )
                if Web3.to_checksum_address(
                    path[-1]
                ) != TOKEN:
                    return False, (
                        "BUY target token mismatch."
                    )

            elif function == "swapExactTokensForETH":
                path = args["path"]
                recipient = Web3.to_checksum_address(
                    args["to"]
                )
                if recipient != WALLET:
                    return False, (
                        "SELL recipient is not the bot wallet."
                    )
                if Web3.to_checksum_address(
                    path[0]
                ) != TOKEN:
                    return False, (
                        "SELL token mismatch."
                    )
                if Web3.to_checksum_address(
                    path[-1]
                ) != WBNB:
                    return False, (
                        "SELL must end with WBNB."
                    )

            return True, "TRANSACTION PASSED FIREWALL"

        except Exception as exc:
            return False, (
                f"Firewall exception: {exc}"
            )

# ============================================================
# EXECUTION ENGINE
# ============================================================

class SecureExecutor:

    def __init__(self):
        self.lock = threading.Lock()

    def sign_and_send(
        self,
        tx,
        action,
        expected_value_wei=0
    ):
        if not LIVE_TRADING:
            logger.info(
                "DRY RUN — transaction NOT signed."
            )
            return "DRY_RUN"

        valid, reason = (
            TransactionFirewall.validate(
                tx,
                action,
                expected_value_wei
            )
        )

        if not valid:
            security_event(
                "TRANSACTION BLOCKED",
                reason
            )
            telegram(
                f"SECURITY BLOCK\n{reason}"
            )
            return None

        try:
            web3.eth.call(
                tx,
                "latest"
            )
        except Exception as exc:
            security_event(
                "SIMULATION FAILED",
                str(exc)
            )
            telegram(
                "SECURITY BLOCK: transaction simulation failed."
            )
            return None

        try:
            signed = web3.eth.account.sign_transaction(
                tx,
                private_key=PRIVATE_KEY
            )
        except Exception as exc:
            security_event(
                "SIGNING FAILED",
                str(exc)
            )
            return None

        try:
            raw = getattr(
                signed,
                "raw_transaction",
                None
            )
            if raw is None:
                raw = signed.rawTransaction

            tx_hash = (
                web3.eth.send_raw_transaction(raw)
            )
            tx_hex = web3.to_hex(tx_hash)

            logger.info(
                "%s submitted: %s",
                action,
                tx_hex
            )
            telegram(
                f"{action} submitted\n{tx_hex}"
            )
            return tx_hash
        except Exception as exc:
            security_event(
                "BROADCAST FAILED",
                str(exc)
            )
            return None

    def buy(
        self,
        bnb_amount_wei
    ):
        with self.lock:
            verify_chain()
            if bnb_amount_wei <= 0:
                return None

            if bnb_amount_wei > web3.to_wei(
                MAX_TRADE_BNB,
                "ether"
            ):
                security_event(
                    "BUY BLOCKED",
                    "BNB hard cap exceeded"
                )
                return None

            try:
                amounts = (
                    router.functions
                    .getAmountsOut(
                        bnb_amount_wei,
                        [WBNB, TOKEN]
                    )
                    .call()
                )
            except Exception as exc:
                logger.error(
                    "BUY quote failed: %s",
                    exc
                )
                return None

            if not amounts or amounts[-1] <= 0:
                return None

            expected_tokens = amounts[-1]
            amount_out_min = int(
                expected_tokens *
                (1 - MAX_SLIPPAGE_PCT / 100)
            )

            gas_price = web3.eth.gas_price
            if gas_price > web3.to_wei(
                MAX_GAS_PRICE_GWEI,
                "gwei"
            ):
                security_event(
                    "BUY BLOCKED",
                    "Gas price too high"
                )
                return None

            nonce = web3.eth.get_transaction_count(
                WALLET,
                "pending"
            )
            deadline = (
                int(time.time()) +
                TX_DEADLINE_SECONDS
            )

            function = (
                router.functions
                .swapExactETHForTokens(
                    amount_out_min,
                    [WBNB, TOKEN],
                    WALLET,
                    deadline
                )
            )

            base_tx = {
                "from": WALLET,
                "value": bnb_amount_wei,
                "nonce": nonce,
                "chainId": CHAIN_ID,
                "gasPrice": gas_price
            }

            try:
                estimated = (
                    function.estimate_gas(
                        base_tx
                    )
                )
            except Exception as exc:
                logger.error(
                    "BUY gas estimation failed: %s",
                    exc
                )
                return None

            gas_limit = min(
                int(estimated * 1.15),
                MAX_GAS_LIMIT
            )
            base_tx["gas"] = gas_limit

            estimated_gas_bnb = float(
                web3.from_wei(
                    gas_limit * gas_price,
                    "ether"
                )
            )

            allowed, reason = (
                HardLimit.check_buy(
                    bnb_amount_wei,
                    estimated_gas_bnb
                )
            )

            if not allowed:
                security_event(
                    "BUY BLOCKED",
                    reason
                )
                telegram(
                    f"BUY BLOCKED\n{reason}"
                )
                return None

            tx = function.build_transaction(
                base_tx
            )

            tx_hash = self.sign_and_send(
                tx,
                "swapExactETHForTokens",
                bnb_amount_wei
            )

            if not tx_hash or tx_hash == "DRY_RUN":
                return tx_hash

            try:
                receipt = (
                    web3.eth
                    .wait_for_transaction_receipt(
                        tx_hash,
                        timeout=180
                    )
                )
            except Exception as exc:
                security_event(
                    "BUY RECEIPT TIMEOUT",
                    str(exc)
                )
                return None

            status = int(receipt.status)
            gas_used = int(receipt.gasUsed)
            gas_bnb = float(
                web3.from_wei(
                    gas_used * gas_price,
                    "ether"
                )
            )

            record_transaction(
                web3.to_hex(tx_hash),
                "BUY",
                float(
                    web3.from_wei(
                        bnb_amount_wei,
                        "ether"
                    )
                ),
                gas_bnb,
                status
            )

            if status != 1:
                security_event(
                    "BUY REVERTED",
                    web3.to_hex(tx_hash)
                )
                return None

            telegram(
                f"BUY CONFIRMED\n"
                f"{web3.to_hex(tx_hash)}"
            )
            return tx_hash

    def sell(
        self,
        token_amount
    ):
        with self.lock:
            verify_chain()
            if token_amount <= 0:
                return None

            token = token_contract(TOKEN)
            actual_balance = (
                token.functions
                .balanceOf(WALLET)
                .call()
            )

            if actual_balance <= 0:
                return None

            sell_amount = min(
                token_amount,
                actual_balance
            )

            try:
                amounts = (
                    router.functions
                    .getAmountsOut(
                        sell_amount,
                        [TOKEN, WBNB]
                    )
                    .call()
                )
            except Exception as exc:
                logger.error(
                    "SELL quote failed: %s",
                    exc
                )
                return None

            if not amounts:
                return None

            expected_bnb = amounts[-1]
            amount_out_min = int(
                expected_bnb *
                (1 - MAX_SLIPPAGE_PCT / 100)
            )

            allowance = (
                token.functions
                .allowance(
                    WALLET,
                    PANCAKESWAP_ROUTER
                )
                .call()
            )

            if allowance < sell_amount:
                approval_hash = (
                    self.approve_exact(
                        token,
                        sell_amount
                    )
                )
                if not approval_hash:
                    return None
                if approval_hash != "DRY_RUN":
                    receipt = (
                        web3.eth
                        .wait_for_transaction_receipt(
                            approval_hash,
                            timeout=180
                        )
                    )
                    if receipt.status != 1:
                        security_event(
                            "APPROVAL FAILED"
                        )
                        return None

            gas_price = web3.eth.gas_price
            if gas_price > web3.to_wei(
                MAX_GAS_PRICE_GWEI,
                "gwei"
            ):
                security_event(
                    "SELL BLOCKED",
                    "Gas price too high"
                )
                return None

            nonce = web3.eth.get_transaction_count(
                WALLET,
                "pending"
            )
            deadline = (
                int(time.time()) +
                TX_DEADLINE_SECONDS
            )

            function = (
                router.functions
                .swapExactTokensForETH(
                    sell_amount,
                    amount_out_min,
                    [TOKEN, WBNB],
                    WALLET,
                    deadline
                )
            )

            params = {
                "from": WALLET,
                "nonce": nonce,
                "chainId": CHAIN_ID,
                "gasPrice": gas_price
            }

            try:
                estimated = (
                    function.estimate_gas(
                        params
                    )
                )
            except Exception as exc:
                logger.error(
                    "SELL gas estimation failed: %s",
                    exc
                )
                return None

            params["gas"] = min(
                int(estimated * 1.15),
                MAX_GAS_LIMIT
            )

            tx = function.build_transaction(
                params
            )

            tx_hash = self.sign_and_send(
                tx,
                "swapExactTokensForETH",
                0
            )

            if not tx_hash or tx_hash == "DRY_RUN":
                return tx_hash

            receipt = (
                web3.eth
                .wait_for_transaction_receipt(
                    tx_hash,
                    timeout=180
                )
            )

            status = int(receipt.status)
            gas_used = int(receipt.gasUsed)
            gas_bnb = float(
                web3.from_wei(
                    gas_used * gas_price,
                    "ether"
                )
            )

            record_transaction(
                web3.to_hex(tx_hash),
                "SELL",
                0,
                gas_bnb,
                status
            )

            if status != 1:
                security_event(
                    "SELL REVERTED",
                    web3.to_hex(tx_hash)
                )
                return None

            reset_hash = (
                self.reset_allowance(token)
            )

            if not reset_hash:
                security_event(
                    "CRITICAL: ALLOWANCE RESET FAILED",
                    "Bot must halt."
                )
                telegram(
                    "CRITICAL SECURITY ALERT\n"
                    "Allowance reset failed.\n"
                    "BOT HALTED."
                )
                raise RuntimeError(
                    "Allowance reset failed."
                )

            telegram(
                f"SELL CONFIRMED\n"
                f"{web3.to_hex(tx_hash)}"
            )
            return tx_hash

    def approve_exact(
        self,
        token,
        amount
    ):
        nonce = web3.eth.get_transaction_count(
            WALLET,
            "pending"
        )
        gas_price = web3.eth.gas_price
        if gas_price > web3.to_wei(
            MAX_GAS_PRICE_GWEI,
            "gwei"
        ):
            return None

        function = token.functions.approve(
            PANCAKESWAP_ROUTER,
            amount
        )

        params = {
            "from": WALLET,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "gasPrice": gas_price,
            "gas": 70000
        }

        tx = function.build_transaction(params)

        if Web3.to_checksum_address(
            tx["to"]
        ) != Web3.to_checksum_address(TOKEN):
            security_event(
                "APPROVAL TOKEN MISMATCH"
            )
            return None

        if int(tx.get("value", 0)) != 0:
            security_event(
                "APPROVAL VALUE NOT ZERO"
            )
            return None

        try:
            decoded = token.decode_function_input(
                tx["data"]
            )
            function_name = decoded[0].fn_name
            args = decoded[1]
            spender = Web3.to_checksum_address(
                args["_spender"]
            )
            approved_amount = int(args["_value"])

            if function_name != "approve":
                return None
            if spender != PANCAKESWAP_ROUTER:
                security_event(
                    "APPROVAL SPENDER BLOCKED",
                    spender
                )
                return None
            if approved_amount != amount:
                security_event(
                    "APPROVAL AMOUNT MISMATCH"
                )
                return None
        except Exception as exc:
            security_event(
                "APPROVAL DECODE FAILED",
                str(exc)
            )
            return None

        return self.sign_and_send(
            tx,
            "approve",
            0
        )

    def reset_allowance(
        self,
        token
    ):
        nonce = web3.eth.get_transaction_count(
            WALLET,
            "pending"
        )
        gas_price = web3.eth.gas_price

        function = token.functions.approve(
            PANCAKESWAP_ROUTER,
            0
        )

        params = {
            "from": WALLET,
            "nonce": nonce,
            "chainId": CHAIN_ID,
            "gasPrice": gas_price,
            "gas": 70000
        }

        tx = function.build_transaction(params)

        try:
            decoded = token.decode_function_input(
                tx["data"]
            )
            args = decoded[1]
            spender = Web3.to_checksum_address(
                args["_spender"]
            )
            amount = int(args["_value"])

            if spender != PANCAKESWAP_ROUTER:
                return None
            if amount != 0:
                return None
        except Exception:
            return None

        tx_hash = self.sign_and_send(
            tx,
            "approve",
            0
        )

        if not tx_hash:
            return None

        if tx_hash == "DRY_RUN":
            return tx_hash

        receipt = (
            web3.eth
            .wait_for_transaction_receipt(
                tx_hash,
                timeout=180
            )
        )

        if receipt.status != 1:
            return None

        verified = (
            token.functions
            .allowance(
                WALLET,
                PANCAKESWAP_ROUTER
            )
            .call()
        )

        if verified != 0:
            security_event(
                "ALLOWANCE RESET VERIFICATION FAILED"
            )
            return None

        logger.info(
            "Allowance verified at ZERO."
        )
        return tx_hash

# ============================================================
# WALLET INTEGRITY MONITOR
# ============================================================

class WalletMonitor:

    def __init__(self):
        self.last_nonce = (
            web3.eth.get_transaction_count(
                WALLET,
                "latest"
            )
        )

    def check(self):
        try:
            current_nonce = (
                web3.eth.get_transaction_count(
                    WALLET,
                    "latest"
                )
            )
            if current_nonce < self.last_nonce:
                security_event(
                    "NONCE ANOMALY",
                    f"{current_nonce} < {self.last_nonce}"
                )
                return False
            self.last_nonce = current_nonce
            return True
        except Exception as exc:
            security_event(
                "WALLET MONITOR FAILURE",
                str(exc)
            )
            return False

# ============================================================
# MARKET DATA
# ============================================================

def get_market_data():
    url = (
        "https://api.dexscreener.com/latest/dex/tokens/"
        + TOKEN_ADDRESS_RAW
    )
    try:
        response = requests.get(
            url,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        pairs = data.get("pairs", [])
        valid = []

        for pair in pairs:
            if pair.get("chainId") != "bsc":
                continue
            if (
                str(pair.get("dexId", ""))
                .lower()
                != "pancakeswap"
            ):
                continue

            price = float(
                pair.get("priceUsd") or 0
            )
            liquidity = float(
                (pair.get("liquidity") or {})
                .get("usd") or 0
            )

            if price <= 0:
                continue
            if liquidity < 15000:
                continue

            valid.append({
                "price": price,
                "liquidity": liquidity,
                "url": pair.get("url")
            })

        if not valid:
            return None

        return max(
            valid,
            key=lambda x: x["liquidity"]
        )
    except Exception as exc:
        logger.error(
            "Market data error: %s",
            exc
        )
        return None

# ============================================================
# MAIN
# ============================================================

def main():
    init_db()
    verify_chain()
    verify_private_key()

    logger.info(
        "================================================"
    )
    logger.info(
        "SECURE BSC BOT v15 STARTED"
    )
    logger.info(
        "Wallet: %s",
        WALLET
    )
    logger.info(
        "Token: %s",
        TOKEN
    )
    logger.info(
        "Mode: %s",
        "LIVE" if LIVE_TRADING else "DRY-RUN"
    )
    logger.info(
        "MAX TRADE: %s BNB",
        MAX_TRADE_BNB
    )
    logger.info(
        "MIN RESERVE: %s BNB",
        MIN_BNB_RESERVE
    )
    logger.info(
        "MAX GAS PRICE: %s Gwei",
        MAX_GAS_PRICE_GWEI
    )
    logger.info(
        "================================================"
    )

    telegram(
        "SECURE BOT v15 STARTED\n"
        f"Mode: {'LIVE' if LIVE_TRADING else 'DRY-RUN'}\n"
        f"Wallet: {WALLET}"
    )

    monitor = WalletMonitor()

    while True:
        try:
            verify_chain()

            if not monitor.check():
                telegram(
                    "CRITICAL SECURITY ALERT\n"
                    "Wallet integrity check failed.\n"
                    "BOT HALTED."
                )
                raise RuntimeError(
                    "Wallet integrity failure."
                )

            balance = bnb_balance()
            logger.info(
                "BNB balance: %.8f",
                balance
            )

            if balance < MIN_BNB_RESERVE:
                logger.warning(
                    "BNB reserve threshold reached."
                )
                time.sleep(LOOP_SECONDS)
                continue

            market = get_market_data()
            if market:
                logger.info(
                    "Market | price=%s | liquidity=%s",
                    market["price"],
                    market["liquidity"]
                )

            time.sleep(LOOP_SECONDS)

        except KeyboardInterrupt:
            logger.info(
                "Bot stopped manually."
            )
            break
        except Exception as exc:
            logger.exception(
                "MAIN LOOP FAILURE"
            )
            telegram(
                "CRITICAL BOT ERROR\n"
                "Bot halted.\n"
                f"{exc}"
            )
            break

# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    main()
