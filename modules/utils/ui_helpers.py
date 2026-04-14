"""
modules/utils/ui_helpers.py — Shared UI components and styling for the CDT system.

Provides consistent formatting, card rendering, and chart helpers
used across all pages. All user-facing text in Bahasa Indonesia.
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ---------------------------------------------------------------------------
# Color Constants (Financial + Cognitive Psychology palette)
# ---------------------------------------------------------------------------

# Trading colors
COLOR_GAIN = "#26a69a"          # Teal-green (calmer than bright green)
COLOR_LOSS = "#ef5350"          # Soft red (less aggressive than #FF0000)
COLOR_NEUTRAL = "#78909c"       # Blue-gray
COLOR_ACCENT = "#4A90E2"        # Soft blue (trust, calm)

# Severity colors (progressive, non-threatening)
SEVERITY_COLORS = {
    "none": "#52C41A",       # Soft green
    "mild": "#4A90E2",       # Blue (not alarming)
    "moderate": "#F5A623",   # Warm amber
    "severe": "#E8553A",     # Deep orange-red (not bright red)
}

SEVERITY_BG = {
    "none": "rgba(82, 196, 26, 0.1)",
    "mild": "rgba(74, 144, 226, 0.1)",
    "moderate": "rgba(245, 166, 35, 0.1)",
    "severe": "rgba(232, 85, 58, 0.1)",
}

# Chart theme
CHART_BG = "rgba(0,0,0,0)"
CHART_GRID = "rgba(255,255,255,0.08)"
CHART_TEXT = "#B0BEC5"

# Severity labels (Bahasa Indonesia)
SEVERITY_LABELS = {
    "none": "Tidak Terdeteksi",
    "mild": "Ringan",
    "moderate": "Sedang",
    "severe": "Berat",
}

SEVERITY_ICONS = {
    "none": "✅",
    "mild": "💡",
    "moderate": "⚠️",
    "severe": "🔶",
}

BIAS_NAMES = {
    "disposition_effect": "Efek Disposisi",
    "overconfidence": "Overconfidence",
    "loss_aversion": "Loss Aversion",
}

BIAS_DESCRIPTIONS = {
    "disposition_effect": "Kecenderungan menjual saham untung terlalu cepat dan menahan saham rugi terlalu lama",
    "overconfidence": "Terlalu sering melakukan trading dengan hasil yang kurang optimal",
    "loss_aversion": "Menahan posisi merugi lebih lama secara tidak proporsional",
}


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def format_rupiah(value: float) -> str:
    """Format float as Indonesian Rupiah."""
    return f"Rp {value:,.0f}"


def format_pct(value: float, decimals: int = 1) -> str:
    """Format float as percentage with sign."""
    return f"{value:+.{decimals}f}%"


def format_severity_badge(severity: str) -> str:
    """Return an icon+label badge string for a severity level."""
    icon = SEVERITY_ICONS.get(severity, "⚪")
    label = SEVERITY_LABELS.get(severity, severity.capitalize())
    return f"{icon} {label}"


# ---------------------------------------------------------------------------
# Plotly Chart Theme
# ---------------------------------------------------------------------------

def apply_chart_theme(fig: go.Figure, height: int = 400) -> go.Figure:
    """Apply consistent dark financial theme to any Plotly figure."""
    fig.update_layout(
        height=height,
        plot_bgcolor=CHART_BG,
        paper_bgcolor=CHART_BG,
        font=dict(color=CHART_TEXT, size=12),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(gridcolor=CHART_GRID, zeroline=False),
        yaxis=dict(gridcolor=CHART_GRID, zeroline=False),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5,
            font=dict(size=11),
        ),
        xaxis_rangeslider_visible=False,
    )
    return fig


def build_severity_gauge(value: float, max_val: float, label: str, severity: str) -> go.Figure:
    """Build a semicircular gauge chart for a single bias metric."""
    color = SEVERITY_COLORS.get(severity, COLOR_NEUTRAL)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(font=dict(size=28, color="white"), valueformat=".2f"),
        title=dict(text=label, font=dict(size=14, color=CHART_TEXT)),
        gauge=dict(
            axis=dict(range=[0, max_val], tickcolor=CHART_TEXT),
            bar=dict(color=color),
            bgcolor="rgba(255,255,255,0.05)",
            borderwidth=0,
            steps=[
                dict(range=[0, max_val * 0.25], color="rgba(82,196,26,0.15)"),
                dict(range=[max_val * 0.25, max_val * 0.5], color="rgba(74,144,226,0.15)"),
                dict(range=[max_val * 0.5, max_val * 0.75], color="rgba(245,166,35,0.15)"),
                dict(range=[max_val * 0.75, max_val], color="rgba(232,85,58,0.15)"),
            ],
        ),
    ))
    fig.update_layout(
        height=200,
        margin=dict(l=20, r=20, t=50, b=10),
        paper_bgcolor=CHART_BG,
        font=dict(color=CHART_TEXT),
    )
    return fig


def build_radar_chart(values: dict, title: str = "Profil Bias") -> go.Figure:
    """Build a radar/spider chart for the CDT bias intensity vector.

    Args:
        values: Dict with keys 'overconfidence', 'disposition', 'loss_aversion'.
        title: Chart title.
    """
    categories = ["Overconfidence", "Efek Disposisi", "Loss Aversion"]
    vals = [
        values.get("overconfidence", 0.0),
        values.get("disposition", 0.0),
        values.get("loss_aversion", 0.0),
    ]
    vals_closed = vals + [vals[0]]
    cats_closed = categories + [categories[0]]

    fig = go.Figure()
    # Fill area
    fig.add_trace(go.Scatterpolar(
        r=vals_closed,
        theta=cats_closed,
        fill="toself",
        fillcolor="rgba(74, 144, 226, 0.2)",
        line=dict(color=COLOR_ACCENT, width=2),
        name="Intensitas Bias",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                gridcolor="rgba(255,255,255,0.1)",
                tickfont=dict(size=10, color=CHART_TEXT),
            ),
            angularaxis=dict(
                tickfont=dict(size=12, color="white"),
                gridcolor="rgba(255,255,255,0.1)",
            ),
            bgcolor=CHART_BG,
        ),
        showlegend=False,
        title=dict(text=title, font=dict(size=16, color="white")),
        height=350,
        margin=dict(l=60, r=60, t=60, b=30),
        paper_bgcolor=CHART_BG,
    )
    return fig


# ---------------------------------------------------------------------------
# Custom CSS Injection
# ---------------------------------------------------------------------------

def inject_custom_css() -> None:
    """Inject custom CSS to polish Streamlit's default styling."""
    st.markdown("""
    <style>
    /* Smoother fonts */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 12px;
        padding: 16px 20px;
    }

    [data-testid="stMetricValue"] {
        font-size: 24px;
        font-weight: 600;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 8px 16px;
    }

    /* Expanders */
    .streamlit-expanderHeader {
        font-size: 16px;
        font-weight: 500;
    }

    /* Buttons */
    .stButton > button[kind="primary"] {
        border-radius: 8px;
        font-weight: 500;
        padding: 12px 24px;
    }

    /* Progress bar */
    .stProgress > div > div {
        border-radius: 8px;
    }

    /* Forms */
    [data-testid="stForm"] {
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px;
    }

    /* Dividers - more subtle */
    hr {
        border-color: rgba(255, 255, 255, 0.06);
    }

    /* Sidebar refinement */
    [data-testid="stSidebar"] {
        background: #0D1117;
    }

    [data-testid="stSidebar"] .stRadio label {
        padding: 8px 12px;
        border-radius: 8px;
        transition: background 0.2s;
    }

    [data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(74, 144, 226, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Coach-Mark Onboarding (first session only)
# ---------------------------------------------------------------------------

def render_coach_mark_onboarding() -> bool:
    """Render a 3-step coach-mark onboarding sequence, shown on first session only.

    Call this at the top of the simulation page before any other simulation UI.
    The sequence is gated on st.session_state["onboarding_shown"]: once the user
    clicks "Mulai Simulasi" on step 3, that flag is set to True and is never shown
    again.

    Returns:
        True  — onboarding is already done (or just completed); caller may proceed.
        False — onboarding step is being displayed; caller should return immediately.
    """
    if st.session_state.get("onboarding_shown", False):
        return True

    step: int = st.session_state.get("onboarding_step", 1)

    _STEPS = [
        {
            "title": "Cara Membaca Grafik",
            "body": (
                "Grafik menampilkan harga historis saham selama 14 hari. "
                "Garis biru = MA5, garis merah = MA20. "
                "Anda tidak perlu menganalisis grafik secara teknis — "
                "cukup putuskan berdasarkan intuisi Anda."
            ),
            "btn": "Lanjut →",
        },
        {
            "title": "Cara Melakukan Transaksi",
            "body": (
                "Gunakan tombol Beli / Jual di bawah setiap saham. "
                "Anda dapat memilih berapa saham yang ingin dibeli. "
                "Tidak semua saham harus diperdagangkan."
            ),
            "btn": "Lanjut →",
        },
        {
            "title": "Tentang Simulasi Ini",
            "body": (
                "Simulasi ini menggunakan data harga saham IDX historis nyata. "
                "Tujuannya bukan untuk menguji kemampuan analisis Anda, "
                "melainkan untuk memahami pola pengambilan keputusan Anda secara alami."
            ),
            "btn": "Mulai Simulasi ✓",
        },
    ]

    n_steps = len(_STEPS)
    current = _STEPS[step - 1]

    # CSS — prefixed with cdt-coach- to avoid collisions with other page styles
    st.markdown("""
    <style>
    .cdt-coach-card {
        background: rgba(74, 144, 226, 0.06);
        border: 1px solid rgba(74, 144, 226, 0.30);
        border-radius: 14px;
        padding: 32px 36px;
        margin: 16px 0 20px 0;
    }
    .cdt-coach-stepper {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.8px;
        text-transform: uppercase;
        color: #4A90E2;
        margin-bottom: 8px;
    }
    .cdt-coach-title {
        font-size: 21px;
        font-weight: 700;
        color: #FFFFFF;
        margin-bottom: 14px;
    }
    .cdt-coach-body {
        font-size: 15px;
        color: #B0BEC5;
        line-height: 1.75;
    }
    .cdt-coach-dots {
        display: flex;
        gap: 8px;
        margin-top: 24px;
    }
    .cdt-coach-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: rgba(74, 144, 226, 0.25);
        display: inline-block;
    }
    .cdt-coach-dot-on {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #4A90E2;
        display: inline-block;
    }
    </style>
    """, unsafe_allow_html=True)

    # Progress dots: active step uses cdt-coach-dot-on, others use cdt-coach-dot
    dots_html = "".join(
        f'<span class="cdt-coach-dot{"-on" if i + 1 == step else ""}"></span>'
        for i in range(n_steps)
    )

    st.markdown(f"""
    <div class="cdt-coach-card">
        <div class="cdt-coach-stepper">LANGKAH {step} DARI {n_steps}</div>
        <div class="cdt-coach-title">{current["title"]}</div>
        <div class="cdt-coach-body">{current["body"]}</div>
        <div class="cdt-coach-dots">{dots_html}</div>
    </div>
    """, unsafe_allow_html=True)

    # Button right-aligned via columns
    _, btn_col = st.columns([2, 1])
    with btn_col:
        if st.button(
            current["btn"],
            type="primary",
            use_container_width=True,
            key=f"cdt_coach_btn_{step}",
        ):
            if step < n_steps:
                st.session_state["onboarding_step"] = step + 1
            else:
                # Final step — mark onboarding complete
                st.session_state["onboarding_shown"] = True
                st.session_state.pop("onboarding_step", None)
            st.rerun()

    return False
