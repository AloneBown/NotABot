# Copyrighting (C) 2024 by AloneBown
#
# <-This code is free software; 
# you can redistribute it and/or modify it under the terms of the license
# This code is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; 
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.->
#  
# See GNU General Public License v3.0 for more information.
# You should receive a copy of it with code or visit https://www.gnu.org/licenses/gpl-3.0.html
# (do not remove this notice)

import discord, gspread, pytz, asyncio, uuid, yaml, json, os
from discord.ext import commands, tasks
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Set up Discord bot
intents = discord.Intents.default(); intents.members = True; bot = discord.Bot(intents=intents)

# Load config file and variables from it
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)
TOKEN = config["token"]; KEY= config["key"]; KEY_T= config["key_t"]; SHEET= config["sheet"]

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_T, scope)
client = gspread.authorize(creds); sheet = client.open(SHEET).sheet1; tickets_sheet = client.open(SHEET).get_worksheet(1)

# Function to append a new message to the corresponding ticket JSON file
def append_message_to_json(ticket_id, author_name, message_content):
    file_path = f"tickets/{ticket_id}/{ticket_id}.json"
    

    with open(file_path, 'r') as json_file:
        ticket_data = json.load(json_file)
    
    ticket_data['messages'].append({"author": author_name, "content": message_content})

    with open(file_path, 'w') as json_file:
        json.dump(ticket_data, json_file, indent=4)

# Ticket view when a ticket is first opened
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
        self.save_ticket_to_json("Accepted", interaction.user.name)
        
        await self.collect_more_messages(interaction)
    
    async def collect_more_messages(self, interaction):
        def check(m):
            return m.author == self.ctx.author and isinstance(m.channel, discord.DMChannel)

        try:
            while True:
                new_message = await bot.wait_for("message", check=check, timeout=300)
                attachments = []
                    if new_message.attachments:
                    for attachment in new_message.attachments:
                        if attachment.content_type.startswith('image/'):
                            file_path = f"tickets/{self.ticket_id}"
                            await attachment.save(f"{file_path}/{attachment.filename}")
                        attachments.append(attachment.url)
                append_message_to_json(self.ticket_id, new_message.author.name, new_message.content, attachments)
        except asyncio.TimeoutError:
            await self.ctx.author.send("No more messages received. You will be informed about the result of investigation.")
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

    # Record ticket in Google Sheets
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
        tickets_sheet.append_row(ticket_info)
    
    # Save ticket as JSON file
    def save_ticket_to_json(self, status, actioned_by):
        ticket_data = {
            "ticket_id": self.ticket_id,
            "author": self.ctx.author.name,
            "user_id": self.ctx.author.id,
            "created_at": datetime.now(pytz.timezone('Europe/Kiev')).strftime("%Y-%m-%d %H:%M:%S"),
            "messages": self.collected_messages,
            "status": status,
            "actioned_by": actioned_by
        }

        core_file_path = f"tickets/{ticket_id}"
        file_path = f"tickets/{self.ticket_id}.json"

        if not os.path.exists(core_file_path):
            os.makedirs(core_file_path)
        with open(file_path, 'w') as json_file:
            json.dump(ticket_data, json_file, indent=4)
        

# Another view for adminpanel, but this time it's a buttons to open tickets
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
    expected_headers = ["1", "2", "3", "4", "5", "6"]
    records = tickets_sheet.get_all_records(expected_headers=expected_headers)
    for record in records:
        tickets.append({
            "id": record["1"],
            "author": record["2"],
            "created_at": datetime.strptime(record["3"], "%Y-%m-%d %H:%M:%S"),
            "status": record["5"]
        })
    return tickets

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as {bot.user}')

# Command to fetch user Discord ID, nickname, and role, and send it to Google Sheets
@bot.slash_command(name="rollin", description="Roll you in to team list")
async def rollin(ctx, minecraft_nickname: str):
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("You do not have the right to use the command.")
        return

    user_id = str(ctx.author.id)
    user_name = str(ctx.author.name)
    allowed_role_ids = {1280939518249140335, 1280939560095715328, 1280939592761086023}
    user_roles = {role.id for role in ctx.author.roles}
    
    if not allowed_role_ids.intersection(user_roles):
        await ctx.respond("You do not have the right to use the command.")
        return
    
    cell = sheet.find(user_id)
    if cell:
        await ctx.respond("You are already enlisted.")
        return
    
    roles = [role.name for role in ctx.author.roles if role.id in allowed_role_ids]
    current_role = ", ".join(roles) if roles else "No roles"
    
    sheet.append_row([user_id, user_name, minecraft_nickname, current_role], table_range="B2")
    
    embed = discord.Embed(
        title="Entry Successful",
        description="You have successfully entered",
        color=discord.Color.blue()
    )
    
    await ctx.respond(embed=embed)

# Command to fetch user role and update from allowed roles
@bot.slash_command(name="stats", description="Check your stats and info")
async def stats(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("You do not have the right to use the command.")
        return

    user_id = str(ctx.author.id)
    allowed_role_ids = {1280939518249140335, 1280939560095715328, 1280939592761086023}
    user_roles = {role.id for role in ctx.author.roles}
    
    if not allowed_role_ids.intersection(user_roles):
        await ctx.respond("You do not have the right to use the command.")
        return
    
    cell = sheet.find(user_id)
    if cell:
        row = cell.row
        current_role_in_sheet = sheet.cell(row, 5).value
        
        minecraft_nickname = sheet.cell(row, 4).value
    
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
    attachments = []
    ticket_id = str(uuid.uuid4())

    try:
        while True:
            message = await bot.wait_for("message", check=check, timeout=15)
            collected_messages.append(message.content)
                if message.attachments:
                    for attachment in new_message.attachments:
                        if attachment.content_type.startswith('image/'):
                            file_path = f"tickets/{self.ticket_id}"
                            await attachment.save(f"{file_path}/{attachment.filename}")
                        attachments.append(attachment.url)
        # Append each new message to the corresponding ticket JSON file
        append_message_to_json(ticket_id, message.author.name, message.content, attachments)

    except asyncio.TimeoutError:
        if not collected_messages:
            await ctx.respond("No messages received. Ticket closed.")
            return
    
        channel_id = 1120064397054853266  
        channel = bot.get_channel(channel_id)
        if channel is None:
            await ctx.respond("Failed to find the specified channel, contact bot owner.")
            return

        message_content = "\n".join(collected_messages)
    
        embed = discord.Embed(title=f"Ticket ID: {ticket_id}", description=message_content, color=discord.Color.blue())
        embed.set_author(name=f"{ctx.author.name} ({ctx.author.id})")
    
        view = TicketView(ctx, ticket_id, collected_messages)
        await channel.send(embed=embed, view=view)
        await ctx.send("Your ticket has been submitted.")
    
    def append_message_to_json(ticket_id, author_name, message_content):
        file_path = f"tickets/{ticket_id}.json"
    
        with open(file_path, 'r') as json_file:
            ticket_data = json.load(json_file)

        ticket_data['messages'].append({"author": author_name, "content": message_content})

# Command to show the ticket admin panel
@bot.slash_command(name="ticketpanel", description="Show the ticket admin panel")
async def ticketpanel(ctx):
    tickets = fetch_tickets()
    embed = discord.Embed(title="Ticket Admin Panel", color=discord.Color.blue())
    for ticket in tickets[:10]:  # Display only the first 10 tickets
        embed.add_field(name=f"Ticket ID: {ticket['id']}", value=f"Author: {ticket['author']}\nCreated At: {ticket['created_at']}\nStatus: {ticket['status']}", inline=False)
    view = TicketAdminView(tickets[:10])
    await ctx.respond(embed=embed, view=view)

# Run bot
bot.run(TOKEN)