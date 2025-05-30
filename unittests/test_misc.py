import typing
import unittest
import io
from typing import Callable
import contextlib
from mock import patch
# import sys
# from pathlib import Path
# sys.path.append(str(Path(__file__).parent.parent))

import discord

from utils.funcs import *
from utils.logger import *


class DummyClass:
    pass


def get_dummy_db():
    pass


def get_dummy_client():
    # noinspection PyTypeChecker
    client = commands.Bot(
        command_prefix=get_prefix,
        intents=discord.Intents.all(),
        fetch_offline_members=True,
        case_insensitive=True
    )


class FunctionOut:
    _stderr: sys
    _stdout: sys
    _out_stringio: io.StringIO
    _err_stringio: io.StringIO
    stdout: str
    bstdout: bytes
    # sbstdout: list[bytes]
    stderr: str
    bstderr: bytes
    # sbstderr: list[bytes]

    def __enter__(self):
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = self._out_stringio = io.StringIO()
        sys.stderr = self._err_stringio = io.StringIO()
        return self

    def __exit__(self, *args):
        # self.extend(self._stringio.getvalue().splitlines())
        self.stdout = self._out_stringio.getvalue()
        self.stderr = self._err_stringio.getvalue()
        self.bstdout = self.stdout.encode()
        self.bstderr = self.stderr.encode()
        # self.sbstdout = self.bstdout.splitlines(keepends=True)
        # self.sbstderr = self.bstderr.splitlines(keepends=True)

        del self._out_stringio
        del self._err_stringio
        sys.stdout = self._stdout
        sys.stderr = self._stderr

    def remove_timestamp(self) -> tuple[bytes, bytes]:
        new_stdout = b""
        new_stderr = b""

        for line in self.stdout.splitlines(keepends=True):
            new_stdout = new_stdout + line.split(maxsplit=3)[-1].encode()
        for line in self.stderr.splitlines(keepends=True):
            new_stderr = new_stderr + line.split(maxsplit=3)[-1].encode()
        return new_stdout, new_stderr


def get_redirected_stdout(method: Callable, *args, **kwargs) -> FunctionOut:
    with FunctionOut() as output:
        # noinspection PyProtectedMember
        method(*args, **kwargs)
    return output


class TestFuncs(unittest.TestCase):
    def test_get_prefix(self):
        self.assertEqual("meow", "mmeoweow")


class TestLogger(unittest.TestCase):
    f: io.StringIO

    def __init__(self, meow_object):
        super().__init__(meow_object)

    @staticmethod
    def meow_log_header():
        print_debug_header("print_debug_header")
        print_debug_header("print_debug_header, underlined", underlined=True)
        print_debug_header("print_debug_header, bold", bold=True)
        print_debug_header("print_debug_header, underlined, bold", underlined=True, bold=True)

    def test_log_header(self):
        out = get_redirected_stdout(self.meow_log_header)
        correct = (
            b'[test_log_header()->get_redirected_stdout()] - print_debug_header\x1b[0m\n'
            b'[test_log_header()->get_redirected_stdout()] - print_debug_header, underlined\x1b[0m\n'
            b'[test_log_header()->get_redirected_stdout()] - print_debug_header, bold\x1b[0m\n'
            b'[test_log_header()->get_redirected_stdout()] - print_debug_header, underlined, bold\x1b[0m\n'
        )
        # print(correct)

        new_stdout, _ = out.remove_timestamp()
        # print(new_stdout)
        self.assertEqual(correct, new_stdout)
        self.assertEqual(b"", out.bstderr)

    @staticmethod
    def meow_log_okblue():
        print_debug_okblue("print_debug_okblue")
        print_debug_okblue("print_debug_okblue, underlined", underlined=True)
        print_debug_okblue("print_debug_okblue, bold", bold=True)
        print_debug_okblue("print_debug_okblue, underlined, bold", underlined=True, bold=True)

    def test_log_okblue(self):
        out = get_redirected_stdout(self.meow_log_okblue)
        correct = (
            b'[test_log_okblue()->get_redirected_stdout()] - print_debug_okblue\x1b[0m\n'
            b'[test_log_okblue()->get_redirected_stdout()] - print_debug_okblue, underlined\x1b[0m\n'
            b'[test_log_okblue()->get_redirected_stdout()] - print_debug_okblue, bold\x1b[0m\n'
            b'[test_log_okblue()->get_redirected_stdout()] - print_debug_okblue, underlined, bold\x1b[0m\n'

        )

        new_stdout, _ = out.remove_timestamp()
        self.assertEqual(correct, new_stdout)
        self.assertEqual(b"", out.bstderr)

    @staticmethod
    def meow_log_okcyan():
        print_debug_okcyan("print_debug_okcyan")
        print_debug_okcyan("print_debug_okcyan, underlined", underlined=True)
        print_debug_okcyan("print_debug_okcyan, bold", bold=True)
        print_debug_okcyan("print_debug_okcyan, underlined, bold", underlined=True, bold=True)

    def test_log_okcyan(self):
        out = get_redirected_stdout(self.meow_log_okcyan)
        correct = (
            b'[test_log_okcyan()->get_redirected_stdout()] - print_debug_okcyan\x1b[0m\n'
            b'[test_log_okcyan()->get_redirected_stdout()] - print_debug_okcyan, underlined\x1b[0m\n'
            b'[test_log_okcyan()->get_redirected_stdout()] - print_debug_okcyan, bold\x1b[0m\n'
            b'[test_log_okcyan()->get_redirected_stdout()] - print_debug_okcyan, underlined, bold\x1b[0m\n'

        )

        new_stdout, _ = out.remove_timestamp()
        self.assertEqual(correct, new_stdout)
        self.assertEqual(b"", out.bstderr)

    @staticmethod
    def meow_log_okgreen():
        print_debug_okgreen("print_debug_okgreen")
        print_debug_okgreen("print_debug_okgreen, underlined", underlined=True)
        print_debug_okgreen("print_debug_okgreen, bold", bold=True)
        print_debug_okgreen("print_debug_okgreen, underlined, bold", underlined=True, bold=True)

    def test_log_okgreen(self):
        out = get_redirected_stdout(self.meow_log_okgreen)
        correct = (
            b'[test_log_okgreen()->get_redirected_stdout()] - print_debug_okgreen\x1b[0m\n'
            b'[test_log_okgreen()->get_redirected_stdout()] - print_debug_okgreen, underlined\x1b[0m\n'
            b'[test_log_okgreen()->get_redirected_stdout()] - print_debug_okgreen, bold\x1b[0m\n'
            b'[test_log_okgreen()->get_redirected_stdout()] - print_debug_okgreen, underlined, bold\x1b[0m\n'

        )

        new_stdout, _ = out.remove_timestamp()
        self.assertEqual(correct, new_stdout)
        self.assertEqual(b"", out.bstderr)

    @staticmethod
    def meow_log_warning():
        print_debug_warning("print_debug_warning")
        print_debug_warning("print_debug_warning, underlined", underlined=True)
        print_debug_warning("print_debug_warning, bold", bold=True)
        print_debug_warning("print_debug_warning, underlined, bold", underlined=True, bold=True)

    def test_log_warning(self):
        out = get_redirected_stdout(self.meow_log_warning)
        correct = (
            b'[test_log_warning()->get_redirected_stdout()] - print_debug_warning\x1b[0m\n'
            b'[test_log_warning()->get_redirected_stdout()] - print_debug_warning, underlined\x1b[0m\n'
            b'[test_log_warning()->get_redirected_stdout()] - print_debug_warning, bold\x1b[0m\n'
            b'[test_log_warning()->get_redirected_stdout()] - print_debug_warning, underlined, bold\x1b[0m\n'
        )
        new_stdout, _ = out.remove_timestamp()
        # print(correct)
        # print(new_stdout)
        self.assertEqual(correct, new_stdout)
        self.assertEqual(b"", out.bstderr)

    @staticmethod
    def meow_log_fail():
        print_debug_fail("print_debug_fail")
        print_debug_fail("print_debug_fail, underlined", underlined=True)
        print_debug_fail("print_debug_fail, bold", bold=True)
        print_debug_fail("print_debug_fail, underlined, bold", underlined=True, bold=True)

    def test_debug_fail(self):
        out = get_redirected_stdout(self.meow_log_fail)
        correct = (
            b'[test_debug_fail()->get_redirected_stdout()] - print_debug_fail\x1b[0m\n'
            b'[test_debug_fail()->get_redirected_stdout()] - print_debug_fail, underlined\x1b[0m\n'
            b'[test_debug_fail()->get_redirected_stdout()] - print_debug_fail, bold\x1b[0m\n'
            b'[test_debug_fail()->get_redirected_stdout()] - print_debug_fail, underlined, bold\x1b[0m\n'
        )
        _, new_stderr = out.remove_timestamp()
        self.assertEqual(b"", out.bstdout)
        self.assertEqual(correct, new_stderr)


if __name__ == "__main__":
    pass

