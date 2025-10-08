import sys
import importlib
import ast
import operator

import discord
from discord.ext import commands

from utils.classes import safe_math_evaluator


class Misc(commands.Cog):
    def __init__(self, client):
        self.client: commands.Bot = client

        # importlib.reload(classes)

    @commands.command()
    async def ping(self, ctx):
        await ctx.send(f"pong! `{round(self.client.latency * 1000)}ms`")

    @commands.command(brief="get the invite for the bot")
    async def invite(self, ctx):
        await ctx.send(f"use this link to invite me!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
                       f"https://discord.com/oauth2/authorize?client_id={self.client.user.id}"
                       f"&permissions=1759218604441599&integration_type=0&scope=bot")

    @commands.command()
    async def about(self, ctx):
        await ctx.send("hello i amm bot craeted by mmeowmeow\n"
                       "code is now rel eased !!! https://github.com/meow6969/superawesometvshowbot ")

    @commands.command()
    async def pfp(self, ctx, user: discord.Member = None):
        if user is None:
            await ctx.send(self.client.user.avatar.url)
            return
        await ctx.send(user.avatar.url)

    @commands.command()
    async def nyanya(self, ctx):
        await ctx.send("<a:FUMOPENGUIINDANCE:1423493655217569973>")

    @commands.command()
    async def math(self, ctx, *, math_expression):
        try:
            r = safe_math_evaluator.eval_math(math_expression)
        except Exception as e:
            await ctx.send(f"this math expression has caused an error!\n"
                           f"```{e}```")
            return
        await ctx.send(f"`{r}`")
        return

    @commands.Cog.listener()
    async def on_reload_cmd_success(self):
        for module in self.client.get_modules_to_reload(sys.modules):
            importlib.reload(module)


async def setup(client):
    await client.add_cog(Misc(client))
