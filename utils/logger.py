import functools
import pathlib
import sys
import inspect
from datetime import datetime
from pathlib import Path
import os

__LOG_FILE_NAME = "bot.log"


# idk why i made this instewad ofjust using buiild in logger
# i think im mjsut a baka


class BColors:  # print pretty colors with these!!!
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def get_log_file_path():
    try:
        parent = Path(__file__).parent.parent
        if "main.py" in os.listdir(parent):
            return parent.joinpath(__LOG_FILE_NAME)
        raise Exception(f"logger doesnt know where it is! couldnt find main.py in parent {parent}!")
    except NameError:
        pass
    if __name__ != "__main__":
        raise Exception("idk if this can even happen")
    me = Path.cwd()
    if "main.py" in os.listdir(me):
        return me.joinpath(__LOG_FILE_NAME)
    if "main.py" in os.listdir(me.parent):
        return me.parent.joinpath(__LOG_FILE_NAME)
    raise Exception(f"logger doesnt know where it is! couldnt find main.py in cwd {me}!")


__LOG_FILE_PATH = get_log_file_path()


def log(message: str) -> None:
    with open(__LOG_FILE_PATH, "a+") as f:
        f.write(str(message) + "\n")


def get_color_modifiers(underlined: bool, bold: bool) -> str:
    color_modifiers = ""
    if underlined:
        color_modifiers += BColors.UNDERLINE
    if bold:
        color_modifiers += BColors.BOLD
    return color_modifiers


def master_print_debug(message: str, color: str, underlined=False, bold=False, prefix=None, **kwargs) -> None:
    if "ERROR" in prefix and "file" not in kwargs:
        kwargs["file"] = sys.stderr
    the_stack = inspect.stack()
    caller = the_stack[1]

    # caller.filename
    sub_caller = the_stack[2]
    stack_str = f""
    # if sub_caller.function != "<module>":
    #     stack_str += f"{sub_caller.function}()->"
    stack_str += f"{pathlib.Path(caller.filename).name}:{caller.lineno}:"
    stack_str += f"{caller.function}()"

    time_str = f"{{END~COLOR}}{{TIME~COLOR~HERE}}{datetime.now().isoformat()}{{END~COLOR}}{{MESSAGE~COLOR~HERE}}"
    del the_stack
    # message = f"{time_str}{prefix}{stack_str} {message}"
    # message = f"{prefix} {time_str} [{stack_str}] - {message}"
    # message = f"{{MESSAGE~COLOR~HERE}}[{{PREFIX~HERE}}] {{TIME~HERE}} [{{STACK~HERE}}]" + f" - {message}"
    # left_part = f"{{MESSAGE~COLOR~HERE}}[{{PREFIX~HERE}}] {time_str} [{stack_str}]"  #  + f" - {message}"

    color += get_color_modifiers(underlined, bold)
    # base_str = f"{{MESSAGE~COLOR~HERE}}[{{PREFIX~HERE}}] {time_str} [{stack_str}]"
    base_str = f"{{MESSAGE~COLOR~HERE}}[{prefix}] {time_str} [{stack_str}]"
    log_str = (
        base_str.replace(f"{{MESSAGE~COLOR~HERE}}", "")
        #  .replace(f"{{PREFIX~HERE}}", prefix)
        .replace(f"{{END~COLOR}}", "")
        .replace(f"{{TIME~COLOR~HERE}}", "")
    )
    print_str = (
        base_str.replace(f"{{MESSAGE~COLOR~HERE}}", color)
        # .replace(f"{{PREFIX~HERE}}", prefix)
        .replace(f"{{END~COLOR}}", BColors.ENDC)
        .replace(f"{{TIME~COLOR~HERE}}", BColors.OKCYAN)
    )

    log(f"{log_str}" + f" - {message}")
    print(f"{print_str}" + f" - {message}{BColors.ENDC}", **kwargs)


print_debug_blank = functools.partial(master_print_debug, color="", prefix="DEBUG ")
print_debug_header = functools.partial(master_print_debug, color=BColors.HEADER, prefix="INFO  ")
print_debug_okblue = functools.partial(master_print_debug, color=BColors.OKBLUE, prefix="INFO  ")
print_debug_okcyan = functools.partial(master_print_debug, color=BColors.OKCYAN, prefix="INFO  ")
print_debug_okgreen = functools.partial(master_print_debug, color=BColors.OKGREEN, prefix="INFO  ")
print_debug_warning = functools.partial(master_print_debug, color=BColors.WARNING, prefix="WARN  ")
print_debug_fail = functools.partial(master_print_debug, color=BColors.FAIL, prefix="ERROR ")

if __name__ == "__main__":
    pass
    # do tests
    # print(__LOG_FILE_PATH)

    # yay it works
