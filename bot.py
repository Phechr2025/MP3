import logging, asyncio, os, subprocess, urllib.request, tempfile
from typing import Union
from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import yt_dlp
from dotenv import load_dotenv

# โหลดค่า TOKEN และ ADMIN_ID จาก .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
ADMIN_ID = os.getenv("ADMIN_ID", "")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ytmp3-bot")

ASK_LINK, ASK_FILENAME, ASK_SENDTO = range(3)
CURRENT_TASK = None
CURRENT_OWNER_ID = None
CURRENT_ORIGIN_CHAT_ID = None
HELP_COMMANDS = {}

def get_user_id(u: Union[Update, CallbackQuery]) -> int:
    if isinstance(u, CallbackQuery):
        return u.from_user.id
    return u.effective_user.id

def get_chat_id(u: Union[Update, CallbackQuery]) -> int | None:
    if isinstance(u, CallbackQuery):
        return u.message.chat.id if u.message else None
    return u.effective_chat.id

async def send_text(u: Union[Update, CallbackQuery], ctx: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        if isinstance(u, CallbackQuery):
            if u.message:
                return await u.edit_message_text(text)
            return await ctx.bot.send_message(chat_id=u.from_user.id, text=text)
        else:
            return await u.message.reply_text(text)
    except Exception:
        if isinstance(u, CallbackQuery):
            return await ctx.bot.send_message(chat_id=u.from_user.id, text=text)

def is_single_video(url: str) -> bool:
    return not ("playlist" in url or "list=" in url)

# ---------------- คำสั่งหลัก ----------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎧 YTMP3 Bot v6\n\n"
        "คำสั่งที่ใช้ได้:\n"
        "/ytmp3 - ดาวน์โหลด YouTube เป็น MP3\n"
        "/cancel - ยกเลิกงานที่กำลังทำ\n"
        "/status - ดูสถานะระบบ\n"
        "/help - แสดงคำสั่งทั้งหมด\n"
        "/clearlock - เคลียร์ล็อก (ใช้ถ้างานค้าง)\n\n"
        "💡 คุณยังสามารถพิมพ์คำสั่งพิเศษที่แอดมินตั้งเองได้ เช่น 'ช่วยเหลือ' หรือ 'ติดต่อแอดมิน'"
    )
    await update.message.reply_text(text)

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmds = [
        "/ytmp3 - ดาวน์โหลด YouTube เป็น MP3",
        "/cancel - ยกเลิกงานที่กำลังทำ",
        "/status - ดูสถานะระบบ",
        "/help - แสดงคำสั่งทั้งหมด",
        "/clearlock - เคลียร์ล็อก (ใช้ถ้างานค้าง)"
    ]
    if HELP_COMMANDS:
        cmds.append("\n✨ คำสั่งพิเศษ:")
        for k, v in HELP_COMMANDS.items():
            cmds.append(f"- {k}: {v}")
    await update.message.reply_text("📌 คำสั่งทั้งหมด:\n" + "\n".join(cmds))

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if CURRENT_TASK:
        await update.message.reply_text("🚧 ตอนนี้ระบบกำลังดาวน์โหลดไฟล์อยู่")
    else:
        await update.message.reply_text("✅ ระบบว่าง พร้อมใช้งาน")

async def clearlock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global CURRENT_TASK, CURRENT_OWNER_ID, CURRENT_ORIGIN_CHAT_ID
    CURRENT_TASK = None
    CURRENT_OWNER_ID = None
    CURRENT_ORIGIN_CHAT_ID = None
    await update.message.reply_text("🧹 เคลียร์ล็อกเรียบร้อยแล้ว")

# ---------------- Workflow ดาวน์โหลด ----------------
async def ytmp3(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📎 กรุณาส่งลิงก์ YouTube (วิดีโอเดี่ยวเท่านั้น ต้องขึ้นต้นด้วย http หรือ https)")
    return ASK_LINK

async def ask_filename(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("❌ ลิงก์ต้องขึ้นต้นด้วย http:// หรือ https:// เท่านั้น")
        return ConversationHandler.END
    if not is_single_video(url):
        await update.message.reply_text("❌ ลิงก์นี้ไม่ใช่วิดีโอเดี่ยวจาก YouTube กรุณาส่งใหม่")
        return ConversationHandler.END
    ctx.user_data["url"] = url
    await update.message.reply_text("📝 ตั้งชื่อไฟล์ (ไม่ต้องใส่ .mp3)\nพิมพ์ No ถ้าจะใช้ชื่อจาก YouTube\n⚠️ ถ้าชื่อเป็นภาษาไทย อาจได้ตัวอักษรไม่ครบ")
    return ASK_FILENAME

async def ask_sendto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    filename = (update.message.text or "").strip() or "No"
    ctx.user_data["filename"] = filename

    keyboard = [[
        InlineKeyboardButton("📥 ส่งส่วนตัว", callback_data="dm"),
        InlineKeyboardButton("👥 ส่งในกลุ่ม", callback_data="group"),
    ]]
    await update.message.reply_text("📤 จะให้ส่งไฟล์ที่ไหนครับ?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_SENDTO

async def ask_sendto_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data
    await query.answer("⏳ กำลังเตรียมดาวน์โหลด...", show_alert=False)
    if query.message:
        await query.edit_message_text(f"⏳ คุณเลือก: {'ส่งส่วนตัว' if choice=='dm' else 'ส่งในกลุ่ม'}\nกำลังดำเนินการ...")
    return await start_download(update, ctx, sendto=choice)

def _progress_hook(d, status_msg, ctx):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '').strip()
        asyncio.create_task(status_msg.edit_text(f"⏳ กำลังดาวน์โหลด... {percent}"))
    elif d['status'] == 'finished':
        asyncio.create_task(status_msg.edit_text("✅ กำลังแปลงไฟล์..."))

async def start_download(u: Union[Update, CallbackQuery], ctx: ContextTypes.DEFAULT_TYPE, sendto: str):
    global CURRENT_TASK, CURRENT_OWNER_ID, CURRENT_ORIGIN_CHAT_ID
    if CURRENT_TASK:
        await send_text(u, ctx, "⛔ มีงานกำลังทำอยู่ กรุณารอก่อน")
        return ConversationHandler.END

    uid = get_user_id(u)
    cid = get_chat_id(u)
    CURRENT_OWNER_ID, CURRENT_ORIGIN_CHAT_ID = uid, cid
    url = ctx.user_data["url"]
    filename = (ctx.user_data.get("filename") or "No").strip()
    status_msg = await send_text(u, ctx, "⏳ กำลังดาวน์โหลด...")

    async def task():
        global CURRENT_TASK, CURRENT_OWNER_ID, CURRENT_ORIGIN_CHAT_ID
        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
                "noplaylist": True,
                "writethumbnail": True,
                "progress_hooks": [lambda d: _progress_hook(d, status_msg, ctx)],
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
                    {"key": "EmbedThumbnail"},
                    {"key": "FFmpegMetadata"},
                ],
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                out_file = ydl.prepare_filename(info)
                if out_file.endswith(".webm"):
                    out_file = out_file[:-5] + ".mp3"
                elif out_file.endswith(".m4a"):
                    out_file = out_file[:-4] + ".mp3"

            display_name = info.get("title", "Audio") if filename.lower() == "no" else filename
            caption = f"🎵 {display_name}\nบันทึกเป็น: {os.path.basename(out_file)}"

            if sendto == "group":
                if isinstance(u, CallbackQuery) and u.message and u.message.chat.type in ("group", "supergroup"):
                    target_chat = u.message.chat.id
                elif isinstance(u, Update) and u.effective_chat and u.effective_chat.type in ("group", "supergroup"):
                    target_chat = u.effective_chat.id
                else:
                    target_chat = CURRENT_OWNER_ID
                    caption += "\nℹ️ ใช้ 'ส่งในกลุ่ม' ได้เฉพาะถ้าเริ่มคำสั่งในกลุ่ม → ระบบส่งเป็นส่วนตัวแทน"
            else:
                target_chat = CURRENT_OWNER_ID

            with open(out_file, "rb") as f:
                await ctx.bot.send_audio(
                    chat_id=target_chat,
                    audio=f,
                    title=display_name,
                    performer="YouTube",
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )

            if status_msg:
                await status_msg.edit_text("✅ เสร็จสิ้น!")
        except Exception as e:
            logger.exception("Download error")
            if status_msg:
                await status_msg.edit_text(f"❌ ผิดพลาด: {e}")
        finally:
            CURRENT_TASK = None
            CURRENT_OWNER_ID = None
            CURRENT_ORIGIN_CHAT_ID = None

    CURRENT_TASK = asyncio.create_task(task())
    return ConversationHandler.END

# ---------------- Utility ----------------
async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global CURRENT_TASK, CURRENT_OWNER_ID
    if CURRENT_TASK and CURRENT_OWNER_ID == update.effective_user.id:
        CURRENT_TASK.cancel()
        CURRENT_TASK = None
        CURRENT_OWNER_ID = None
        await update.message.reply_text("🛑 ยกเลิกงานเรียบร้อย")
    else:
        await update.message.reply_text("ℹ️ ไม่มีงานที่กำลังทำ")

# ---------------- เพิ่มระบบตั้งคำสั่งพิเศษ ----------------
async def set_custom_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_ID):
        await update.message.reply_text("❌ คุณไม่ใช่แอดมิน ไม่สามารถใช้คำสั่งนี้ได้")
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("⚠️ ใช้รูปแบบ: /setcmd [คำ] [ข้อความ/ลิงก์]")
        return
    key = ctx.args[0]
    val = " ".join(ctx.args[1:])
    HELP_COMMANDS[key] = val
    await update.message.reply_text(f"✅ เพิ่มคำสั่งพิเศษ '{key}' เรียบร้อย")

async def custom_command_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in HELP_COMMANDS:
        await update.message.reply_text(HELP_COMMANDS[text])

def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("ytmp3", ytmp3)],
        states={
            ASK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_filename)],
            ASK_FILENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_sendto)],
            ASK_SENDTO: [CallbackQueryHandler(ask_sendto_callback)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clearlock", clearlock))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("setcmd", set_custom_command))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_command_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
