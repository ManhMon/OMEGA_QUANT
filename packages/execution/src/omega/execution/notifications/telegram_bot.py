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

    def send_daily_signal_batch(self, date: str, target_portfolio: Dict[str, Dict[str, Any]], current_prices: Dict[str, float]) -> bool:
        """Format and send a batched daily signal oracle message."""
        if not target_portfolio:
            return self.send_message(f"🧠 *OMEGA ORACLE* [{date}]\n\nNo trading signals today. Portfolio unchanged.")
            
        lines = [f"🧠 *OMEGA ORACLE* [{date}]", ""]
        lines.append("`[MÃ]    [LỆNH]    [KHỐI LƯỢNG]    [TẠM TÍNH (M)]`")
        lines.append("--------------------------------------------------")
        
        total_value = 0.0
        for sym, data in target_portfolio.items():
            qty = data.get("quantity", 0)
            if qty == 0:
                continue
            side = "MUA" if qty > 0 else "BÁN"
            abs_qty = abs(qty)
            price = current_prices.get(sym, 0.0)
            notional = (abs_qty * price * 1000.0) / 1_000_000
            total_value += notional if side == "MUA" else -notional
            
            # Format row fixed width
            lines.append(f"`{sym:<7} {side:<9} {abs_qty:<14,} {notional:,.1f}`")
            
        lines.append("--------------------------------------------------")
        action_word = "MUA" if total_value >= 0 else "BÁN RÒNG"
        lines.append(f"**Tổng Net:** {action_word} `{abs(total_value):,.1f}` Triệu VND")
        
        return self.send_message("\n".join(lines))

    def send_trade_alert(self, symbol: str, side: str, qty: int, price: float, mode: str = "PAPER") -> bool:
        """Format and send a trade execution alert."""
        icon = "🟢" if side.upper() == "BUY" else "🔴"
        notional = (qty * price * 1000.0) / 1_000_000  # Convert to Millions VND (price_scale=1000.0)
        price_vnd = price * 1000.0  # Raw price unit -> VND

        text = (
            f"{icon} *OMEGA EXECUTION* [{mode}]\n"
            f"**{symbol}** | {side.upper()}\n"
            f"Volume: `{qty:,}`\n"
            f"Price: `{price_vnd:,.0f}` VND\n"
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