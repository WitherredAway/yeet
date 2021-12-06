import discord
from discord.ext import commands
import asyncio
from main import *
from typing import Counter
import wikipedia

class Useful(commands.Cog):
    """Useful commands"""
    def __init__(self, bot):
        self.bot = bot
  
    #avatar
    @commands.command(name="avatar",
                      aliases=["av", "pfp", "profilepicture"],
                      brief="Avatar url",
                      help="Sends the avatar url of author/mentioned member.")
    async def avatar(self, ctx, member: discord.Member=None):
        member = member or ctx.author
        embed = discord.Embed(title=f"Avatar of {member}", color=embed_colour)
        embed.set_image(url = ctx.author.avatar.url)
        await ctx.send(embed=embed)
  
    #wiki
    @commands.command(name="wiki",
                      aliases=["wikipedia"],
                      brief="Searches wikipedia for info.",
                      help="Use this command to look up anything on wikipedia. Sends the first 10 sentences from wikipedia.")
    async def wiki(self, ctx, *, arg=None):
      try:
          if arg == None:
              await ctx.send("Please, specify what do you want me to search.")
          elif arg:
              msg = await ctx.send("Fetching...")
              start = arg.replace(" ", "")
              end = wikipedia.summary(start)
              await msg.edit(content = f"```py\n{end}\n```")
      except:
          try:
              start = arg.replace(" ", "")
              end = wikipedia.summary(start, sentences=10)
              await msg.edit(content = f"```py\n{end}\n```")
          except:
              await msg.edit(content = "Not found.")

    # timer
    global max_time
    max_time = 600
    time = ""
    mins = ""
    tr_start_user = ""
    msg = ""
    secondint = ""
  
    @commands.group(name = "timer",
                    aliases = ["tr", "countdown", "cd"],
                    brief = "Sets a timer",
                    help = "Sets a timer, which the bot will count down from and ping at the end.",
                    invoke_without_command=True,
                    case_insensitive=True)
    async def timer(self, ctx):
        await ctx.send_help(ctx.command)

    #timer start
    @timer.command(name="start",
                   aliases=["s"],
                   brief="Starts timer.",
                   help=f"Sets a timer for <seconds> and counts down from it(max {round(max_time/60, 2)}mins or {max_time}seconds). One timer per user at a time. Stop a running timer by using the {prefix}timer stop command.")
    @commands.max_concurrency(1, per=commands.BucketType.user, wait = False)
    async def _timer_start(self, ctx, seconds: int):
    
        global time
        time = round(seconds, 2)
        global mins
        mins = round(seconds/60, 2)
        global tr_start_user
        tr_start_user = ctx.author
        global msg
        msg = f"{ctx.author.mention} time's up! ({mins}mins or {seconds}seconds)"
        global secondint
        secondint = seconds

        class TimerStopView(discord.ui.View):
            @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
            async def confirm(_self, button: discord.ui.Button, interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    return
                _self.stop()
                global secondint
                global mins
                global time
                global msg
                msg = f"{ctx.author.mention} timer stopped! Stopped at {round(secondint/60, 2)}mins/{secondint}seconds **out of** {mins}mins/{time}seconds"
                secondint = 1
        view = TimerStopView()
        if seconds > max_time:
            await ctx.send(f"Timer can be set for max **{max_time/60}** minutes or **{max_time}** seconds")
        elif seconds <= 0:
            await ctx.send("Please input a positive whole number.")
        else:
            message = await ctx.send(f"Timer: {secondint} seconds", view=view)
        while secondint > 0:
            secondint -= 1
            if secondint == 0:
                await message.edit(content=msg, view=None)
                break
            await message.edit(content=f"Timer: {secondint} seconds.")
            await asyncio.sleep(1)
    
    @_timer_start.error
    async def timerstart_error(self,ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send("The time must be a positive whole number.")

    # timer stop
    @timer.command(name = "stop",
                    aliases = ["end"],
                    brief = "Stops running timer",
                    help = "Stops a running `timer` command."
                    )
    async def _timer_stop(self, ctx):
        try:
            global msg
            global mins
            global time
            global tr_start_user
            global secondint
            if secondint > 0 and ctx.author == tr_start_user:
                msg = f"{ctx.author.mention} timer stopped! Stopped at {round(secondint/60, 2)}mins/{secondint}seconds **out of** {mins}mins/{time}seconds"
                secondint = 1
                await ctx.message.add_reaction('👍')
            else:
                await ctx.send(f"There isn't a `timer` running that belongs to you.")
        except Exception as e:
            raise e
        
def setup(bot):
  bot.add_cog(Useful(bot))
