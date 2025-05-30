import importlib
import json
import os

import git
import discord
from discord.ext import commands
import aioboto3

import utils.classes
# from cogs.utils.logger import *
# from cogs.utils import classes
# from cogs.utils import funcs
from utils.logger import *
from utils import classes
from utils import funcs


async def secret_discord_log(_client: commands.Bot, message, underlined=False, bold=False):
    print_debug_fail(json.dumps(message), underlined=underlined, bold=bold)
    super_important_logs_channel = _client.get_channel(_client.super_important_logs_channel_id)

    await super_important_logs_channel.send(json.dumps(message))


async def public_discord_log(_channel: discord.TextChannel, message, underlined=False, bold=False):
    print_debug_warning("public_discord_log: " + json.dumps(message), underlined=underlined, bold=bold)
    await _channel.send(json.dumps(message))


with open("config.json") as meowf:
    meow = json.load(meowf)
    default_prefix = meow["default_prefix"]
    debug = meow["debug"]
    debug_default_prefix = meow["debug_default_prefix"]
    debug_database_location = meow["debug_database_location"]

bot_intents = discord.Intents.default()
bot_intents.members = True
bot_intents.message_content = True

if debug:
    default_prefix = debug_default_prefix
    database_location = debug_database_location

# noinspection PyTypeChecker
client = commands.Bot(
    command_prefix=funcs.get_prefix,
    intents=bot_intents,
    fetch_offline_members=True,
    case_insensitive=True
)
client.debug = debug
client.default_prefix = default_prefix
# client.face_detector = MTCNN(device="GPU:0")

with open("config.json") as meowf:
    meow = json.load(meowf)
    client.owners = meow["owners"]
    client.illegal_prefix_characters = meow["illegal_prefix_characters"]
    client.database_location = meow["database_location"]
    client.super_important_logs_channel_id = meow["super_important_logs_channel_id"]
    client.snipe_image_channel_id = meow["snipe_image_channel_id"]
    client.git_pull_on_reload_command = meow["git_pull_on_reload_command"]
    client.super_awesome_tv_shows_server_id = meow["super_awesome_tv_shows_server"]
    client.aws_s3_config = meow["aws_s3_config"]

    def get_modules_to_reload(the_modules: dict) -> list:
        modules_to_reload = []
        for module in the_modules.keys():
            fr_module = the_modules[module]
            if "__file__" not in dir(fr_module):
                continue
            if fr_module.__file__ is None:
                continue
            if "__package__" not in dir(fr_module):
                continue
            if "site-packages" in fr_module.__file__:
                continue
            if "superawesometvshowbot" not in fr_module.__file__:
                continue
            if "utils" not in fr_module.__file__:
                continue
            modules_to_reload.append(fr_module)
        return modules_to_reload
    client.get_modules_to_reload = get_modules_to_reload

client.secret_discord_log = secret_discord_log
client.public_discord_log = public_discord_log


@client.event
async def on_ready():
    # cogs
    cogs = os.listdir('./cogs/')
    for cog in cogs:
        cog_list = cog.split('.')
        if cog_list[len(cog_list) - 1] == 'py':
            await client.load_extension(f'cogs.{cog_list[0]}')

    print_debug_okgreen(f'Logged on as {client.user}!')

    # https://docs.vultr.com/how-to-use-vultr-object-storage-in-python
    client.s3 = await utils.classes.AwsS3Manager.setup_new(client.aws_s3_config)

    client.db = classes.Database(client, client.database_location)
    await client.db.create()
    print_debug_okgreen("database successfully loaded")

    client.snipe_image_channel = client.get_channel(client.snipe_image_channel_id)

    client.per_channel_event_tracker = utils.classes.PerChannelEventTracker()
    await client.per_channel_event_tracker.add_new_event_tracker(utils.classes.UrlEventTracker(client))
    print_debug_okgreen("event tracker successfully loaded")

    if client.debug:
        print_debug_okgreen(f'loaded debug tv show bot')
    else:
        print_debug_okgreen(f'loaded tv show bot')


@client.event
async def on_reload_cmd_success():
    for module in client.get_modules_to_reload(sys.modules):
        importlib.reload(module)


with open("config.json") as meow:
    if client.debug:
        token = json.load(meow)["debug-token"]
    else:
        token = json.load(meow)["token"]

# client = MyClient()
client.run(token)
