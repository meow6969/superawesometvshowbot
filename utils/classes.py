from __future__ import annotations

from configparser import ConfigParser

import aiosqlite
import re
import asyncio
import math
import json
import time
import queue
import random
import threading
import requests
import ast
import operator
import inspect
from typing import Callable

from lxml.html.diff import href_token
from typing_extensions import Self
import icrawler.builtin
import icrawler.storage

import aioboto3
import aiofiles
import botocore.config
import boto3.s3.transfer
import aiobotocore.session
import aiobotocore.client
import discord
from discord.ext import commands
import undetected_chromedriver as uc
from undetected_chromedriver import Chrome
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import lxml.html
from lxml.html import HtmlElement

from utils.logger import *
from utils.funcs import find_url_from_message


# my only wish in this world is to never need to open this file ever again

class DatabaseGuild:
    def __init__(self, guild_id: int, is_privileged: bool, prefix: str, welcome_channel_id: int | None = None,
                 extend_snipe_command_to_multiple_messages: bool = False, jailed_users: str | None = None):
        self.guild_id: int = guild_id
        self.is_privileged: bool = is_privileged
        self.prefix: str = prefix
        self.welcome_channel_id: int | None = welcome_channel_id
        self.extend_snipe_command_to_multiple_messages: bool = extend_snipe_command_to_multiple_messages
        self.jailed_users: str | None = jailed_users


class Database:
    db: aiosqlite.Connection
    database_structure: dict

    def __init__(self, client: commands.Bot, database_location: str):
        self.client = client
        self.database_location = database_location
        self.database_loaded = False
        self.guilds_info = {}

    async def create(self):
        self.db = await aiosqlite.connect(self.database_location)
        self.database_structure = await self.get_database_structure()
        await self.db_setup()
        await self.update_table_columns()
        await self.add_all_guilds_to_db()
        await self.get_all_guilds_info()
        self.database_loaded = True

    async def shutdown(self):
        await self.db.commit()
        await self.db.close()
        self.database_loaded = False

    async def get_database_structure(self) -> dict:
        with open("utils/database_structure.json") as f:
            return self.remove_comments_from_database_structure(json.load(f))

    @staticmethod
    def remove_comments_from_database_structure(database_structure: dict) -> dict:
        new_database_structure = {}
        for table_name in database_structure.keys():
            if table_name.startswith("comment_"):
                continue
            new_table = {}
            for column_name in database_structure[table_name].keys():
                if column_name.startswith("comment_"):
                    continue
                new_table[column_name] = database_structure[table_name][column_name]
            new_database_structure[table_name] = new_table
        return new_database_structure

    async def db_setup(self) -> None:
        cursor = await self.db.cursor()
        for table_name in self.database_structure.keys():
            sql_command = f"CREATE TABLE IF NOT EXISTS {table_name} (\n"

            for column_name in self.database_structure[table_name].keys():
                sql_command += f"    {column_name} {self.database_structure[table_name][column_name]},\n"
            sql_command = sql_command[:-2]
            sql_command += f"\n);"
            await cursor.execute(sql_command)
        await cursor.close()
        await self.db.commit()

    # this code is so terrible oh my god
    async def update_table_columns(self):
        for table_name in self.database_structure.keys():
            cursor = await self.db.execute(f"PRAGMA table_info({table_name});")
            table_columns = await cursor.fetchall()
            table_column_names = []
            for table_column in table_columns:
                # table_column is: (cid: int, name: str, type: str, notnull: bool, dflt_value: null, pk: bool)
                #                   cid = the id,        type = data type                            pk = primary key
                table_column_names.append(table_column[1])
                if table_column[1] not in self.database_structure[table_name].keys():
                    # the database has an extra column that the database_structure does not
                    self.client.secret_discord_log(
                        self.client,
                        f"column {table_column_names} was found in the database but not in db_structure! "
                        f"please check on this! The bot will still run but this should not go unchecked",
                        bold=True
                    )

            # we dont need to add any new tables here since that is handled in db_setup()
            for column_name in self.database_structure[table_name].keys():  # bruh wtf is even happening here
                if column_name not in table_column_names:
                    # we need to add a new column to the table
                    print_debug_okcyan(f"adding new column \"{column_name}\" to table {table_name} "
                                       f"with attributes \"{self.database_structure[table_name][column_name]}\"")
                    await cursor.execute(
                        f"ALTER TABLE {table_name} ADD {column_name} "
                        f"{self.database_structure[table_name][column_name]};")
                for table_column in table_columns:
                    if table_column[1] != column_name:
                        continue
                    column_proper_structure = self.database_structure[table_name][column_name]
                    if table_column[2] not in column_proper_structure:
                        # the type was changed
                        print_debug_fail(
                            f"column {column_name} in table {table_name} has changed its type "
                            f"please manually fix this!\n"
                            f"(DB:{table_column['type']} -> DB_STRUCTURE:{column_proper_structure})",
                            bold=True,
                            underlined=True
                        )
                        exit(1)
                    if table_column[3] == 1 and "NOT NULL" not in column_proper_structure or \
                            table_column[3] == 0 and "NOT NULL" in column_proper_structure:
                        # we need to change this rows "notnull" value to 0
                        print_debug_fail(
                            f"column \"{column_name}\" in table \"{table_name}\" has changed its notnull! "
                            f"please manually fix this!\n"
                            f"(DB:notnull={table_column[3]} -> DB_STRUCTURE:{column_proper_structure})",
                            bold=True,
                            underlined=True
                        )
                        exit(1)
            await cursor.close()
        await self.db.commit()

    async def add_guild_to_db(self, guild: discord.Guild) -> None:
        if await self.is_item_in_table("guilds", guild.id):
            # we already tracked this guild, yay
            return
        await self.insert_into_table_values("guilds", {
            "guild_id": guild.id,
            "is_privileged": False,
            "prefix": self.client.default_prefix,
            "extend_snipe_command_to_multiple_messages": False
        })

        self.guilds_info[guild.id] = DatabaseGuild(
            guild.id,
            False,
            self.client.default_prefix,
            None,
            False
        )

    async def add_all_guilds_to_db(self) -> None:
        cursor = await self.db.cursor()
        for guild in self.client.guilds:
            await self.add_guild_to_db(guild)
        await cursor.close()
        await self.db.commit()

    async def get_one_guild_info(self, guild: discord.Guild) -> None:
        if await self.is_item_in_table("guilds", guild.id):
            guild_info = await self.select_guild(guild.id, is_privileged=True, prefix=True, welcome_channel_id=True)
            if len(guild_info) == 0:  # idk how this would happen btu whatever
                return
            new_guild_info = DatabaseGuild(
                guild.id,
                guild_info["is_privileged"],
                guild_info["prefix"],
                guild_info["welcome_channel_id"],
                guild_info["extend_snipe_command_to_multiple_messages"],
                guild_info["jailed_users"]
            )
            self.guilds_info = new_guild_info
        else:
            await self.add_guild_to_db(guild)

    async def get_all_guilds_info(self):
        cursor = await self.db.cursor()
        await cursor.execute(f"SELECT * FROM guilds;")
        rows = await cursor.fetchall()
        for row in rows:
            guild_info = DatabaseGuild(row[0], row[1], row[2], row[3], row[4])
            self.guilds_info[row[0]] = guild_info
        await cursor.close()

    async def is_item_in_table(self, table_name: str, item_id: int) -> bool:
        table_id_name = await self.get_id_name_for_table(table_name)
        cursor = await self.db.execute(f"SELECT 1 FROM {table_name} WHERE {table_id_name} = {item_id};")
        if await cursor.fetchone() is None:
            return False
        return True

    async def get_id_name_for_table(self, table_name: str) -> str:
        for column_name in self.database_structure[table_name].keys():
            if "PRIMARY KEY" in self.database_structure[table_name][column_name]:
                return column_name
        error_message = f"given table_name ({table_name}) does not have a primary key according to database_structure"
        print_debug_fail(error_message, bold=True)
        raise Exception(error_message)

    async def insert_message_to_database(self, message: discord.Message, attachments: str):
        await self.insert_into_table_values("messages", {
            "message_id": message.id,
            "author_nick": message.author.display_name,
            "author_pfp_url": message.author.display_avatar.url,
            "content": message.content,
            "attachments": attachments
        })

    async def insert_channel_to_database(
            self, channel: discord.TextChannel, ignore=None, snipe_webhook_url=None, dmall_webhook_url=None,
            last_deleted_message_id=None):
        objects_to_insert = {}
        if snipe_webhook_url is not None:
            objects_to_insert["snipe_webhook_url"] = snipe_webhook_url
        if dmall_webhook_url is not None:
            objects_to_insert["dmall_webhook_url"] = dmall_webhook_url
        if last_deleted_message_id is not None:
            objects_to_insert["last_deleted_message_id"] = last_deleted_message_id
        if ignore is not None:
            objects_to_insert["ignore"] = ignore
        if await self.check_if_key_exists("channel_id", channel.id, "channels"):
            if len(objects_to_insert) == 0:
                error_msg = f"insert_channel_to_database: no arguments passed for already existing channel {channel.id}"
                self.client.secret_discord_log(error_msg)
                raise Exception(error_msg)
            await self.update_table_set_where("channels", objects_to_insert,
                                              "channel_id", channel.id)
        else:
            # the channel doesnt exist in the database so we need to add it
            objects_to_insert["channel_id"] = channel.id
            if ignore is None:
                objects_to_insert["ignore"] = False
            await self.insert_into_table_values("channels", objects_to_insert)

    async def insert_guild_to_database(
            self, guild: discord.Guild, is_privileged=None, prefix=None, welcome_channel_id=None,
            extend_snipe_command_to_multiple_messages=None, jailed_users=None):
        objects_to_insert = {}
        if is_privileged is not None:
            objects_to_insert["is_privileged"] = is_privileged
        if prefix is not None:
            objects_to_insert["prefix"] = prefix
        if welcome_channel_id is not None:
            objects_to_insert["welcome_channel_id"] = welcome_channel_id
        if extend_snipe_command_to_multiple_messages is not None:
            objects_to_insert["extend_snipe_command_to_multiple_messages"] = extend_snipe_command_to_multiple_messages
        if jailed_users is not None:
            objects_to_insert["jailed_users"] = jailed_users
        if await self.check_if_key_exists("guild_id", guild.id, "guilds"):
            if len(objects_to_insert) == 0:
                error_msg = f"insert_guild_to_database: no arguments passed for already existing guild {guild.id}"
                self.client.secret_discord_log(error_msg)
                raise Exception(error_msg)
            await self.update_table_set_where("guilds", objects_to_insert,
                                              "guild_id", guild.id)
        else:
            # the guild doesnt exist in the database so we need to add it and set default values
            objects_to_insert["guild_id"] = guild.id
            if is_privileged is None:
                objects_to_insert["is_privileged"] = False
            if prefix is None:
                objects_to_insert["prefix"] = self.client.default_prefix
            if extend_snipe_command_to_multiple_messages is None:
                objects_to_insert["extend_snipe_command_to_multiple_messages"] = False
            await self.insert_into_table_values("guilds", objects_to_insert)

    async def update_table_set_where(self, table_name: str, objects_to_insert: dict,
                                     where_key: str, where_equals) -> None:
        if len(objects_to_insert) == 0:
            return

        set_command = ""
        # no injection detection has to happen here cause these strings dont have quotations in them
        for key in objects_to_insert.keys():
            set_command += f"{key} = :{key}, "
        set_command = set_command[:-2]
        objects_to_insert[where_key] = where_equals
        cursor = await self.db.cursor()
        await cursor.execute(
            f"UPDATE {table_name} SET {set_command} WHERE {where_key} = :{where_key};", objects_to_insert)
        await cursor.close()
        await self.db.commit()

    async def insert_into_table_values(self, table_name: str, objects_to_insert: dict) -> None:
        if len(objects_to_insert) == 0:
            return

        information_to_insert = ""
        values_to_insert = ""
        for key in objects_to_insert.keys():
            information_to_insert += f"{key}, "
            values_to_insert += f":{key}, "
        information_to_insert = information_to_insert[:-2]
        values_to_insert = values_to_insert[:-2]

        cursor = await self.db.cursor()
        await cursor.execute(
            f"INSERT INTO {table_name} ({information_to_insert}) VALUES ({values_to_insert})",
            objects_to_insert
        )
        await cursor.close()
        await self.db.commit()

    async def select_channel(self, channel_id: int, ignore=False, snipe_webhook_url=False, dmall_webhook_url=False,
                             last_deleted_message_id=False) -> dict:

        if not await self.check_if_key_exists("channel_id", channel_id, "channels"):
            return {}

        information_to_retrieve = ""
        if ignore:
            information_to_retrieve += f"ignore, "
        if snipe_webhook_url:
            information_to_retrieve += f"snipe_webhook_url, "
        if dmall_webhook_url:
            information_to_retrieve += f"dmall_webhook_url, "
        if last_deleted_message_id:
            information_to_retrieve += f"last_deleted_message_id, "

        if information_to_retrieve.strip() == '':  # no retrieval information was enabled
            return {}
        information_to_retrieve = information_to_retrieve[:-2]  # take off the last ", "

        cursor = await self.db.execute(f"""
            SELECT {information_to_retrieve} FROM channels WHERE channel_id=:channel_id
        ;""", {"channel_id": channel_id})
        response = await cursor.fetchone()

        data_retrieved = []
        for i in information_to_retrieve.split(','):
            data_retrieved.append(i.strip())
        await cursor.close()

        return self.fetch_one_to_dict(response, data_retrieved)

    async def select_message(self, message_id: int, author_nick=False, author_pfp_url=False, content=False,
                             attachments=False) -> dict:
        if not await self.check_if_key_exists("message_id", message_id, "messages"):
            print_debug_fail(f"could not find nessage_id {message_id}")
            return {}

        information_to_retrieve = ""
        if author_nick:
            information_to_retrieve += f"author_nick, "
        if author_pfp_url:
            information_to_retrieve += f"author_pfp_url, "
        if content:
            information_to_retrieve += f"content, "
        if attachments:
            information_to_retrieve += f"attachments, "

        if information_to_retrieve.strip() == '':  # no retrieval information was enabled
            return {}
        information_to_retrieve = information_to_retrieve[:-2]  # take off the last ", "

        cursor = await self.db.execute(f"""
            SELECT {information_to_retrieve} FROM messages WHERE message_id=:message_id
        ;""", {"message_id": message_id})
        response = await cursor.fetchone()

        data_retrieved = []
        for i in information_to_retrieve.split(','):
            data_retrieved.append(i.strip())
        await cursor.close()

        return self.fetch_one_to_dict(response, data_retrieved)

    async def select_guild(self, guild_id: int, is_privileged=False, prefix=False, welcome_channel_id=False,
                           extend_snipe_command_to_multiple_messages=False, jailed_users=False) -> dict:
        if not await self.check_if_key_exists("guild_id", guild_id, "guilds"):
            print_debug_fail(f"could not find guild_id {guild_id}")
            return {}

        information_to_retrieve = ""
        if is_privileged:
            information_to_retrieve += f"is_privileged, "
        if prefix:
            information_to_retrieve += f"prefix, "
        if welcome_channel_id:
            information_to_retrieve += f"welcome_channel_id, "
        if extend_snipe_command_to_multiple_messages:
            information_to_retrieve += f"extend_snipe_command_to_multiple_messages, "
        if jailed_users:
            information_to_retrieve += f"jailed_users, "

        if information_to_retrieve.strip() == '':  # no retrieval information was enabled
            return {}
        information_to_retrieve = information_to_retrieve[:-2]  # take off the last ", "

        cursor = await self.db.execute(f"""
            SELECT {information_to_retrieve} FROM guilds WHERE guild_id=:guild_id
        ;""", {"guild_id": guild_id})
        response = await cursor.fetchone()

        data_retrieved = []
        for i in information_to_retrieve.split(','):
            data_retrieved.append(i.strip())
        await cursor.close()

        return self.fetch_one_to_dict(response, data_retrieved)

    async def check_if_key_exists(self, key: str, key_value, table_name: str) -> bool:
        # print(key)
        # print(key_value)
        # print(db_name)
        # response = self.cur.execute(f"""
        #     SELECT :key FROM :db_name WHERE :key=:key_value
        # ;""", {"key": key, "db_name": db_name, "key_value": key_value})
        response = await self.db.execute(f"""
            SELECT {key} FROM {table_name} WHERE {key} = :key_value
        ;""", {"key_value": key_value})
        rows = await response.fetchall()

        if len(list(rows)) == 0:
            return False
        else:
            return True

    # @staticmethod
    # def fetch_all_to_dict(response, data_retrieved) -> dict:
    #     return_dict = {}
    #     __response = []
    #     for i in response:
    #         for y in i:
    #             __response.append(y)
    #     for i, info in enumerate(__response):
    #         return_dict[data_retrieved[i]] = info
    #     return return_dict

    @staticmethod
    def fetch_one_to_dict(response, data_retrieved) -> dict:
        return_dict = {}
        for i, info in enumerate(response):
            return_dict[data_retrieved[i]] = response[i]
        return return_dict

    @staticmethod
    def convert_size(size_bytes) -> str:
        if size_bytes == 0:
            return "0B"
        size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return "%s %s" % (s, size_name[i])


class BaseDriver(Chrome):
    # driver: Chrome
    disconnect_msg: str = 'Unable to evaluate script: disconnected: not connected to DevTools\n'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # self.driver = uc.Chrome()

    def driver_sleep_until_closed(self) -> None:
        print("waiting for user to close browser...")
        while True:
            cur_log = self.get_log("driver")
            if len(cur_log) > 0 and cur_log[-1]["message"] == self.disconnect_msg:
                print("Browser window closed by user")
                return
            time.sleep(1)

    @staticmethod
    def human_send_keys(element: WebElement, text: str, enter=False) -> None:
        for key in text:
            element.send_keys(key)
            time.sleep(random.uniform(0, 0.1))
        if enter:
            element.send_keys(Keys.RETURN)

    @staticmethod
    def parse_styles(styles: str) -> dict[str, str]:
        r_dict = {}
        if styles.strip() == '':
            return r_dict
        # print(f"styles: {styles}")
        for style in styles.split(";"):
            if style.strip() == '':
                continue
            # print(f"style: {style}")
            # print(f"style.split(\":\")={style.split(':')}")
            # print(f"style.split(\":\")[0]={style.split(':')[0]}")
            # print(f"style.split(\":\")[1]={style.split(':')[1]}")
            r_dict[style.split(":")[0].strip()] = style.split(":")[1].strip()
        return r_dict

    def get_elements(self, by: By, selector: str, _min=0, _max=1,
                     from_element: WebElement | None = None) -> list[WebElement]:
        # print(f"with by={by} getting selector: {selector}")
        if from_element is None:
            # print(f"searching with BaseDriver")
            elements = self.find_elements(by, selector)
        else:
            # print(f"searching with from_element")
            elements = from_element.find_elements(by, selector)

        if (len(elements) <= _min != -1) or (len(elements) > _max != -1):
            raise IndexError(f"elements list of len {len(elements)} not in bounds of min={_min}, max={_max}\n"
                             f"selector={selector}")
        return elements

    def get_element(self, by: By, selector: str, _min=0, _max=1,
                    from_element: WebElement | None = None) -> WebElement:
        elements = self.get_elements(by, selector, _min=_min, _max=_max, from_element=from_element)
        # print(f"get_element: {len(elements)}")
        return elements[0]

    def wait_until_loaded(self):
        while self.execute_script("return document.readyState;") != "complete":
            time.sleep(3)
        # r = self.execute_script("return document.readyState;")
        # print(f"wait_until_loaded: {r}")

    def scroll_to_bottom(self):
        self.execute_script("window.scrollTo(0, document.body.scrollHeight);")


class GoogleImage:
    driver: BaseDriver
    element: WebElement
    real_image_url: str | None = None
    selector: str = "//*[@id=\"Sva75c\"]/div[2]/div[2]/div/div[2]/c-wiz/div/div[@data-ved and @jsaction]/" + \
                    "div[@jsaction and @data-ved]/a/img[contains(@style,\"visibility: hidden\")]"

    def __init__(self, driver: BaseDriver, elem: WebElement):
        self.driver = driver
        self.element = elem

    def get_real_image_url(self) -> str:
        self.element.click()
        time.sleep(2)
        self.driver.wait_until_loaded()
        image_url = self.get_focused_image()
        if image_url is None:
            raise Exception(f"image url {image_url} not found")
        self.real_image_url = image_url
        return image_url

    def get_focused_image(self) -> str:
        self.driver.wait_until_loaded()
        e_count = 0
        while True:
            try:
                pics = self.driver.get_elements(
                    By.XPATH,
                    self.selector,
                    _max=4
                )
                best_quality = {"val": 0, "pic": pics[0]}
                for pic in pics:
                    pic_styles = self.driver.parse_styles(pic.get_attribute("style"))
                    n_pic_styles = {}
                    for style in pic_styles.keys():
                        if "width" not in style and "height" not in style:
                            continue
                        if pic_styles[style].endswith("px"):
                            n_pic_styles[style] = int(pic_styles[style][:-2])
                            continue
                        n_pic_styles[style] = int(pic_styles[style])
                    b = max(n_pic_styles, key=n_pic_styles.get)
                    if n_pic_styles[b] > best_quality["val"]:
                        best_quality["val"] = n_pic_styles[b]
                        best_quality["pic"] = pic

                return best_quality["pic"].get_attribute("src")
            except IndexError as e:
                print("error")
                e_count += 1
                if e_count > 10:
                    print(f"{e}")
                    input()
                time.sleep(1)

    @staticmethod
    def convert_many(driver: BaseDriver, elems: list[WebElement]) -> list[Self]:
        r_list = []
        for elem in elems:
            r_list.append(GoogleImage(driver, elem))
        return r_list


class GoogleImageResult:
    driver: BaseDriver
    image_elements: list[GoogleImage]
    image_pointer: int
    images_search_url: str

    def __init__(self, query: str, **kwargs):
        self.driver = BaseDriver(**kwargs)
        self.image_elements = self.get_google_images(query)
        self.image_pointer = -1

    def ensure_valid_pointer(self):
        if self.image_pointer + 1 > len(self.image_elements):
            self.image_pointer = len(self.image_elements) - 1
            return
        if self.image_pointer < 0:
            self.image_pointer = 0
            return
        return

    def get_google_image_url(self) -> str:
        self.ensure_valid_pointer()
        img_elem = self.image_elements[self.image_pointer]
        if img_elem.real_image_url is not None:
            return img_elem.real_image_url
        return img_elem.get_real_image_url()

    def get_next_image_url(self) -> str:
        self.image_pointer += 1
        self.ensure_valid_pointer()
        return self.get_google_image_url()

    def get_previous_image_url(self) -> str:
        self.image_pointer -= 1
        self.ensure_valid_pointer()
        return self.get_google_image_url()

    def get_image_url_at(self, i: int) -> str:
        self.image_pointer = i
        self.ensure_valid_pointer()
        return self.get_google_image_url()

    def get_google_images(self, query: str) -> list[GoogleImage]:
        # self.driver.get("https://images.google.com")
        self.driver.get(f"https://www.google.com/search?q={query.replace(' ', '+')}&sclient=img&udm=2")

        # search_bar = self.driver.get_element(By.XPATH, "//textarea[@aria-label=\"Search\" and @title=\"Search\"]")
        # self.driver.human_send_keys(search_bar, query, enter=True)
        # self.images_search_url = self.driver.current_url
        self.driver.wait_until_loaded()
        images = self.driver.get_elements(
            By.XPATH,
            "//div[@id=\"rso\" and @class]/div[@class]/div[@jscontroller and not(@class)]/"
            "div[@jsmodel and @class]/div[@jscontroller and not(@class)]/"
            "div[@jscontroller and @class]/div[@jsname and @class]",
            _max=-1
        )

        # input(f"images len={len(images)}")
        return GoogleImage.convert_many(self.driver, images)

    def close(self):
        self.driver.close()


class LinkSaver(icrawler.Downloader):
    def __init__(self, thread_num, signal, session, storage, link_store: list[str]):
        """Init Parser with some shared variables."""
        super().__init__(thread_num, signal, session, storage)
        self.signal = signal
        self.session = session
        self.storage = storage
        self.file_idx_offset = 0
        self.clear_status()
        self.link_store: list[str] = link_store

    def clear_status(self):
        """Reset fetched_num to 0."""
        self.fetched_num = 0

    def set_file_idx_offset(self, file_idx_offset=0):
        if isinstance(file_idx_offset, int):
            self.file_idx_offset = file_idx_offset
        elif file_idx_offset == "auto":
            self.file_idx_offset = self.storage.max_file_idx()
        else:
            raise ValueError('"file_idx_offset" must be an integer or `auto`')

    def get_filename(self, task, default_ext=""):
        return task["file_url"].split("/")[-1].split("?")[0]

    def reach_max_num(self):
        if self.signal.get("reach_max_num"):
            return True
        if self.max_num > 0 and self.fetched_num >= self.max_num:
            return True
        else:
            return False

    def keep_file(self, task, response, **kwargs):
        return True

    def download(self, task, default_ext="", timeout=5, max_retry=3, overwrite=False, **kwargs) -> bool:
        if len(task["file_url"]) > 250:
            task["success"] = False
            return False
        try:
            req = requests.get(task["file_url"])
            if req.status_code != 200:
                task["success"] = False
                return False
        except:
            task["success"] = False
            return False
        self.link_store.append(task["file_url"])
        task["success"] = True
        task["filename"] = self.get_filename(task)
        return True

    def start(self, file_idx_offset=0, *args, **kwargs):
        self.clear_status()
        self.set_file_idx_offset(file_idx_offset)
        self.init_workers(*args, **kwargs)
        for worker in self.workers:
            worker.start()

    def worker_exec(self, max_num, default_ext="", queue_timeout=5, req_timeout=5, max_idle_time=None, **kwargs):
        self.max_num = max_num
        last_download_time = time.time()

        while True:
            if len(self.link_store) >= self.max_num:
                break

            current_time = time.time()
            if max_idle_time is not None and current_time - last_download_time > max_idle_time and self.fetched_num > 0:
                break

            try:
                task = self.in_queue.get(timeout=queue_timeout)
            except queue.Empty:
                if self.signal.get("parser_exited"):
                    break
                elif self.fetched_num == 0:
                    pass
                else:
                    break
            except:
                pass
            else:
                success = self.download(task, default_ext, req_timeout, **kwargs)
                if success:
                    last_download_time = time.time()
                self.process_meta(task)
                self.in_queue.task_done()

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class ICrawlerGoogleImageResult:
    image_links: list[str]
    image_pointer: int
    images_search_url: str
    images_to_get: int = 100

    def __init__(self, query: str, **kwargs):
        self.image_links = []
        self.image_thread = threading.Thread(target=self.get_images,
                                             args=(self.image_links, query, self.images_to_get))
        self.image_thread.start()
        self.image_pointer = -1

    @staticmethod
    def get_images(image_url_list: list[str], query: str, images_to_get: int):
        google_crawler = icrawler.builtin.GoogleImageCrawler(
            feeder_threads=1,
            parser_threads=1,
            downloader_threads=1,
            downloader_cls=LinkSaver,
            extra_downloader_args={"link_store": image_url_list},
            log_level=50
        )
        google_crawler.crawl(keyword=query, max_num=images_to_get)

    def ensure_valid_pointer(self):
        if self.image_pointer + 1 > len(self.image_links):
            self.image_pointer = len(self.image_links) - 1
            return
        if self.image_pointer < 0:
            self.image_pointer = 0
            return
        return

    def get_google_image_url(self) -> str:
        self.ensure_valid_pointer()
        return self.image_links[self.image_pointer]

    def get_next_image_url(self) -> str:
        self.image_pointer += 1
        return self.get_google_image_url()

    def get_previous_image_url(self) -> str:
        self.image_pointer -= 1
        return self.get_google_image_url()

    def get_image_url_at(self, i: int) -> str:
        self.image_pointer = i
        return self.get_google_image_url()

    def close(self):
        pass


class SafeMathEvaluator:
    ast_operators: dict[type[ast.operator] | type[ast.unaryop], Callable] = {}
    min_allowed_num = -2 ** 63
    max_allowed_num = 2 ** 63 - 1
    max_allowed_power = 2 ** 16
    max_expression_length = 2 ** 8

    def __init__(self):
        pass

    @staticmethod
    def operator_wrapper(ast_operators_dict, ast_operator_type: str | type[ast.operator] | type[ast.unaryop]):
        def wrapper(custom_operator_func: Callable):
            real_ast_operator_type = None
            if inspect.isclass(ast_operator_type) and (
                    issubclass(ast_operator_type, ast.operator) or
                    issubclass(ast_operator_type, ast.unaryop)):
                real_ast_operator_type = ast_operator_type
            else:
                ast_attr = getattr(ast, ast_operator_type, None)
                if not ast_attr:
                    raise TypeError(f"invalid ast_operator_type, got {ast_operator_type}")
                if not issubclass(ast_attr, ast.operator) and not issubclass(ast_attr, ast.unaryop):
                    raise TypeError(
                        f"invalid ast_operator_type ast_attr type, "
                        f"expected type ast.operator or ast.unaryop got {ast_attr}")
                real_ast_operator_type = ast_attr

            def argument_verifier_func(*args: int | float, **kwargs: int | float):
                for i in args + tuple(kwargs.values()):
                    if i < SafeMathEvaluator.min_allowed_num:
                        raise ValueError(f"numbers cannot be smaller than {SafeMathEvaluator.min_allowed_num}")
                    if i > SafeMathEvaluator.max_allowed_num:
                        raise ValueError(f"numbers cannot be greater than {SafeMathEvaluator.max_allowed_num}")
                return custom_operator_func(*args, **kwargs)

            argument_verifier_func.__name__ = custom_operator_func.__name__

            ast_operators_dict[real_ast_operator_type] = argument_verifier_func

            return argument_verifier_func

        return wrapper

    @staticmethod
    @operator_wrapper(ast_operators, "Add")
    def _add(a, b):
        return operator.add(a, b)

    @staticmethod
    @operator_wrapper(ast_operators, ast.Sub)
    def _sub(a, b):
        return operator.sub(a, b)

    @staticmethod
    @operator_wrapper(ast_operators, ast.Mult)
    def _mul(a, b):
        return operator.mul(a, b)

    @staticmethod
    @operator_wrapper(ast_operators, ast.Div)
    def _div(a, b):
        return operator.truediv(a, b)

    @staticmethod
    @operator_wrapper(ast_operators, ast.Pow)
    def _pow(a, b):
        if abs(b) > SafeMathEvaluator.max_allowed_power:
            raise ValueError(f"power cannot be greater than {SafeMathEvaluator.max_allowed_power}")
        return operator.pow(a, b)

    @staticmethod
    @operator_wrapper(ast_operators, "USub")
    def _neg(a):
        return operator.neg(a)

    def eval_math(self, node):
        if isinstance(node, str):
            node = node.replace("^", "**")
            # print(f"evaluating expression \"{node}\"")
            if len(node) > self.max_expression_length:
                raise ValueError(f"expression length greater than {self.max_expression_length}, got length {len(node)}")
            return self.eval_math(ast.parse(node, mode="eval").body)
        match node:
            case ast.Constant(value) if isinstance(value, int):
                return value
            case ast.BinOp(left, op, right):
                return self.ast_operators[type(op)](self.eval_math(left), self.eval_math(right))
            case ast.UnaryOp(op, operand):
                return self.ast_operators[type(op)](self.eval_math(operand))
            case _:
                raise TypeError(f"invalid node type {node}")


class EventTrackerBaseEvent:
    client: commands.Bot
    amount_to_save: int = 1
    key: str
    _saved_events: dict[int, list] = {}

    def __init__(self, client, key: str, amount_to_save: int = 1):
        self.client = client
        self.key = key
        self.amount_to_save = amount_to_save

    async def _ensure_channel_object(self, channel: discord.TextChannel | int) -> discord.TextChannel:
        if isinstance(channel, int):
            return self.client.get_channel(channel)
        return channel

    async def on_message(self, message: discord.Message):
        pass

    async def get_saved_event(self, channel: discord.TextChannel | int, index=-1):
        channel = await self._ensure_channel_object(channel)
        if channel.id not in self._saved_events or len(self._saved_events[channel.id]) < max(index, 0) + 1:
            return None
        return self._saved_events[channel.id][index]

    async def save_new_event(self, channel: discord.TextChannel | int, event):
        channel = await self._ensure_channel_object(channel)
        if channel.id not in self._saved_events:
            self._saved_events[channel.id] = []
        self._saved_events[channel.id].append(event)
        # print_debug_blank(f"added a new event to channel {channel.name} at key {self.key}, {event}")
        if len(self._saved_events[channel.id]) > self.amount_to_save:
            del self._saved_events[channel.id][0]

    async def get_saved_events(self, channel: discord.TextChannel | int):
        channel = await self._ensure_channel_object(channel)
        return self._saved_events.get(channel.id, None)

    async def forget_saved_events(self, channel: discord.TextChannel | int):
        channel = await self._ensure_channel_object(channel)
        self._saved_events[channel.id] = []


class UrlEventTracker(EventTrackerBaseEvent):
    key: str = "last_url"
    num_of_falses_before_forgetting = 5
    num_of_falses: dict[int, int] = {}

    def __init__(self, client, amount_to_save: int = 1):
        super().__init__(client, self.key, amount_to_save)

    async def num_falses_tracker(self, message: discord.Message, reset=False):
        if message.channel.id not in self.num_of_falses or reset:
            self.num_of_falses[message.channel.id] = 0
            return
        self.num_of_falses[message.channel.id] += 1
        if self.num_of_falses[message.channel.id] >= self.num_of_falses_before_forgetting:
            # print_debug_blank(f"forgetting saved {self.key} events for channel {message.channel.name}")
            await self.forget_saved_events(message.channel)

    async def on_message(self, message: discord.Message):
        # rec=2 means that it wont search replies for a link
        url = await find_url_from_message(self.client, message, check_reply=False, check_tracker=False)
        if url is None:
            await self.num_falses_tracker(message)
            return
        # print_debug_blank(f"url event tracker found url {url}")
        await self.num_falses_tracker(message, reset=True)

        await self.save_new_event(message.channel, url)


class PerChannelEventTracker:
    _tracked_events: dict[str, EventTrackerBaseEvent] = {}

    def __init__(self):
        print_debug_okgreen("per channel event tracker started")

    async def on_message(self, message: discord.Message):
        # print_debug_blank("checking message for urls...")
        for tracker in self._tracked_events.values():
            await tracker.on_message(message)

    async def get_saved_event(self, key, channel: discord.TextChannel | int, index=-1):
        tracker = self._tracked_events.get(key, None)
        # print_debug_blank(f"tracker we found with key {key} was: {tracker}")
        # print_debug_blank(f"_tracked_events={self._tracked_events}")
        if tracker is None:
            return None
        return await tracker.get_saved_event(channel, index=index)

    async def add_new_event_tracker(self, event_tracker: EventTrackerBaseEvent):
        self._tracked_events[event_tracker.key] = event_tracker


class AwsS3Manager:
    config: dict
    session: aioboto3.Session
    bucket: str
    s3_config: dict
    file_link_mask: str

    # client_config: botocore.config.Config

    def __init__(self, s3_config: dict):
        self.config = s3_config
        self.bucket = self.config["bucket_name"]
        self.s3_config = {
            "region_name": self.config["hostname"].split(".")[0],
            "aws_access_key_id": self.config["access_key"],
            "aws_secret_access_key": self.config["secret_key"]

        }
        self.endp = "https://" + self.config["hostname"]
        if "file_link_mask" in self.config:
            self.file_link_mask = self.config["file_link_mask"]
        # self.client_config = botocore.config.Config(**self.s3_config)

    async def setup(self):
        self.session = aioboto3.Session(**self.s3_config)
        await self.create_bucket_if_not_exists()

    async def get_buckets(self):
        async with self.session.client("s3", endpoint_url=self.endp) as s3:
            buckets = await s3.list_buckets()
            return buckets["Buckets"]

    async def create_bucket_if_not_exists(self):
        async with self.session.client("s3", endpoint_url=self.endp) as s3:
            r = await s3.list_buckets()
            for bucket in await self.get_buckets():
                if bucket["Name"] == self.bucket:
                    return
            await s3.create_bucket(Bucket=self.bucket)

    async def upload_file_to_bucket(self, file: pathlib.Path, s3_path: str, public=True):
        async with self.session.client("s3", endpoint_url=self.endp) as s3:
            async with aiofiles.open(file, "rb") as f:
                # with file.open("rb") as f:
                if public:
                    extra_args = {"ACL": "public-read"}
                else:
                    extra_args = None
                await s3.upload_fileobj(f, self.bucket, s3_path, ExtraArgs=extra_args)
        if self.file_link_mask is not None:
            return f"{self.file_link_mask}/{s3_path}"
        return f"{self.endp}/{s3_path}"

    @staticmethod
    async def setup_new(s3_config: dict) -> AwsS3Manager:
        a = AwsS3Manager(s3_config)
        await a.setup()
        return a


# time in seconds: aliases for this amount of time
# the most human readable plural form of the time unit is at the end so we can easily return it to display to users
time_unit_codes: dict[int, list[str]] = {
    1: ["s", "sec", "second", "seconds"],
    60: ["m", "min", "mins", "minute", "minutes"],
    60 * 60: ["h", "hour", "hours"],
    24 * 60 * 60: ["d", "day", "days"],
    7 * 24 * 60 * 60: ["w", "week", "weeks"],
    30 * 24 * 60 * 60: ["mo", "mon", "month", "months"],
    365 * 24 * 60 * 60: ["y", "year", "years"]
}
time_parser_regex = re.compile(r"(\A[0-9]*)\s*([a-zA-Z]*)\b")


class DiscordTimespan:
    time_in_seconds: int
    time_unit: str
    time_unit_base_seconds: int
    num_of_time_unit: int
    unix_time_expires: int

    def __init__(self, num_of_time_unit: int, time_unit: str = "minutes"):
        self.num_of_time_unit = num_of_time_unit
        r = self._get_time_unit(time_unit)
        if r[0] is None:
            raise Exception(f"Invalid time unit '{time_unit}'")
        self.time_unit_base_seconds = r[0]
        self.time_unit = r[1]
        self.time_in_seconds = self.time_unit_base_seconds * self.num_of_time_unit
        self.unix_time_expires = int(time.time() + self.time_in_seconds)

    def __str__(self):
        return f"{self.num_of_time_unit} {self.time_unit}"

    def __repr__(self):
        return self.__str__()

    def __gt__(self, other):
        return self.unix_time_expires > other

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str) -> DiscordTimespan:
        time_span = cls.from_str(argument)
        if time_span is None:
            raise commands.BadArgument(f"Invalid time span '{argument}'")
        return time_span

    @staticmethod
    def _get_time_unit(in_str: str) -> tuple[int, str] | tuple[None, None]:
        # returns the time unit in seconds as well as the human readable name in a tuple

        for seconds in time_unit_codes.keys():
            if in_str in time_unit_codes[seconds]:
                return seconds, time_unit_codes[seconds][-1]
        return None, None

    @staticmethod
    def from_str(in_str: str) -> DiscordTimespan | None:
        # returns the number parsed from in_str, the human readable time unit parsed from in_str, and the

        r = time_parser_regex.findall(in_str)
        if len(r) == 0:
            return None
        r_groups = r[0]
        if not r_groups[0].isdigit():
            return None
        n = int(r_groups[0])
        _, unit = DiscordTimespan._get_time_unit(r_groups[1])
        if unit is None:
            return DiscordTimespan(n)
        return DiscordTimespan(n, unit)


def test_google_images():
    queries = [
        "meow",
        "anime",
        "anime gamer",
        "astolfo femboy gaming"
    ]
    for query in queries:
        r = GoogleImageResult(query)
        print(f"{query}:")
        print(f"{{")
        print(f"  search_url={r.images_search_url}")
        for i in range(3):
            # print(f"query={query}, i={i}, result={r.get_next_image_url()}")
            print(f"  i={i}, result={r.get_next_image_url()}")
        print(f"}}\n")
        r.close()


def test_s3():
    async def actually_test_it():
        aws_man: AwsS3Manager = await AwsS3Manager.setup_new(s3_config)
        print(await aws_man.get_buckets())
        # await aws_man.upload_file_to_bucket(pathlib.Path("/home/meow/Pictures/coolanimepicture69mushroomanime.png"),
        #                                     "meowbot/pics/coolpic.png")
        r = await aws_man.upload_file_to_bucket(pathlib.Path("/home/meow/Videos/canisitonyourfaceandpeeinyourmout"
                                                             "htrust"
                                                             "meyoulllikeitittasteslikemonsterwannatryitpeepis"
                                                             "surineimju"
                                                             "stkiddingletsholdhandslove.mp4"),
                                                "meowbot/vids/coolvid.mp4")
        print(f"returned url: {r}")
        # print(type(aws_man.client))
        # print(s3_obj)

    with open("../config.json") as meowf:
        s3_config = json.load(meowf)["aws_s3_config"]
    loop = asyncio.get_event_loop()
    loop.run_until_complete(actually_test_it())


safe_math_evaluator = SafeMathEvaluator()


if __name__ == "__main__":
    test_s3()
    # print(safe_math_evaluator.eval_math("1 + 2*3**(4^2) / (6 + -7)"))
    # test_google_images()

# if __name__ == "__main__":
#     with open("database_structure.json") as f:
#         meow_structure = json.load(f)
#
#     new_database_structure = {}
#     for table_name in meow_structure.keys():
#         if table_name.startswith("comment_"):
#             continue
#         new_table = {}
#         for column_name in meow_structure[table_name].keys():
#             if column_name.startswith("comment_"):
#                 continue
#             new_table[column_name] = meow_structure[table_name][column_name]
#         new_database_structure[table_name] = new_table
#     print_debug_okgreen(json.dumps(new_database_structure, indent=2))
