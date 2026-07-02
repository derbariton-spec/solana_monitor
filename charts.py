from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_candlestick_chart(candles: pd.DataFrame, title: str = "SOL/USD") -> None:
    if candles is None or candles.empty:
        st.info("Keine Kerzendaten verfügbar.")
        return
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=candles["time"],
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name=title,
            )
        ]
    )
    fig.update_layout(
        title=title,
        height=620,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=50, b=10),
        yaxis_title="USD",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_line_history(df: pd.DataFrame, column: str, title: str = "Verlauf") -> None:
    if df is None or df.empty or column not in df.columns:
        st.info("Keine historischen Daten verfügbar.")
        return
    chart_df = df.set_index("snapshot_date")[[column]].dropna()
    if chart_df.empty:
        st.info("Für diese Kennzahl gibt es noch keine Werte.")
        return
    st.line_chart(chart_df)
