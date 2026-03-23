import os
import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio

# ระบบ Keep-Alive สำหรับ Railway/Replit
try:
    from myserver import server_on
except ImportError:
    def server_on(): pass

class MonkeyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!Monkey", intents=intents)

    async def setup_hook(self):
        # 🌟 คัดมาให้ใหม่! Node ที่ "ยังมีลมหายใจ" และ Railway รู้จักแน่นอน
        # ผมใส่ https และพอร์ตมาตรฐานกลับไป เพราะ DNS บน Railway ชอบแบบนี้มากกว่าครับ
        nodes = [
            wavelink.Node(
                uri="https://lava-v4.ajieblogs.eu.org", # Node ตัวท็อป เสถียรสูง
                password="https://dsc.gg/ajidevserver"
            ),
            wavelink.Node(
                uri="https://lavalink.lexnet.cc", # ตัวสำรองแรงๆ
                password="lexn3t_@*_!"
            ),
            wavelink.Node(
                uri="https://lavalink.oops.wtf", # ตัวช่วยสุดท้าย
                password="www.freelavalink.pw"
            )
        ]
        
        # เชื่อมต่อระบบ (ถ้าตัวแรกตาย มันจะกระโดดไปตัวที่ 2-3 เองอัตโนมัติ)
        await wavelink.Pool.connect(client=self, nodes=nodes)
        await self.tree.sync()
        print(f"Synced Slash Commands for {self.user}")

    async def on_ready(self):
        print(f"✅ บอทออนไลน์แล้วในชื่อ: {self.user}")
        print("------")

bot = MonkeyBot()

# --- อีเวนต์: เมื่อ Lavalink Node เชื่อมต่อสำเร็จ ---
@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f"🔥 Node: {payload.node.identifier} เชื่อมต่อสำเร็จ! พร้อมทะลวง YouTube")

# --- อีเวนต์: แจ้งเตือนเมื่อเล่นเพลงถัดไป ---
@bot.event
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    player: wavelink.Player = payload.player
    if not player: return
    
    track: wavelink.Playable = payload.track

    if hasattr(player, 'is_first_play') and player.is_first_play:
        player.is_first_play = False
        return

    embed = discord.Embed(
        title="⏭️ กำลังเล่นเพลงถัดไปในคิว",
        description=f"**[{track.title}]({track.uri})**",
        color=discord.Color.purple()
    )
    if track.artwork:
        embed.set_thumbnail(url=track.artwork)
    embed.set_footer(text="Monkey Music Bot 🐒 x Lavalink")
    
    if hasattr(player, 'home_channel'):
        await player.home_channel.send(embed=embed)

# --- คำสั่ง: /play ---
@bot.tree.command(name="play", description="เล่นเพลงหรือเพิ่มเพลงเข้าในคิว")
@app_commands.describe(search="ชื่อเพลงหรือลิงก์ YouTube")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ เข้าห้องเสียงก่อนดิลูกพี่!", ephemeral=True)

    await interaction.response.defer()

    if not interaction.guild.voice_client:
        try:
            player: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player, timeout=20.0, self_deaf=True)
            player.home_channel = interaction.channel
        except Exception as e:
            return await interaction.followup.send(f"❌ บอทเข้าห้องไม่ได้ (Lavalink อาจจะล่มหรือเต็ม): {e}")
    else:
        player: wavelink.Player = interaction.guild.voice_client

    try:
        tracks: wavelink.Search = await wavelink.Playable.search(search)
        if not tracks:
            return await interaction.followup.send("❌ หาเพลงไม่เจอครับ!")

        track: wavelink.Playable = tracks[0] if not isinstance(tracks, wavelink.Playlist) else tracks.tracks[0]

        if not player.playing:
            player.is_first_play = True
            await player.play(track, volume=100)
            embed = discord.Embed(title="🎶 กำลังเล่นเพลง", description=f"**[{track.title}]({track.uri})**", color=discord.Color.green())
        else:
            await player.queue.put_wait(track)
            embed = discord.Embed(title="📝 เพิ่มลงคิวแล้ว", description=f"**[{track.title}]({track.uri})**\nลำดับ: `{player.queue.count}`", color=discord.Color.blue())
        
        if track.artwork: embed.set_thumbnail(url=track.artwork)
        embed.set_footer(text="Monkey Music Bot 🐒")
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการดึงเพลง: {e}")

# --- คำสั่ง: /queue (แบ่งหน้าอัตโนมัติ) ---
@bot.tree.command(name="queue", description="ดูรายการเพลงในคิว")
async def queue(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if not player or player.queue.is_empty:
        return await interaction.response.send_message("📭 คิวว่างเปล่า...", ephemeral=True)

    await interaction.response.defer()
    embeds = []
    current_desc = ""
    
    for i, track in enumerate(player.queue): 
        line = f"`{i+1}.` [{track.title}]({track.uri})\n"
        if len(current_desc) + len(line) > 3500:
            embeds.append(discord.Embed(title=f"📋 คิวเพลง (ส่วนที่ {len(embeds)+1})", description=current_desc, color=discord.Color.blue()))
            current_desc = line
        else: current_desc += line

    if current_desc:
        embed = discord.Embed(title=f"📋 คิวเพลง (ส่วนที่ {len(embeds)+1})", description=current_desc, color=discord.Color.blue())
        embed.set_footer(text=f"รวมทั้งหมด {player.queue.count} เพลง")
        embeds.append(embed)

    for index, emb in enumerate(embeds):
        await interaction.followup.send(embed=emb) if index == 0 else await interaction.channel.send(embed=emb)

# --- คำสั่ง: /skip ---
@bot.tree.command(name="skip", description="ข้ามเพลง")
async def skip(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player and player.playing:
        await player.skip(force=True)
        await interaction.response.send_message("⏩ **ข้ามล่ะนะ!**")

# --- คำสั่ง: /back ---
@bot.tree.command(name="back", description="ย้อนเพลง")
async def back(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player and not player.queue.history.is_empty:
        prev_track = player.queue.history[-1]
        del player.queue.history[-1]
        if player.current: player.queue.put_at(0, player.current)
        player.queue.put_at(0, prev_track)
        player.is_first_play = True
        await player.skip(force=True)
        await interaction.response.send_message(f"⏪ **ย้อนกลับไปที่:** {prev_track.title}")
    else:
        await interaction.response.send_message("❌ ไม่มีประวัติเพลง!", ephemeral=True)

# --- คำสั่ง: /stop ---
@bot.tree.command(name="stop", description="หยุดและออกจากห้อง")
async def stop(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player:
        player.queue.clear()
        await player.disconnect()
        await interaction.response.send_message("👋 บาย!")

if __name__ == "__main__":
    server_on()
    bot.run(os.getenv('TOKEN'))