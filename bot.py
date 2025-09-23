import discord
from discord.ext import commands
import yt_dlp
import os
import imageio_ffmpeg

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# โฟลเดอร์เก็บไฟล์ชั่วคราว
DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ffmpeg แบบพกพา
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# กำหนด User ID ที่อนุญาต (1 คน)
ALLOWED_USER = 1147798918973898762  # 👈 แก้เป็น Discord User ID ของคุณ

# ฟอร์ม Modal
class YTModal(discord.ui.Modal):
    def __init__(self, channel):
        super().__init__(title="YouTube to MP3")
        self.channel = channel
        self.add_item(discord.ui.InputText(label="วางลิงก์ YouTube"))

    async def callback(self, interaction: discord.Interaction):
        url = self.children[0].value
        await interaction.response.send_message("🎵 กำลังโหลดและแปลงเป็น MP3 ...", ephemeral=True)

        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
                "ffmpeg_location": FFMPEG_PATH,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                filename = filename.rsplit(".", 1)[0] + ".mp3"

            await self.channel.send(file=discord.File(filename))
            os.remove(filename)

        except Exception as e:
            await self.channel.send(f"❌ Error: {e}")


@bot.slash_command(name="ytmp3", description="แปลง YouTube เป็น MP3")
async def ytmp3(ctx: discord.ApplicationContext):
    if ctx.author.id != ALLOWED_USER:
        await ctx.respond("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    modal = YTModal(ctx.channel)
    await ctx.send_modal(modal)


bot.run(os.getenv("DISCORD_TOKEN"))
