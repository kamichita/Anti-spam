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

SPECIAL_USER_ID = 1109692644348661852

spam_tracker = defaultdict(list)
SPAM_THRESHOLD = 4
SPAM_LIMIT = 5

JST = timezone(timedelta(hours=9))

def is_admin(ctx):
    admin_role = discord.utils.get(ctx.guild.roles, name="管理者")
    return admin_role in ctx.author.roles or ctx.author.id == SPECIAL_USER_ID

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}!")

@bot.command(name="anti-spam")
async def anti_spam(ctx):
    if not is_admin(ctx):
        await ctx.send("このコマンドは管理者のみが使用できます！")
        return
    await ctx.send("スパム検出が有効になりました！")

@bot.command(name="link-フィルターon")
async def link_filter_on(ctx):
    if not is_admin(ctx):
        await ctx.send("このコマンドは管理者のみが使用できます！")
        return
    bot.link_filter_enabled = True
    await ctx.send("リンクフィルターが有効になりました！")

@bot.command(name="link-フィルターoff")
async def link_filter_off(ctx):
    if not is_admin(ctx):
        await ctx.send("このコマンドは管理者のみが使用できます！")
        return
    bot.link_filter_enabled = False
    await ctx.send("リンクフィルターが無効になりました！")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.now(timezone.utc)
    user_messages = spam_tracker[message.author.id]
    user_messages.append(message)

    spam_tracker[message.author.id] = [
        msg for msg in user_messages if (now - msg.created_at).total_seconds() <= SPAM_THRESHOLD
    ]

    if len(spam_tracker[message.author.id]) >= SPAM_LIMIT:
        await message.author.timeout(timedelta(days=7), reason="スパム検出")
        spam_content = "\n".join([msg.content for msg in spam_tracker[message.author.id]])
        alert_message = await message.channel.send(
            f"⚠️ スパムが検出されました。\nユーザー: {message.author.mention}\nスパム内容:\n{spam_content}"
        )
        await alert_message.add_reaction("🦵")
        await alert_message.add_reaction("🟩")

        def check(reaction, user):
            return user.guild_permissions.administrator and reaction.message.id == alert_message.id

        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
            if str(reaction.emoji) == "🦵":
                await message.guild.ban(message.author, reason="スパム")
                await message.channel.send(f"{message.author.mention} をBANしました。")
            elif str(reaction.emoji) == "🟩":
                await message.author.edit(timed_out_until=None)
                await message.channel.send(f"{message.author.mention} のタイムアウトを解除しました。")
        except asyncio.TimeoutError:
            await message.channel.send("管理者の対応がありませんでした。")
        return

    if bot.link_filter_enabled and "http" in message.content:
        await message.delete()
        await message.channel.send(f"{message.author.mention} リンクは禁止されています。")

    await bot.process_commands(message)

bot.run(os.getenv("TOKEN"))
