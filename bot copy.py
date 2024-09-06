import discord
import gspread
import pytz
import asyncio
import uuid
from discord.ext import commands, tasks
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime


# Set up Discord bot
intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("Nothing to see here", scope)
client = gspread.authorize(creds)
sheet = client.open("And here").sheet1
tickets = client.open("And here x2").get_worksheet(1)

class TicketView(discord.ui.View):
    def __init__(self, ctx, ticket_id, collected_messages):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.ticket_id = ticket_id
        self.collected_messages = collected_messages
        self.accepted = False
        self.rejected = False

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.rejected:
            await interaction.response.send_message("This ticket has already been rejected.", ephemeral=True)
            return

        self.accepted = True
        await self.ctx.author.send(f"Your ticket with ID {self.ticket_id} has been accepted. Please provide more information if you want.")
        self.record_ticket("Accepted", interaction.user.name)
        self.stop()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.accepted:
            await interaction.response.send_message("This ticket has already been accepted.", ephemeral=True)
            return

        self.rejected = True
        await interaction.response.send_message("Your ticket is rejected.", ephemeral=True)
        await self.ctx.author.send(f"Your ticket with ID {self.ticket_id} has been rejected.")
        self.record_ticket("Rejected", interaction.user.name)
        self.stop()

    def record_ticket(self, status, actioned_by):
        kyiv_tz = pytz.timezone('Europe/Kiev')
        current_time = datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S")
        ticket_info = [
            self.ticket_id,
            self.ctx.author.name,
            current_time,
            "\n".join(self.collected_messages),
            status,
            actioned_by
        ]
        tickets.append_row(ticket_info)

class TicketAdminView(discord.ui.View):
    def __init__(self, tickets, page=0):
        super().__init__(timeout=None)
        self.tickets = tickets
        self.page = page
        self.create_buttons()

    def create_buttons(self):
        start = self.page * 10
        end = start + 10
        for ticket in self.tickets[start:end]:
            button = discord.ui.Button(label=f"Ticket {ticket['id']}", style=discord.ButtonStyle.primary)
            button.callback = self.create_callback(ticket['id'])
            self.add_item(button)
        
        if self.page > 0:
            prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary)
            prev_button.callback = self.prev_page
            self.add_item(prev_button)
        
        if end < len(self.tickets):
            next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)

    def create_callback(self, ticket_id):
        async def callback(interaction):
            await interaction.response.send_message(f"/aticket {ticket_id}", ephemeral=True)
        return callback

    async def prev_page(self, interaction):
        self.page -= 1
        await self.update_view(interaction)

    async def next_page(self, interaction):
        self.page += 1
        await self.update_view(interaction)

    async def update_view(self, interaction):
        self.clear_items()
        self.create_buttons()
        await interaction.response.edit_message(view=self)

def fetch_tickets():
    tickets = []
    records = tickets.get_all_records()
    for record in records:
        tickets.append({
            "id": record["ID"],
            "author": record["Author"],
            "created_at": datetime.strptime(record["Created At"], "%Y-%m-%d %H:%M:%S")
        })
    return tickets

@bot.slash_command(name="adminpanel", description="Show the ticket admin panel")
async def admin_panel(ctx):
    tickets = fetch_tickets()
    embed = discord.Embed(title="Ticket Admin Panel", color=discord.Color.blue())
    for ticket in tickets[:10]:  # Display only the first 10 tickets
        embed.add_field(name=f"Ticket ID: {ticket['id']}", value=f"Author: {ticket['author']}\nCreated At: {ticket['created_at']}", inline=False)
    
    view = TicketAdminView(tickets[:10])
    await ctx.respond(embed=embed, view=view)

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

# Command to open a ticket via Discord DM
@bot.slash_command(name="ticket", description="Open a ticket")
async def ticket(ctx):
    if not isinstance(ctx.channel, discord.DMChannel):
        await ctx.respond("Please open a ticket via DM.")
        return
    
    await ctx.respond("Please describe your issue.")

    def check(m):
        return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

    collected_messages = []
    ticket_id = str(uuid.uuid4()) # Generate a random ticket ID

    try:
        while True:
            message = await bot.wait_for("message", check=check, timeout=30)
            collected_messages.append(message.content)
    except asyncio.TimeoutError:
        if not collected_messages:
            await ctx.respond("No messages received. Ticket closed.")
            return
    
        # Send collected messages to the specific channel in embed format
        channel_id = 1120064397054853266  
        channel = bot.get_channel(channel_id)
        if channel is None:
            await ctx.respond("Failed to find the specified channel.")
            return

        message_content = "\n".join(collected_messages)
    
        embed = discord.Embed(title=f"Ticket ID: {ticket_id}", description=message_content, color=discord.Color.blue())
        embed.set_author(name=f"{ctx.author.name} ({ctx.author.id})")
    
        view = TicketView(ctx, ticket_id, collected_messages)
        await channel.send(embed=embed, view=view)
        await ctx.send("Your ticket has been submitted.")

# Run bot
bot.run('you realy expect me to put my token here?')