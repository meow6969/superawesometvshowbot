import re

import discord
from discord.ext import commands

from utils.logger import print_debug_blank

# url_verifier_regex = re.compile(r'\Ahttp(?:s|(?:)):\/\/(?=(?:\w+?\.\w+)+)[\w\.]*?\/[\S]*\b')
# the old one would only find a url if it was at the very start of the string
# this one finds all of the urls in a string
url_verifier_regex = re.compile(r'\bhttp(?:s|(?:)):\/\/(?=(?:\w+?\.\w+)+)[\w\.]*?\/[\S]*\b')


def get_prefix(client: commands.Bot, message: discord.Message) -> str:
    if isinstance(message.channel, discord.DMChannel):
        return client.default_prefix
    if not hasattr(client, "db"):
        return client.default_prefix
    # assert isinstance(client.db, classes.Database)
    if not client.db.database_loaded:
        return client.default_prefix
    p = client.db.guilds_info[message.guild.id].prefix
    if message.content.lower().startswith(p):  # we do this so the prefix is case insensitive
        return message.content[:len(p)]
    return p


async def find_url_from_message(client: commands.Bot, message: discord.Message,
                                check_reply=True, check_tracker=True) -> str | None:
    async def do_check_tracker():
        if check_tracker:
            return await client.per_channel_event_tracker.get_saved_event("last_url", message.channel)
        return None

    url = url_verifier_regex.search(message.content)
    if not url:
        # print_debug_blank(f"message.reference={message.reference}")
        # print_debug_blank(f"type(message.reference)={type(message.reference)}")
        if check_reply and isinstance(message.reference, discord.MessageReference) and \
                message.reference.cached_message is not None:
            url = url_verifier_regex.search(message.reference.cached_message.content)
            if url is not None:
                return url.group()
        return await do_check_tracker()
    return url.group()


# def does_image_have_face(image, detector: MTCNN):
#     imgy = load_image(image)
#     result = detector.detect_faces(imgy)
#     print(result)
#     if len(result) > 0:
#         return True
#     return False


if __name__ == "__main__":
    pass
    # get_google_images("meow")
    # //*[@id="rso"]/div/div/div[1]/div/div/div[3]/div[2]/h3/a/div/div/div/g-img
    # //*[@id="rso"]/div/div/div[1]/div/div/div[2]
    # //h1[text()="Search Results" and @class]/parent::div[@data-hveid and @data-ved]/div[@class and @eid and
    # memory_image = io.BytesIO()
    # nya_detector = MTCNN(device="GPU:0")
    # await img.save(memory_image)
    # save_img = Image.open(memory_image)
    # save_img = Image.frombytes("RGB", (img.width, img.height), memory_image.read())
    # nupy_img = numpy.array(save_img)
    # result = does_image_have_face(nupy_img, self.client.face_detector)
    # nya_result = does_image_have_face(
    #     "/home/meow/Pictures/awhellnahmilktook40benadrylsdphdrugs.jpeg",
    #     nya_detector
    # )
    # print(nya_result)
    # get_redirected_stdout(meow_debug_fail)
