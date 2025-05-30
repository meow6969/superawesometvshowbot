import asyncio
import io
import json
import contextlib
import subprocess
import uuid
import pathlib
import stat
import git
import os
import importlib
import sys
import re

import aiohttp
import discord
from discord.ext import commands

import utils.funcs
from utils.logger import *
from utils import funcs
from utils import classes


class Moderator(commands.Cog):
    client: commands.Bot
    discord_supported_markdown_languages = [  # found by doing ctrl+shift+f search in chrome dev tools for string "zsh"
        "1c", "4d", "abnf", "accesslog", "ada", "arduino", "ino", "armasm", "arm", "avrasm", "actionscript", "as",
        "ass", "ssa", "alan", "ansi", "i", "log", "ln", "angelscript", "asc", "apache", "apacheconf", "applescript",
        "osascript", "arcade", "asciidoc", "adoc", "aspectj", "autohotkey", "autoit", "awk", "mawk", "nawk", "gawk",
        "bash", "sh", "zsh", "basic", "bbcode", "blade", "bnf", "brainfuck", "bf", "csharp", "cs", "c", "h", "cpp",
        "hpp", "cc", "hh", "c++", "h++", "cxx", "hxx", "cal", "cos", "cls", "cmake", "cmake.in", "coq", "csp", "css",
        "csv", "capnproto", "capnp", "chaos", "kaos", "chapel", "chpl", "cisco", "clojure", "clj", "coffeescript",
        "coffee", "cson", "iced", "cpc", "crmsh", "crm", "pcmk", "crystal", "cr", "cypher", "d", "dns", "zone",
        "bind", "dos", "bat", "cmd", "dart", "delphi", "dpr", "dfm", "pas", "pascal", "freepascal", "lazarus", "lpr",
        "lfm", "diff", "patch", "django", "jinja", "dockerfile", "docker", "dsconfig", "dts", "dust", "dst", "dylan",
        "ebnf", "elixir", "ex", "elm", "erlang", "erl", "extempore", "xtlang", "xtm", "fsharp", "fs", "fix", "fortran",
        "f90", "f95", "gcode", "nc", "gams", "gms", "gauss", "gss", "godot", "gdscript", "gherkin", "gn", "gni", "go",
        "golang", "gf", "golo", "gololang", "gradle", "groovy", "xml", "html", "xhtml", "rss", "atom", "xjb", "xsd",
        "xsl", "plist", "svg", "http", "https", "haml", "handlebars", "hbs", "html.hbs", "html.handlebars", "haskell",
        "hs", "haxe", "hx", "hy", "hylang", "ini", "toml", "inform7", "i7", "irpf90", "json", "java", "jsp",
        "javascript", "js", "jsx", "jolie", "iol", "ol", "julia", "julia-repl", "kotlin", "kt", "tex", "leaf",
        "lean", "lasso", "ls", "lassoscript", "less", "ldif", "lisp", "livecodeserver", "livescript", "lock", "ls",
        "lua", "makefile", "mk", "mak", "make", "markdown", "md", "mkdown", "mkd", "mathematica", "mma", "wl",
        "matlab", "maxima", "mel", "mercury", "mirc", "mrc", "mizar", "mojolicious", "monkey", "moonscript", "moon",
        "n1ql", "nsis", "never", "nginx", "nginxconf", "nim", "nimrod", "nix", "ocl", "ocaml", "ml", "objectivec",
        "mm", "objc", "obj-c", "obj-c++", "objective-c++", "glsl", "openscad", "scad", "ruleslanguage", "oxygene",
        "pf", "pf.conf", "php", "php3", "php4", "php5", "php6", "php7", "parser3", "perl", "pl", "pm", "plaintext",
        "txt", "text", "pony", "pgsql", "postgres", "postgresql", "powershell", "ps", "ps1", "processing", "prolog",
        "properties", "proto", "protobuf", "puppet", "pp", "python", "py", "gyp", "profile", "python-repl", "pycon",
        "k", "kdb", "qml", "r", "cshtml", "razor", "razor-cshtml", "reasonml", "re", "redbol", "rebol", "red",
        "red-system", "rib", "rsl", "graph", "instances", "robot", "rf", "rpm-specfile", "rpm", "spec", "rpm-spec",
        "specfile", "ruby", "rb", "gemspec", "podspec", "thor", "irb", "rust", "rs", "SAS", "sas", "scss", "sql",
        "p21", "step", "stp", "scala", "scheme", "scilab", "sci", "shexc", "shell", "console", "smali", "smalltalk",
        "st", "sml", "ml", "solidity", "sol", "stan", "stanfuncs", "stata", "iecst", "scl", "structured-text",
        "stylus", "styl", "subunit", "supercollider", "sc", "srt", "svelte", "swift", "tcl", "tk", "terraform",
        "tf", "hcl", "tap", "thrift", "tp", "tsql", "ttml", "twig", "craftcms", "typescript", "ts", "tsx",
        "unicorn-rails-log", "vbnet", "vb", "vba", "vbscript", "vbs", "vhdl", "vala", "verilog", "v", "vim", "vtt",
        "axapta", "x++", "x86asm", "xl", "tao", "xquery", "xpath", "xq", "yml", "yaml", "zephir", "zep"
    ]
    # this should match pretty 1:1 with how discord does it # why am i so bad at this
    exec_cmd_remove_code_extras = re.compile(
        f"(\\A[\\w =,-]*(`{{3}}(?:(?:("
        f"{re.sub('([+.])', f'{chr(92)}{chr(92)}{chr(92)}1', '|'.join(discord_supported_markdown_languages))}"
        f"|(?:))(?=\\n))|(?:))|(?<!`)`{{1,2}}(?!`))(?:[\\s]|(?:))*)|(?:(?:[\\s]|(?:))*(`{{0,3}}?)[\\s]*\\Z)"
    )
    exec_py_options = ["return", "timeout"]
    exec_cmd_options = ["return", "timeout"]
    exec_cmd_get_options_regex = re.compile(f"-{{0,2}}(?:({'|'.join(exec_cmd_options)}))=(\\w+)")
    exec_py_get_options_regex = re.compile(f"-{{0,2}}(?:({'|'.join(exec_py_options)}))=(\\w+)")

    def __init__(self, client):
        self.client = client

    @commands.command(brief='clears the channels pins',
                      description='clears the channels pins and posts them all in a seperate channel', hidden=True)
    @commands.has_permissions(administrator=True)
    async def archive_pins(self, ctx):  # TODO: redo this and make it archive pins immediately when pinning them
                                        # TODO: oh god this is really bad
        if ctx.message.guild.id != 690036880812671048:
            await ctx.message.channel.send('this is cheseburger server only comand hehe')
            return
        chnl = self.client.get_channel(742952152653365289)
        # archive_channel = self.client.get_channel(742952152653365289)
        all_pins = await ctx.message.channel.pins()
        for i in all_pins:
            mat = i.attachments
            # TODO: make message link toggleable
            msg_link = 'https://discord.com/channels/690036880812671048/' + str(i.channel.id) + '/' + str(i.id)
            if len(mat) == 0:
                async with aiohttp.ClientSession() as session:
                    with open('config.json') as w:
                        idk = json.load(w)
                        url = idk['pinwebhookurl']
                    # webhook = Webhook.from_url(url, adapter=AsyncWebhookAdapter(session))
                    webhook = discord.Webhook.from_url(url, session=session)
                    await webhook.send(f'{discord.utils.escape_mentions(i.content)}\n{msg_link}',
                                       username=i.author.name,
                                       avatar_url=i.author.display_avatar)

                await chnl.send('‏‏‎ ‎')
            elif len(mat) == 1:
                async with aiohttp.ClientSession() as session:
                    with open('config.json') as w:
                        idk = json.load(w)
                        url = idk['pinwebhookurl']
                    webhook = discord.Webhook.from_url(url, session=session)
                    await webhook.send(f'{discord.utils.escape_mentions(i.content)}\n{msg_link}\n{mat[0].url}',
                                       username=i.author.name,
                                       avatar_url=i.author.display_avatar)
                await chnl.send('‏‏‎ ‎')
            else:
                async with aiohttp.ClientSession() as session:
                    with open('config.json') as w:
                        idk = json.load(w)
                        url = idk['pinwebhookurl']
                    webhook = discord.Webhook.from_url(url, session=session)
                    await webhook.send(f'{discord.utils.escape_mentions(i.content)}\n{msg_link}',
                                       username=i.author.name,
                                       avatar_url=i.author.display_avatar)
                    for image in range(len(mat)):
                        await webhook.send(mat[image - 1].url)
                await chnl.send('‏‏‎ ‎')
            await i.unpin(reason='to archive')
            # print(all_pins)

    @commands.command(hidden=True)
    async def kys(self, ctx):
        if ctx.author.id not in self.client.owners:
            return
        await ctx.send("killing mmyself")
        await self.client.close()

    async def code_input_parse(self, ctx, code, options_regex, default_formatting="ansi"):
        if code.strip() == "":
            await ctx.send("there is no code")
            return None

        format_option = (f"```{default_formatting}", "```")
        purge_backticks = True
        special_args = options_regex.findall(code.split()[0])
        timeout = 10  # seconds

        for argy in special_args:
            match argy[0]:
                case "return":
                    if argy[1] == "nobacktick":
                        format_option = (f"", "")
                        purge_backticks = False
                    elif argy[1] in self.discord_supported_markdown_languages:
                        format_option = (f"```{argy[1]}", "```")
                    else:
                        await ctx.send(f"return flag has invalid value! got {argy[1]}")
                        return None
                case "timeout":
                    try:
                        timeout = int(argy[1])
                    except ValueError:
                        await ctx.send(f"timeout has invalid value! got {argy[1]}")
                        return None
                case _:
                    await ctx.send(f"flag {argy[0]} isnt immplemented its over !!")
                    raise NotImplementedError

        code = self.exec_cmd_remove_code_extras.sub("", code)
        return code, format_option, timeout, purge_backticks

    @commands.command(hidden=True)
    async def bash(self, ctx, *, code):
        if ctx.author.id not in self.client.owners:
            return

        r = await self.code_input_parse(ctx, code, self.exec_cmd_get_options_regex)
        if r is None:
            return
        code, format_option, timeout, purge_backticks = r

        # if code.startswith("```"):
        #     code = code[3:]
        #     potential_formatter = code.split("\n")[0].split()
        #     if len(potential_formatter) > 0 and potential_formatter[0] in self.discord_supported_markdown_languages:
        #         code = code[len(potential_formatter):]
        # if code[-3:] == "```":
        #     code = code[:-3]
        sh_path = pathlib.Path(f"/tmp/{uuid.uuid4().hex}.sh")

        print(sh_path)
        zsh_options = (  # "setopt ERR_EXIT \n"
            "setopt SHARE_HISTORY \n"
            "setopt PROMPT_SUBST \n"
            "setopt EXTENDED_GLOB \n"
            "setopt EXTENDED_HISTORY \n"
            "setopt AUTO_PUSHD"
        )
        # TODO: allow like custom env vars in config file or something
        pre_cmds = (f"#!/bin/zsh \n"
                    f"unset LESS \n"
                    f"export COWPATH=\":${{HOME}}/.cowsay/cowfiles\" \n"
                    f"autoload -Uz add-zsh-hook \n"
                    f"{zsh_options} \n"
                    # f"cd ~"
                    )
        _echo_cmd = "\"> ${(z)3}\""
        pre_cmds = (f"{pre_cmds} \n"
                    f"function preexec () {{ \n"
                    f"    echo {_echo_cmd} \n"
                    f"}}")

        full_cmd = f"{pre_cmds} \n{code} \n"
        with open(sh_path, "w+") as f:
            f.write(full_cmd)
        sh_path.chmod(sh_path.stat().st_mode | stat.S_IEXEC)

        try:
            p = subprocess.Popen([str(sh_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            r = p.poll()

            while r is None:
                r = p.poll()
                timeout -= .2
                await asyncio.sleep(.2)
                if timeout <= 0:
                    p.terminate()
                    raise TimeoutError
            normal_output, error_output = p.communicate()
            if isinstance(normal_output, bytes):
                normal_output = normal_output.decode("utf-8")
            if isinstance(error_output, bytes):
                error_output = error_output.decode("utf-8").strip()
            normal_output = normal_output.strip()
            error_output = error_output.strip()
        except Exception as e:
            await ctx.send(f"```py\n{e.__class__.__name__}: {e}```")
            return

        if normal_output == "" and error_output == "":
            await ctx.send("no stdout")
            return
        if purge_backticks:
            repl = "'"
        else:
            repl = "\\`"
        normal_output = normal_output.replace("`", repl)
        error_output = error_output.replace("`", repl)
        if len(normal_output) + len(error_output) > 1990:
            msg = (f"output is too long, truncating\n"
                   f"{format_option[0]}\n"
                   f"{normal_output}")[:max(0, 1960 - len(error_output))]

            error_output = error_output[:1900]
            if len(error_output) > 0:
                msg += (f"\n"
                        f"{format_option[1]}\n"
                        f"error output: \n"
                        f"{format_option[0]}\n"
                        f"{error_output}\n"
                        f"{format_option[1]}\n")
            else:
                msg += f"{format_option[1]}"
            await ctx.send(msg)
            return
        msg = (f"{format_option[0]}\n"
               f"{normal_output}\n"
               f"{format_option[1]}")
        if len(error_output) > 0:
            msg += (f"\n"
                    f"error output: \n"
                    f"{format_option[0]}\n"
                    f"{error_output}\n"
                    f"{format_option[1]}")
        await ctx.send(msg)

    @commands.command(hidden=True)
    async def execute(self, ctx, *, code):
        if ctx.author.id not in self.client.owners:
            return
        r = await self.code_input_parse(ctx, code, self.exec_cmd_get_options_regex, "py")
        if r is None:
            return
        code, format_option, timeout, purge_backticks = r
        if code.strip() == "":
            await ctx.send("there is no code")
            return

        str_obj = io.StringIO()  # Retrieves a stream of data  # wow coment u are so smart that literally isnt the mmmomst obvious thing ever

        try:
            with contextlib.redirect_stdout(str_obj):
                exec(code, {'self': self})
        except Exception as e:
            await ctx.send(f"```py\n{e.__class__.__name__}: {e}```")
            return

        stdout = str_obj.getvalue()
        if stdout == "":
            await ctx.send("no stdout")
            return
        if purge_backticks:
            btr = "'"
        else:
            btr = "\\`"
        stdout = stdout.replace("`", btr)
        if len(stdout) > 1990:
            msg = f"output is too long, truncating\n{format_option[0]}\n{stdout}"[:1990]
            msg += f"{format_option[1]}"
            await ctx.send(msg)
            return
        await ctx.send(f'{format_option[0]}\n{stdout}{format_option[1]}')

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def prefix(self, ctx: commands.Context, *, new_prefix: str):
        current_prefix = self.client.db.guilds_info[ctx.guild.id]
        if current_prefix == new_prefix:
            await ctx.send(f"given prefix is same as the current prefix, {current_prefix}")
            return
        for char in self.client.illegal_prefix_characters:
            if char in new_prefix:
                if char == " ":
                    await ctx.send(f"bot prefix cannot contain a space")
                    return
                if char == "`":
                    await ctx.send(f"prefix contains disallowed character: `` `")
                    return
                await ctx.send(f"prefix contains disallowed character: `{char}`")
                return
        # await ctx.send("changing prefix...")
        await self.client.db.insert_guild_to_database(ctx.guild, prefix=new_prefix)
        self.client.db.guilds_info[ctx.guild.id].prefix = new_prefix
        await ctx.send(f"bot prefix changed to: `{new_prefix}`")

    @prefix.error
    async def prefix_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"you didnt give a prefix, but my current prefix is "
                           f"`{await self.client.get_prefix(ctx.message)}`")
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("you need moderate_members permission to change my prefix")
            return
        raise error

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def dmall(self, ctx):
        prefix = funcs.get_prefix(self.client, ctx.message)
        try:
            if ctx.message.content.split()[1] == "--raw":
                #                      12 is len("dmall") + len(" --raw ")
                cutoff = len(prefix) + 12
                raw = True
            else:
                raw = False
                #                      6 is len("dmall") + 1 for the space
                cutoff = len(prefix) + 6
        except IndexError:
            raw = False
            cutoff = 7

        if len(ctx.message.content[cutoff:].strip()) == 0 and len(ctx.message.attachments) == 0:
            await ctx.channel.send('u gotta put stuff')
            return
        ctx.message.content = ctx.message.content[cutoff:]

        channel_info = await self.client.db.select_channel(ctx.channel.id, dmall_webhook_url=True)
        if len(channel_info) == 0 or channel_info["dmall_webhook_url"] is None:
            # the channel doesnt exist in the db or theres no assigned dmall_webhook_url
            webhook = await ctx.channel.create_webhook(name="_dm")
            webhook_url = webhook.url
            await self.client.db.insert_channel_to_database(ctx.channel, dmall_webhook_url=webhook_url)
        else:
            webhook_url = channel_info["dmall_webhook_url"]

        # excepted_users = [1026460119489318952, 344817255118405632]  # ids of ppl who arent dmed
        excepted_users = []  # ill do this later i guess
        for m in ctx.guild.members:
            if m.id not in excepted_users:
                star = ctx.message.content
                if len(ctx.message.attachments) > 0:
                    star += f'\n{ctx.message.attachments[0].url}'
                if not raw:
                    star += f'\n- sent by {ctx.author}'
                star = f"<@{m.id}> {star}"
                if m.id != self.client.user.id and not m.bot:
                    try:
                        channel = await m.create_dm()
                        await channel.send(f'{star}')
                    except discord.errors.HTTPException:
                        await discord.Webhook.from_url(webhook_url, client=self.client).send(
                            content=f"<@{m.id}> has me blocked or has DMs off!",
                            username=self.client.user.display_name,
                            avatar_url=self.client.user.display_avatar.url
                        )
                        return

        await ctx.channel.send('done dming everyone')

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def purge(self, ctx, num: int):
        await ctx.channel.purge(limit=num)
        await ctx.channel.send(f"purged {num} messages")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clear(self, ctx):
        await ctx.send("https://tenor.com/view/fuwamoco-fuwawa-mococo-フワワ-モココ-gif-9014022038646658986 "
                       "https://tenor.com/view/limbus-company-ishmael-ishmael-brainrot-gif-11592142758723011036 "
                       "https://tenor.com/view/senatorlia-robin-hsr-star-rail-robin-hsr-gif-1904876825581590663 "
                       "https://tenor.com/view/smh-anime-girl-gif-12459523042458670621 "
                       "https://tenor.com/view/reimu-reimu-hakurei-china-love-love-china-gif-4739820462458512257 ")

    @commands.command(hidden=True)
    async def reload(self, ctx):
        with open('config.json') as file:
            self.client.owners = json.load(file)["owners"]
        if ctx.author.id not in self.client.owners:
            return
        if not self.client.debug and self.client.git_pull_on_reload_command:
            try:
                g = git.cmd.Git(os.getcwd())
                g.pull()
            except Exception as e:
                await ctx.send(f"error in git pull:\n```{e}```")
        # with open('config.json') as configf:
        #     config = json.load(configf)
        #     self.client.owners = config['owners']

        try:
            cogs_ = os.listdir('./cogs/')
            for cog_ in cogs_:
                _cog_list = cog_.split('.')
                if _cog_list[len(_cog_list) - 1] == 'py':
                    await self.client.reload_extension(f'cogs.{_cog_list[0]}')
        except Exception as e:
            await ctx.send(f"error in reloading cogs:\n```{e}```")

        for module in self.client.get_modules_to_reload(sys.modules):
            importlib.reload(module)

        try:
            new_db = classes.Database(self.client, self.client.database_location)
            await new_db.create()
            self.client.db = new_db
        except Exception as e:
            await ctx.send(f"error in reloading database:\n```{e}```")

        self.client.dispatch("reload_cmd_success")

        await ctx.send('reloaded')

    @commands.command(hidden=True)
    async def test_get_url(self, ctx):
        await ctx.send(f"the url i got is: {await utils.funcs.find_url_from_message(self.client, ctx.message)}")

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        pass
        # if str(ctx.command) == 'reload':
        #     with open('config.json') as file:
        #         owners = json.load(file)["owner-ids"]
        #     if ctx.author.id in owners:
        #         importlib.reload(dmall)


async def setup(client):
    await client.add_cog(Moderator(client))
