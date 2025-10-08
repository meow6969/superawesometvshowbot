import sys
import importlib
import json
import traceback
import re
from datetime import datetime, timedelta
from dateutil import parser, tz
import math
from io import StringIO
from html.parser import HTMLParser

import aiohttp
import operator

import discord
from discord.ext import commands, tasks

from utils.classes import DatabaseUser
from utils.logger import print_debug_okgreen


# TODO: write a thing that checks ur canvas calendar every day for what stuff u need to do
# TODO: write a command dat shows both ur late assignents and future assignents


def convert_canvas_timestamp(timestamp: str) -> datetime:
    # a = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")

    # for some reason datetime.strptime return ur timer zone but dateutils.parser.parse returns da utc
    # so fricked up
    return parser.parse(timestamp)


# https://stackoverflow.com/questions/753052/strip-html-from-strings-in-python
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


# https://stackoverflow.com/questions/947776/strip-all-non-numeric-characters-except-for-from-a-string-in-python#947789
non_decimal = re.compile(r'[^\d.]+')


def strip_non_numbers(a: str) -> int:
    return int(non_decimal.sub('', a))


# i will group all of the information we will want to display to the user in a class so that we can collect it all in
# a bucket then later format it and shorten certain parts to stay with in 2000 character limit
class CanvasNotification:
    header: str = "No header supplied."
    title: str = "No title supplied."
    url: str = "No url supplied."
    content: str = "No content supplied."
    footer: str = "No footer supplied."
    course_id: int | None = None
    course_info: dict | None = None
    # timestamp: str = "No timestamp supplied."

    def __str__(self):
        char_limit = 1990
        link_text = self.header
        if self.course_info is not None:
            link_text = f"{self.course_info['name']} -- {link_text}"
        first_part = f"[{link_text}]({self.url})"
        char_limit -= len(first_part)
        # if self.timestamp != "No timestamp supplied.":
        #     last_part = f"<t:{int(convert_canvas_timestamp(self.timestamp).timestamp())}:F>"
        # else:
        #     last_part = self.timestamp
        if self.footer == "No footer supplied.":
            last_part = ""
        else:
            last_part = f"###{self.footer}"
        char_limit -= len(last_part)
        title_part = f"# {self.title}"
        if len(title_part) > math.floor(char_limit / 2):
            title_part = f"{title_part[:math.floor(char_limit / 2) - 3]}..."
        middle_part = f"{self.content}"
        if len(middle_part) > char_limit:
            middle_part = f"{middle_part[:math.floor(char_limit / 2) - 3]}..."
        return (f"{first_part}\n"
                f"{title_part}\n"
                f"{middle_part}\n"
                f"{last_part}")

    def __repr__(self):
        return self.__str__()


def datetime_to_discord(d: datetime) -> str:
    return f"<t:{int(d.timestamp())}:F>"


def canvas_date_to_discord(d: str) -> str:
    return datetime_to_discord(convert_canvas_timestamp(d))


async def make_canvas_request(endpoint: str, hostname: str, token: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://{hostname}/api/v1/{endpoint}",
                               headers={"Authorization": f"Bearer {token}"}) as r:
            return await r.json()


class Canvas(commands.Cog):
    hostname_check = re.compile(r"^[\w.-]+$")
    # so this will hold collected information about the canvas courses
    # will be indexed via [hostname][course_id] to get the course information
    canvas_course_info_collection: dict[str, dict[int, dict]]

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

    @commands.command(hidden=False)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def canvas_set_hostname(self, ctx, hostname):
        a = await self.validate_canvas_hostname(hostname)
        if a:
            await ctx.send(a)
            return
        await self.client.db.update_user_canvas_hostname(ctx.author, hostname)
        await ctx.send("host name save!!")

    @commands.command(hidden=False)
    @commands.cooldown(1, 1, commands.BucketType.user)
    async def canvas_set_token(self, ctx, token: str):
        if token is None or token.strip() == "" or len(token) < 10:  # i think all tokens are prety long i?? hav no idea
            await ctx.send("token is invalid!!! not valid token")
            return

        await self.client.db.update_user_canvas_token(ctx.author, token)
        await ctx.send("token saved  !!")

    @staticmethod
    async def get_canvas_user(hostname: str, token: str) -> dict:
        return await make_canvas_request("users/self", hostname, token)
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(f"https://{hostname}/api/v1/users/self",
        #                            headers={"Authorization": f"Bearer {token}"}) as r:
        #         return await r.json()

    @commands.command(brief="get the bot to check if your canvas details are good", hidden=False)
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
    async def get_canvas_notifications(canvas_hostname: str, canvas_token: str) -> list[dict] | None:
        return await make_canvas_request("users/self/activity_stream", canvas_hostname, canvas_token)
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(f"https://{canvas_hostname}/api/v1/users/self/activity_stream",
        #                            headers={"Authorization": f"Bearer {canvas_token}"}) as r:
        #         if r.status != 200:
        #             return None
        #         return await r.json()

    @staticmethod
    async def get_canvas_calendar(canvas_hostname: str, canvas_token: str) -> list[dict] | None:
        return await make_canvas_request("users/self/upcoming_events", canvas_hostname, canvas_token)
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(f"https://{canvas_hostname}/api/v1/users/self/upcoming_events", )

    @staticmethod
    async def get_canvas_course(course_id: int, canvas_hostname: str, canvas_token: str) -> list[dict] | None:
        return await make_canvas_request(f"courses/{course_id}", canvas_hostname, canvas_token)

    async def pretty_print_canvas_notification(self, notif: dict, hostname: str, token: str) -> str:
        if "error" in notif:
            return (f"canvas notification error!\n"
                    f"```{json.dumps(notif, indent=2)}```")

        a = CanvasNotification()
        # noinspection PyBroadException
        try:
            # if "updated_at" in notif:
            #     a.timestamp = notif["updated_at"]
            if "html_url" in notif:
                a.url = notif["html_url"]

            match notif["type"]:
                case "Message":
                    a.header = "New canvas message!"
                    # a.url = notif["url"]
                    a.title = strip_tags(notif["title"])
                    a.content = strip_tags(notif["message"])
                    a.course_id = notif["course_id"]
                case "DiscussionTopic":
                    a.header = "New canvas discussion topic!"
                    # a.url = notif["html_url"]
                    a.title = strip_tags(notif["title"])
                    a.content = strip_tags(notif["message"])
                    a.course_id = notif["course_id"]
                case "Submission":
                    if notif["submission_type"] is not None and "quiz" in notif["submission_type"]:
                        a.header = "New canvas quiz!"
                    else:
                        a.header = "New canvas assignment!"
                    # a.url = notif["html_url"]
                    a.title = strip_tags(notif["title"])
                    a.content = strip_tags(notif["assignment"]["description"])
                    a.footer = f"due by: {canvas_date_to_discord(notif['assignment']['due_at'])}"
                    a.course_id = notif["course"]["course_id"]
                    a.course_info = notif["course"]
                    if hostname not in self.canvas_course_info_collection:
                        self.canvas_course_info_collection[hostname] = {}
                    if a.course_id not in self.canvas_course_info_collection[hostname]:
                        self.canvas_course_info_collection[hostname][a.course_id] = a.course_info
                case "Conversation":
                    a.header = "New canvas inbox message!"
                    target_message = notif['latest_messages'][0]
                    a.title = notif["title"]
                    a.content = f"{strip_tags(target_message['message'])}"
                    a.course_id = target_message["course_id"]
                    # a.url = notif["html_url"]
                case "Announcement":
                    a.header = "New canvas announcement!"
                    a.title = strip_tags(notif["title"])
                    a.content = strip_tags(notif["message"])
                    a.course_id = notif["course_id"]
                case "assignment":
                    a.header = "Canvas assignment due in 24 hrs!"
                    a.title = strip_tags(notif["title"])
                    if "description" not in notif or not isinstance(notif["description"], str):
                        notif["description"] = ""
                    a.content = strip_tags(notif["description"])
                    a.footer = f"due by: {canvas_date_to_discord(notif['assignment']['due_at'])}>"
                    a.course_id = notif["assignment"]["course_id"]
                case _:
                    return f"```{json.dumps(notif, indent=2)[:1990]}```"
        except Exception as _:
            return (f"error occurred parsing message!\n"
                    f"{traceback.format_exc()}"[:1990])
        print_debug_okgreen(json.dumps(notif, indent=2))
        if a.course_id is not None and a.course_info is None:
            a.course_info = await self.get_canvas_course(a.course_id, hostname, token)
        return str(a)

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
                notifs = await self.get_canvas_notifications(user.canvas_hostname, user.canvas_token)
                if notifs is None or type(notifs) != list or len(notifs) == 0:
                    continue
                calendar_notifs = await self.get_canvas_calendar(user.canvas_hostname, user.canvas_token)
                if calendar_notifs is None or type(notifs) != list or len(calendar_notifs) == 0:
                    continue
                tomorrow = datetime.now() + timedelta(days=1)
                for i in calendar_notifs:
                    if i["type"] != "assignment":  # just skip it i guess idk
                        continue
                    due = convert_canvas_timestamp(i["assignment"]["due_at"])

                    if due.timestamp() < tomorrow.timestamp():
                        # the default id has a thing preceeding it like "assignment_xxxxxxx" so i remmmove dat stuff
                        # cause we need a int for the next part
                        # i think all ids are unique,. not sure tho
                        i["id"] = strip_non_numbers(i["id"])
                        notifs.append(i)

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
                # await dm_channel.send(f"```{json.dumps(notification, indent=2)[:1985]}```")
                await dm_channel.send(await self.pretty_print_canvas_notification(
                    notification, user.canvas_hostname, user.canvas_token))
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

    @staticmethod
    async def get_overdue_assignments(hostname: str, token: str) -> list[dict]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://{hostname}/api/v1/users/self/missing_submissions",
                                   headers={"Authorization": f"Bearer {token}"}) as r:
                if r.status != 200:
                    return None
                return await r.json()

    @staticmethod
    async def get_upcoming_events(hostname: str, token: str) -> list[dict]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://{hostname}/api/v1/users/self/upcoming_events",
                                   headers={"Authorization": f"Bearer {token}"}) as r:
                if r.status != 200:
                    return None
                return await r.json()

    @commands.command()
    async def canvas_show_assignments(self, ctx):
        user_data = await self.client.db.select_user(ctx.author.id, canvas_token=True, canvas_hostname=True,
                                                     canvas_valid=True)
        if not user_data["canvas_valid"]:
            return
        if user_data["canvas_hostname"] is None or user_data["canvas_hostname"] == "":
            return
        if user_data["canvas_token"] is None or user_data["canvas_token"] == "":
            return

        overdue_assignments = await self.get_overdue_assignments(user_data["canvas_hostname"], user_data["canvas_token"])
        if type(overdue_assignments) != list or "error" in overdue_assignments:
            print(overdue_assignments)
            await ctx.send("error getting overdue assignments")
            return
        upcoming_events = await self.get_upcoming_events(user_data["canvas_hostname"], user_data["canvas_token"])
        if type(upcoming_events) != list or "error" in upcoming_events:
            await ctx.send("error getting upcoming assignments")
            return
        upcoming_assignments: list[dict] = []
        for a in upcoming_events:
            if a["type"] != "assignment":
                continue
            upcoming_assignments.append(a)
        await ctx.send(f"u have {len(upcoming_assignments)} upcoming assignments, "
                       f"and {len(overdue_assignments)} overdue assignments")

    @tasks.loop(minutes=10)
    async def canvas_notify(self):
        await self.do_canvas_notify()

    @commands.Cog.listener()
    async def on_reload_cmd_success(self):
        for module in self.client.get_modules_to_reload(sys.modules):
            importlib.reload(module)


async def setup(client):
    await client.add_cog(Canvas(client))
