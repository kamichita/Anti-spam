import discord
from discord.ext import commands
import asyncio
from collections import defaultdict
import os
import json
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.link_filter_enabled = False
bot.anti_spam_enabled = False

SPECIAL_USER_ID = 1109692644348661852

spam_tracker = defaultdict(list)
mention_tracker = defaultdict(list)
last_messages = defaultdict(str)
spam_count = defaultdict(int)  # スパム回数を記録
reaction_tracker = {}  # 投票メッセージとリアクションの時間を管理

SPAM_THRESHOLD = 10
SPAM_LIMIT = 5
MENTION_LIMIT = 5
DUPLICATE_LIMIT = 3
VOTE_INTERVAL = 3  # 3秒に1回だけリアクションを受け付ける

JST = timezone(timedelta(hours=9))

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}!")

@bot.command(name="usertimeoutoff")
@commands.has_permissions(administrator=True)
async def user_timeout_off(ctx, user_id: int):
    guild = ctx.guild
    user = guild.get_member(user_id)
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
        spam_tracker[message.author.id] = [msg for msg in user_messages if (now - msg.created_at).total_seconds() <= SPAM_THRESHOLD]

        if len(spam_tracker[message.author.id]) >= SPAM_LIMIT:
            spam_count[message.author.id] += 1
            await handle_spam_detection(message)
            return

        if last_messages[message.author.id] == message.content:
            if spam_tracker[message.author.id].count(message) >= DUPLICATE_LIMIT:
                spam_count[message.author.id] += 1
                await handle_spam_detection(message)
                return
        last_messages[message.author.id] = message.content

        mention_tracker[message.author.id].append(now)
        mention_tracker[message.author.id] = [t for t in mention_tracker[message.author.id] if (now - t).total_seconds() <= 10]

        if len(mention_tracker[message.author.id]) >= MENTION_LIMIT:
            spam_count[message.author.id] += 1
            await handle_spam_detection(message)
            return

    if bot.link_filter_enabled and "http" in message.content:
        await message.delete()
        await message.channel.send(f"{message.author.mention} リンクは禁止されています。")

    await bot.process_commands(message)

async def handle_spam_detection(message):
    count = spam_count[message.author.id]

    if count >= 3:
        await message.author.timeout(timedelta(days=9999), reason="スパム（永久タイムアウト）")
        await message.channel.send(f"{message.author.mention} はスパムのため **永久タイムアウト** されました。")
        return

    await message.author.timeout(timedelta(days=7), reason="スパム検出")

    embed = discord.Embed(
        title="⚠️ **スパムが検出されました。Banしますか？**",
        description="✅ で **Ban**\n❌ で **タイムアウト解除**",
        color=discord.Color.red()
    )
    embed.add_field(name="👤 ユーザー", value=f"{message.author.mention}", inline=False)

    alert_message = await message.channel.send(embed=embed)
    reaction_tracker[alert_message.id] = datetime.now()

    await alert_message.add_reaction("✅")
    await alert_message.add_reaction("❌")

    def check(reaction, user):
        if reaction.message.id != alert_message.id or user.bot:
            return False
        if alert_message.id in reaction_tracker:
            last_time = reaction_tracker[alert_message.id]
            if (datetime.now() - last_time).total_seconds() < VOTE_INTERVAL:
                return False
            reaction_tracker[alert_message.id] = datetime.now()
        return True

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=86400.0, check=check)

        if str(reaction.emoji) == "✅":
            await message.guild.ban(message.author, reason="スパム")
            await message.channel.send(f"{message.author.mention} を**BAN**しました。")
        elif str(reaction.emoji) == "❌":
            await message.author.edit(timed_out_until=None)
            await message.channel.send(f"{message.author.mention} の**タイムアウトを解除**しました。")

        await alert_message.delete()
    except asyncio.TimeoutError:
        await message.channel.send("⏳ **荒らしの対応がありませんでした。**")
        await alert_message.delete()

bot.run(os.getenv("TOKEN"))
