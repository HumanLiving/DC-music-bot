import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import yt_dlp
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)
music_queue = {}

class MusicControlView(discord.ui.View):
    def __init__(self, vc, guild_id, interaction, current_url):
        super().__init__(timeout=None)
        self.vc = vc
        self.guild_id = guild_id
        self.interaction = interaction
        self.current_url = current_url

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.primary)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vc.is_playing():
            self.vc.pause()
            await interaction.response.send_message("⏸️ 暫停播放", ephemeral=True)

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vc.is_paused():
            self.vc.resume()
            await interaction.response.send_message("▶️ 繼續播放", ephemeral=True)

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.vc.is_playing():
            self.vc.stop()
            await interaction.response.send_message("⏭️ 已跳過", ephemeral=True)

    @discord.ui.button(label="🔁 Restart", style=discord.ButtonStyle.secondary)
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.vc.stop()
        music_queue[self.guild_id].insert(0, self.current_url)
        await interaction.response.send_message("🔁 重新播放", ephemeral=True)

    @discord.ui.button(label="⏹️ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.vc.disconnect()
        music_queue[self.guild_id] = []
        await interaction.response.send_message("⏹️ 停止播放並離開語音", ephemeral=True)

async def play_next(interaction, guild_id):
    if music_queue[guild_id]:
        next_url = music_queue[guild_id].pop(0)
        await play_song(interaction, next_url)
    else:
        # 沒有下一首 → 等 10 秒，如果還是空的就退出
        await asyncio.sleep(10)
        if not music_queue[guild_id]:  # 確認 10 秒後還是沒歌
            vc = interaction.guild.voice_client
            if vc and vc.is_connected():
                await vc.disconnect()
                await interaction.channel.send("📭 播放完畢，已自動離開語音頻道。")


async def play_song(interaction, url):
    guild = interaction.guild
    guild_id = guild.id
    voice_client = guild.voice_client

    try:
        # 若 bot 不在語音頻道，自動加入使用者的語音頻道
        if not voice_client or not voice_client.is_connected():
            user_vc = interaction.user.voice.channel if interaction.user.voice else None
            if user_vc:
                voice_client = await user_vc.connect()
            else:
                await interaction.followup.send("❌ 找不到你的語音頻道")
                return

        ydl_opts = {
            'format': 'bestaudio',
            'quiet': True,
            'noplaylist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
            title = info.get('title')
            duration = info.get('duration')
            webpage_url = info.get('webpage_url')
            video_id = info.get('id')

        source = await discord.FFmpegOpusAudio.from_probe(
            audio_url,
            method='fallback',
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        )

        def after_play(e):
            if e:
                print(f"播放錯誤：{e}")
                music_queue[guild_id].insert(0, url)
            fut = asyncio.run_coroutine_threadsafe(play_next(interaction, guild_id), bot.loop)
            try:
                fut.result()
            except Exception as ex:
                print(f"播放下一首時發生錯誤：{ex}")

        voice_client.play(source, after=after_play)

        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        embed = discord.Embed(title="🎵 Now Playing", description=f"[{title}]({webpage_url})", color=0x1DB954)
        embed.set_thumbnail(url=thumbnail_url)
        embed.set_footer(text="音樂機器人")
        embed.add_field(name="時長", value=f"{duration // 60}:{duration % 60:02d}")

        view = MusicControlView(voice_client, guild_id, interaction, url)
        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        print(f"錯誤：{e}")
        await interaction.followup.send(f"❌ 播放失敗：{e}")

@bot.tree.command(name="play", description="播放 YouTube 音樂")
@app_commands.describe(url="YouTube 音樂連結")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    user = interaction.user
    guild_id = interaction.guild.id

    if not user.voice or not user.voice.channel:
        await interaction.followup.send("❗ 請先加入語音頻道")
        return

    if guild_id not in music_queue:
        music_queue[guild_id] = []

    voice_client = interaction.guild.voice_client

    if voice_client and voice_client.is_playing():
        music_queue[guild_id].append(url)
        await interaction.followup.send("✅ 已加入播放序列")
    else:
        await play_song(interaction, url)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} 已上線")

bot.run(TOKEN)