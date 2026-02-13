"""
FORRASPY - Configuração Central
Bot de inteligência on-chain para Telegram
"""

import os
from dataclasses import dataclass, field
from typing import Optional

# Carrega .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ══════════════════════════════════════════════════════════════
# CONFIGURAÇÕES DO BOT
# ══════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "SEU_TOKEN_AQUI")

# ══════════════════════════════════════════════════════════════
# API KEYS - Preencha com suas chaves
# ══════════════════════════════════════════════════════════════

# Solana
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "")
SOLSCAN_API_KEY = os.getenv("SOLSCAN_API_KEY", "")
BIRDEYE_API_KEY = os.getenv("BIRDEYE_API_KEY", "")

# EVM (Base & BSC)
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "")
BSCSCAN_API_KEY = os.getenv("BSCSCAN_API_KEY", "")
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY", "")

# Análise avançada (opcional)
ARKHAM_API_KEY = os.getenv("ARKHAM_API_KEY", "")
DEXSCREENER_API_KEY = os.getenv("DEXSCREENER_API_KEY", "")

# ══════════════════════════════════════════════════════════════
# RPCs
# ══════════════════════════════════════════════════════════════

SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
BASE_RPC = os.getenv("BASE_RPC", "https://mainnet.base.org")
BSC_RPC = os.getenv("BSC_RPC", "https://bsc-dataseed1.binance.org")

# Se tiver Helius, usa RPC deles (mais rápido)
if HELIUS_API_KEY:
    SOLANA_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# ══════════════════════════════════════════════════════════════
# ENDPOINTS DAS APIs
# ══════════════════════════════════════════════════════════════

ENDPOINTS = {
    "dexscreener": "https://api.dexscreener.com/latest/dex",
    "birdeye": "https://public-api.birdeye.so",
    "helius": "https://api.helius.xyz/v0",
    "solscan": "https://pro-api.solscan.io/v2.0",
    "basescan": "https://api.basescan.org/api",
    "bscscan": "https://api.bscscan.com/api",
    "moralis": "https://deep-index.moralis.io/api/v2.2",
    "defined": "https://graph.defined.fi/graphql",
    "goplus": "https://api.gopluslabs.io/api/v1",
}

# ══════════════════════════════════════════════════════════════
# CONFIGURAÇÕES DE ANÁLISE
# ══════════════════════════════════════════════════════════════

@dataclass
class AnalysisConfig:
    # Quantos top holders/traders analisar
    top_holders_count: int = 20
    top_traders_count: int = 15
    
    # Profundidade da análise de funding
    funding_depth: int = 3  # Quantos hops de funding rastrear
    
    # Limites de transações a buscar
    max_transactions: int = 500
    
    # Threshold para considerar "conexão" entre wallets
    connection_threshold: float = 0.7  # 0 a 1
    
    # Mínimo de lucro para considerar "top trader" (em USD)
    min_profit_usd: float = 100.0
    
    # Chains suportadas
    supported_chains: list = field(default_factory=lambda: ["solana", "base", "bsc"])


ANALYSIS_CONFIG = AnalysisConfig()

# ══════════════════════════════════════════════════════════════
# CHAIN IDS
# ══════════════════════════════════════════════════════════════

CHAIN_IDS = {
    "base": 8453,
    "bsc": 56,
    "ethereum": 1,
}

CHAIN_NAMES = {
    "base": "Base",
    "bsc": "BNB Smart Chain",
    "solana": "Solana",
}

EXPLORER_URLS = {
    "base": "https://basescan.org",
    "bsc": "https://bscscan.com",
    "solana": "https://solscan.io",
}
