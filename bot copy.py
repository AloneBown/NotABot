import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Set up Discord bot
intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("Nothing to see here", scope)
client = gspread.authorize(creds)
sheet = client.open("Or here").sheet1

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')

# Command to fetch user Discord ID, nickname, and role, and send it to Google Sheets
@bot.slash_command(name="rollin", description="Roll you in to team list")
async def rollin(ctx, minecraft_nickname: str):
    # Check if the user has administrator rights
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("You do not have the right to use the command.")
        return

    user_id = str(ctx.author.id)
    user_name = str(ctx.author.name)
    allowed_role_ids = {1280939518249140335, 1280939560095715328, 1280939592761086023}
    user_roles = {role.id for role in ctx.author.roles}
    
    # Check if the user has any of the allowed roles
    if not allowed_role_ids.intersection(user_roles):
        await ctx.respond("You do not have the right to use the command.")
        return
    
    # Check if the user is already entered into the table
    cell = sheet.find(user_id)
    if cell:
        await ctx.respond("You are already enlisted.")
        return
    
    roles = [role.name for role in ctx.author.roles if role.id in allowed_role_ids]
    current_role = ", ".join(roles) if roles else "No roles"
    
    # Append the user ID, name, Minecraft nickname, and role to the Google Sheet
    sheet.append_row([user_id, user_name, minecraft_nickname, current_role], table_range="B2")
    
    # Create an embed message
    embed = discord.Embed(
        title="Entry Successful",
        description="You have successfully entered",
        color=discord.Color.blue()
    )
    
    await ctx.respond(embed=embed)

# Command to fetch user role and update from allowed roles
@bot.slash_command(name="stats", description="Check your stats and info")
async def stats(ctx):
    # Check if the user has administrator rights
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("You do not have the right to use the command.")
        return

    user_id = str(ctx.author.id)
    allowed_role_ids = {1280939518249140335, 1280939560095715328, 1280939592761086023}
    user_roles = {role.id for role in ctx.author.roles}
    
    # Check if the user has any of the allowed roles
    if not allowed_role_ids.intersection(user_roles):
        await ctx.respond("You do not have the right to use the command.")
        return
    
    # Fetch the user's current role from the Google Sheet
    cell = sheet.find(user_id)
    if cell:
        row = cell.row
        current_role_in_sheet = sheet.cell(row, 5).value
        
         # Fetch the Minecraft nickname from the Google Sheet (assuming it's in column 3)
        minecraft_nickname = sheet.cell(row, 4).value
            
        # Create an embed message
        embed = discord.Embed(
            title="Information about the player",
            color=discord.Color.yellow()
        )
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
        embed.add_field(name="Discord Name", value=ctx.author.name, inline=False)
        embed.add_field(name="Minecraft Nickname", value=minecraft_nickname, inline=False)
        embed.add_field(name="Role", value=current_role_in_sheet, inline=False)
            
        await ctx.respond(embed=embed)
    else:
        await ctx.respond("User not found in the sheet.")

# Run bot
bot.run('you realy expect me to put my token here?')