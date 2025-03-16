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
last_messages = defaultdict(str)

SPAM_THRESHOLD = 4  # 秒
SPAM_LIMIT = 5  # 短時間で5回以上送信
DUPLICATE_LIMIT = 3  # 同じメッセージを3回連続で送信

JST = timezone(timedelta(hours=9))  # 日本時間

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}!")

@bot.command(name="anti-spam")
@commands.has_permissions(administrator=True)
async def anti_spam(ctx):
    bot.anti_spam_enabled = not bot.anti_spam_enabled
    status = "有効" if bot.anti_spam_enabled else "無効"
    await ctx.send(f"スパム検出を{status}にしました！")

@bot.command(name="link-filter-on")
@commands.has_permissions(administrator=True)
async def link_filter_on(ctx):
    bot.link_filter_enabled = True
    await ctx.send("リンクフィルターが有効になりました！")

@bot.command(name="link-filter-off")
@commands.has_permissions(administrator=True)
async def link_filter_off(ctx):
    bot.link_filter_enabled = False
    await ctx.send("リンクフィルターが無効になりました！")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.anti_spam_enabled:
        now = datetime.now(timezone.utc)
        user_messages = spam_tracker[message.author.id]
        user_messages.append(message)

        # 直近のメッセージのみ残す
        spam_tracker[message.author.id] = [
            msg for msg in user_messages if (now - msg.created_at).total_seconds() <= SPAM_THRESHOLD
        ]

        # **短時間に5回以上送信 → スパム**
        if len(spam_tracker[message.author.id]) >= SPAM_LIMIT:
            await handle_spam_detection(message)
            return

        # **同じ内容のメッセージを3回連続で送信 → スパム**
        if last_messages[message.author.id] == message.content:
            if spam_tracker[message.author.id].count(message) >= DUPLICATE_LIMIT:
                await handle_spam_detection(message)
                return
        last_messages[message.author.id] = message.content

    # **リンクフィルター**
    if bot.link_filter_enabled and "http" in message.content:
        await message.delete()
        await message.channel.send(f"{message.author.mention} リンクは禁止されています。")

    await bot.process_commands(message)

async def handle_spam_detection(message):
    await message.author.timeout(timedelta(days=7), reason="スパム検出")

    spam_content = "\n".join([msg.content for msg in spam_tracker[message.author.id]])
    alert_message = await message.channel.send(
        f"⚠️ **スパムが検出されました。**\n"
        f"👤 ユーザー: {message.author.mention}\n"
        f"📜 スパム内容:\n```\n{spam_content}\n```"
    )
    await alert_message.add_reaction("✅")  # タイムアウト解除
    await alert_message.add_reaction("❌")  # BAN

    def check(reaction, user):
        return (
            user.guild_permissions.administrator
            and reaction.message.id == alert_message.id
            and user != message.author
        )

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        if str(reaction.emoji) == "❌":
            await message.guild.ban(message.author, reason="スパム")
            await message.channel.send(f"{message.author.mention} をBANしました。")
        elif str(reaction.emoji) == "✅":
            await message.author.edit(timed_out_until=None)
            await message.channel.send(f"{message.author.mention} のタイムアウトを解除しました。")
    except asyncio.TimeoutError:
        await message.channel.send("管理者の対応がありませんでした。")

bot.run(os.getenv("TOKEN"))
