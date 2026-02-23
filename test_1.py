#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monte Carlo Stress Lab (single-file app)
- No extra deps beyond PyQt5/numpy/pandas/matplotlib/scipy(optional fallback)
"""

import json
import math
import traceback
from dataclasses import dataclass
from datetime import datetime, date, timedelta

import numpy as np
import pandas as pd

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QLineEdit, QFileDialog, QMessageBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QTextEdit, QTableWidget, QTableWidgetItem, QCheckBox
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

try:
    from scipy.stats import norm
    _cdf = norm.cdf
    _pdf = norm.pdf
except Exception:
    def _cdf(x):
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def _pdf(x):
        return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


def apply_theme(widget):
    widget.setStyleSheet("""
        QMainWindow, QWidget { background: #0f1115; color: #e6e6e6; }
        QGroupBox { border: 1px solid #2a2f3a; border-radius: 8px; margin-top: 8px; padding: 8px; }
        QPushButton { border: 1px solid #3a4252; border-radius: 6px; padding: 6px 10px; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { background: #171b22; border: 1px solid #2a2f3a; }
        QTabWidget::pane { border: 1px solid #2a2f3a; }
    """)


def set_button_variant(btn, variant="secondary"):
    btn.setProperty("variant", variant)
    style = {
        "primary": "background:#2d6cdf;color:white;",
        "secondary": "background:#222833;color:#dfe6f3;",
        "danger": "background:#8b2e2e;color:white;"
    }.get(variant, "")
    btn.setStyleSheet(f"QPushButton{{{style}}}")
    # mandatory repolish
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    btn.update()


@dataclass
class OptionContract:
    symbol: str
    option_type: str
    strike: float
    expiry: datetime
    qty: int
    premium: float
    entry_date: datetime
    iv: float
    r: float
    dividend_yield: float = 0.0
    multiplier: float = 1.0

    def T(self, now: datetime) -> float:
        t = (self.expiry - now).total_seconds() / (365.0 * 24 * 3600)
        if t <= 0:
            return 1.0 / (365.0 * 24 * 60)  # epsilon
        return t

    def d1(self, S, now):
        T = self.T(now)
        sig = max(self.iv, 1e-6)
        return (math.log(max(S, 1e-8) / max(self.strike, 1e-8)) + (self.r - self.dividend_yield + 0.5 * sig * sig) * T) / (sig * math.sqrt(T))

    def d2(self, S, now):
        return self.d1(S, now) - max(self.iv, 1e-6) * math.sqrt(self.T(now))

    def price_bs(self, S, now):
        T = self.T(now)
        d1 = self.d1(S, now)
        d2 = self.d2(S, now)
        disc_r = math.exp(-self.r * T)
        disc_q = math.exp(-self.dividend_yield * T)
        if self.option_type.upper() == "C":
            return S * disc_q * _cdf(d1) - self.strike * disc_r * _cdf(d2)
        return self.strike * disc_r * _cdf(-d2) - S * disc_q * _cdf(-d1)

    def greeks(self, S, now):
        T = self.T(now)
        sig = max(self.iv, 1e-6)
        d1 = self.d1(S, now)
        d2 = self.d2(S, now)
        disc_r = math.exp(-self.r * T)
        disc_q = math.exp(-self.dividend_yield * T)
        delta = disc_q * _cdf(d1) if self.option_type.upper() == "C" else disc_q * (_cdf(d1) - 1)
        gamma = disc_q * _pdf(d1) / (max(S, 1e-8) * sig * math.sqrt(T))
        vega = S * disc_q * _pdf(d1) * math.sqrt(T)
        theta = (-(S * disc_q * _pdf(d1) * sig) / (2 * math.sqrt(T))) / 365.0
        rho = (self.strike * T * disc_r * (_cdf(d2) if self.option_type.upper() == "C" else -_cdf(-d2)))
        return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta, "rho": rho}

    def payoff_at_expiry(self, S_T):
        intrinsic = max(0.0, S_T - self.strike) if self.option_type.upper() == "C" else max(0.0, self.strike - S_T)
        pnl_one = (intrinsic - self.premium) if self.qty > 0 else (self.premium - intrinsic)
        return pnl_one * abs(self.qty) * self.multiplier


class MultiLegStrategy:
    def __init__(self, legs=None, metadata=None):
        self.legs = legs or []
        self.metadata = metadata or {}

    def value(self, S, now):
        return sum(leg.price_bs(S, now) * leg.qty * leg.multiplier for leg in self.legs)

    def greeks(self, S, now):
        out = {"delta": 0, "gamma": 0, "vega": 0, "theta": 0, "rho": 0}
        for leg in self.legs:
            g = leg.greeks(S, now)
            for k in out:
                out[k] += g[k] * leg.qty * leg.multiplier
        return out

    def pnl_distribution(self, S_T_arr):
        return np.array([sum(leg.payoff_at_expiry(s) for leg in self.legs) for s in S_T_arr], dtype=float)

    def break_even_points(self, now, S_min=0.5, S_max=2.0, n=500):
        if not self.legs:
            return []
        ref = max(1.0, np.mean([l.strike for l in self.legs]))
        grid = np.linspace(S_min * ref, S_max * ref, n)
        y = np.array([sum(leg.payoff_at_expiry(s) for leg in self.legs) for s in grid])
        bes = []
        for i in range(1, len(grid)):
            if y[i - 1] == 0 or y[i] == 0 or y[i - 1] * y[i] < 0:
                bes.append(float(grid[i]))
        return bes[:4]

    def max_loss_max_profit(self, now):
        if not self.legs:
            return None
        ref = max(1.0, np.mean([l.strike for l in self.legs]))
        grid = np.linspace(0.2 * ref, 2.5 * ref, 1000)
        y = np.array([sum(leg.payoff_at_expiry(s) for leg in self.legs) for s in grid])
        return {"max_loss": float(np.min(y)), "max_profit": float(np.max(y))}


class MarketRegime:
    def __init__(self, atr=0, realized_vol=0, implied_vol=0, trend_filter=0, event_risk=False):
        self.atr = atr
        self.realized_vol = realized_vol
        self.implied_vol = implied_vol
        self.trend_filter = trend_filter
        self.event_risk = event_risk

    def classify(self):
        iv = max(1e-8, float(self.implied_vol or 0))
        rv = max(1e-8, float(self.realized_vol or 0))
        iv_rv = iv / rv
        if iv_rv >= 1.35:
            regime = "panic"
            vol_regime = "EXTREME_VOL"
        elif iv_rv >= 1.10:
            regime = "normal"
            vol_regime = "RICH_VOL"
        elif iv_rv <= 0.90:
            regime = "quiet"
            vol_regime = "LOW_VOL_UNDERPRICED"
        else:
            regime = "normal"
            vol_regime = "FAIR_VOL"

        if vol_regime in ("RICH_VOL", "EXTREME_VOL"):
            rec = "short_vol_defined_risk_only"
        else:
            rec = "long_vol"
        if self.event_risk and regime != "panic":
            rec = "event_sensitive_wait_or_smaller_size"

        dte = "7-30 DTE" if regime == "normal" else ("3-14 DTE" if regime == "quiet" else "2-10 DTE")
        return {
            "regime": regime,
            "vol_regime": vol_regime,
            "iv_rv_ratio": iv_rv,
            "recommended_structure": rec,
            "recommended_horizon": dte,
            "why": f"IV/RV={iv_rv:.2f}; thresholds: <0.90 cheap, 0.90-1.10 fair, 1.10-1.35 rich, >1.35 extreme"
        }


class StressEngine:
    def simulate_paths(self, S0, mu, sigma, T, steps, n_paths, model="GBM", event_jump=0.0):
        steps = max(1, int(steps))
        n_paths = int(min(max(100, n_paths), 50000))
        dt = T / steps if T > 0 else 1 / 365
        z = np.random.normal(size=(n_paths, steps))
        drift = (mu - 0.5 * sigma * sigma) * dt
        diff = sigma * np.sqrt(dt) * z
        log_returns = drift + diff
        if event_jump != 0:
            log_returns[:, 0] += np.log(max(1e-8, 1 + event_jump))
        log_price = np.cumsum(log_returns, axis=1)
        paths = S0 * np.exp(np.hstack([np.zeros((n_paths, 1)), log_price]))
        times = np.linspace(0, T, steps + 1)
        return paths, times

    def scenario_shock(self, paths, shock_type, magnitude=0.02):
        p = paths.copy()
        if shock_type == "gap_up":
            p *= (1 + abs(magnitude))
        elif shock_type == "gap_down":
            p *= (1 - abs(magnitude))
        return p

    def risk_metrics(self, pnl, alpha=0.05):
        pnl = np.asarray(pnl, dtype=float)
        var = float(np.quantile(pnl, alpha))
        tail = pnl[pnl <= var]
        es = float(np.mean(tail)) if len(tail) else var
        return {
            "mean": float(np.mean(pnl)),
            "median": float(np.median(pnl)),
            "ProbProfit": float(np.mean(pnl > 0)),
            "VaR_alpha": var,
            "ES_alpha": es,
            "TailRatio": float(es / (abs(var) + 1e-9)),
        }

    def kelly_size(self, edge, variance, fraction=0.25):
        if variance <= 0:
            return 0.0
        return max(0.0, fraction * edge / variance)


class TradeDetailWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trade Detail")
        lay = QVBoxLayout(self)
        self.figure = Figure(figsize=(5, 3))
        self.plot_canvas = FigureCanvas(self.figure)  # required canvas
        lay.addWidget(self.plot_canvas)

    def plot_iv_smile(self, strikes=None, ivs=None):
        strikes = strikes or [90, 100, 110]
        ivs = ivs or [0.22, 0.20, 0.23]
        ax = self.figure.subplots()
        ax.clear()
        ax.plot(strikes, ivs)
        ax.set_title("IV Smile")
        self.plot_canvas.draw_idle()


class IVCalculator(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Options Lab")
        self.resize(1280, 820)
        self.engine = StressEngine()
        self.df_journal = pd.DataFrame()
        self.current_strategy = MultiLegStrategy([])
        self.policy = {
            "long_take_profit": 0.40,
            "long_stop_loss": -0.35,
            "short_take_profit_credit": 0.35,
            "short_stop_multiple": 1.5,
            "max_risk_pct": 0.01,
            "fractional_kelly": 0.25,
            "absolute_cap": 1000.0,
        }
        self._build_ui()
        apply_theme(self)

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        lay = QVBoxLayout(root)

        top = QHBoxLayout()
        self.btn_load = QPushButton("Load Journal")
        self.btn_load.clicked.connect(self.load_journal_data)
        set_button_variant(self.btn_load, "primary")
        top.addWidget(self.btn_load)

        self.btn_run_diag = QPushButton("Diagnostics")
        self.btn_run_diag.clicked.connect(self.run_diagnostics)
        set_button_variant(self.btn_run_diag, "secondary")
        top.addWidget(self.btn_run_diag)
        top.addStretch(1)
        lay.addLayout(top)

        self.tabs = QTabWidget(); lay.addWidget(self.tabs)
        self.tab_journal = QWidget(); self.tab_stress = QWidget()
        self.tabs.addTab(self.tab_journal, "Trade Journal")
        self.tabs.addTab(self.tab_stress, "🧪 Stress Lab (Monte Carlo)")

        self._build_journal_tab()
        self._build_stress_tab()

    def _build_journal_tab(self):
        lay = QVBoxLayout(self.tab_journal)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Symbol", "Type", "Strike", "Qty", "Premium", "Entry Date", "Expiry Date", "Days"]) 
        lay.addWidget(self.table)

        btns = QHBoxLayout()
        b_refresh = QPushButton("Refresh Positions"); b_refresh.clicked.connect(self.refresh_current_positions)
        b_save = QPushButton("Save Edits"); b_save.clicked.connect(self.save_journal_edits)
        set_button_variant(b_refresh, "secondary"); set_button_variant(b_save, "primary")
        btns.addWidget(b_refresh); btns.addWidget(b_save); btns.addStretch(1)
        lay.addLayout(btns)

    def _build_stress_tab(self):
        lay = QVBoxLayout(self.tab_stress)

        snap = QGroupBox("Portfolio Snapshot")
        f = QFormLayout(snap)
        self.lbl_snap = QLabel("No data loaded")
        f.addRow("Snapshot", self.lbl_snap)
        lay.addWidget(snap)

        controls = QGroupBox("Controls")
        c = QFormLayout(controls)
        self.cmb_group = QComboBox(); self.cmb_group.addItems(["Gold", "US500", "WallStreet", "Tech100", "Custom"])
        self.cmb_view = QComboBox(); self.cmb_view.addItems(["single trade", "grouped by expiry", "grouped by underlying"])
        self.sp_paths = QSpinBox(); self.sp_paths.setRange(100, 50000); self.sp_paths.setValue(5000)
        self.sp_steps = QSpinBox(); self.sp_steps.setRange(5, 365); self.sp_steps.setValue(60)
        self.sp_mu = QDoubleSpinBox(); self.sp_mu.setRange(-2, 2); self.sp_mu.setSingleStep(0.01); self.sp_mu.setValue(0.0)
        self.sp_sigma = QDoubleSpinBox(); self.sp_sigma.setRange(0.01, 3.0); self.sp_sigma.setSingleStep(0.01); self.sp_sigma.setValue(0.20)
        self.sp_gap = QDoubleSpinBox(); self.sp_gap.setRange(-0.05, 0.05); self.sp_gap.setSingleStep(0.005); self.sp_gap.setValue(0.0)
        self.sp_alpha = QDoubleSpinBox(); self.sp_alpha.setRange(0.01, 0.20); self.sp_alpha.setSingleStep(0.01); self.sp_alpha.setValue(0.05)
        self.ed_account = QLineEdit("10000")
        c.addRow("Instrument group", self.cmb_group); c.addRow("Strategy view", self.cmb_view)
        c.addRow("n_paths", self.sp_paths); c.addRow("steps", self.sp_steps)
        c.addRow("mu", self.sp_mu); c.addRow("sigma", self.sp_sigma)
        c.addRow("gap shock", self.sp_gap); c.addRow("alpha", self.sp_alpha)
        c.addRow("account value", self.ed_account)
        lay.addWidget(controls)

        btns = QHBoxLayout()
        b_run = QPushButton("Run Stress"); b_evt = QPushButton("Run Event Shock")
        b_exp = QPushButton("Export Report"); b_exit = QPushButton("Generate Exit Plan")
        set_button_variant(b_run, "primary"); set_button_variant(b_evt, "secondary")
        set_button_variant(b_exp, "secondary"); set_button_variant(b_exit, "primary")
        b_run.clicked.connect(self.run_stress)
        b_evt.clicked.connect(lambda: self.run_stress(event=True))
        b_exp.clicked.connect(self.export_report)
        b_exit.clicked.connect(self.generate_exit_plan)
        for b in (b_run, b_evt, b_exp, b_exit): btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        viz = QHBoxLayout()
        self.fig = Figure(figsize=(8, 4))
        self.canvas = FigureCanvas(self.fig)
        viz.addWidget(self.canvas, 2)
        self.txt_teach = QTextEdit(); self.txt_teach.setReadOnly(True)
        self.txt_teach.setPlaceholderText("What the numbers mean + top risks + discipline guidance")
        viz.addWidget(self.txt_teach, 1)
        lay.addLayout(viz)

        self.txt_action = QTextEdit(); self.txt_action.setReadOnly(True)
        self.txt_action.setPlaceholderText("Thorp Discipline Output")
        lay.addWidget(self.txt_action)

        policy = QGroupBox("Policy Settings")
        p = QFormLayout(policy)
        self.sp_pol_long_tp = QDoubleSpinBox(); self.sp_pol_long_tp.setRange(0.05, 2.0); self.sp_pol_long_tp.setSingleStep(0.05); self.sp_pol_long_tp.setValue(self.policy["long_take_profit"])
        self.sp_pol_long_sl = QDoubleSpinBox(); self.sp_pol_long_sl.setRange(-1.0, -0.05); self.sp_pol_long_sl.setSingleStep(0.05); self.sp_pol_long_sl.setValue(self.policy["long_stop_loss"])
        self.sp_pol_short_tp = QDoubleSpinBox(); self.sp_pol_short_tp.setRange(0.10, 0.90); self.sp_pol_short_tp.setSingleStep(0.05); self.sp_pol_short_tp.setValue(self.policy["short_take_profit_credit"])
        self.sp_pol_short_sl = QDoubleSpinBox(); self.sp_pol_short_sl.setRange(1.1, 4.0); self.sp_pol_short_sl.setSingleStep(0.1); self.sp_pol_short_sl.setValue(self.policy["short_stop_multiple"])
        self.sp_pol_risk = QDoubleSpinBox(); self.sp_pol_risk.setRange(0.001, 0.05); self.sp_pol_risk.setSingleStep(0.001); self.sp_pol_risk.setValue(self.policy["max_risk_pct"])
        self.sp_pol_kelly = QDoubleSpinBox(); self.sp_pol_kelly.setRange(0.05, 1.0); self.sp_pol_kelly.setSingleStep(0.05); self.sp_pol_kelly.setValue(self.policy["fractional_kelly"])
        self.chk_event = QCheckBox("Event risk flag")
        p.addRow("Long TP", self.sp_pol_long_tp)
        p.addRow("Long SL", self.sp_pol_long_sl)
        p.addRow("Short TP (credit)", self.sp_pol_short_tp)
        p.addRow("Short SL multiple", self.sp_pol_short_sl)
        p.addRow("Max risk %", self.sp_pol_risk)
        p.addRow("Fractional Kelly", self.sp_pol_kelly)
        p.addRow(self.chk_event)
        b_apply = QPushButton("Apply Policy")
        set_button_variant(b_apply, "secondary")
        b_apply.clicked.connect(self.apply_policy_settings)
        p.addRow(b_apply)
        lay.addWidget(policy)

    def apply_policy_settings(self):
        self.policy["long_take_profit"] = float(self.sp_pol_long_tp.value())
        self.policy["long_stop_loss"] = float(self.sp_pol_long_sl.value())
        self.policy["short_take_profit_credit"] = float(self.sp_pol_short_tp.value())
        self.policy["short_stop_multiple"] = float(self.sp_pol_short_sl.value())
        self.policy["max_risk_pct"] = float(self.sp_pol_risk.value())
        self.policy["fractional_kelly"] = float(self.sp_pol_kelly.value())
        self.update_strategy_recommendation()
        QMessageBox.information(self, "Policy", "Policy settings updated.")

    # ---- Required data consistency methods ----
    def recompute_days_to_expiry(self, df):
        if df is None or df.empty:
            return df
        out = df.copy()
        today = datetime.today().date()
        if "Expiry Date" not in out.columns:
            out["Expiry Date"] = pd.NaT
        out["Expiry Date"] = pd.to_datetime(out["Expiry Date"], errors="coerce")

        if "Days" in out.columns:
            out.loc[out["Expiry Date"].isna() & out["Days"].notna(), "Expiry Date"] = [
                pd.Timestamp(today + timedelta(days=int(max(0, d)))) for d in out.loc[out["Expiry Date"].isna() & out["Days"].notna(), "Days"]
            ]
        out["Days"] = out["Expiry Date"].apply(lambda x: max(0, (x.date() - today).days) if pd.notna(x) else np.nan)
        return out

    def load_journal_data(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, "Open Journal", "", "Excel (*.xlsx *.xls)")
            if not path:
                return
            df = pd.read_excel(path)

            # If both call/put premium columns exist, split into two legs when both are present.
            if "Call Premium" in df.columns or "Put Premium" in df.columns:
                rows = []
                for _, r in df.iterrows():
                    cp = r.get("Call Premium", np.nan)
                    pp = r.get("Put Premium", np.nan)
                    base = r.to_dict()
                    if pd.notna(cp):
                        rc = dict(base)
                        rc["Type"] = "Call"
                        rc["Premium"] = cp
                        rows.append(rc)
                    if pd.notna(pp):
                        rp = dict(base)
                        rp["Type"] = "Put"
                        rp["Premium"] = pp
                        rows.append(rp)
                    if pd.isna(cp) and pd.isna(pp):
                        rows.append(base)
                df = pd.DataFrame(rows)

            if "Type" not in df.columns:
                df["Type"] = np.where(df.get("Premium", pd.Series(index=df.index)).notna(), "Call", "Put")
            if "Premium" not in df.columns:
                df["Premium"] = pd.to_numeric(df.get("Premium", 0), errors="coerce").fillna(0)
            if "Qty" not in df.columns:
                df["Qty"] = 1
            if "Entry Date" not in df.columns:
                df["Entry Date"] = pd.Timestamp(datetime.today().date())
            if "Expiry Date" not in df.columns:
                df["Expiry Date"] = pd.NaT
            df["Entry Date"] = pd.to_datetime(df["Entry Date"], errors="coerce")
            df = self.recompute_days_to_expiry(df)
            self.df_journal = df
            self.refresh_current_positions()
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Could not load journal:\n{e}")

    def _df_to_table(self):
        self.table.setRowCount(0)
        if self.df_journal.empty:
            return
        cols = ["Symbol", "Type", "Strike", "Qty", "Premium", "Entry Date", "Expiry Date", "Days"]
        for c in cols:
            if c not in self.df_journal.columns:
                self.df_journal[c] = np.nan
        self.table.setRowCount(len(self.df_journal))
        for i, row in self.df_journal.iterrows():
            for j, c in enumerate(cols):
                self.table.setItem(i, j, QTableWidgetItem(str(row.get(c, ""))))

    def _table_to_df(self):
        cols = []
        for i in range(self.table.columnCount()):
            h = self.table.horizontalHeaderItem(i)
            cols.append(h.text() if h is not None else f"col_{i}")
        records = []
        for r in range(self.table.rowCount()):
            rec = {}
            for c in range(self.table.columnCount()):
                it = self.table.item(r, c)
                rec[cols[c]] = it.text().strip() if it else ""
            records.append(rec)
        df = pd.DataFrame(records)
        for num in ["Strike", "Qty", "Premium", "Days"]:
            if num in df.columns:
                df[num] = pd.to_numeric(df[num], errors="coerce")
        for dt in ["Entry Date", "Expiry Date"]:
            if dt in df.columns:
                df[dt] = pd.to_datetime(df[dt], errors="coerce")
        return df

    def save_journal_edits(self):
        try:
            self.df_journal = self.recompute_days_to_expiry(self._table_to_df())
            self.refresh_current_positions()
            QMessageBox.information(self, "Saved", "Journal edits applied and DTE recomputed.")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def refresh_current_positions(self):
        self.df_journal = self.recompute_days_to_expiry(self.df_journal)
        self._df_to_table()
        self.current_strategy = self._map_journal_to_strategy(self.df_journal)
        self.update_strategy_recommendation()

    def _map_journal_to_strategy(self, df):
        legs = []
        if df is None or df.empty:
            return MultiLegStrategy([])
        for _, r in df.iterrows():
            try:
                sym = str(r.get("Symbol", "UNKNOWN"))
                typ = str(r.get("Type", "Call")).strip().upper()
                opt = "C" if typ.startswith("C") else "P"
                strike = float(r.get("Strike", np.nan))
                qty = int(r.get("Qty", 0))
                premium = float(r.get("Premium", 0) or 0)
                entry = pd.to_datetime(r.get("Entry Date"), errors="coerce")
                expiry = pd.to_datetime(r.get("Expiry Date"), errors="coerce")
                if pd.isna(expiry):
                    continue
                iv = float(r.get("IV", self.sp_sigma.value()) or self.sp_sigma.value())
                rr = float(r.get("Rate", 0.02) or 0.02)
                mult = float(r.get("Multiplier", 1) or 1)
                if pd.isna(entry):
                    entry = pd.Timestamp(datetime.today().date())
                legs.append(OptionContract(sym, opt, strike, expiry.to_pydatetime(), qty, premium, entry.to_pydatetime(), iv, rr, 0.0, mult))
            except Exception:
                continue
        return MultiLegStrategy(legs)

    def update_strategy_recommendation(self):
        self.df_journal = self.recompute_days_to_expiry(self.df_journal)
        n = len(self.current_strategy.legs)
        if n == 0:
            self.lbl_snap.setText("No open trades loaded")
            self.txt_teach.setPlainText("Empty state: load a journal to run stress tests.")
            self.txt_action.setPlainText("NO TRADE: Missing strategy legs.")
            return
        now = datetime.now()
        S0 = max(1.0, float(np.mean([l.strike for l in self.current_strategy.legs])))
        g = self.current_strategy.greeks(S0, now)
        dtes = [max(0, (l.expiry.date() - date.today()).days) for l in self.current_strategy.legs]
        snapshot = f"legs={n} | net Δ={g['delta']:.2f} Γ={g['gamma']:.4f} ν={g['vega']:.2f} θ/day={g['theta']:.2f} | DTE min/avg={min(dtes)}/{np.mean(dtes):.1f}"
        self.lbl_snap.setText(snapshot)

    def run_stress(self, event=False):
        try:
            if not self.current_strategy.legs:
                self.txt_action.setPlainText("NO TRADE\nWhy this happened: No mapped legs from journal.")
                return
            now = datetime.now()
            S0 = max(1.0, float(np.mean([l.strike for l in self.current_strategy.legs])))
            T = max(1/365, np.mean([l.T(now) for l in self.current_strategy.legs]))
            mu = self.sp_mu.value()
            sigma = self.sp_sigma.value()
            paths, times = self.engine.simulate_paths(S0, mu, sigma, T, self.sp_steps.value(), self.sp_paths.value(), event_jump=(self.sp_gap.value() if event else 0.0))
            S_T = paths[:, -1]
            pnl = self.current_strategy.pnl_distribution(S_T)
            metrics = self.engine.risk_metrics(pnl, self.sp_alpha.value())

            # plots
            self.fig.clear()
            ax1 = self.fig.add_subplot(121)
            ax2 = self.fig.add_subplot(122)
            ax1.hist(pnl, bins=50, alpha=0.8)
            ax1.axvline(metrics["VaR_alpha"], color="r", linestyle="--", label="VaR")
            ax1.axvline(metrics["ES_alpha"], color="m", linestyle="--", label="ES")
            ax1.set_title("P&L Distribution")
            ax1.legend()

            sel = np.random.choice(paths.shape[0], size=min(200, paths.shape[0]), replace=False)
            ax2.plot(paths[sel].T, alpha=0.08)
            ax2.set_title("Path Fan")
            self.canvas.draw_idle()

            bes = self.current_strategy.break_even_points(now)
            mm = self.current_strategy.max_loss_max_profit(now)
            why = [
                f"ProbProfit={metrics['ProbProfit']:.2%}; threshold>55% for premium-selling confidence.",
                f"VaR({self.sp_alpha.value():.0%})={metrics['VaR_alpha']:.2f}; ES={metrics['ES_alpha']:.2f}; deeper tail than VaR means loss clustering.",
                f"Theta/day≈{self.current_strategy.greeks(S0, now)['theta']:.2f}; positive theta helps if price stays near breakeven region.",
            ]
            self.txt_teach.setPlainText(
                "What the numbers mean\n"
                f"- Break-evens (approx): {', '.join(f'{x:.2f}' for x in bes) if bes else 'n/a'}\n"
                f"- Max loss/profit (grid): {mm}\n"
                f"- 3 biggest risks: tail gap, vol regime shift, expiry gamma.\n\n"
                + "\n".join(f"• {w}" for w in why)
            )
            self.txt_action.setPlainText(self._thorp_output(metrics, sigma, S0, T, bes))
            self._log_stress(metrics, mu, sigma)
        except Exception as e:
            self.txt_action.setPlainText("NO TRADE\nWhy this happened: Stress run failed with exception.\n" + str(e))

    def _thorp_output(self, metrics, iv, S0, T, bes):
        rv_proxy = max(0.01, iv * 0.9)
        edge = (iv - rv_proxy)
        expected_move = S0 * iv * math.sqrt(T)
        be_dist = min([abs(b - S0) for b in bes], default=np.nan)
        movement_check = (be_dist <= expected_move) if not np.isnan(be_dist) else False
        regime = MarketRegime(realized_vol=rv_proxy, implied_vol=iv, event_risk=self.chk_event.isChecked()).classify()

        account = float(self.ed_account.text() or 10000)
        max_risk = min(account * self.policy["max_risk_pct"], self.policy["absolute_cap"])
        var = max(1e-6, np.var([metrics["mean"], metrics["median"], metrics["VaR_alpha"], metrics["ES_alpha"]]))
        kelly = self.engine.kelly_size(edge, var, self.policy["fractional_kelly"])

        # machine-weighted score (required buckets)
        regime_fit = 25 if regime["recommended_structure"] in ("short_vol_defined_risk_only", "long_vol") else 12
        vol_edge = 25 if ((regime["vol_regime"] in ("RICH_VOL", "EXTREME_VOL") and edge > 0) or (regime["vol_regime"] == "LOW_VOL_UNDERPRICED" and edge < 0)) else 12
        structure_quality = 20 if np.isfinite(be_dist) else 8
        event_timing = 15 if not self.chk_event.isChecked() else 8
        exec_quality = 15 if metrics["TailRatio"] > -2.0 else 7
        total_score = regime_fit + vol_edge + structure_quality + event_timing + exec_quality

        decision = "PASS"
        gates = []
        if total_score < 70:
            gates.append("score_below_70")
        if not movement_check:
            gates.append("breakeven_outside_expected_move")
        if kelly <= 0:
            gates.append("no_positive_edge")
        if max_risk <= 0:
            gates.append("SIZE_TOO_LARGE")
        if not gates:
            decision = "TRADE"

        return (
            "Thorp Discipline Output\n"
            f"1) Thesis check: {decision}. Why: IV-RV={edge:.4f}; expected move={expected_move:.2f}; nearest BE distance={be_dist if not np.isnan(be_dist) else 'n/a'}; IV/RV={regime['iv_rv_ratio']:.2f}.\n"
            f"2) Exit rules: long premium TP +{self.policy['long_take_profit']:.0%}, SL {self.policy['long_stop_loss']:.0%}; short premium TP {self.policy['short_take_profit_credit']:.0%} credit, SL {self.policy['short_stop_multiple']:.1f}x credit.\n"
            "3) Adjustments: only if invalidation breached or vol regime flips.\n"
            f"4) Next size recommendation: fractional Kelly={kelly:.4f}; hard risk cap={max_risk:.2f}.\n"
            "5) Do-not-do: no undefined-risk short premium.\n"
            f"Volatility Classifier: {regime['vol_regime']} ({regime['why']})\n"
            f"Score Breakdown => Regime:{regime_fit}/25 Vol:{vol_edge}/25 Structure:{structure_quality}/20 Event:{event_timing}/15 Execution:{exec_quality}/15 Total:{total_score}/100\n"
            f"Gate Failures: {', '.join(gates) if gates else 'none'}\n"
            "Why this happened: Decision is metric-anchored (ProbProfit, VaR/ES, BE vs expected move, IV-RV, weighted score)."
        )

    def generate_exit_plan(self):
        self.txt_action.append("\nExit Plan (exact):\n- If TP hit: close at limit order.\n- If SL hit: close immediately, no averaging down.\n- If DTE<=2 and no move: close long premium.\n- If short strike breach + momentum: close short premium.")

    def export_report(self):
        try:
            if self.df_journal.empty:
                QMessageBox.warning(self, "Export", "Nothing to export")
                return
            path, _ = QFileDialog.getSaveFileName(self, "Export Report", "stress_report.xlsx", "Excel (*.xlsx)")
            if not path:
                return
            # Try openpyxl first; fall back to default writer if unavailable.
            writer_kwargs = {"engine": "openpyxl"}
            try:
                writer = pd.ExcelWriter(path, **writer_kwargs)
            except Exception:
                writer = pd.ExcelWriter(path)

            with writer as w:
                self.df_journal.to_excel(w, index=False, sheet_name="Trade Journal")
                pd.DataFrame([{
                    "timestamp": datetime.now(),
                    "action_panel": self.txt_action.toPlainText(),
                    "teaching": self.txt_teach.toPlainText(),
                }]).to_excel(w, index=False, sheet_name="OnePage")
                stress_log = getattr(self, "stress_log", pd.DataFrame())
                if stress_log is not None and not stress_log.empty:
                    stress_log.to_excel(w, index=False, sheet_name="Stress_Log")
            QMessageBox.information(self, "Export", "Report exported.")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _log_stress(self, metrics, mu, sigma):
        if self.df_journal is None:
            return
        explain = self.txt_teach.toPlainText().splitlines()[:5]
        log = pd.DataFrame([{
            "timestamp": datetime.now(), "underlying": self.cmb_group.currentText(),
            "strategy_type": self.cmb_view.currentText(), "paths": self.sp_paths.value(), "steps": self.sp_steps.value(),
            "mu": mu, "sigma": sigma, "VaR": metrics["VaR_alpha"], "ES": metrics["ES_alpha"],
            "ProbProfit": metrics["ProbProfit"], "expected_pnl": metrics["mean"],
            "suggested_action": "TRADE" if metrics["ProbProfit"] > 0.5 else "PASS",
            "top_whys": " | ".join(explain)
        }])
        self.stress_log = getattr(self, "stress_log", pd.DataFrame())
        self.stress_log = pd.concat([self.stress_log, log], ignore_index=True)

    def run_diagnostics(self):
        try:
            msgs = []
            # parity sanity
            now = datetime.now()
            c = OptionContract("X", "C", 100, now + timedelta(days=30), 1, 5, now, 0.2, 0.02)
            p = OptionContract("X", "P", 100, now + timedelta(days=30), 1, 5, now, 0.2, 0.02)
            S = 100
            lhs = c.price_bs(S, now) - p.price_bs(S, now)
            rhs = S - 100 * math.exp(-0.02 * c.T(now))
            msgs.append(f"Parity check |diff|={abs(lhs-rhs):.4f}")
            # monotonicity in IV
            c_low = OptionContract("X", "C", 100, now + timedelta(days=30), 1, 5, now, 0.1, 0.02)
            c_hi = OptionContract("X", "C", 100, now + timedelta(days=30), 1, 5, now, 0.3, 0.02)
            msgs.append(f"Price(iv=0.3) >= Price(iv=0.1): {c_hi.price_bs(S, now) >= c_low.price_bs(S, now)}")
            # dte non-negative
            if not self.df_journal.empty and "Days" in self.df_journal.columns:
                msgs.append(f"DTE non-negative: {(self.df_journal['Days'].fillna(0) >= 0).all()}")
            QMessageBox.information(self, "Diagnostics", "\n".join(msgs))
        except Exception:
            QMessageBox.critical(self, "Diagnostics", traceback.format_exc())


if __name__ == "__main__":
    app = QApplication([])
    w = IVCalculator()
    w.show()
    app.exec_()
