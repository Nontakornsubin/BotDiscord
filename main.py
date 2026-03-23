import os
import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio

# เชื่อมต่อกับไฟล์ server สำหรับ Keep-Alive (ถ้าคุณใช้)
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
        # 🌟 เปลี่ยนมาใช้ Node ที่ SSL ปกติ และเสถียรกว่าเดิม
        # ผมใส่ไว้ให้ 2 ตัวเลยครับ ถ้าตัวแรกล่ม ตัวที่สองจะทำงานแทนอัตโนมัติ (Pro ไปอีก!)
        nodes = [
            wavelink.Node(
                uri="https://lavalink.lexnet.cc:443", 
                password="lexn3t_@*_!"
            ),
            wavelink.Node(
                uri="https://lavalink.jirayu.net:443", # Node คนไทย เสถียรมาก!
                password="youshallnotpass"
            )
        ]
        
        await wavelink.Pool.connect(client=self, nodes=nodes)
        await self.tree.sync()
        print(f"Synced Slash Commands for {self.user}")

    async def on_ready(self):
        print(f"✅ บอทออนไลน์แล้วในชื่อ: {self.user}")
        print("------")

bot = MonkeyBot()

# --- Event: เมื่อเชื่อมต่อ Lavalink สำเร็จ ---
@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f"🔥 Lavalink Node: {payload.node.identifier} เชื่อมต่อสำเร็จ! พร้อมลุย YouTube")

# --- Event: เมื่อเพลงเริ่มเล่น (ใช้แจ้งเตือนเพลงถัดไป) ---
@bot.event
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    player: wavelink.Player = payload.player
    if not player: return
    
    track: wavelink.Playable = payload.track

    # ป้องกันไม่ให้บอทส่งข้อความซ้ำตอนเริ่มเพลงแรก (เพราะ /play ส่งไปแล้ว)
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

# --- Command: /play ---
@bot.tree.command(name="play", description="เล่นเพลงหรือเพิ่มเพลงเข้าในคิว")
@app_commands.describe(search="ชื่อเพลงหรือลิงก์ YouTube")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        embed = discord.Embed(description="❌ **กูจะรู้ไหมว่าคุณมึงอยู่ห้องไหน!**", color=discord.Color.red())
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    await interaction.response.defer()

    # เชื่อมต่อ Voice Channel
    if not interaction.guild.voice_client:
        try:
            player: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player, timeout=30.0, self_deaf=True)
            player.home_channel = interaction.channel # จำห้องแชทไว้ส่งข้อความ
        except Exception as e:
            return await interaction.followup.send(f"❌ เข้าห้องไม่ได้: {e}")
    else:
        player: wavelink.Player = interaction.guild.voice_client
        player.home_channel = interaction.channel

    try:
        # ค้นหาเพลง
        tracks: wavelink.Search = await wavelink.Playable.search(search)
        if not tracks:
            return await interaction.followup.send("❌ ค้นหาเพลงนี้ไม่พบ!")

        # ตรวจสอบว่าเป็น Playlist หรือไม่
        track: wavelink.Playable = tracks[0] if not isinstance(tracks, wavelink.Playlist) else tracks.tracks[0]

        if not player.playing:
            player.is_first_play = True
            await player.play(track, volume=100)
            
            embed = discord.Embed(
                title="🎶 กำลังเล่นเพลง",
                description=f"**[{track.title}]({track.uri})**",
                color=discord.Color.green()
            )
        else:
            await player.queue.put_wait(track)
            embed = discord.Embed(
                title="📝 เพิ่มลงคิวแล้ว",
                description=f"**[{track.title}]({track.uri})**\nลำดับที่: `{player.queue.count}`",
                color=discord.Color.blue()
            )
        
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        embed.add_field(name="สั่งโดย", value=interaction.user.mention)
        embed.set_footer(text="Monkey Music Bot 🐒 x Lavalink")
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}")

# --- Command: /queue (ระบบแบ่งหน้าอัตโนมัติ) ---
@bot.tree.command(name="queue", description="ดูรายการเพลงที่อยู่ในคิวทั้งหมดตอนนี้")
async def queue(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if not player or player.queue.is_empty:
        embed = discord.Embed(description="📭 **ตอนนี้ไม่มีเพลงในคิวเลย ว่างจัด**", color=discord.Color.light_gray())
        return await interaction.response.send_message(embed=embed)

    await interaction.response.defer()
    embeds = []
    current_desc = ""
    
    for i, track in enumerate(player.queue): 
        line = f"`{i+1}.` [{track.title}]({track.uri})\n"
        if len(current_desc) + len(line) > 3500:
            embeds.append(discord.Embed(title=f"📋 คิวเพลง (ส่วนที่ {len(embeds)+1})", description=current_desc, color=discord.Color.blue()))
            current_desc = line
        else:
            current_desc += line

    if current_desc:
        embed = discord.Embed(title=f"📋 คิวเพลง (ส่วนที่ {len(embeds)+1})", description=current_desc, color=discord.Color.blue())
        embed.set_footer(text=f"รวมทั้งหมด {player.queue.count} เพลง | Monkey Music Bot 🐒")
        embeds.append(embed)

    for index, emb in enumerate(embeds):
        if index == 0: await interaction.followup.send(embed=emb)
        else: await interaction.channel.send(embed=emb)

# --- Command: /jump ---
@bot.tree.command(name="jump", description="ข้ามไปเล่นเพลงในคิวตามลำดับที่ระบุทันที")
async def jump(interaction: discord.Interaction, index: int):
    player: wavelink.Player = interaction.guild.voice_client
    if not player or player.queue.is_empty:
        return await interaction.response.send_message("❌ คิวว่างเปล่า!", ephemeral=True)

    if 1 <= index <= player.queue.count:
        track = player.queue[index - 1]
        del player.queue[index - 1]
        player.queue.put_at(0, track)
        player.is_first_play = True
        await player.skip(force=True)
        await interaction.response.send_message(embed=discord.Embed(description=f"🦘 **กระโดดข้ามไปเล่น:** {track.title}", color=discord.Color.purple()))
    else:
        await interaction.response.send_message(f"❌ ระบุเลขให้ถูกดิ๊! (1-{player.queue.count})", ephemeral=True)

# --- Command: /back ---
@bot.tree.command(name="back", description="ย้อนกลับไปเล่นเพลงก่อนหน้า")
async def back(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player and not player.queue.history.is_empty:
        prev_track = player.queue.history[-1]
        del player.queue.history[-1]
        
        if player.current:
            player.queue.put_at(0, player.current)
        
        player.queue.put_at(0, prev_track)
        player.is_first_play = True
        await player.skip(force=True)
        await interaction.response.send_message(embed=discord.Embed(description=f"⏪ **ย้อนกลับไปเล่น:** {prev_track.title}", color=discord.Color.orange()))
    else:
        await interaction.response.send_message("❌ ไม่มีประวัติเพลงให้ย้อนแล้วโว้ย!", ephemeral=True)

# --- Command: /skip ---
@bot.tree.command(name="skip", description="ข้ามเพลงปัจจุบัน")
async def skip(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player and player.playing:
        await player.skip(force=True)
        await interaction.response.send_message(embed=discord.Embed(description="⏩ **ข้ามล่ะนะ!**", color=discord.Color.gold()))
    else:
        await interaction.response.send_message("❌ ไม่ได้เล่นเพลงอยู่จะให้ข้ามอะไร!", ephemeral=True)

# --- Command: /stop ---
@bot.tree.command(name="stop", description="หยุดเพลงและออกจากห้องเสียง")
async def stop(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player:
        player.queue.clear()
        await player.disconnect()
        await interaction.response.send_message(embed=discord.Embed(title="👋 บาย! ไว้เจอกันใหม่นะมนุษย์", color=discord.Color.dark_gray()))
    else:
        await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้องเสียง!", ephemeral=True)

if __name__ == "__main__":
    server_on()
    bot.run(os.getenv('TOKEN'))