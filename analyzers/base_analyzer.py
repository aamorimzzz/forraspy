"""
FORRASPY - Analyzer Base
Classe base para todos os analyzers de chain
"""

import aiohttp
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger("forraspy")


# ══════════════════════════════════════════════════════════════
# DATA MODELS
# ══════════════════════════════════════════════════════════════

@dataclass
class TokenInfo:
    """Informações do token"""
    address: str
    name: str = "Unknown"
    symbol: str = "???"
    decimals: int = 18
    total_supply: float = 0
    price_usd: float = 0
    market_cap: float = 0
    liquidity_usd: float = 0
    volume_24h: float = 0
    price_change_24h: float = 0
    pair_address: str = ""
    dex_name: str = ""
    chain: str = ""
    created_at: Optional[int] = None
    holder_count: int = 0
    # Segurança
    is_honeypot: Optional[bool] = None
    buy_tax: Optional[float] = None
    sell_tax: Optional[float] = None
    is_mintable: Optional[bool] = None
    is_proxy: Optional[bool] = None
    owner_address: Optional[str] = None
    

@dataclass
class WalletProfile:
    """Perfil completo de uma wallet"""
    address: str
    chain: str
    
    # Dados de trading no token analisado
    total_bought: float = 0
    total_sold: float = 0
    total_bought_usd: float = 0
    total_sold_usd: float = 0
    pnl_usd: float = 0
    pnl_percent: float = 0
    current_holding: float = 0
    current_holding_usd: float = 0
    num_buys: int = 0
    num_sells: int = 0
    first_buy_time: Optional[int] = None
    last_trade_time: Optional[int] = None
    avg_buy_price: float = 0
    avg_sell_price: float = 0
    
    # Análise de funding
    funding_source: str = "unknown"
    funding_amount: float = 0
    funding_chain: str = ""
    funding_tx: str = ""
    funding_time: Optional[int] = None
    
    # Dados gerais da wallet
    wallet_age_days: int = 0
    first_seen: Optional[int] = None
    total_tokens_traded: int = 0
    total_tx_count: int = 0
    native_balance: float = 0
    
    # Conexões e correlações
    connected_wallets: list = field(default_factory=list)
    probable_other_wallets: list = field(default_factory=list)
    tokens_traded: list = field(default_factory=list)
    
    # Classificação
    is_sniper: bool = False
    is_whale: bool = False
    is_insider: bool = False
    is_bot: bool = False
    wallet_label: str = ""  # Label conhecida (ex: "Binance Hot Wallet")
    
    # Score
    similarity_scores: dict = field(default_factory=dict)


@dataclass 
class AnalysisResult:
    """Resultado completo da análise"""
    token: TokenInfo
    chain: str
    top_traders: list[WalletProfile] = field(default_factory=list)
    wallet_clusters: dict = field(default_factory=dict)
    risk_score: int = 50
    risk_flags: list = field(default_factory=list)
    analysis_time: float = 0
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


# ══════════════════════════════════════════════════════════════
# BASE ANALYZER
# ══════════════════════════════════════════════════════════════

class BaseAnalyzer(ABC):
    """Classe base para analyzers de cada chain"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._rate_limit_semaphore = asyncio.Semaphore(5)  # Max 5 requests simultâneos
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _request(
        self, 
        url: str, 
        method: str = "GET",
        headers: dict = None, 
        params: dict = None,
        json_data: dict = None,
        retries: int = 3
    ) -> Optional[dict]:
        """Request HTTP com rate limiting e retry"""
        async with self._rate_limit_semaphore:
            session = await self._get_session()
            for attempt in range(retries):
                try:
                    async with session.request(
                        method, url, 
                        headers=headers, 
                        params=params, 
                        json=json_data
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            wait = min(2 ** attempt * 2, 30)
                            logger.warning(f"Rate limited, aguardando {wait}s...")
                            await asyncio.sleep(wait)
                        else:
                            logger.error(f"HTTP {resp.status} em {url}")
                            text = await resp.text()
                            logger.debug(f"Response: {text[:200]}")
                            if attempt < retries - 1:
                                await asyncio.sleep(1)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout em {url}, tentativa {attempt+1}/{retries}")
                except Exception as e:
                    logger.error(f"Erro em {url}: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(1)
        return None

    # ── Métodos abstratos que cada chain implementa ──
    
    @abstractmethod
    async def get_token_info(self, contract: str) -> Optional[TokenInfo]:
        """Busca informações do token"""
        pass
    
    @abstractmethod
    async def get_top_holders(self, contract: str, limit: int = 20) -> list[dict]:
        """Busca os maiores holders do token"""
        pass
    
    @abstractmethod
    async def get_token_trades(self, contract: str, limit: int = 500) -> list[dict]:
        """Busca trades recentes do token"""
        pass
    
    @abstractmethod
    async def get_wallet_funding(self, wallet: str) -> dict:
        """Rastreia de onde a wallet foi fundada"""
        pass
    
    @abstractmethod
    async def get_wallet_transactions(self, wallet: str, limit: int = 100) -> list[dict]:
        """Busca transações da wallet"""
        pass
    
    @abstractmethod
    async def get_wallet_tokens(self, wallet: str) -> list[dict]:
        """Busca tokens que a wallet possui/negociou"""
        pass
    
    # ── Métodos comuns ──
    
    async def get_token_security(self, contract: str, chain_id: str = "1") -> dict:
        """
        Usa GoPlus Security API para verificar segurança do token.
        Funciona para EVM chains.
        """
        from ..config import ENDPOINTS
        url = f"{ENDPOINTS['goplus']}/token_security/{chain_id}"
        data = await self._request(url, params={"contract_addresses": contract})
        if data and data.get("result"):
            return data["result"].get(contract.lower(), {})
        return {}
    
    async def get_dexscreener_data(self, contract: str) -> Optional[dict]:
        """Busca dados do DexScreener (funciona para todas as chains)"""
        from ..config import ENDPOINTS
        url = f"{ENDPOINTS['dexscreener']}/tokens/{contract}"
        data = await self._request(url)
        if data and data.get("pairs"):
            # Retorna o par com maior liquidez
            pairs = sorted(
                data["pairs"], 
                key=lambda x: float(x.get("liquidity", {}).get("usd", 0)),
                reverse=True
            )
            return pairs[0] if pairs else None
        return None
    
    async def analyze_top_traders(self, contract: str, config=None) -> list[WalletProfile]:
        """
        Pipeline completo de análise de top traders:
        1. Busca trades do token
        2. Identifica top traders por PnL
        3. Analisa funding de cada wallet
        4. Correlaciona wallets
        """
        from ..config import ANALYSIS_CONFIG
        config = config or ANALYSIS_CONFIG
        
        logger.info(f"Buscando trades para {contract[:12]}...")
        trades = await self.get_token_trades(contract, config.max_transactions)
        if not trades:
            logger.warning("Nenhum trade encontrado")
            return []
        
        # Agrupa por wallet e calcula PnL
        wallet_stats = self._aggregate_trades(trades)
        
        # Ordena por PnL absoluto
        sorted_wallets = sorted(
            wallet_stats.values(),
            key=lambda x: abs(x.get("pnl_usd", 0)),
            reverse=True
        )[:config.top_traders_count]
        
        # Constrói perfis com análise de funding
        profiles = []
        tasks = []
        
        for stats in sorted_wallets:
            task = self._build_wallet_profile(stats, contract)
            tasks.append(task)
        
        profiles = await asyncio.gather(*tasks, return_exceptions=True)
        profiles = [p for p in profiles if isinstance(p, WalletProfile)]
        
        logger.info(f"Analisados {len(profiles)} top traders")
        return profiles
    
    def _aggregate_trades(self, trades: list) -> dict:
        """Agrupa trades por wallet e calcula estatísticas"""
        wallet_stats = {}
        
        for trade in trades:
            wallet = trade.get("wallet", "").lower()
            if not wallet:
                continue
                
            if wallet not in wallet_stats:
                wallet_stats[wallet] = {
                    "address": wallet,
                    "buys": [],
                    "sells": [],
                    "total_bought": 0,
                    "total_sold": 0,
                    "total_bought_usd": 0,
                    "total_sold_usd": 0,
                    "first_trade": trade.get("timestamp", 0),
                    "last_trade": trade.get("timestamp", 0),
                }
            
            stats = wallet_stats[wallet]
            amount = float(trade.get("amount", 0))
            amount_usd = float(trade.get("amount_usd", 0))
            ts = trade.get("timestamp", 0)
            
            if trade.get("side") == "buy":
                stats["buys"].append(trade)
                stats["total_bought"] += amount
                stats["total_bought_usd"] += amount_usd
            else:
                stats["sells"].append(trade)
                stats["total_sold"] += amount
                stats["total_sold_usd"] += amount_usd
            
            stats["first_trade"] = min(stats["first_trade"], ts) if ts else stats["first_trade"]
            stats["last_trade"] = max(stats["last_trade"], ts) if ts else stats["last_trade"]
        
        # Calcula PnL
        for wallet, stats in wallet_stats.items():
            stats["pnl_usd"] = stats["total_sold_usd"] - stats["total_bought_usd"]
            if stats["total_bought_usd"] > 0:
                stats["pnl_percent"] = (stats["pnl_usd"] / stats["total_bought_usd"]) * 100
            else:
                stats["pnl_percent"] = 0
        
        return wallet_stats
    
    async def _build_wallet_profile(self, stats: dict, contract: str) -> WalletProfile:
        """Constrói perfil completo de uma wallet"""
        address = stats["address"]
        chain = getattr(self, 'chain_name', 'unknown')
        
        profile = WalletProfile(
            address=address,
            chain=chain,
            total_bought=stats["total_bought"],
            total_sold=stats["total_sold"],
            total_bought_usd=stats["total_bought_usd"],
            total_sold_usd=stats["total_sold_usd"],
            pnl_usd=stats["pnl_usd"],
            pnl_percent=stats.get("pnl_percent", 0),
            num_buys=len(stats["buys"]),
            num_sells=len(stats["sells"]),
            first_buy_time=stats.get("first_trade"),
            last_trade_time=stats.get("last_trade"),
        )
        
        # Análise de funding
        try:
            funding = await self.get_wallet_funding(address)
            if funding:
                profile.funding_source = funding.get("source", "unknown")
                profile.funding_amount = funding.get("amount", 0)
                profile.funding_chain = funding.get("chain", chain)
                profile.funding_tx = funding.get("tx_hash", "")
                profile.funding_time = funding.get("timestamp")
        except Exception as e:
            logger.error(f"Erro ao buscar funding de {address[:12]}: {e}")
        
        # Busca outros tokens da wallet (para correlação)
        try:
            tokens = await self.get_wallet_tokens(address)
            profile.tokens_traded = [t.get("address", "") for t in tokens[:50]]
            profile.total_tokens_traded = len(tokens)
        except Exception as e:
            logger.debug(f"Erro ao buscar tokens de {address[:12]}: {e}")
        
        # Classifica wallet
        profile = self._classify_wallet(profile, stats)
        
        return profile
    
    def _classify_wallet(self, profile: WalletProfile, stats: dict) -> WalletProfile:
        """Classifica o tipo da wallet baseado no comportamento"""
        # Sniper: comprou muito cedo, poucas transações
        if profile.first_buy_time and profile.num_buys <= 3:
            profile.is_sniper = True
        
        # Bot: muitas transações em curto período
        if profile.num_buys + profile.num_sells > 50:
            time_span = (profile.last_trade_time or 0) - (profile.first_buy_time or 0)
            if time_span < 3600 and time_span > 0:  # Menos de 1h
                profile.is_bot = True
        
        # Whale: grande volume
        if profile.total_bought_usd > 10000:
            profile.is_whale = True
        
        # Insider: comprou antes de grande pump e vendeu no topo
        if profile.pnl_percent > 500 and profile.num_buys <= 5:
            profile.is_insider = True
        
        return profile
    
    async def find_wallet_connections(self, profiles: list[WalletProfile]) -> dict:
        """
        Encontra conexões entre wallets:
        - Mesma fonte de funding
        - Padrões de trading similares
        - Tokens em comum
        """
        from ..utils.helpers import calculate_wallet_similarity
        
        connections = {}
        clusters = {}
        
        # Agrupa por funding source
        for p in profiles:
            src = p.funding_source
            if src and src != "unknown":
                if src not in clusters:
                    clusters[src] = []
                clusters[src].append(p.address)
        
        # Calcula similaridade entre todos os pares
        for i, p1 in enumerate(profiles):
            for p2 in profiles[i+1:]:
                sim = calculate_wallet_similarity(
                    {
                        "funding_source": p1.funding_source,
                        "tokens_traded": p1.tokens_traded,
                        "first_seen": p1.first_buy_time,
                        "avg_trade_size": p1.total_bought_usd / max(p1.num_buys, 1)
                    },
                    {
                        "funding_source": p2.funding_source,
                        "tokens_traded": p2.tokens_traded,
                        "first_seen": p2.first_buy_time,
                        "avg_trade_size": p2.total_bought_usd / max(p2.num_buys, 1)
                    }
                )
                
                if sim >= 0.5:
                    key = f"{p1.address[:8]}-{p2.address[:8]}"
                    connections[key] = {
                        "wallet_a": p1.address,
                        "wallet_b": p2.address,
                        "similarity": sim,
                        "reasons": self._get_connection_reasons(p1, p2, sim)
                    }
                    
                    # Marca como possível outra wallet
                    p1.probable_other_wallets.append({
                        "address": p2.address,
                        "confidence": sim
                    })
                    p2.probable_other_wallets.append({
                        "address": p1.address,
                        "confidence": sim
                    })
        
        return {
            "connections": connections,
            "funding_clusters": {k: v for k, v in clusters.items() if len(v) > 1}
        }
    
    def _get_connection_reasons(self, p1: WalletProfile, p2: WalletProfile, sim: float) -> list:
        """Lista razões da conexão entre wallets"""
        reasons = []
        
        if p1.funding_source == p2.funding_source and p1.funding_source != "unknown":
            reasons.append(f"Mesma fonte de funding: {p1.funding_source[:12]}...")
        
        tokens1 = set(p1.tokens_traded)
        tokens2 = set(p2.tokens_traded)
        common = tokens1 & tokens2
        if len(common) > 3:
            reasons.append(f"{len(common)} tokens em comum")
        
        if p1.first_buy_time and p2.first_buy_time:
            diff = abs(p1.first_buy_time - p2.first_buy_time)
            if diff < 300:
                reasons.append("Compras quase simultâneas (<5min)")
            elif diff < 3600:
                reasons.append("Compras na mesma hora")
        
        return reasons

    async def full_analysis(self, contract: str) -> AnalysisResult:
        """
        Executa análise completa:
        1. Info do token
        2. Top traders + PnL
        3. Funding analysis
        4. Wallet connections
        5. Risk assessment
        """
        import time
        start = time.time()
        
        # 1. Token info
        logger.info(f"[1/5] Buscando info do token...")
        token = await self.get_token_info(contract)
        if not token:
            raise ValueError(f"Token não encontrado: {contract}")
        
        # 2. Top traders
        logger.info(f"[2/5] Analisando top traders...")
        traders = await self.analyze_top_traders(contract)
        
        # 3. Conexões (já inclui funding)
        logger.info(f"[3/5] Buscando conexões entre wallets...")
        connections = await self.find_wallet_connections(traders)
        
        # 4. Risk assessment
        logger.info(f"[4/5] Avaliando riscos...")
        risk_score, risk_flags = self._assess_risk(token, traders, connections)
        
        elapsed = time.time() - start
        logger.info(f"[5/5] Análise completa em {elapsed:.1f}s")
        
        return AnalysisResult(
            token=token,
            chain=getattr(self, 'chain_name', 'unknown'),
            top_traders=traders,
            wallet_clusters=connections,
            risk_score=risk_score,
            risk_flags=risk_flags,
            analysis_time=elapsed,
        )
    
    def _assess_risk(self, token: TokenInfo, traders: list, connections: dict) -> tuple[int, list]:
        """Avalia score de risco do token (0=scam, 100=seguro)"""
        score = 70  # Base
        flags = []
        
        # Token checks
        if token.is_honeypot:
            score -= 50
            flags.append("🍯 HONEYPOT DETECTADO")
        
        if token.buy_tax and token.buy_tax > 5:
            score -= 15
            flags.append(f"💸 Buy tax alta: {token.buy_tax}%")
        
        if token.sell_tax and token.sell_tax > 5:
            score -= 20
            flags.append(f"💸 Sell tax alta: {token.sell_tax}%")
        
        if token.is_mintable:
            score -= 10
            flags.append("⚠️ Token mintável (supply pode aumentar)")
        
        if token.liquidity_usd < 5000:
            score -= 15
            flags.append(f"💧 Liquidez baixa: ${token.liquidity_usd:,.0f}")
        
        if token.holder_count < 50:
            score -= 10
            flags.append(f"👥 Poucos holders: {token.holder_count}")
        
        # Trader behavior checks
        insiders = [t for t in traders if t.is_insider]
        if len(insiders) > 2:
            score -= 15
            flags.append(f"🕵️ {len(insiders)} possíveis insiders detectados")
        
        snipers = [t for t in traders if t.is_sniper]
        if len(snipers) > 5:
            score -= 10
            flags.append(f"🎯 {len(snipers)} snipers detectados")
        
        # Connection checks
        funding_clusters = connections.get("funding_clusters", {})
        if len(funding_clusters) > 2:
            score -= 15
            flags.append(f"🔗 {len(funding_clusters)} clusters de wallets conectadas")
        
        for cluster_id, wallets in funding_clusters.items():
            if len(wallets) > 3:
                score -= 10
                flags.append(f"⚠️ {len(wallets)} wallets da mesma fonte")
                break
        
        score = max(0, min(100, score))
        
        if not flags:
            flags.append("✅ Nenhum red flag detectado")
        
        return score, flags
