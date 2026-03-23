import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio

from myserver import server_on

YDL_OPTIONS = {
    'format': 'bestaudio/best/m4a/ogg/wav', 
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
    'cookiefile': 'cookies.txt',
    
    # เพิ่มบรรทัดเหล่านี้เพื่อข้ามข้อผิดพลาดเรื่อง Format
    'ignoreerrors': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

# --- ตั้งค่าตำแหน่งไฟล์ FFmpeg ---
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
# --- ตัวแปรเก็บข้อมูลเพลง (แยกตามเซิร์ฟเวอร์) ---
song_queue = {}    # คิวเพลงถัดไป
song_history = {}  # ประวัติเพลงที่เล่นไปแล้ว

class MonkeyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!Monkey", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced Slash Commands for {self.user}")
    async def on_ready(self):
        print(f"✅ บอทออนไลน์แล้วในชื่อ: {self.user}")
        print(f"🆔 ID: {self.user.id}")
        print("------")

bot = MonkeyBot()

# --- ฟังก์ชันจัดการคิวเพลง ---
def check_queue(interaction, error=None):
    guild_id = interaction.guild_id
    vc = interaction.guild.voice_client
    
    if guild_id in song_queue and song_queue[guild_id] and vc:
        next_song = song_queue[guild_id].pop(0)
        
        async def play_next():
            source = await discord.FFmpegOpusAudio.from_probe(next_song['url'], **FFMPEG_OPTIONS)
            vc.play(source, after=lambda e: check_queue(interaction, e))
            
            # เก็บลงประวัติ
            if guild_id not in song_history: song_history[guild_id] = []
            song_history[guild_id].append(next_song)
            
            await interaction.channel.send(f"⏭️ **เพลงถัดไป:** {next_song['title']}")
            
        asyncio.run_coroutine_threadsafe(play_next(), bot.loop)

# --- Slash Command: /play ---
@bot.tree.command(name="play", description="เล่นเพลงหรือเพิ่มเพลงเข้าในคิวจากการค้นหาหรือจากลิงก์")
@app_commands.describe(search="ชื่อเพลงหรือลิงก์ YouTube")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ กูจะรู้ไหมว่าคุณมึงอยู่ห้องไหน!", ephemeral=True)

    await interaction.response.defer()

    # --- ระบบตัดลิงก์เพลย์ลิสต์ (&list=...) ---
    clean_search = search.split('&')[0] if "youtube.com" in search else search

    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect()

    guild_id = interaction.guild_id
    if guild_id not in song_queue: song_queue[guild_id] = []
    if guild_id not in song_history: song_history[guild_id] = []

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            # ค้นหาเพลง
            query = f"ytsearch:{clean_search}" if "http" not in clean_search else clean_search
            info_data = ydl.extract_info(query, download=False)
            
            if 'entries' in info_data and len(info_data['entries']) > 0:
                info = info_data['entries'][0]
            else:
                info = info_data

            song_data = {
                'url': info['url'], 
                'title': info['title'], 
                'webpage_url': info.get('webpage_url'),
                'thumbnail': info.get('thumbnail')
            }

            if vc.is_playing() or vc.is_paused():
                song_queue[guild_id].append(song_data)
                await interaction.followup.send(f"📝 **เพิ่มลงคิวแล้ว:** {song_data['title']}")
            else:
                source = await discord.FFmpegOpusAudio.from_probe(song_data['url'], **FFMPEG_OPTIONS)
                vc.play(source, after=lambda e: check_queue(interaction, e))
                song_history[guild_id].append(song_data)

                embed = discord.Embed(
                    title="🎶 กำลังเล่นเพลง",
                    description=f"**[{song_data['title']}]({song_data['webpage_url']})**",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=song_data['thumbnail'])
                embed.add_field(name="สั่งโดย", value=interaction.user.mention)
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}")

# --- Slash Command: /back (ย้อนกลับ) ---
@bot.tree.command(name="back", description="ย้อนกลับไปเล่นเพลงก่อนหน้า")
async def back(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    vc = interaction.guild.voice_client

    if guild_id in song_history and len(song_history[guild_id]) > 1:
        current_song = song_history[guild_id].pop() 
        prev_song = song_history[guild_id].pop()
        
        song_queue[guild_id].insert(0, current_song)
        
        source = await discord.FFmpegOpusAudio.from_probe(prev_song['url'], **FFMPEG_OPTIONS)
        if vc.is_playing(): vc.stop()
        
        vc.play(source, after=lambda e: check_queue(interaction, e))
        song_history[guild_id].append(prev_song)
        
        await interaction.response.send_message(f"⏪ **ย้อนกลับไปที่:** {prev_song['title']}")
    else:
        await interaction.response.send_message("❌ ไม่มีเพลงก่อนหน้าในประวัติ!", ephemeral=True)

# --- Slash Command: /skip (ถัดไป) ---
@bot.tree.command(name="skip", description="ข้ามเพลงปัจจุบัน")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop() # stop จะไปเรียก check_queue ให้อัตโนมัติ
        await interaction.response.send_message("⏩ ข้ามเพลงให้แล้วจ้า!")
    else:
        await interaction.response.send_message("❌ ไม่ได้เล่นเพลงอะไรอยู่จะให้ข้ามอะไรก่อน!", ephemeral=True)

# --- Slash Command: /stop ---
@bot.tree.command(name="stop", description="หยุดเพลงและให้บอทออกจากห้องเสียง")
async def stop(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        song_queue[interaction.guild_id] = [] # ล้างคิว
        await interaction.guild.voice_client.disconnect()
        embed = discord.Embed(
            title="👋 บอกให้หยุดเล่นเเเล้วกูจะอยู่ไหม ไกลปู กูไปละ",
            description=f"{interaction.user.mention}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ ลิงยังไม่อยู่ในห้องมึงรีบหรอ", ephemeral=True)
        
if __name__ == "__main__":
    server_on()
    try:
        bot.run(os.getenv('TOKEN'))
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
