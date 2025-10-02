import sys
import importlib
import json
import traceback

import aiohttp
import operator

import discord
from discord.ext import commands, tasks

from utils.classes import DatabaseUser


class Misc(commands.Cog):
    def __init__(self, client):
        self.client: commands.Bot = client
        self.canvas_notify.start()

    def cog_unload(self):
        self.canvas_notify.cancel()

    @staticmethod
    async def get_canvas_notifications(canvas_token: str, canvas_hostname: str) -> list[dict] | None:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://{canvas_hostname}/api/v1/users/self/activity_stream",
                                   headers={"Authorization": f"Bearer {canvas_token}"}) as r:
                if r.status != 200:
                    return None
                return await r.json()

    @tasks.loop(minutes=5)
    async def canvas_notify(self):
        if not hasattr(self.client, "db"):
            return

        users: list[DatabaseUser] = self.client.db.get_all_users_info()
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
                await dm_channel.send(json.dumps(notification, indent=2)[:1999])
                notified_list.append(notification["id"])
                notified_modified = True
            if notified_modified:
                new_notified = "|".join(notified_list)
                await self.client.db.update_user_canvas_notified(user.user_id, new_notified)

    @commands.Cog.listener()
    async def on_reload_cmd_success(self):
        for module in self.client.get_modules_to_reload(sys.modules):
            importlib.reload(module)


async def setup(client):
    await client.add_cog(Misc(client))
