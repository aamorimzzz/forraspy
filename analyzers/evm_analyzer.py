"""
FORRASPY - EVM Analyzer (Base & BSC)
Análise de tokens e wallets em chains EVM
APIs: Basescan/BSCScan, Moralis, DexScreener, GoPlus
"""

import asyncio
import logging
from typing import Optional

from .base_analyzer import BaseAnalyzer, TokenInfo, WalletProfile
from ..config import (
    BASESCAN_API_KEY, BSCSCAN_API_KEY, MORALIS_API_KEY,
    BASE_RPC, BSC_RPC, ENDPOINTS, CHAIN_IDS, ANALYSIS_CONFIG
)

logger = logging.getLogger("forraspy")


class EVMAnalyzer(BaseAnalyzer):
    """Analyzer para chains EVM (Base e BSC)"""
    
    def __init__(self, chain: str = "base"):
        super().__init__()
        self.chain = chain.lower()
        self.chain_name = chain.lower()
        
        if self.chain == "base":
            self.explorer_api = ENDPOINTS["basescan"]
            self.api_key = BASESCAN_API_KEY
            self.rpc_url = BASE_RPC
            self.chain_id = CHAIN_IDS["base"]
            self.native_symbol = "ETH"
            self.native_decimals = 18
        elif self.chain == "bsc":
            self.explorer_api = ENDPOINTS["bscscan"]
            self.api_key = BSCSCAN_API_KEY
            self.rpc_url = BSC_RPC
            self.chain_id = CHAIN_IDS["bsc"]
            self.native_symbol = "BNB"
            self.native_decimals = 18
        else:
            raise ValueError(f"Chain não suportada: {chain}")
    
    # ══════════════════════════════════════════════════════════
    # TOKEN INFO
    # ══════════════════════════════════════════════════════════
    
    async def get_token_info(self, contract: str) -> Optional[TokenInfo]:
        """Busca info do token combinando múltiplas fontes"""
        contract = contract.lower()
        token = TokenInfo(address=contract, chain=self.chain)
        
        # DexScreener (principal, sem API key)
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
        
        # Explorer API (supply, decimals)
        explorer_data = await self._explorer_token_info(contract)
        if explorer_data:
            token.total_supply = float(explorer_data.get("totalSupply", 0))
            token.decimals = int(explorer_data.get("decimals", 18))
        
        # Moralis (holders e dados extras)
        if MORALIS_API_KEY:
            moralis_data = await self._moralis_token_info(contract)
            if moralis_data:
                token.holder_count = moralis_data.get("holder_count", 0)
                if not token.total_supply:
                    token.total_supply = float(moralis_data.get("total_supply_formatted", 0))
        
        # GoPlus Security Check
        security = await self.get_token_security(contract, str(self.chain_id))
        if security:
            token.is_honeypot = security.get("is_honeypot") == "1"
            token.buy_tax = float(security.get("buy_tax", 0) or 0) * 100
            token.sell_tax = float(security.get("sell_tax", 0) or 0) * 100
            token.is_mintable = security.get("is_mintable") == "1"
            token.is_proxy = security.get("is_proxy") == "1"
            token.owner_address = security.get("owner_address")
        
        return token if token.name != "Unknown" else None
    
    async def _explorer_token_info(self, contract: str) -> Optional[dict]:
        """Info via Basescan/BSCScan API"""
        if not self.api_key:
            return None
        
        # Token supply
        data = await self._request(self.explorer_api, params={
            "module": "stats",
            "action": "tokensupply",
            "contractaddress": contract,
            "apikey": self.api_key
        })
        
        result = {}
        if data and data.get("status") == "1":
            result["totalSupply"] = data.get("result", "0")
        
        # Token info via source code (para decimals)
        abi_data = await self._request(self.explorer_api, params={
            "module": "contract",
            "action": "getabi",
            "address": contract,
            "apikey": self.api_key
        })
        
        if abi_data and abi_data.get("status") == "1":
            result["has_verified_source"] = True
        
        return result if result else None
    
    async def _moralis_token_info(self, contract: str) -> Optional[dict]:
        """Info via Moralis API"""
        chain_map = {"base": "base", "bsc": "bsc"}
        chain_param = chain_map.get(self.chain, self.chain)
        
        url = f"{ENDPOINTS['moralis']}/erc20/metadata"
        headers = {"X-API-Key": MORALIS_API_KEY}
        data = await self._request(url, headers=headers, params={
            "chain": chain_param,
            "addresses[]": contract
        })
        
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None
    
    # ══════════════════════════════════════════════════════════
    # TOP HOLDERS
    # ══════════════════════════════════════════════════════════
    
    async def get_top_holders(self, contract: str, limit: int = 20) -> list[dict]:
        """Busca top holders via Moralis ou Explorer"""
        holders = []
        
        # Via Moralis (melhor para holders)
        if MORALIS_API_KEY:
            holders = await self._moralis_top_holders(contract, limit)
        
        # Fallback: Explorer API (token transfers -> calcular holders)
        if not holders:
            holders = await self._explorer_top_holders(contract, limit)
        
        return holders[:limit]
    
    async def _moralis_top_holders(self, contract: str, limit: int) -> list[dict]:
        """Top holders via Moralis"""
        chain_map = {"base": "base", "bsc": "bsc"}
        url = f"{ENDPOINTS['moralis']}/erc20/{contract}/owners"
        headers = {"X-API-Key": MORALIS_API_KEY}
        
        data = await self._request(url, headers=headers, params={
            "chain": chain_map.get(self.chain, self.chain),
            "limit": limit,
            "order": "DESC"
        })
        
        if not data or "result" not in data:
            return []
        
        holders = []
        for item in data["result"]:
            balance = float(item.get("balance_formatted", 0))
            holders.append({
                "address": item.get("owner_address", ""),
                "owner": item.get("owner_address", ""),
                "amount": balance,
                "percentage": float(item.get("percentage_relative_to_total_supply", 0)),
            })
        
        return holders
    
    async def _explorer_top_holders(self, contract: str, limit: int) -> list[dict]:
        """
        Reconstrói top holders a partir de transfers.
        Menos preciso que Moralis, mas funciona sem API key premium.
        """
        if not self.api_key:
            return []
        
        # Busca últimas 1000 transfers
        data = await self._request(self.explorer_api, params={
            "module": "account",
            "action": "tokentx",
            "contractaddress": contract,
            "page": 1,
            "offset": 1000,
            "sort": "desc",
            "apikey": self.api_key
        })
        
        if not data or data.get("status") != "1":
            return []
        
        # Calcula balances
        balances = {}
        for tx in data.get("result", []):
            from_addr = tx.get("from", "").lower()
            to_addr = tx.get("to", "").lower()
            value = float(tx.get("value", 0))
            decimals = int(tx.get("tokenDecimal", 18))
            amount = value / (10 ** decimals)
            
            if from_addr:
                balances[from_addr] = balances.get(from_addr, 0) - amount
            if to_addr:
                balances[to_addr] = balances.get(to_addr, 0) + amount
        
        # Ordena por balance
        sorted_holders = sorted(
            [(addr, bal) for addr, bal in balances.items() if bal > 0],
            key=lambda x: x[1],
            reverse=True
        )
        
        holders = []
        for addr, bal in sorted_holders[:limit]:
            holders.append({
                "address": addr,
                "owner": addr,
                "amount": bal,
                "percentage": 0,
            })
        
        return holders
    
    # ══════════════════════════════════════════════════════════
    # TRADES
    # ══════════════════════════════════════════════════════════
    
    async def get_token_trades(self, contract: str, limit: int = 500) -> list[dict]:
        """
        Busca trades do token.
        Combina Explorer API (token transfers) com DEX data.
        """
        trades = []
        
        # Via Moralis (melhor: inclui decoded swaps)
        if MORALIS_API_KEY:
            trades = await self._moralis_token_trades(contract, limit)
        
        # Fallback: Explorer token transfers
        if not trades:
            trades = await self._explorer_token_trades(contract, limit)
        
        return trades
    
    async def _moralis_token_trades(self, contract: str, limit: int) -> list[dict]:
        """Trades via Moralis Token Transfers"""
        chain_map = {"base": "base", "bsc": "bsc"}
        url = f"{ENDPOINTS['moralis']}/erc20/{contract}/transfers"
        headers = {"X-API-Key": MORALIS_API_KEY}
        
        all_trades = []
        cursor = None
        
        while len(all_trades) < limit:
            params = {
                "chain": chain_map.get(self.chain, self.chain),
                "limit": min(limit - len(all_trades), 100),
            }
            if cursor:
                params["cursor"] = cursor
            
            data = await self._request(url, headers=headers, params=params)
            if not data:
                break
            
            for item in data.get("result", []):
                value = float(item.get("value_decimal", 0) or item.get("value", 0))
                
                # Determina se é buy ou sell baseado no from/to
                from_addr = item.get("from_address", "").lower()
                to_addr = item.get("to_address", "").lower()
                
                # Se vem de um router/pool, é buy. Se vai para, é sell.
                trade = {
                    "tx_hash": item.get("transaction_hash", ""),
                    "wallet": to_addr,  # Default: quem recebeu
                    "side": "buy",  # Default: será refinado
                    "amount": abs(value),
                    "amount_usd": float(item.get("value_decimal", 0) or 0),
                    "price": 0,
                    "timestamp": 0,
                    "block": int(item.get("block_number", 0)),
                    "from": from_addr,
                    "to": to_addr,
                }
                
                # Tenta extrair timestamp
                if item.get("block_timestamp"):
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(
                            item["block_timestamp"].replace("Z", "+00:00")
                        )
                        trade["timestamp"] = int(dt.timestamp())
                    except:
                        pass
                
                # Heurística: se from é um router known, é buy para to_addr
                if self._is_dex_router(from_addr):
                    trade["wallet"] = to_addr
                    trade["side"] = "buy"
                elif self._is_dex_router(to_addr):
                    trade["wallet"] = from_addr
                    trade["side"] = "sell"
                
                all_trades.append(trade)
            
            cursor = data.get("cursor")
            if not cursor:
                break
            
            await asyncio.sleep(0.25)
        
        return all_trades[:limit]
    
    async def _explorer_token_trades(self, contract: str, limit: int) -> list[dict]:
        """Trades via Explorer API (Basescan/BSCScan)"""
        if not self.api_key:
            return []
        
        trades = []
        page = 1
        per_page = min(limit, 100)
        
        while len(trades) < limit:
            data = await self._request(self.explorer_api, params={
                "module": "account",
                "action": "tokentx",
                "contractaddress": contract,
                "page": page,
                "offset": per_page,
                "sort": "desc",
                "apikey": self.api_key
            })
            
            if not data or data.get("status") != "1":
                break
            
            results = data.get("result", [])
            if not results:
                break
            
            for tx in results:
                value = float(tx.get("value", 0))
                decimals = int(tx.get("tokenDecimal", 18))
                amount = value / (10 ** decimals)
                
                from_addr = tx.get("from", "").lower()
                to_addr = tx.get("to", "").lower()
                
                trade = {
                    "tx_hash": tx.get("hash", ""),
                    "wallet": to_addr,
                    "side": "buy",
                    "amount": amount,
                    "amount_usd": 0,  # Explorer não dá USD
                    "price": 0,
                    "timestamp": int(tx.get("timeStamp", 0)),
                    "block": int(tx.get("blockNumber", 0)),
                    "from": from_addr,
                    "to": to_addr,
                    "gas_price": int(tx.get("gasPrice", 0)),
                }
                
                if self._is_dex_router(from_addr):
                    trade["wallet"] = to_addr
                    trade["side"] = "buy"
                elif self._is_dex_router(to_addr):
                    trade["wallet"] = from_addr
                    trade["side"] = "sell"
                
                trades.append(trade)
            
            page += 1
            if len(results) < per_page:
                break
            
            await asyncio.sleep(0.3)  # Rate limit
        
        return trades[:limit]
    
    # ══════════════════════════════════════════════════════════
    # WALLET FUNDING
    # ══════════════════════════════════════════════════════════
    
    async def get_wallet_funding(self, wallet: str) -> dict:
        """
        Rastreia de onde a wallet recebeu o primeiro ETH/BNB.
        """
        result = {
            "source": "unknown",
            "amount": 0,
            "chain": self.chain,
            "tx_hash": "",
            "timestamp": None,
            "source_label": "",
        }
        
        if not self.api_key:
            return result
        
        # Busca transações normais (ETH/BNB), ordenadas por mais antiga
        data = await self._request(self.explorer_api, params={
            "module": "account",
            "action": "txlist",
            "address": wallet,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 50,
            "sort": "asc",
            "apikey": self.api_key
        })
        
        if not data or data.get("status") != "1":
            return result
        
        # Encontra primeira TX recebida com valor
        for tx in data.get("result", []):
            to_addr = tx.get("to", "").lower()
            value = int(tx.get("value", 0))
            
            if to_addr == wallet.lower() and value > 0:
                amount = value / (10 ** self.native_decimals)
                from_addr = tx.get("from", "")
                
                return {
                    "source": from_addr,
                    "amount": amount,
                    "chain": self.chain,
                    "tx_hash": tx.get("hash", ""),
                    "timestamp": int(tx.get("timeStamp", 0)),
                    "source_label": self._identify_known_wallet(from_addr),
                }
        
        # Verifica internal transactions (pode ter sido fundada via contract)
        int_data = await self._request(self.explorer_api, params={
            "module": "account",
            "action": "txlistinternal",
            "address": wallet,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 20,
            "sort": "asc",
            "apikey": self.api_key
        })
        
        if int_data and int_data.get("status") == "1":
            for tx in int_data.get("result", []):
                if tx.get("to", "").lower() == wallet.lower() and int(tx.get("value", 0)) > 0:
                    amount = int(tx["value"]) / (10 ** self.native_decimals)
                    from_addr = tx.get("from", "")
                    return {
                        "source": from_addr,
                        "amount": amount,
                        "chain": self.chain,
                        "tx_hash": tx.get("hash", ""),
                        "timestamp": int(tx.get("timeStamp", 0)),
                        "source_label": self._identify_known_wallet(from_addr),
                    }
        
        return result
    
    # ══════════════════════════════════════════════════════════
    # WALLET TRANSACTIONS & TOKENS
    # ══════════════════════════════════════════════════════════
    
    async def get_wallet_transactions(self, wallet: str, limit: int = 100) -> list[dict]:
        """Busca transações recentes da wallet"""
        if not self.api_key:
            return []
        
        data = await self._request(self.explorer_api, params={
            "module": "account",
            "action": "txlist",
            "address": wallet,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": limit,
            "sort": "desc",
            "apikey": self.api_key
        })
        
        if data and data.get("status") == "1":
            return data.get("result", [])
        return []
    
    async def get_wallet_tokens(self, wallet: str) -> list[dict]:
        """Busca tokens que a wallet possui"""
        tokens = []
        
        # Via Moralis
        if MORALIS_API_KEY:
            chain_map = {"base": "base", "bsc": "bsc"}
            url = f"{ENDPOINTS['moralis']}/{wallet}/erc20"
            headers = {"X-API-Key": MORALIS_API_KEY}
            
            data = await self._request(url, headers=headers, params={
                "chain": chain_map.get(self.chain, self.chain)
            })
            
            if data:
                for item in data if isinstance(data, list) else data.get("result", []):
                    tokens.append({
                        "address": item.get("token_address", ""),
                        "symbol": item.get("symbol", ""),
                        "name": item.get("name", ""),
                        "amount": float(item.get("balance_formatted", 0) or 0),
                    })
                return tokens
        
        # Fallback: Explorer token transfers (reconstrói balance)
        if self.api_key:
            data = await self._request(self.explorer_api, params={
                "module": "account",
                "action": "tokentx",
                "address": wallet,
                "page": 1,
                "offset": 200,
                "sort": "desc",
                "apikey": self.api_key
            })
            
            if data and data.get("status") == "1":
                token_set = set()
                for tx in data.get("result", []):
                    addr = tx.get("contractAddress", "").lower()
                    if addr not in token_set:
                        token_set.add(addr)
                        tokens.append({
                            "address": addr,
                            "symbol": tx.get("tokenSymbol", ""),
                            "name": tx.get("tokenName", ""),
                            "amount": 0,  # Precisaria calcular
                        })
        
        return tokens
    
    # ══════════════════════════════════════════════════════════
    # DEX ROUTERS & KNOWN WALLETS
    # ══════════════════════════════════════════════════════════
    
    def _is_dex_router(self, address: str) -> bool:
        """Verifica se endereço é um DEX router"""
        address = address.lower()
        
        # Uniswap V2/V3 routers
        known_routers = {
            # Uniswap
            "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",  # Uniswap V2 Router
            "0xe592427a0aece92de3edee1f18e0157c05861564",  # Uniswap V3 Router
            "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",  # Uniswap V3 Router 2
            "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad",  # Uniswap Universal Router
            # PancakeSwap (BSC)
            "0x10ed43c718714eb63d5aa57b78b54704e256024e",  # PancakeSwap V2
            "0x13f4ea83d0bd40e75c8222255bc855a974568dd4",  # PancakeSwap V3
            "0x1b81d678ffb9c0263b24a97847620c99d213eb14",  # PancakeSwap Universal
            # Base DEXs
            "0x2626664c2603336e57b271c5c0b26f421741e481",  # Uniswap V3 (Base)
            "0x198ef79f1f515f02dfe9e3115ed9fc07183f02fc",  # BaseSwap Router
            # Aerodrome (Base)
            "0xcf77a3ba9a5ca399b7c97c74d54e5b1beb874e43",  # Aerodrome Router
        }
        
        return address in known_routers
    
    def _identify_known_wallet(self, address: str) -> str:
        """Identifica wallets conhecidas (CEXs, bridges, etc)"""
        address = address.lower()
        
        known = {
            # Binance
            "0x28c6c06298d514db089934071355e5743bf21d60": "Binance Hot Wallet",
            "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance Hot Wallet 2",
            "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance Hot Wallet 3",
            "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance Hot Wallet 8",
            # Coinbase
            "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase Hot Wallet",
            "0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43": "Coinbase Commerce",
            # OKX
            "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX Hot Wallet",
            # Bridges
            "0x3154cf16ccdb4c6d922629664174b904d80f2c35": "Base Bridge",
            "0x49048044d57e1c92a77f79988d21fa8faf74e97e": "Base Portal",
        }
        
        return known.get(address, "")
