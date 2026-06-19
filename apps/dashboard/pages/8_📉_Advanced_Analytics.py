"""
Advanced Analytics Page
Performance attribution, alpha decay monitoring, signal quality
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

from services.attribution_service import AttributionService
from services.alpha_decay_service import AlphaDecayService
from services.data_loader import DataLoaderService
from config.dashboard_config import PAGE_TITLE, PAGE_ICON

st.set_page_config(
    page_title=f"{PAGE_TITLE} - Advanced Analytics",
    page_icon=PAGE_ICON,
    layout="wide"
)

st.markdown("# 📉 Advanced Analytics")
st.markdown("Phân tích chi tiết hiệu suất, alpha decay và chất lượng signals")

# Initialize services
attribution_service = AttributionService()
alpha_decay_service = AlphaDecayService()

# Tabs
tab1, tab2, tab3 = st.tabs([
    "📊 Performance Attribution",
    "📉 Alpha Decay Monitoring",
    "🎯 Signal Quality"
])

# Tab 1: Performance Attribution
with tab1:
    st.markdown("## 📊 Performance Attribution")
    st.markdown("Phân tích nguồn gốc lợi nhuận: allocation, selection, interaction effects")
    
    # Load portfolio data
    data_loader = DataLoaderService()
    portfolio_data = data_loader.load_portfolio_data()
    benchmark_data = data_loader.load_benchmark_data()
    
    if portfolio_data is None or benchmark_data is None:
        st.warning("⚠️ Chưa có dữ liệu portfolio hoặc benchmark. Hãy chạy backtest trước.")
    else:
        # Calculate attribution
        try:
            attribution_result = attribution_service.calculate_attribution(
                portfolio_returns=portfolio_data['returns'],
                benchmark_returns=benchmark_data['returns'],
                portfolio_weights=portfolio_data['weights'],
                benchmark_weights=benchmark_data['weights'],
                sectors=portfolio_data['sectors']
            )
            
            # Display summary
            st.markdown("### 📈 Tóm tắt Attribution")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_return = attribution_result['total_return']
                st.metric("Tổng lợi nhuận", f"{total_return:.2%}")
            
            with col2:
                allocation_effect = attribution_result['allocation_effect']
                st.metric("Allocation Effect", f"{allocation_effect:.2%}")
            
            with col3:
                selection_effect = attribution_result['selection_effect']
                st.metric("Selection Effect", f"{selection_effect:.2%}")
            
            with col4:
                interaction_effect = attribution_result['interaction_effect']
                st.metric("Interaction Effect", f"{interaction_effect:.2%}")
            
            # Sector attribution table
            st.markdown("### 🏢 Sector Attribution")
            
            sector_attribution = attribution_result['sector_attribution']
            
            # Create dataframe
            sector_df = pd.DataFrame(sector_attribution)
            sector_df = sector_df.sort_values('total_effect', ascending=False)
            
            # Display table
            st.dataframe(
                sector_df,
                column_config={
                    'sector': 'Sector',
                    'allocation_effect': st.column_config.NumberColumn(
                        'Allocation',
                        format='%.2f%%'
                    ),
                    'selection_effect': st.column_config.NumberColumn(
                        'Selection',
                        format='%.2f%%'
                    ),
                    'interaction_effect': st.column_config.NumberColumn(
                        'Interaction',
                        format='%.2f%%'
                    ),
                    'total_effect': st.column_config.NumberColumn(
                        'Total',
                        format='%.2f%%'
                    )
                },
                width="stretch",
                hide_index=True
            )
            
            # Visualization: Sector contribution waterfall
            st.markdown("### 📊 Đóng góp theo Sector")
            
            fig = go.Figure(go.Waterfall(
                name="Sector Attribution",
                orientation="v",
                measure=["relative"] * len(sector_df),
                x=sector_df['sector'],
                y=sector_df['total_effect'] * 100,
                textposition="outside",
                text=[f"{v:.2f}%" for v in sector_df['total_effect'] * 100],
                connector={"line": {"color": "rgb(63, 63, 63)"}},
            ))
            
            fig.update_layout(
                title="Waterfall Chart: Đóng góp lợi nhuận theo Sector",
                xaxis_title="Sector",
                yaxis_title="Đóng góp (%)",
                showlegend=False,
                height=500
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # Factor attribution
            st.markdown("### 🔬 Factor Attribution")
            st.markdown("Phân tích lợi nhuận theo các factors (Fama-French 5 factors)")
            
            factor_attribution = attribution_service.calculate_factor_attribution(
                portfolio_returns=portfolio_data['returns'],
                factor_returns=benchmark_data['factor_returns']
            )
            
            factor_df = pd.DataFrame(factor_attribution)
            
            fig = px.bar(
                factor_df,
                x='factor',
                y='contribution',
                title="Đóng góp theo Factor",
                labels={'factor': 'Factor', 'contribution': 'Đóng góp (%)'},
                color='contribution',
                color_continuous_scale='RdYlGn'
            )
            
            fig.update_layout(height=400)
            st.plotly_chart(fig, width="stretch")
            
            # Display factor table
            st.dataframe(
                factor_df,
                column_config={
                    'factor': 'Factor',
                    'exposure': st.column_config.NumberColumn('Exposure', format='%.3f'),
                    'factor_return': st.column_config.NumberColumn('Factor Return', format='%.2f%%'),
                    'contribution': st.column_config.NumberColumn('Contribution', format='%.2f%%')
                },
                width="stretch",
                hide_index=True
            )
            
        except Exception as e:
            st.error(f"❌ Lỗi khi tính attribution: {str(e)}")

# Tab 2: Alpha Decay Monitoring
with tab2:
    st.markdown("## 📉 Alpha Decay Monitoring")
    st.markdown("Theo dõi sự suy giảm của alpha signals theo thời gian")
    
    # Load alpha signals
    data_loader = DataLoaderService()
    alpha_signals = data_loader.load_alpha_signals()
    
    if alpha_signals is None:
        st.warning("⚠️ Chưa có dữ liệu alpha signals. Hãy chạy evolution hoặc backtest trước.")
    else:
        # Calculate decay metrics
        try:
            decay_metrics = alpha_decay_service.calculate_decay(
                signals=alpha_signals['signals'],
                returns=alpha_signals['returns'],
                lags=[1, 5, 10, 20, 60]
            )
            
            # Display summary
            st.markdown("### 📊 Tóm tắt Alpha Decay")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                avg_ic = decay_metrics['avg_ic']
                st.metric("Average IC", f"{avg_ic:.4f}")
            
            with col2:
                ic_half_life = decay_metrics['ic_half_life']
                st.metric("IC Half-Life", f"{ic_half_life:.1f} days")
            
            with col3:
                decay_rate = decay_metrics['decay_rate']
                st.metric("Decay Rate", f"{decay_rate:.4f}")
            
            # IC decay curve
            st.markdown("### 📈 IC Decay Curve")
            
            ic_by_lag = decay_metrics['ic_by_lag']
            
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=list(ic_by_lag.keys()),
                y=list(ic_by_lag.values()),
                mode='lines+markers',
                name='IC',
                line=dict(color='#2E86AB', width=3),
                marker=dict(size=10)
            ))
            
            # Add half-life line
            half_life_ic = ic_by_lag[1] / 2 if 1 in ic_by_lag else 0
            fig.add_hline(
                y=half_life_ic,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Half-Life IC ({half_life_ic:.4f})"
            )
            
            fig.update_layout(
                title="Information Coefficient (IC) theo Lag",
                xaxis_title="Lag (days)",
                yaxis_title="IC",
                hovermode='x unified',
                height=500
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # Signal lifecycle
            st.markdown("### 🔄 Signal Lifecycle")
            
            signal_lifecycle = alpha_decay_service.analyze_signal_lifecycle(
                signals=alpha_signals['signals'],
                returns=alpha_signals['returns']
            )
            
            # Create lifecycle dataframe
            lifecycle_df = pd.DataFrame(signal_lifecycle)
            
            # Color code by status
            def color_status(val):
                if val == 'Active':
                    return 'background-color: #90EE90'
                elif val == 'Decaying':
                    return 'background-color: #FFD700'
                elif val == 'Dead':
                    return 'background-color: #FF6B6B'
                return ''
            
            styled_df = lifecycle_df.style.applymap(
                color_status,
                subset=['status']
            )
            
            st.dataframe(
                styled_df,
                column_config={
                    'signal_id': 'Signal ID',
                    'status': 'Status',
                    'age_days': st.column_config.NumberColumn('Age (days)', format='%d'),
                    'current_ic': st.column_config.NumberColumn('Current IC', format='%.4f'),
                    'peak_ic': st.column_config.NumberColumn('Peak IC', format='%.4f'),
                    'ic_decay': st.column_config.NumberColumn('IC Decay', format='%.2f%%')
                },
                width="stretch",
                hide_index=True
            )
            
            # Decay heatmap
            st.markdown("### 🔥 Decay Heatmap")
            
            decay_heatmap = alpha_decay_service.generate_decay_heatmap(
                signals=alpha_signals['signals'],
                returns=alpha_signals['returns'],
                max_lag=60
            )
            
            fig = px.imshow(
                decay_heatmap,
                labels=dict(x="Lag (days)", y="Signal", color="IC"),
                title="IC Decay Heatmap",
                color_continuous_scale='RdYlGn',
                aspect='auto'
            )
            
            fig.update_layout(height=600)
            st.plotly_chart(fig, width="stretch")
            
        except Exception as e:
            st.error(f"❌ Lỗi khi phân tích alpha decay: {str(e)}")

# Tab 3: Signal Quality
with tab3:
    st.markdown("## 🎯 Signal Quality")
    st.markdown("Đánh giá chất lượng của các alpha signals")
    
    # Load signals
    data_loader = DataLoaderService()
    signals = data_loader.load_alpha_signals()
    
    if signals is None:
        st.warning("⚠️ Chưa có dữ liệu signals. Hãy chạy evolution hoặc backtest trước.")
    else:
        # Calculate quality metrics
        try:
            quality_metrics = alpha_decay_service.calculate_signal_quality(
                signals=signals['signals'],
                returns=signals['returns']
            )
            
            # Summary metrics
            st.markdown("### 📊 Tóm tắt chất lượng")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_signals = quality_metrics['total_signals']
                st.metric("Tổng Signals", total_signals)
            
            with col2:
                active_signals = quality_metrics['active_signals']
                st.metric("Active Signals", active_signals)
            
            with col3:
                avg_ic = quality_metrics['avg_ic']
                st.metric("Avg IC", f"{avg_ic:.4f}")
            
            with col4:
                ic_ir = quality_metrics['ic_ir']
                st.metric("IC Information Ratio", f"{ic_ir:.2f}")
            
            # Signal quality distribution
            st.markdown("### 📈 Phân bố chất lượng Signals")
            
            quality_dist = quality_metrics['quality_distribution']
            
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                x=list(quality_dist.keys()),
                y=list(quality_dist.values()),
                marker_color=['#FF6B6B', '#FFD700', '#90EE90'],
                text=list(quality_dist.values()),
                textposition='auto'
            ))
            
            fig.update_layout(
                title="Phân bố chất lượng Signals",
                xaxis_title="Quality Level",
                yaxis_title="Number of Signals",
                height=400
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # Top performing signals
            st.markdown("### 🏆 Top Performing Signals")
            
            top_signals = quality_metrics['top_signals']
            
            if top_signals:
                top_df = pd.DataFrame(top_signals)
                
                st.dataframe(
                    top_df,
                    column_config={
                        'signal_id': 'Signal ID',
                        'ic': st.column_config.NumberColumn('IC', format='%.4f'),
                        'ic_ir': st.column_config.NumberColumn('IC IR', format='%.2f'),
                        'turnover': st.column_config.NumberColumn('Turnover', format='%.2f%%'),
                        'sharpe': st.column_config.NumberColumn('Sharpe', format='%.2f'),
                        'max_drawdown': st.column_config.NumberColumn('Max DD', format='%.2f%%')
                    },
                    width="stretch",
                    hide_index=True
                )
            else:
                st.info("Không có signals đủ tiêu chuẩn")
            
            # Signal correlation matrix
            st.markdown("### 🔗 Signal Correlation Matrix")
            
            correlation_matrix = quality_metrics['correlation_matrix']
            
            if correlation_matrix is not None:
                fig = px.imshow(
                    correlation_matrix,
                    labels=dict(x="Signal", y="Signal", color="Correlation"),
                    title="Ma trận tương quan giữa các Signals",
                    color_continuous_scale='RdBu',
                    aspect='auto'
                )
                
                fig.update_layout(height=600)
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("Không đủ signals để tính correlation")
            
            # Signal performance over time
            st.markdown("### 📈 Signal Performance Over Time")
            
            performance_over_time = quality_metrics['performance_over_time']
            
            if performance_over_time:
                perf_df = pd.DataFrame(performance_over_time)
                
                fig = go.Figure()
                
                fig.add_trace(go.Scatter(
                    x=perf_df['date'],
                    y=perf_df['avg_ic'],
                    mode='lines',
                    name='Avg IC',
                    line=dict(color='#2E86AB', width=2)
                ))
                
                fig.add_trace(go.Scatter(
                    x=perf_df['date'],
                    y=perf_df['ic_ir'],
                    mode='lines',
                    name='IC IR',
                    line=dict(color='#A23B72', width=2),
                    yaxis='y2'
                ))
                
                fig.update_layout(
                    title="Hiệu suất Signals theo thời gian",
                    xaxis_title="Date",
                    yaxis_title="Avg IC",
                    yaxis2=dict(
                        title='IC IR',
                        overlaying='y',
                        side='right'
                    ),
                    hovermode='x unified',
                    height=500
                )
                
                st.plotly_chart(fig, width="stretch")
            
        except Exception as e:
            st.error(f"❌ Lỗi khi đánh giá chất lượng signals: {str(e)}")
