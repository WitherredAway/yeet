import io
import math
import typing
from typing import Dict, List, Tuple, Union
import cProfile
from typing import Dict, Optional
import unicodedata
from PIL import Image

import discord
import numpy as np


def isfloat(input):
    try:
        float(input)
    except:
        return False
    else:
        return True


def invert_dict(dict: typing.Dict) -> typing.Dict:
    inverted_dict = {value: key for key, value in dict.items()}
    return inverted_dict


def profile(func):
    def decorator(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = func(*args, **kwargs)
        pr.disable()
        pr.print_stats(sort="tottime")
        return result

    return decorator


def async_profile(func):
    async def decorator(*args, **kwargs):
        pr = cProfile.Profile()
        pr.enable()
        result = await func(*args, **kwargs)
        pr.disable()
        pr.print_stats(sort="tottime")
        return result

    return decorator


def image_to_file(image: Image, *, filename: Optional[str] = "image") -> discord.File:
    with io.BytesIO() as image_binary:
        image.save(image_binary, "PNG")
        image_binary.seek(0)

        return discord.File(fp=image_binary, filename=f"{filename}.png")


class UrlView(discord.ui.View):
    def __init__(self, url_dict: Dict[str, str]):
        super().__init__()

        for text, url_row_tup in url_dict.items():
            if isinstance(url_row_tup, tuple):
                url, row = url_row_tup
            else:
                url, row = url_row_tup, None
            self.add_item(
                discord.ui.Button(
                    label=text, url=url, style=discord.ButtonStyle.url, row=row
                )
            )


class RoleButton(discord.ui.Button):
    def __init__(self, role_name: str, **kwargs):
        self.role_name = role_name
        kwargs["label"] = self.role_name
        super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        role = discord.utils.get(interaction.guild.roles, name=self.role_name)
        if role is None:
            return await interaction.response.send_message(
                f"Role {self.role_name} not found."
            )

        if role in user.roles:
            await user.remove_roles(role)
            return await interaction.response.send_message(
                content=f"Took away {role.mention}!",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(roles=False),
            )
        await user.add_roles(role)
        await interaction.response.send_message(
            content=f"Gave you {role.mention}!",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions(roles=False),
        )


class RoleMenu(discord.ui.View):
    def __init__(self, roles_dict: Dict[str, discord.ButtonStyle]):
        self.roles_dict = roles_dict
        super().__init__(timeout=None)
        for role_name, style in self.roles_dict.items():
            if len(self.children) == 25:
                break
            self.add_item(
                RoleButton(role_name, style=style, custom_id=f"rolemenu:{role_name}")
            )


PB_BARS = {0.0: "⬜", 0.3: "🟧", 0.7: "🟨", 1.0: "🟩"}


def make_progress_bar(val: int, max_val: int, *, length: Optional[int] = 10) -> str:
    full_bar = np.full(length, PB_BARS[0.0])

    if not (val == max_val == 0):
        to_val = round((length / max_val) * val)
    else:
        to_val = 0
    percent = to_val / length
    cell = ""
    for per, bar in PB_BARS.items():
        if per < percent:
            continue
        else:
            cell = bar
            break

    full_bar[:to_val] = cell
    return "".join(full_bar)


def normalize(text: str) -> str:
    """Taken from poketwo!"""
    try:
        text = text.casefold()
    except AttributeError:
        return ""
    norm = unicodedata.normalize("NFD", text)
    result = "".join(ch for ch in norm if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFKC", result)


def resize(
    file: io.BytesIO,
    *,
    height: int,
    width: int,
    crop: Optional[bool] = False,
    fit: Optional[bool] = False,
) -> Tuple[bytes, Tuple[int]]:
    att_image = Image.open(file)
    if fit is True:
        bbox = att_image.getbbox()
        if (width, height) == att_image.size:
            # if h and w are the same as the original file, set it to the new bbox so it doesn't resize the image
            width, height = (bbox[2] - bbox[0], bbox[3] - bbox[1])
        att_image = att_image.crop(bbox)
    else:
        bbox = (0, 0, *att_image.size)

    if crop is True:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))

        offset = (
            (image.size[0] - bbox[2] + bbox[0]) // 2,
            (image.size[1] - bbox[3] + bbox[1]) // 2,
        )

        image.paste(att_image, offset)
    else:
        image = att_image.resize((width, height))

    with io.BytesIO() as image_bytes:
        image.save(image_bytes, "PNG")
        return image_bytes.getvalue(), image.size


def center_resize(
    file: io.BytesIO,
    *,
    height: int,
    width: int,
    crop: Optional[bool] = None,
    fit: Optional[bool] = False,
) -> Tuple[bytes, Tuple[int]]:
    att_image = Image.open(file)
    if crop is not True:
        h_issmall = height <= att_image.size[1]
        w_issmall = width <= att_image.size[0]
        if h_issmall and w_issmall:
            with io.BytesIO() as file:
                att_image.save(file, "PNG")
                return resize(file=file, height=height, width=width, crop=crop, fit=fit)
        elif h_issmall:
            att_image = Image.open(
                io.BytesIO(
                    resize(file, height=height, width=att_image.size[0], fit=fit)
                )
            )
        elif w_issmall:
            att_image = Image.open(
                io.BytesIO(resize(file, height=att_image.size[1], width=width, fit=fit))
            )
    else:
        if fit is True:
            bbox = att_image.getbbox()
            att_image = att_image.crop(bbox)
        else:
            bbox = (0, 0, *att_image.size)

    bg_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    offset = (
        (bg_image.size[0] - bbox[2] + bbox[0]) // 2,
        (bg_image.size[1] - bbox[3] + bbox[1]) // 2,
    )

    region_image = Image.new(
        "RGBA", (bbox[2] - bbox[0], bbox[3] - bbox[1]), (0, 0, 0, 0)
    )
    region_image.paste(att_image, (0, 0))

    bg_image.paste(att_image, offset)

    with io.BytesIO() as image_bytes:
        bg_image.save(image_bytes, "PNG")
        return image_bytes.getvalue(), bg_image.size


class SimpleModal(discord.ui.Modal):
    def __init__(self, *, title: str, inputs: List[discord.TextInput]):
        super().__init__(title=title)
        if len(inputs) > 5:
            raise ValueError("Too many TextInputs passed into SimpleModal")
        for input in inputs:
            self.add_item(input)

    @property
    def label_dict(self) -> Dict[str, discord.ui.TextInput]:
        ch_dict = {child.label: child for child in self.children}
        return ch_dict

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.stop()


def enumerate_list(_list: List) -> List[str]:
    ret = [f"{idx + 1}. {element}" for idx, element in enumerate(_list)]
    return ret if len(ret) > 0 else ["None"]


def value_to_option_dict(
    select_menu: discord.SelectMenu,
) -> Dict[int, discord.SelectOption]:
    return {option.value: option for option in select_menu.options}


def emoji_to_option_dict(
    select_menu: discord.SelectMenu,
) -> Dict[discord.PartialEmoji, discord.SelectOption]:
    return {
        option.emoji.name
        if option.emoji.is_unicode_emoji()
        else option.emoji.id: option
        for option in select_menu.options
    }

def round_up(num: Union[int, float]) -> int:
    if num >= 0:
        return math.floor(num + 0.5)
    else:
        return math.ceil(num - 0.5)