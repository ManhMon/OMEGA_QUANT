"""
Regime Detection Page
Phân tích chế độ thị trường sử dụng HMM
"""
import streamlit as st
import sys
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.regime_service import RegimeService
from services.data_loader import DataLoaderService
from config.dashboard_config import PAGE_TITLE, PAGE_ICON

st.set_page_config(
    page_title=f"{PAGE_TITLE} - Regime Detection",
    page_icon=PAGE_ICON,
    layout="wide"
)

st.markdown("# 🌊 Regime Detection")
st.markdown("Phân tích chế độ thị trường và hiệu suất theo từng regime")

# Initialize services
regime_service = RegimeService()
data_loader = DataLoaderService()

# Tabs
tab1, tab2, tab3 = st.tabs([
    "📊 Current Regime",
    "📈 Regime History",
    "🎯 Regime-Aware Performance"
])

# Tab 1: Current Regime
with tab1:
    st.markdown("## 📊 Current Market Regime")
    st.markdown("Phân tích chế độ thị trường hiện tại")
    
    # Load market data
    market_data = data_loader.load_market_data()
    
    if market_data is None:
        st.warning("⚠️ Chưa có dữ liệu thị trường. Hãy chạy data loader trước.")
    else:
        try:
            # Detect current regime
            current_regime = regime_service.detect_current_regime(market_data)
            
            # Display current regime with visual indicator
            st.markdown("### 🎯 Chế độ hiện tại")
            
            regime_colors = {
                'Bull': '#90EE90',
                'Bear': '#FF6B6B',
                'Sideways': '#FFD700'
            }
            
            regime_emojis = {
                'Bull': '🐂',
                'Bear': '🐻',
                'Sideways': '➡️'
            }
            
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col2:
                regime_name = current_regime['regime']
                confidence = current_regime['confidence']
                color = regime_colors.get(regime_name, '#CCCCCC')
                emoji = regime_emojis.get(regime_name, '❓')
                
                st.markdown(
                    f"""
                    <div style="background-color: {color}; padding: 2rem; border-radius: 10px; text-align: center;">
                        <h1 style="font-size: 4rem; margin: 0;">{emoji}</h1>
                        <h2 style="margin: 0.5rem 0;">{regime_name} Market</h2>
                        <p style="font-size: 1.5rem; margin: 0;">Confidence: {confidence:.1f}%</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            
            # Regime probabilities
            st.markdown("### 📊 Xác suất các chế độ")
            
            probabilities = current_regime['probabilities']
            
            fig = go.Figure(data=[
                go.Bar(
                    x=list(probabilities.keys()),
                    y=list(probabilities.values()),
                    marker_color=[regime_colors.get(k, '#CCCCCC') for k in probabilities.keys()],
                    text=[f"{v:.1f}%" for v in probabilities.values()],
                    textposition='auto'
                )
            ])
            
            fig.update_layout(
                title="Xác suất các chế độ thị trường",
                xaxis_title="Regime",
                yaxis_title="Probability (%)",
                yaxis=dict(range=[0, 100]),
                height=400
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # Market indicators
            st.markdown("### 📈 Chỉ số thị trường")
            
            indicators = current_regime['indicators']
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Return (20d)",
                    f"{indicators['return_20d']:.2%}",
                    delta=f"{indicators['return_20d_change']:.2%}"
                )
            
            with col2:
                st.metric(
                    "Volatility (20d)",
                    f"{indicators['volatility_20d']:.2%}",
                    delta=f"{indicators['volatility_20d_change']:.2%}"
                )
            
            with col3:
                st.metric(
                    "Volume Ratio",
                    f"{indicators['volume_ratio']:.2f}x",
                    delta=f"{indicators['volume_ratio_change']:.2f}x"
                )
            
            with col4:
                st.metric(
                    "Market Breadth",
                    f"{indicators['market_breadth']:.2%}",
                    delta=f"{indicators['market_breadth_change']:.2%}"
                )
            
            # Regime characteristics
            st.markdown("### 🔍 Đặc điểm chế độ hiện tại")
            
            characteristics = regime_service.get_regime_characteristics(regime_name)
            
            st.markdown(f"""
            **Mô tả:** {characteristics['description']}
            
            **Đặc điểm chính:**
            - Lợi nhuận trung bình: {characteristics['avg_return']:.2%}
            - Biến động trung bình: {characteristics['avg_volatility']:.2%}
            - Khối lượng giao dịch: {characteristics['avg_volume']}
            
            **Khuyến nghị chiến lược:**
            {characteristics['strategy_recommendation']}
            """)
            
        except Exception as e:
            st.error(f"❌ Lỗi khi phân tích regime hiện tại: {str(e)}")

# Tab 2: Regime History
with tab2:
    st.markdown("## 📈 Regime History")
    st.markdown("Lịch sử các chế độ thị trường")
    
    # Load market data
    market_data = data_loader.load_market_data()
    
    if market_data is None:
        st.warning("⚠️ Chưa có dữ liệu thị trường. Hãy chạy data loader trước.")
    else:
        try:
            # Get regime history
            regime_history = regime_service.get_regime_history(
                market_data,
                lookback_days=365
            )
            
            # Regime timeline chart
            st.markdown("### 📊 Timeline chế độ thị trường")
            
            timeline_df = pd.DataFrame(regime_history['timeline'])
            
            # Create color mapping
            color_map = {
                'Bull': '#90EE90',
                'Bear': '#FF6B6B',
                'Sideways': '#FFD700'
            }
            
            fig = go.Figure()
            
            # Add regime periods as colored backgrounds
            for _, period in timeline_df.iterrows():
                fig.add_vrect(
                    x0=period['start_date'],
                    x1=period['end_date'],
                    fillcolor=color_map.get(period['regime'], '#CCCCCC'),
                    opacity=0.3,
                    line_width=0,
                    annotation_text=period['regime'],
                    annotation_position="top"
                )
            
            # Add price line
            price_data = regime_history['prices']
            fig.add_trace(go.Scatter(
                x=price_data['dates'],
                y=price_data['values'],
                mode='lines',
                name='Market Index',
                line=dict(color='black', width=2)
            ))
            
            fig.update_layout(
                title="Timeline chế độ thị trường (1 năm)",
                xaxis_title="Date",
                yaxis_title="Market Index",
                height=500,
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # Regime distribution
            st.markdown("### 📊 Phân bố thời gian theo chế độ")
            
            distribution = regime_history['distribution']
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Pie chart
                fig = px.pie(
                    values=list(distribution.values()),
                    names=list(distribution.keys()),
                    title="Phân bố thời gian theo chế độ",
                    color=list(distribution.keys()),
                    color_discrete_map=color_map
                )
                st.plotly_chart(fig, width="stretch")
            
            with col2:
                # Statistics table
                st.markdown("**Thống kê:**")
                
                total_days = sum(distribution.values())
                
                stats_data = []
                for regime, days in distribution.items():
                    stats_data.append({
                        'Regime': regime,
                        'Days': days,
                        'Percentage': f"{days/total_days*100:.1f}%",
                        'Avg Duration': f"{regime_history['avg_duration'][regime]:.1f} days"
                    })
                
                stats_df = pd.DataFrame(stats_data)
                st.dataframe(stats_df, width="stretch", hide_index=True)
            
            # Regime transitions
            st.markdown("### 🔄 Chuyển đổi chế độ")
            
            transitions = regime_history['transitions']
            
            if transitions:
                transition_df = pd.DataFrame(transitions)
                
                # Transition matrix
                st.markdown("**Ma trận chuyển đổi:**")
                
                transition_matrix = regime_service.calculate_transition_matrix(transitions)
                
                fig = px.imshow(
                    transition_matrix,
                    labels=dict(x="To Regime", y="From Regime", color="Probability"),
                    title="Ma trận xác suất chuyển đổi chế độ",
                    color_continuous_scale='Blues',
                    aspect='auto'
                )
                
                st.plotly_chart(fig, width="stretch")
                
                # Recent transitions
                st.markdown("**Chuyển đổi gần đây:**")
                
                recent_transitions = transition_df.tail(10)
                
                st.dataframe(
                    recent_transitions,
                    column_config={
                        'date': 'Date',
                        'from_regime': 'From',
                        'to_regime': 'To',
                        'duration_days': st.column_config.NumberColumn(
                            'Duration (days)',
                            format='%d'
                        )
                    },
                    width="stretch",
                    hide_index=True
                )
            else:
                st.info("Không có chuyển đổi chế độ nào trong khoảng thời gian này")
            
        except Exception as e:
            st.error(f"❌ Lỗi khi phân tích lịch sử regime: {str(e)}")

# Tab 3: Regime-Aware Performance
with tab3:
    st.markdown("## 🎯 Regime-Aware Performance")
    st.markdown("Phân tích hiệu suất theo từng chế độ thị trường")
    
    # Load data
    market_data = data_loader.load_market_data()
    portfolio_data = data_loader.load_portfolio_data()
    
    if market_data is None or portfolio_data is None:
        st.warning("⚠️ Chưa có dữ liệu thị trường hoặc portfolio. Hãy chạy backtest trước.")
    else:
        try:
            # Calculate regime-aware performance
            regime_performance = regime_service.calculate_regime_performance(
                market_data=market_data,
                portfolio_returns=portfolio_data['returns']
            )
            
            # Summary by regime
            st.markdown("### 📊 Hiệu suất theo chế độ")
            
            performance_by_regime = regime_performance['by_regime']
            
            # Create summary table
            summary_data = []
            for regime, metrics in performance_by_regime.items():
                summary_data.append({
                    'Regime': regime,
                    'Return': metrics['return'],
                    'Volatility': metrics['volatility'],
                    'Sharpe': metrics['sharpe'],
                    'Max DD': metrics['max_drawdown'],
                    'Win Rate': metrics['win_rate'],
                    'Trades': metrics['num_trades']
                })
            
            summary_df = pd.DataFrame(summary_data)
            
            # Display with color coding
            st.dataframe(
                summary_df,
                column_config={
                    'Regime': 'Regime',
                    'Return': st.column_config.NumberColumn('Return', format='%.2f%%'),
                    'Volatility': st.column_config.NumberColumn('Volatility', format='%.2f%%'),
                    'Sharpe': st.column_config.NumberColumn('Sharpe', format='%.2f'),
                    'Max DD': st.column_config.NumberColumn('Max DD', format='%.2f%%'),
                    'Win Rate': st.column_config.NumberColumn('Win Rate', format='%.1f%%'),
                    'Trades': st.column_config.NumberColumn('Trades', format='%d')
                },
                width="stretch",
                hide_index=True
            )
            
            # Performance comparison chart
            st.markdown("### 📈 So sánh hiệu suất theo chế độ")
            
            fig = go.Figure()
            
            regimes = list(performance_by_regime.keys())
            returns = [performance_by_regime[r]['return'] * 100 for r in regimes]
            sharpes = [performance_by_regime[r]['sharpe'] for r in regimes]
            
            fig.add_trace(go.Bar(
                name='Return (%)',
                x=regimes,
                y=returns,
                marker_color=[color_map.get(r, '#CCCCCC') for r in regimes]
            ))
            
            fig.add_trace(go.Scatter(
                name='Sharpe Ratio',
                x=regimes,
                y=sharpes,
                mode='lines+markers',
                yaxis='y2',
                line=dict(color='black', width=3),
                marker=dict(size=12)
            ))
            
            fig.update_layout(
                title="Hiệu suất theo chế độ thị trường",
                xaxis_title="Regime",
                yaxis_title="Return (%)",
                yaxis2=dict(
                    title='Sharpe Ratio',
                    overlaying='y',
                    side='right'
                ),
                height=500,
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # Regime-specific metrics
            st.markdown("### 🔍 Chi tiết theo từng chế độ")
            
            for regime in ['Bull', 'Bear', 'Sideways']:
                if regime in performance_by_regime:
                    metrics = performance_by_regime[regime]
                    
                    with st.expander(f"{regime_emojis.get(regime, '❓')} {regime} Market"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Tổng lợi nhuận", f"{metrics['return']:.2%}")
                            st.metric("Volatility", f"{metrics['volatility']:.2%}")
                            st.metric("Sharpe Ratio", f"{metrics['sharpe']:.2f}")
                        
                        with col2:
                            st.metric("Max Drawdown", f"{metrics['max_drawdown']:.2%}")
                            st.metric("Win Rate", f"{metrics['win_rate']:.1f}%")
                            st.metric("Profit Factor", f"{metrics['profit_factor']:.2f}")
                        
                        with col3:
                            st.metric("Số trades", metrics['num_trades'])
                            st.metric("Avg Trade", f"{metrics['avg_trade_return']:.2%}")
                            st.metric("Exposure", f"{metrics['exposure']:.1f}%")
                        
                        # Equity curve for this regime
                        if 'equity_curve' in metrics:
                            fig = go.Figure()
                            
                            fig.add_trace(go.Scatter(
                                x=metrics['equity_curve']['dates'],
                                y=metrics['equity_curve']['values'],
                                mode='lines',
                                name=f'{regime} Equity',
                                line=dict(color=color_map.get(regime, '#CCCCCC'), width=2)
                            ))
                            
                            fig.update_layout(
                                title=f"Equity Curve - {regime} Market",
                                xaxis_title="Date",
                                yaxis_title="Portfolio Value",
                                height=400
                            )
                            
                            st.plotly_chart(fig, width="stretch")
            
            # Strategy recommendations
            st.markdown("### 💡 Khuyến nghị chiến lược")
            
            best_regime = max(
                performance_by_regime.items(),
                key=lambda x: x[1]['sharpe']
            )
            
            worst_regime = min(
                performance_by_regime.items(),
                key=lambda x: x[1]['sharpe']
            )
            
            st.markdown(f"""
            **Chế độ hiệu quả nhất:** {best_regime[0]} Market
            - Sharpe Ratio: {best_regime[1]['sharpe']:.2f}
            - Return: {best_regime[1]['return']:.2%}
            
            **Chế độ kém hiệu quả nhất:** {worst_regime[0]} Market
            - Sharpe Ratio: {worst_regime[1]['sharpe']:.2f}
            - Return: {worst_regime[1]['return']:.2%}
            
            **Khuyến nghị:**
            - Tăng cường giao dịch trong chế độ {best_regime[0]}
            - Giảm exposure hoặc áp dụng chiến lược phòng thủ trong chế độ {worst_regime[0]}
            - Xem xét regime-aware position sizing để tối ưu hiệu suất
            """)
            
        except Exception as e:
            st.error(f"❌ Lỗi khi phân tích hiệu suất theo regime: {str(e)}")
