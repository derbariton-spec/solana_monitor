from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

APP_TITLE = "Solana Research Terminal"
APP_VERSION = "4.0.0"
SOLANA_LOGO_URL = "https://cryptologos.cc/logos/solana-sol-logo.png"
DEFAULT_CHAIN = "Solana"
DEFAULT_PRODUCT_ID = "SOL-USD"
DEFAULT_COINGLASS_SYMBOL = "SOL"
DEFAULT_COINGLASS_PAIR = "SOLUSDT"
DEFAULT_COINGLASS_EXCHANGE = "Binance"

SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
JITOSOL_MINT = "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn"
USDC_MINT = "EPjFWdd5AufqSSqeM2qvyhtT4wWnF6nZHu4Pwh3wz2z"

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
COINGECKO_MARKET_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
COINBASE_CANDLES_URL = "https://api.exchange.coinbase.com/products/{product_id}/candles"
DEFILLAMA_TVL_URL = "https://api.llama.fi/v2/historicalChainTvl/Solana"
DEFILLAMA_PROTOCOLS_URL = "https://api.llama.fi/protocols"
DEFILLAMA_STABLES_URL = "https://stablecoins.llama.fi/stablecoincharts/Solana"
DEFILLAMA_DEX_URL = "https://api.llama.fi/overview/dexs/Solana"
DEFILLAMA_FEES_URL = "https://api.llama.fi/overview/fees/Solana"
DEFILLAMA_RWA_PRO_URL_TEMPLATE = "https://pro-api.llama.fi/{api_key}/rwa/chain/Solana"

COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com"
COINGLASS_LIQUIDATION_HEATMAP_ENDPOINT = "/api/futures/liquidation/aggregated-heatmap/model1"
COINGLASS_PAIR_HEATMAP_ENDPOINT = "/api/futures/liquidation/heatmap/model1"
COINGLASS_OPEN_INTEREST_ENDPOINT = "/api/futures/openInterest/ohlc-history"
COINGLASS_FUNDING_ENDPOINT = "/api/futures/fundingRate/oi-weight-ohlc-history"

REQUEST_TIMEOUT = 25
USER_AGENT = "solana-research-terminal/4.0"
LOCAL_DATA_CSV = "data/solana_fundamentals.csv"

CANDLE_INTERVALS = {
    "1 Minute": 60,
    "5 Minuten": 300,
    "15 Minuten": 900,
    "1 Stunde": 3600,
    "6 Stunden": 21600,
    "1 Tag": 86400,
}

CANDLE_RANGES = {
    "1 Tag": 1,
    "7 Tage": 7,
    "30 Tage": 30,
    "90 Tage": 90,
    "1 Jahr": 365,
}

MAX_COINBASE_CANDLES = 300


def get_secret(name: str, default: str | None = None) -> str | None:
    """Read from Streamlit secrets first, then environment variables."""
    if st is not None:
        try:
            if name in st.secrets:
                value = st.secrets.get(name)
                return str(value) if value is not None else default
        except Exception:
            pass
    return os.environ.get(name, default)


@dataclass(frozen=True)
class RuntimeConfig:
    supabase_url: str | None
    supabase_anon_key: str | None
    coinglass_api_key: str | None
    defillama_api_key: str | None
    solana_rpc_url: str


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        supabase_url=get_secret("SUPABASE_URL"),
        supabase_anon_key=get_secret("SUPABASE_ANON_KEY") or get_secret("SUPABASE_KEY"),
        coinglass_api_key=get_secret("COINGLASS_API_KEY"),
        defillama_api_key=get_secret("DEFILLAMA_API_KEY"),
        solana_rpc_url=get_secret("SOLANA_RPC_URL", SOLANA_RPC_URL) or SOLANA_RPC_URL,
    )


def has_supabase() -> bool:
    cfg = load_runtime_config()
    return bool(cfg.supabase_url and cfg.supabase_anon_key)


def has_coinglass() -> bool:
    return bool(load_runtime_config().coinglass_api_key)
