import sys
import importlib
import json
import traceback
import re

import aiohttp
import operator

import discord
from discord.ext import commands, tasks

from utils.classes import DatabaseUser


class Canvas(commands.Cog):
    hostname_check = re.compile(r"^[\w.-]+$")

    def __init__(self, client):
        self.client: commands.Bot = client
        self.canvas_notify.start()
        self.notifying = False

    def cog_unload(self):
        self.canvas_notify.cancel()

    async def validate_canvas_hostname(self, hostname: str) -> str | None:
        if not self.hostname_check.match(hostname):
            return "host name is not valid!!! NOT petan  !!!! !"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://{hostname}/login/oauth2/auth") as r:
                    try:
                        meow = await r.json()
                    except aiohttp.client_exceptions.ContentTypeError:
                        return "host name is not canvas host name !!!!!! "
                    if "error" not in meow:
                        return "host namme is not canvas host name!!! no error !!"
                    if meow["error"] != "invalid_client":
                        return "host namme is not canvas host name!!! not invalid client!!"
        except aiohttp.ClientError as e:
            print(type(e))
            return f"host name {hostname} is not valid!!! NOT connect  !!!! ! {e}"
        return None

    @commands.command(hidden=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def canvas_set_hostname(self, ctx, hostname):
        a = await self.validate_canvas_hostname(hostname)
        if a:
            await ctx.send(a)
            return
        await self.client.db.update_user_canvas_hostname(ctx.author, hostname)
        await ctx.send("host name save!!")

    @commands.command(hidden=True)
    @commands.cooldown(1, 1, commands.BucketType.user)
    async def canvas_set_token(self, ctx, token: str):
        if token is None or token.strip() == "" or len(token) < 10:  # i think all tokens are prety long i?? hav no idea
            await ctx.send("token is invalid!!! not valid token")
            return

        await self.client.db.update_user_canvas_token(ctx.author, token)
        await ctx.send("token saved  !!")

    @staticmethod
    async def get_canvas_user(hostname, token) -> dict:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://{hostname}/api/v1/users/self",
                                   headers={"Authorization": f"Bearer {token}"}) as r:
                return await r.json()

    @commands.command(brief="get the bot to check if your canvas details are good", hidden=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def canvas_verify_credentials(self, ctx):
        a: dict = await self.client.db.select_user(ctx.author.id, canvas_token=True, canvas_hostname=True)
        if len(a) == 0:
            await ctx.send("u arent in the database!!! invalid")
            return
        hostname: str = a["canvas_hostname"]
        token: str = a["canvas_token"]
        if hostname is None:
            hostname = ""

        b = await self.validate_canvas_hostname(hostname)
        if b:
            await ctx.send(b)
            return
        c = await self.get_canvas_user(hostname, token)
        if "error" in c or "name" not in c:
            await ctx.send(f"token is wrong !!! NO GOOD\n"
                           f"```{json.dumps(c, indent=2)}```")
        await self.client.db.update_user_canvas_valid(ctx.author, True)

    @commands.command(brief="remove all canvas data about you from bot", hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def canvas_remove_data(self, ctx):
        if not await self.client.db.check_if_key_exists("user_id", ctx.author.id, "users"):
            await ctx.send("u arenrt  in the data base")
            return
        await self.client.db.update_table_set_where("users", {
            "canvas_token": None,
            "canvas_hostname": None,
            "canvas_already_notified": "",
            "canvas_valid": False
        }, "user_id", ctx.author.id)
        await ctx.send("canvas data removed !!! ")

    @staticmethod
    async def get_canvas_notifications(canvas_token: str, canvas_hostname: str) -> list[dict] | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://{canvas_hostname}/api/v1/users/self/activity_stream",
                                   headers={"Authorization": f"Bearer {canvas_token}"}) as r:
                if r.status != 200:
                    return None
                return await r.json()

    async def baka_notify(self):
        users: list[DatabaseUser] = await self.client.db.get_all_users_info()
        for user in users:
            if not user.canvas_valid:
                continue
            if user.canvas_hostname is None or user.canvas_hostname == "":
                continue
            if user.canvas_token is None or user.canvas_token == "":
                continue
            disc_user = self.client.get_user(user.user_id)
            if disc_user is None:
                continue
            try:
                dm_channel = await disc_user.create_dm()
            except discord.errors.HTTPException:
                continue

            # noinspection PyBroadException
            try:
                notifs = await self.get_canvas_notifications(user.canvas_token, user.canvas_hostname)
                if notifs is None or type(notifs) != list or len(notifs) == 0:
                    continue
            except Exception as _:
                traceback.print_exc()
                print(f"AAAAAAHHHH")
                continue
                # hehe
                # TODO: make like idk aa uhh like autommmatically make the peoples like uhh   thing like ... not valid
            if user.canvas_already_notified is None:
                user.canvas_already_notified = ""
            notified_list = []
            notified_modified = False
            for i in user.canvas_already_notified.split("|"):
                try:
                    notified_list.append(int(i))
                except ValueError:
                    continue
            for notification in notifs:
                if "id" not in notification:
                    continue
                if notification["id"] in notified_list:
                    continue
                await dm_channel.send(f"```{json.dumps(notification, indent=2)[:1985]}```")
                notified_list.append(notification["id"])
                notified_modified = True
            if notified_modified:
                new_notified = "|".join(list(map(str, notified_list)))
                await self.client.db.update_user_canvas_notified(user, new_notified)

    async def do_canvas_notify(self):
        if not hasattr(self.client, "db"):
            return
        if self.notifying:
            return
        self.notifying = True
        try:
            await self.baka_notify()
        except Exception:
            traceback.print_exc()
        self.notifying = False

    @commands.command(hidden=True)
    async def notify_canvas(self, ctx):
        if ctx.author.id not in self.client.owners:
            return
        await self.do_canvas_notify()
        await ctx.send("done doing canvas notify !!!!!")

    @tasks.loop(minutes=10)
    async def canvas_notify(self):
        await self.do_canvas_notify()

    @commands.Cog.listener()
    async def on_reload_cmd_success(self):
        for module in self.client.get_modules_to_reload(sys.modules):
            importlib.reload(module)


async def setup(client):
    await client.add_cog(Canvas(client))
