import io
from PIL import Image
import sys
import importlib

import numpy
import discord
from discord.ext import commands

from utils.logger import *


# this file is for general on_*() events stuff


class OnMsg(commands.Cog):
    def __init__(self, client):
        self.client: commands.Bot = client

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.client.per_channel_event_tracker.on_message(message)

        if message.content.strip() != '':
            print_debug_okcyan(f'Message from {message.author}: {message.content}')
        if isinstance(message.channel, discord.channel.DMChannel) or \
                message.author.id == self.client.user.id:
            return
        if self.client.user.mentioned_in(message) and message.mention_everyone is False:
            if message.reference is not None and message.reference.resolved is not None and \
                    message.reference.resolved.author == self.client.user:
                return
            await message.channel.send(f"My prefix is `{self.client.default_prefix}`")
        if len(message.attachments) == 0:
            return
        if message.author.id == 415130598777290753:
            return
        # if message.attachments[0].content_type.startswith("video") and not message.attachments[0].filename.endswith(".webm"):
        #     await message.delete()
        #     await message.channel.send(f"{message.author.mention} only webm videos allowed!!!!")
        # if message.guild.id == self.client.super_awesome_tv_shows_server_id and len(message.attachments) > 0:
        #     for img in message.attachments:
        #         if img.filename.split(".")[-1] not in ["png", "jpg", "jpeg", "webp"]:
        #             continue
        #         memory_image = io.BytesIO()
        #         await img.save(memory_image)
        #         save_img = Image.open(memory_image)
        #         # save_img = Image.frombytes("RGB", (img.width, img.height), memory_image.read())
        #         nupy_img = numpy.array(save_img)
        #         result = does_image_have_face(nupy_img, self.client.face_detector)
        #         if result:
        #             await message.channel.send(
        #                 "no real people alowed!!!!\n"
        #                 "https://tenor.com/view/violet-evergarden-real-people-anime-please-stop-posting-real-"
        #                 "people-gif-gif-26268050")
        # does_image_have_face(img.)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        pass

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        pass

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        pass

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.client.db.add_guild_to_db(guild)
        if guild.system_channel is not None:
            await guild.system_channel.send(f"hello nya!! my prefix is `{self.client.default_prefix}`!")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):  # TODO: welcome channel thing
        pass
        # await member.add_roles(discord.utils.get(member.guild.roles, id=1367336990252732507))

    @commands.Cog.listener()
    async def on_reload_cmd_success(self):
        for module in self.client.get_modules_to_reload(sys.modules):
            importlib.reload(module)


async def setup(client):
    await client.add_cog(OnMsg(client))
