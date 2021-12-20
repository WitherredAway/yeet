import discord
from discord.ext import commands, tasks
from main import *
import re
import itertools
import emojis
import asyncio
from typing import Optional
import copy

row_alpha = [
    "🇦",
    "🇧",
    "🇨",
    "🇩",
    "🇪",
    "🇫",
    "🇬",
    "🇭",
    "🇮",
    "🇯",
    "🇰",
    "🇱",
    "🇲",
    "🇳",
    "🇴",
    "🇵",
    "🇶"
]

col_alpha = [
    "0️⃣",
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣",
    "5️⃣",
    "6️⃣",
    "7️⃣",
    "8️⃣",
    "9️⃣",
    "🔟",
    "<:11:920679053688725596>",
    "<:12:920679079756300339>",
    "<:13:920679103332495430>",
    "<:14:920679132260618260>",
    "<:15:920679200854253578>",
    "<:16:920679238414266408>"
]

class DrawButtons(discord.ui.View):
    def __init__(self, ctx, board, row_list, col_list):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.response = None
        self.initial_board = board
        self.board = copy.deepcopy(self.initial_board)
        self.row_list = row_list
        self.col_list = col_list
        self.cursor_row = int(len(row_list)/2)
        self.cursor_col = int(len(col_list)/2)
        self.cursor = self.board[self.cursor_row][self.cursor_col]
        self.cursor_row_max = row_list.index(row_list[-1])
        self.cursor_col_max = col_list.index(col_list[-1])
        self.auto = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(f"This instance does not belong to you, use the `{self.ctx.command}` command to create your own instance.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        self.add_item(discord.ui.Button(label=f"This interaction has timed out. Use {self.ctx.prefix}{self.ctx.command} for a new one.", style=discord.ButtonStyle.gray, disabled=True))
        self.board[self.cursor_row][self.cursor_col] = self.find_key(self.board[self.cursor_row][self.cursor_col])
        embed = make_embed(self.ctx, self.board, "❌", self.row_list, self.col_list)
        await self.response.edit(embed=embed, view=self)

        
    def cursor_conv(self, row_key):
        conv = {
            "A": 0,
            "B": 1,
            "C": 2,
            "D": 3,
            "E": 4,
            "F": 5,
            "G": 6,
            "H": 7,
            "I": 8,
            "J": 9,
            "K": 10,
            "L": 11,
            "M": 12,
            "N": 13,
            "O": 14,
            "P": 15,
            "Q": 16

        }
        row = conv[row_key]-self.cursor_row
        return row
    cur_cle = {
            "🟥": "🔴",
            "🟧": "🟠",
            "🟨": "🟡",
            "🟩": "🟢",
            "🟦": "🔵",
            "🟪": "🟣",
            "🟫": "🟤",
            "⬛": "⚫",
            "⬜": "⚪"
    }

    def find_key(self, value):
        for key, val in self.cur_cle.items():
            if val == value:
                return key
        return value
             
    async def move_cursor(self, interaction: discord.Interaction, row_move: int=0, col_move: int=0):
        self.board[self.cursor_row][self.cursor_col] = self.find_key(self.board[self.cursor_row][self.cursor_col])
        self.cursor_row += row_move
        self.cursor_col += col_move
        if self.auto == True:
            await self.edit_draw(interaction, self.cursor)
        try:
            self.board[self.cursor_row][self.cursor_col] = self.cur_cle[self.board[self.cursor_row][self.cursor_col]]
        except KeyError:
            self.board[self.cursor_row][self.cursor_col] = self.board[self.cursor_row][self.cursor_col]
        embed = make_embed(self.ctx, self.board, self.cursor, self.row_list, self.col_list)
        await interaction.edit_original_message(embed=embed)
            
    async def edit_draw(self, interaction, draw=None, corner=None):
        if self.board[self.cursor_row][self.cursor_col] == draw:
            return
        if draw is None:
            draw = self.board[self.cursor_row][self.cursor_col]
        if corner is None:
            corner = self.cursor
        self.board[self.cursor_row][self.cursor_col] = draw
        embed = make_embed(self.ctx, self.board, corner, self.row_list, self.col_list)
        await interaction.edit_original_message(embed=embed)

    @discord.ui.select(placeholder="Select colour",
                       min_values=1,
                       max_values=1,
                       options=[
                           discord.SelectOption(
                               label="Red",
                               emoji="🟥",
                               value="🔴"
                           ),
                           discord.SelectOption(
                               label="Red",
                               emoji="🟧",
                               value="🟠"
                           ),
                           discord.SelectOption(
                               label="Red",
                               emoji="🟨",
                               value="🟡"
                           ),
                           discord.SelectOption(
                               label="Red",
                               emoji="🟩",
                               value="🟢"
                           ),
                           discord.SelectOption(
                               label="Red",
                               emoji="🟦",
                               value="🔵"
                           ),
                           discord.SelectOption(
                               label="Red",
                               emoji="🟪",
                               value="🟣"
                           ),
                           discord.SelectOption(
                               label="Red",
                               emoji="🟫",
                               value="🟤"
                           ),
                           discord.SelectOption(
                               label="Red",
                               emoji="⬛",
                               value="⚫"
                           )
                       ]
                      )
    async def colour_picker(self, select, interaction):
        await interaction.response.defer()
        self.cursor = select.values[0]
    
    @discord.ui.button(emoji="<:stop:921864670145552444>", style=discord.ButtonStyle.danger)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.board[self.cursor_row][self.cursor_col] = self.find_key(self.board[self.cursor_row][self.cursor_col])
        embed = make_embed(self.ctx, self.board, "❌", self.row_list, self.col_list)
        await interaction.edit_original_message(embed=embed, view=None)
        self.stop()

    @discord.ui.button(emoji="<:clear:921385293989445683>", style=discord.ButtonStyle.danger)
    async def clear(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.auto = False
        self.auto_colour.style = discord.ButtonStyle.gray
        self.cursor_row = int(len(self.row_list)/2)
        self.cursor_col = int(len(self.col_list)/2)
        self.board = copy.deepcopy(self.initial_board)
        embed = make_embed(self.ctx, self.board, self.cursor, self.row_list, self.col_list)
        await interaction.edit_original_message(embed=embed, view=self)
    
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.gray)
    async def placeholder1(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.gray)
    async def placeholder2(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
    """
    @discord.ui.button(emoji="⬜", style=discord.ButtonStyle.gray)
    async def white(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "⚪"
        await self.edit_draw(interaction)
        
    @discord.ui.button(emoji="🟥", style=discord.ButtonStyle.gray)
    async def red(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "🔴"
        await self.edit_draw(interaction)
    """
    @discord.ui.button(emoji="<:up_left:920896021700161547>", style=discord.ButtonStyle.blurple)
    async def up_right(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = -1
        col_move = -1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)
        
    @discord.ui.button(emoji="<:up:920895538696704053>", style=discord.ButtonStyle.blurple)
    async def up(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = -1
        col_move = 0
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(emoji="<:up_right:920895852128657480>", style=discord.ButtonStyle.blurple)
    async def up_left(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = -1
        col_move = 1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)
    
    @discord.ui.button(emoji="⬛", style=discord.ButtonStyle.gray)
    async def black(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "⚫"
        await self.edit_draw(interaction)
        
    @discord.ui.button(emoji="🟧", style=discord.ButtonStyle.gray)
    async def orange(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "🟠"
        await self.edit_draw(interaction)
        
    @discord.ui.button(emoji="<:left:920895993145327628>", style=discord.ButtonStyle.blurple)
    async def left(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = 0
        col_move = -1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(emoji="<:auto_cursor:921352341427470347>", style=discord.ButtonStyle.gray)
    async def auto_colour(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.auto == False:
            self.auto = True
            self.auto_colour.style = discord.ButtonStyle.green
        elif self.auto == True:
            self.auto = False
            self.auto_colour.style = discord.ButtonStyle.grey
        await interaction.edit_original_message(view=self)

    @discord.ui.button(emoji="<:right:920895888229036102>", style=discord.ButtonStyle.blurple)
    async def right(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = 0
        col_move = 1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)
    
    @discord.ui.button(emoji="🟫", style=discord.ButtonStyle.gray)
    async def brown(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "🟤"
        await self.edit_draw(interaction)
        
    @discord.ui.button(emoji="🟨", style=discord.ButtonStyle.gray)
    async def yellow(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "🟡"
        await self.edit_draw(interaction)
        
    @discord.ui.button(emoji="<:down_left:920895965987242025>", style=discord.ButtonStyle.blurple)
    async def down_left(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = 1
        col_move = -1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)
        
    @discord.ui.button(emoji="<:middle:920897054060998676>", style=discord.ButtonStyle.green)
    async def dot(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.edit_draw(interaction, self.cursor)
        
    @discord.ui.button(emoji="<:down:920895939030429696>", style=discord.ButtonStyle.blurple)
    async def down(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = 1
        col_move = 0
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(emoji="<:down_right:920895913608765551>", style=discord.ButtonStyle.blurple)
    async def down_right(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        row_move = 1
        col_move = 1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)
    """
    @discord.ui.button(emoji="🟪", style=discord.ButtonStyle.gray)
    async def purple(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "🟣"
        await self.edit_draw(interaction)
        
    @discord.ui.button(emoji="🟩", style=discord.ButtonStyle.gray)
    async def green(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "🟢"
        await self.edit_draw(interaction)
        
    @discord.ui.button(emoji="🟦", style=discord.ButtonStyle.gray)
    async def blue(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        self.cursor = "🔵"
        await self.edit_draw(interaction)
    """
    @discord.ui.button(emoji="<:emojismiley:920902406336815104>", style=discord.ButtonStyle.gray)
    async def emoji(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        res = await interaction.channel.send(content="Please send a single emoji you want to draw on your drawing board. e.g. 😎")
        def first_emoji(self, sentence):
            return [word for word in sentence.split() if str(word.encode('unicode-escape'))[2] == '\\' ]

        def check(m):
            return m.author == interaction.user and len(m.content.split(" ")) == 1
        try:
            msg = await self.ctx.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await interaction.channel.send(content="Timed out.")
        try:
            emoji = await commands.PartialEmojiConverter.convert(self, self.ctx, msg.content)
        except commands.PartialEmojiConversionFailure:
            if emojis.count(msg.content) > 0:
                emoji = list(emojis.get(msg.content))[0]
            else:
                return await interaction.channel.send(content="Invalid emoji")
        self.cursor = str(emoji)
        await self.edit_draw(interaction)
        await res.delete()
        await asyncio.sleep(0.5)
        await msg.delete()
        
    @discord.ui.button(emoji="<:ABCD:920896121285537832>", style=discord.ButtonStyle.blurple)
    async def set_cursor(self, button: discord.Button, interaction: discord.Interaction):
        await interaction.response.defer()
        res = await self.ctx.send('Please type the cell you want to move the cursor to. e.g. "A1", "a8", "A10", etc.')
        def check(m):
            return m.author == interaction.user
        try:
            msg = await self.ctx.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await self.ctx.send("Timed out.")
        cell = msg.content.upper()
        if len(cell) != 2 and len(cell) != 3:
            return await self.ctx.send("Min and max length of cell must be 2 and 3")
        ABC = "ABCDEFGHIJKLMNOPQ"
        NUM = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16"]
        row_key = cell[0]
        col_key = cell[1:]
        if row_key not in ABC[:self.cursor_row_max+1] or col_key not in NUM[:self.cursor_col_max+1]:
            return await self.ctx.send(f"Invalid cell provided.")
        row_move = self.cursor_conv(row_key)
        col_move = int(col_key)-self.cursor_col
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)
        await res.delete()
        await asyncio.sleep(0.5)
        await msg.delete()

def make_embed(ctx, board, corner, row, col):
    embed = discord.Embed(title=f"{ctx.author}'s drawing board.")
    val = ""
    for idx, i in enumerate(board):
        val += f"\n{row[idx]}  {''.join(i)}\u200b"
    embed.add_field(name=f"{corner}  {''.join(col)}\u200b", value=val, inline=False)
    embed.set_footer(text=f"Tip: You can customize the size of the board! {ctx.prefix}help {ctx.command} for more info.")
    return embed


class Draw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    @commands.bot_has_permissions(external_emojis=True)
    @commands.command(name="draw",
                      aliases=["drawing", "paint", "painting"],
                      case_insensitive=True,
                      help="p",
                      description="p"
                     )
    async def draw(self, ctx, height: Optional[int]=9, width: Optional[int]=9, background: str="⬜"):
        bg = background
        bg_list = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪", "🟫", "⬛", "⬜", "🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "🟤", "⚫", "⚪", "🔳"]
        if bg not in bg_list:
            return await ctx.send(f"Please include a proper background. Available backgrounds:\n{', '.join(bg_list)}")
        if height > 17 or width > 17:
            return await ctx.send("Max height and width is 17!")  
        board = [
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            [bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg, bg],
            
        ]
        
        tboard = board[:height]
        for idx, r in enumerate(tboard):
            tboard[idx] = tboard[idx][:width]
        row_list = row_alpha[:height]
        col_list = col_alpha[:width]

        try:
            tboard[int(len(row_list)/2)][int(len(col_list)/2)] = DrawButtons.cur_cle[tboard[int(len(row_list)/2)][int(len(col_list)/2)]]
        except KeyError:
            tboard = tboard
            
        view = DrawButtons(ctx, tboard, row_list, col_list)
        
        response = await ctx.send(embed=make_embed(ctx, tboard, "*️⃣", row_list, col_list), view=view)
        view.response = response
        await view.wait()

def setup(bot):
    bot.add_cog(Draw(bot))