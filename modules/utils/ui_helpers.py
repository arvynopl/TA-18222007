"""
modules/utils/ui_helpers.py — shared UI components and styling for the CDT system (v6 light theme).

All text is in Bahasa Indonesia (EYD V). The palette is tuned for a white
background with WCAG AA contrast against #FFFFFF.
"""
from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ---------------------------------------------------------------------------
# Color constants (v6 — light theme, WCAG AA on #FFFFFF)
# ---------------------------------------------------------------------------

# Financial palette tuned for contrast on a white background.
COLOR_GAIN = "#0F9D58"       # Deeper green
COLOR_LOSS = "#D93025"       # Deeper red
COLOR_NEUTRAL = "#5F6368"
COLOR_ACCENT = "#2563EB"     # Primary brand blue

SEVERITY_COLORS = {
    "none": "#0F9D58",
    "mild": "#2563EB",
    "moderate": "#E37400",
    "severe": "#C5221F",
}

SEVERITY_BG = {
    "none": "rgba(15, 157, 88, 0.08)",
    "mild": "rgba(37, 99, 235, 0.08)",
    "moderate": "rgba(227, 116, 0, 0.10)",
    "severe": "rgba(197, 34, 31, 0.10)",
}

# Chart theme (light background)
CHART_BG = "rgba(0,0,0,0)"
CHART_GRID = "rgba(0,0,0,0.08)"
CHART_TEXT = "#4A4A4A"
CHART_TITLE = "#1C1E21"

# Severity labels (Bahasa Indonesia EYD V)
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
    "overconfidence": "Bias Keyakinan Berlebih",
    "loss_aversion": "Kecenderungan Menghindari Kerugian",
}

BIAS_DESCRIPTIONS = {
    "disposition_effect": (
        "Kecenderungan menjual saham yang sedang untung terlalu cepat dan "
        "menahan saham rugi terlalu lama."
    ),
    "overconfidence": (
        "Terlalu sering melakukan transaksi dengan hasil yang kurang optimal."
    ),
    "loss_aversion": (
        "Menahan posisi merugi secara tidak proporsional lebih lama "
        "dibandingkan posisi untung."
    ),
}


# ---------------------------------------------------------------------------
# Top navigation (v6)
# ---------------------------------------------------------------------------

NAV_ITEMS = [
    ("Beranda", "Beranda"),
    ("Simulasi Investasi", "Simulasi Investasi"),
    ("Hasil Analisis & Umpan Balik", "Hasil Analisis & Umpan Balik"),
    ("Profil Kognitif Saya", "Profil Kognitif Saya"),
]

# Pre-measured minimum width accommodates the longest label in bold:
# "Hasil Analisis & Umpan Balik" at font-weight 700, ~14px sans-serif.
_NAV_MIN_WIDTH_PX = 240


def render_top_nav(current: str, enabled_map: dict) -> str:
    """Render the horizontal top navigation and return the label clicked (if any).

    Cards are pre-sized to their bold/active width so the layout doesn't
    reflow when the active page changes — see min-width calibration above.
    """
    st.markdown(
        f"""
        <style>
          .cdt-nav-wrap {{
              display:flex; gap:8px; margin:0 0 18px 0;
              border-bottom:1px solid #E5E7EB; padding-bottom:10px;
          }}
          .stButton > button.cdt-nav-btn {{
              min-width: {_NAV_MIN_WIDTH_PX}px;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(len(NAV_ITEMS))
    clicked: str | None = None
    for (label, key), col in zip(NAV_ITEMS, cols):
        with col:
            is_active = (current == label)
            enabled = enabled_map.get(label, True)
            btn_label = f"**{label}**" if is_active else label
            if enabled:
                if st.button(
                    btn_label,
                    key=f"cdt_nav_{key}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    clicked = label
            else:
                st.caption(f"🔒 {label}")
    return clicked or current


def render_mobile_banner() -> None:
    """Show a single-line banner on mobile viewports (<768px)."""
    st.markdown(
        """
        <style>
        @media (max-width: 768px) {
            .cdt-mobile-warn { display:block !important; }
        }
        .cdt-mobile-warn { display:none;
            background:#FEF3C7; color:#92400E; padding:12px 16px;
            border-radius:8px; margin-bottom:16px; font-size:14px;
            border:1px solid #FDE68A;
        }
        </style>
        <div class="cdt-mobile-warn">
            Untuk pengalaman optimal, gunakan perangkat berlayar ≥10 inci
            (laptop, PC, atau tablet).
        </div>
        """,
        unsafe_allow_html=True,
    )


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
# Plotly chart theme
# ---------------------------------------------------------------------------

def apply_chart_theme(fig: go.Figure, height: int = 400) -> go.Figure:
    """Apply the consistent v6 light-theme styling to a Plotly figure."""
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
            font=dict(size=11, color=CHART_TEXT),
        ),
        xaxis_rangeslider_visible=False,
    )
    return fig


def build_severity_gauge(value: float, max_val: float, label: str, severity: str) -> go.Figure:
    """Build a semicircular gauge chart for a single bias metric (light theme)."""
    color = SEVERITY_COLORS.get(severity, COLOR_NEUTRAL)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number=dict(font=dict(size=28, color=CHART_TITLE), valueformat=".2f"),
        title=dict(text=label, font=dict(size=14, color=CHART_TEXT)),
        gauge=dict(
            axis=dict(range=[0, max_val], tickcolor=CHART_TEXT),
            bar=dict(color=color),
            bgcolor="rgba(0,0,0,0.03)",
            borderwidth=0,
            steps=[
                dict(range=[0, max_val * 0.25], color="rgba(15,157,88,0.10)"),
                dict(range=[max_val * 0.25, max_val * 0.5], color="rgba(37,99,235,0.10)"),
                dict(range=[max_val * 0.5, max_val * 0.75], color="rgba(227,116,0,0.10)"),
                dict(range=[max_val * 0.75, max_val], color="rgba(197,34,31,0.10)"),
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
    """Build a radar chart for the CDT bias intensity vector (light theme)."""
    categories = [
        BIAS_NAMES["overconfidence"],
        BIAS_NAMES["disposition_effect"],
        BIAS_NAMES["loss_aversion"],
    ]
    vals = [
        values.get("overconfidence", 0.0),
        values.get("disposition", 0.0),
        values.get("loss_aversion", 0.0),
    ]
    vals_closed = vals + [vals[0]]
    cats_closed = categories + [categories[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals_closed,
        theta=cats_closed,
        fill="toself",
        fillcolor="rgba(37, 99, 235, 0.18)",
        line=dict(color=COLOR_ACCENT, width=2),
        name="Intensitas Bias",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                gridcolor=CHART_GRID,
                tickfont=dict(size=10, color=CHART_TEXT),
            ),
            angularaxis=dict(
                tickfont=dict(size=12, color=CHART_TITLE),
                gridcolor=CHART_GRID,
            ),
            bgcolor=CHART_BG,
        ),
        showlegend=False,
        title=dict(text=title, font=dict(size=16, color=CHART_TITLE)),
        height=350,
        margin=dict(l=60, r=60, t=60, b=30),
        paper_bgcolor=CHART_BG,
    )
    return fig


# ---------------------------------------------------------------------------
# Dual-ring radar (v6 Phase 4)
# ---------------------------------------------------------------------------

def _normalised_scientific_thresholds() -> dict:
    """Severe thresholds from config.py, normalised to the shared [0, 1] axis.

    - DEI severe = 0.50 (already in 0–1)
    - OCS severe = 0.70 (already in 0–1)
    - LAI severe = 2.00 normalised by LAI_EMA_CEILING (e.g. 3.0 → 0.667)
    """
    from config import DEI_SEVERE, OCS_SEVERE, LAI_SEVERE, LAI_EMA_CEILING
    return {
        "dei": float(DEI_SEVERE),
        "ocs": float(OCS_SEVERE),
        "lai": min(float(LAI_SEVERE) / float(LAI_EMA_CEILING), 1.0),
    }


def build_dual_radar_chart(
    current_scores: dict,
    avg_scores: dict,
    personal_thresholds: dict | None = None,
    personal_threshold_is_fallback: bool = False,
) -> go.Figure:
    """Build a dual-trace radar with two reference rings:

    1. **Titik Waspada Ilmiah** — severe thresholds from config (literature).
    2. **Titik Waspada Pribadi** — ``personal_thresholds`` dict (μ + 1σ);
       falls back to scientific thresholds when ``personal_threshold_is_fallback``
       is True (e.g., session_count < 3).

    Both ``current_scores`` and ``avg_scores`` are dicts keyed ``dei/ocs/lai``
    in [0, 1].
    """
    categories = [
        "Efek Disposisi (DEI)",
        "Bias Keyakinan Berlebih (OCS)",
        "Menghindari Kerugian (LAI)",
    ]

    def _vec(scores: dict) -> list[float]:
        return [
            float(scores.get("dei", 0.0)),
            float(scores.get("ocs", 0.0)),
            float(scores.get("lai", 0.0)),
        ]

    current_vals = _vec(current_scores)
    avg_vals = _vec(avg_scores)
    cats_closed = categories + [categories[0]]
    current_closed = current_vals + [current_vals[0]]
    avg_closed = avg_vals + [avg_vals[0]]

    sci = _normalised_scientific_thresholds()
    sci_closed = [sci["dei"], sci["ocs"], sci["lai"], sci["dei"]]

    personal_thresholds = personal_thresholds or sci
    pers_closed = [
        float(personal_thresholds.get("dei", sci["dei"])),
        float(personal_thresholds.get("ocs", sci["ocs"])),
        float(personal_thresholds.get("lai", sci["lai"])),
    ]
    pers_closed += [pers_closed[0]]
    pers_label = (
        "Titik Waspada Pribadi (data belum cukup)"
        if personal_threshold_is_fallback
        else "Titik Waspada Pribadi"
    )

    fig = go.Figure()

    # Scientific watchpoint — severe thresholds from literature (solid outline)
    fig.add_trace(go.Scatterpolar(
        r=sci_closed,
        theta=cats_closed,
        mode="lines",
        line=dict(color="rgba(197, 34, 31, 0.55)", width=1.5),
        name="Titik Waspada Ilmiah",
        showlegend=True,
        hovertemplate=(
            "<b>Ambang berat (literatur)</b><br>"
            "%{theta}: %{r:.2f}<extra></extra>"
        ),
    ))

    # Personal watchpoint — user's μ + 1σ, per bias (dashed outline)
    fig.add_trace(go.Scatterpolar(
        r=pers_closed,
        theta=cats_closed,
        mode="lines",
        line=dict(color="rgba(37, 99, 235, 0.55)", width=1.5, dash="dash"),
        name=pers_label,
        showlegend=True,
        hovertemplate=(
            "<b>Ambang pribadi (rerata + 1 deviasi standar)</b><br>"
            "%{theta}: %{r:.2f}<extra></extra>"
        ),
    ))

    # Session average trace
    fig.add_trace(go.Scatterpolar(
        r=avg_closed,
        theta=cats_closed,
        mode="lines+markers",
        line=dict(color=SEVERITY_COLORS["moderate"], width=2, dash="dot"),
        marker=dict(size=6, color=SEVERITY_COLORS["moderate"]),
        name="Rata-rata Anda",
        showlegend=True,
    ))

    # Current session trace (solid blue, semi-transparent fill)
    fig.add_trace(go.Scatterpolar(
        r=current_closed,
        theta=cats_closed,
        fill="toself",
        fillcolor="rgba(37, 99, 235, 0.16)",
        line=dict(color=COLOR_ACCENT, width=2),
        marker=dict(size=7, color=COLOR_ACCENT),
        name="Sesi Ini",
        showlegend=True,
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 1],
                gridcolor=CHART_GRID,
                tickfont=dict(size=10, color=CHART_TEXT),
            ),
            angularaxis=dict(
                tickfont=dict(size=12, color=CHART_TITLE),
                gridcolor=CHART_GRID,
            ),
            bgcolor=CHART_BG,
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.32,
            xanchor="center",
            x=0.5,
            font=dict(size=11, color=CHART_TEXT),
        ),
        title=dict(
            text="Radar Bias: Sesi Ini, Rata-rata, dan Titik Waspada",
            font=dict(size=16, color=CHART_TITLE),
        ),
        height=440,
        margin=dict(l=60, r=60, t=70, b=90),
        paper_bgcolor=CHART_BG,
    )
    return fig


# ---------------------------------------------------------------------------
# Custom CSS injection (v6 — light theme)
# ---------------------------------------------------------------------------

def inject_custom_css() -> None:
    """Inject the v6 light-theme CSS polish."""
    st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }

    /* Metric cards — equal-height baseline (v6 Phase 2 card consistency) */
    [data-testid="stMetric"] {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 16px 20px;
        min-height: 140px;
    }

    [data-testid="stMetricValue"] {
        font-size: 24px;
        font-weight: 600;
        color: #1C1E21;
    }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 16px; }

    /* Expanders */
    .streamlit-expanderHeader { font-size: 16px; font-weight: 500; }

    /* Buttons */
    .stButton > button[kind="primary"] {
        border-radius: 8px;
        font-weight: 500;
        padding: 12px 24px;
    }
    .stButton > button[kind="secondary"] {
        border-radius: 8px;
        background: #FFFFFF;
        color: #1F2937;
        border: 1px solid #E5E7EB;
    }
    .stButton > button[kind="secondary"]:hover {
        background: #F3F4F6;
        color: #111827;
    }

    /* Forms */
    [data-testid="stForm"] {
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 16px;
        background: #FFFFFF;
    }

    hr { border-color: #E5E7EB; }

    /* Uniform card helper (Phase 2 item #3) */
    .cdt-card {
        min-height: 180px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Coach-mark onboarding (kept; palette refreshed for light theme)
# ---------------------------------------------------------------------------

def render_coach_mark_onboarding() -> bool:
    """Three-step coach-mark sequence shown once before the first simulation."""
    if st.session_state.get("onboarding_shown", False):
        return True

    step: int = st.session_state.get("onboarding_step", 1)

    _STEPS = [
        {
            "title": "Cara Membaca Grafik",
            "body": (
                "Grafik menampilkan harga historis saham selama 14 hari. "
                "Garis oranye adalah MA5, garis hijau adalah MA20. "
                "Anda tidak perlu menganalisis grafik secara teknis — "
                "cukup ambil keputusan berdasarkan intuisi Anda."
            ),
            "btn": "Lanjut →",
        },
        {
            "title": "Cara Melakukan Transaksi",
            "body": (
                "Gunakan tombol Beli atau Jual di bawah setiap saham. "
                "Anda dapat memilih berapa lembar yang ingin dibeli. "
                "Tidak setiap saham harus diperdagangkan."
            ),
            "btn": "Lanjut →",
        },
        {
            "title": "Tentang Simulasi Ini",
            "body": (
                "Simulasi ini menggunakan data harga saham IDX historis. "
                "Tujuannya bukan menguji kemampuan analisis Anda, "
                "melainkan memahami pola pengambilan keputusan Anda secara alami."
            ),
            "btn": "Mulai Simulasi ✓",
        },
    ]

    n_steps = len(_STEPS)
    current = _STEPS[step - 1]

    st.markdown("""
    <style>
    .cdt-coach-card {
        background: rgba(37, 99, 235, 0.05);
        border: 1px solid rgba(37, 99, 235, 0.25);
        border-radius: 14px;
        padding: 32px 36px;
        margin: 16px 0 20px 0;
    }
    .cdt-coach-stepper {
        font-size: 11px; font-weight: 700; letter-spacing: 1.8px;
        text-transform: uppercase; color: #2563EB; margin-bottom: 8px;
    }
    .cdt-coach-title {
        font-size: 21px; font-weight: 700; color: #111827; margin-bottom: 14px;
    }
    .cdt-coach-body {
        font-size: 15px; color: #4B5563; line-height: 1.75;
    }
    .cdt-coach-dots { display: flex; gap: 8px; margin-top: 24px; }
    .cdt-coach-dot, .cdt-coach-dot-on {
        width: 8px; height: 8px; border-radius: 50%; display: inline-block;
    }
    .cdt-coach-dot { background: rgba(37, 99, 235, 0.25); }
    .cdt-coach-dot-on { background: #2563EB; }
    </style>
    """, unsafe_allow_html=True)

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
                st.session_state["onboarding_shown"] = True
                st.session_state.pop("onboarding_step", None)
            st.rerun()

    return False
