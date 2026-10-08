"""
Bot de Telegram para Cuotas Aumentadas y Cálculo de EV con Publicación en Canal.
"""
import io
import logging
import os
from typing import Dict, Any, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import (
    load_settings,
    update_ev_range,
    set_channel_id,
    add_admin,
)
from calculator import calculate_ev, parse_percentage, parse_odd
from vision import extract_bet_from_image, parse_text_info, format_event_name

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Campos requeridos para completar una apuesta
REQUIRED_FIELDS = [
    ("casa", "🏠 Casa de apuestas (ej. Bet365, Winamax)"),
    ("evento", "⚽ Evento / Partido (ej. Real Madrid vs Barcelona)"),
    ("suceso", "🎯 Suceso / Pronóstico (ej. Vinicius marca gol)"),
    ("cuota_aumentada", "🚀 Cuota Aumentada (ej. 2.50)"),
    ("cuota_normal", "📊 Cuota sin aumento / Cuota normal más alta (ej. 2.10)"),
    ("margen", "📐 Margen de la casa (ej. 5% o 0.05)"),
]

def format_odd_str(val) -> str:
    """Formatea cuotas numéricas con dos decimales (ej. 3.3 -> 3.30)"""
    try:
        f = float(str(val).replace(",", "."))
        return f"{f:.2f}"
    except Exception:
        return str(val)

def format_channel_post(data: Dict[str, Any]) -> str:
    """
    Genera el formato exacto requerido para el canal:
    - Cuota normal ➡️ Cuota aumentada (+EV% EV) en la misma línea.
    - 'Resultado:' queda vacío para que el usuario pueda editarlo después.
    """
    ev_val = data.get("ev", 0.0)
    ev_sign = "+" if ev_val > 0 else ""
    cuota_n = format_odd_str(data.get("cuota_normal", "N/A"))
    cuota_a = format_odd_str(data.get("cuota_aumentada", "N/A"))
    return (
        f"🏠 <b>Casa:</b> {data.get('casa', 'N/A')}\n"
        f"⚽ <b>Evento:</b> {data.get('evento', 'N/A')}\n"
        f"🎯 <b>Suceso:</b> {data.get('suceso', 'N/A')}\n"
        f"📊 <b>Cuota:</b> {cuota_n} ➡️ <b>{cuota_a}</b> ({ev_sign}{ev_val}% EV)\n"
        f"🏁 <b>Resultado:</b> "
    )

def is_user_authorized(user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    settings = load_settings()
    admin_ids = settings.get("admin_ids", [])
    if not admin_ids:
        # Si no hay admins configurados, se auto-autoriza el primero
        add_admin(user_id)
        return True
    return user_id in admin_ids

def get_missing_field(bet: Dict[str, Any]) -> Optional[tuple]:
    for key, label in REQUIRED_FIELDS:
        val = bet.get(key)
        if val is None or str(val).strip() == "":
            return (key, label)
    return None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /start"""
    user = update.effective_user
    if not is_user_authorized(user.id):
        await update.message.reply_text("⛔ No estás autorizado para usar este bot.")
        return

    settings = load_settings()
    min_ev = settings.get("min_ev", 5.0)
    max_ev = settings.get("max_ev", 10.0)
    channel = settings.get("channel_id", "Sin configurar")

    texto = (
        f"👋 <b>¡Hola, {user.first_name}!</b>\n\n"
        f"Soy tu bot asistente para filtrar y publicar <b>Cuotas Aumentadas con Valor Esperado (EV)</b>.\n\n"
        f"⚙️ <b>Configuración actual:</b>\n"
        f"• 📈 Rango de EV permitido: <b>{min_ev}% a {max_ev}%</b>\n"
        f"• 📢 Canal de destino: <code>{channel}</code>\n\n"
        f"📌 <b>¿Cómo usarlo?</b>\n"
        f"1. Envíame la <b>captura de pantalla</b> de la cuota aumentada.\n"
        f"2. En el pie de foto (o en los mensajes siguientes) dime los datos que falten (margen, cuota normal, etc.).\n"
        f"3. Si falta algún dato, te lo preguntaré automáticamente.\n"
        f"4. Calcularé el EV: si entra en tu rango, te pediré <b>confirmación</b> con vista previa antes de publicarlo en el canal.\n\n"
        f"🛠️ <b>Comandos disponibles:</b>\n"
        f"• <code>/rango [min] [max]</code> - Ver o cambiar el rango de EV (ej: <code>/rango 5 10</code>)\n"
        f"• <code>/canal [@usuario_o_id]</code> - Ver o cambiar el canal de publicación\n"
        f"• <code>/cancelar</code> - Cancelar la apuesta en curso\n"
        f"• <code>/ayuda</code> - Ver instrucciones completas"
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja /ayuda"""
    if not is_user_authorized(update.effective_user.id):
        return
    texto = (
        "📖 <b>Guía de Uso Rápido:</b>\n\n"
        "1. <b>Enviar captura:</b> Manda la imagen directamente. Si quieres ahorrar tiempo, pon en el texto de la foto:\n"
        "   <code>Margen: 5% Cuota: 2.10 Evento: Madrid vs Barça Casa: Bet365</code>\n"
        "2. <b>Si no pones texto:</b> La IA intentará leer el suceso, cuota aumentada y evento de la imagen. Los campos que no encuentre te los preguntará uno por uno.\n"
        "3. <b>Cálculo de EV:</b>\n"
        "   Calcula la probabilidad real sin margen y el % de EV.\n"
        "4. <b>Confirmación:</b> Verás una vista previa idéntica a como saldrá en el canal y botones para <b>Confirmar</b> o <b>Cancelar</b>.\n"
        "5. <b>En el Canal:</b> Se publica la foto con todos los datos y <code>Resultado: </code> vacío listo para editar cuando acabe el evento."
    )
    await update.message.reply_text(texto, parse_mode=ParseMode.HTML)

async def canal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configura o muestra el ID del canal"""
    if not is_user_authorized(update.effective_user.id):
        return

    args = context.args
    settings = load_settings()

    if not args:
        actual = settings.get("channel_id", "Sin configurar")
        await update.message.reply_text(
            f"📢 Canal actual configurado: <code>{actual}</code>\n\n"
            f"Para cambiarlo, usa: <code>/canal @nombre_del_canal</code> (o el ID numérico ej: <code>-1001234567890</code>).\n"
            f"<i>Recuerda que el bot debe ser Administrador en el canal para poder publicar.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    nuevo_canal = args[0].strip()
    set_channel_id(nuevo_canal)
    await update.message.reply_text(
        f"✅ Canal actualizado a: <code>{nuevo_canal}</code>\n"
        f"Asegúrate de que el bot sea administrador en dicho canal con permisos para enviar mensajes y fotos.",
        parse_mode=ParseMode.HTML
    )

async def rango_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Configura o muestra el rango de EV"""
    if not is_user_authorized(update.effective_user.id):
        return

    args = context.args
    settings = load_settings()

    if not args or len(args) < 2:
        min_ev = settings.get("min_ev", 5.0)
        max_ev = settings.get("max_ev", 10.0)
        await update.message.reply_text(
            f"📊 <b>Rango de EV actual:</b> del <b>{min_ev}%</b> al <b>{max_ev}%</b>\n\n"
            f"Para modificarlo, usa: <code>/rango [min] [max]</code>\n"
            f"Ejemplo: <code>/rango 5 10</code> o <code>/rango 4.5 12</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        min_val = float(args[0].replace(",", "."))
        max_val = float(args[1].replace(",", "."))
        if min_val >= max_val:
            await update.message.reply_text("⚠️ El valor mínimo debe ser menor que el máximo.")
            return

        update_ev_range(min_val, max_val)
        await update.message.reply_text(
            f"✅ <b>Rango de EV actualizado con éxito:</b>\n"
            f"Nuevo rango: <b>{min_val}% a {max_val}%</b>",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await update.message.reply_text("⚠️ Parámetros inválidos. Ejemplo de uso: <code>/rango 5 10</code>", parse_mode=ParseMode.HTML)

async def cancelar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela la operación en curso"""
    if not is_user_authorized(update.effective_user.id):
        return

    if "current_bet" in context.user_data:
        del context.user_data["current_bet"]
        await update.message.reply_text("❌ Operación cancelada. Borrador descartado.")
    else:
        await update.message.reply_text("ℹ️ No hay ninguna operación o borrador pendiente.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe la captura enviada por el usuario"""
    if not is_user_authorized(update.effective_user.id):
        return

    photo = update.message.photo[-1] # Obtener la mayor resolución
    caption = update.message.caption or ""

    status_msg = await update.message.reply_text("🔍 <i>Analizando la captura...</i>", parse_mode=ParseMode.HTML)

    # Descargar imagen en memoria para procesar
    photo_file = await context.bot.get_file(photo.file_id)
    image_bytes = await photo_file.download_as_bytearray()

    # Intentar extraer datos por IA
    extracted = extract_bet_from_image(bytes(image_bytes))

    # Parsear también el texto que haya venido en el caption
    caption_data = parse_text_info(caption)

    # Combinar: lo del caption tiene prioridad si el usuario lo especificó a mano
    bet_data = {
        "photo_file_id": photo.file_id,
        "casa": caption_data.get("casa") or extracted.get("casa"),
        "evento": caption_data.get("evento") or extracted.get("evento"),
        "suceso": caption_data.get("suceso") or extracted.get("suceso"),
        "cuota_aumentada": caption_data.get("cuota_aumentada") or extracted.get("cuota_aumentada"),
        "cuota_normal": caption_data.get("cuota_normal") or extracted.get("cuota_normal"),
        "margen": caption_data.get("margen") or extracted.get("margen"),
    }

    context.user_data["current_bet"] = bet_data
    await status_msg.delete()

    await check_next_step(update, context)

async def check_next_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica si faltan datos y pide el siguiente o pasa al cálculo y confirmación"""
    bet = context.user_data.get("current_bet")
    if not bet:
        return

    missing = get_missing_field(bet)
    chat = update.effective_chat

    if missing:
        field_key, field_name = missing
        bet["awaiting_field"] = field_key
        
        # Resumen de lo que ya tenemos
        conocidos = []
        if bet.get("suceso"): conocidos.append(f"• 🎯 Suceso: <b>{bet['suceso']}</b>")
        if bet.get("cuota_aumentada"): conocidos.append(f"• 🚀 Cuota Aumentada: <b>{bet['cuota_aumentada']}</b>")
        if bet.get("casa"): conocidos.append(f"• 🏠 Casa: <b>{bet['casa']}</b>")
        if bet.get("evento"): conocidos.append(f"• ⚽ Evento: <b>{bet['evento']}</b>")
        if bet.get("cuota_normal"): conocidos.append(f"• 📊 Cuota sin aumento: <b>{bet['cuota_normal']}</b>")
        if bet.get("margen"): conocidos.append(f"• 📐 Margen: <b>{bet['margen']}</b>")

        resumen = "\n".join(conocidos) if conocidos else "<i>Ninguno aún</i>"

        texto = (
            f"📝 <b>Datos detectados:</b>\n{resumen}\n\n"
            f"👉 <b>Falta un dato requerido:</b>\n"
            f"Por favor, responde con: <b>{field_name}</b>\n\n"
            f"<i>(O escribe varios a la vez, ej: 'Bet365 | Real Madrid vs Girona | 2.15 | 4.5%')</i>"
        )
        await chat.send_message(texto, parse_mode=ParseMode.HTML)
        return

    # Si ya tenemos todos los datos, procedemos al cálculo
    bet["awaiting_field"] = None
    try:
        cuota_n = bet["cuota_normal"]
        cuota_a = bet["cuota_aumentada"]
        margen = bet["margen"]

        ev, prob_fair = calculate_ev(cuota_n, cuota_a, margen)
        bet["ev"] = ev
        bet["prob_fair"] = prob_fair
    except Exception as e:
        await chat.send_message(f"❌ Error al calcular el EV: {e}\nPor favor revisa los valores introducidos con /cancelar y vuelve a probar.")
        return

    # Comprobación de rango de EV
    settings = load_settings()
    min_ev = settings.get("min_ev", 5.0)
    max_ev = settings.get("max_ev", 10.0)

    in_range = (min_ev <= ev <= max_ev)

    ev_sign = "+" if ev > 0 else ""
    channel = settings.get("channel_id", "Sin configurar")

    if not in_range:
        # Fuera de rango
        mensaje_alerta = (
            f"⚠️ <b>EV FUERA DE RANGO</b>\n\n"
            f"• EV Calculado: <b>{ev_sign}{ev}%</b> (Prob. Fair: {prob_fair}%)\n"
            f"• Rango permitido: <b>{min_ev}% a {max_ev}%</b>\n\n"
            f"La cuota no cumple con el rango establecido para publicarse automáticamente en el canal."
        )
        keyboard = [
            [
                InlineKeyboardButton("⚡ Forzar publicación de todos modos", callback_data="force_publish"),
                InlineKeyboardButton("❌ Descartar", callback_data="cancel_bet")
            ]
        ]
        await chat.send_message(mensaje_alerta, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
        return

    # En rango -> Petición de confirmación con vista previa
    preview_caption = format_channel_post(bet)

    keyboard = [
        [
            InlineKeyboardButton("✅ Confirmar y Publicar en Canal", callback_data="confirm_publish"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel_bet")
        ]
    ]

    await chat.send_message(
        f"🎯 <b>¡EV en rango! (+{ev}%)</b>\n\n"
        f"📢 <b>VISTA PREVIA DEL MENSAJE PARA EL CANAL:</b>\n"
        f"Destino: <code>{channel}</code>\n"
        f"─────────────────────\n"
        f"{preview_caption}\n"
        f"─────────────────────\n\n"
        f"¿Deseas confirmar la subida al canal oficial?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def handle_text_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las respuestas de texto del usuario cuando el bot le pregunta datos"""
    if not is_user_authorized(update.effective_user.id):
        return

    bet = context.user_data.get("current_bet")
    if not bet:
        return

    text = update.message.text.strip()

    # Primero revisar si el texto incluye múltiples datos formateados (ej: "margen 5% cuota 2.10")
    parsed_multi = parse_text_info(text)
    if parsed_multi:
        for k, v in parsed_multi.items():
            if v is not None:
                bet[k] = v

    # Si hay un campo específico esperando respuesta y no se asignó arriba
    awaiting = bet.get("awaiting_field")
    if awaiting and awaiting not in parsed_multi:
        if awaiting in ["cuota_normal", "cuota_aumentada"]:
            try:
                bet[awaiting] = parse_odd(text)
            except Exception:
                await update.message.reply_text("⚠️ Por favor introduce una cuota numérica válida (ej: 2.15).")
                return
        elif awaiting == "margen":
            try:
                # Validar que se pueda parsear
                parse_percentage(text)
                bet["margen"] = text
            except Exception:
                await update.message.reply_text("⚠️ Por favor introduce un margen válido (ej: 5% o 0.05).")
                return
        elif awaiting == "evento":
            bet["evento"] = format_event_name(text)
        else:
            bet[awaiting] = text

    await check_next_step(update, context)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de confirmación y cancelación"""
    query = update.callback_query
    await query.answer()

    action = query.data
    bet = context.user_data.get("current_bet")

    if not bet:
        await query.edit_message_text("⚠️ La apuesta ya fue procesada o descartada.")
        return

    if action == "cancel_bet":
        del context.user_data["current_bet"]
        await query.edit_message_text("❌ Publicación cancelada y borrador eliminado.")
        return

    if action in ["confirm_publish", "force_publish"]:
        settings = load_settings()
        channel = settings.get("channel_id")

        if not channel:
            await query.edit_message_text(
                "❌ <b>Error:</b> No has configurado el canal de destino.\n"
                "Usa el comando <code>/canal @nombre_del_canal</code> y vuelve a intentarlo.",
                parse_mode=ParseMode.HTML
            )
            return

        caption_post = format_channel_post(bet)
        photo_id = bet.get("photo_file_id")

        try:
            # Subir foto + mensaje juntos en un único post
            await context.bot.send_photo(
                chat_id=channel,
                photo=photo_id,
                caption=caption_post,
                parse_mode=ParseMode.HTML
            )
            del context.user_data["current_bet"]
            await query.edit_message_text(
                f"🎉 <b>¡Publicado con éxito en el canal!</b>\n\n"
                f"Canal: <code>{channel}</code>\n"
                f"EV: <b>+{bet.get('ev')}%</b>\n\n"
                f"<i>El campo 'Resultado:' ha quedado vacío para que puedas editarlo desde el canal cuando termine el evento.</i>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error publicando en canal: {e}")
            await query.edit_message_text(
                f"❌ <b>Error al publicar en el canal:</b>\n<code>{e}</code>\n\n"
                f"Verifica que el bot sea <b>Administrador</b> en el canal <code>{channel}</code> con permiso para publicar mensajes.",
                parse_mode=ParseMode.HTML
            )

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "TU_TELEGRAM_BOT_TOKEN":
        print("="*60)
        print("ERROR: TELEGRAM_BOT_TOKEN no configurado en el archivo .env")
        print("Por favor, edita el archivo .env y añade tu token de BotFather.")
        print("="*60)
        return

    app = Application.builder().token(token).build()

    # Comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("ayuda", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rango", rango_command))
    app.add_handler(CommandHandler("canal", canal_command))
    app.add_handler(CommandHandler("cancelar", cancelar_command))

    # Handlers para fotos, texto y callbacks (solo en chat privado con el usuario)
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text_response))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    print("Iniciando Bot de Telegram para Cuotas Aumentadas...")
    app.run_polling()

if __name__ == "__main__":
    main()
