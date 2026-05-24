from __future__ import annotations

import logging
import os
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class TelegramAlertBot:
    """
    Telegram Notification Bot for OMEGA_QUANT.
    Sends trade executions, liquidation alerts, and system health warnings.
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.environ.get("OMEGA_TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("OMEGA_TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            logger.warning("TelegramAlertBot disabled: Missing OMEGA_TELEGRAM_BOT_TOKEN or OMEGA_TELEGRAM_CHAT_ID")

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a text message to the configured chat."""
        if not self.enabled:
            return False
            
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            response = requests.post(url, json=payload, timeout=5.0)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False

    def send_trade_alert(self, symbol: str, side: str, qty: int, price: float, mode: str = "PAPER") -> bool:
        """Format and send a trade execution alert."""
        icon = "🟢" if side.upper() == "BUY" else "🔴"
        notional = (qty * price) / 1_000_000  # Convert to Millions VND
        
        text = (
            f"{icon} *OMEGA EXECUTION* [{mode}]\n"
            f"**{symbol}** | {side.upper()}\n"
            f"Volume: `{qty:,}`\n"
            f"Price: `{price:,.0f}` VND\n"
            f"Value: `{notional:,.1f}` M VND"
        )
        return self.send_message(text)
        
    def send_liquidation_alert(self, symbol: str, qty: int, urgency: str = "HIGH") -> bool:
        """Format and send an urgent liquidation alert."""
        text = (
            f"🚨 *LIQUIDATION DEFENSE TRIGGERED*\n"
            f"**{symbol}**\n"
            f"Volume Dumped: `{qty:,}`\n"
            f"Urgency: `{urgency}`\n"
            f"Priority: SELL-FIRST"
        )
        return self.send_message(text)