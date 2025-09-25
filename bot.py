import logging, asyncio, os, subprocess, urllib.request, tempfile
from typing import Union
from telegram import Update, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv
import yt_dlp

# โหลดค่า TOKEN และ ADMIN_ID จาก .env
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

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

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎧 YTMP3 Bot v6

"
        "คำสั่งที่ใช้ได้:
"
        "/ytmp3 - ดาวน์โหลด YouTube เป็น MP3
"
        "/cancel - ยกเลิกงานที่กำลังทำ
"
        "/status - ดูสถานะระบบ
"
        "/help - แสดงคำสั่งทั้งหมด
"
        "/clearlock - เคลียร์ล็อก

"
        "✨ คำสั่งพิเศษ: พิมพ์ตรง ๆ เช่น 'ช่วยเหลือ', 'ติดต่อแอดมิน'"
    )
    await update.message.reply_text(text)

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmds = [
        "/ytmp3 - ดาวน์โหลด YouTube เป็น MP3",
        "/cancel - ยกเลิกงาน",
        "/status - ดูสถานะระบบ",
        "/help - แสดงคำสั่ง",
        "/clearlock - เคลียร์ล็อก",
    ]
    text = "📌 คำสั่งทั้งหมด:
" + "
".join(cmds)
    if HELP_COMMANDS:
        text += "\n\n✨ คำสั่งพิเศษ:\n" + "\n".join([f"{k} → {v}" for k,v in HELP_COMMANDS.items()])
    await update.message.reply_text(text)

async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if CURRENT_TASK:
        await update.message.reply_text("🚧 กำลังดาวน์โหลดอยู่")
    else:
        await update.message.reply_text("✅ พร้อมใช้งาน")

async def clearlock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global CURRENT_TASK, CURRENT_OWNER_ID, CURRENT_ORIGIN_CHAT_ID
    CURRENT_TASK = None
    CURRENT_OWNER_ID = None
    CURRENT_ORIGIN_CHAT_ID = None
    await update.message.reply_text("🧹 เคลียร์ล็อกเรียบร้อยแล้ว")

async def ytmp3(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📎 ส่งลิงก์ YouTube (ต้องเป็นวิดีโอเดี่ยว)")
    return ASK_LINK

async def ask_filename(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("❌ ลิงก์ต้องขึ้นด้วย http หรือ https")
        return ConversationHandler.END
    if not is_single_video(url):
        await update.message.reply_text("❌ ลิงก์นี้ไม่ใช่วิดีโอเดี่ยว")
        return ConversationHandler.END
    ctx.user_data["url"] = url
    await update.message.reply_text("📝 ตั้งชื่อไฟล์ (ไม่ต้องใส่ .mp3)\nพิมพ์ No ถ้าจะใช้ชื่อจาก YouTube")
    return ASK_FILENAME

async def ask_sendto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    filename = (update.message.text or "").strip() or "No"
    ctx.user_data["filename"] = filename

    keyboard = [[
        InlineKeyboardButton("📥 ส่งส่วนตัว", callback_data="dm"),
        InlineKeyboardButton("👥 ส่งในกลุ่ม", callback_data="group"),
    ]]
    await update.message.reply_text("📤 จะให้ส่งที่ไหน?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_SENDTO

async def ask_sendto_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    choice = query.data
    await query.answer("⏳ กำลังเตรียมดาวน์โหลด...", show_alert=False)
    if query.message:
        await query.edit_message_text(f"⏳ คุณเลือก: {'ส่งส่วนตัว' if choice=='dm' else 'ส่งในกลุ่ม'}\nกำลังทำงาน...")
    return await start_download(update, ctx, sendto=choice)

def _download_and_prepare_thumb(url: str) -> str | None:
    if not url:
        return None
    try:
        tmpdir = tempfile.mkdtemp(prefix="thumb_")
        raw_path = os.path.join(tmpdir, "thumb")
        urllib.request.urlretrieve(url, raw_path)
        jpg_path = raw_path + ".jpg"
        cmd = ["ffmpeg", "-y", "-i", raw_path, "-q:v", "2", jpg_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return jpg_path if os.path.exists(jpg_path) else raw_path
    except Exception:
        return None

async def start_download(u: Union[Update, CallbackQuery], ctx: ContextTypes.DEFAULT_TYPE, sendto: str):
    global CURRENT_TASK, CURRENT_OWNER_ID, CURRENT_ORIGIN_CHAT_ID
    if CURRENT_TASK:
        await send_text(u, ctx, "⛔ มีงานกำลังทำอยู่")
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
                "progress_hooks": [lambda d: asyncio.create_task(report_progress(d, status_msg))],
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
            thumb_path = _download_and_prepare_thumb(info.get("thumbnail"))
            caption = f"🎵 {display_name}\nบันทึกเป็น: {os.path.basename(out_file)}"
            if sendto == "group":
                if isinstance(u, CallbackQuery) and u.message and u.message.chat.type in ("group","supergroup"):
                    target_chat = u.message.chat.id
                elif isinstance(u, Update) and u.effective_chat and u.effective_chat.type in ("group","supergroup"):
                    target_chat = u.effective_chat.id
                else:
                    target_chat = CURRENT_OWNER_ID
                    caption += "\nℹ️ ใช้ 'ส่งในกลุ่ม' ได้เฉพาะในกลุ่ม → ส่งเป็นส่วนตัวแทน"
            else:
                target_chat = CURRENT_OWNER_ID
            with open(out_file, "rb") as f:
                if thumb_path and os.path.exists(thumb_path):
                    with open(thumb_path, "rb") as t:
                        await ctx.bot.send_audio(chat_id=target_chat,audio=f,title=display_name,
                            performer="YouTube",caption=caption,parse_mode=ParseMode.HTML,thumbnail=t)
                else:
                    await ctx.bot.send_audio(chat_id=target_chat,audio=f,title=display_name,
                        performer="YouTube",caption=caption,parse_mode=ParseMode.HTML)
            if status_msg: await status_msg.edit_text("✅ เสร็จสิ้น!")
        except Exception as e:
            logger.exception("Download error")
            if status_msg: await status_msg.edit_text(f"❌ ผิดพลาด: {e}")
        finally:
            CURRENT_TASK = None
            CURRENT_OWNER_ID = None
            CURRENT_ORIGIN_CHAT_ID = None
    CURRENT_TASK = asyncio.create_task(task())
    return ConversationHandler.END

async def report_progress(d, msg):
    if d["status"] == "downloading":
        percent = d.get("_percent_str", "").strip()
        try:
            await msg.edit_text(f"⏳ กำลังดาวน์โหลด... {percent}")
        except Exception:
            pass

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global CURRENT_TASK, CURRENT_OWNER_ID
    if CURRENT_TASK and CURRENT_OWNER_ID == update.effective_user.id:
        CURRENT_TASK.cancel()
        CURRENT_TASK = None
        CURRENT_OWNER_ID = None
        await update.message.reply_text("🛑 ยกเลิกงานแล้ว")
    else:
        await update.message.reply_text("ℹ️ ไม่มีงานที่กำลังทำ")

async def special_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in HELP_COMMANDS:
        await update.message.reply_text(HELP_COMMANDS[text])
    elif get_user_id(update) == ADMIN_ID:
        parts = text.split("=",1)
        if len(parts)==2:
            HELP_COMMANDS[parts[0].strip()] = parts[1].strip()
            await update.message.reply_text(f"✅ เพิ่มคำสั่ง {parts[0]} เรียบร้อย")
    else:
        return

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
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, special_command))
    app.run_polling()

if __name__ == "__main__":
    main()
