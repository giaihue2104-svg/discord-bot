import discord
from discord.ext import commands
import aiohttp
import asyncpg
import os
from rembg import remove
from PIL import Image
import io

TOKEN = os.getenv("TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)

# Only moderators can use command
def is_mod():
    async def predicate(ctx):
        return ctx.author.guild_permissions.manage_roles
    return commands.check(predicate)

@bot.event
async def on_ready():
    bot.db = await asyncpg.create_pool(DATABASE_URL)
    print(f"Logged in as {bot.user}")

# ADDROLE COMMAND
# Usage: !addrole @member "Role Name" #color1 #color2 [icon_url or attach image]
@bot.command()
@is_mod()
async def addrole(
    ctx,
    member: discord.Member,
    role_name: str,
    color1_hex: str,
    color2_hex: str,
    icon_url: str = None
):
    try:
        guild = ctx.guild

        primary_color_int = int(color1_hex.replace("#", ""), 16)
        role_color = discord.Color(primary_color_int)

        # Use attached image if no URL provided
        if not icon_url:
            if ctx.message.attachments:
                icon_url = ctx.message.attachments[0].url
            else:
                await ctx.send("❌ Please provide an image URL or attach an image.")
                return

        await ctx.send("🖼️ Removing background, please wait...")
        async with aiohttp.ClientSession() as session:
            async with session.get(icon_url) as resp:
                if resp.status != 200:
                    await ctx.send("❌ Couldn't download image.")
                    return
                raw_bytes = await resp.read()
        input_image = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
        output_image = remove(input_image)
        output_buffer = io.BytesIO()
        output_image.save(output_buffer, format="PNG")
        icon_bytes = output_buffer.getvalue()

        new_role = await guild.create_role(
            name=role_name,
            color=role_color,
            display_icon=icon_bytes
        )

        # Apply gradient color via Discord API if secondary color is provided
        if color2_hex:
            secondary_color_int = int(color2_hex.replace("#", ""), 16)
            headers = {
                "Authorization": f"Bot {TOKEN}",
                "Content-Type": "application/json"
            }
            payload = {
                "colors": {
                    "primary_color": primary_color_int,
                    "secondary_color": secondary_color_int
                }
            }
            async with aiohttp.ClientSession() as session:
                await session.patch(
                    f"https://discord.com/api/v10/guilds/{guild.id}/roles/{new_role.id}",
                    json=payload,
                    headers=headers
                )

        # Move the role to the top (just below the bot's highest role)
        try:
            bot_top_role = guild.me.top_role
            target_position = bot_top_role.position - 1
            await guild.edit_role_positions(positions={new_role: target_position})
        except Exception as e:
            await ctx.send(f"⚠️ Role created but couldn't move it to the top: {e}")

        await member.add_roles(new_role)

        await ctx.send(
            f"✅ Role **{role_name}** created and given to {member.mention}"
        )

    except discord.Forbidden:
        await ctx.send("❌ Bot lacks permission.")
    except Exception as e:
        print(f"addrole error: {e}")
        await ctx.send(f"❌ Something went wrong: {e}")

# AFK COMMAND
@bot.command()
async def afk(ctx, *, reason="AFK"):
    user_id = str(ctx.author.id)

    existing = await bot.db.fetchrow(
        "SELECT reason FROM afk_users WHERE user_id = $1", user_id
    )
    if existing:
        await ctx.send(f"{ctx.author.mention} you're already AFK: {existing['reason']}")
        return

    await bot.db.execute(
        "INSERT INTO afk_users (user_id, reason) VALUES ($1, $2)",
        user_id, reason
    )
    await ctx.send(f"{ctx.author.mention} is now AFK: {reason}")

# BACK COMMAND
@bot.command()
async def back(ctx):
    user_id = str(ctx.author.id)

    existing = await bot.db.fetchrow(
        "SELECT reason FROM afk_users WHERE user_id = $1", user_id
    )
    if not existing:
        await ctx.send(f"{ctx.author.mention} you're not AFK.")
        return

    await bot.db.execute(
        "DELETE FROM afk_users WHERE user_id = $1", user_id
    )
    await ctx.send(f"Welcome back {ctx.author.mention}!")

# AUTO-REPLY WHEN AN AFK USER IS MENTIONED
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    for mentioned in message.mentions:
        record = await bot.db.fetchrow(
            "SELECT reason, set_at FROM afk_users WHERE user_id = $1",
            str(mentioned.id)
        )
        if record:
            await message.channel.send(
                f"{mentioned.display_name} is currently AFK: {record['reason']}"
            )

    await bot.process_commands(message)

# NEW COMMAND (mod only)
@bot.command(name="new")
@commands.has_permissions(manage_roles=True)
async def new_command(ctx):
    channel_id = 1486623717260791859
    channel = ctx.guild.get_channel(channel_id)

    if channel:
        ticket_channel = ctx.guild.get_channel(1486622352790917162)
        ticket_mention = ticket_channel.mention if ticket_channel else "#ticket-channel"
        await ctx.send(
            f"If you want to be a member of Luminosity, please read our requirements at the {channel.mention} channel and create a ticket at {ticket_mention} channel!"
        )
    else:
        await ctx.send("Announcement channel not found.")

# PURGE COMMAND
# Usage: !purge <number>
@bot.command()
@is_mod()
async def purge(ctx, amount: int):
    if amount < 1 or amount > 500:
        await ctx.send("❌ Please provide a number between 1 and 500.")
        return

    try:
        await ctx.message.delete()
        await ctx.channel.purge(limit=amount)
    except discord.Forbidden:
        await ctx.send("❌ Bot lacks permission to delete messages.")
    except Exception as e:
        await ctx.send(f"❌ Something went wrong: {e}")

# ROLE COMMAND
# Usage: !role @member @Role
@bot.command(name="role")
@is_mod()
async def role_cmd(ctx, member: discord.Member, role: discord.Role):
    if role in member.roles:
        await ctx.send(f"❌ {member.mention} already has the **{role.name}** role.")
        return

    try:
        await member.add_roles(role)
        await ctx.send(f"✅ **{role.name}** has been given to {member.mention}.")
    except discord.Forbidden:
        await ctx.send("❌ Bot lacks permission to assign that role.")
    except Exception as e:
        await ctx.send(f"❌ Something went wrong: {e}")

# DELETEROLE COMMAND
# Usage: !deleterole @member @Role  OR  !deleterole @member Role Name
@bot.command()
@is_mod()
async def deleterole(ctx, member: discord.Member, role: discord.Role):
    if role not in member.roles:
        await ctx.send(f"❌ {member.mention} doesn't have the **{role.name}** role.")
        return

    try:
        await member.remove_roles(role)
        await ctx.send(f"✅ {member.mention} has been removed from **{role.name}**.")
    except discord.Forbidden:
        await ctx.send("❌ Bot lacks permission to delete that role.")
    except Exception as e:
        await ctx.send(f"❌ Something went wrong: {e}")

# ROLEFORM COMMAND
# Usage: !roleform — posts a guide embed showing how to request a custom role
@bot.command()
@is_mod()
async def roleform(ctx):
    embed = discord.Embed(
        title="Custom Role Form",
        description=(
            "Please send us your answer like this form\n\n"
            "```\n"
            "Role Name:\n"
            "Hex Color 1:\n"
            "Hex Color 2:\n"
            "Tag the user:\n"
            "Image: (attach the image)\n"
            "```"
        ),
        color=discord.Color.blurple()
    )
    await ctx.send(embed=embed)

# BAN COMMAND
# Usage: !ban @member [reason]
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    if member == ctx.author:
        await ctx.send("❌ You can't ban yourself.")
        return
    if member.top_role >= ctx.author.top_role:
        await ctx.send("❌ You can't ban someone with an equal or higher role than you.")
        return

    try:
        await member.ban(reason=reason)
        await ctx.send(f"✅ **{member}** has been banned. Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("❌ Bot lacks permission to ban that member.")
    except Exception as e:
        await ctx.send(f"❌ Something went wrong: {e}")

# WARN COMMAND
# Usage: !warn @member [reason]
@bot.command()
@is_mod()
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    await bot.db.execute(
        "INSERT INTO warnings (guild_id, user_id, reason, moderator_id) VALUES ($1, $2, $3, $4)",
        str(ctx.guild.id), str(member.id), reason, str(ctx.author.id)
    )
    await ctx.send(f"⚠️ {member.mention} has been warned. Reason: {reason}")

# WARNINGS COMMAND
# Usage: !warnings @member
@bot.command()
@is_mod()
async def warnings(ctx, member: discord.Member):
    records = await bot.db.fetch(
        "SELECT reason, moderator_id, created_at FROM warnings WHERE guild_id = $1 AND user_id = $2 ORDER BY created_at DESC",
        str(ctx.guild.id), str(member.id)
    )

    if not records:
        await ctx.send(f"{member.mention} has no warnings.")
        return

    embed = discord.Embed(
        title=f"Warnings for {member.display_name}",
        color=discord.Color.orange()
    )
    for i, r in enumerate(records, 1):
        mod = ctx.guild.get_member(int(r['moderator_id']))
        mod_name = mod.display_name if mod else "Unknown"
        embed.add_field(
            name=f"#{i} — {r['created_at'].strftime('%Y-%m-%d')} by {mod_name}",
            value=r['reason'],
            inline=False
        )

    await ctx.send(embed=embed)

# REACTION ROLE SETUP
# Usage: !reactionrole <message_id> <emoji> @Role
@bot.command()
@is_mod()
async def reactionrole(ctx, message_id: int, emoji: str, role: discord.Role):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.add_reaction(emoji)
    except discord.NotFound:
        await ctx.send("❌ Message not found in this channel.")
        return
    except discord.HTTPException:
        await ctx.send("❌ Invalid emoji.")
        return

    await bot.db.execute(
        "INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES ($1, $2, $3, $4)",
        str(ctx.guild.id), str(message_id), emoji, str(role.id)
    )
    await ctx.send(f"✅ Reaction role set! React with {emoji} on that message to get **{role.name}**.")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    record = await bot.db.fetchrow(
        "SELECT role_id FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
        str(payload.guild_id), str(payload.message_id), str(payload.emoji)
    )
    if not record:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    role = guild.get_role(int(record['role_id']))
    if member and role:
        await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload):
    record = await bot.db.fetchrow(
        "SELECT role_id FROM reaction_roles WHERE guild_id = $1 AND message_id = $2 AND emoji = $3",
        str(payload.guild_id), str(payload.message_id), str(payload.emoji)
    )
    if not record:
        return

    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)
    role = guild.get_role(int(record['role_id']))
    if member and role:
        await member.remove_roles(role)

# HELP COMMAND
@bot.command()
async def cmd(ctx):
    embed = discord.Embed(
        title="✨ Lumi — Command List",
        description="Here's everything Lumi can do!",
        color=0x9b59b6
    )

    embed.add_field(
        name="📢 General",
        value=(
            "`!new`\n"
            "→ Posts the membership announcement"
        ),
        inline=False
    )

    embed.add_field(
        name="🛡️ Moderation",
        value=(
            "`!purge <number>`\n"
            "→ Deletes messages in the current channel\n\n"
            "`!ban @member [reason]`\n"
            "→ Bans a member from the server\n\n"
            "`!warn @member [reason]`\n"
            "→ Warns a member\n\n"
            "`!warnings @member`\n"
            "→ Shows all warnings for a member"
        ),
        inline=False
    )

    embed.add_field(
        name="🎨 Custom Roles",
        value=(
            "`!addrole @member Name #color1 #color2 [image]`\n"
            "→ Creates a gradient role with a custom icon\n\n"
            "`!deleterole @member @Role`\n"
            "→ Removes a role from a member\n\n"
            "`!role @member @Role`\n"
            "→ Assigns an existing role to a member\n\n"
            "`!roleform`\n"
            "→ Posts the custom role request form"
        ),
        inline=False
    )

    embed.add_field(
        name="💤 AFK",
        value=(
            "`!afk [reason]`\n"
            "→ Sets your AFK status\n\n"
            "`!back`\n"
            "→ Removes your AFK status"
        ),
        inline=False
    )

    embed.add_field(
        name="⭐ Reaction Roles",
        value=(
            "`!reactionrole <message_id> <emoji> @Role`\n"
            "→ Sets up a reaction role on a message"
        ),
        inline=False
    )

    embed.set_footer(text="[ ] = optional  •  < > = required  •  Mod-only commands require manage roles/ban permission")
    await ctx.send(embed=embed)

bot.run(TOKEN)
import asyncio

async def main():
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="Bot is healthy!"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8000)))
    await site.start()
    print(f"Web server started on port {os.environ.get('PORT', 8000)}")
    async with bot:
        await bot.start(TOKEN)
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
