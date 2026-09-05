import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

# Per-server state
countdown_running = {}
countdown_message = {}
last_session_key = {}
sent_alerts = {}


def get_all_conference_sessions():
    tz = ZoneInfo("America/Denver")
    now = datetime.now(tz)
    year = now.year

    april_sessions = [
        ("Saturday Morning", datetime(year, 4, 4, 10, 0, tzinfo=tz)),
        ("Saturday Afternoon", datetime(year, 4, 4, 14, 0, tzinfo=tz)),
        ("Sunday Morning", datetime(year, 4, 5, 10, 0, tzinfo=tz)),
        ("Sunday Afternoon", datetime(year, 4, 5, 14, 0, tzinfo=tz)),
    ]

    october_sessions = [
        ("Saturday Morning", datetime(year, 10, 3, 10, 0, tzinfo=tz)),
        ("Saturday Afternoon", datetime(year, 10, 3, 14, 0, tzinfo=tz)),
        ("Sunday Morning", datetime(year, 10, 4, 10, 0, tzinfo=tz)),
        ("Sunday Afternoon", datetime(year, 10, 4, 14, 0, tzinfo=tz)),
    ]

    all_sessions = april_sessions + october_sessions
    future_sessions = [(name, dt) for name, dt in all_sessions if dt > now]

    if future_sessions:
        return future_sessions

    next_year = year + 1
    return [
        ("Saturday Morning", datetime(next_year, 4, 4, 10, 0, tzinfo=tz)),
        ("Saturday Afternoon", datetime(next_year, 4, 4, 14, 0, tzinfo=tz)),
        ("Sunday Morning", datetime(next_year, 4, 5, 10, 0, tzinfo=tz)),
        ("Sunday Afternoon", datetime(next_year, 4, 5, 14, 0, tzinfo=tz)),
    ]


def get_next_session():
    sessions = get_all_conference_sessions()
    session_name, session_time = sessions[0]
    conference_name = "April General Conference" if session_time.month == 4 else "October General Conference"
    session_key = f"{conference_name}|{session_name}|{int(session_time.timestamp())}"
    return conference_name, session_name, session_time, session_key


def format_countdown(target_time):
    now = datetime.now(target_time.tzinfo)
    diff = target_time - now

    if diff.total_seconds() <= 0:
        return "0d 0h 0m 0s"

    total = int(diff.total_seconds())
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60

    return f"{days}d {hours}h {minutes}m {seconds}s"


def discord_timestamp(dt: datetime, style: str = "F") -> str:
    return f"<t:{int(dt.timestamp())}:{style}>"


def build_embed(conference_name, session_name, session_time, started=False):
    embed = discord.Embed(
        title="🌸 General Conference Live Countdown",
        description="Prepare your heart for General Conference 🤍",
        color=0xF8A5C2
    )

    embed.add_field(name="🌷 Conference", value=conference_name, inline=False)
    embed.add_field(name="✨ Next Session", value=session_name, inline=False)
    embed.add_field(name="🕊️ Starts", value=discord_timestamp(session_time, "F"), inline=False)

    if started:
        embed.add_field(name="💖 Status", value="This session has started.", inline=False)
    else:
        embed.add_field(
            name="⏳ Time Remaining",
            value=f"{discord_timestamp(session_time, 'R')}\n⌛ {format_countdown(session_time)}",
            inline=False
        )

    embed.add_field(
        name="📖 Scripture",
        value="“Whether by mine own voice or by the voice of my servants, it is the same.” — D&C 1:38",
        inline=False
    )

    embed.set_footer(text="The Church of Jesus Christ of Latter-day Saints")
    return embed


async def send_alerts(guild_id, channel, conference_name, session_name, session_time, session_key):
    now = datetime.now(session_time.tzinfo)
    seconds_left = int((session_time - now).total_seconds())

    alert_points = {
        3600: "🌸 One hour until",
        1800: "💗 Thirty minutes until",
        600: "🕊️ Ten minutes until"
    }

    if guild_id not in sent_alerts:
        sent_alerts[guild_id] = set()

    for threshold, label in alert_points.items():
        alert_key = f"{session_key}|{threshold}"

        if 0 < seconds_left <= threshold and alert_key not in sent_alerts[guild_id]:
            await channel.send(
                f"{label} **{session_name}** in **{conference_name}**!\n"
                f"🕰️ Starts: {discord_timestamp(session_time, 'F')} ({discord_timestamp(session_time, 'R')})"
            )
            sent_alerts[guild_id].add(alert_key)


@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} command(s)")
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="conference_timer", description="Start the live General Conference countdown")
async def conference_timer(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("❌ Use this in a server.", ephemeral=True)
        return

    guild_id = interaction.guild.id

    if countdown_running.get(guild_id, False):
        msg = countdown_message.get(guild_id)
        await interaction.response.send_message(
            f"🌸 Already running: {msg.jump_url if msg else ''}",
            ephemeral=True
        )
        return

    countdown_running[guild_id] = True
    sent_alerts[guild_id] = set()

    try:
        conference_name, session_name, session_time, session_key = get_next_session()
        last_session_key[guild_id] = session_key

        await interaction.response.send_message(
            embed=build_embed(conference_name, session_name, session_time)
        )

        message = await interaction.original_response()
        countdown_message[guild_id] = message

        try:
            await message.pin()
        except Exception as pin_error:
            print("Pin failed:", pin_error)

        while True:
            try:
                conference_name, session_name, session_time, new_key = get_next_session()
                now = datetime.now(session_time.tzinfo)

                if new_key != last_session_key[guild_id]:
                    last_session_key[guild_id] = new_key
                    sent_alerts[guild_id] = set()

                await send_alerts(
                    guild_id,
                    interaction.channel,
                    conference_name,
                    session_name,
                    session_time,
                    new_key
                )

                if now >= session_time:
                    await message.edit(
                        embed=build_embed(conference_name, session_name, session_time, True)
                    )
                    await asyncio.sleep(5)
                    continue

                await message.edit(
                    embed=build_embed(conference_name, session_name, session_time)
                )

                await asyncio.sleep(1)

            except Exception as loop_error:
                print("LOOP ERROR:", loop_error)
                await asyncio.sleep(5)

    finally:
        countdown_running[guild_id] = False
        countdown_message[guild_id] = None


@bot.tree.command(name="conference_view", description="Jump to the current countdown")
async def conference_view(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("❌ Use this in a server.", ephemeral=True)
        return

    guild_id = interaction.guild.id

    if not countdown_running.get(guild_id):
        await interaction.response.send_message("❌ No countdown running.", ephemeral=True)
        return

    msg = countdown_message.get(guild_id)

    await interaction.response.send_message(
        f"🌸 Jump here: {msg.jump_url}" if msg else "❌ Not found.",
        ephemeral=True
    )


bot.run(TOKEN)