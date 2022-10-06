import asyncio
import typing
from typing import Optional, Union, Literal, List, Dict, Tuple, TypeVar
import io
from functools import cached_property
import re
import copy

import emojis
import numpy as np
import discord
from discord.ext import commands, tasks
from .utils.utils import invert_dict
import PIL
from PIL import Image
from pilmoji import Pilmoji

from constants import u200b, NEW_LINE
from .draw_utils.constants import (
    ROW_ICONS_DICT,
    ROW_ICONS,
    COLUMN_ICONS_DICT,
    COLUMN_ICONS,
    CURSOR,
    LETTER_TO_NUMBER,
    ALPHABETS,
    NUMBERS,
)
from .draw_utils.emoji import (
    draw_emoji,
    SentEmoji,
    AddedEmoji,
)


lock = asyncio.Lock()


async def wait_for(ctx: commands.Context, *, check):
    async with lock:
        return await ctx.bot.wait_for("message", timeout=30, check=check)


def make_board(
    bg: str, height: int, width: int
) -> Tuple[np.array, Tuple[str], Tuple[str]]:
    board = np.full((height, width), bg, dtype="object")
    row_labels = ROW_ICONS[:height]
    col_labels = COLUMN_ICONS[:width]

    try:
        board[int(height / 2), int(width / 2)] = CURSOR[
            board[int(height / 2), int(width / 2)]
        ]
    except KeyError:
        pass
    return board, row_labels, col_labels


class Draw(commands.Cog):
    """Category with commands to bring out your inner artist."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    display_emoji = "🖌️"

    @commands.bot_has_permissions(external_emojis=True)
    @commands.group(
        name="draw",
        aliases=("drawing", "paint", "painting"),
        case_insensitive=True,
        brief="Make pixel art on discord!",
        help="wip",
        description="Command which you can use to make pixel art using buttons and dropdown menus.",
        invoke_without_command=True,
    )
    async def draw(
        self,
        ctx: commands.Context,
        height: Optional[int] = 9,
        width: Optional[int] = 9,
        background: Literal["🟥", "🟧", "🟨", "🟩", "🟦", "🟪", "🟫", "⬛", "⬜"] = "⬜",
    ) -> None:
        bg = background
        if height < 5 or height > 17:
            return await ctx.send("Height must be atleast 5 and atmost 17")

        if width < 5 or width > 17:
            return await ctx.send("Width must be atleast 5 and atmost 17")

        board, row_list, col_list = make_board(bg, height, width)
        view = DrawButtons(bg, board, row_list, col_list, ctx=ctx)

        response = await ctx.send(embed=view.embed, view=view)
        view.response = response
        await view.wait()

    @draw.command(
        name="copy",
        brief="Copy a drawing.",
        help="Copy a drawing from an embed by replying to the message or using message link.",
        description="Allows you to copy a drawing that was done with the `draw` command. This will also copy the palette! You can copy by replying to such a message or by providing the message link (or ID).",
    )
    async def copy(
        self,
        ctx: commands.Context,
        message_link: Optional[discord.Message] = None,
    ):
        message = message_link
        if ctx.message.reference:
            message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        elif message_link is None or not isinstance(message_link, discord.Message):
            return await ctx.send_help(ctx.command)

        if all(
            (
                message.embeds,
                "drawing board" in message.embeds[0].title,
                message.author == ctx.bot.user,
            )
        ):
            name = message.embeds[0].fields[0].name
            value = message.embeds[0].fields[0].value
            board = []
            for line in value.split("\n"):
                board.append(line.split("  ")[1].split("\u200b"))
            board = np.array(board, dtype="object")
        else:
            return await ctx.send(
                "Invalid message, make sure it's a draw embed and a message from the bot."
            )

        row_list = ROW_ICONS[: len(board)]
        col_list = COLUMN_ICONS[: len(board[0])]
        try:
            board[int(len(row_list) / 2), int(len(col_list) / 2)] = CURSOR[
                board[int(len(row_list) / 2), int(len(col_list) / 2)]
            ]
        except KeyError:
            pass
        options = discord.ui.View.from_message(message, timeout=0).children[0].options
        for option in options:
            if option.label.endswith(" (base)"):
                bg = str(option.emoji)

        view = DrawButtons(
            bg, board, row_list, col_list, ctx=ctx, selectmenu_options=options
        )
        view.cursor = name.split("  ")[0]
        view.clear_cursors()
        view.draw_cursor()

        response = await ctx.send(embed=view.embed, view=view)
        view.response = response
        await view.wait()


C = TypeVar("C", bound="Colour")


class Colour:
    # RGB_A accepts RGB values and an optional Alpha value
    def __init__(self, RGB_A: Tuple[int], *, bot: commands.Bot):
        self.RGBA = RGB_A if len(RGB_A) == 4 else (*RGB_A, 255)
        self.RGB = self.RGBA[:3]
        self.R, self.G, self.B, self.A = self.RGBA

        self.bot = bot
        self.loop = self.bot.loop

    @cached_property
    def hex(self) -> str:
        return "%02x%02x%02x" % self.RGB

    @cached_property
    def base_emoji(self) -> Image:
        return draw_emoji("🟪")

    async def to_bytes(self) -> io.BytesIO():
        return await self.loop.run_in_executor(None, self._to_bytes)

    def _to_bytes(self) -> io.BytesIO():
        image = self._to_image()
        with io.BytesIO() as image_bytes:
            image.save(image_bytes, "PNG")
            # image_bytes.seek(0)
            return image_bytes.getvalue()

    async def to_file(self) -> discord.File:
        return await self.loop.run_in_executor(None, self._to_file)

    def _to_file(self) -> discord.File:
        image_bytes = io.BytesIO(self._to_bytes())
        return discord.File(image_bytes, filename=f"{self.hex}.png")

    async def to_image(self, base_emoji: Optional[str] = None) -> Image:
        return await self.loop.run_in_executor(None, self._to_image, base_emoji)

    def _to_image(self, base_emoji: Optional[str] = None) -> Image:
        # If you pass in an emoji, it uses that as base
        # Else it uses the base_emoji property which uses 🟪
        base_emoji = draw_emoji(base_emoji) if base_emoji else self.base_emoji
        data = np.array(base_emoji)
        r, g, b, a = data.T

        data[..., :-1][a != 0] = self.RGB

        # Set the alpha relatively, to respect individual alpha values
        alpha_percent = self.A / 255
        data[..., -1] = alpha_percent * data[..., -1]

        image = Image.fromarray(data)

        return image

    async def to_emoji(self, guild: discord.Guild):
        return await guild.create_custom_emoji(
            name=self.hex, image=await self.to_bytes()
        )

    @classmethod
    async def from_emoji(cls, emoji: str, *, bot: commands.Bot) -> C:
        image = await bot.loop.run_in_executor(None, draw_emoji, emoji)
        colors = [
            color
            for color in sorted(
                image.getcolors(image.size[0] * image.size[1]),
                key=lambda c: c[0],
                reverse=True,
            )
            if color[1][-1] > 0
        ]

        return cls(colors[0][1], bot=bot)

    @classmethod
    def mix_colours(cls, colours: List[Tuple[int, C]], *, bot: commands.Bot) -> C:
        colours = [
            colour.RGBA if isinstance(colour, Colour) else colour for colour in colours
        ]
        total_weight = len(colours)

        return cls(
            tuple(round(sum(colour) / total_weight) for colour in zip(*colours)),
            bot=bot,
        )


class DrawSelectMenu(discord.ui.Select):
    def __init__(
        self,
        *,
        options: Optional[List[discord.SelectOption]] = None,
        bg: str,
        ctx: commands.Context,
    ):
        self.ctx = ctx
        self.bot = self.ctx.bot
        options = (
            options
            if options
            else [
                discord.SelectOption(label="Red", emoji="🟥", value="🟥"),
                discord.SelectOption(label="Orange", emoji="🟧", value="🟧"),
                discord.SelectOption(label="Yellow", emoji="🟨", value="🟨"),
                discord.SelectOption(label="Green", emoji="🟩", value="🟩"),
                discord.SelectOption(label="Blue", emoji="🟦", value="🟦"),
                discord.SelectOption(label="Purple", emoji="🟪", value="🟪"),
                discord.SelectOption(label="Brown", emoji="🟫", value="🟫"),
                discord.SelectOption(label="Black", emoji="⬛", value="⬛"),
                discord.SelectOption(label="White", emoji="⬜", value="⬜"),
                discord.SelectOption(
                    label="Add Emoji(s)",
                    emoji="<:emojismiley:920902406336815104>",
                    value="emoji",
                ),
            ]
        )
        for option in options:
            if str(option.emoji) == bg and not option.label.endswith(" (base)"):
                option.label += " (base)"

        super().__init__(
            placeholder="🎨 Palette",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    @property
    def option_values_dict(self) -> Dict[str, discord.SelectOption]:
        return {option.value: option for option in self.options}

    @property
    def option_emojis_dict(self) -> Dict[str, discord.SelectOption]:
        return {
            option.emoji.name
            if option.emoji.is_unicode_emoji()
            else option.emoji.id: option
            for option in self.options
        }

    async def upload_emoji(self, colour: Colour) -> discord.Emoji:
        # Look if emoji already exists
        for guild in self.bot.EMOJI_SERVERS:
            guild_emojis = await guild.fetch_emojis()
            for guild_emoji in guild_emojis:
                if colour.hex == guild_emoji.name:
                    return guild_emoji

        # Emoji does not exist already, proceed to create
        for guild in self.bot.EMOJI_SERVERS:
            try:
                emoji = await colour.to_emoji(guild)
            except discord.HTTPException:
                continue
            else:
                return emoji

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        self.ctx = self.view.ctx
        select = self
        if "emoji" in select.values:
            res = await interaction.followup.send(
                content="Please send a message containing the emojis you want to add to your palette. E.g. `😎 I like turtles 🐢`"
            )

            def check(m):
                return m.author == interaction.user

            try:
                msg = await wait_for(self.ctx, check=check)
                await msg.delete()
            except asyncio.TimeoutError:
                return await res.edit(content="Timed out.")

            content = msg.content
            # Get any unicode emojis from the content
            # and list them as SentEmoji objects
            unicode_emojis = [
                SentEmoji(emoji=emoji, index=content.index(emoji))
                for emoji in emojis.get(content)
            ]
            # Get any flag/regional indicator emojis from the content
            # and list them as SentEmoji objects
            flag_emojis = [
                SentEmoji(
                    emoji=emoji.group(0),
                    index=emoji.start(),
                )
                for emoji in re.finditer("[\U0001F1E6-\U0001F1FF]", content)
            ]
            # Get any custom emojis from the content
            # and list them as SentEmoji objects
            custom_emojis = [
                SentEmoji(emoji=emoji.group(0), index=emoji.start())
                for emoji in re.finditer(r"<a?:[a-zA-Z0-9_]+:\d+>", content)
            ]

            # Gather all the emojis and sort them by index
            sent_emojis = sorted(
                unicode_emojis + flag_emojis + custom_emojis,
                key=lambda emoji: emoji.index,
            )

            added_emojis = {}
            for num, sent_emoji in enumerate(sent_emojis):
                emoji_check = discord.PartialEmoji.from_str(sent_emoji.emoji)
                emoji = copy.copy(emoji_check)

                emoji_identifier = emoji.id if emoji.id else emoji.name
                existing_emojis = [
                    (em.id if em.id else em.name)
                    for em in [opt.emoji for opt in select.options]
                ]
                if emoji_identifier in existing_emojis:
                    added_emoji = AddedEmoji(
                        sent_emoji=sent_emoji, emoji=emoji, status="Already exists."
                    )

                else:
                    added_emoji = AddedEmoji(
                        sent_emoji=sent_emoji,
                        emoji=emoji,
                        status="Added.",
                        name="_" if emoji.is_custom_emoji() else emoji.name,
                    )

                added_emojis[emoji_identifier] = added_emoji

            replaced_emojis = {}
            for added_emoji in added_emojis.values():
                if added_emoji.status != "Added.":
                    continue

                if len(select.options) == 25:
                    replaced_option = select.options.pop(10)
                    replaced_emoji = replaced_option.emoji
                    replaced_emoji.name = replaced_option.label
                    replaced_emojis[
                        replaced_emoji.id if replaced_emoji.id else replaced_emoji.name
                    ] = AddedEmoji.from_option(
                        replaced_option,
                        status=f"Replaced because limit reached (by {added_emoji}).",
                        sent_emoji=SentEmoji(emoji=replaced_emoji),
                    )
                    added_emoji.status = f"Added (replaced {replaced_emoji})."

                option = discord.SelectOption(
                    label=added_emoji.original_name,
                    emoji=added_emoji.emoji,
                    value=str(added_emoji.emoji),
                )
                select.append_option(option)

            added_emojis.update(replaced_emojis)

            if len(select.options[10:]) > 0:
                self.view.cursor = select.options[-1].value

            response = [
                f"%s - {added_emoji.status}" % added_emoji.emoji
                for added_emoji in added_emojis.values()
            ]

            try:
                await interaction.edit_original_message(
                    embed=self.view.embed, view=self.view
                )
            except discord.HTTPException as error:
                await interaction.followup.send(content=error)
                raise error
            await res.edit(content="\n".join(response) or "Aborted")

        elif len(select.values) > 1:
            selected_options = [
                self.option_values_dict.get(value) for value in self.values
            ]

            selected_emojis = [str(option.emoji) for option in selected_options]
            colours = [
                await Colour.from_emoji(emoji, bot=self.bot)
                for emoji in selected_emojis
            ]

            mixed_colour = Colour.mix_colours(colours, bot=self.bot)

            emoji = await self.upload_emoji(mixed_colour)

            option = self.option_emojis_dict.get(emoji.id)
            if option is not None:
                self.view.cursor = option.value
            else:
                option = discord.SelectOption(
                    label=" + ".join(
                        [
                            str(option.emoji)
                            if option.emoji.is_unicode_emoji()
                            else option.emoji.name
                            for option in selected_options
                        ]
                    ),  # mixed_colour.hex,
                    emoji=emoji,
                    value=str(emoji),
                )
                select.append_option(option)
                self.view.cursor = select.options[-1].value

            try:
                await interaction.edit_original_message(
                    embed=self.view.embed, view=self.view
                )
            except discord.HTTPException as error:
                await interaction.followup.send(content=error)
                raise error
            await interaction.followup.send(
                content=f'Mixed colours:\n{" + ".join(selected_emojis)} = {emoji}'
            )

        elif self.view.cursor != select.values[0]:
            self.view.cursor = select.values[0]
            await interaction.edit_original_message(embed=self.view.embed)


class DrawButtons(discord.ui.View):
    def __init__(
        self,
        bg,
        board,
        row_list,
        col_list,
        *,
        ctx: commands.Context,
        selectmenu_options: Optional[List[discord.SelectOption]] = None,
    ):
        super().__init__(timeout=600)
        children = self.children.copy()
        self.clear_items()
        self.add_item(DrawSelectMenu(options=selectmenu_options, bg=bg, ctx=ctx))
        for item in children:
            self.add_item(item)

        self.bg = bg
        self.initial_board = board
        self.board = self.initial_board.copy()
        self.row_list = row_list
        self.col_list = col_list
        self.cursor_row = int(len(row_list) / 2)
        self.cursor_col = int(len(col_list) / 2)
        self.ctx = ctx
        self.response = None
        self.cells = [(self.cursor_row, self.cursor_col)]
        self.cursor = self.bg
        self.cursor_row_max = row_list.index(row_list[-1])
        self.cursor_col_max = col_list.index(col_list[-1])
        self.initial_cell = (None, None)
        self.initial_row = self.initial_cell[0]
        self.initial_col = self.initial_cell[1]
        self.final_cell = (None, None)
        self.final_row = self.final_cell[0]
        self.final_col = self.final_cell[1]
        self.inv_CURSOR = invert_dict(CURSOR)

        self.auto = False
        self.fill = False

    @property
    def embed(self):
        embed = discord.Embed(title=f"{self.ctx.author}'s drawing board.")

        cursor_rows = tuple(cell_tuple[0] for cell_tuple in self.cells)
        cursor_cols = tuple(cell_tuple[1] for cell_tuple in self.cells)
        row_list = [
            (row if idx not in cursor_rows else ROW_ICONS_DICT[row])
            for idx, row in enumerate(self.row_list)
        ]
        col_list = [
            (col if idx not in cursor_cols else COLUMN_ICONS_DICT[col])
            for idx, col in enumerate(self.col_list)
        ]

        # The actual board
        embed.description = f"""{self.cursor}      {u200b.join(col_list)}

{NEW_LINE.join(
    [
        f"{row_list[idx]}      {u200b.join(row)}"
        for idx, row in enumerate(self.board)
    ]
)}"""

        embed.set_footer(
            text=(
                f"The board looks wack? Try decreasing its size! Do {self.ctx.clean_prefix}help draw for more info."
                if all((len(self.row_list) >= 10, len(self.col_list) >= 10))
                else f"You can customize this board! Do {self.ctx.clean_prefix}help draw for more info."
            )
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                f"This instance does not belong to you, use the `{self.ctx.command}` command to create your own instance.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self):
        self.stop_board()
        self.add_item(
            discord.ui.Button(
                label=f"This interaction has timed out. Use {self.ctx.prefix}{self.ctx.command} for a new one.",
                style=discord.ButtonStyle.gray,
                disabled=True,
            )
        )
        await self.response.edit(embed=self.embed, view=self)
        self.stop()

    def stop_board(self):
        selectmenu = self.children[0]
        selectmenu.disabled = True

        self.clear_items()
        self.add_item(selectmenu)
        self.clear_cursors(empty=True)

    def un_cursor(self, value):
        return self.inv_CURSOR.get(value, value)

    def draw_cursor(self, row: Optional[int] = None, col: Optional[int] = None):
        row = row if row is not None else self.cursor_row
        col = col if col is not None else self.cursor_col
        try:
            self.board[row, col] = CURSOR[self.board[row, col]]
        except KeyError:
            pass

    def clear_cursors(self, *, empty: Optional[bool] = False):
        for x, row in enumerate(self.board):
            for y, _ in enumerate(row):
                cell_tuple = (x, y)
                self.board[cell_tuple] = self.un_cursor(self.board[cell_tuple])

        self.cells = [(self.cursor_row, self.cursor_col)] if empty is False else []

    async def edit_draw(self, interaction: discord.Interaction, draw: Optional[str] = None):
        if (
            all(
                self.board[row, col] == draw
                for row, col in self.cells
            )
            and self.auto is False
        ):
            return
        backup_board = copy.deepcopy(self.board)
        if draw is None:
            draw = self.board[self.cursor_row, self.cursor_col]
        for row, col in self.cells:
            self.board[row, col] = CURSOR.get(draw, draw)
        
        try:
            await interaction.edit_original_message(embed=self.embed, view=self)
        except discord.HTTPException:
            self.board = backup_board
            await interaction.edit_original_message(embed=self.embed, view=self)
            await interaction.followup.send(
                content="Max characters reached. Please remove some custom emojis from the board.\nCustom emojis take up more than 20 characters each, while most unicode/default ones take up 1!\nMaximum is 4096 characters due to discord limitations.",
                ephemeral=True
            )

    async def move_cursor(
        self, interaction: discord.Interaction, row_move: int = 0, col_move: int = 0
    ):
        self.clear_cursors()
        self.cursor_row += (
            row_move if self.cursor_row + row_move <= self.cursor_row_max else 0
        )
        self.cursor_col += (
            col_move if self.cursor_col + col_move <= self.cursor_col_max else 0
        )
        if self.fill is not True:
            self.cells = [(self.cursor_row, self.cursor_col)]
        elif self.fill is True:
            self.final_cell = (self.cursor_row, self.cursor_col)
            self.final_row = self.final_cell[0]
            self.final_col = self.final_cell[1]

            self.cells = [
                (row, col)
                for col in range(
                    min(self.initial_col, self.final_col),
                    max(self.initial_col, self.final_col) + 1,
                )
                for row in range(
                    min(self.initial_row, self.final_row),
                    max(self.initial_row, self.final_row) + 1,
                )
            ]

        if self.auto is True:
            await self.edit_draw(interaction, self.cursor)

        for cell_tuple in self.cells:
            self.draw_cursor(*cell_tuple)

        if self.auto is not True:
            await interaction.edit_original_message(embed=self.embed)

    # ------ buttons ------

    @discord.ui.button(
        emoji="<:stop:921864670145552444>", style=discord.ButtonStyle.danger
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop_board()
        await interaction.edit_original_message(embed=self.embed, view=self)
        self.stop()

    @discord.ui.button(
        emoji="<:clear:922414780193579009>", style=discord.ButtonStyle.danger
    )
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.auto = False
        self.auto_colour.style = discord.ButtonStyle.gray
        self.fill = False
        self.fill_bucket.style = discord.ButtonStyle.grey
        self.cursor_row = int(len(self.row_list) / 2)
        self.cursor_col = int(len(self.col_list) / 2)
        self.board, _, _ = make_board(self.bg, len(self.col_list), len(self.row_list))
        self.clear_cursors()
        self.draw_cursor()
        await interaction.edit_original_message(embed=self.embed, view=self)

    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.gray)
    async def placeholder1(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.gray)
    async def placeholder2(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

    @discord.ui.button(
        emoji="<:fill:930832869692149790>", style=discord.ButtonStyle.gray
    )
    async def fill_bucket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        if self.fill == False:
            self.fill = True
            self.initial_cell = (self.cursor_row, self.cursor_col)
            self.initial_row = self.initial_cell[0]
            self.initial_col = self.initial_cell[1]
            self.fill_bucket.style = discord.ButtonStyle.green
        elif self.fill == True:
            self.fill = False
            self.clear_cursors()
            self.draw_cursor()
            self.fill_bucket.style = discord.ButtonStyle.grey
        await self.edit_draw(interaction)

    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.gray)
    async def placeholder3(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

    @discord.ui.button(
        emoji="<:up_left:920896021700161547>", style=discord.ButtonStyle.blurple
    )
    async def up_right(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        row_move = -1
        col_move = -1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(
        emoji="<:up:920895538696704053>", style=discord.ButtonStyle.blurple
    )
    async def up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        row_move = -1
        col_move = 0
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(
        emoji="<:up_right:920895852128657480>", style=discord.ButtonStyle.blurple
    )
    async def up_left(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        row_move = -1
        col_move = 1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.gray)
    async def placeholder5(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

    @discord.ui.button(
        emoji="<:erase:927526530052132894>", style=discord.ButtonStyle.gray
    )
    async def erase(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.edit_draw(interaction, CURSOR[self.bg])

    @discord.ui.button(
        emoji="<:left:920895993145327628>", style=discord.ButtonStyle.blurple
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        row_move = 0
        col_move = -1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(
        emoji="<:auto_cursor:921352341427470347>", style=discord.ButtonStyle.gray
    )
    async def auto_colour(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        if self.auto == False:
            self.auto = True
            self.auto_colour.style = discord.ButtonStyle.green
        elif self.auto == True:
            self.auto = False
            self.auto_colour.style = discord.ButtonStyle.grey
        await interaction.edit_original_message(view=self)

    @discord.ui.button(
        emoji="<:right:920895888229036102>", style=discord.ButtonStyle.blurple
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        row_move = 0
        col_move = 1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.gray)
    async def placeholder6(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()

    @discord.ui.button(
        emoji="<:middle:920897054060998676>", style=discord.ButtonStyle.green
    )
    async def draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.edit_draw(interaction, self.cursor)

    @discord.ui.button(
        emoji="<:down_left:920895965987242025>", style=discord.ButtonStyle.blurple
    )
    async def down_left(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        row_move = 1
        col_move = -1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(
        emoji="<:down:920895939030429696>", style=discord.ButtonStyle.blurple
    )
    async def down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        row_move = 1
        col_move = 0
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(
        emoji="<:down_right:920895913608765551>", style=discord.ButtonStyle.blurple
    )
    async def down_right(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        row_move = 1
        col_move = 1
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)

    @discord.ui.button(
        emoji="<:ABCD:920896121285537832>", style=discord.ButtonStyle.blurple
    )
    async def set_cursor(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        res = await interaction.followup.send(
            content='Please type the cell you want to move the cursor to. e.g. "A1", "a1", "A10", "A", "10", etc.',
            ephemeral=True,
        )

        def check(m):
            return m.author == interaction.user

        try:
            msg = await wait_for(self.ctx, check=check)
            await msg.delete()
        except asyncio.TimeoutError:
            return await res.edit(content="Timed out.")
        cell = msg.content.upper()

        ABC = ALPHABETS[: self.cursor_row_max + 1]
        NUM = NUMBERS[: self.cursor_col_max + 1]
        CELL_REGEX = f"^(?P<row>[A-{ABC[-1]}])(?P<col>[0-9]|(?:1[0-{NUM[-1] % 10}]))$"
        ROW_OR_CELL_REGEX = (
            f"(?:^(?P<row>[A-{ABC[-1]}])$)|(?:^(?P<col>[0-9]|(?:1[0-{NUM[-1] % 10}]))$)"
        )

        match = re.match(CELL_REGEX, cell)
        if match:
            row_key = match.group("row")
            col_key = int(match.group("col"))
        else:
            match = re.match(ROW_OR_CELL_REGEX, cell)
            row_key = match.group("row")
            row_key = row_key if row_key is not None else ABC[self.cursor_row]

            col_key = match.group("col")
            col_key = int(col_key) if col_key is not None else self.cursor_col

        if row_key not in ABC or col_key not in NUM:
            return await res.edit(content="Aborted.")

        row_move = LETTER_TO_NUMBER[row_key] - self.cursor_row
        col_move = col_key - self.cursor_col
        await self.move_cursor(interaction, row_move=row_move, col_move=col_move)
        await res.edit(
            content=f"Moved cursor to **{cell}** ({LETTER_TO_NUMBER[row_key]}, {col_key})"
        )


async def setup(bot):
    await bot.add_cog(Draw(bot))
