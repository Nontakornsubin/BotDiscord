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
    'format': 'bestaudio/best', # กลับมาใช้แบบมาตรฐาน
    'noplaylist': True,
    'quiet': False, 
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
    'cookiefile': 'cookies.txt' if cookie_content else None,
    'source_address': '0.0.0.0',
    
    # 🌟 1. ทะลวงการบล็อกระดับประเทศ/ภูมิภาคที่ YouTube ชอบแอบทำกับ IP เซิร์ฟเวอร์
    'geo_bypass': True,
    
    'extractor_args': {
        'youtube': {
            # 🌟 2. ปลอมตัวเป็นระบบหลังบ้านของ YouTube (web_creator) และ Smart TV
            # ซึ่งเป็น 2 ช่องทางที่ YouTube แทบจะไม่เคยบล็อก Format เลย!
            'player_client': ['web_creator', 'tv', 'mweb'] 
        }
    }
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

# --- Slash Command: /queue (ระบบตัดขึ้นหน้าใหม่อัตโนมัติ) ---
@bot.tree.command(name="queue", description="ดูรายการเพลงที่อยู่ในคิวทั้งหมดตอนนี้")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    if guild_id not in song_queue or not song_queue[guild_id]:
        embed = discord.Embed(description="📭 **ตอนนี้ไม่มีเพลงในคิวเลย ว่างจัด**", color=discord.Color.light_gray())
        return await interaction.response.send_message(embed=embed)

    await interaction.response.defer()

    q_list = song_queue[guild_id]
    embeds = []
    current_desc = ""
    
    for i, song in enumerate(q_list): 
        line = f"`{i+1}.` [{song['title']}]({song.get('webpage_url', '')})\n"
        
        # ตัดขึ้นกล่องใหม่ถ้าข้อความยาวเกิน 3,500 ตัวอักษร
        if len(current_desc) + len(line) > 3500:
            embed = discord.Embed(
                title=f"📋 รายการเพลงในคิว (ส่วนที่ {len(embeds) + 1})", 
                description=current_desc, 
                color=discord.Color.blue()
            )
            embeds.append(embed)
            current_desc = line
        else:
            current_desc += line

    # เก็บตกเนื้อหาส่วนที่เหลือลงกล่องสุดท้าย
    if current_desc:
        embed = discord.Embed(
            title=f"📋 รายการเพลงในคิว (ส่วนที่ {len(embeds) + 1})", 
            description=current_desc, 
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"รวมทั้งหมด {len(q_list)} เพลง | Monkey Music Bot 🐒")
        embeds.append(embed)

    # ทยอยส่งกล่องข้อความ
    for index, emb in enumerate(embeds):
        if index == 0:
            await interaction.followup.send(embed=emb)
        else:
            await interaction.channel.send(embed=emb)

# --- Slash Command: /jump ---
@bot.tree.command(name="jump", description="ข้ามไปเล่นเพลงในคิวตามลำดับที่ระบุทันที")
@app_commands.describe(index="ลำดับเพลงในคิว (ดูตัวเลขจาก /queue)")
async def jump(interaction: discord.Interaction, index: int):
    guild_id = interaction.guild_id
    vc = interaction.guild.voice_client

    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(embed=discord.Embed(description="❌ ไม่ได้เล่นเพลงอะไรอยู่!", color=discord.Color.red()), ephemeral=True)

    if guild_id not in song_queue or not song_queue[guild_id]:
        return await interaction.response.send_message(embed=discord.Embed(description="❌ คิวว่างเปล่า!", color=discord.Color.red()), ephemeral=True)

    if index < 1 or index > len(song_queue[guild_id]):
        return await interaction.response.send_message(embed=discord.Embed(description=f"❌ หาไม่เจอ! กรุณาระบุตัวเลขให้ถูกต้อง (1 ถึง {len(song_queue[guild_id])})", color=discord.Color.red()), ephemeral=True)

    # ดึงเพลงจากคิวแล้วเอามาแทรกไว้คิวที่ 1
    target_song = song_queue[guild_id].pop(index - 1)
    song_queue[guild_id].insert(0, target_song)
    
    embed = discord.Embed(
        title="🦘 กระโดดข้ามคิว!",
        description=f"**ดึงเพลงนี้ขึ้นมาเล่นทันที:**\n[{target_song['title']}]({target_song.get('webpage_url', '')})",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)
    vc.stop() # หยุดเพลงปัจจุบัน ระบบจะดึงคิวที่ 1 (เพลงที่เพิ่งแซงคิว) มาเล่นต่อทันที

# --- Slash Command: /back ---
@bot.tree.command(name="back", description="ย้อนกลับไปเล่นเพลงก่อนหน้าทีละ 1 เพลง")
async def back(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    vc = interaction.guild.voice_client

    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(embed=discord.Embed(description="❌ ไม่ได้เล่นเพลงอะไรอยู่!", color=discord.Color.red()), ephemeral=True)

    if guild_id in song_history and len(song_history[guild_id]) > 1:
        current_song = song_history[guild_id].pop() 
        prev_song = song_history[guild_id].pop()
        
        # เอาเพลงปัจจุบันยัดกลับไปรอคิวที่ 2, เอาเพลงก่อนหน้ายัดไปรอคิวที่ 1
        song_queue[guild_id].insert(0, current_song)
        song_queue[guild_id].insert(0, prev_song)
        
        embed = discord.Embed(
            title="⏪ ย้อนกลับ 1 เพลง",
            description=f"**ครับพี่เดี๋ยวเล่นเพลงเดิมให้:**\n[{prev_song['title']}]({prev_song.get('webpage_url', '')})",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed)
        vc.stop()
    else:
        embed = discord.Embed(description="❌ **ย้อนสุดเเล้วโว้ยยยย!** (ไม่มีเพลงก่อนหน้า)", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Slash Command: /skip ---
@bot.tree.command(name="skip", description="ข้ามเพลงปัจจุบัน")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        embed = discord.Embed(description="⏩ **ข้ามล่ะ!**", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        vc.stop() 
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