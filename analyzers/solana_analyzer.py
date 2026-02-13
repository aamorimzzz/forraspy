"""
FORRASPY - Solana Analyzer
Análise de tokens e wallets na rede Solana
APIs: Helius, Birdeye, Solscan, DexScreener, GoPlus
"""

import asyncio
import logging
from typing import Optional

from .base_analyzer import BaseAnalyzer, TokenInfo, WalletProfile
from ..config import (
    HELIUS_API_KEY, BIRDEYE_API_KEY, SOLSCAN_API_KEY,
    SOLANA_RPC, ENDPOINTS, ANALYSIS_CONFIG
)

logger = logging.getLogger("forraspy")


class SolanaAnalyzer(BaseAnalyzer):
    
    chain_name = "solana"
    
    def __init__(self):
        super().__init__()
    
    # ══════════════════════════════════════════════════════════
    # TOKEN INFO
    # ══════════════════════════════════════════════════════════
    
    async def get_token_info(self, contract: str) -> Optional[TokenInfo]:
        """Busca info do token combinando múltiplas fontes"""
        token = TokenInfo(address=contract, chain="solana")
        
        # Fonte principal: DexScreener (não precisa de API key)
        dex_data = await self.get_dexscreener_data(contract)
        if dex_data:
            token.name = dex_data.get("baseToken", {}).get("name", "Unknown")
            token.symbol = dex_data.get("baseToken", {}).get("symbol", "???")
            token.price_usd = float(dex_data.get("priceUsd", 0) or 0)
            token.market_cap = float(dex_data.get("marketCap", 0) or 0)
            token.liquidity_usd = float(dex_data.get("liquidity", {}).get("usd", 0) or 0)
            token.volume_24h = float(dex_data.get("volume", {}).get("h24", 0) or 0)
            token.price_change_24h = float(dex_data.get("priceChange", {}).get("h24", 0) or 0)
            token.pair_address = dex_data.get("pairAddress", "")
            token.dex_name = dex_data.get("dexId", "")
            token.created_at = dex_data.get("pairCreatedAt")
        
        # Fonte adicional: Birdeye (dados mais ricos)
        if BIRDEYE_API_KEY:
            birdeye = await self._birdeye_token_info(contract)
            if birdeye:
                token.holder_count = birdeye.get("holder", 0)
                if not token.market_cap:
                    token.market_cap = birdeye.get("mc", 0)
                token.total_supply = birdeye.get("supply", 0)
                token.decimals = birdeye.get("decimals", 9)
        
        # Segurança via GoPlus (adaptado para Solana)
        security = await self._get_solana_security(contract)
        if security:
            token.is_honeypot = security.get("is_honeypot", False)
            token.is_mintable = security.get("is_mintable", False)
            token.owner_address = security.get("owner_address")
        
        return token if token.name != "Unknown" else None
    
    async def _birdeye_token_info(self, contract: str) -> Optional[dict]:
        """Birdeye API - info detalhada do token"""
        url = f"{ENDPOINTS['birdeye']}/defi/token_overview"
        headers = {
            "X-API-KEY": BIRDEYE_API_KEY,
            "x-chain": "solana"
        }
        data = await self._request(url, headers=headers, params={"address": contract})
        if data and data.get("success"):
            return data.get("data", {})
        return None
    
    async def _get_solana_security(self, contract: str) -> Optional[dict]:
        """GoPlus Security para Solana"""
        url = f"{ENDPOINTS['goplus']}/solana/token_security"
        data = await self._request(url, params={"contract_addresses": contract})
        if data and data.get("result"):
            return data["result"].get(contract, {})
        return None
    
    # ══════════════════════════════════════════════════════════
    # TOP HOLDERS
    # ══════════════════════════════════════════════════════════
    
    async def get_top_holders(self, contract: str, limit: int = 20) -> list[dict]:
        """Busca top holders do token"""
        holders = []
        
        # Via Helius
        if HELIUS_API_KEY:
            holders = await self._helius_top_holders(contract, limit)
        
        # Fallback: Birdeye
        if not holders and BIRDEYE_API_KEY:
            holders = await self._birdeye_top_holders(contract, limit)
        
        # Fallback: Solscan
        if not holders and SOLSCAN_API_KEY:
            holders = await self._solscan_top_holders(contract, limit)
        
        return holders[:limit]
    
    async def _helius_top_holders(self, contract: str, limit: int) -> list[dict]:
        """Top holders via Helius DAS API"""
        url = f"{ENDPOINTS['helius']}/token-metadata"
        headers = {"Content-Type": "application/json"}
        params = {"api-key": HELIUS_API_KEY}
        
        # Helius - buscar via RPC getLargestTokenAccounts
        rpc_url = SOLANA_RPC
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [contract]
        }
        
        data = await self._request(rpc_url, method="POST", json_data=payload)
        if not data or "result" not in data:
            return []
        
        holders = []
        for acc in data["result"].get("value", [])[:limit]:
            holders.append({
                "address": acc.get("address", ""),
                "amount": float(acc.get("uiAmount", 0) or acc.get("amount", 0)),
                "percentage": 0,  # Calculado depois
            })
        
        # Resolve token accounts -> owner wallets via Helius
        if HELIUS_API_KEY and holders:
            tasks = [self._resolve_token_account(h["address"]) for h in holders]
            owners = await asyncio.gather(*tasks, return_exceptions=True)
            for i, owner in enumerate(owners):
                if isinstance(owner, str):
                    holders[i]["owner"] = owner
                else:
                    holders[i]["owner"] = holders[i]["address"]
        
        return holders
    
    async def _resolve_token_account(self, token_account: str) -> str:
        """Resolve token account para owner wallet"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getAccountInfo",
            "params": [
                token_account,
                {"encoding": "jsonParsed"}
            ]
        }
        data = await self._request(SOLANA_RPC, method="POST", json_data=payload)
        if data and "result" in data:
            info = data["result"].get("value", {})
            if info:
                parsed = info.get("data", {}).get("parsed", {}).get("info", {})
                return parsed.get("owner", token_account)
        return token_account
    
    async def _birdeye_top_holders(self, contract: str, limit: int) -> list[dict]:
        """Top holders via Birdeye"""
        url = f"{ENDPOINTS['birdeye']}/defi/v3/token/holder"
        headers = {
            "X-API-KEY": BIRDEYE_API_KEY,
            "x-chain": "solana"
        }
        data = await self._request(url, headers=headers, params={
            "address": contract,
            "limit": limit
        })
        if not data or not data.get("success"):
            return []
        
        holders = []
        for item in data.get("data", {}).get("items", []):
            holders.append({
                "address": item.get("owner", ""),
                "amount": float(item.get("uiAmount", 0)),
                "percentage": float(item.get("percentage", 0)),
            })
        return holders
    
    async def _solscan_top_holders(self, contract: str, limit: int) -> list[dict]:
        """Top holders via Solscan Pro API"""
        url = f"{ENDPOINTS['solscan']}/token/holders"
        headers = {"token": SOLSCAN_API_KEY}
        data = await self._request(url, headers=headers, params={
            "address": contract,
            "page": 1,
            "page_size": limit
        })
        if not data or not data.get("success"):
            return []
        
        holders = []
        for item in data.get("data", []):
            holders.append({
                "address": item.get("owner", ""),
                "amount": float(item.get("amount", 0)),
                "percentage": float(item.get("percentage", 0)),
            })
        return holders
    
    # ══════════════════════════════════════════════════════════
    # TRADES
    # ══════════════════════════════════════════════════════════
    
    async def get_token_trades(self, contract: str, limit: int = 500) -> list[dict]:
        """Busca trades do token"""
        trades = []
        
        # Via Birdeye (melhor para trades)
        if BIRDEYE_API_KEY:
            trades = await self._birdeye_trades(contract, limit)
        
        # Fallback: Helius parsed transactions
        if not trades and HELIUS_API_KEY:
            trades = await self._helius_trades(contract, limit)
        
        return trades
    
    async def _birdeye_trades(self, contract: str, limit: int) -> list[dict]:
        """Trades via Birdeye"""
        url = f"{ENDPOINTS['birdeye']}/defi/txs/token"
        headers = {
            "X-API-KEY": BIRDEYE_API_KEY,
            "x-chain": "solana"
        }
        
        all_trades = []
        offset = 0
        page_size = min(limit, 50)
        
        while len(all_trades) < limit:
            data = await self._request(url, headers=headers, params={
                "address": contract,
                "tx_type": "swap",
                "limit": page_size,
                "offset": offset
            })
            
            if not data or not data.get("success"):
                break
            
            items = data.get("data", {}).get("items", [])
            if not items:
                break
            
            for item in items:
                trade = {
                    "tx_hash": item.get("txHash", ""),
                    "wallet": item.get("owner", ""),
                    "side": "buy" if item.get("side") == "buy" else "sell",
                    "amount": abs(float(item.get("tokenAmount", 0) or 0)),
                    "amount_usd": abs(float(item.get("volumeUSD", 0) or 0)),
                    "price": float(item.get("price", 0) or 0),
                    "timestamp": item.get("blockUnixTime", 0),
                    "source": item.get("source", ""),
                }
                all_trades.append(trade)
            
            offset += page_size
            if len(items) < page_size:
                break
            
            await asyncio.sleep(0.2)  # Rate limit gentil
        
        return all_trades[:limit]
    
    async def _helius_trades(self, contract: str, limit: int) -> list[dict]:
        """Trades via Helius Enhanced Transactions API"""
        url = f"{ENDPOINTS['helius']}/addresses/{contract}/transactions"
        params = {
            "api-key": HELIUS_API_KEY,
            "type": "SWAP",
            "limit": min(limit, 100)
        }
        
        data = await self._request(url, params=params)
        if not data:
            return []
        
        trades = []
        for tx in data:
            if tx.get("type") != "SWAP":
                continue
            
            swap = tx.get("events", {}).get("swap", {})
            if not swap:
                continue
            
            native_input = swap.get("nativeInput")
            native_output = swap.get("nativeOutput")
            token_inputs = swap.get("tokenInputs", [])
            token_outputs = swap.get("tokenOutputs", [])
            
            # Determina se é buy ou sell do token
            is_buy = any(t.get("mint") == contract for t in token_outputs)
            
            trade = {
                "tx_hash": tx.get("signature", ""),
                "wallet": tx.get("feePayer", ""),
                "side": "buy" if is_buy else "sell",
                "amount": 0,
                "amount_usd": 0,
                "price": 0,
                "timestamp": tx.get("timestamp", 0),
                "source": tx.get("source", ""),
            }
            
            # Extrai amounts
            for t in (token_outputs if is_buy else token_inputs):
                if t.get("mint") == contract:
                    trade["amount"] = float(t.get("tokenAmount", 0))
            
            trades.append(trade)
        
        return trades
    
    # ══════════════════════════════════════════════════════════
    # WALLET FUNDING
    # ══════════════════════════════════════════════════════════
    
    async def get_wallet_funding(self, wallet: str) -> dict:
        """
        Rastreia a origem dos fundos da wallet.
        Busca a primeira transação SOL recebida.
        """
        result = {
            "source": "unknown",
            "amount": 0,
            "chain": "solana",
            "tx_hash": "",
            "timestamp": None,
            "source_label": "",
        }
        
        # Via Helius - busca transações mais antigas
        if HELIUS_API_KEY:
            funding = await self._helius_wallet_funding(wallet)
            if funding:
                return funding
        
        # Fallback: Solscan
        if SOLSCAN_API_KEY:
            funding = await self._solscan_wallet_funding(wallet)
            if funding:
                return funding
        
        # Fallback: RPC direto - busca signatures
        funding = await self._rpc_wallet_funding(wallet)
        if funding:
            return funding
        
        return result
    
    async def _helius_wallet_funding(self, wallet: str) -> Optional[dict]:
        """Funding via Helius Enhanced Transactions"""
        url = f"{ENDPOINTS['helius']}/addresses/{wallet}/transactions"
        params = {
            "api-key": HELIUS_API_KEY,
            "type": "TRANSFER",
            "limit": 100,
        }
        
        data = await self._request(url, params=params)
        if not data:
            return None
        
        # Procura a primeira transferência SOL recebida
        transfers = sorted(data, key=lambda x: x.get("timestamp", float("inf")))
        
        for tx in transfers:
            native = tx.get("nativeTransfers", [])
            for t in native:
                if t.get("toUserAccount") == wallet and t.get("amount", 0) > 0:
                    amount_sol = t["amount"] / 1e9
                    return {
                        "source": t.get("fromUserAccount", "unknown"),
                        "amount": amount_sol,
                        "chain": "solana",
                        "tx_hash": tx.get("signature", ""),
                        "timestamp": tx.get("timestamp"),
                        "source_label": self._identify_known_wallet(t.get("fromUserAccount", "")),
                    }
        
        return None
    
    async def _solscan_wallet_funding(self, wallet: str) -> Optional[dict]:
        """Funding via Solscan Pro API"""
        url = f"{ENDPOINTS['solscan']}/account/transfer"
        headers = {"token": SOLSCAN_API_KEY}
        data = await self._request(url, headers=headers, params={
            "address": wallet,
            "activity_type[]": "ACTIVITY_SOL_TRANSFER",
            "flow": "in",
            "page": 1,
            "page_size": 10,
            "sort_by": "block_time",
            "sort_order": "asc"
        })
        
        if not data or not data.get("success"):
            return None
        
        items = data.get("data", [])
        if items:
            first = items[0]
            return {
                "source": first.get("from_address", "unknown"),
                "amount": float(first.get("amount", 0)) / 1e9,
                "chain": "solana",
                "tx_hash": first.get("trans_id", ""),
                "timestamp": first.get("block_time"),
                "source_label": self._identify_known_wallet(first.get("from_address", "")),
            }
        
        return None
    
    async def _rpc_wallet_funding(self, wallet: str) -> Optional[dict]:
        """Funding via RPC direto (fallback)"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [
                wallet,
                {"limit": 20, "commitment": "finalized"}
            ]
        }
        
        data = await self._request(SOLANA_RPC, method="POST", json_data=payload)
        if not data or "result" not in data:
            return None
        
        sigs = data["result"]
        if not sigs:
            return None
        
        # Pega a assinatura mais antiga
        oldest = sigs[-1]
        
        # Busca detalhes da transação
        tx_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                oldest["signature"],
                {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
            ]
        }
        
        tx_data = await self._request(SOLANA_RPC, method="POST", json_data=tx_payload)
        if not tx_data or "result" not in tx_data:
            return None
        
        tx = tx_data["result"]
        if not tx:
            return None
        
        # Extrai o sender
        instructions = (tx.get("transaction", {}).get("message", {})
                       .get("instructions", []))
        
        for ix in instructions:
            parsed = ix.get("parsed", {})
            if parsed.get("type") == "transfer":
                info = parsed.get("info", {})
                if info.get("destination") == wallet:
                    return {
                        "source": info.get("source", "unknown"),
                        "amount": float(info.get("lamports", 0)) / 1e9,
                        "chain": "solana",
                        "tx_hash": oldest["signature"],
                        "timestamp": tx.get("blockTime"),
                        "source_label": self._identify_known_wallet(info.get("source", "")),
                    }
        
        return None
    
    # ══════════════════════════════════════════════════════════
    # WALLET TRANSACTIONS & TOKENS
    # ══════════════════════════════════════════════════════════
    
    async def get_wallet_transactions(self, wallet: str, limit: int = 100) -> list[dict]:
        """Busca transações recentes da wallet"""
        if HELIUS_API_KEY:
            url = f"{ENDPOINTS['helius']}/addresses/{wallet}/transactions"
            params = {"api-key": HELIUS_API_KEY, "limit": min(limit, 100)}
            data = await self._request(url, params=params)
            if data:
                return data
        
        # Fallback: RPC
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [wallet, {"limit": limit}]
        }
        data = await self._request(SOLANA_RPC, method="POST", json_data=payload)
        if data and "result" in data:
            return data["result"]
        
        return []
    
    async def get_wallet_tokens(self, wallet: str) -> list[dict]:
        """Busca todos os tokens que a wallet possui"""
        # Via RPC
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                wallet,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ]
        }
        
        data = await self._request(SOLANA_RPC, method="POST", json_data=payload)
        if not data or "result" not in data:
            return []
        
        tokens = []
        for acc in data["result"].get("value", []):
            info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
            amount = float(info.get("tokenAmount", {}).get("uiAmount", 0) or 0)
            
            tokens.append({
                "address": info.get("mint", ""),
                "amount": amount,
                "decimals": info.get("tokenAmount", {}).get("decimals", 0),
            })
        
        return [t for t in tokens if t["amount"] > 0]
    
    # ══════════════════════════════════════════════════════════
    # WALLETS CONHECIDAS
    # ══════════════════════════════════════════════════════════
    
    def _identify_known_wallet(self, address: str) -> str:
        """Identifica wallets conhecidas (CEXs, bridges, etc)"""
        known = {
            # Binance
            "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9": "Binance",
            # Coinbase
            "H8sMJSCQxfKiFTCfDR3DUMLPwcRbM61LGFJ8N4dK3WjS": "Coinbase",
            # FTX (legacy)
            "2AQdpHJ2JpcEgPiATUXjQxA8QmafFegfQwSLWSprPicm": "FTX",
            # Raydium
            "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": "Raydium Authority",
            # Jupiter
            "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
            # Wormhole
            "worm2ZoG2kUd4vFXhvjh93UUH596ayRfgQ2MgjNMTth": "Wormhole Bridge",
            # Phantom swap
            "PhoeNiXZ8ByJGLkxNfZRnkUfjvmuYqLR89jjFHGqdXY": "Phoenix DEX",
        }
        return known.get(address, "")
