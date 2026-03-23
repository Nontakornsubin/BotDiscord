import os
import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio

from myserver import server_on

class MonkeyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!Monkey", intents=intents)

    async def setup_hook(self):
        # 🌟 ตั้งค่า Wavelink เพื่อเชื่อมต่อกับเซิร์ฟเวอร์ Lavalink สาธารณะ (ฟรี & ทะลวง YouTube 100%)
        nodes = [
            wavelink.Node(
                uri="https://lava-v4.ajieblogs.eu.org",
                password="https://dsc.gg/ajidevserver"
            )
        ]
        # เชื่อมต่อระบบ
        await wavelink.Pool.connect(client=self, nodes=nodes)
        await self.tree.sync()
        print(f"Synced Slash Commands for {self.user}")

    async def on_ready(self):
        print(f"✅ บอทออนไลน์แล้วในชื่อ: {self.user}")
        print("------")

bot = MonkeyBot()

# --- อีเวนต์: เมื่อเชื่อมต่อ Lavalink สำเร็จ ---
@bot.event
async def on_wavelink_node_ready(payload: wavelink.NodeReadyEventPayload):
    print(f"🔥 Lavalink Node เชื่อมต่อสำเร็จ! พร้อมทะลวง YouTube ทุกคลิป!")

# --- อีเวนต์: แจ้งเตือนเมื่อเล่นเพลงถัดไปในคิว ---
@bot.event
async def on_wavelink_track_start(payload: wavelink.TrackStartEventPayload):
    player: wavelink.Player = payload.player
    if not player:
        return
        
    track: wavelink.Playable = payload.track

    # ป้องกันไม่ให้บอทส่งข้อความซ้ำซ้อนตอนเราเพิ่งพิมพ์คำสั่ง /play
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
    
    # ส่งข้อความไปยังห้องแชทล่าสุดที่สั่งเพลง
    if hasattr(player, 'home_channel'):
        await player.home_channel.send(embed=embed)


# --- Slash Command: /play ---
@bot.tree.command(name="play", description="เล่นเพลงหรือเพิ่มเพลงเข้าในคิว")
@app_commands.describe(search="ชื่อเพลงหรือลิงก์ YouTube")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        embed = discord.Embed(description="❌ **กูจะรู้ไหมว่าคุณมึงอยู่ห้องไหน!**", color=discord.Color.red())
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    await interaction.response.defer()

    # ดึงตัวเล่นเพลง หรือสร้างใหม่ถ้ายังไม่เข้าห้อง
    if not interaction.guild.voice_client:
        try:
            player: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player, timeout=60.0, self_deaf=True)
            player.home_channel = interaction.channel # จำห้องแชทไว้ส่งข้อความ
        except Exception as e:
            return await interaction.followup.send(f"❌ เข้าห้องไม่ได้: {e}")
    else:
        player: wavelink.Player = interaction.guild.voice_client
        player.home_channel = interaction.channel

    try:
        # 🌟 ค้นหาเพลงผ่านระบบของ Lavalink (รองรับทั้งชื่อและลิงก์ YouTube เต็มรูปแบบ)
        tracks: wavelink.Search = await wavelink.Playable.search(search)
        if not tracks:
            return await interaction.followup.send("❌ ค้นหาเพลงนี้ไม่พบ! (ลองพิมพ์ชื่อเพลงใหม่ดูนะ)")

        # เลือกเพลงแรกที่หาเจอ
        if isinstance(tracks, wavelink.Playlist):
            track: wavelink.Playable = tracks.tracks[0]
        else:
            track: wavelink.Playable = tracks[0]

        if not player.playing:
            player.is_first_play = True # ทำเครื่องหมายว่าเป็นเพลงแรกที่สั่ง
            await player.play(track, volume=100)
            
            embed = discord.Embed(
                title="🎶 กำลังเล่นเพลง",
                description=f"**[{track.title}]({track.uri})**",
                color=discord.Color.green()
            )
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
            embed.add_field(name="สั่งโดย", value=interaction.user.mention)
            embed.set_footer(text="Monkey Music Bot 🐒 x Lavalink")
            await interaction.followup.send(embed=embed)
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
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาดจากเซิร์ฟเวอร์เพลง: {e}")

# --- Slash Command: /queue (แยกหน้าอัตโนมัติ) ---
@bot.tree.command(name="queue", description="ดูรายการเพลงที่อยู่ในคิวทั้งหมดตอนนี้")
async def queue(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if not player or player.queue.is_empty:
        embed = discord.Embed(description="📭 **ตอนนี้ไม่มีเพลงในคิวเลย ว่างจัด**", color=discord.Color.light_gray())
        return await interaction.response.send_message(embed=embed)

    await interaction.response.defer()

    embeds = []
    current_desc = ""
    
    # วนลูปโชว์คิวแบบรองรับความยาวทะลุลิมิต 100 เพลง+
    for i, track in enumerate(player.queue): 
        line = f"`{i+1}.` [{track.title}]({track.uri})\n"
        
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

    if current_desc:
        embed = discord.Embed(
            title=f"📋 รายการเพลงในคิว (ส่วนที่ {len(embeds) + 1})", 
            description=current_desc, 
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"รวมทั้งหมด {player.queue.count} เพลง | Monkey Music Bot 🐒")
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
    player: wavelink.Player = interaction.guild.voice_client

    if not player or not player.playing:
        return await interaction.response.send_message(embed=discord.Embed(description="❌ ไม่ได้เล่นเพลงอะไรอยู่!", color=discord.Color.red()), ephemeral=True)

    if player.queue.is_empty:
        return await interaction.response.send_message(embed=discord.Embed(description="❌ คิวว่างเปล่า!", color=discord.Color.red()), ephemeral=True)

    if index < 1 or index > player.queue.count:
        return await interaction.response.send_message(embed=discord.Embed(description=f"❌ หาไม่เจอ! กรุณาระบุตัวเลขให้ถูกต้อง (1 ถึง {player.queue.count})", color=discord.Color.red()), ephemeral=True)

    # ดึงเพลงเป้าหมายออกมาจากคิว
    track = player.queue[index - 1]
    del player.queue[index - 1]
    
    embed = discord.Embed(
        title="🦘 กระโดดข้ามคิว!",
        description=f"**ดึงเพลงนี้ขึ้นมาเล่นทันที:**\n[{track.title}]({track.uri})",
        color=discord.Color.purple()
    )
    await interaction.response.send_message(embed=embed)
    
    # แทรกไว้เป็นคิวที่ 1 แล้วข้ามเพลงปัจจุบันเพื่อเล่นทันที
    player.queue.put_at(0, track)
    player.is_first_play = True
    await player.skip(force=True)

# --- Slash Command: /back ---
@bot.tree.command(name="back", description="ย้อนกลับไปเล่นเพลงก่อนหน้าทีละ 1 เพลง")
async def back(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client

    if not player or not player.playing:
        return await interaction.response.send_message(embed=discord.Embed(description="❌ ไม่ได้เล่นเพลงอะไรอยู่!", color=discord.Color.red()), ephemeral=True)

    # ประวัติเพลงถูกเก็บไว้ใน player.queue.history
    if player.queue.history.is_empty:
        embed = discord.Embed(description="❌ **ย้อนสุดเเล้วโว้ยยยย!** (ไม่มีเพลงก่อนหน้า)", color=discord.Color.red())
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    current_track = player.current
    prev_track = player.queue.history[-1] # เพลงล่าสุดที่เพิ่งเล่นจบไป
    del player.queue.history[-1] # ลบออกจากประวัติ

    # เอาเพลงปัจจุบันยัดกลับไปรอคิวที่ 2
    if current_track:
        player.queue.put_at(0, current_track)
    
    # เอาเพลงในอดีตยัดไปรอคิวที่ 1
    player.queue.put_at(0, prev_track)
    
    embed = discord.Embed(
        title="⏪ ย้อนกลับ 1 เพลง",
        description=f"**ครับพี่เดี๋ยวเล่นเพลงเดิมให้:**\n[{prev_track.title}]({prev_track.uri})",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)
    
    player.is_first_play = True
    await player.skip(force=True)

# --- Slash Command: /skip ---
@bot.tree.command(name="skip", description="ข้ามเพลงปัจจุบัน")
async def skip(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player and player.playing:
        embed = discord.Embed(description="⏩ **ข้ามล่ะ!**", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)
        await player.skip(force=True) 
    else:
        embed = discord.Embed(description="❌ **ไม่ได้เล่นเพลงอะไรอยู่จะให้กูข้ามอะไรก่อน!**", color=discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Slash Command: /stop ---
@bot.tree.command(name="stop", description="หยุดเพลงและให้บอทออกจากห้องเสียง")
async def stop(interaction: discord.Interaction):
    player: wavelink.Player = interaction.guild.voice_client
    if player:
        player.queue.clear() # ล้างคิวให้เกลี้ยง
        await player.disconnect()
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