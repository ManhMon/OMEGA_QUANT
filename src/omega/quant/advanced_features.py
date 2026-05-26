"""
Advanced Technical Indicators cho V21_QUANT.
Bo sung RSI, MACD, Bollinger Bands, ATR, Money Flow...
"""
import math
from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class AdvancedFeatureConfig:
    # Cac thong so cho indicators
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    adx_period: int = 14
    # Toggle features
    enable_rsi: bool = True
    enable_macd: bool = True
    enable_bb: bool = True
    enable_atr: bool = True
    enable_adx: bool = True


def compute_rsi(closes: List[float], period: int = 14) -> List[float]:
    """Relative Strength Index."""
    if not closes or len(closes) < period + 1:
        return [float('nan')] * (len(closes) if closes else 0)
    
    # Guard: all NaN check
    if all(math.isnan(c) for c in closes):
        return [float('nan')] * len(closes)
    
    rsi = []
    gains = []
    losses = []
    
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0.0)
        losses.append(-diff if diff < 0 else 0.0)
    
    # EMA-based RSI
    alpha = 2.0 / (period + 1)
    
    if len(gains) < period:
        return [float('nan')] * len(closes)
        
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    rsi_out = [float('nan')] * period
    
    if avg_loss == 0:
        rsi_out.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_out.append(100.0 - (100.0 / (1.0 + rs)))
    
    for i in range(period, len(gains)):
        avg_gain = alpha * gains[i] + (1 - alpha) * avg_gain
        avg_loss = alpha * losses[i] + (1 - alpha) * avg_loss
        
        rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
        rsi_val = 100.0 - (100.0 / (1.0 + rs))
        rsi_out.append(rsi_val)
    
    return rsi_out

def compute_macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> List[float]:
    """MACD - Moving Average Convergence Divergence."""
    if not closes or len(closes) < slow:
        return [float('nan')] * (len(closes) if closes else 0)
    
    # Guard: if input series is empty or all NaN, return NaN series
    if not closes or all(math.isnan(c) for c in closes):
        return [float('nan')] * (len(closes) if closes else 0)
    # Simple EMA guard – ensure we have at least one valid numeric value
    # If the first value is NaN, replace it with the first non‑NaN value
    first_valid = next((c for c in closes if not math.isnan(c)), None)
    if first_valid is None:
        return [float('nan')] * len(closes)
    # Replace initial EMA seed with a safe numeric value
    ema_fast = first_valid
    ema_slow = first_valid
    ema_sig = first_valid
    
    alpha_fast = 2.0 / (fast + 1)
    alpha_slow = 2.0 / (slow + 1)
    alpha_sig = 2.0 / (signal + 1)
    
    macd_line = []
    
    for close in closes:
        ema_fast = alpha_fast * close + (1 - alpha_fast) * ema_fast
        ema_slow = alpha_slow * close + (1 - alpha_slow) * ema_slow
        macd_line.append(ema_fast - ema_slow)
    
    # Signal line (EMA of MACD line)
    signal_line = []
    for i in range(len(macd_line)):
        if i == 0:
            signal_line.append(macd_line[0])
        else:
            signal_line.append(alpha_sig * macd_line[i] + (1 - alpha_sig) * signal_line[-1])
    
    # Histogram. Values before the slow EMA has enough observations are warmup.
    histogram = [
        float('nan') if i < slow - 1 else m - s
        for i, (m, s) in enumerate(zip(macd_line, signal_line))
    ]
    
    return histogram

def compute_bollinger_bands(closes: List[float], period: int = 20, num_std: float = 2.0) -> tuple:
    """Bollinger Bands."""
    if len(closes) < period:
        return [float('nan')] * len(closes), [float('nan')] * len(closes), [float('nan')] * len(closes)
    
    sma = []
    upper = []
    lower = []
    
    for i in range(len(closes)):
        if i < period - 1:
            sma.append(float('nan'))
            upper.append(float('nan'))
            lower.append(float('nan'))
        else:
            window = closes[i - period + 1:i + 1]
            sma_val = sum(window) / period
            sma.append(sma_val)
            
            variance = sum((x - sma_val) ** 2 for x in window) / period
            std = variance ** 0.5
            
            upper.append(sma_val + num_std * std)
            lower.append(sma_val - num_std * std)
    
    return upper, sma, lower

def compute_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Average True Range."""
    if len(highs) != len(lows) or len(highs) != len(closes) or len(highs) < period + 1:
        return [float('nan')] * len(highs)
    
    tr = []
    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        tr.append(max(high_low, high_close, low_close))
    
    if len(tr) < period:
        return [float('nan')] * len(highs)
    
    atr = []
    # First ATR is simple average
    atr.append(sum(tr[:period]) / period)
    
    # Subsequent ATRs are smoothed
    alpha = 1.0 / period
    for i in range(period, len(tr)):
        atr.append(alpha * tr[i] + (1 - alpha) * atr[-1])
    
    return [float('nan')] * period + atr

def compute_money_flow(*args) -> List[float]:
    """Money Flow (price * volume) với momentum."""
    if len(args) == 2:
        closes, volumes = args
        highs = lows = closes
    elif len(args) == 4:
        highs, lows, closes, volumes = args
    else:
        raise TypeError("compute_money_flow expects (closes, volumes) or (highs, lows, closes, volumes)")

    if not (len(highs) == len(lows) == len(closes) == len(volumes)) or len(closes) < 2:
        return [float('nan')] * len(closes)
    
    mf = []
    for i in range(1, len(closes)):
        typical = (highs[i] + lows[i] + closes[i]) / 3.0
        mf.append(typical * volumes[i])
    
    return [float('nan')] + mf

def compute_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Average Directional Index."""
    if len(highs) != len(lows) or len(highs) != len(closes) or len(highs) < period + 1:
        return [float('nan')] * len(highs)
    
    tr = []
    plus_dm = []
    minus_dm = []
    
    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        tr.append(max(high_low, high_close, low_close))
        
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        
        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0.0)
        
        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0.0)
    
    out = [float('nan')] * len(highs)
    alpha = 1.0 / period
    prev_adx = None

    for end in range(period, len(highs)):
        start = end - period
        tr_sum = sum(tr[start:end])
        if tr_sum <= 0:
            dx = 0.0
        else:
            plus_di = 100.0 * sum(plus_dm[start:end]) / tr_sum
            minus_di = 100.0 * sum(minus_dm[start:end]) / tr_sum
            di_sum = plus_di + minus_di
            dx = 0.0 if di_sum == 0 else abs(plus_di - minus_di) / di_sum * 100.0

        prev_adx = dx if prev_adx is None else alpha * dx + (1 - alpha) * prev_adx
        out[end] = prev_adx

    return out
