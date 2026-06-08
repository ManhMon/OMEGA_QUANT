"""
Backtest Runner Page
Chạy backtest với các tùy chọn cấu hình
"""
import streamlit as st
import sys
from pathlib import Path
import time
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.backtest_executor import BacktestExecutor, BacktestConfig
from config.dashboard_config import PAGE_TITLE, PAGE_ICON, DATA_DIR

st.set_page_config(
    page_title=f"{PAGE_TITLE} - Backtest Runner",
    page_icon=PAGE_ICON,
    layout="wide"
)

st.markdown("# 🧪 Backtest Runner")
st.markdown("Chạy backtest với các tùy chọn cấu hình và xem kết quả real-time")

# Sidebar configuration
with st.sidebar:
    st.markdown("## ⚙️ Cấu hình Backtest")
    
    # Backtest mode
    mode = st.radio(
        "Chế độ chạy",
        ["Quick Test (1 ticker)", "Full Backtest"],
        help="Quick Test: chạy nhanh với 1 ticker để kiểm tra. Full Backtest: chạy đầy đủ với tất cả tickers"
    )
    
    st.markdown("---")
    
    # Date range
    st.markdown("### 📅 Thời gian")
    from datetime import datetime
    
    default_start = datetime(2015, 1, 5)
    default_end = datetime(2026, 5, 14)
    
    start_date = st.date_input("Ngày bắt đầu", value=default_start)
    end_date = st.date_input("Ngày kết thúc", value=default_end)
    
    st.markdown("---")
    
    # Capital
    initial_capital = st.number_input(
        "Vốn ban đầu (VND)",
        min_value=10_000_000,
        max_value=100_000_000_000,
        value=1_000_000_000,
        step=100_000_000,
        format="%d"
    )
    
    st.markdown("---")
    
    # Strategy
    strategy = st.selectbox(
        "Chiến lược",
        ["multi_factor", "momentum", "mean_reversion"],
        help="Chọn chiến lược giao dịch"
    )
    
    # Advanced options
    with st.expander("🔧 Tùy chọn nâng cao"):
        slippage_bps = st.slider(
            "Slippage (bps)",
            min_value=0,
            max_value=100,
            value=10,
            help="Slippage tính bằng basis points (1 bp = 0.01%)"
        )
        
        commission_bps = st.slider(
            "Commission (bps)",
            min_value=0,
            max_value=100,
            value=20,
            help="Phí giao dịch tính bằng basis points"
        )
        
        use_xgboost = st.checkbox(
            "Sử dụng XGBoost",
            value=True,
            help="Bật/tắt XGBoost signal path"
        )

        st.markdown("---")
        drawdown_control = st.checkbox(
            "Kích hoạt Drawdown Control",
            value=False,
            help="Tự động cắt vị thế về cash khi chạm mức sụt giảm tối đa"
        )
        drawdown_threshold = st.slider(
            "Ngưỡng Drawdown (%)",
            min_value=1.0,
            max_value=50.0,
            value=5.0,
            step=0.5,
            help="Tỷ lệ sụt giảm tối đa từ đỉnh tài khoản trước khi chuyển về cash"
        ) / 100.0
    
    st.markdown("---")
    
    run_button = st.button("🚀 Chạy Backtest", type="primary", use_container_width=True)

# Main content
if run_button:
    # Validate inputs
    if start_date >= end_date:
        st.error("❌ Ngày bắt đầu phải trước ngày kết thúc")
        st.stop()
    
    if (end_date - start_date).days > 365 * 10:
        st.error("❌ Khoảng thời gian không được vượt quá 10 năm")
        st.stop()
    
    # Create config
    from config.dashboard_config import BACKTEST_SCRIPT
    config = BacktestConfig(
        script_path=str(BACKTEST_SCRIPT),
        start_date=str(start_date),
        end_date=str(end_date),
        initial_capital=float(initial_capital),
        strategy=strategy,
        slippage_bps=float(slippage_bps),
        commission_bps=float(commission_bps),
        quick_mode=(mode == "Quick Test (1 ticker)"),
        use_xgboost=use_xgboost,
        drawdown_control=drawdown_control,
        drawdown_threshold=drawdown_threshold
    )
    
    # Initialize executor
    executor = BacktestExecutor()
    
    # Check if already running
    if executor.is_locked():
        lock_info = executor.get_lock_info()
        st.warning(f"⚠️ Backtest đang chạy. PID: {lock_info.get('pid', 'N/A')}")
        st.stop()
    
    # Run backtest (non-blocking pattern)
    st.markdown("## 🏃 Đang chạy Backtest...")
    
    # Terminal-style log display
    log_container = st.empty()
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Start subprocess
    start_time = time.time()
    start_result = executor.start(config)
    
    if not start_result["started"]:
        st.error(f"❌ Không thể khởi động backtest: {start_result.get('error', 'Unknown error')}")
        st.stop()
    
    # Poll for output (non-blocking)
    log_lines = []
    MAX_DISPLAY_LINES = 50
    poll_interval = 0.1  # 100ms
    
    while not executor.is_complete():
        # Poll for new output
        new_lines = executor.poll_output(max_messages=100)
        
        if new_lines:
            log_lines.extend(new_lines)
            
            # Update terminal display
            display_lines = log_lines[-MAX_DISPLAY_LINES:]
            log_container.code("\n".join(display_lines), language="log")
            
            # Update status
            elapsed = time.time() - start_time
            status_text.text(f"📋 {len(log_lines)} dòng log | ⏱️ {elapsed:.1f}s")
            
            # Parse progress from last line
            last_line = new_lines[-1]
            
            # Match "Step X of Y" pattern
            if "Step" in last_line and "of" in last_line:
                try:
                    parts = last_line.split("Step")[1].split("of")
                    current = int(parts[0].strip())
                    total = int(parts[1].strip().split()[0])
                    progress_bar.progress(current / total)
                except (ValueError, IndexError):
                    pass
            
            # Match "fold X/Y" pattern
            if "fold" in last_line.lower() and "/" in last_line:
                try:
                    import re
                    match = re.search(r'fold\s*(\d+)\s*/\s*(\d+)', last_line, re.IGNORECASE)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        progress_bar.progress(current / total)
                except (ValueError, IndexError):
                    pass
        
        time.sleep(poll_interval)
    
    # Get final result
    result = executor.get_result(use_xgboost=use_xgboost)
    elapsed_time = time.time() - start_time
    
    # Display results
    if result["success"]:
        st.success(f"✅ Backtest hoàn thành trong {elapsed_time:.1f} giây")
        
        results = result["results"]
        
        # Summary metrics
        st.markdown("## 📊 Kết quả Walk-Forward")
        
        summary = results.get("summary", {})
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Avg Portfolio IC", f"{summary.get('avg_portfolio_ic', 0):.4f}")
        
        with col2:
            st.metric("Avg Sharpe Ratio", f"{summary.get('avg_portfolio_sharpe', 0):.2f}")
        
        with col3:
            st.metric("Avg Max Drawdown", f"{summary.get('avg_portfolio_max_dd', 0):.2%}")
        
        with col4:
            st.metric("Tổng số Folds", f"{summary.get('total_folds', 0)}")
            
        fold_details = results.get("fold_details", [])
        if fold_details:
            import pandas as pd
            import plotly.graph_objects as go
            
            df_folds = pd.DataFrame(fold_details)
            
            # Walk-forward Fold Comparison
            st.markdown("### 📈 Hiệu suất theo Folds")
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_folds["fold_id"],
                y=df_folds["portfolio_sharpe"],
                name="Sharpe Ratio",
                marker_color="#2E86AB"
            ))
            fig.add_trace(go.Scatter(
                x=df_folds["fold_id"],
                y=df_folds["portfolio_ic"],
                name="Portfolio IC",
                yaxis="y2",
                mode="lines+markers",
                line=dict(color="#E63946", width=3)
            ))
            
            fig.update_layout(
                title="So sánh Sharpe Ratio & Portfolio IC qua các Folds",
                xaxis=dict(title="Fold ID", tickmode="linear"),
                yaxis=dict(title="Sharpe Ratio", side="left"),
                yaxis2=dict(title="Portfolio IC", side="right", overlaying="y", showgrid=False),
                hovermode='x unified',
                height=450,
                legend=dict(x=0.01, y=0.99)
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Drawdown & Return Comparison
            st.markdown("### 📉 Drawdown & Lợi nhuận theo Folds")
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=df_folds["fold_id"],
                y=df_folds["portfolio_total_return"],
                name="Total Return",
                marker_color="#3A86C8"
            ))
            fig2.add_trace(go.Scatter(
                x=df_folds["fold_id"],
                y=df_folds["portfolio_max_dd"],
                name="Max Drawdown",
                mode="lines+markers",
                line=dict(color="#E63946", width=2)
            ))
            fig2.update_layout(
                title="Total Return & Max Drawdown qua các Folds",
                xaxis=dict(title="Fold ID", tickmode="linear"),
                yaxis=dict(title="Tỷ lệ (%)", tickformat=".1%"),
                hovermode='x unified',
                height=400,
                legend=dict(x=0.01, y=0.99)
            )
            st.plotly_chart(fig2, use_container_width=True)
            
        # Alpha average IC bar chart
        alpha_ics = results.get("alpha_ics", {})
        if alpha_ics:
            import plotly.graph_objects as go
            st.markdown("### 🧪 Trung bình IC của các Alphas")
            alpha_names = list(alpha_ics.keys())
            alpha_values = list(alpha_ics.values())
            
            # Sort by IC value descending
            alpha_data = sorted(zip(alpha_names, alpha_values), key=lambda x: x[1], reverse=True)
            sorted_names = [x[0] for x in alpha_data]
            sorted_values = [x[1] for x in alpha_data]
            
            fig_alpha = go.Figure()
            fig_alpha.add_trace(go.Bar(
                x=sorted_names,
                y=sorted_values,
                name="Average IC",
                marker=dict(
                    color=sorted_values,
                    colorscale="RdYlGn",
                    showscale=True
                )
            ))
            fig_alpha.update_layout(
                title="Trung bình IC của từng Alpha",
                xaxis_title="Alpha Factor",
                yaxis_title="Average IC",
                height=400
            )
            st.plotly_chart(fig_alpha, use_container_width=True)
            
        # Detailed table
        if fold_details:
            with st.expander("📋 Xem chi tiết các Folds"):
                import pandas as pd
                df_disp = df_folds[[
                    "fold_id", "train_start", "train_end", "test_start", "test_end",
                    "portfolio_ic", "portfolio_sharpe", "portfolio_max_dd", "portfolio_total_return",
                    "n_train_samples", "n_test_samples"
                ]].copy()
                df_disp.columns = [
                    "Fold ID", "Train Bắt đầu", "Train Kết thúc", "Test Bắt đầu", "Test Kết thúc",
                    "Portfolio IC", "Sharpe Ratio", "Max Drawdown", "Tổng lợi nhuận",
                    "Số mẫu Train", "Số mẫu Test"
                ]
                st.dataframe(
                    df_disp.style.format({
                        "Portfolio IC": "{:.4f}",
                        "Sharpe Ratio": "{:.2f}",
                        "Max Drawdown": "{:.2%}",
                        "Tổng lợi nhuận": "{:.2%}",
                        "Số mẫu Train": "{:,}",
                        "Số mẫu Test": "{:,}"
                    }),
                    use_container_width=True
                )
        
        # Export options
        st.markdown("### 💾 Xuất kết quả")
        
        col1, col2 = st.columns(2)
        
        with col1:
            import json
            
            json_data = json.dumps(results, indent=2, ensure_ascii=False)
            st.download_button(
                label="📥 Download JSON",
                data=json_data,
                file_name=f"backtest_results_{start_date}_{end_date}.json",
                mime="application/json"
            )
        
        with col2:
            if fold_details:
                csv_data = pd.DataFrame(fold_details).to_csv(index=False)
                st.download_button(
                    label="📥 Download Folds (CSV)",
                    data=csv_data,
                    file_name=f"backtest_folds_{start_date}_{end_date}.csv",
                    mime="text/csv"
                )
        
    else:
        st.error(f"❌ Backtest thất bại: {result.get('error', 'Unknown error')}")
        
        # Show output if available
        output = result.get("output", "")
        if output:
            with st.expander("📋 Xem log"):
                st.code(output)

else:
    # Instructions
    st.markdown("""
    ## 📖 Hướng dẫn sử dụng
    
    ### 1. Cấu hình Backtest
    
    Sử dụng sidebar bên trái để cấu hình:
    
    - **Chế độ chạy**: 
      - Quick Test: Chạy nhanh với 1 ticker để kiểm tra (< 5 phút)
      - Full Backtest: Chạy đầy đủ với tất cả tickers (15-30 phút)
    
    - **Thời gian**: Chọn khoảng thời gian backtest
    
    - **Vốn ban đầu**: Số vốn khởi điểm (VND)
    
    - **Chiến lược**: 
      - Multi-factor: Kết hợp nhiều factors
      - Momentum: Đánh theo xu hướng
      - Mean Reversion: Đánh ngược xu hướng
    
    - **Tùy chọn nâng cao**:
      - Slippage: Độ trượt giá (basis points)
      - Commission: Phí giao dịch (basis points)
      - XGBoost: Bật/tắt XGBoost signal
    
    ### 2. Chạy Backtest
    
    Nhấn nút **🚀 Chạy Backtest** để bắt đầu.
    
    Progress sẽ được hiển thị real-time.
    
    ### 3. Xem kết quả
    
    Sau khi hoàn thành, bạn sẽ thấy:
    
    - **Summary metrics**: Tổng lợi nhuận, Sharpe, Max DD, Win Rate
    - **Equity Curve**: Diễn biến giá trị portfolio
    - **Drawdown Chart**: Drawdown theo thời gian
    - **Trade Summary**: Thống kê giao dịch
    - **Monthly Returns Heatmap**: Lợi nhuận theo tháng
    - **Export**: Download kết quả (JSON, CSV)
    
    ### ⚠️ Lưu ý
    
    - Backtest chạy trong subprocess riêng, không ảnh hưởng đến dashboard
    - Chỉ có thể chạy 1 backtest tại một thời điểm (lock file)
    - Full Backtest có thể mất 15-30 phút
    - Kết quả sẽ được lưu vào `data/phase35_results/`
    """)
    
    # Show recent backtests
    st.markdown("## 📂 Backtest gần đây")
    
    @st.cache_data(ttl=300)  # Cache 5 phút
    def load_recent_backtests():
        """Load 5 backtest results gần nhất"""
        results = []
        if DATA_DIR.exists():
            result_files = sorted(
                DATA_DIR.glob("phase35_results/phase35_backtest_results_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )[:5]
            
            for result_file in result_files:
                try:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    results.append({
                        'file': result_file.name,
                        'data': data,
                        'mtime': result_file.stat().st_mtime
                    })
                except Exception as e:
                    st.warning(f"Không thể đọc {result_file.name}: {str(e)}")
        return results
    
    recent_results = load_recent_backtests()
    
    if recent_results:
        for i, item in enumerate(recent_results):
            data = item['data']
            config = data.get("config", {})
            summary = data.get("summary", {})
            timestamp = data.get("timestamp", "")
            
            with st.expander(f"📊 Backtest #{i+1} - {timestamp}"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.markdown(f"**Thời gian**: {config.get('start_date')} → {config.get('end_date')}")
                    st.markdown(f"**Chiến lược**: {config.get('strategy')}")
                
                with col2:
                    st.metric("Avg IC", f"{summary.get('avg_portfolio_ic', 0):.4f}")
                    st.metric("Avg Sharpe", f"{summary.get('avg_portfolio_sharpe', 0):.2f}")
                
                with col3:
                    st.metric("Avg Max DD", f"{summary.get('avg_portfolio_max_dd', 0):.2%}")
                    st.markdown(f"**Folds**: {summary.get('total_folds', 0)}")
    else:
        st.info("Chưa có backtest nào. Hãy chạy backtest đầu tiên!")
