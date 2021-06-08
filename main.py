import asyncio
import os
import discord
from replit import db
from keep_alive import keep_alive
from discord.ext import commands
from pretty_help import DefaultMenu, PrettyHelp

prefix = '_'

def get_prefix(bot, message):

    prefixes = [prefix, '>>']
    if not message.guild:
        return prefix
    return commands.when_mentioned_or(*prefixes)(bot, message)

menu = DefaultMenu("◀️", "▶️", "❌", active_time = 60)

embed_colour = 0xf1c40f

cmd_cd = 2

log_channel = 837542790119686145

bot = commands.AutoShardedBot(
                   shard_count=2,
                   command_prefix=get_prefix, 
                   owner_id=267550284979503104,
                   case_insensitive=True, 
                   help_command=PrettyHelp(),
                   self_bot=False)

bot.help_command = PrettyHelp(menu=menu, color=embed_colour, sort_command=False, show_index=True)

for filename in os.listdir('./cogs'):
  if filename.endswith(".py"):
    bot.load_extension(f'cogs.{filename[:-3]}')

keep_alive()
my_secret = os.environ['botTOKEN']
bot.run(my_secret, bot = True)
