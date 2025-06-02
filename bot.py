import discord
from discord.ext import commands
from discord import app_commands
import wavelink
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re

# Spotify API setup - replace with your own credentials
SPOTIFY_CLIENT_ID = '48949b0494bc484395c5ff9dbb5cefb7'
SPOTIFY_CLIENT_SECRET = 'e2f6f070266844adadd79b167e8d7aad'

spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# Lavalink connection info
LAVALINK_HOST = '127.0.0.1'
LAVALINK_PORT = 2333
LAVALINK_PASSWORD = 'youshallnotpass'

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Keep track of queues per guild
queues = {}

def is_spotify_url(url: str):
    return "open.spotify.com" in url

async def search_youtube(query: str, node: wavelink.Node):
    # You can improve this by using yt-dlp or Lavalink search
    tracks = await node.get_tracks(f"ytsearch:{query}")
    return tracks[0] if tracks else None

async def spotify_to_youtube_track(spotify_url: str, node: wavelink.Node):
    # Extract track info using spotipy, then search YouTube
    track_id = spotify_url.split("/")[-1].split("?")[0]
    track = spotify.track(track_id)
    query = f"{track['name']} {track['artists'][0]['name']}"
    return await search_youtube(query, node)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"Logged in as {self.bot.user}")
        # Connect Lavalink node on ready
        if not hasattr(self.bot, "lavalink"):
            self.bot.lavalink = wavelink.Client(bot=self.bot)
            await self.bot.lavalink.create_node(
                host=LAVALINK_HOST,
                port=LAVALINK_PORT,
                password=LAVALINK_PASSWORD,
                region="us_central"
            )
        print("Lavalink node connected.")

    async def connect_voice(self, interaction: discord.Interaction):
        # Connect to voice channel user is in
        if interaction.user.voice is None:
            await interaction.response.send_message("You must be connected to a voice channel.", ephemeral=True)
            return None
        channel = interaction.user.voice.channel
        player = self.bot.lavalink.get_player(interaction.guild.id)
        if not player or not player.is_connected():
            player = await channel.connect(cls=wavelink.Player)
        else:
            await player.move_to(channel)
        return player

    async def play_next(self, interaction: discord.Interaction, guild_id):
        if queues[guild_id]:
            player = self.bot.lavalink.get_player(guild_id)
            track = queues[guild_id].pop(0)
            await player.play(track)
            await interaction.channel.send(f"Now playing: {track.title}")
        else:
            player = self.bot.lavalink.get_player(guild_id)
            await player.disconnect()
            await interaction.channel.send("Queue ended, leaving voice channel.")

    @app_commands.command(name="play", description="Play a song from YouTube or Spotify")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        player = await self.connect_voice(interaction)
        if player is None:
            return
        
        # Initialize queue if none
        if interaction.guild.id not in queues:
            queues[interaction.guild.id] = []

        node = self.bot.lavalink.get_node()

        # Check if query is a Spotify URL
        if is_spotify_url(query):
            track = await spotify_to_youtube_track(query, node)
            if not track:
                await interaction.followup.send("Couldn't find the track on YouTube.")
                return
        else:
            # Direct YouTube or search query
            # If URL is a YouTube link, Lavalink can handle it directly
            if re.match(r'https?://(www\.)?(youtube\.com|youtu\.be)/.+', query):
                tracks = await node.get_tracks(query)
                track = tracks[0] if tracks else None
            else:
                # Search YouTube by query string
                track = await search_youtube(query, node)

            if not track:
                await interaction.followup.send("No tracks found.")
                return

        # Queue or play immediately
        player = self.bot.lavalink.get_player(interaction.guild.id)

        if not player.is_playing():
            await player.play(track)
            await interaction.followup.send(f"Now playing: {track.title}")
        else:
            queues[interaction.guild.id].append(track)
            await interaction.followup.send(f"Added to queue: {track.title}")

    @app_commands.command(name="skip", description="Skip the currently playing song")
    async def skip(self, interaction: discord.Interaction):
        player = self.bot.lavalink.get_player(interaction.guild.id)
        if not player or not player.is_playing():
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await player.stop()
        await interaction.response.send_message("Skipped current song.")
        # Play next in queue
        if interaction.guild.id in queues and queues[interaction.guild.id]:
            next_track = queues[interaction.guild.id].pop(0)
            await player.play(next_track)
            await interaction.followup.send(f"Now playing: {next_track.title}")
        else:
            await player.disconnect()

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction):
        player = self.bot.lavalink.get_player(interaction.guild.id)
        if not player or not player.is_playing():
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await player.pause()
        await interaction.response.send_message("Paused.")

    @app_commands.command(name="resume", description="Resume the current song")
    async def resume(self, interaction: discord.Interaction):
        player = self.bot.lavalink.get_player(interaction.guild.id)
        if not player or not player.is_paused():
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)
            return
        await player.resume()
        await interaction.response.send_message("Resumed.")

    @app_commands.command(name="queue", description="Show the current queue")
    async def queue_cmd(self, interaction: discord.Interaction):
        q = queues.get(interaction.guild.id, [])
        if not q:
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return
        msg = "**Queue:**\n" + "\n".join([f"{i+1}. {track.title}" for i, track in enumerate(q[:10])])
        await interaction.response.send_message(msg)

async def main():
    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start("your_discord_bot_token_here")

asyncio.run(main())

