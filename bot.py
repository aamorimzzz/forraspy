"""
FORRASPY — Bot Principal do Telegram
Bot de inteligência on-chain para análise de tokens e wallets
"""

import os
import io
import json
import asyncio
import logging
import tempfile
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN, ANALYSIS_CONFIG
from analyzers import SolanaAnalyzer, EVMAnalyzer, AnalysisResult
from exports import export_to_json, export_wallets_only, export_connections_only
from utils.helpers import detect_chain, is_valid_evm_address, is_valid_solana_address
from telegram_formatter import (
    format_token_overview, format_top_traders, format_wallet_detail,
    format_connections_summary, format_help_message, format_analyzing_message,
    format_error_message
)

# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("forraspy")

# ══════════════════════════════════════════════════════════════
# ESTADO POR CHAT (armazena última análise)
# ══════════════════════════════════════════════════════════════

# chat_id -> AnalysisResult
chat_analyses: dict[int, AnalysisResult] = {}

# chat_id -> current page for traders list
chat_pages: dict[int, int] = {}


# ══════════════════════════════════════════════════════════════
# ANALYZERS (lazy init)
# ══════════════════════════════════════════════════════════════

_analyzers = {}

def get_analyzer(chain: str):
    """Retorna analyzer para a chain especificada (singleton)"""
    if chain not in _analyzers:
        if chain == "solana":
            _analyzers[chain] = SolanaAnalyzer()
        elif chain in ("base", "bsc"):
            _analyzers[chain] = EVMAnalyzer(chain)
        else:
            raise ValueError(f"Chain não suportada: {chain}")
    return _analyzers[chain]


# ══════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    await update.message.reply_text(
        format_help_message(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    await update.message.reply_text(
        format_help_message(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def cmd_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /analyze <contrato> [chain]
    Executa análise completa do token.
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Use: <code>/analyze &lt;contrato&gt; [chain]</code>\n"
            "Exemplo: <code>/analyze 0x123...abc base</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    contract = args[0].strip()
    chain_override = args[1].strip().lower() if len(args) > 1 else None
    
    # Detecta chain
    chain = _resolve_chain(contract, chain_override)
    if not chain:
        await update.message.reply_text(
            format_error_message(
                "Não consegui detectar a chain.\n"
                "Para endereços 0x, especifique: <code>/analyze 0x... base</code> ou <code>bsc</code>"
            ),
            parse_mode=ParseMode.HTML
        )
        return
    
    # Envia mensagem de "analisando"
    status_msg = await update.message.reply_text(
        format_analyzing_message(contract, chain),
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Executa análise
        analyzer = get_analyzer(chain)
        result = await analyzer.full_analysis(contract)
        
        # Salva no estado
        chat_id = update.effective_chat.id
        chat_analyses[chat_id] = result
        chat_pages[chat_id] = 0
        
        # Envia overview do token
        await status_msg.edit_text(
            format_token_overview(result),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        # Envia top traders com botões
        if result.top_traders:
            keyboard = _build_traders_keyboard(0, result)
            await update.message.reply_text(
                format_top_traders(result, page=0),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        
        # Envia conexões se encontradas
        connections = result.wallet_clusters.get("connections", {})
        if connections:
            await update.message.reply_text(
                format_connections_summary(result),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        
        # Botões de ação
        action_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📁 Exportar JSON", callback_data="export_full"),
                InlineKeyboardButton("📊 Só Wallets", callback_data="export_wallets"),
            ],
            [
                InlineKeyboardButton("🔗 Só Conexões", callback_data="export_connections"),
                InlineKeyboardButton("🔄 Re-analisar", callback_data=f"reanalyze_{contract}_{chain}"),
            ]
        ])
        
        await update.message.reply_text(
            "⬆️ <b>Ações disponíveis:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=action_keyboard
        )
    
    except ValueError as e:
        await status_msg.edit_text(
            format_error_message(str(e)),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.exception(f"Erro na análise de {contract}")
        await status_msg.edit_text(
            format_error_message(f"Erro inesperado: {str(e)[:200]}"),
            parse_mode=ParseMode.HTML
        )


async def cmd_traders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra lista de top traders da última análise"""
    chat_id = update.effective_chat.id
    result = chat_analyses.get(chat_id)
    
    if not result:
        await update.message.reply_text(
            "❌ Nenhuma análise recente. Use <code>/analyze &lt;contrato&gt;</code> primeiro.",
            parse_mode=ParseMode.HTML
        )
        return
    
    page = chat_pages.get(chat_id, 0)
    keyboard = _build_traders_keyboard(page, result)
    
    await update.message.reply_text(
        format_top_traders(result, page=page),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


async def cmd_connections(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra conexões entre wallets da última análise"""
    chat_id = update.effective_chat.id
    result = chat_analyses.get(chat_id)
    
    if not result:
        await update.message.reply_text(
            "❌ Nenhuma análise recente. Use <code>/analyze &lt;contrato&gt;</code> primeiro.",
            parse_mode=ParseMode.HTML
        )
        return
    
    await update.message.reply_text(
        format_connections_summary(result),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra detalhes de uma wallet específica"""
    chat_id = update.effective_chat.id
    result = chat_analyses.get(chat_id)
    
    if not context.args:
        await update.message.reply_text(
            "❌ Use: <code>/wallet &lt;endereço&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    wallet_addr = context.args[0].strip().lower()
    
    if not result:
        await update.message.reply_text(
            "❌ Nenhuma análise recente. Use <code>/analyze &lt;contrato&gt;</code> primeiro.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Procura a wallet na análise
    wallet = None
    for t in result.top_traders:
        if t.address.lower() == wallet_addr:
            wallet = t
            break
    
    if not wallet:
        await update.message.reply_text(
            f"❌ Wallet <code>{wallet_addr[:12]}...</code> não encontrada nos top traders.\n"
            "Use <code>/traders</code> para ver a lista.",
            parse_mode=ParseMode.HTML
        )
        return
    
    await update.message.reply_text(
        format_wallet_detail(wallet),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exporta análise para JSON"""
    chat_id = update.effective_chat.id
    result = chat_analyses.get(chat_id)
    
    if not result:
        await update.message.reply_text(
            "❌ Nenhuma análise recente. Use <code>/analyze &lt;contrato&gt;</code> primeiro.",
            parse_mode=ParseMode.HTML
        )
        return
    
    export_type = context.args[0].strip().lower() if context.args else "full"
    await _send_json_export(update, result, export_type)


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra/altera configurações"""
    config = ANALYSIS_CONFIG
    
    msg = f"""
⚙️ <b>Configurações FORRASPY</b>

👥 Top traders analisados: <b>{config.top_traders_count}</b>
📊 Max transações: <b>{config.max_transactions}</b>
🔗 Profundidade funding: <b>{config.funding_depth}</b> hops
💰 Lucro mínimo: <b>${config.min_profit_usd:.0f}</b>
🎯 Threshold conexão: <b>{config.connection_threshold*100:.0f}%</b>

<i>Configurações são fixas nesta versão.</i>
""".strip()
    
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════════════════
# MESSAGE HANDLER (detecta contratos)
# ══════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Detecta quando o usuário manda apenas um contrato e 
    inicia análise automaticamente.
    """
    text = update.message.text.strip()
    
    # Ignora se começa com /
    if text.startswith("/"):
        return
    
    # Verifica se é um contrato válido
    parts = text.split()
    potential_contract = parts[0]
    chain_hint = parts[1].lower() if len(parts) > 1 else None
    
    detected = detect_chain(potential_contract)
    
    if detected:
        # É um contrato! Resolve chain e analisa
        if detected == "evm" and not chain_hint:
            # Pede para especificar a chain
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔵 Base", callback_data=f"chain_base_{potential_contract}"),
                    InlineKeyboardButton("🟡 BSC", callback_data=f"chain_bsc_{potential_contract}"),
                ]
            ])
            await update.message.reply_text(
                f"🔍 Contrato EVM detectado!\n"
                f"<code>{potential_contract}</code>\n\n"
                f"Qual chain?",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
        else:
            # Chain conhecida, analisa direto
            chain = chain_hint or detected
            if chain == "evm":
                chain = chain_hint or "base"  # Default: Base
            
            context.args = [potential_contract, chain]
            await cmd_analyze(update, context)


# ══════════════════════════════════════════════════════════════
# CALLBACK HANDLERS (botões inline)
# ══════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa cliques em botões inline"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    
    # Seleção de chain
    if data.startswith("chain_"):
        parts = data.split("_", 2)
        chain = parts[1]
        contract = parts[2]
        
        # Simula o comando /analyze
        context.args = [contract, chain]
        
        # Cria um pseudo-update com message
        await query.edit_message_text(
            format_analyzing_message(contract, chain),
            parse_mode=ParseMode.HTML
        )
        
        try:
            analyzer = get_analyzer(chain)
            result = await analyzer.full_analysis(contract)
            
            chat_analyses[chat_id] = result
            chat_pages[chat_id] = 0
            
            await query.edit_message_text(
                format_token_overview(result),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            
            if result.top_traders:
                keyboard = _build_traders_keyboard(0, result)
                await query.message.reply_text(
                    format_top_traders(result, page=0),
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )
            
        except Exception as e:
            await query.edit_message_text(
                format_error_message(str(e)),
                parse_mode=ParseMode.HTML
            )
    
    # Paginação de traders
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        result = chat_analyses.get(chat_id)
        
        if result:
            chat_pages[chat_id] = page
            keyboard = _build_traders_keyboard(page, result)
            await query.edit_message_text(
                format_top_traders(result, page=page),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
    
    # Detalhe de wallet
    elif data.startswith("detail_"):
        wallet_addr = data.split("_", 1)[1]
        result = chat_analyses.get(chat_id)
        
        if result:
            for t in result.top_traders:
                if t.address.lower() == wallet_addr.lower():
                    await query.message.reply_text(
                        format_wallet_detail(t),
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    break
    
    # Exports
    elif data.startswith("export_"):
        export_type = data.replace("export_", "")
        result = chat_analyses.get(chat_id)
        
        if result:
            await _send_json_export_from_callback(query, result, export_type)
    
    # Re-analisar
    elif data.startswith("reanalyze_"):
        parts = data.split("_", 2)
        contract = parts[1]
        chain = parts[2]
        
        await query.edit_message_text(
            format_analyzing_message(contract, chain),
            parse_mode=ParseMode.HTML
        )
        
        try:
            analyzer = get_analyzer(chain)
            result = await analyzer.full_analysis(contract)
            
            chat_analyses[chat_id] = result
            chat_pages[chat_id] = 0
            
            await query.edit_message_text(
                format_token_overview(result),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            await query.edit_message_text(
                format_error_message(str(e)),
                parse_mode=ParseMode.HTML
            )


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _resolve_chain(contract: str, override: str = None) -> str:
    """Resolve a chain para um contrato"""
    if override:
        if override in ("base", "bsc", "solana"):
            return override
    
    detected = detect_chain(contract)
    if detected == "solana":
        return "solana"
    elif detected == "evm":
        return override or None  # Precisa especificar
    
    return None


def _build_traders_keyboard(page: int, result: AnalysisResult) -> InlineKeyboardMarkup:
    """Constrói teclado de navegação para lista de traders"""
    per_page = 5
    total = len(result.top_traders)
    total_pages = (total + per_page - 1) // per_page
    
    buttons = []
    
    # Navegação
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Próximo ➡️", callback_data=f"page_{page+1}"))
    
    if nav_row:
        buttons.append(nav_row)
    
    # Botões de detalhe para cada wallet na página
    start = page * per_page
    end = start + per_page
    detail_buttons = []
    
    for i, t in enumerate(result.top_traders[start:end], start + 1):
        short = t.address[:6] + "..." + t.address[-4:]
        detail_buttons.append(
            InlineKeyboardButton(f"🔍 #{i} {short}", callback_data=f"detail_{t.address}")
        )
    
    # 2 botões por linha
    for i in range(0, len(detail_buttons), 2):
        buttons.append(detail_buttons[i:i+2])
    
    return InlineKeyboardMarkup(buttons)


async def _send_json_export(update, result: AnalysisResult, export_type: str):
    """Envia arquivo JSON como documento"""
    token_symbol = result.token.symbol
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    if export_type == "wallets":
        json_str = export_wallets_only(result.top_traders)
        filename = f"forraspy_{token_symbol}_wallets_{timestamp}.json"
    elif export_type == "connections":
        json_str = export_connections_only(result.wallet_clusters)
        filename = f"forraspy_{token_symbol}_connections_{timestamp}.json"
    else:
        json_str = export_to_json(result)
        filename = f"forraspy_{token_symbol}_full_{timestamp}.json"
    
    # Envia como arquivo
    file_bytes = json_str.encode("utf-8")
    bio = io.BytesIO(file_bytes)
    bio.name = filename
    
    await update.message.reply_document(
        document=InputFile(bio, filename=filename),
        caption=f"📁 Exportação {export_type.upper()} — ${token_symbol}\n"
                f"📊 {len(file_bytes)/1024:.1f} KB",
        parse_mode=ParseMode.HTML
    )


async def _send_json_export_from_callback(query, result: AnalysisResult, export_type: str):
    """Envia JSON a partir de callback query"""
    token_symbol = result.token.symbol
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    if export_type == "wallets":
        json_str = export_wallets_only(result.top_traders)
        filename = f"forraspy_{token_symbol}_wallets_{timestamp}.json"
    elif export_type == "connections":
        json_str = export_connections_only(result.wallet_clusters)
        filename = f"forraspy_{token_symbol}_connections_{timestamp}.json"
    else:
        json_str = export_to_json(result)
        filename = f"forraspy_{token_symbol}_full_{timestamp}.json"
    
    file_bytes = json_str.encode("utf-8")
    bio = io.BytesIO(file_bytes)
    bio.name = filename
    
    await query.message.reply_document(
        document=InputFile(bio, filename=filename),
        caption=f"📁 Exportação {export_type.upper()} — ${token_symbol}\n"
                f"📊 {len(file_bytes)/1024:.1f} KB",
        parse_mode=ParseMode.HTML
    )


# ══════════════════════════════════════════════════════════════
# CLEANUP
# ══════════════════════════════════════════════════════════════

async def cleanup(application):
    """Fecha sessions dos analyzers"""
    for analyzer in _analyzers.values():
        await analyzer.close()


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    """Inicia o bot"""
    if TELEGRAM_BOT_TOKEN == "SEU_TOKEN_AQUI":
        print("❌ Configure TELEGRAM_BOT_TOKEN no config.py ou variável de ambiente!")
        print("   Crie o bot em @BotFather no Telegram")
        return
    
    print("""
    ╔══════════════════════════════════════╗
    ║   🕵️ FORRASPY — Intelligence Bot    ║
    ║   Análise On-Chain para Telegram    ║
    ╠══════════════════════════════════════╣
    ║   Chains: Solana | Base | BSC       ║
    ║   Status: Iniciando...              ║
    ╚══════════════════════════════════════╝
    """)
    
    # Build app
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Registra handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("analyze", cmd_analyze))
    app.add_handler(CommandHandler("traders", cmd_traders))
    app.add_handler(CommandHandler("connections", cmd_connections))
    app.add_handler(CommandHandler("wallet", cmd_wallet))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("config", cmd_config))
    
    # Callback handler (botões inline)
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Message handler (detecta contratos automaticamente)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_message
    ))
    
    # Cleanup ao fechar
    app.post_shutdown = cleanup
    
    print("✅ Bot iniciado! Aguardando mensagens...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
