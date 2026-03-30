import discord
from discord.ext import commands
import aiohttp

TOKEN = ("TOKEN")
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# Only moderators can use command
def is_mod():
    async def predicate(ctx):
        return ctx.author.guild_permissions.manage_roles
    return commands.check(predicate)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
@is_mod()
async def addrole(
    ctx,
    member: discord.Member,
    role_name: str,
    color_hex: str,
    icon_url: str
):
    try:
        guild = ctx.guild

        # Convert hex color
        role_color = discord.Color(
            int(color_hex.replace("#", ""), 16)
        )

        # Download icon image
        async with aiohttp.ClientSession() as session:
            async with session.get(icon_url) as resp:
                if resp.status != 200:
                    await ctx.send("❌ Couldn't download image.")
                    return
                icon_bytes = await resp.read()

        # Create role
        new_role = await guild.create_role(
            name=role_name,
            color=role_color,
            display_icon=icon_bytes
        )

        # Give role to tagged user
        await member.add_roles(new_role)

        await ctx.send(
            f"✅ Role **{role_name}** created and given to {member.mention}"
        )

    except discord.Forbidden:
        await ctx.send("❌ Bot lacks permission to manage roles.")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@addrole.error
async def addrole_error(ctx, error):

    if isinstance(error, commands.CheckFailure):
        await ctx.send(
            "❌ Only moderators can use this command."
        )

    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "Usage:\n"
            "!addrole @user RoleName #color image_url"
        )


bot.run(TOKEN)
@bot.command()
async def afk(ctx, *, reason="AFK"):
    member = ctx.author

    # Get original name
    original_name = member.display_name

    # If already AFK, prevent stacking tags
    if original_name.startswith("["):
        await ctx.send("You're already AFK!")
        return

    # Create new nickname
    new_name = f"[{reason}] {original_name}"

    try:
        await member.edit(nick=new_name)
        await ctx.send(f"{member.mention} is now AFK: {reason}")
    except discord.Forbidden:
        await ctx.send("I can't change your nickname. Check my permissions!")
@bot.command()
async def back(ctx):
    member = ctx.author
    name = member.display_name

    # Remove [reason] part
    if name.startswith("["):
        new_name = name.split("] ", 1)[1]

        try:
            await member.edit(nick=new_name)
            await ctx.send(f"Welcome back {member.mention}!")
        except discord.Forbidden:
            await ctx.send("I can't change your nickname.")
    else:
        await ctx.send("You're not AFK.")
@bot.command()
@commands.has_permissions(manage_roles=True)  # Only mods/admins
async def join(ctx):
    channel_id = 1486623717260791859
    channel = ctx.guild.get_channel(channel_id)

    if channel:
        await ctx.send(
            f"If you want to be a member of Luminosity, please read at the {channel.mention} channel!"
        )
    else:
        await ctx.send("Announcement channel not found.")
