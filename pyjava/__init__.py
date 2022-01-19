import enum
import os
from asyncio import subprocess
from distutils import command
from subprocess import Popen
from typing import List, Literal, Optional, cast, overload
from unicodedata import name

_java_popen: Optional[Popen[str]] = None


class JavaException(Exception):
    type: str

    def __init__(self, fromstr: str) -> None:
        type, message = fromstr.split(': ', 1)
        self.type = type
        super().__init__(message)

    def __str__(self) -> str:
        return f'{self.type}: {super().__str__()}'


def _maybe_init() -> Popen:
    if _java_popen is None:
        return init()
    return _java_popen


def _find_java() -> str:
    if 'JAVA_HOME' in os.environ:
        JAVA_HOME = os.environ['JAVA_HOME']
        java_executable = os.path.join(JAVA_HOME, 'bin', 'java')
        if os.path.isfile(java_executable):
            return java_executable
    return 'java'


_DIGIT_CHARS = '0123456789abcdefghijklmnopqrstuvwxyz'

class Py2JCommand(enum.IntEnum):
    SHUTDOWN = 0
    GET_CLASS = 1

    @property
    def command_char(self) -> str:
        return _DIGIT_CHARS[self]


class J2PyCommand(enum.IntEnum):
    SHUTDOWN = 0
    PRINT_OUT = 1
    INT_RESULT = 2
    ERROR_RESULT = 3

    @property
    def command_char(self) -> str:
        return _DIGIT_CHARS[self]


def _int_to_str(i: int) -> str:
    result = []
    while i:
        next = i >> 5
        result.append(_DIGIT_CHARS[i - (next << 5)])
        i = next
    return ''.join(reversed(result))


def _write_command(command: Py2JCommand) -> None:
    popen = _maybe_init()
    assert popen.stdin is not None
    popen.stdin.write(command.command_char)
    popen.stdin.flush()


def _write_int(i: int) -> None:
    popen = _maybe_init()
    assert popen.stdin is not None
    popen.stdin.write(_int_to_str(i).zfill(4))
    popen.stdin.flush()


def _write_str(s: str) -> None:
    popen = _maybe_init()
    assert popen.stdin is not None
    _write_int(len(s))
    popen.stdin.write(s)
    popen.stdin.flush()


def _read_int() -> int:
    popen = _maybe_init()
    assert popen.stdout is not None
    return int(popen.stdout.read(4), 32)


def _read_str() -> str:
    popen = _maybe_init()
    assert popen.stdout is not None
    return popen.stdout.read(_read_int())


@overload
def _execute_command(command: Literal[Py2JCommand.GET_CLASS], name: str) -> int: ...

@overload
def _execute_command(command: Literal[Py2JCommand.SHUTDOWN]) -> None: ...

def _execute_command(command: Py2JCommand, *args):
    _write_command(command)
    if command == Py2JCommand.GET_CLASS:
        assert len(args) == 1
        name = cast(str, args[0])
        _write_str(name)
    popen = _maybe_init()
    assert popen.stdout is not None
    while True:
        recv_command = J2PyCommand(int(popen.stdout.read(1), 36))
        if recv_command == J2PyCommand.ERROR_RESULT:
            raise JavaException(_read_str())
        elif recv_command == J2PyCommand.INT_RESULT:
            return _read_int()
        elif recv_command == J2PyCommand.SHUTDOWN:
            global _java_popen
            _java_popen = None
            return None
        elif recv_command == J2PyCommand.PRINT_OUT:
            print(_read_str())


def init(
    java_executable: Optional[str] = None,
    class_path: Optional[List[str]] = None
) -> Popen:
    global _java_popen
    if java_executable is None:
        java_executable = _find_java()
    if class_path is None:
        class_path = []
    class_path.insert(1, os.path.dirname(__file__))
    _java_popen = Popen(
        [
            java_executable,
            '-classpath', os.pathsep.join(class_path),
            'PyJavaExecutor'
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        encoding='latin-1'
    )
    return _java_popen


class ClassProxy:
    name: str
    object_index: int

    def __init__(self, name: str, index: int) -> None:
        self.name = name
        self.object_index = index

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<ClassProxy name={self.name} id={self.object_index}>'


def class_for_name(name: str) -> ClassProxy:
    return ClassProxy(name, _execute_command(Py2JCommand.GET_CLASS, name))
