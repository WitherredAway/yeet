from __future__ import annotations

import logging
import os
import time
from functools import cached_property
from typing import TYPE_CHECKING, Callable, List, Optional, Union

import discord
from cogs.AFD.utils.views import SubmitView
import gists
import pandas as pd
from discord.ext import commands

from helpers.constants import INDENT, NL
from helpers.context import CustomContext

from ..utils.utils import UrlView, make_progress_bar
from .utils.views import AfdView
from .utils.utils import AFDRoleMenu, EmbedColours, Row
from .utils.urls import AFD_CREDITS_GIST_URL, AFD_GIST_URL, SHEET_URL, SUBMISSION_URL
from .utils.sheet import AfdSheet
from .utils.constants import (
    AFD_ADMIN_ROLE_ID,
    AFD_ROLE_ID,
    CLAIM_LIMIT,
    DEL_ATTRS_TO_UPDATE,
    LOG_CHANNEL_ID,
    UPDATE_CHANNEL_ID,
)
from .utils.labels import (
    CMT_LABEL,
    SUBMIT_BTN_LABEL,
)
from .ext.afd_gist import AfdGist

if TYPE_CHECKING:
    from main import Bot


log = logging.getLogger(__name__)


class PokemonView(discord.ui.View):
    def __init__(
        self,
        ctx: CustomContext,
        row: Row,
        *,
        afdcog: Afd,
        user: Optional[discord.User] = None,
        approved_by: Optional[discord.User] = None,
    ):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.row = row
        self.pokemon = self.row.pokemon
        self.afdcog = afdcog
        self.sheet = self.afdcog.sheet
        self.user = user
        self.approved_by = approved_by

        self.msg: discord.Message

    async def on_timeout(self):
        self.clear_items()
        await self.msg.edit(embed=self.embed, view=self)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                f"You can't use this!",
                ephemeral=True,
            )
            return False
        return True

    @property
    def embed(self) -> Bot.Embed:
        ctx = self.ctx
        row = self.row
        pokemon = self.pokemon
        base_image = self.sheet.get_pokemon_image(pokemon)

        embed = ctx.bot.Embed(title=f"#{row.dex} - {pokemon}")
        embed.set_thumbnail(url=base_image)
        self.update(embed)
        return embed

    def update(self, embed: Bot.Embed):
        """Method responsible for setting things based on status such as Status footer, Embed colour, Fields and Buttons"""
        self.clear_items()

        row = self.row
        color = self.ctx.bot.Embed.COLOUR
        if row.claimed:
            embed.set_author(
                name=f"{row.username} ({row.user_id})", icon_url=self.user.avatar.url
            )

            status = "Claimed."
            color = EmbedColours.CLAIMED.value
            if row.user_id == self.ctx.author.id:
                self.add_item(self.unclaim_btn)  # Add unclaim button if claimed by self

            if row.user_id == self.ctx.author.id:
                self.submit_btn.label = (
                    SUBMIT_BTN_LABEL if not row.image else "Edit submission"
                )
                self.add_item(self.submit_btn)  # Add submit button if claimed by self

            if row.image:
                embed.set_image(url=row.image)
                if row.completed:
                    status = f"Complete! Approved by {self.approved_by}."
                    color = EmbedColours.COMPLETED.value
                    if self.afdcog.is_admin(self.ctx.author):
                        self.add_item(
                            self.unapprove_btn
                        )  # Add unapprove button if completed
                else:
                    if self.afdcog.is_admin(self.ctx.author):
                        self.add_item(
                            self.approve_btn
                        )  # Add approve button if not completed

                if row.correction_pending:
                    status = "Correction pending."
                    color = EmbedColours.CORRECTION.value
                    embed.add_field(
                        name=f"{CMT_LABEL} by {self.approved_by}",
                        value=str(row.comment),
                        inline=False,
                    )
                elif row.unreviewed:
                    status = "Submitted, Awaiting review."
                    color = EmbedColours.UNREVIEWED.value

            if (not row.image) or (row.correction_pending):
                if self.afdcog.is_admin(self.ctx.author):
                    self.add_item(
                        self.remind_btn
                    )  # Add remind button if not submitted or correction pending

            embed.set_footer(
                text=f"{status}",
            )
        else:
            status = "Not claimed."
            color = EmbedColours.UNCLAIMED.value
            embed.set_footer(text=status)
            self.add_item(self.claim_btn)  # Add claim button if not claimed

        embed.color = color

    async def update_msg(self):
        await self.sheet.update_df()
        self.row = self.sheet.get_pokemon_row(self.pokemon)
        self.user = (
            (await self.afdcog.fetch_user(self.row.user_id))
            if self.row.claimed
            else None
        )
        await self.msg.edit(embed=self.embed, view=self)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.blurple, row=0)
    async def claim_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        await self.afdcog.claim(self.ctx, self.pokemon)
        await self.update_msg()

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.red, row=0)
    async def unclaim_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        await self.afdcog.unclaim(self.ctx, self.pokemon)
        await self.update_msg()

    @discord.ui.button(label=SUBMIT_BTN_LABEL, style=discord.ButtonStyle.blurple, row=0)
    async def submit_btn(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = self.ctx.bot.Embed(
            title=f"Submit drawing for {self.pokemon}",
            description=f"""**Steps to submit a drawing**:
- Upload it to the website ({SUBMISSION_URL}) using the Upload button below. You will be given a URL to the uploaded image.
- Use the green submit button below and paste in the URL to submit it!
    - You can edit/delete a submission later!""",
        )
        embed.set_footer(
            text="The upload website is an official Pokétwo website made by Oliver!"
        )
        view = SubmitView(self.afdcog, row=self.row, ctx=self.ctx)
        await interaction.response.send_message(embed=embed, view=view)
        view.msg = await interaction.original_message()
        await view.wait()
        await self.update_msg()

    @discord.ui.button(label="Remind", style=discord.ButtonStyle.blurple, row=1)
    async def remind_btn(
        self, interaction: discord.Interaction, button: discord.Buttons
    ):
        await self.afdcog.send_notification(
            embed=self.afdcog.pkm_remind_embed(self.row), user=self.user, ctx=self.ctx
        )
        await interaction.response.send_message(
            f"Successfully sent a reminder to **{self.user}**.", ephemeral=True
        )

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, row=1)
    async def approve_btn(
        self, interaction: discord.Interaction, button: discord.Buttons
    ):
        await interaction.response.defer()
        await self.afdcog.approve(self.ctx, self.pokemon)
        await self.update_msg()

    @discord.ui.button(label="Unapprove", style=discord.ButtonStyle.red, row=1)
    async def unapprove_btn(
        self, interaction: discord.Interaction, button: discord.Buttons
    ):
        await interaction.response.defer()
        await self.afdcog.unapprove(self.ctx, self.pokemon)
        await self.update_msg()


class Afd(AfdGist):
    def __init__(self, bot):
        self.bot: Bot = bot
        self.hidden = True

        self.bot.user_cache: dict = {}
        self.user_cache = self.bot.user_cache

        self.sheet: AfdSheet

    display_emoji = "🗓️"

    async def cog_load(self):
        self.gists_client = gists.Client()
        await self.gists_client.authorize(os.getenv("WgithubTOKEN"))

        self.log_channel = await self.bot.fetch_channel(LOG_CHANNEL_ID)
        self.update_channel = await self.bot.fetch_channel(UPDATE_CHANNEL_ID)
        self.afd_gist = await self.gists_client.get_gist(AFD_GIST_URL)
        self.credits_gist = await self.gists_client.get_gist(AFD_CREDITS_GIST_URL)

        start = time.time()
        await self.sheet.setup()
        log.info(f"AFD: Fetched spreadsheet in {round(time.time()-start, 2)}s")

        self.update_pokemon.start()

    async def cog_unload(self):
        if self.update_pokemon.is_running():
            self.update_pokemon.cancel()

    @property
    def pk(self) -> pd.DataFrame:
        return self.bot.pk

    @property
    def df(self) -> pd.DataFrame:
        return self.sheet.df

    @property
    def total_amount(self) -> int:
        return len(self.df)

    @cached_property
    def sheet(self) -> AfdSheet:
        return AfdSheet(SHEET_URL, pokemon_df=self.pk)

    def is_admin(self, user: discord.Member) -> bool:
        return AFD_ADMIN_ROLE_ID in [r.id for r in user.roles]

    def confirmation_embed(
        self,
        description: str,
        *,
        row: Optional[Row] = None,
        colour: Optional[EmbedColours] = None,
        footer: Optional[str] = None,
    ) -> Bot.Embed:
        embed = self.bot.Embed(
            description=description, colour=colour.value if colour else colour
        )
        if row is not None:
            pokemon_image = self.sheet.get_pokemon_image(row.pokemon)
            embed.set_thumbnail(url=pokemon_image)
            if row.image:
                embed.set_image(url=row.image)
        if footer:
            embed.set_footer(text=footer)
        return embed

    def pkm_remind_embed(self, pkm_rows: Union[Row, List[Row]]) -> Bot.Embed:
        if not isinstance(pkm_rows, list):
            pkm_rows = [pkm_rows]
        embed = self.bot.Embed(
            title="AFD Reminder",
        )
        pkms = [
            f"- {row.pokemon}{f' (`{row.comment}`)' if row.comment else ''}"
            for row in pkm_rows
        ]
        embed.add_field(
            name="Your following claimed Pokémon have not been completed yet",
            value=NL.join(pkms),
            inline=False,
        )
        embed.add_field(name="Deadline", value=self.sheet.DEADLINE_TS, inline=False)
        embed.set_footer(
            text="Please draw them or unclaim any you think you cannot finish. Thank you!"
        )
        return embed

    async def fetch_user(self, user_id: int) -> discord.User:
        user_id = int(user_id)
        if (user := self.user_cache.get(user_id)) is not None:
            return user

        if (user := self.bot.get_user(user_id)) is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except Exception as e:
                await self.update_channel.send(user_id)
                raise e

        self.user_cache[user_id] = user
        return user

    async def send_notification(
        self,
        embed: Union[Bot.Embed, List[Bot.Embed]],
        *,
        user: discord.User,
        ctx: CustomContext,
        view: Optional[discord.ui.View] = None,
    ) -> bool:
        if not isinstance(embed, list):
            embed = [embed]

        try:
            await user.send(embeds=embed, view=view)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send(f"{user.mention} (Unable to DM)", embeds=embed, view=view)
            return False
        else:
            return True

    async def get_pokemon(self, ctx: CustomContext, name: str) -> Union[str, None]:
        try:
            name = self.sheet.get_pokemon(name)
        except IndexError:
            await ctx.reply(
                embed=self.confirmation_embed(
                    f"`{name}` is not a valid Pokemon!", colour=EmbedColours.INVALID
                )
            )
            return None
        return name

    async def check_claim(
        self,
        ctx: CustomContext,
        decide_msg: Callable[[Row], str],
        pokemon: str,
        *,
        check: Callable[[Row], bool],
        row: Optional[Row] = None,
        decide_footer: Optional[Callable[[Row], str]] = None,
        cmsg: Optional[bool] = None,
    ) -> bool:
        if not row:
            # Check once again for any changes to the sheet
            await self.sheet.update_df()
            row = self.sheet.get_pokemon_row(pokemon)

        if check(row):
            embed = self.confirmation_embed(
                decide_msg(row),
                row=row,
                colour=EmbedColours.INVALID,
                footer=decide_footer(row) if decide_footer else decide_footer,
            )
            if cmsg:
                await cmsg.edit(embed=embed)
            else:
                await ctx.reply(embed=embed)
            return True
        return False

    @property
    def embed(self) -> Bot.Embed:
        unc_list, unc_amount = self.validate_unclaimed()
        claimed_amount = self.total_amount - unc_amount

        unr_list, unr_amount = self.validate_unreviewed()

        ml_list, ml_list_mention, ml_amount = self.validate_missing_link()
        submitted_amount = claimed_amount - ml_amount
        completed_amount = submitted_amount - unr_amount

        description = f"""**Topic:** {self.sheet.TOPIC}

**Deadline**: {self.sheet.DEADLINE_TS}
**Max claimed (unfinished) pokemon**: {self.sheet.CLAIM_MAX}
**Max unapproved pokemon**: {self.sheet.UNAPP_MAX}
"""
        embed = self.bot.Embed(
            title="Welcome to the April Fools community project!",
            description=description,
        )
        embed.add_field(
            name="Rules",
            value=self.sheet.RULES.format(
                CLAIM_MAX=self.sheet.CLAIM_MAX, UNAPP_MAX=self.sheet.UNAPP_MAX
            ),
            inline=False,
        )

        embed.add_field(
            name="Community Stats",
            value=f"""**Completed**
{make_progress_bar(completed_amount, self.total_amount)} {completed_amount}/{self.total_amount}
**Submitted**
{make_progress_bar(submitted_amount, self.total_amount)} {submitted_amount}/{self.total_amount}
**Claimed**
{make_progress_bar(claimed_amount, self.total_amount)} {claimed_amount}/{self.total_amount}""",
            inline=False,
        )
        return embed

    @commands.check_any(commands.is_owner(), commands.has_role(AFD_ROLE_ID))
    @commands.group(
        name="afd",
        brief="Afd commands",
        description="Command with a variety of afd event subcommands! If invoked alone, it will show event stats.",
    )
    async def afd(self, ctx: CustomContext):
        await ctx.typing()
        if ctx.invoked_subcommand is None:
            await ctx.invoke(self.info)

    # --- Owner only commands ---
    @commands.is_owner()
    @afd.command(
        name="new_spreadsheet",
        brief="Used to create a brand new spreadsheet.",
        description="Sets up a new spreadsheet to use. Intended to be used only once.",
    )
    async def new(self, ctx: CustomContext):
        if hasattr(self, "sheet"):
            return await ctx.reply("A spreadsheet already exists.")

        async with ctx.typing():
            self.sheet: AfdSheet = await AfdSheet.create_new(pokemon_df=self.pk)

        embed = self.bot.Embed(
            title="New Spreadsheet created",
            description=f"[Please set it permanently in the code.]({self.sheet.url})",
        )
        await ctx.reply(
            embed=embed, view=UrlView({"Go To Spreadsheet": self.sheet.url})
        )

    @commands.is_owner()
    @afd.command(
        name="forceupdate",
        brief="Forcefully update AFD gists.",
        description="Used to forcefully update the AFD gist and Credits gist",
    )
    async def forceupdate(self, ctx: CustomContext):
        for attr in DEL_ATTRS_TO_UPDATE:
            try:
                delattr(self, attr)
            except AttributeError:
                pass

        await ctx.message.add_reaction("▶️")
        self.update_pokemon.restart()
        await ctx.message.add_reaction("✅")

    @commands.is_owner()
    @afd.command(name="rolemenu")
    async def rolemenu(self, ctx: CustomContext):
        role_menu = AFDRoleMenu()
        await ctx.send(
            f"""<@&{AFD_ROLE_ID}>: Role required to access `afd` commands
<@&{AFD_ADMIN_ROLE_ID}>: Role required to access AFD Admin only `afd` commands.""",
            view=role_menu,
            allowed_mentions=discord.AllowedMentions(roles=False),
        )

    # --- AFD Admin only commands ---
    @commands.has_role(AFD_ADMIN_ROLE_ID)
    @afd.command(
        name="forceclaim",
        aliases=("fc",),
        brief="Forcefully claim a pokemon in someone's behalf.",
        description="AFD Admin-only command to forcefully claim a pokemon in someone's behalf.",
        help=f"""When this command is ran, first the sheet data will be fetched. Then:
1. A pokemon, with the normalized and deaccented version of the provided name *including alt names*, will be searched for. If not found, it will return invalid.
2. That pokemon's availability on the sheet will be checked:
{INDENT}**i. If it's *not* claimed yet:**
{INDENT}{INDENT}- If the user already has max claims ({CLAIM_LIMIT}), it will still give you the option to proceed.
{INDENT}{INDENT}- Otherwise, you will be prompted to confirm that you want to forceclaim the pokemon for the user.
{INDENT}**ii. If it's already claimed by *the same user*, you will be informed of such.**
{INDENT}**iii. If it's already claimed by *another user*, you will be prompted to confirm if you want to override. Will warn you \
    if there is a drawing submitted already.**
3. The sheet will finally be updated with the user's Username and ID""",
    )
    async def forceclaim(
        self, ctx: CustomContext, user: Optional[discord.User] = None, *, pokemon: str
    ):
        if user is None:
            user = ctx.author
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        if not row.claimed:
            content = None
            if self.sheet.can_claim(user) is False:
                content = f"**{user}** already has the max number ({CLAIM_LIMIT}) of pokemon claimed, still continue?"

            conf, cmsg = await ctx.confirm(
                embed=self.confirmation_embed(
                    content
                    or f"Are you sure you want to forceclaim **{pokemon}** for **{user}**?",
                    row=row,
                ),
                confirm_label="Force Claim",
            )
            if conf is False:
                return
        elif row.user_id == user.id:
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** is already claimed by **{user}**!",
                    row=row,
                    colour=EmbedColours.INVALID,
                )
            )
        else:
            conf, cmsg = await ctx.confirm(
                embed=self.confirmation_embed(
                    f"**{pokemon}** is already claimed by **{row.username}**, override and claim it for **{user}**?\
                        {' There is a drawing submitted already which will be removed.' if row.image else ''}",
                    row=row,
                ),
                confirm_label="Force Claim",
            )
            if conf is False:
                return

        self.sheet.claim(user, pokemon)
        await self.sheet.update_row(row.dex)
        await cmsg.edit(
            embed=self.confirmation_embed(
                f"You have successfully force claimed **{pokemon}** for **{user}**.",
                row=row,
                colour=EmbedColours.CLAIMED,
            )
        )
        embed = self.confirmation_embed(
            f"**{pokemon}** has been forcefully claimed for **{user}**.",
            row=row,
            colour=EmbedColours.CLAIMED,
            footer=f"by {ctx.author}",
        )
        view = UrlView({"Go to message": cmsg.jump_url})
        await self.log_channel.send(embed=embed, view=view)
        embed.description = f"**{pokemon}** has been forcefully claimed for you."
        await self.send_notification(embed, user=user, ctx=ctx, view=view)

    @commands.has_role(AFD_ADMIN_ROLE_ID)
    @afd.command(
        name="forceunclaim",
        aliases=("ufc",),
        brief="Forcefully unclaim a pokemon",
        description="AFD Admin-only command to forcefully unclaim a pokemon",
        help=f"""When this command is ran, first the sheet data will be fetched. Then:
1. A pokemon, with the normalized and deaccented version of the provided name *including alt names*, will be searched for. If not found, it will return invalid.
2. That pokemon's availability on the sheet will be checked:
{INDENT}**i. If it is claimed:**
{INDENT}{INDENT}- You will be prompted to confirm that you want to force unclaim the pokemon.\
    Will warn you if there is a drawing submitted already.
{INDENT}{INDENT}- The sheet will finally be updated and remove the user's Username and ID
{INDENT}**ii. If it's *not* claimed, you will be informed of such.**""",
    )
    async def forceunclaim(self, ctx, *, pokemon: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        if not row.claimed:
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** is not claimed.",
                    row=row,
                    colour=EmbedColours.INVALID,
                )
            )
        conf, cmsg = await ctx.confirm(
            embed=self.confirmation_embed(
                f"**{pokemon}** is currently claimed by **{row.username}**, forcefully unclaim?\
                        {' There is a drawing already submitted which will be removed.' if row.image else ''}",
                row=row,
            ),
            confirm_label="Force Unclaim",
        )
        if conf is False:
            return

        self.sheet.unclaim(
            pokemon,
        )
        await cmsg.edit(
            embed=self.confirmation_embed(
                f"You have successfully force unclaimed **{pokemon}** from **{row.username}**.",
                row=row,
                colour=EmbedColours.UNCLAIMED,
            )
        )
        embed = self.confirmation_embed(
            f"**{pokemon}** has been forcefully unclaimed from **{row.username}**.",
            row=row,
            colour=EmbedColours.UNCLAIMED,
            footer=f"by {ctx.author}",
        )
        user = await self.fetch_user(row.user_id)
        view = UrlView({"Go to message": cmsg.jump_url})
        await self.log_channel.send(embed=embed, view=view)
        embed.description = f"**{pokemon}** has been forcefully unclaimed from you."
        await self.send_notification(embed, user=user, ctx=ctx, view=view)

    async def approve(self, ctx: CustomContext, pokemon: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        conf = cmsg = None
        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        approved_by = (
            await self.fetch_user(row.approved_by) if row.approved_by else None
        )
        if any((not row.claimed, not row.image)):
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** {'is not claimed' if not row.claimed else 'has not been submitted'}.",
                    colour=EmbedColours.INVALID,
                )
            )
        elif row.completed:
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** has already been approved by **{approved_by}**!",
                    colour=EmbedColours.COMPLETED,
                )
            )
        conf, cmsg = await ctx.confirm(
            embed=self.confirmation_embed(
                f"""{f'There is a correction pending with comment "{row.comment}" by **{approved_by}**. ' if row.correction_pending else ''}\nAre you sure you want to approve **{pokemon}**?""",
                row=row,
            ),
            confirm_label="Approve",
        )
        if conf is False:
            return

        self.sheet.approve(pokemon, by=ctx.author.id)
        await self.sheet.update_row(row.dex)
        await cmsg.edit(
            embed=self.confirmation_embed(
                f"**{pokemon}** has been approved! 🎉",
                row=row,
                colour=EmbedColours.COMPLETED,
                footer=f"You can undo this using the `unapprove` command.",
            )
        )
        embed = self.confirmation_embed(
            f"**{pokemon}** has been approved! 🎉",
            row=row,
            colour=EmbedColours.COMPLETED,
            footer=f"by {ctx.author}",
    )
    async def approve_cmd(self, ctx: CustomContext, *, pokemon: str):
        await self.approve(ctx, pokemon)

    async def unapprove(self, ctx: CustomContext, pokemon: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        conf = cmsg = None
        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        if not row.completed:
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** has not been approved.",
                    colour=EmbedColours.INVALID,
                )
            )
        approved_by = await self.fetch_user(row.approved_by)
        conf, cmsg = await ctx.confirm(
            embed=self.confirmation_embed(
                f"Are you sure you want to unapprove **{pokemon}**?",
                row=row,
                footer=f"Approved by {approved_by}",
            ),
            confirm_label="Unapprove",
        )
        if conf is False:
            return

        self.sheet.unapprove(pokemon)
        await self.sheet.update_row(row.dex)
        await cmsg.edit(
            embed=self.confirmation_embed(
                f"**{pokemon}** has been unapproved.",
                row=row,
                colour=EmbedColours.UNREVIEWED,
            )
        )
        embed = self.confirmation_embed(
            f"**{pokemon}** has been unapproved.",
            row=row,
            colour=EmbedColours.UNREVIEWED,
            footer=f"by {ctx.author}",
        )
        user = await self.fetch_user(row.user_id)
        view = UrlView({"Go to message": cmsg.jump_url})
        await self.log_channel.send(embed=embed, view=view)
        await self.send_notification(embed, user=user, ctx=ctx, view=view)

    @commands.has_role(AFD_ADMIN_ROLE_ID)
    @afd.command(
        name="unapprove",
        brief="Unapprove an approved drawing",
        help="""Used to unapprove an approved drawing submission.""",
    )
    async def unapprove_cmd(self, ctx: CustomContext, *, pokemon: str):
        await self.unapprove(ctx, pokemon)

    # --- Public commands ---
    @afd.command(
        name="info",
        aliases=("information", "progress"),
        brief="View progress of the april fool's event.",
        help="""If `pokemon` arg is passed and `user` is not, it will show info of that pokemon.
If `user` arg is passed, it will show stats of that user. Otherwise it will show your stats. If `user` is a non-participant, it will not show their stats.""",
        description="Shows user and community stats.",
    )
    async def info(
        self,
        ctx: CustomContext,
        user: Optional[discord.User] = None,
        *,
        pokemon: Optional[str] = None,
    ):
        if pokemon and (user is None):
            return await ctx.invoke(self.view, pokemon=pokemon)
        if user is None:
            user = ctx.author

        await self.sheet.update_df()
        view = AfdView(self, ctx=ctx)
        view.msg = await ctx.reply(embed=self.embed, view=view)

    @afd.command(
        name="view",
        aliases=("pokemon", "pkm", "d", "dex"),
        brief="See info of a pokemon from the sheet",
    )
    async def view(self, ctx: CustomContext, *, pokemon: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        user = (await self.fetch_user(row.user_id)) if row.claimed else None
        approved_by = (
            (await self.fetch_user(row.approved_by)) if row.approved_by else None
        )

        view = PokemonView(ctx, row, afdcog=self, user=user, approved_by=approved_by)
        view.msg = await ctx.send(embed=view.embed, view=view)

    async def claim(self, ctx: CustomContext, pokemon: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        conf = cmsg = None
        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        if not row.claimed:
            if self.sheet.can_claim(ctx.author) is False and not self.is_admin(
                ctx.author
            ):
                return await ctx.reply(
                    embed=self.confirmation_embed(
                        f"You already have the max number ({CLAIM_LIMIT}) of pokemon claimed!",
                        colour=EmbedColours.INVALID,
                    )
                )

            conf, cmsg = await ctx.confirm(
                embed=self.confirmation_embed(
                    f"Are you sure you want to claim **{pokemon}**?", row=row
                ),
            )
            if conf is False:
                return

        decide_msg = (
            lambda row: f"**{pokemon}** is already claimed by **{'you' if row.user_id == ctx.author.id else row.username}**!"
        )
        check = lambda row: row.claimed
        decide_footer = (
            lambda row: "You can unclaim it using the `unclaim` command."
            if row.user_id == ctx.author.id
            else None
        )
        claimed = await self.check_claim(
            ctx,
            decide_msg,
            pokemon,
            check=check,
            row=row if conf is None else None,
            decide_footer=decide_footer,
            cmsg=cmsg,
        )
        if claimed is True:
            return

        self.sheet.claim(ctx.author, pokemon)
        await self.sheet.update_row(row.dex)
        embed = self.confirmation_embed(
            f"You have successfully claimed **{pokemon}**, have fun! :D",
            row=row,
            colour=EmbedColours.CLAIMED,
            footer=f"You can undo this using the `unclaim` command.",
        )
        await cmsg.edit(embed=embed)

        view = UrlView({"Go to message": cmsg.jump_url})
        await self.log_channel.send(
            embed=self.confirmation_embed(
                f"**{ctx.author}** has claimed **{pokemon}**.",
                row=row,
                colour=EmbedColours.CLAIMED,
            ),
            view=view,
        )

        await self.send_notification(embed, user=ctx.author, ctx=ctx, view=view)

    @afd.command(
        name="claim",
        brief="Claim a pokemon to draw",
        description=f"Claim a pokemon to draw. Can have upto {CLAIM_LIMIT} claimed pokemon at a time. Pokemon alt names are supported!",
        help=f"""When this command is ran, first the sheet data will be fetched. Then:
1. A pokemon, with the normalized and deaccented version of the provided name *including alt names*, will be searched for. If not found, it will return invalid.
2. That pokemon's availability on the sheet will be checked:
{INDENT}**i. If it's *not* claimed yet:**
{INDENT}{INDENT}- If you already have max claims ({CLAIM_LIMIT}), it will not let you claim. Does not apply to admins.
{INDENT}{INDENT}- Otherwise, you will be prompted to confirm that you want to claim the pokemon.
{INDENT}{INDENT}- The sheet data will be fetched again to check for any changes since.
{INDENT}{INDENT}{INDENT}- If the pokemon has since been claimed, you will be informed of such.
{INDENT}{INDENT}- The sheet will finally be updated with your Username and ID
{INDENT}**ii. If it's already claimed by *you* or *someone else*, you will be informed of such.**""",
    )
    async def claim_cmd(self, ctx: CustomContext, *, pokemon: str):
        await self.claim(ctx, pokemon)

    async def unclaim(self, ctx: CustomContext, pokemon: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        conf = cmsg = None
        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        if row.user_id == ctx.author.id:
            conf, cmsg = await ctx.confirm(
                embed=self.confirmation_embed(
                    f"Are you sure you want to unclaim **{pokemon}**?\
                        {' You have already submitted a drawing which will be removed.' if row.image else ''}",
                    row=row,
                ),
                confirm_label="Unclaim",
            )
            if conf is False:
                return

        check = lambda row: (not row.claimed) or row.user_id != ctx.author.id
        decide_msg = (
            lambda row: f"**{pokemon}** is not claimed."
            if not row.claimed
            else f"**{pokemon}** is claimed by **{row.username}**!"
        )
        decide_footer = (
            lambda row: None
            if not row.claimed
            else (
                "You can force unclaim it using the `forceunclaim` command."
                if self.is_admin(ctx.author)
                else None
            )
        )
        not_claimed = await self.check_claim(
            ctx,
            decide_msg,
            pokemon,
            check=check,
            row=row if conf is None else None,
            decide_footer=decide_footer,
            cmsg=cmsg,
        )
        if not_claimed is True:
            return

        self.sheet.unclaim(pokemon)
        await self.sheet.update_row(row.dex)
        embed = self.confirmation_embed(
            f"You have successfully unclaimed **{pokemon}**.",
            row=row,
            colour=EmbedColours.UNCLAIMED,
        )
        await cmsg.edit(embed=embed)

        view = UrlView({"Go to message": cmsg.jump_url})
        await self.log_channel.send(
            embed=self.confirmation_embed(
                f"**{ctx.author}** has unclaimed **{pokemon}**.",
                row=row,
                colour=EmbedColours.UNCLAIMED,
            ),
            view=view,
        )

        await self.send_notification(embed, user=ctx.author, ctx=ctx, view=view)

    @afd.command(
        name="unclaim",
        brief="Unclaim a pokemon",
        description=f"Unclaim a pokemon claimed by you.",
        help=f"""When this command is ran, first the sheet data will be fetched. Then:
1. A pokemon, with the normalized and deaccented version of the provided name *including alt names*, will be searched for. If not found, it will return invalid.
2. That pokemon's availability on the sheet will be checked:
{INDENT}**i. If it is claimed by *you*:**
{INDENT}{INDENT}- You will be prompted to confirm that you want to unclaim the pokemon.\
    Will warn you if you have already submitted a drawing.
{INDENT}{INDENT}- The sheet will finally be updated and remove your Username and ID
{INDENT}**ii. If it's *not* claimed, you will be informed of such.**
{INDENT}**iii. If it's claimed by *someone else*, you will be informed of such.**""",
    )
    async def unclaim_cmd(self, ctx: CustomContext, *, pokemon: str):
        await self.unclaim(ctx, pokemon)

    def dual_image_embed(
        self,
        description: str,
        *,
        url1: Optional[Union[str, None]] = None,
        url2: str,
        thumbnail: str,
        color: Optional[int] = None,
        footer: Optional[str] = None,
    ):
        embeds = []
        embed = self.bot.Embed(description=description, url=url1, color=color)
        embed.set_thumbnail(url=thumbnail)
        if footer:
            embed.set_footer(text=footer)
        if url1:
            embed.set_image(url=url1)
            embeds.append(embed)

        embed2 = embed.copy()
        embed2.set_image(url=url2)
        embeds.append(embed2)

        return embeds

    async def submit(self, ctx: CustomContext, pokemon: str, *, image_url: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return
        # TODO image_url CHECK

        conf = cmsg = None
        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        base_image = self.sheet.get_pokemon_image(row.pokemon)
        if not row.claimed:
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** is not claimed.",
                    colour=EmbedColours.INVALID,
                )
            )
        if not (row.user_id == ctx.author.id):
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** is not claimed by you!",
                    colour=EmbedColours.INVALID,
                )
            )

        embeds = self.dual_image_embed(
            description=f"Are you sure you want to {'re' if row.image else ''}submit the following drawing for **{pokemon}**?\n\n{'Before / After' if row.image else ''}",
            url1=row.image,
            url2=image_url,
            thumbnail=base_image,
        )
        conf, cmsg = await ctx.confirm(
            embed=embeds,
            confirm_label="Submit",
        )
        if conf is False:
            return

        self.sheet.submit(pokemon, image_url=image_url)
        await self.sheet.update_row(row.dex)
        embeds = self.dual_image_embed(
            description=f"You have successfully {'re' if row.image else ''}submitted the following image for **{pokemon}**.\n\n{'Before / After' if row.image else ''}",
            url1=row.image,
            url2=image_url,
            thumbnail=base_image,
            color=EmbedColours.UNREVIEWED.value,
            footer="You will be notified when it has been reviewed :)",
        )
        await cmsg.edit(embeds=embeds)

        view = UrlView({"Go to message": cmsg.jump_url})
        await self.log_channel.send(
            embeds=self.dual_image_embed(
                description=f"{ctx.author} has {'re' if row.image else ''}submitted the following image for **{pokemon}**.\n\n{'Before / After' if row.image else ''}",
                url1=row.image,
                url2=image_url,
                thumbnail=base_image,
                color=EmbedColours.UNREVIEWED.value,
            ),
            view=view,
        )

        await self.send_notification(embeds, user=ctx.author, ctx=ctx, view=view)

    @afd.command(
        name="submit",
        bried="Submit a drawing.",
        help="Submit a drawing for a pokemon. This also removes any approved or comment status. WIP, TODO: VALIDATE URL",
    )
    async def submit_cmd(self, ctx: CustomContext, pokemon: str, image_url: str):
        await self.submit(ctx, pokemon, image_url=image_url)

    async def unsubmit(self, ctx: CustomContext, pokemon: str):
        pokemon = await self.get_pokemon(ctx, pokemon)
        if not pokemon:
            return

        conf = cmsg = None
        await self.sheet.update_df()
        row = self.sheet.get_pokemon_row(pokemon)
        base_image = self.sheet.get_pokemon_image(row.pokemon)
        if not row.image:
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** is not submitted.",
                    colour=EmbedColours.INVALID,
                )
            )
        if not (row.user_id == ctx.author.id):
            return await ctx.reply(
                embed=self.confirmation_embed(
                    f"**{pokemon}** is not submitted by you!",
                    colour=EmbedColours.INVALID,
                )
            )

        embeds = self.dual_image_embed(
            description=f"Are you sure you want to unsubmit the following drawing for **{pokemon}**?",
            url2=row.image,
            thumbnail=base_image,
        )
        conf, cmsg = await ctx.confirm(
            embed=embeds,
            confirm_label="Unsubmit",
        )
        if conf is False:
            return

        self.sheet.submit(pokemon, image_url="")
        await self.sheet.update_row(row.dex)
        embeds = self.dual_image_embed(
            description=f"You have successfully unsubmitted the following image for **{pokemon}**",
            url2=row.image,
            thumbnail=base_image,
            color=EmbedColours.CLAIMED.value,
        )
        await cmsg.edit(embeds=embeds)

        view = UrlView({"Go to message": cmsg.jump_url})
        await self.log_channel.send(
            embeds=self.dual_image_embed(
                description=f"{ctx.author} has unsubmitted the following image for **{pokemon}**.",
                url2=row.image,
                thumbnail=base_image,
                color=EmbedColours.CLAIMED.value,
            ),
            view=view,
        )

        await self.send_notification(embeds, user=ctx.author, ctx=ctx, view=view)

    @afd.command(
        name="unsubmit",
        bried="Clear submitted drawing of a pokemon.",
        help="Clear submitted drawing of a pokemon. This also removes any approved or comment status.",
    )
    async def unsubmit_cmd(self, ctx: CustomContext, pokemon: str):
        await self.unsubmit(ctx, pokemon)


async def setup(bot):
    await bot.add_cog(Afd(bot))
