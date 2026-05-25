import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd

# Fix import path for omega namespace packages
workspace_root = Path(__file__).parent.parent
sys.path.insert(0, str(workspace_root / "packages" / "execution" / "src"))
sys.path.insert(0, str(workspace_root / "packages" / "data" / "src"))

from omega.execution.execution_engine import ExecutionEngine, ExecutionEngineConfig
from omega.execution.order_router import OrderRouterConfig, TradingMode, LatencyConfig
from omega.data.registry import DatasetRegistry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PaperTradingDryRun")

def load_historical_data() -> pd.DataFrame:
    """Tải dữ liệu VNStock thật từ Parquet."""
    try:
        # Load directly
        df = pd.read_parquet(str(workspace_root / "data" / "market_data.parquet"))
        logger.info(f"Loaded {len(df)} rows from VNStock dataset.")
        return df
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        # Dữ liệu giả lập nếu không tìm thấy Parquet
        logger.info("Using mock market data for dry run...")
        dates = pd.date_range(end=pd.Timestamp.now(), periods=30)
        data = []
        for d in dates:
            for sym in ["HPG", "VNM", "FPT", "SSI", "MWG"]:
                data.append({"time": d, "ticker": sym, "close": 50000.0, "volume": 100000})
        return pd.DataFrame(data)

def run_dry_run():
    logger.info("=== BẮT ĐẦU: END-TO-END PAPER TRADING DRY RUN (30 NGÀY) ===")
    
    # Khởi tạo Execution Engine (Phase 16) với chế độ PAPER và bật phòng thủ Liquidation
    router_cfg = OrderRouterConfig(mode=TradingMode.PAPER, simulate_latency=True, latency_config=LatencyConfig(paper_base_ms=10.0))
    engine_cfg = ExecutionEngineConfig(
        mode=TradingMode.PAPER,
        router_config=router_cfg,
        liquidation_mode=True,  # Ưu tiên bán trước
        defense_gross_exposure_cap=5000000000.0  # Max 5 Tỷ VND
    )
    engine = ExecutionEngine(engine_cfg)
    
    df = load_historical_data()
    
    # Lọc lấy 30 ngày giao dịch gần nhất
    df['date'] = pd.to_datetime(df['date']).dt.date
    latest_dates = sorted(df['date'].unique())[-30:]
    
    current_portfolio = {} # Không truyền VND vào current portfolio để tránh bị coi là chứng khoán cần thanh lý
    
    for i, current_date in enumerate(latest_dates):
        logger.info(f"\n--- Ngày {i+1}/30: {current_date} ---")
        
        # Lấy giá đóng cửa của ngày hôm đó (Mô phỏng PIT an toàn)
        day_data = df[df['date'] == current_date]
        if day_data.empty:
            continue
            
        # Tạo Envelope giá thị trường hiện tại
        current_prices_dict = dict(zip(day_data['ticker'], day_data['close']))
        prices_envelope = {
            "data": current_prices_dict,
            "timestamp": time.time(),
            "provenance": "vnstock-historical-dryrun"
        }
        
        # Mô phỏng sinh tín hiệu (Target Portfolio) cho 5 mã cổ phiếu lớn (bỏ VND ra khỏi target equity)
        target_portfolio = {
            "HPG": {"quantity": 5000},
            "FPT": {"quantity": 2000},
            "VNM": {"quantity": 0 if i % 5 == 0 else 1000}, # Chốt lời định kỳ
            "SSI": {"quantity": 3000},
            "MWG": {"quantity": 4000}
        }
        
        current_portfolio = {
            "HPG": {"quantity": 0},
            "FPT": {"quantity": 0},
            "VNM": {"quantity": 1000},
            "SSI": {"quantity": 0},
            "MWG": {"quantity": 0}
        }
        
        # Nếu mock data thì lấy luôn giá mặc định
        for sym in ["HPG", "VNM", "FPT", "SSI", "MWG"]:
            if sym not in current_prices_dict:
                current_prices_dict[sym] = 50000.0
        
        logger.info(f"Target Portfolio generated: {target_portfolio}")
        
        # Thực thi workflow bằng Engine Phase 16
        try:
            summary = engine.execute_workflow(
                target_portfolio=target_portfolio,
                current_portfolio=current_portfolio,
                current_prices=prices_envelope,
                allow_odd_lot=False
            )
            
            if summary["success"]:
                logger.info(f"Execution Successful! Thống kê lệnh:")
                for order in summary["orders"]:
                    liq_tag = "[LIQUIDATION]" if order.get("is_liquidation") else ""
                    logger.info(f"  -> {order['symbol']}: {order['status']} - Broker ID: {order['broker_order_id']} {liq_tag}")
                
                # Cập nhật danh mục giả lập sau giao dịch
                for sym, target in target_portfolio.items():
                    current_portfolio[sym] = {"quantity": target["quantity"]}
                    
            else:
                logger.warning(f"Execution Failed/Halted: Chờ retry vào ngày hôm sau.")
                
        except Exception as e:
            logger.error(f"Lỗi Execution Engine: {e}")
            
        # In Metric
        metrics = engine.get_execution_metrics()
        logger.info(f"Metrics cuối ngày: Gross Liq Exposure = {metrics.get('gross_liquidation_exposure_notional', 0):,.0f} VND, " 
                    f"Orders Filled = {metrics.get('total_filled', 0)}")
        time.sleep(0.5)

    logger.info("\n=== HOÀN THÀNH PAPER TRADING DRY RUN ===")
    final_metrics = engine.get_execution_metrics()
    logger.info(f"Tổng kết 30 ngày: {final_metrics}")

if __name__ == "__main__":
    run_dry_run()