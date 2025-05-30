import discord
from discord.ext import commands
import io
import time
import json
import importlib
import sys
import threading
import re
import asyncio
import subprocess
import os
import pathlib
import uuid

import yt_dlp

import utils.classes
import utils.funcs
# from utils.classes import GoogleImageResult


def get_max_attachment_size() -> int:
    return 10485760


async def get_message_attachments_string(message: discord.Message, client: commands.Bot) -> str:
    # called on message_delete and on_message
    # reuploads the image to the archive channel

    if len(message.attachments) == 0:
        return ""

    atchmnts_sizes = 0
    atchmnts_list = []
    for atchmnt in message.attachments:
        atchmnts_sizes += atchmnt.size
        if atchmnts_sizes >= get_max_attachment_size():
            break
        fp = io.BytesIO()
        await atchmnt.save(fp)
        fp.seek(0)
        atchmnts_list.append(discord.File(fp, filename=atchmnt.filename))
    new_msg = await client.snipe_image_channel.send(files=atchmnts_list)
    atchmnts_list_str = ""
    for new_atchmnt in new_msg.attachments:
        atchmnts_list_str += new_atchmnt.url + ", "

    # [:-2] to remove the last ", "
    return atchmnts_list_str[:-2]


class Fun(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.snipe_cooldowns = {}
        self.snipe_currently_uploading = []
        self.snipe_commands_deferred = {}
        self.snipe_cooldown_time_s = 6

        # self.current_image_embeds: dict[int, tuple[discord.Message, utils.classes.ICrawlerGoogleImageResult, discord.User]] = {}

    async def save_message(self, message: discord.Message, deleted=False) -> None:
        if await self.client.db.check_if_key_exists("message_id", message.id, "messages"):
            return
        channel_info = await self.client.db.select_channel(
            message.channel.id, ignore=True
        )
        if len(channel_info) == 0:
            pass
        else:
            if channel_info["ignore"]:
                return
        if message.channel.id not in self.snipe_currently_uploading:
            self.snipe_currently_uploading.append(message.channel.id)
        # find the server and category to place the images
        archiv_imgs_urls = await get_message_attachments_string(message, self.client)
        if len(archiv_imgs_urls.strip()) == 0 and len(message.content.strip()) == 0:
            return

        await self.client.db.insert_message_to_database(message, archiv_imgs_urls)
        if deleted:
            await self.client.db.insert_channel_to_database(message.channel, last_deleted_message_id=message.id)
        if message.channel.id in self.snipe_currently_uploading:
            self.snipe_currently_uploading.remove(message.channel.id)
            await self.send_deferred_snipe_commands()

    async def send_deferred_snipe_commands(self):
        the_keys = list(self.snipe_commands_deferred.keys())
        for channel_id in the_keys:
            if channel_id in self.snipe_currently_uploading:
                continue
            await self.snipe_commands_deferred[channel_id]["wait_message"].delete()
            self.snipe_cooldowns[self.snipe_commands_deferred[channel_id]["snipe_message"].author.id] = 0
            await self.snipe_script(self.snipe_commands_deferred[channel_id]["snipe_message"])
            del self.snipe_commands_deferred[channel_id]

    # called on message 'snipe' or {prefix}snipe
    async def snipe_script(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.author.id in self.snipe_cooldowns.keys():
            current_time = time.time()
            if current_time - self.snipe_cooldown_time_s < self.snipe_cooldowns[message.author.id]:
                return

        self.snipe_cooldowns[message.author.id] = time.time()

        channel_info = await self.client.db.select_channel(
            message.channel.id, snipe_webhook_url=True,
            last_deleted_message_id=True, ignore=True
        )

        if len(channel_info) == 0:
            await message.channel.send("no tracked deleted messages for this channel")
            return
        if channel_info["ignore"]:
            await message.channel.send("snipe command is disabled in this channel, sorry")
            return
        if channel_info["last_deleted_message_id"] is None:
            await message.channel.send("no tracked deleted messages for this channel")
            return
        if channel_info["last_deleted_message_id"] == 0:
            await message.channel.send("snipe command was purged, last deleted message was forgotten")
            return

        if message.channel.id in self.snipe_currently_uploading:
            wait_message = await message.channel.send("please wait, i havent saved the most recent message yet...")
            self.snipe_commands_deferred[message.channel.id] = {
                "wait_message": wait_message,
                "snipe_message": message
            }
            return

        if channel_info["snipe_webhook_url"] is None:
            webhook = await message.channel.create_webhook(name="_snipe")
            webhook_url = webhook.url
            await self.client.db.insert_channel_to_database(message.channel, snipe_webhook_url=webhook_url)
        else:
            webhook_url = channel_info["snipe_webhook_url"]
        message_info = await self.client.db.select_message(
            channel_info["last_deleted_message_id"], author_nick=True, author_pfp_url=True, content=True,
            attachments=True
        )
        if len(message_info) == 0:
            await self.client.public_discord_log(message.channel, message_info)
            await message.channel.send("no tracked deleted messages for this channel, message_info = 0")
            return

        guild_info = await self.client.db.select_guild(
            message.guild.id, extend_snipe_command_to_multiple_messages=True
        )

        if len(guild_info) == 0:
            extend_snipe_command_to_multiple_messages = False  # we just assume the default in this case
        else:
            extend_snipe_command_to_multiple_messages = guild_info["extend_snipe_command_to_multiple_messages"]

        if not extend_snipe_command_to_multiple_messages:
            message_content = discord.utils.escape_mentions(message_info['content'])
            if len(message_content) > 1500:
                # if message is longer than 1500 chars only post 1 attachment
                atchmnt = message_info["attachments"].split(", ")[0].strip()
            else:
                atchmnt = message_info["attachments"].strip()
            if len(message_content) + len(atchmnt) > 1999:  # 1999 because of the \n separating content and attachment
                message_content = message_content[:2000 - len(atchmnt) - 4]  # - 4 because "...\n"
                message_content += f"..."
            message_content += f"\n{atchmnt}"
            return await discord.Webhook.from_url(webhook_url, client=self.client).send(
                content=message_content,
                username=message_info["author_nick"],
                avatar_url=message_info["author_pfp_url"]
            )

        message_text = discord.utils.escape_mentions(message_info['content'])
        message_texts = []
        for i in range(0, len(message_text) + 2000, 2000):
            # only take the first 2000 chars
            cut_message = message_text[:2000]
            if cut_message.strip() == "":
                message_texts.append("")
            else:
                message_texts.append(str(message_text[:2000]))
            message_text = message_text[2000:]
        # add \n to the last element in list
        last_index = len(message_texts) - 1
        if len(message_texts[last_index]) == 2000:
            message_texts.append("")
            last_index += 1
        message_texts[last_index] = message_texts[last_index] + "\n"
        attachments = message_info["attachments"].split(", ")
        for attachment in attachments:
            if len(message_texts[-1]) + len(attachment) >= 2000:
                message_texts.append("")
            last_index = len(message_texts) - 1
            message_texts[last_index] = message_texts[last_index] + attachment + " "
        for i in message_texts:
            if i.strip() == "":
                continue
            await discord.Webhook.from_url(webhook_url, client=self.client).send(
                content=i,
                username=message_info["author_nick"],
                avatar_url=message_info["author_pfp_url"]
            )
        # requests.post(webhook_url, json.dumps(data), headers={"Content-Type": "application/json"})

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author == self.client.user or message.author.bot:
            return

        # here we save the most recent deleted message in that channel
        await self.save_message(message, deleted=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.client.user or message.author.bot:
            return

        # save all images to a channel
        # if len(message.attachments) > 0:
        #     await save_message(self.client, message)

        # snipes on message instead of command
        if message.content.lower() == 'snipe' or message.content.lower() == 'sniper' \
                or message.content.lower() == 'thnipe':
            await self.snipe_script(message)
        # await self.client.process_commands(message)

    @commands.command(
        brief='sends the last deleted message. do sex!snipe (disable/enable) to disable/enable in the channel',
        description="sends the last deleted message\n"
                    "do \"<prefix>snipe (disable/enable)\" to disable/enable in the channel\n"
                    "example: \"sex!snipe disable\" (snipe is now disabled from the entire channel)\n"
                    "default: enable\n\n"
                    f"do \"<prefix>snipe (disable/enable) multiple messages\" to disable/enable 1 snipe "
                    "message being able to be broken up into multiple messages in the server (for example, if "
                    "someone sends a message with more than 2000 characters)\n"
                    "example: <prefix>snipe enable multiple messages (a snipe message can now be broken up "
                    "into multiple messages)\n"
                    "default: disable"
    )
    async def snipe(self, ctx: commands.Context, *, disable=""):
        extra_options = ["disable", "enable", "disable multiple messages", "enable multiple messages", "purge"]
        if disable in extra_options:
            if disable == "purge":
                if not ctx.permissions.manage_messages:
                    return await ctx.send("you need manage messages permission to snipe purge")
                await self.client.db.insert_channel_to_database(ctx.channel, last_deleted_message_id=0)
                return await ctx.send("forgot the last deleted message")
            if not ctx.permissions.manage_channels:
                return await ctx.send("you need manage channels permission to disable the bot")
            if disable == "disable":
                await self.client.db.insert_channel_to_database(ctx.channel, ignore=True)
                return await ctx.send("disabled snipe command in this channel")
            if disable == "enable":
                await self.client.db.insert_channel_to_database(ctx.channel, ignore=False)
                return await ctx.send("enabled snipe command in this channel")
            if disable == "disable multiple messages":
                await self.client.db.insert_guild_to_database(
                    ctx.guild, extend_snipe_command_to_multiple_messages=False)
                return await ctx.send("disabled multiple snipe messages in this server")
            if disable == "enable multiple messages":
                await self.client.db.insert_guild_to_database(
                    ctx.guild, extend_snipe_command_to_multiple_messages=True)
                return await ctx.send("enabled multiple snipe messages in this channel")
        await self.snipe_script(ctx.message)

    # @commands.has_permissions(manage_messages=True)
    # @commands.command()
    # async def snipe_purge(self, ctx: commands.Context):
    #     await self.client.db.insert_channel_to_database(ctx.channel, last_deleted_message_id=0)

    class ImageButtons(discord.ui.View):
        message: discord.Message

        def __init__(self, *, timeout=180, r: utils.classes.ICrawlerGoogleImageResult, a: discord.User):
            super().__init__(timeout=timeout)
            self.r = r
            self.a = a

        async def on_timeout(self) -> None:
            self.clear_items()
            await self.message.edit(view=self)

        @staticmethod
        def generate_image_embed(r: utils.classes.ICrawlerGoogleImageResult, a: discord.User) -> discord.Embed:
            embed = discord.Embed(
                title="Google Image Result",
                color=discord.Color.random(),
            )
            embed.set_author(name=a.name, icon_url=a.avatar.url)
            embed.set_footer(text=f"page {r.image_pointer + 1}/{r.images_to_get}")
            embed.set_image(url=r.get_google_image_url())
            # print(f"current url: {r.get_google_image_url()}")
            return embed

        @discord.ui.button(label="<", style=discord.ButtonStyle.gray, disabled=True)
        async def left_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            for child in self.children:
                if type(child) == discord.ui.Button and child.label == ">":
                    child.disabled = False
            self.r.get_previous_image_url()
            if self.r.image_pointer == 0:
                button.disabled = True
            else:
                button.disabled = False
            await interaction.response.edit_message(embed=self.generate_image_embed(self.r, self.a), view=self)

        @discord.ui.button(label=">", style=discord.ButtonStyle.gray)
        async def right_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            for child in self.children:
                if type(child) == discord.ui.Button and child.label == "<":
                    child.disabled = False
            self.r.get_next_image_url()
            if self.r.image_pointer >= self.r.images_to_get + 1:
                button.disabled = True
            else:
                button.disabled = False
            await interaction.response.edit_message(embed=self.generate_image_embed(self.r, self.a), view=self)
            # await interaction.edit_original_response(embed=self.generate_image_embed(self.r, self.a))
            # await interaction.

    @commands.command(
        brief='search google for a picture',
        description="search google for a picture",
        aliases=["img"]
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def image(self, ctx, *, query):
        # query = " ".join(query)
        # print(query)

        r = utils.classes.ICrawlerGoogleImageResult(query)
        wait_timeout = 5
        wait_duration = 0.2
        while len(r.image_links) == 0:
            await asyncio.sleep(wait_duration)
            wait_timeout -= wait_duration
            if wait_timeout < 0:
                await ctx.send("timeout occurred while trying to get images")
                return
        r.get_next_image_url()
        # print(r.image_links)
        view = self.ImageButtons(r=r, a=ctx.author)
        m: discord.Message = await ctx.send(embed=self.ImageButtons.generate_image_embed(r, ctx.author), view=view)
        view.message = m
        # self.current_image_embeds[m.id] = (m, r, ctx.author)

    @commands.Cog.listener()
    async def on_reload_cmd_success(self):
        importlib.reload(utils.classes)

    @commands.command()
    async def sex(self, ctx):
        await ctx.send("uuoh,,, momgm ,., aomg  ,, i anw t  i,,  sex ,sexsexs  ex, !!! se RAPE RTAPE!! "
                       "RAPE   RAPE  YOU!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

    @commands.command(aliases=["dl"])
    async def download(self, ctx: commands.Context, url: str = ""):
        def do_download(ydl_inst, url, results):
            results.append(ydl_inst.extract_info(url))

        b4 = time.time()

        new_url = await utils.funcs.find_url_from_message(self.client, ctx.message)

        if new_url is None:
            await ctx.send(f"invalid url: {url}")
            return
        url = new_url
        confirmation = await ctx.send(f"downloading video at url {url}...")
        ytdlp_timeout = 120
        upload_timeout = 120
        ytdlp_opts = {
            # "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "restrictfilenames": True,
            "windowsfilenames": True,
            # "forcefilename": True,
            "max_filesize": 209715200,
            "format_sort": ["res:480", "+size", "+fps"],
            "quiet": False,
            "paths": {"home": "/tmp"},
            "postprocessors": [{"key": "FFmpegCopyStream"}],
            "postprocessor_args": {"copystream": ["-c:v", "libx264", "-c:a", "aac", "-f", "mp4"]}
        }
        with yt_dlp.YoutubeDL(ytdlp_opts) as ydl:
            result = ["cat"]
            dl_t = threading.Thread(target=do_download, args=(ydl, url, result))
            dl_t.start()
            while dl_t.is_alive():
                await asyncio.sleep(0.2)
                ytdlp_timeout -= 0.2
                if ytdlp_timeout < 0:
                    await ctx.send("timeout occurred while trying to download video")
                    return
            if len(result) == 1:
                await ctx.send(f"error downloading video from url {url}, got invalid result")
                return
            info = result[1]
            if not isinstance(info, dict) or "requested_downloads" not in info.keys() or \
                    len(info["requested_downloads"]) == 0 or "filepath" not in info["requested_downloads"][0].keys() or (
                    "filesize" not in info["requested_downloads"][0].keys() and "filesize_approx"
                    not in info["requested_downloads"][0].keys()):
                await ctx.send(f"error downloading video from url {url}, got invalid info")
                return
            filepath = info["requested_downloads"][0]["filepath"]
            filesize = os.path.getsize(filepath)
            # if "filesize" not in info["requested_downloads"][0].keys():
            #     filesize = info["requested_downloads"][0]["filesize_approx"]
            # else:
            #     filesize = info["requested_downloads"][0]["filesize"]
            filename = info["requested_downloads"][0]["filename"]
        # print(ctx.guild.filesize_limit)
        # print(filesize)

        # if ctx.guild.filesize_limit <= filesize:  i think discord.py has a bug with this
        if 10000000 <= filesize:
            video_url = await self.client.s3.upload_file_to_bucket(
                pathlib.Path(filepath),
                f"meowbot/{str(uuid.uuid4()).replace('-', '')}_{pathlib.Path(filename).name}"
            )
            # p = subprocess.Popen(["/home/meow/.local/bin/jesterupload", filepath, "temp"], stdout=subprocess.PIPE,
            #                      stderr=subprocess.PIPE)
            # r = p.poll()
            #
            # # print(r)
            # while r is None:
            #     r = p.poll()
            #     upload_timeout -= .2
            #     await asyncio.sleep(.2)
            #     if upload_timeout <= 0:
            #         p.terminate()
            #         await ctx.send("timeout occurred when uploading file to server")
            #         return
            # if p.returncode != 0:
            #     await ctx.send(f"error uploading file to server")
            #     return
            # video_url, _ = p.communicate()
            # if isinstance(video_url, bytes):
            #     video_url = video_url.decode("utf-8")
            await confirmation.delete()
            await ctx.reply(f"took {time.time() - b4} seconds\n"
                            f"{video_url}")
            return
        await confirmation.delete()
        await ctx.reply(file=discord.File(filepath, filename=filename))

    @commands.Cog.listener()
    async def on_reload_cmd_success(self):
        for module in self.client.get_modules_to_reload(sys.modules):
            importlib.reload(module)


async def setup(client: commands.Bot):
    await client.add_cog(Fun(client))
