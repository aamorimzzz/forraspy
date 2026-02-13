"""
FORRASPY - Utilidades gerais
"""

import re
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional


def detect_chain(contract: str) -> Optional[str]:
    """
    Detecta automaticamente a chain baseado no formato do contrato.
    - Solana: Base58, 32-44 chars
    - EVM (Base/BSC): 0x + 40 hex chars
    """
    contract = contract.strip()
    
    # EVM address (Base ou BSC) - precisa de contexto adicional ou flag do user
    if re.match(r'^0x[a-fA-F0-9]{40}$', contract):
        return "evm"  # Precisa especificar se é Base ou BSC
    
    # Solana address (Base58)
    if re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', contract):
        return "solana"
    
    return None


def is_valid_evm_address(address: str) -> bool:
    return bool(re.match(r'^0x[a-fA-F0-9]{40}$', address.strip()))


def is_valid_solana_address(address: str) -> bool:
    return bool(re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', address.strip()))


def shorten_address(address: str, chars: int = 6) -> str:
    """Encurta endereço: 0x1234...abcd"""
    if len(address) <= chars * 2 + 3:
        return address
    return f"{address[:chars]}...{address[-chars:]}"


def format_usd(value: float) -> str:
    """Formata valor em USD"""
    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:,.2f}M"
    elif abs(value) >= 1_000:
        return f"${value/1_000:,.2f}K"
    elif abs(value) >= 1:
        return f"${value:,.2f}"
    else:
        return f"${value:.6f}"


def format_token_amount(amount: float, decimals: int = 2) -> str:
    """Formata quantidade de tokens"""
    if amount >= 1_000_000_000:
        return f"{amount/1_000_000_000:,.{decimals}f}B"
    elif amount >= 1_000_000:
        return f"{amount/1_000_000:,.{decimals}f}M"
    elif amount >= 1_000:
        return f"{amount/1_000:,.{decimals}f}K"
    else:
        return f"{amount:,.{decimals}f}"


def format_percentage(value: float) -> str:
    """Formata percentual com emoji"""
    emoji = "🟢" if value > 0 else "🔴" if value < 0 else "⚪"
    return f"{emoji} {value:+.2f}%"


def format_time_ago(timestamp: int) -> str:
    """Converte timestamp para 'há X tempo'"""
    now = datetime.now(timezone.utc)
    dt = datetime.fromtimestamp(timestamp, timezone.utc)
    diff = now - dt
    
    if diff.days > 365:
        years = diff.days // 365
        return f"{years}a atrás"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months}m atrás"
    elif diff.days > 0:
        return f"{diff.days}d atrás"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h atrás"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}min atrás"
    else:
        return "agora"


def generate_wallet_fingerprint(wallet: str) -> str:
    """Gera um fingerprint único para correlação de wallets"""
    return hashlib.sha256(wallet.encode()).hexdigest()[:12]


def build_explorer_link(address: str, chain: str, type: str = "address") -> str:
    """Gera link para o explorer da chain"""
    explorers = {
        "solana": "https://solscan.io",
        "base": "https://basescan.org",
        "bsc": "https://bscscan.com",
    }
    base_url = explorers.get(chain, "")
    if type == "address":
        return f"{base_url}/account/{address}" if chain == "solana" else f"{base_url}/address/{address}"
    elif type == "tx":
        return f"{base_url}/tx/{address}"
    elif type == "token":
        return f"{base_url}/token/{address}"
    return base_url


def escape_markdown_v2(text: str) -> str:
    """Escapa caracteres especiais para Telegram MarkdownV2"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def risk_score_emoji(score: int) -> str:
    """Retorna emoji baseado no score de risco (0-100)"""
    if score >= 80:
        return "🟢 SEGURO"
    elif score >= 60:
        return "🟡 MODERADO"
    elif score >= 40:
        return "🟠 ARRISCADO"
    elif score >= 20:
        return "🔴 PERIGOSO"
    else:
        return "💀 SCAM PROVÁVEL"


def cluster_wallets_by_funding(wallets_data: list) -> dict:
    """
    Agrupa wallets que foram fundadas pela mesma fonte.
    Retorna clusters de wallets potencialmente do mesmo dono.
    """
    clusters = {}
    
    for wallet in wallets_data:
        funding_source = wallet.get("funding_source", "unknown")
        if funding_source not in clusters:
            clusters[funding_source] = []
        clusters[funding_source].append(wallet)
    
    # Filtra clusters com mais de 1 wallet (possível mesmo dono)
    suspicious_clusters = {
        k: v for k, v in clusters.items() 
        if len(v) > 1 and k != "unknown"
    }
    
    return suspicious_clusters


def calculate_wallet_similarity(wallet_a: dict, wallet_b: dict) -> float:
    """
    Calcula similaridade entre duas wallets baseado em:
    - Mesma fonte de funding
    - Timing similar de transações
    - Tokens em comum
    - Padrões de comportamento
    """
    score = 0.0
    
    # Mesma fonte de funding
    if (wallet_a.get("funding_source") == wallet_b.get("funding_source") 
            and wallet_a.get("funding_source") != "unknown"):
        score += 0.4
    
    # Tokens em comum
    tokens_a = set(wallet_a.get("tokens_traded", []))
    tokens_b = set(wallet_b.get("tokens_traded", []))
    if tokens_a and tokens_b:
        overlap = len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)
        score += overlap * 0.3
    
    # Timing similar (criação da wallet)
    created_a = wallet_a.get("first_seen", 0)
    created_b = wallet_b.get("first_seen", 0)
    if created_a and created_b:
        time_diff = abs(created_a - created_b)
        if time_diff < 3600:  # Menos de 1 hora
            score += 0.2
        elif time_diff < 86400:  # Menos de 1 dia
            score += 0.1
    
    # Padrão de valores similares
    avg_a = wallet_a.get("avg_trade_size", 0)
    avg_b = wallet_b.get("avg_trade_size", 0)
    if avg_a and avg_b:
        ratio = min(avg_a, avg_b) / max(avg_a, avg_b)
        if ratio > 0.8:
            score += 0.1
    
    return min(score, 1.0)
