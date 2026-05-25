"""Chart wrapper helpers for dashboard pages."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st


PLOTLY_COLORS = [
    "#0f766e",
    "#f97316",
    "#2563eb",
    "#e11d48",
    "#7c3aed",
    "#059669",
    "#d97706",
    "#475569",
]


def _render_plotly_chart(data: pd.DataFrame, *, kind: str) -> None:
    frame = data.reset_index()
    if frame.empty:
        st.info("보여드릴 내용이 아직 없습니다.")
        return

    if kind == "line":
        x_col = frame.columns[0]
        y_col = frame.columns[1]
        figure = px.line(
            frame,
            x=x_col,
            y=y_col,
            markers=True,
            color_discrete_sequence=[PLOTLY_COLORS[0]],
        )
        figure.update_traces(line={"width": 3}, marker={"size": 8})
    elif len(frame) > 1:
        names_col = frame.columns[0]
        values_col = frame.columns[1]
        figure = px.pie(
            frame,
            names=names_col,
            values=values_col,
            hole=0.45,
            color_discrete_sequence=PLOTLY_COLORS,
        )
        figure.update_traces(textposition="inside", textinfo="percent+label")
    else:
        x_col = frame.columns[0]
        y_col = frame.columns[1]
        figure = px.bar(
            frame,
            x=x_col,
            y=y_col,
            color_discrete_sequence=[PLOTLY_COLORS[0]],
        )
        figure.update_traces(marker_line_width=0, width=0.55)

    figure.update_layout(
        margin={"l": 16, "r": 16, "t": 16, "b": 16},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#18202b", "size": 13},
        showlegend=kind != "line",
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.2, "xanchor": "center", "x": 0.5},
    )
    if kind == "line":
        figure.update_xaxes(showgrid=False)
        figure.update_yaxes(showgrid=True, gridcolor="#e5e7eb", zeroline=False)
    elif len(frame) == 1:
        figure.update_xaxes(title=None)
        figure.update_yaxes(title=None, showgrid=True, gridcolor="#e5e7eb", zeroline=False)

    st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def render_chart_box(title: str, data: Any, *, kind: str = "bar") -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if data is None:
            st.info("보여드릴 내용이 아직 없습니다.")
            return
        if isinstance(data, pd.DataFrame):
            if data.empty:
                st.info("보여드릴 내용이 아직 없습니다.")
            else:
                _render_plotly_chart(data, kind=kind)
            return
        st.write(data)
