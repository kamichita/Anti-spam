import discord
from discord.ext import commands
import asyncio
from collections import defaultdict
import os
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.link_filter_enabled = False
bot.anti_spam_enabled = False

spam_tracker = defaultdict(list)
mention_tracker = defaultdict(list)
last_messages = defaultdict(str)
user_spam_count = defaultdict(int)
recent_voters = {}

SPAM_THRESHOLD = 10
SPAM_LIMIT = 5
MENTION_LIMIT = 5
DUPLICATE_LIMIT = 3
VOTE_COOLDOWN = 3  

JST = timezone(timedelta(hours=9))

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}!")

@bot.command(name="anti-spam")
@commands.has_permissions(administrator=True)
async def anti_spam(ctx):
    bot.anti_spam_enabled = not bot.anti_spam_enabled
    await ctx.send(f"スパム検出を{'有効' if bot.anti_spam_enabled else '無効'}にしました！")

@bot.command(name="usertimeoutoff")
@commands.has_permissions(administrator=True)
async def usertimeoutoff(ctx, user_id: int):
    user = ctx.guild.get_member(user_id)
    if user:
        await user.edit(timed_out_until=None)
        await ctx.send(f"{user.mention} のタイムアウトを解除しました。")
    else:
        await ctx.send("ユーザーが見つかりません。")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.now(timezone.utc)

    if bot.anti_spam_enabled:
        user_messages = spam_tracker[message.author.id]
        user_messages.append(message)
        spam_tracker[message.author.id] = [
            msg for msg in user_messages if (now - msg.created_at).total_seconds() <= SPAM_THRESHOLD
        ]

        if len(spam_tracker[message.author.id]) >= SPAM_LIMIT:
            await handle_spam_detection(message)
            return

        if last_messages[message.author.id] == message.content:
            if spam_tracker[message.author.id].count(message) >= DUPLICATE_LIMIT:
                await handle_spam_detection(message)
                return
        last_messages[message.author.id] = message.content

        mention_tracker[message.author.id].append(now)
        mention_tracker[message.author.id] = [
            t for t in mention_tracker[message.author.id] if (now - t).total_seconds() <= 10
        ]

        if len(mention_tracker[message.author.id]) >= MENTION_LIMIT:
            await handle_spam_detection(message)
            return

    if bot.link_filter_enabled and "http" in message.content:
        await message.delete()
        await message.channel.send(f"{message.author.mention} リンクは禁止されています。")

    await bot.process_commands(message)

async def handle_spam_detection(message):
    user_id = message.author.id
    user_spam_count[user_id] += 1

    if user_spam_count[user_id] == 6:
        await message.author.timeout(None, reason="スパム検出 - 永久タイムアウト")
        await message.channel.send(f"{message.author.mention} を**永久タイムアウト**しました。")
        return

    await message.author.timeout(timedelta(days=7), reason="スパム検出")

    spam_content = "\n".join([msg.content for msg in spam_tracker[user_id]])
    embed = discord.Embed(
        title="⚠️ **スパムが検出されました。Banしますか？**",
        description="✅ **Ban**\n❌ **タイムアウトを解除**",
        color=discord.Color.red()
    )
    embed.add_field(name="👤 ユーザー", value=f"{message.author.mention}", inline=False)
    embed.add_field(name="📜 スパム内容", value=f"```\n{spam_content}\n```", inline=False)

    alert_message = await message.channel.send(embed=embed)
    await alert_message.add_reaction("✅")
    await alert_message.add_reaction("❌")

    def check(reaction, user):
        return reaction.message.id == alert_message.id and not user.bot

    try:
        while True:
            reaction, user = await bot.wait_for("reaction_add", timeout=86400.0, check=check)

            if user.id in recent_voters and (datetime.now() - recent_voters[user.id]).total_seconds() < VOTE_COOLDOWN:
                continue

            recent_voters[user.id] = datetime.now()
            await alert_message.remove_reaction(reaction.emoji, user)

            if str(reaction.emoji) == "✅":
                await message.guild.ban(message.author, reason="スパム")
                await message.channel.send(f"{message.author.mention} を**BAN**しました。")
                await alert_message.delete()
                return

            elif str(reaction.emoji) == "❌":
                await message.author.edit(timed_out_until=None)
                await message.channel.send(f"{message.author.mention} の**タイムアウトを解除**しました。")
                await alert_message.delete()
                return
    except asyncio.TimeoutError:
        await message.channel.send("⏳ **荒らしの対応がありませんでした。**")


bot.run(os.getenv("TOKEN"))
