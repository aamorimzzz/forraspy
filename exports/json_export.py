"""
FORRASPY - Módulo de Exportação
Exporta resultados da análise para JSON
"""

import json
import os
from datetime import datetime
from dataclasses import asdict
from typing import Optional

from ..analyzers.base_analyzer import AnalysisResult, WalletProfile, TokenInfo


def export_to_json(
    result: AnalysisResult,
    filepath: Optional[str] = None,
    pretty: bool = True
) -> str:
    """
    Exporta resultado da análise completa para JSON.
    Retorna o conteúdo JSON como string e salva em arquivo se filepath fornecido.
    """
    export_data = {
        "forraspy_version": "1.0.0",
        "exported_at": datetime.utcnow().isoformat(),
        "analysis_time_seconds": result.analysis_time,
        
        "token": _serialize_token(result.token),
        "chain": result.chain,
        "risk_assessment": {
            "score": result.risk_score,
            "level": _risk_level(result.risk_score),
            "flags": result.risk_flags,
        },
        
        "top_traders": [_serialize_wallet(w) for w in result.top_traders],
        "total_traders_analyzed": len(result.top_traders),
        
        "wallet_clusters": _serialize_clusters(result.wallet_clusters),
        
        "summary": _generate_summary(result),
    }
    
    indent = 2 if pretty else None
    json_str = json.dumps(export_data, indent=indent, ensure_ascii=False, default=str)
    
    if filepath:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_str)
    
    return json_str


def export_wallets_only(
    wallets: list[WalletProfile],
    filepath: Optional[str] = None,
    pretty: bool = True
) -> str:
    """Exporta apenas a lista de wallets para JSON (mais leve)"""
    export_data = {
        "forraspy_version": "1.0.0",
        "exported_at": datetime.utcnow().isoformat(),
        "wallets_count": len(wallets),
        "wallets": [_serialize_wallet(w) for w in wallets],
    }
    
    json_str = json.dumps(export_data, indent=2 if pretty else None, 
                          ensure_ascii=False, default=str)
    
    if filepath:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_str)
    
    return json_str


def export_connections_only(
    clusters: dict,
    filepath: Optional[str] = None
) -> str:
    """Exporta apenas as conexões entre wallets"""
    export_data = {
        "forraspy_version": "1.0.0",
        "exported_at": datetime.utcnow().isoformat(),
        "connections": _serialize_clusters(clusters),
    }
    
    json_str = json.dumps(export_data, indent=2, ensure_ascii=False, default=str)
    
    if filepath:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_str)
    
    return json_str


# ══════════════════════════════════════════════════════════════
# SERIALIZERS
# ══════════════════════════════════════════════════════════════

def _serialize_token(token: TokenInfo) -> dict:
    return {
        "address": token.address,
        "name": token.name,
        "symbol": token.symbol,
        "chain": token.chain,
        "decimals": token.decimals,
        "price_usd": token.price_usd,
        "market_cap": token.market_cap,
        "liquidity_usd": token.liquidity_usd,
        "volume_24h": token.volume_24h,
        "price_change_24h": token.price_change_24h,
        "total_supply": token.total_supply,
        "holder_count": token.holder_count,
        "dex": token.dex_name,
        "pair_address": token.pair_address,
        "created_at": token.created_at,
        "security": {
            "is_honeypot": token.is_honeypot,
            "buy_tax_percent": token.buy_tax,
            "sell_tax_percent": token.sell_tax,
            "is_mintable": token.is_mintable,
            "is_proxy": token.is_proxy,
            "owner": token.owner_address,
        }
    }


def _serialize_wallet(wallet: WalletProfile) -> dict:
    return {
        "address": wallet.address,
        "chain": wallet.chain,
        
        "trading": {
            "total_bought": wallet.total_bought,
            "total_sold": wallet.total_sold,
            "total_bought_usd": wallet.total_bought_usd,
            "total_sold_usd": wallet.total_sold_usd,
            "pnl_usd": wallet.pnl_usd,
            "pnl_percent": wallet.pnl_percent,
            "current_holding": wallet.current_holding,
            "current_holding_usd": wallet.current_holding_usd,
            "num_buys": wallet.num_buys,
            "num_sells": wallet.num_sells,
            "avg_buy_price": wallet.avg_buy_price,
            "avg_sell_price": wallet.avg_sell_price,
            "first_buy_time": wallet.first_buy_time,
            "last_trade_time": wallet.last_trade_time,
        },
        
        "funding": {
            "source": wallet.funding_source,
            "amount": wallet.funding_amount,
            "chain": wallet.funding_chain,
            "tx_hash": wallet.funding_tx,
            "timestamp": wallet.funding_time,
        },
        
        "profile": {
            "wallet_age_days": wallet.wallet_age_days,
            "first_seen": wallet.first_seen,
            "total_tokens_traded": wallet.total_tokens_traded,
            "total_tx_count": wallet.total_tx_count,
            "native_balance": wallet.native_balance,
        },
        
        "classification": {
            "is_sniper": wallet.is_sniper,
            "is_whale": wallet.is_whale,
            "is_insider": wallet.is_insider,
            "is_bot": wallet.is_bot,
            "label": wallet.wallet_label,
        },
        
        "connections": {
            "connected_wallets": wallet.connected_wallets,
            "probable_other_wallets": wallet.probable_other_wallets,
        },
        
        "tokens_traded_addresses": wallet.tokens_traded[:20],  # Limita para não ficar enorme
    }


def _serialize_clusters(clusters: dict) -> dict:
    connections = clusters.get("connections", {})
    funding_clusters = clusters.get("funding_clusters", {})
    
    return {
        "wallet_connections": [
            {
                "wallet_a": conn["wallet_a"],
                "wallet_b": conn["wallet_b"],
                "similarity_score": conn["similarity"],
                "reasons": conn["reasons"],
            }
            for conn in connections.values()
        ],
        "funding_clusters": [
            {
                "funding_source": source,
                "wallets": wallets,
                "count": len(wallets),
            }
            for source, wallets in funding_clusters.items()
        ],
        "total_connections": len(connections),
        "total_clusters": len(funding_clusters),
    }


def _risk_level(score: int) -> str:
    if score >= 80:
        return "SAFE"
    elif score >= 60:
        return "MODERATE"
    elif score >= 40:
        return "RISKY"
    elif score >= 20:
        return "DANGEROUS"
    else:
        return "PROBABLE_SCAM"


def _generate_summary(result: AnalysisResult) -> dict:
    """Gera resumo estatístico da análise"""
    traders = result.top_traders
    
    total_profit = sum(t.pnl_usd for t in traders if t.pnl_usd > 0)
    total_loss = sum(t.pnl_usd for t in traders if t.pnl_usd < 0)
    
    snipers = [t for t in traders if t.is_sniper]
    whales = [t for t in traders if t.is_whale]
    insiders = [t for t in traders if t.is_insider]
    bots = [t for t in traders if t.is_bot]
    
    # Wallets com conexões
    connected = [t for t in traders if t.probable_other_wallets]
    
    # Funding sources únicas
    funding_sources = set(
        t.funding_source for t in traders 
        if t.funding_source and t.funding_source != "unknown"
    )
    
    return {
        "total_traders_analyzed": len(traders),
        "total_realized_profit_usd": total_profit,
        "total_realized_loss_usd": total_loss,
        "net_pnl_usd": total_profit + total_loss,
        "classification_breakdown": {
            "snipers": len(snipers),
            "whales": len(whales),
            "probable_insiders": len(insiders),
            "bots": len(bots),
        },
        "connected_wallets": len(connected),
        "unique_funding_sources": len(funding_sources),
        "risk_score": result.risk_score,
        "risk_level": _risk_level(result.risk_score),
    }
