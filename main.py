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

SPAM_THRESHOLD = 10  # 秒
SPAM_LIMIT = 5  # 短時間で5回以上送信
MENTION_LIMIT = 5  # 10秒以内に5回以上メンション
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

    now = datetime.now(timezone.utc)

    # **新規メンバー判定**
    joined_at = message.author.joined_at
    is_new_member = (now - joined_at).total_seconds() < 86400  # 1日未満

    if bot.anti_spam_enabled:
        # **メッセージスパム検出**
        user_messages = spam_tracker[message.author.id]
        user_messages.append(message)

        # 直近のメッセージのみ残す
        spam_tracker[message.author.id] = [
            msg for msg in user_messages if (now - msg.created_at).total_seconds() <= SPAM_THRESHOLD
        ]

        if len(spam_tracker[message.author.id]) >= SPAM_LIMIT:
            await handle_spam_detection(message)
            return

        # **同じ内容のメッセージを3回連続で送信 → スパム**
        if last_messages[message.author.id] == message.content:
            if spam_tracker[message.author.id].count(message) >= DUPLICATE_LIMIT:
                await handle_spam_detection(message)
                return
        last_messages[message.author.id] = message.content

        # **メンションスパム検出**
        mention_tracker[message.author.id].append(now)
        mention_tracker[message.author.id] = [
            t for t in mention_tracker[message.author.id] if (now - t).total_seconds() <= 10
        ]

        if len(mention_tracker[message.author.id]) >= MENTION_LIMIT:
            await handle_spam_detection(message)
            return

    # **リンクフィルター**
    if bot.link_filter_enabled and "http" in message.content:
        await message.delete()
        await message.channel.send(f"{message.author.mention} リンクは禁止されています。")

    await bot.process_commands(message)

async def handle_spam_detection(message):
    await message.author.timeout(timedelta(days=7), reason="スパム検出")

    spam_content = "\n".join([msg.content for msg in spam_tracker[message.author.id]])
    embed = discord.Embed(
        title="⚠️ **スパムが検出されました。Banしますか？**",
        description=(
            "✅ リアクションで **Ban** します\n"
            "❌ リアクションで **タイムアウトを解除** します"
        ),
        color=discord.Color.red()
    )
    embed.add_field(name="👤 ユーザー", value=f"{message.author.mention}", inline=False)
    embed.add_field(name="📜 スパム内容", value=f"```\n{spam_content}\n```", inline=False)

    alert_message = await message.channel.send(embed=embed)
    await alert_message.add_reaction("✅")  # Ban
    await alert_message.add_reaction("❌")  # タイムアウト解除

    def check(reaction, user):
        return (
            user.guild_permissions.administrator
            and reaction.message.id == alert_message.id
            and user != message.author
        )

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
        await alert_message.remove_reaction(reaction.emoji, user)

        if str(reaction.emoji) == "✅":
            await message.guild.ban(message.author, reason="スパム")
            await message.channel.send(f"{message.author.mention} を**BAN**しました。")
        elif str(reaction.emoji) == "❌":
            await message.author.edit(timed_out_until=None)
            await message.channel.send(f"{message.author.mention} の**タイムアウトを解除**しました。")
    except asyncio.TimeoutError:
        await message.channel.send("⏳ **管理者の対応がありませんでした。**")

bot.run(os.getenv("TOKEN"))
