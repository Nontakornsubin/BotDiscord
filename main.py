import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio

from myserver import server_on

# 🌟 1. ประกาศตัวแปรและสร้างไฟล์คุ้กกี้
cookie_content = os.getenv('YT_COOKIES')
if cookie_content:
    formatted_cookies = cookie_content.replace('\\n', '\n') 
    with open('cookies.txt', 'w', encoding='utf-8') as f:
        f.write(formatted_cookies)
    print("✅ สร้างไฟล์ cookies.txt สำเร็จ!")
else:
    print("⚠️ ไม่พบ YT_COOKIES ใน Environment Variables")

# 🌟 2. ตั้งค่า YDL_OPTIONS และ FFMPEG_OPTIONS
YDL_OPTIONS = {
    'format': 'bestaudio/best/ba/b/wa/w', 
    'noplaylist': True,
    'quiet': False, 
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
    'cookiefile': 'cookies.txt' if cookie_content else None,
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -user_agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"',
    'options': '-vn'
}

# --- ตัวแปรเก็บข้อมูลเพลง ---
song_queue = {}    
song_history = {}  

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
        print("------")

bot = MonkeyBot()

# --- ฟังก์ชันจัดการคิวเพลง ---
def check_queue(interaction, error=None):
    if error:
        print(f"Player error: {error}")
        
    guild_id = interaction.guild_id
    vc = interaction.guild.voice_client
    
    if guild_id in song_queue and song_queue[guild_id] and vc:
        next_song = song_queue[guild_id].pop(0)
        
        async def play_next():
            source = discord.FFmpegPCMAudio(next_song['url'], **FFMPEG_OPTIONS)
            vc.play(source, after=lambda e: check_queue(interaction, e))
            
            if guild_id not in song_history: song_history[guild_id] = []
            song_history[guild_id].append(next_song)
            
            # แจ้งเตือนเพลงถัดไปแบบ Embed สวยๆ
            embed = discord.Embed(
                title="⏭️ กำลังเล่นเพลงถัดไปในคิว",
                description=f"**[{next_song['title']}]({next_song.get('webpage_url', '')})**",
                color=discord.Color.purple()
            )
            if next_song.get('thumbnail'):
                embed.set_thumbnail(url=next_song['thumbnail'])
            embed.set_footer(text="Monkey Music Bot 🐒")
            await interaction.channel.send(embed=embed)
            
        asyncio.run_coroutine_threadsafe(play_next(), bot.loop)

# --- Slash Command: /play ---
@bot.tree.command(name="play", description="เล่นเพลงหรือเพิ่มเพลงเข้าในคิว")
@app_commands.describe(search="ชื่อเพลงหรือลิงก์ YouTube")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        embed = discord.Embed(description="❌ **กูจะรู้ไหมว่าคุณมึงอยู่ห้องไหน!**", color=discord.Color.red())
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    await interaction.response.defer()

    clean_search = search.split('&')[0] if "youtube.com" in search else search

    vc = interaction.guild.voice_client
    if not vc:
        try:
            vc = await interaction.user.voice.channel.connect(timeout=60.0, self_deaf=True)
        except Exception as e:
            return await interaction.followup.send(f"❌ เข้าห้องไม่ได้: {e}")

    guild_id = interaction.guild_id
    if guild_id not in song_queue: song_queue[guild_id] = []
    if guild_id not in song_history: song_history[guild_id] = []

    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        try:
            query = f"ytsearch:{clean_search}" if "http" not in clean_search else clean_search
            info_data = await asyncio.to_thread(ydl.extract_info, query, download=False)
            
            if info_data is None:
                return await interaction.followup.send("❌ ไม่สามารถดึงข้อมูลเพลงได้")

            if 'entries' in info_data:
                if not info_data['entries']:
                    return await interaction.followup.send("❌ ค้นหาเพลงนี้ไม่พบ!")
                info = info_data['entries'][0]
            else:
                info = info_data

            if info is None:
                return await interaction.followup.send("❌ ข้อมูลเพลงว่างเปล่า!")

            song_data = {
                'url': info.get('url'), 
                'title': info.get('title', 'Unknown Title'), 
                'webpage_url': info.get('webpage_url', ''),
                'thumbnail': info.get('thumbnail', '')
            }

            if not song_data['url']:
                 return await interaction.followup.send("❌ ดึงไฟล์เสียงไม่ได้ คลิปนี้อาจจะถูกจำกัดการเข้าถึงนะ!")

            if vc.is_playing() or vc.is_paused():
                song_queue[guild_id].append(song_data)
                embed = discord.Embed(
                    title="📝 เพิ่มลงคิวแล้ว",
                    description=f"**[{song_data['title']}]({song_data['webpage_url']})**\nลำดับที่: `{len(song_queue[guild_id])}`",
                    color=discord.Color.blue()
                )
                if song_data['thumbnail']:
                    embed.set_thumbnail(url=song_data['thumbnail'])
                embed.add_field(name="สั่งโดย", value=interaction.user.mention)
                embed.set_footer(text="Monkey Music Bot 🐒")
                await interaction.followup.send(embed=embed)
            else:
                source = discord.FFmpegPCMAudio(song_data['url'], **FFMPEG_OPTIONS)
                vc.play(source, after=lambda e: check_queue(interaction, e))
                song_history[guild_id].append(song_data)

                embed = discord.Embed(
                    title="🎶 กำลังเล่นเพลง",
                    description=f"**[{song_data['title']}]({song_data['webpage_url']})**",
                    color=discord.Color.green()
                )
                if song_data['thumbnail']:
                     embed.set_thumbnail(url=song_data['thumbnail'])
                embed.add_field(name="สั่งโดย", value=interaction.user.mention)
                embed.set_footer(text="Monkey Music Bot 🐒")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}")

# --- Slash Command: /back ---
@bot.tree.command(name="back", description="ย้อนกลับไปเล่นเพลงก่อนหน้า")
async def back(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    vc = interaction.guild.voice_client

    if guild_id in song_history and len(song_history[guild_id]) > 1:
        current_song = song_history[guild_id].pop() 
        prev_song = song_history[guild_id].pop()
        
        song_queue[guild_id].insert(0, current_song)
        
        source = discord.FFmpegPCMAudio(prev_song['url'], **FFMPEG_OPTIONS)
        if vc.is_playing(): vc.stop()
        
        vc.play(source, after=lambda e: check_queue(interaction, e))
        song_history[guild_id].append(prev_song)
        
        embed = discord.Embed(
            title="⏪ ย้อนกลับ",
            description=f"**ครับพี่เดี๋ยวเล่นเพลงเดิมให้:**\n[{prev_song['title']}]({prev_song.get('webpage_url', '')})",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(description="❌ **ย้อนสุดเเล้วโว้ยยยย!** (ไม่มีเพลงก่อนหน้า)", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Slash Command: /skip ---
@bot.tree.command(name="skip", description="ข้ามเพลงปัจจุบัน")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop() 
        embed = discord.Embed(description="⏩ **ข้ามล่ะ!**", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(description="❌ **ไม่ได้เล่นเพลงอะไรอยู่จะให้กูข้ามอะไรก่อน!**", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Slash Command: /stop ---
@bot.tree.command(name="stop", description="หยุดเพลงและให้บอทออกจากห้องเสียง")
async def stop(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        song_queue[interaction.guild_id] = [] # ล้างคิว
        await interaction.guild.voice_client.disconnect()
        embed = discord.Embed(
            title="👋 บอกให้หยุดเล่นเเเล้วกูจะอยู่ไหม ไกลปู กูไปละ",
            description=f"เตะโดย: {interaction.user.mention}",
            color=discord.Color.dark_gray()
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(description="❌ **ลิงยังไม่อยู่ในห้องมึงรีบหรอ**", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
if __name__ == "__main__":
    server_on()
    try:
        bot.run(os.getenv('TOKEN'))
    except Exception as e:
        print(f"❌ Error starting bot: {e}")