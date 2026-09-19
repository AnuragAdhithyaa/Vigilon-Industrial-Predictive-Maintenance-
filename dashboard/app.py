"""
vigilon/dashboard/app.py
Vigilon Live Monitoring Dashboard — 3D industrial dark theme.
Run with:  streamlit run dashboard/app.py

Original features PRESERVED + NEW additions:
  NEW ► 3D WebGL-style network topology (canvas-based, embedded via HTML component)
  NEW ► Per-client health radar chart (Plotly)
  NEW ► Convergence heatmap (client × round accuracy grid)
  NEW ► Per-layer attack detection panel (Z-score per layer)
  NEW ► LR schedule display + convergence threshold indicator
  NEW ► Delta-weight communication savings metric
  NEW ► Early-stop indicator when convergence threshold hit
"""

import streamlit as st
import json
import time
import random
import math
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="VIGILON — Federated Intelligence",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 3D Industrial CSS (ALL ORIGINAL STYLES PRESERVED) ─────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700&family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&display=swap');

/* ── Root palette ── */
:root {
  --bg-deep:      #020c14;
  --bg-panel:     #04141f;
  --bg-card:      #061a28;
  --border-glow:  #00d4ff22;
  --border-crit:  #ff3c3c55;
  --accent-cyan:  #00d4ff;
  --accent-teal:  #00ffb3;
  --accent-warn:  #ffaa00;
  --accent-crit:  #ff3c3c;
  --accent-ok:    #00ffb3;
  --text-primary: #e0f4ff;
  --text-dim:     #4a7a9b;
  --text-mono:    #00d4ff;
  --grid-color:   #0a2a3a;
  --glow-cyan:    0 0 20px #00d4ff44, 0 0 40px #00d4ff22;
  --glow-teal:    0 0 20px #00ffb344, 0 0 40px #00ffb322;
  --glow-warn:    0 0 20px #ffaa0044;
  --glow-crit:    0 0 20px #ff3c3c66, 0 0 40px #ff3c3c33;
}

/* ── Global reset ── */
html, body, [class*="css"] {
  font-family: 'Rajdhani', sans-serif !important;
  background-color: var(--bg-deep) !important;
  color: var(--text-primary) !important;
}

.stApp { background: var(--bg-deep) !important; }

/* ── Animated hex grid background ── */
.stApp::before {
  content: '';
  position: fixed;
  inset: 0;
  background-image:
    repeating-linear-gradient(0deg,   transparent, transparent 39px, var(--grid-color) 40px),
    repeating-linear-gradient(90deg,  transparent, transparent 39px, var(--grid-color) 40px);
  opacity: 0.4;
  pointer-events: none;
  z-index: 0;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #030f1a 0%, #020c14 100%) !important;
  border-right: 1px solid var(--border-glow) !important;
}

section[data-testid="stSidebar"] * { color: var(--text-primary) !important; }

/* ── Main header ── */
.vigilon-header {
  text-align: center;
  padding: 1.5rem 0 0.5rem;
  position: relative;
}

.vigilon-logo {
  font-family: 'Orbitron', monospace;
  font-size: 3.2rem;
  font-weight: 900;
  letter-spacing: 0.3em;
  background: linear-gradient(135deg, #00d4ff 0%, #00ffb3 50%, #00d4ff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  text-shadow: none;
  filter: drop-shadow(0 0 20px #00d4ff88);
  animation: pulse-logo 3s ease-in-out infinite;
}

@keyframes pulse-logo {
  0%, 100% { filter: drop-shadow(0 0 20px #00d4ff88); }
  50%       { filter: drop-shadow(0 0 40px #00d4ffcc); }
}

.vigilon-sub {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.75rem;
  letter-spacing: 0.4em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-top: 0.2rem;
}

/* ── 3D Card style ── */
.v-card {
  background: linear-gradient(135deg, #07202f 0%, #04141f 60%, #061a28 100%);
  border: 1px solid var(--border-glow);
  border-radius: 4px;
  padding: 1.2rem 1.4rem;
  position: relative;
  overflow: hidden;
  box-shadow:
    0 4px 6px #00000066,
    0 1px 0 #00d4ff11 inset,
    0 -1px 0 #00000033 inset;
  transition: border-color 0.3s, box-shadow 0.3s;
}

.v-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
  opacity: 0.6;
}

.v-card:hover {
  border-color: #00d4ff44;
  box-shadow: var(--glow-cyan), 0 4px 6px #00000066;
}

.v-card.warn {
  border-color: var(--border-crit);
  box-shadow: var(--glow-warn), 0 4px 6px #00000066;
  animation: warn-pulse 2s ease-in-out infinite;
}

.v-card.crit {
  border-color: #ff3c3c88;
  box-shadow: var(--glow-crit), 0 4px 6px #00000066;
  animation: crit-pulse 1s ease-in-out infinite;
}

@keyframes warn-pulse {
  0%, 100% { box-shadow: var(--glow-warn), 0 4px 6px #00000066; }
  50%       { box-shadow: 0 0 30px #ffaa0066, 0 4px 6px #00000066; }
}

@keyframes crit-pulse {
  0%, 100% { box-shadow: var(--glow-crit), 0 4px 6px #00000066; }
  50%       { box-shadow: 0 0 50px #ff3c3c88, 0 4px 6px #00000066; }
}

/* ── Card label ── */
.v-label {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.65rem;
  letter-spacing: 0.25em;
  color: var(--text-dim);
  text-transform: uppercase;
  margin-bottom: 0.3rem;
}

/* ── Big metric number ── */
.v-metric {
  font-family: 'Orbitron', monospace;
  font-size: 2.4rem;
  font-weight: 700;
  line-height: 1;
  color: var(--accent-cyan);
  text-shadow: var(--glow-cyan);
}

.v-metric.ok   { color: var(--accent-teal); text-shadow: var(--glow-teal); }
.v-metric.warn { color: var(--accent-warn); text-shadow: var(--glow-warn); }
.v-metric.crit { color: var(--accent-crit); text-shadow: var(--glow-crit); }

/* ── Status badge ── */
.v-badge {
  display: inline-block;
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.7rem;
  letter-spacing: 0.15em;
  padding: 0.2rem 0.6rem;
  border-radius: 2px;
  text-transform: uppercase;
  font-weight: 700;
}

.v-badge.ok   { background: #00ffb322; color: var(--accent-teal); border: 1px solid #00ffb344; }
.v-badge.warn { background: #ffaa0022; color: var(--accent-warn); border: 1px solid #ffaa0044; }
.v-badge.crit { background: #ff3c3c22; color: var(--accent-crit); border: 1px solid #ff3c3c44; animation: crit-pulse 1s infinite; }
.v-badge.info { background: #00d4ff11; color: var(--accent-cyan); border: 1px solid #00d4ff33; }

/* ── Section title ── */
.v-section-title {
  font-family: 'Orbitron', monospace;
  font-size: 0.75rem;
  letter-spacing: 0.3em;
  color: var(--accent-cyan);
  text-transform: uppercase;
  border-bottom: 1px solid var(--border-glow);
  padding-bottom: 0.5rem;
  margin-bottom: 1rem;
}

/* ── Progress bars ── */
.v-bar-track {
  background: #0a2a3a;
  border-radius: 2px;
  height: 6px;
  overflow: hidden;
  margin: 0.3rem 0;
  box-shadow: inset 0 1px 3px #00000066;
}

.v-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  background: linear-gradient(90deg, var(--accent-cyan), var(--accent-teal));
  box-shadow: 0 0 8px var(--accent-cyan);
}

.v-bar-fill.ok   { background: linear-gradient(90deg, var(--accent-teal), #00c896); box-shadow: 0 0 8px var(--accent-teal); }
.v-bar-fill.warn { background: linear-gradient(90deg, #ffaa00, #ff7700); box-shadow: 0 0 8px #ffaa00; }
.v-bar-fill.crit { background: linear-gradient(90deg, #ff3c3c, #ff0000); box-shadow: 0 0 8px #ff3c3c; }
.v-bar-fill.info { background: linear-gradient(90deg, var(--accent-cyan), var(--accent-teal)); }

/* ── Factory node ── */
.factory-node {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.7rem 1rem;
  border: 1px solid var(--border-glow);
  border-radius: 3px;
  margin-bottom: 0.5rem;
  background: #04141f;
  transition: all 0.3s;
}

.factory-node:hover { border-color: #00d4ff44; background: #06202f; }

.factory-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.factory-dot.ok      { background: var(--accent-teal); box-shadow: 0 0 8px var(--accent-teal); }
.factory-dot.warn    { background: var(--accent-warn); box-shadow: 0 0 8px var(--accent-warn); animation: dot-blink 1.5s infinite; }
.factory-dot.crit    { background: var(--accent-crit); box-shadow: 0 0 8px var(--accent-crit); animation: dot-blink 0.7s infinite; }
.factory-dot.offline { background: var(--text-dim); }

@keyframes dot-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.2; }
}

/* ── Log entry ── */
.log-entry {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.68rem;
  padding: 0.35rem 0.6rem;
  border-left: 2px solid var(--text-dim);
  margin-bottom: 0.3rem;
  color: #7ab8d4;
  background: #03101a;
  border-radius: 0 2px 2px 0;
}

.log-entry.warn { border-left-color: var(--accent-warn); color: #ffaa00cc; }
.log-entry.crit { border-left-color: var(--accent-crit); color: #ff3c3ccc; }
.log-entry.ok   { border-left-color: var(--accent-teal); color: #00ffb3cc; }

/* ── NEW: Heatmap cell ── */
.heat-row {
  display: flex;
  gap: 2px;
  margin-bottom: 2px;
  align-items: center;
}
.heat-label {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.55rem;
  color: var(--text-dim);
  width: 60px;
  flex-shrink: 0;
  text-align: right;
  padding-right: 6px;
}
.heat-cell {
  height: 18px;
  flex: 1;
  border-radius: 1px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.5rem;
  transition: all 0.3s;
  min-width: 20px;
}

/* ── NEW: Layer attack panel ── */
.layer-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0;
  border-bottom: 1px solid #051520;
}
.layer-name {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.55rem;
  color: var(--text-dim);
  width: 110px;
  flex-shrink: 0;
}
.layer-bar-track {
  flex: 1;
  height: 4px;
  background: #0a2a3a;
  border-radius: 1px;
  overflow: hidden;
}
.layer-bar-fill {
  height: 100%;
  border-radius: 1px;
  transition: width 0.4s;
}
.layer-zscore {
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.55rem;
  width: 40px;
  text-align: right;
  flex-shrink: 0;
}

/* ── Streamlit overrides ── */
div[data-testid="stMetric"]      { background: transparent !important; }
div[data-testid="stMetricValue"] { font-family: 'Orbitron', monospace !important; color: var(--accent-cyan) !important; }
div[data-testid="stMetricLabel"] { font-family: 'Share Tech Mono', monospace !important; color: var(--text-dim) !important; letter-spacing: 0.1em !important; }

.stSelectbox > div > div,
.stSlider > div { background: var(--bg-card) !important; }

button[kind="primary"] {
  background: linear-gradient(135deg, #00d4ff22, #00ffb322) !important;
  border: 1px solid var(--accent-cyan) !important;
  color: var(--accent-cyan) !important;
  font-family: 'Orbitron', monospace !important;
  letter-spacing: 0.1em !important;
}

div[data-testid="stDataFrame"] { border: 1px solid var(--border-glow) !important; }

/* ── Separator ── */
hr { border-color: var(--border-glow) !important; }

/* ── Scan line animation ── */
@keyframes scan {
  0%   { transform: translateY(-100%); opacity: 0; }
  10%  { opacity: 0.05; }
  90%  { opacity: 0.05; }
  100% { transform: translateY(100vh); opacity: 0; }
}

.scan-line {
  position: fixed;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
  animation: scan 4s linear infinite;
  pointer-events: none;
  z-index: 9999;
}
</style>

<div class="scan-line"></div>
""", unsafe_allow_html=True)


# ── Data loading helpers ───────────────────────────────────────────────────────

METRICS_DIR = Path("results/metrics")

@st.cache_data(ttl=2)
def load_global_metrics() -> list[dict]:
    path = METRICS_DIR / "global_metrics.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


@st.cache_data(ttl=2)
def load_round_metas() -> list[dict]:
    metas = []
    if METRICS_DIR.exists():
        for p in sorted(METRICS_DIR.glob("server_round_*.json")):
            with open(p) as f:
                metas.append(json.load(f))
    return metas


def get_latest_round_meta() -> dict:
    metas = load_round_metas()
    return metas[-1] if metas else {}


def get_client_latest(client_id: int) -> dict:
    """Return the most recent eval metrics for a client."""
    if not METRICS_DIR.exists():
        return {}
    files = sorted(METRICS_DIR.glob(f"client_{client_id}_eval_r*.json"))
    if not files:
        return {}
    with open(files[-1]) as f:
        return json.load(f)


# ── Demo data generator (original + extended with per-client data) ─────────────

def generate_demo_metrics(n_rounds: int = 20, n_clients: int = 3,
                           attack: bool = False) -> list[dict]:
    """
    Original generator extended to also return per-client accuracy/loss
    and simulated layer Z-scores for the new panels.
    """
    rows = []
    acc  = 0.52
    for r in range(1, n_rounds + 1):
        random.seed(r * 97)
        acc  = min(acc + random.uniform(0.01, 0.04) * (1 - acc), 0.91)
        loss = max(1.4 - r * 0.05 + random.uniform(-0.02, 0.02), 0.15)

        clients = []
        for c in range(n_clients):
            random.seed(r * 13 + c * 100)
            c_acc  = min(acc + random.uniform(-0.08, 0.06), 1.0)
            c_loss = max(loss + random.uniform(-0.05, 0.1), 0.05)
            poisoned = attack and c == 2 and r >= 4
            if poisoned:
                c_acc  = random.uniform(0.03, 0.08)
                c_loss = random.uniform(2.2, 3.1)
            clients.append({
                "client_id": c,
                "accuracy":  round(c_acc, 4),
                "loss":      round(c_loss, 4),
                "poisoned":  poisoned,
            })

        # Simulated per-layer Z-scores (NEW) — attack client has extreme scores
        layer_zscores = {}
        layer_names = [
            "conv1.weight", "conv1.bn", "conv2.weight", "conv2.bn",
            "fc1.weight", "fc1.bias", "fc2.weight", "fc2.bias"
        ]
        for ln in layer_names:
            random.seed(r * 31 + hash(ln) % 1000)
            zs = [random.gauss(0, 0.4) for _ in range(n_clients)]
            if attack and r >= 4:
                zs[2] = random.uniform(3.2, 6.8)   # client 2 poisoned layer
            layer_zscores[ln] = [round(z, 3) for z in zs]

        # NEW: delta-weight norm (simulated communication savings)
        delta_norm = round(random.uniform(0.8, 2.5) * (1 - r / (n_rounds * 2)), 4)

        # NEW: convergence delta (difference in accuracy from last round)
        prev_acc = rows[-1]["accuracy"] if rows else 0.0
        conv_delta = round(abs(acc - prev_acc), 5)

        rows.append({
            "round":        r,
            "accuracy":     round(acc, 4),
            "loss":         round(loss, 4),
            "clients":      clients,
            "layer_zscores": layer_zscores,
            "delta_norm":   delta_norm,
            "conv_delta":   conv_delta,
            "timestamp":    (datetime.now() - timedelta(seconds=(n_rounds - r) * 45)).isoformat(),
            "attack_detected": attack and r == 4,
        })
    return rows


# ── Sidebar (ALL ORIGINAL CONTROLS PRESERVED) ─────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 1rem 0 0.5rem;'>
      <div style='font-family:Orbitron,monospace; font-size:1.3rem; font-weight:900;
                  background: linear-gradient(135deg,#00d4ff,#00ffb3);
                  -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                  letter-spacing:0.2em;'>
        VIGILON
      </div>
      <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                  color:#4a7a9b; letter-spacing:0.3em; margin-top:0.2rem;'>
        FEDERATED INTELLIGENCE
      </div>
    </div>
    <hr style='border-color:#00d4ff22; margin:0.5rem 0 1rem;'/>
    """, unsafe_allow_html=True)

    st.markdown('<div class="v-section-title">⬡ System Config</div>', unsafe_allow_html=True)

    num_clients   = st.slider("Factory Nodes", 2, 5, 3)
    num_rounds    = st.slider("Total Rounds",  5, 30, 20)
    aggregation   = st.selectbox("Aggregation", ["FedMedian (Robust)", "FedAvg"])
    attack_mode   = st.toggle("🔴 Simulate Attack", value=False)
    dp_mode       = st.toggle("🔒 Differential Privacy", value=True)

    st.markdown('<hr style="border-color:#00d4ff22; margin:1rem 0;"/>', unsafe_allow_html=True)
    st.markdown('<div class="v-section-title">⬡ Live Feed</div>', unsafe_allow_html=True)
    auto_refresh  = st.toggle("Auto Refresh (2s)", value=True)
    demo_mode     = st.toggle("Demo Mode (Simulated)", value=True)

    # NEW: convergence threshold slider
    st.markdown('<hr style="border-color:#00d4ff22; margin:1rem 0;"/>', unsafe_allow_html=True)
    st.markdown('<div class="v-section-title">⬡ NEW — Convergence</div>', unsafe_allow_html=True)
    conv_threshold = st.slider("Convergence Threshold", 0.001, 0.02, 0.005, 0.001,
                                help="Early-stop if accuracy delta drops below this value")
    show_heatmap   = st.toggle("Show Convergence Heatmap", value=True)
    show_radar     = st.toggle("Show Client Radar Chart", value=True)
    show_topology  = st.toggle("Show 3D Network Topology", value=True)
    show_layers    = st.toggle("Show Layer Attack Panel", value=True)

    st.markdown('<hr style="border-color:#00d4ff22; margin:1rem 0;"/>', unsafe_allow_html=True)
    st.markdown("""
    <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                color:#4a7a9b; text-align:center; line-height:1.8;'>
      SERVER: localhost:8080<br/>
      PROTOCOL: gRPC / Flower<br/>
      PRIVACY: ε = 1.0<br/>
      BUILT BY: ADHITHYAA A
    </div>
    """, unsafe_allow_html=True)


# ── Load / generate metrics ────────────────────────────────────────────────────

if demo_mode:
    cache_key = f"{num_rounds}_{num_clients}_{attack_mode}"
    if ("demo_round" not in st.session_state or
            st.session_state.get("demo_cache_key") != cache_key):
        st.session_state.demo_round     = 0
        st.session_state.demo_full      = generate_demo_metrics(
            num_rounds, num_clients, attack_mode)
        st.session_state.demo_cache_key = cache_key

    if auto_refresh and st.session_state.demo_round < num_rounds:
        st.session_state.demo_round = min(
            st.session_state.demo_round + 1, num_rounds
        )

    metrics_history = st.session_state.demo_full[:st.session_state.demo_round]
    current_round   = st.session_state.demo_round
else:
    metrics_history = load_global_metrics()
    current_round   = len(metrics_history)

latest         = metrics_history[-1] if metrics_history else {"accuracy": 0, "loss": 0, "round": 0}
attack_detected = attack_mode and current_round > 3

# NEW: convergence early-stop check
converged = False
if len(metrics_history) >= 3:
    recent_deltas = [metrics_history[i]["conv_delta"]
                     for i in range(-3, 0) if "conv_delta" in metrics_history[i]]
    if recent_deltas and all(d < conv_threshold for d in recent_deltas):
        converged = True


# ── Header (ORIGINAL) ─────────────────────────────────────────────────────────

st.markdown("""
<div class="vigilon-header">
  <div class="vigilon-logo">VIGILON</div>
  <div class="vigilon-sub">Secure Self-Evolving Industrial Intelligence Network</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br/>", unsafe_allow_html=True)

# Status bar (ORIGINAL + NEW badges)
attack_html = (
    '<span class="v-badge crit">⚠ ATTACK DETECTED</span>' if attack_detected
    else '<span class="v-badge ok">● SECURE</span>'
)
agg_label = "MEDIAN" if "Median" in aggregation else "FEDAVG"
dp_html   = '<span class="v-badge info">🔒 DP ACTIVE ε=1.0</span>' if dp_mode else ""
conv_html = '<span class="v-badge warn">⬡ CONVERGED — EARLY STOP</span>' if converged else ""

st.markdown(f"""
<div style='display:flex; gap:0.8rem; align-items:center; justify-content:center;
            flex-wrap:wrap; margin-bottom:1.5rem;'>
  <span class="v-badge info">ROUND {current_round}/{num_rounds}</span>
  <span class="v-badge info">AGG: {agg_label}</span>
  <span class="v-badge info">NODES: {num_clients}</span>
  {attack_html}
  {dp_html}
  {conv_html}
  <span class="v-badge info">⏱ {datetime.now().strftime('%H:%M:%S')}</span>
</div>
""", unsafe_allow_html=True)


# ── Top KPI row (ORIGINAL 4 cards + NEW 2 cards) ──────────────────────────────

k1, k2, k3, k4, k5, k6 = st.columns(6)

acc_val  = latest.get("accuracy", 0)
loss_val = latest.get("loss", 0)
acc_pct  = f"{acc_val*100:.1f}%"
acc_cls  = "ok" if acc_val >= 0.83 else ("warn" if acc_val >= 0.6 else "crit")
loss_cls = "ok" if loss_val < 0.4  else ("warn" if loss_val < 0.9  else "crit")

with k1:
    st.markdown(f"""
    <div class="v-card">
      <div class="v-label">Global Accuracy</div>
      <div class="v-metric {acc_cls}">{acc_pct}</div>
      <div style='margin-top:0.5rem;'>
        <div class="v-bar-track">
          <div class="v-bar-fill {acc_cls}" style='width:{acc_val*100:.1f}%;'></div>
        </div>
      </div>
      <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                  color:#4a7a9b; margin-top:0.3rem;'>TARGET: ≥85%</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="v-card">
      <div class="v-label">Global Loss</div>
      <div class="v-metric {loss_cls}">{loss_val:.4f}</div>
      <div style='margin-top:0.5rem;'>
        <div class="v-bar-track">
          <div class="v-bar-fill {loss_cls}" style='width:{min(loss_val/2,1)*100:.1f}%;'></div>
        </div>
      </div>
      <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                  color:#4a7a9b; margin-top:0.3rem;'>CROSS-ENTROPY</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    progress_pct = (current_round / max(num_rounds, 1)) * 100
    st.markdown(f"""
    <div class="v-card">
      <div class="v-label">Training Progress</div>
      <div class="v-metric">{current_round}<span style='font-size:1rem;color:#4a7a9b;'>/{num_rounds}</span></div>
      <div style='margin-top:0.5rem;'>
        <div class="v-bar-track">
          <div class="v-bar-fill" style='width:{progress_pct:.1f}%;'></div>
        </div>
      </div>
      <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                  color:#4a7a9b; margin-top:0.3rem;'>FL ROUNDS COMPLETE</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    threat_cls  = "crit" if attack_detected else "ok"
    threat_text = "THREAT" if attack_detected else "NOMINAL"
    threat_val  = "HIGH" if attack_detected else "CLEAR"
    st.markdown(f"""
    <div class="v-card {'crit' if attack_detected else ''}">
      <div class="v-label">Security Status</div>
      <div class="v-metric {threat_cls}">{threat_val}</div>
      <div style='margin-top:0.6rem;'>
        <span class="v-badge {threat_cls}">{threat_text}</span>
      </div>
      <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                  color:#4a7a9b; margin-top:0.3rem;'>
        AGG: {'MEDIAN DEFENSE' if 'Median' in aggregation else 'FEDAVG — VULNERABLE'}
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── NEW KPI card 5: Delta-weight comm savings ──────────────────────────────────
with k5:
    delta_norm  = latest.get("delta_norm", 0)
    savings_pct = max(0, round((1 - delta_norm / 2.5) * 100, 1))
    sv_cls      = "ok" if savings_pct >= 60 else ("warn" if savings_pct >= 30 else "crit")
    st.markdown(f"""
    <div class="v-card">
      <div class="v-label">Comm Savings</div>
      <div class="v-metric {sv_cls}">{savings_pct:.0f}%</div>
      <div style='margin-top:0.5rem;'>
        <div class="v-bar-track">
          <div class="v-bar-fill {sv_cls}" style='width:{savings_pct:.1f}%;'></div>
        </div>
      </div>
      <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                  color:#4a7a9b; margin-top:0.3rem;'>DELTA-WEIGHT XFER</div>
    </div>
    """, unsafe_allow_html=True)

# ── NEW KPI card 6: Convergence delta ─────────────────────────────────────────
with k6:
    conv_delta  = latest.get("conv_delta", 0)
    cd_cls      = "ok" if conv_delta >= conv_threshold else "warn"
    cd_label    = "CONVERGED" if converged else "TRAINING"
    st.markdown(f"""
    <div class="v-card {'warn' if converged else ''}">
      <div class="v-label">Conv. Δ Accuracy</div>
      <div class="v-metric {cd_cls}" style='font-size:1.8rem;'>{conv_delta:.5f}</div>
      <div style='margin-top:0.6rem;'>
        <span class="v-badge {'warn' if converged else 'ok'}">{cd_label}</span>
      </div>
      <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                  color:#4a7a9b; margin-top:0.3rem;'>THRESHOLD: {conv_threshold:.3f}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br/>", unsafe_allow_html=True)


# ── NEW: 3D Network Topology (HTML component) ─────────────────────────────────

if show_topology:
    st.markdown('<div class="v-section-title">⬡ 3D Network Topology — Live Federation Graph</div>',
                unsafe_allow_html=True)

    # Build JS arrays for node states so the canvas reflects real sim state
    node_states = []
    factory_names = ["Factory Alpha", "Factory Beta", "Factory Gamma",
                     "Factory Delta", "Factory Epsilon"]
    for i in range(num_clients):
        cl = latest.get("clients", [{}] * num_clients)
        cl_data = cl[i] if i < len(cl) else {}
        poisoned = attack_mode and i == 2 and current_round >= 4
        acc      = cl_data.get("accuracy", 0) if current_round > 0 else 0
        status   = "crit" if poisoned else ("ok" if acc >= 0.75 else ("warn" if acc >= 0.5 else "off"))
        node_states.append({
            "id": i, "name": factory_names[i],
            "acc": acc, "status": status, "poisoned": poisoned,
        })

    nodes_js = json.dumps(node_states)

    topology_html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #020c14; overflow: hidden; }}
  canvas {{ display: block; width: 100%; }}
  #info {{
    position: absolute; bottom: 8px; left: 50%; transform: translateX(-50%);
    display: flex; gap: 16px;
    font-family: 'Share Tech Mono', monospace; font-size: 10px; color: #2a5c78;
    letter-spacing: 1px;
  }}
  .inf {{ display: flex; align-items: center; gap: 5px; }}
  .dot {{ width: 7px; height: 7px; border-radius: 50%; }}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="info">
  <div class="inf"><div class="dot" style="background:#00ffb3;box-shadow:0 0 6px #00ffb3"></div>HEALTHY</div>
  <div class="inf"><div class="dot" style="background:#ffaa00;box-shadow:0 0 6px #ffaa00"></div>DEGRADED</div>
  <div class="inf"><div class="dot" style="background:#ff3c3c;box-shadow:0 0 6px #ff3c3c;animation:b .7s infinite"></div>COMPROMISED</div>
  <div class="inf"><div class="dot" style="background:#00d4ff;box-shadow:0 0 8px #00d4ff"></div>SERVER</div>
</div>
<style>@keyframes b{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}</style>
<script>
const NODES = {nodes_js};
const ROUND = {current_round};
const canvas = document.getElementById('c');
const ctx    = canvas.getContext('2d');
let W, H, angle = 0;

function resize() {{
  W = canvas.width  = window.innerWidth;
  H = canvas.height = window.innerHeight - 32;
}}
resize();
window.addEventListener('resize', resize);

const COLOR = {{ ok:'#00ffb3', warn:'#ffaa00', crit:'#ff3c3c', off:'#2a5c78' }};

function draw() {{
  ctx.clearRect(0, 0, W, H);
  angle += 0.006;
  const cx = W / 2, cy = H / 2;
  const R  = Math.min(W, H) * 0.30;

  // Grid dots background
  ctx.fillStyle = '#0a2a3a33';
  for (let gx = 0; gx < W; gx += 40)
    for (let gy = 0; gy < H; gy += 40)
      ctx.fillRect(gx, gy, 1, 1);

  const n = NODES.length;
  const projected = NODES.map((nd, i) => {{
    const theta = (i / n) * Math.PI * 2 + angle;
    const phi   = Math.PI * 0.38;
    const x3 = R * Math.cos(theta) * Math.sin(phi);
    const y3 = R * Math.sin(theta) * 0.52;
    const z3 = R * Math.cos(theta) * Math.cos(phi);
    const sc = 1 / (1 - z3 / (R * 3.5));
    return {{ px: cx + x3 * sc, py: cy + y3 * sc, z3, sc, nd }};
  }});
  projected.sort((a, b) => a.z3 - b.z3);

  // Cross-links between nodes
  for (let i = 0; i < projected.length; i++) {{
    for (let j = i + 1; j < projected.length; j++) {{
      const a = projected[i], b = projected[j];
      ctx.beginPath(); ctx.moveTo(a.px, a.py); ctx.lineTo(b.px, b.py);
      ctx.strokeStyle = 'rgba(0,255,179,0.05)';
      ctx.lineWidth = 0.5; ctx.setLineDash([2, 6]); ctx.stroke();
    }}
  }}
  ctx.setLineDash([]);

  // Server ↔ node spokes
  for (const p of projected) {{
    const col = COLOR[p.nd.status] || '#2a5c78';
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(p.px, p.py);
    ctx.strokeStyle = p.nd.poisoned
      ? 'rgba(255,60,60,0.3)'
      : (ROUND > 0 ? 'rgba(0,212,255,0.18)' : 'rgba(42,92,120,0.15)');
    ctx.lineWidth = 1; ctx.setLineDash([3, 5]); ctx.stroke();
    ctx.setLineDash([]);

    // Animated data packet travelling along spoke
    if (ROUND > 0) {{
      const t = (angle * 2 + projected.indexOf(p)) % 1;
      const px2 = cx + (p.px - cx) * t;
      const py2 = cy + (p.py - cy) * t;
      ctx.beginPath(); ctx.arc(px2, py2, 2, 0, Math.PI * 2);
      ctx.fillStyle = col + 'cc'; ctx.fill();
    }}
  }}

  // Draw client nodes (back-to-front)
  for (const p of projected) {{
    const col = COLOR[p.nd.status] || '#2a5c78';
    const r   = 9 * p.sc;

    // Glow
    const grd = ctx.createRadialGradient(p.px, p.py, 0, p.px, p.py, r * 2.8);
    grd.addColorStop(0, col + '55'); grd.addColorStop(1, col + '00');
    ctx.beginPath(); ctx.arc(p.px, p.py, r * 2.8, 0, Math.PI * 2);
    ctx.fillStyle = grd; ctx.fill();

    // Ring
    ctx.beginPath(); ctx.arc(p.px, p.py, r, 0, Math.PI * 2);
    ctx.fillStyle   = col + '22';
    ctx.strokeStyle = col;
    ctx.lineWidth   = 1.5 * p.sc;
    ctx.fill(); ctx.stroke();

    // Label
    const fs = Math.max(8, 9 * p.sc);
    ctx.font      = `bold ${{fs}}px "Share Tech Mono", monospace`;
    ctx.fillStyle = col;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(`C${{p.nd.id}}`, p.px, p.py);

    ctx.font      = `${{Math.max(7, 7.5 * p.sc)}}px "Share Tech Mono", monospace`;
    ctx.fillStyle = '#2a5c78';
    ctx.fillText(p.nd.name.split(' ')[1], p.px, p.py + r + 10 * p.sc);

    if (ROUND > 0) {{
      const accTxt = p.nd.poisoned ? '⚠ POISON' : `${{(p.nd.acc * 100).toFixed(1)}}%`;
      ctx.font      = `${{Math.max(6, 7 * p.sc)}}px "Share Tech Mono", monospace`;
      ctx.fillStyle = col;
      ctx.fillText(accTxt, p.px, p.py + r + 20 * p.sc);
    }}
  }}

  // Server node
  const sR  = 13;
  const sGrd = ctx.createRadialGradient(cx, cy, 0, cx, cy, sR * 3.5);
  sGrd.addColorStop(0, 'rgba(0,212,255,0.55)');
  sGrd.addColorStop(1, 'rgba(0,212,255,0)');
  ctx.beginPath(); ctx.arc(cx, cy, sR * 3.5, 0, Math.PI * 2);
  ctx.fillStyle = sGrd; ctx.fill();

  ctx.beginPath(); ctx.arc(cx, cy, sR, 0, Math.PI * 2);
  ctx.fillStyle   = 'rgba(0,212,255,0.18)';
  ctx.strokeStyle = '#00d4ff';
  ctx.lineWidth   = 2; ctx.fill(); ctx.stroke();

  ctx.font = 'bold 8px "Share Tech Mono", monospace';
  ctx.fillStyle = '#00d4ff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('SVR', cx, cy);

  // Rotating rings around server
  for (let ri = 1; ri <= 2; ri++) {{
    const pR = sR + ri * 8 + Math.sin(angle * 3 + ri) * 3;
    ctx.beginPath(); ctx.arc(cx, cy, pR, angle * (ri % 2 === 0 ? 1 : -1), angle * (ri % 2 === 0 ? 1 : -1) + Math.PI * 1.2);
    ctx.strokeStyle = `rgba(0,212,255,${{0.12 / ri}})`;
    ctx.lineWidth   = 1; ctx.stroke();
  }}

  requestAnimationFrame(draw);
}}
draw();
</script>
</body>
</html>
"""
    st.components.v1.html(topology_html, height=300, scrolling=False)
    st.markdown("<br/>", unsafe_allow_html=True)


# ── Charts row (ORIGINAL Plotly acc/loss chart + NEW radar) ───────────────────

col_chart1, col_chart2 = st.columns([3, 2] if not show_radar else [2, 2])

with col_chart1:
    st.markdown('<div class="v-section-title">⬡ Accuracy & Loss Over Rounds</div>',
                unsafe_allow_html=True)

    if metrics_history:
        df = pd.DataFrame(metrics_history)

        try:
            import plotly.graph_objects as go

            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=df["round"], y=df["accuracy"] * 100,
                name="Accuracy (%)",
                line=dict(color="#00d4ff", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(0,212,255,0.05)",
                mode="lines+markers",
                marker=dict(size=5, color="#00d4ff"),
            ))

            fig.add_trace(go.Scatter(
                x=df["round"], y=df["loss"],
                name="Loss",
                line=dict(color="#00ffb3", width=2, dash="dot"),
                yaxis="y2",
                mode="lines+markers",
                marker=dict(size=4, color="#00ffb3"),
            ))

            # NEW: convergence delta line
            if "conv_delta" in df.columns:
                fig.add_trace(go.Scatter(
                    x=df["round"], y=df["conv_delta"] * 100,
                    name="Δ Acc (×100)",
                    line=dict(color="#a78bfa", width=1.2, dash="dashdot"),
                    yaxis="y2",
                    mode="lines",
                    opacity=0.7,
                ))

            if attack_mode and current_round > 5:
                fig.add_vrect(
                    x0=3, x1=min(current_round, 10),
                    fillcolor="rgba(255,60,60,0.08)",
                    line_color="rgba(255,60,60,0.3)",
                    annotation_text="ATTACK ZONE",
                    annotation_font_color="#ff3c3c",
                    annotation_font_size=10,
                )

            fig.add_hline(
                y=85, line_dash="dash",
                line_color="rgba(255,170,0,0.4)",
                annotation_text="Target 85%",
                annotation_font_color="#ffaa00",
                annotation_font_size=10,
            )

            # NEW: convergence threshold line on y2
            fig.add_hline(
                y=conv_threshold * 100,
                line_dash="dot",
                line_color="rgba(167,139,250,0.4)",
                yref="y2",
                annotation_text=f"Conv. Δ {conv_threshold:.3f}",
                annotation_font_color="#a78bfa",
                annotation_font_size=9,
            )

            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(4,20,31,0.8)",
                font=dict(family="Share Tech Mono", color="#4a7a9b", size=11),
                xaxis=dict(title="Round", gridcolor="#0a2a3a", color="#4a7a9b", showgrid=True),
                yaxis=dict(title="Accuracy (%)", gridcolor="#0a2a3a", color="#00d4ff", range=[0, 100]),
                yaxis2=dict(title="Loss / Δ×100", overlaying="y", side="right",
                            color="#00ffb3", showgrid=False),
                legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#00d4ff",
                            borderwidth=1, font=dict(color="#7ab8d4")),
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
            )
            st.plotly_chart(fig, use_container_width=True)

        except ImportError:
            chart_df = df[["round", "accuracy", "loss"]].set_index("round")
            st.line_chart(chart_df)
    else:
        st.markdown("""
        <div style='height:200px; display:flex; align-items:center; justify-content:center;
                    color:#4a7a9b; font-family:Share Tech Mono,monospace; font-size:0.8rem;
                    border:1px dashed #0a2a3a; border-radius:4px;'>
          AWAITING FEDERATED ROUNDS...
        </div>
        """, unsafe_allow_html=True)


# ── NEW: Client Health Radar Chart ────────────────────────────────────────────

with col_chart2:
    if show_radar and metrics_history:
        st.markdown('<div class="v-section-title">⬡ Client Health Radar</div>',
                    unsafe_allow_html=True)
        try:
            import plotly.graph_objects as go

            radar_fig = go.Figure()
            categories = ["Accuracy", "Stability", "Low Loss", "Norm OK", "Participation"]
            colors_radar = ["#00d4ff", "#00ffb3", "#ffaa00", "#a78bfa", "#f472b6"]
            factory_names = ["Factory Alpha", "Factory Beta", "Factory Gamma",
                             "Factory Delta", "Factory Epsilon"]

            clients_data = latest.get("clients", [])
            for i, cl in enumerate(clients_data[:num_clients]):
                poisoned = attack_mode and i == 2 and current_round >= 4
                acc  = cl.get("accuracy", 0)
                loss = cl.get("loss", 1)
                random.seed(i * 41 + current_round)
                if poisoned:
                    vals = [5, 8, 3, 10, 90]
                else:
                    vals = [
                        round(acc * 100, 1),
                        round((1 - random.uniform(0, 0.12)) * 100, 1),
                        round((1 - min(loss / 2, 1)) * 100, 1),
                        round((1 - random.uniform(0, 0.15)) * 100, 1),
                        100,
                    ]
                vals_closed = vals + [vals[0]]
                cats_closed = categories + [categories[0]]
                col_r = colors_radar[i % len(colors_radar)]
                radar_fig.add_trace(go.Scatterpolar(
                    r=vals_closed, theta=cats_closed,
                    fill="toself",
                    name=factory_names[i],
                    line=dict(color=col_r, width=1.5),
                    fillcolor=f"rgba({int(col_r[1:3],16)},{int(col_r[3:5],16)},{int(col_r[5:7],16)},0.09)",
                    marker=dict(size=4, color=col_r),
                ))

            radar_fig.update_layout(
                polar=dict(
                    bgcolor="rgba(4,20,31,0.8)",
                    radialaxis=dict(visible=True, range=[0, 100],
                                   gridcolor="#0a2a3a", color="#2a5c78", tickfont=dict(size=8)),
                    angularaxis=dict(gridcolor="#0a2a3a", color="#4a7a9b", tickfont=dict(size=9)),
                ),
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#7ab8d4", size=9)),
                margin=dict(l=20, r=20, t=20, b=20),
                height=300,
            )
            st.plotly_chart(radar_fig, use_container_width=True)

        except ImportError:
            st.markdown("""<div style='color:#4a7a9b; font-family:Share Tech Mono,monospace;
                font-size:0.7rem; padding:1rem;'>Install plotly for radar chart.</div>""",
                        unsafe_allow_html=True)
    else:
        # Original factory nodes panel (shown when radar is off)
        st.markdown('<div class="v-section-title">⬡ Factory Nodes</div>', unsafe_allow_html=True)
        factory_names = ["Factory Alpha", "Factory Beta", "Factory Gamma",
                         "Factory Delta", "Factory Epsilon"]
        for i in range(num_clients):
            if demo_mode and current_round > 0:
                rng_seed = i * 100 + current_round
                random.seed(rng_seed)
                client_acc  = min(acc_val + random.uniform(-0.06, 0.06), 1.0)
                is_attacker = attack_mode and i == 2
                status = "crit" if is_attacker else ("ok" if client_acc >= 0.75 else "warn")
                label  = "⚠ COMPROMISED" if is_attacker else f"{client_acc*100:.1f}%"
            else:
                status = "offline"
                label  = "OFFLINE"
            st.markdown(f"""
            <div class="factory-node">
              <div class="factory-dot {status}"></div>
              <div style='flex:1;'>
                <div style='font-family:Rajdhani,sans-serif; font-weight:600;
                            font-size:0.85rem; color:#e0f4ff;'>{factory_names[i]}</div>
                <div style='font-family:Share Tech Mono,monospace; font-size:0.6rem;
                            color:#4a7a9b;'>NODE {i} · CLIENT_{i}</div>
              </div>
              <div style='font-family:Orbitron,monospace; font-size:0.75rem;
                          color:{"#ff3c3c" if status=="crit" else "#00d4ff"};'>{label}</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("<br/>", unsafe_allow_html=True)


# ── NEW: Convergence Heatmap ───────────────────────────────────────────────────

if show_heatmap and current_round > 0:
    st.markdown('<div class="v-section-title">⬡ Convergence Heatmap — Client × Round Accuracy</div>',
                unsafe_allow_html=True)

    factory_names = ["Factory Alpha", "Factory Beta", "Factory Gamma",
                     "Factory Delta", "Factory Epsilon"]
    # Show last 15 rounds
    start_r  = max(0, current_round - 15)
    disp_rounds = metrics_history[start_r:]

    heat_html = '<div style="overflow-x:auto; padding-bottom:4px;">'

    # Column headers
    heat_html += '<div class="heat-row">'
    heat_html += '<div class="heat-label">CLIENT</div>'
    for row in disp_rounds:
        heat_html += f'<div class="heat-cell" style="background:transparent; color:#2a5c78; font-size:0.5rem;">R{row["round"]}</div>'
    heat_html += '</div>'

    for i in range(num_clients):
        heat_html += '<div class="heat-row">'
        heat_html += f'<div class="heat-label">{factory_names[i].split()[1]}</div>'
        for row in disp_rounds:
            clients_list = row.get("clients", [])
            cl = clients_list[i] if i < len(clients_list) else {}
            acc      = cl.get("accuracy", 0)
            poisoned = attack_mode and i == 2 and row["round"] >= 4
            if poisoned:
                bg  = "rgba(255,60,60,0.35)"
                col = "#ff3c3c"
                txt = "⚠"
            else:
                g   = int(acc * 180)
                b   = int(acc * 100)
                bg  = f"rgba(0,{g},{b},0.38)"
                col = f"rgba(0,{min(g+60,255)},{min(b+155,255)},0.9)"
                txt = f"{int(acc*100)}"
            heat_html += (f'<div class="heat-cell" style="background:{bg}; color:{col};">'
                          f'{txt}</div>')
        heat_html += '</div>'

    heat_html += '</div>'
    st.markdown(heat_html, unsafe_allow_html=True)
    st.markdown("<br/>", unsafe_allow_html=True)


# ── Bottom row: per-client bars + event log (ORIGINAL) ────────────────────────

col_bars, col_log = st.columns([2, 3])

factory_names = ["Factory Alpha", "Factory Beta", "Factory Gamma",
                 "Factory Delta", "Factory Epsilon"]

with col_bars:
    st.markdown('<div class="v-section-title">⬡ Per-Node Accuracy</div>', unsafe_allow_html=True)

    for i in range(num_clients):
        if demo_mode and current_round > 0:
            random.seed(i * 77 + current_round)
            c_acc   = min(acc_val + random.uniform(-0.08, 0.05), 1.0)
            is_att  = attack_mode and i == 2
            bar_cls = "crit" if is_att else ("ok" if c_acc >= 0.75 else "warn")
            c_pct   = 5.0 if is_att else c_acc * 100
        else:
            bar_cls = "info"
            c_pct   = 0
            c_acc   = 0

        st.markdown(f"""
        <div style='margin-bottom:0.8rem;'>
          <div style='display:flex; justify-content:space-between;
                      font-family:Share Tech Mono,monospace; font-size:0.65rem;
                      color:#4a7a9b; margin-bottom:0.2rem;'>
            <span>CLIENT_{i} / {factory_names[i]}</span>
            <span style='color:{"#ff3c3c" if (attack_mode and i==2) else "#00d4ff"};'>
              {"POISONED" if (attack_mode and i==2) else f"{c_pct:.1f}%"}
            </span>
          </div>
          <div class="v-bar-track">
            <div class="v-bar-fill {bar_cls}" style='width:{c_pct:.1f}%;'></div>
          </div>
        </div>
        """, unsafe_allow_html=True)


with col_log:
    st.markdown('<div class="v-section-title">⬡ System Event Log</div>', unsafe_allow_html=True)

    log_entries = []

    if demo_mode and current_round > 0:
        now = datetime.now()
        for r in range(max(1, current_round - 5), current_round + 1):
            ts = (now - timedelta(seconds=(current_round - r) * 45)).strftime("%H:%M:%S")
            random.seed(r * 13)
            r_acc = metrics_history[r-1]["accuracy"] if r <= len(metrics_history) else 0
            log_entries.append(("ok",
                f"{ts} · ROUND {r:03d} COMPLETE · acc={r_acc*100:.1f}% · {random.randint(2,3)} clients"))
            if attack_mode and r == 4:
                log_entries.append(("crit",
                    f"{ts} · ⚠ POISONED UPDATE DETECTED · client_2 · norm=187.3"))
            if attack_mode and r == 5 and "Median" in aggregation:
                log_entries.append(("ok",
                    f"{ts} · ✓ MEDIAN AGGREGATION REJECTED outlier · model stable"))
            if r % 5 == 0:
                log_entries.append(("info",
                    f"{ts} · CHECKPOINT SAVED · results/metrics/global_metrics.json"))
            # NEW: LR schedule log entries
            if r in (5, 10, 15):
                lr = round(1e-3 * (0.5 ** (r // 5)), 6)
                log_entries.append(("info",
                    f"{ts} · LR SCHEDULER · cosine decay → lr={lr:.6f}"))
            # NEW: convergence check log
            if r == current_round and converged:
                log_entries.append(("warn",
                    f"{ts} · ⬡ CONVERGENCE THRESHOLD HIT · Δacc < {conv_threshold:.3f} · consider early stop"))
        if dp_mode:
            log_entries.append(("info",
                f"{now.strftime('%H:%M:%S')} · DIFFERENTIAL PRIVACY ACTIVE · ε=1.0 · σ=1.1"))
        # NEW: comm savings log
        if current_round > 0 and latest.get("delta_norm"):
            dn = latest["delta_norm"]
            sv = max(0, round((1 - dn / 2.5) * 100, 1))
            log_entries.append(("info",
                f"{now.strftime('%H:%M:%S')} · DELTA-WEIGHT XFER · norm={dn:.4f} · saved {sv:.0f}% bandwidth"))

    if not log_entries:
        log_entries = [("info", f"{datetime.now().strftime('%H:%M:%S')} · Waiting for FL rounds...")]

    for cls, msg in reversed(log_entries[-10:]):
        st.markdown(f'<div class="log-entry {cls}">{msg}</div>', unsafe_allow_html=True)

st.markdown("<br/>", unsafe_allow_html=True)


# ── NEW: Per-Layer Attack Detection Panel ─────────────────────────────────────

if show_layers and current_round > 0:
    st.markdown('<div class="v-section-title">⬡ Per-Layer Z-Score Attack Detection</div>',
                unsafe_allow_html=True)

    layer_zscores = latest.get("layer_zscores", {})
    if layer_zscores:
        col_lay1, col_lay2 = st.columns(2)
        items = list(layer_zscores.items())
        mid   = len(items) // 2

        def render_layers(items_subset):
            html = ""
            for layer_name, zs in items_subset:
                max_z      = max(abs(z) for z in zs)
                layer_cls  = "crit" if max_z > 2.5 else ("warn" if max_z > 1.5 else "ok")
                layer_col  = "#ff3c3c" if layer_cls == "crit" else ("#ffaa00" if layer_cls == "warn" else "#00ffb3")
                bar_width  = min(max_z / 7.0, 1.0) * 100
                html += f"""
                <div class="layer-row">
                  <div class="layer-name">{layer_name}</div>
                  <div class="layer-bar-track">
                    <div class="layer-bar-fill"
                         style="width:{bar_width:.1f}%;
                                background:{layer_col};
                                box-shadow:0 0 4px {layer_col}88;"></div>
                  </div>
                  <div class="layer-zscore" style="color:{layer_col};">z={max_z:.2f}</div>
                  <span class="v-badge {layer_cls}" style="font-size:0.55rem; padding:0.1rem 0.4rem;">
                    {'ANOMALY' if layer_cls=='crit' else ('WATCH' if layer_cls=='warn' else 'OK')}
                  </span>
                </div>"""
            return html

        with col_lay1:
            st.markdown(render_layers(items[:mid]), unsafe_allow_html=True)
        with col_lay2:
            st.markdown(render_layers(items[mid:]), unsafe_allow_html=True)

        # Summary
        anomaly_layers = [k for k, vs in layer_zscores.items() if max(abs(z) for z in vs) > 2.5]
        if anomaly_layers:
            st.markdown(f"""
            <div style='margin-top:0.6rem; padding:0.5rem 0.8rem;
                        background:#ff3c3c11; border:1px solid #ff3c3c33; border-radius:3px;
                        font-family:Share Tech Mono,monospace; font-size:0.65rem; color:#ff3c3ccc;'>
              ⚠ LAYER ANOMALY DETECTED: {', '.join(anomaly_layers)} —
              {'MEDIAN AGGREGATION will suppress outlier' if 'Median' in aggregation else 'FedAvg VULNERABLE — switch to FedMedian'}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""<div style='color:#2a5c78; font-family:Share Tech Mono,monospace;
            font-size:0.65rem;'>No layer data available yet.</div>""", unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)


# ── Footer (ORIGINAL) ─────────────────────────────────────────────────────────

st.markdown("""
<div style='text-align:center; font-family:Share Tech Mono,monospace; font-size:0.6rem;
            color:#1a3a4a; padding:1rem 0; border-top:1px solid #0a2a3a;
            letter-spacing:0.2em;'>
  VIGILON v2.0 · LOVELY PROFESSIONAL UNIVERSITY · ADHITHYAA A · FEDERATED LEARNING NODE
</div>
""", unsafe_allow_html=True)


# ── Auto-refresh (ORIGINAL) ───────────────────────────────────────────────────

if auto_refresh:
    time.sleep(2)
    st.rerun()