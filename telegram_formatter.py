"""
FORRASPY - Formatador de Mensagens Telegram
Gera mensagens formatadas bonitas para o bot
"""

from ..analyzers.base_analyzer import AnalysisResult, WalletProfile, TokenInfo
from ..utils.helpers import (
    shorten_address, format_usd, format_token_amount, 
    format_percentage, format_time_ago, risk_score_emoji,
    build_explorer_link
)


def format_token_overview(result: AnalysisResult) -> str:
    """Formata overview do token para Telegram"""
    t = result.token
    chain_emoji = {"solana": "◎", "base": "🔵", "bsc": "🟡"}.get(result.chain, "⛓")
    
    msg = f"""
🔍 <b>FORRASPY — Análise de Token</b>

{chain_emoji} <b>{t.name}</b> (${t.symbol})
📋 <code>{t.address}</code>

💰 <b>Preço:</b> {format_usd(t.price_usd)}
📊 <b>Market Cap:</b> {format_usd(t.market_cap)}
💧 <b>Liquidez:</b> {format_usd(t.liquidity_usd)}
📈 <b>Volume 24h:</b> {format_usd(t.volume_24h)}
{format_percentage(t.price_change_24h)} <b>24h</b>
👥 <b>Holders:</b> {t.holder_count:,}
🏦 <b>DEX:</b> {t.dex_name or 'N/A'}

━━━━━━━━━━━━━━━━━━━━━
"""
    
    # Security section
    if t.is_honeypot is not None:
        msg += "\n🛡 <b>SEGURANÇA</b>\n"
        msg += f"  {'🍯 HONEYPOT!' if t.is_honeypot else '✅ Não é honeypot'}\n"
        
        if t.buy_tax is not None:
            tax_emoji = "⚠️" if t.buy_tax > 5 else "✅"
            msg += f"  {tax_emoji} Buy Tax: {t.buy_tax:.1f}%\n"
        
        if t.sell_tax is not None:
            tax_emoji = "⚠️" if t.sell_tax > 5 else "✅"
            msg += f"  {tax_emoji} Sell Tax: {t.sell_tax:.1f}%\n"
        
        if t.is_mintable is not None:
            msg += f"  {'⚠️ Mintável' if t.is_mintable else '✅ Não mintável'}\n"
        
        if t.is_proxy is not None:
            msg += f"  {'⚠️ Proxy contract' if t.is_proxy else '✅ Sem proxy'}\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    # Risk score
    msg += f"\n🎯 <b>Risk Score:</b> {result.risk_score}/100 — {risk_score_emoji(result.risk_score)}\n"
    
    if result.risk_flags:
        for flag in result.risk_flags[:5]:
            msg += f"  {flag}\n"
    
    msg += f"\n⏱ Análise em {result.analysis_time:.1f}s"
    
    return msg.strip()


def format_top_traders(result: AnalysisResult, page: int = 0, per_page: int = 5) -> str:
    """Formata lista de top traders paginada"""
    traders = result.top_traders
    start = page * per_page
    end = start + per_page
    page_traders = traders[start:end]
    total_pages = (len(traders) + per_page - 1) // per_page
    
    if not page_traders:
        return "❌ Nenhum trader encontrado."
    
    chain = result.chain
    msg = f"👥 <b>TOP TRADERS</b> — ${result.token.symbol}\n"
    msg += f"📄 Página {page + 1}/{total_pages} ({len(traders)} total)\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, t in enumerate(page_traders, start + 1):
        # Badges
        badges = []
        if t.is_sniper: badges.append("🎯")
        if t.is_whale: badges.append("🐋")
        if t.is_insider: badges.append("🕵️")
        if t.is_bot: badges.append("🤖")
        badge_str = " ".join(badges) if badges else ""
        
        # PnL emoji
        pnl_emoji = "🟢" if t.pnl_usd > 0 else "🔴"
        
        explorer_link = build_explorer_link(t.address, chain)
        
        msg += f"<b>#{i} {badge_str}</b>\n"
        msg += f"  📍 <a href='{explorer_link}'>{shorten_address(t.address)}</a>\n"
        msg += f"  {pnl_emoji} PnL: {format_usd(t.pnl_usd)} ({t.pnl_percent:+.1f}%)\n"
        msg += f"  💵 Comprou: {format_usd(t.total_bought_usd)} ({t.num_buys}x)\n"
        msg += f"  💵 Vendeu: {format_usd(t.total_sold_usd)} ({t.num_sells}x)\n"
        
        if t.funding_source and t.funding_source != "unknown":
            label = t.wallet_label or shorten_address(t.funding_source)
            msg += f"  🏦 Funding: {label}\n"
        
        if t.probable_other_wallets:
            msg += f"  🔗 {len(t.probable_other_wallets)} wallet(s) conectada(s)\n"
        
        msg += "\n"
    
    # Legenda
    msg += "━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🎯 Sniper  🐋 Whale  🕵️ Insider  🤖 Bot\n"
    
    return msg.strip()


def format_wallet_detail(wallet: WalletProfile) -> str:
    """Formata detalhes de uma wallet específica"""
    chain = wallet.chain
    explorer_link = build_explorer_link(wallet.address, chain)
    
    # Badges
    badges = []
    if wallet.is_sniper: badges.append("🎯 Sniper")
    if wallet.is_whale: badges.append("🐋 Whale")
    if wallet.is_insider: badges.append("🕵️ Provável Insider")
    if wallet.is_bot: badges.append("🤖 Bot")
    badge_str = " | ".join(badges) if badges else "👤 Trader Normal"
    
    pnl_emoji = "🟢" if wallet.pnl_usd > 0 else "🔴"
    
    msg = f"""
🔎 <b>DETALHE DA WALLET</b>

📍 <a href='{explorer_link}'><code>{wallet.address}</code></a>
⛓ <b>Chain:</b> {chain.upper()}
🏷 <b>Tipo:</b> {badge_str}
{f"🏷 <b>Label:</b> {wallet.wallet_label}" if wallet.wallet_label else ""}

━━ <b>TRADING</b> ━━━━━━━━━━━━━
{pnl_emoji} <b>PnL:</b> {format_usd(wallet.pnl_usd)} ({wallet.pnl_percent:+.1f}%)
💵 Comprado: {format_usd(wallet.total_bought_usd)} ({wallet.num_buys} txs)
💵 Vendido: {format_usd(wallet.total_sold_usd)} ({wallet.num_sells} txs)
📊 Holding atual: {format_token_amount(wallet.current_holding)}

━━ <b>FUNDING</b> ━━━━━━━━━━━━━
🏦 <b>Origem:</b> {shorten_address(wallet.funding_source) if wallet.funding_source != 'unknown' else '❓ Desconhecida'}
💰 <b>Valor:</b> {wallet.funding_amount:.4f} {wallet.funding_chain.upper() if wallet.funding_chain else ''}
"""
    
    if wallet.funding_source and wallet.funding_source != "unknown":
        fund_link = build_explorer_link(wallet.funding_source, chain)
        msg += f"🔗 <a href='{fund_link}'>Ver funding source</a>\n"
    
    if wallet.funding_tx:
        tx_link = build_explorer_link(wallet.funding_tx, chain, "tx")
        msg += f"📝 <a href='{tx_link}'>Ver TX de funding</a>\n"
    
    if wallet.funding_time:
        msg += f"📅 Funding: {format_time_ago(wallet.funding_time)}\n"
    
    # Connections
    if wallet.probable_other_wallets:
        msg += "\n━━ <b>WALLETS CONECTADAS</b> ━━━━━━\n"
        for conn in wallet.probable_other_wallets[:5]:
            addr = conn.get("address", "")
            conf = conn.get("confidence", 0)
            conf_bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            link = build_explorer_link(addr, chain)
            msg += f"  🔗 <a href='{link}'>{shorten_address(addr)}</a>\n"
            msg += f"     Confiança: [{conf_bar}] {conf*100:.0f}%\n"
    
    # Profile info
    msg += f"\n━━ <b>PERFIL</b> ━━━━━━━━━━━━━━━\n"
    msg += f"📊 Tokens negociados: {wallet.total_tokens_traded}\n"
    
    if wallet.first_buy_time:
        msg += f"📅 1ª compra: {format_time_ago(wallet.first_buy_time)}\n"
    
    if wallet.last_trade_time:
        msg += f"📅 Último trade: {format_time_ago(wallet.last_trade_time)}\n"
    
    return msg.strip()


def format_connections_summary(result: AnalysisResult) -> str:
    """Formata resumo das conexões entre wallets"""
    clusters = result.wallet_clusters
    connections = clusters.get("connections", {})
    funding_clusters = clusters.get("funding_clusters", {})
    chain = result.chain
    
    if not connections and not funding_clusters:
        return "✅ Nenhuma conexão suspeita encontrada entre os top traders."
    
    msg = f"🔗 <b>CONEXÕES ENTRE WALLETS</b> — ${result.token.symbol}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Funding clusters
    if funding_clusters:
        msg += "🏦 <b>CLUSTERS POR FUNDING</b>\n"
        msg += "(Wallets fundadas pela mesma fonte)\n\n"
        
        for source, wallets in list(funding_clusters.items())[:5]:
            source_link = build_explorer_link(source, chain)
            msg += f"  📍 Fonte: <a href='{source_link}'>{shorten_address(source)}</a>\n"
            msg += f"  👥 {len(wallets)} wallets:\n"
            for w in wallets[:5]:
                w_link = build_explorer_link(w, chain)
                msg += f"    ├─ <a href='{w_link}'>{shorten_address(w)}</a>\n"
            if len(wallets) > 5:
                msg += f"    └─ ... +{len(wallets)-5} mais\n"
            msg += "\n"
    
    # Direct connections
    if connections:
        msg += "🔗 <b>CONEXÕES DIRETAS</b>\n"
        msg += "(Wallets com alta similaridade)\n\n"
        
        sorted_conns = sorted(
            connections.values(), 
            key=lambda x: x["similarity"], 
            reverse=True
        )
        
        for conn in sorted_conns[:8]:
            sim = conn["similarity"]
            sim_bar = "█" * int(sim * 10) + "░" * (10 - int(sim * 10))
            
            a_link = build_explorer_link(conn["wallet_a"], chain)
            b_link = build_explorer_link(conn["wallet_b"], chain)
            
            msg += f"  <a href='{a_link}'>{shorten_address(conn['wallet_a'])}</a>"
            msg += f" ↔ <a href='{b_link}'>{shorten_address(conn['wallet_b'])}</a>\n"
            msg += f"  Similaridade: [{sim_bar}] {sim*100:.0f}%\n"
            
            for reason in conn.get("reasons", [])[:2]:
                msg += f"    ↳ {reason}\n"
            msg += "\n"
    
    # Summary
    msg += "━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📊 Total: {len(connections)} conexões, {len(funding_clusters)} clusters\n"
    msg += "⚠️ Muitas conexões podem indicar coordenação/insider trading"
    
    return msg.strip()


def format_help_message() -> str:
    """Mensagem de ajuda do bot"""
    return """
🕵️ <b>FORRASPY</b> — Bot de Inteligência On-Chain

<b>Como usar:</b>
Cole o endereço de contrato de um token e eu faço a análise completa.

<b>Comandos:</b>
📋 <code>/analyze &lt;contrato&gt;</code> — Análise completa
📋 <code>/analyze &lt;contrato&gt; base</code> — Forçar chain Base
📋 <code>/analyze &lt;contrato&gt; bsc</code> — Forçar chain BSC
📋 <code>/analyze &lt;contrato&gt; solana</code> — Forçar chain Solana

📊 <code>/traders</code> — Ver top traders (após análise)
🔗 <code>/connections</code> — Ver conexões entre wallets
🔍 <code>/wallet &lt;endereço&gt;</code> — Detalhe de uma wallet
📁 <code>/export</code> — Exportar análise para JSON
📁 <code>/export wallets</code> — Exportar só wallets
📁 <code>/export connections</code> — Exportar só conexões

⚙️ <code>/config</code> — Configurações
❓ <code>/help</code> — Esta mensagem

<b>Chains suportadas:</b>
◎ Solana  |  🔵 Base  |  🟡 BSC

<b>Detecção automática:</b>
• Endereços 0x... → EVM (Base/BSC) 
• Endereços Base58 → Solana
• Para EVM, especifique <code>base</code> ou <code>bsc</code>

━━━━━━━━━━━━━━━━━━━━━
🔒 <i>Dados são buscados de APIs públicas</i>
💡 <i>Dica: mande só o contrato que eu analiso!</i>
""".strip()


def format_analyzing_message(contract: str, chain: str) -> str:
    """Mensagem de 'analisando...' """
    chain_emoji = {"solana": "◎", "base": "🔵", "bsc": "🟡"}.get(chain, "⛓")
    return f"""
🔍 <b>Analisando...</b>

{chain_emoji} Chain: <b>{chain.upper()}</b>
📋 Contrato: <code>{shorten_address(contract, 8)}</code>

⏳ Buscando dados do token...
⏳ Analisando top traders...
⏳ Rastreando funding sources...
⏳ Correlacionando wallets...

<i>Isso pode levar 15-60 segundos...</i>
""".strip()


def format_error_message(error: str) -> str:
    """Formata mensagem de erro"""
    return f"""
❌ <b>Erro na análise</b>

{error}

💡 <b>Dicas:</b>
• Verifique se o contrato está correto
• Para EVM, especifique a chain: <code>/analyze 0x... base</code>
• O token precisa ter liquidez em uma DEX
• Use <code>/help</code> para ver os comandos
""".strip()
