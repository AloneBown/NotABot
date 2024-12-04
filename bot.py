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

import discord, gspread, pytz, asyncio, uuid, yaml, json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Set up Discord bot
intents = discord.Intents.default(); intents.members = True; bot = discord.Bot(intents=intents)

# Load config file and variables from it
with open("config.yml", "r") as file:
    config = yaml.safe_load(file)
TOKEN = config["token"]; KEY= config["key"]; KEY_T= config["key_t"]; SHEET= config["sheet"]; GUILD= config["guild"]

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_T, scope)
client = gspread.authorize(creds); sheet = client.open(SHEET).sheet1; tickets_sheet = client.open(SHEET).get_worksheet(1)

# Function to append a new message to the corresponding ticket JSON file
def append_message_to_json(ticket_id, author_name, message_content, attachments):
    file_path = f"tickets/{ticket_id}.json"
    try:
        with open(file_path, 'r') as json_file:
            ticket_data = json.load(json_file)
    except FileNotFoundError:
        ticket_data = {"messages": []}
    except json.JSONDecodeError:
        raise ValueError("Error decoding ticket data.")

    ticket_data['messages'].append({
        "author": author_name,
        "content": message_content,
        "attachments": attachments
    })

    with open(file_path, 'w') as json_file:
        json.dump(ticket_data, json_file, indent=4)

# Ticket view when a ticket is first opened
class TicketView(discord.ui.View):
    def __init__(self, ctx, ticket_id, collected_messages, attachments):
        super().__init__(timeout=None)
        self.ctx = ctx; self.bot = bot; self.ticket_id = ticket_id; self.collected_messages = collected_messages; self.guild_id = GUILD
        self.accepted = False; self.rejected = False; self.attachments = attachments; self.closed = False; self.sellected_moderator = None
        
        # Fetch the guild using the bot and guild_id
        guild = self.bot.get_guild(self.guild_id)
        if guild is not None:
            self.moderators = [member for member in guild.members if any(role.name == 'тест' for role in member.roles)]
            print(f"Found {len(self.moderators)} moderators.")
            if 1 <= len(self.moderators) <= 25:
                options = [discord.SelectOption(label=moderator.name, value=str(moderator.id)) for moderator in self.moderators]
                select = discord.ui.Select(placeholder="Select a moderator", options=options, custom_id="moderator_select")
                select.callback = self.moderator_select_callback
                self.add_item(select)
            else:
                raise ValueError("The number of moderators must be between 1 and 25.")
        else:
            self.moderators = []
            print("Guild not found or bot does not have access to the guild.") 

    async def moderator_select_callback(self, interaction: discord.Interaction):
        selected_moderator_id = int(interaction.data['values'][0])
        guild = self.bot.get_guild(self.guild_id)
        selected_moderator = discord.utils.get(guild.members, id=selected_moderator_id)
        self.sellected_moderator = selected_moderator.name
        self.accepted = True
        self.closed = False
        await self.ctx.author.send(f"Your ticket with ID {self.ticket_id} has been accepted. Moderator, that will rewiew your ticket - {self.sellected_moderator}. Please provide more information if you want.")
        await interaction.response.send_message("Ticket is accepted.", ephemeral=True)
        self.record_ticket("Accepted", interaction.user.name, "Open", self.sellected_moderator)
        self.save_ticket_to_json("Accepted", interaction.user.name, "Open", self.sellected_moderator)

        await self.collect_more_messages(interaction)
    
    async def collect_more_messages(self, interaction):
        def check(m):
            return m.author == self.ctx.author and isinstance(m.channel, discord.DMChannel)

        try:
            while True:
                new_message = await bot.wait_for("message", check=check, timeout=15)
                attachments = [attachment.url for attachment in new_message.attachments]
                append_message_to_json(self.ticket_id, new_message.author.name, new_message.content, attachments)
        except asyncio.TimeoutError:
            await self.ctx.author.send("No more messages received. You will be informed about the result of investigation.")
            self.stop()

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.accepted:
            await interaction.response.send_message("This ticket has already been accepted.", ephemeral=True)
            return
        await asyncio.sleep(5)
        await interaction.delete(1)

        self.rejected = True
        self.closed = True
        await interaction.response.send_message("Your ticket is rejected.", ephemeral=True)
        await self.ctx.author.send(f"Your ticket with ID {self.ticket_id} has been rejected.")
        self.record_ticket("Rejected", interaction.user.name, "Closed", "None")
        self.stop()

    # Record ticket in Google Sheets
    def record_ticket(self, status, actioned_by, closed, selected_moderator):
        kyiv_tz = pytz.timezone('Europe/Kiev')
        current_time = datetime.now(kyiv_tz).strftime("%Y-%m-%d %H:%M:%S")
        ticket_info = [
            self.ticket_id,
            self.ctx.author.name,
            current_time,
            "\n".join(self.collected_messages),
            status,
            actioned_by,     
            closed,
            selected_moderator
        ]
        tickets_sheet.append_row(ticket_info)
    
    # Save ticket as JSON file
    def save_ticket_to_json(self, status, actioned_by, closed, selected_moderator):
        file_path = f"tickets/{self.ticket_id}.json"

        ticket_data = {
            "ticket_id": self.ticket_id,
            "author": self.ctx.author.name,
            "user_id": self.ctx.author.id,
            "created_at": datetime.now(pytz.timezone('Europe/Kiev')).strftime("%Y-%m-%d %H:%M:%S"),
            "messages": self.collected_messages,
            "status": status,
            "actioned_by": actioned_by,
            "moderator": selected_moderator,
            "closed": closed
        }
        for message, attachment in zip(self.collected_messages, self.attachments):
            ticket_data['messages'].append({
                "author": self.ctx.author.name,
                "content": message,
                "attachments": attachment
            })

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
            await aticket(interaction, ticket_id=ticket_id)
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
    expected_headers = ["1", "2", "3", "4", "5", "6", "7", "8"]
    records = tickets_sheet.get_all_records(expected_headers=expected_headers)
    for record in records:
        tickets.append({
            "id": record["1"],
            "author": record["2"],
            "created_at": datetime.strptime(record["3"], "%Y-%m-%d %H:%M:%S"),
            "status": record["5"],
            "closed": record["7"]
        })
    return tickets

# View for admin to see ticket messages and close the ticket
class AticketView(discord.ui.View):
    def __init__(self, ticket_id, ticket_author):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id; self.closed = False; self.ctx.author = ticket_author
        self.bot = bot

    @discord.ui.button(label="Record an conversation", style=discord.ButtonStyle.success)
    async def answer_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message(f"Please provide answer to latest message below", ephemeral=True)
        await self.collect_more_messages_a(interaction)
    
    async def collect_more_messages_a(self, interaction):
        message = None
        attachments = []
        try:
            def check(message):
                return message.channel == interaction.channel and message.author == interaction.user
        
            message = await self.bot.wait_for("message", timeout=15, check=check)
            attachments = [attachment.url for attachment in message.attachments]
            append_message_to_json(self.ticket_id, message.author.name, message.content, attachments)
            await interaction.channel.send("Message and attachments collected successfully.")
        except asyncio.TimeoutError:
            await interaction.channel.send("No response received. Timeout.")
            self.stop()

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.send_message("This ticket is closed.", ephemeral=True)
        self.closed = True
        self.record_ticket_closing("Closed")

        ticket_author = self.ctx.author
        try:
            await ticket_author.send(f"Your ticket with ID {self.ticket_id} has been closed.")
        except discord.Forbidden:
            print(f"Could not send DM to {ticket_author.name}. They might have DMs disabled.")

        await asyncio.sleep(5)
        await interaction.delete_original_message()
        self.stop() 

    def record_ticket_closing(self, closed):
        cell = tickets_sheet.find(self.ticket_id)
        status_cell = tickets_sheet.cell(cell.row, cell.col + 6)
        tickets_sheet.update_cell(status_cell.row, status_cell.col, status)
        status = closed

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
            attachments = [attachment.url for attachment in message.attachments]
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
    
        view = TicketView(ctx, ticket_id, collected_messages, attachments)
        await channel.send(embed=embed, view=view)
        await ctx.send("Your ticket has been submitted.")

# Command to show the ticket admin panel
@bot.slash_command(name="ticketpanel", description="Show the ticket admin panel")
async def ticketpanel(ctx):
    tickets = fetch_tickets()
    embed = discord.Embed(title="Ticket Admin Panel", color=discord.Color.blue())
    for ticket in tickets[:10]:# Display only the first 10 tickets
        if ticket['closed'] == "Closed":
            continue
        embed.add_field(name=f"Ticket ID: {ticket['id']}", value=f"Author: {ticket['author']}\nCreated At: {ticket['created_at']}\nStatus: {ticket['status']}\nOpen/Closed: {ticket['closed']}", inline=False)
    view = TicketAdminView(tickets[:10])
    await ctx.respond(embed=embed, view=view)

@bot.slash_command(name="aticket", description="Admin ticket view")
async def aticket(ctx_or_interaction, ticket_id: str):
    if isinstance(ctx_or_interaction, discord.Interaction):
        user = ctx_or_interaction.user
        response_method = ctx_or_interaction.response.send_message
    else:
        user = ctx_or_interaction.author
        response_method = ctx_or_interaction.send

    if not user.guild_permissions.administrator:
        await response_method("You do not have the right to use the command.")
        return

    ticket_file_path = f"tickets/{ticket_id}.json"
    try:
        with open(ticket_file_path, 'r') as json_file:
            ticket_data = json.load(json_file)
    except FileNotFoundError:
        await response_method("Ticket is not found.")
        return
    except json.JSONDecodeError:
        await response_method("Error decoding ticket data.")
        return
    
    top_message = next((msg for msg in ticket_data['messages'] if isinstance(msg, str)), "No messages available")

    ticket_author = ticket_data['author']
    embed_info = discord.Embed(title=f"Ticket ID: {ticket_data['ticket_id']}", color=discord.Color.blue())
    embed_info.add_field(name="Author", value=ticket_data['author'], inline=False)
    embed_info.add_field(name="Created At", value=ticket_data['created_at'], inline=False)
    embed_info.add_field(name="Status", value=ticket_data['status'], inline=False)
    embed_info.add_field(name="Actioned By", value=ticket_data['actioned_by'], inline=False)
    embed_info.add_field(name="Moderator", value=ticket_data['moderator'], inline=False)
    embed_info.add_field(name="Open/Closed", value=ticket_data['closed'], inline=False)
    embed_info.add_field(name="Message", value=top_message, inline=False)
        
    embed_messages = discord.Embed(title="Messages", color=discord.Color.blue())
    messages = ticket_data.get('messages', [])
    if not isinstance(messages, list):
        messages = []
    else:
        messages = [msg for msg in messages if isinstance(msg, dict)]
        
    for message in messages:
        message_content = f"{message.get('author', 'Unknown')}: {message.get('content', 'No content')}, {message.get('attachments', 'No attachments')}"
        embed_messages.add_field(name="Message", value=message_content, inline=False)
        
    view = AticketView(ticket_id, ticket_author)
    await response_method(embeds=[embed_info, embed_messages], view=view)   
# Run bot
bot.run(TOKEN)