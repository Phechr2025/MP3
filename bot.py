import logging, asyncio, os
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

CUSTOM_COMMANDS = {}

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
    return url.startswith("http") and not ("playlist" in url or "list=" in url)

# ---------------- คำสั่งหลัก ----------------
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎧 YTMP3 Bot v6\n\n"
        "คำสั่งที่ใช้ได้:\n"
        "/ytmp3 - ดาวน์โหลด YouTube เป็น MP3\n"
        "/cancel - ยกเลิกงานที่กำลังทำ\n"
        "/status - ดูสถานะระบบ\n"
        "/help - แสดงคำสั่งทั้งหมด\n"
        "/clearlock - เคลียร์ล็อก (ใช้ถ้างานค้าง)\n"
        "/addcmd - เพิ่มคำสั่งพิเศษ (เฉพาะแอดมิน)"
    )
    await update.message.reply_text(text)

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmds = [
        "/ytmp3 - ดาวน์โหลด YouTube เป็น MP3",
        "/cancel - ยกเลิกงานที่กำลังทำ",
        "/status - ดูสถานะระบบ",
        "/help - แสดงคำสั่งทั้งหมด",
        "/clearlock - เคลียร์ล็อก (ใช้ถ้างานค้าง)",
        "/addcmd - เพิ่มคำสั่งพิเศษ (เฉพาะแอดมิน)"
    ]
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

# ---------------- ระบบคำสั่งพิเศษ ----------------
async def addcmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ คุณไม่ใช่แอดมิน")
        return
    await update.message.reply_text("📝 พิมพ์ชื่อคำสั่งพิเศษที่ต้องการเพิ่ม (ไม่ต้องใส่ /)")
    return "ASK_CMD_NAME"

async def set_cmd_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd_name = update.message.text.strip()
    ctx.user_data["new_cmd"] = cmd_name
    await update.message.reply_text(f"✏️ กำหนดข้อความตอบกลับสำหรับคำสั่ง `{cmd_name}`")
    return "ASK_CMD_REPLY"

async def set_cmd_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd_name = ctx.user_data["new_cmd"]
    reply_text = update.message.text.strip()
    CUSTOM_COMMANDS[cmd_name] = reply_text
    await update.message.reply_text(f"✅ เพิ่มคำสั่ง `{cmd_name}` เรียบร้อยแล้ว!")
    return ConversationHandler.END

async def custom_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.strip().lstrip("/")
    if cmd in CUSTOM_COMMANDS:
        await update.message.reply_text(CUSTOM_COMMANDS[cmd])

def main():
    app = Application.builder().token(TOKEN).build()

    conv_addcmd = ConversationHandler(
        entry_points=[CommandHandler("addcmd", addcmd)],
        states={
            "ASK_CMD_NAME": [MessageHandler(filters.TEXT & ~filters.COMMAND, set_cmd_name)],
            "ASK_CMD_REPLY": [MessageHandler(filters.TEXT & ~filters.COMMAND, set_cmd_reply)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("clearlock", clearlock))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(conv_addcmd)
    app.add_handler(MessageHandler(filters.COMMAND, custom_cmd))

    app.run_polling()

if __name__ == "__main__":
    main()
