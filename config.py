# config.py

# --- LOCAL DATABASE ---
# Single source of truth for the DuckDB file path. All scripts import this.
DB_PATH = "ensuring_success.duckdb"

# --- VOLATILITY SETTINGS (ATR Multipliers) ---
# How much "breathing room" the stock gets
ATR_MULTIPLIER = {
    "INTRADAY": 0.5,   # Fractional stop for quick intraday invalidation
    "SWING": 2.5,      # Standard structural noise filter
    "POSITIONAL": 4.0  # Deep macro breathing room
}

# --- TREND SETTINGS (Moving Average Anchors) ---
TREND_ANCHOR = {
    "SWING": "sma_20",
    "POSITIONAL": "sma_50"
}

# --- EXIT LABELING (The "Win" Definition) ---
# Lowered to teach the AI to respect solid trends, not just massive home runs.
TSL_THRESHOLD = {
    "SWING": 4.0,      # If a Swing trade nets >4% before stopping out, it's a valid win.
    "POSITIONAL": 8.0  # If Positional nets >8% before stopping out, it's a valid win.
}

# --- DISCOVERY ENGINE THRESHOLDS (Brain 1 Minimums) ---
# Realistic market movement expectations.
CONVICTION_THRESHOLDS = {
    "INTRADAY": 1.5,   # A solid, highly achievable daily pop for Indian equities.
    "SWING": 6.0,      # A strong multi-day momentum burst.
    "POSITIONAL": 12.0 # A definitive macro trend.
}

# --- SURVIVAL_PROBABILITY_THRESHOLDS (Brain 2 Minimums) ---
# The Institutional Sweet Spot.
SURVIVAL_PROBABILITY_THRESHOLDS = {
    "INTRADAY": 50.0,
    "SWING": 50.0,
    "POSITIONAL": 50.0
}

# --- MINIMUM_RISK_REWARD (The Capital Manager) ---
# Mathematically dominant when paired with a 70% win probability.
MINIMUM_RISK_REWARD = {
    "INTRADAY": 2.0,   # Excellent R/R for fast intraday action.
    "SWING": 4.0,      # The standard quant minimum for swing setups.
    "POSITIONAL": 6.0  # Highly asymmetric, but achievable macro targets.
}

# --- POSITION SIZING & RISK LIMITS ---
MAX_CAPITAL_PER_TRADE = {
    "INTRADAY": 20000,
    "SWING": 20000,
    "POSITIONAL": 20000
}

MAX_RISK_PCT_PER_TRADE = {
    "INTRADAY": 5.0,
    "SWING": 5.0,
    "POSITIONAL": 5.0
}

# --- AI MODEL HYPERPARAMETERS ---
MODEL_PARAMS = {
    "n_estimators": 100,
    "learning_rate": 0.05,
    "max_depth": 6
}

GLOBAL_MODEL_PARAMS = {
    "n_estimators": 100,
    "learning_rate": 0.05,
    "max_depth": 8
}

# --- BRAIN 3: REGIME OPTIMIZER SETTINGS ---
# Minimum number of unaudited rejections required to trigger a Walk-Forward Optimization
MIN_UNAUDITED_REJECTIONS = 2500 

# Grid Search Boundaries: How far the AI is allowed to adjust the dials (Min, Max, Step)
SEARCH_SPACE = {
    "INTRADAY": {
        "conviction": (0.5, 3.0, 0.2),
        "survival": (40.0, 80.0, 2.0),
        "rr": (1.5, 4.0, 0.2)
    },
    "SWING": {
        "conviction": (3.0, 10.0, 0.5),
        "survival": (40.0, 80.0, 2.0),
        "rr": (2.0, 6.0, 0.2)
    },
    "POSITIONAL": {
        "conviction": (8.0, 20.0, 1.0),
        "survival": (40.0, 85.0, 2.0),
        "rr": (2.5, 8.0, 0.5)
    }
}

# --- EXECUTION MANAGER SETTINGS ---
# The maximum acceptable degradation in Risk/Reward due to overnight gaps
SLIPPAGE_TOLERANCE_PCT = 5.0

# --- GHOST TRADE SIMULATION (Brain 3 Real Outcomes) ---
# Max trading days to look forward when simulating ghost trade outcomes
GHOST_TRADE_MAX_DAYS = {
    "INTRADAY": 1,      # Same-day only
    "SWING": 15,         # Up to 3 weeks
    "POSITIONAL": 45     # Up to ~2 months
}
