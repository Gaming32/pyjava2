import abc
import atexit
import enum
import os
from asyncio import subprocess
from subprocess import Popen
from typing import Dict, List, Literal, Optional, Tuple, Union, cast, overload

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
    FREE_OBJECT = 2
    GET_METHOD = 3
    TO_STRING = 4

    @property
    def command_char(self) -> str:
        return _DIGIT_CHARS[self]


class J2PyCommand(enum.IntEnum):
    SHUTDOWN = 0
    PRINT_OUT = 1
    INT_RESULT = 2
    ERROR_RESULT = 3
    VOID_RESULT = 4
    STRING_RESULT = 5

    @property
    def command_char(self) -> str:
        return _DIGIT_CHARS[self]


def _int_to_str(i: int) -> str:
    result = []
    if i < 0:
        i += 1 << 32 # Make unsigned
    while i:
        next = i >> 4
        result.append(_DIGIT_CHARS[i - (next << 4)])
        i = next
    return ''.join(reversed(result)).zfill(8)


def _write_command(command: Py2JCommand) -> None:
    popen = _maybe_init()
    assert popen.stdin is not None
    popen.stdin.write(command.command_char)
    popen.stdin.flush()


def _write_int(i: int) -> None:
    popen = _maybe_init()
    assert popen.stdin is not None
    popen.stdin.write(_int_to_str(i))
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
    return int(popen.stdout.read(8), 16)


def _read_str() -> str:
    popen = _maybe_init()
    assert popen.stdout is not None
    return popen.stdout.read(_read_int())


@overload
def _execute_command(command: Literal[Py2JCommand.SHUTDOWN]) -> None: ...

@overload
def _execute_command(command: Literal[Py2JCommand.GET_CLASS], name: str) -> int: ...

@overload
def _execute_command(command: Literal[Py2JCommand.FREE_OBJECT], index: int) -> None: ...

@overload
def _execute_command(command: Literal[Py2JCommand.GET_METHOD], class_index: int, name: str, types: Tuple['ClassProxy']) -> int: ...

@overload
def _execute_command(command: Literal[Py2JCommand.TO_STRING], index: int) -> str: ...

def _execute_command(command: Py2JCommand, *args):
    _write_command(command)
    if command == Py2JCommand.GET_CLASS:
        assert len(args) == 1
        name = cast(str, args[0])
        _write_str(name)
    elif command in (Py2JCommand.FREE_OBJECT, Py2JCommand.TO_STRING):
        assert len(args) == 1
        index = cast(int, args[0])
        _write_int(index)
    elif command == Py2JCommand.GET_METHOD:
        assert len(args) == 3
        class_index = cast(int, args[0])
        name = cast(str, args[1])
        types = cast(Tuple[ClassProxy], args[2])
        _write_int(class_index)
        _write_str(name)
        _write_int(len(types))
        for type in types:
            _write_int(type.object_index)
    popen = _maybe_init()
    assert popen.stdout is not None
    while True:
        recv_command = J2PyCommand(int(popen.stdout.read(1), 36))
        if recv_command == J2PyCommand.ERROR_RESULT:
            raise JavaException(_read_str())
        elif recv_command == J2PyCommand.INT_RESULT:
            return _read_int()
        elif recv_command == J2PyCommand.VOID_RESULT:
            return None
        elif recv_command == J2PyCommand.SHUTDOWN:
            global _java_popen
            _java_popen = None
            _loaded_classes.clear()
            _loaded_methods.clear()
            return None
        elif recv_command == J2PyCommand.PRINT_OUT:
            print(_read_str())
        elif recv_command == J2PyCommand.STRING_RESULT:
            return _read_str()


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


def quit():
    global _java_popen
    if _java_popen is None:
        return
    _execute_command(Py2JCommand.SHUTDOWN)


class AbstractObjectProxy(abc.ABC):
    object_index: int

    def __del__(self) -> None:
        if _java_popen is not None:
            try:
                _execute_command(Py2JCommand.FREE_OBJECT, self.object_index)
            except Exception:
                pass

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} id={self.object_index}>'

    def java_to_string(self) -> str:
        return _execute_command(Py2JCommand.TO_STRING, self.object_index)


class ClassProxy(AbstractObjectProxy):
    name: str
    object_index: int

    def __init__(self, name: str, index: int) -> None:
        self.name = name
        self.object_index = index
        try:
            _loaded_classes[name] = self
        except NameError:
            pass # This is a default class

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<ClassProxy name={self.name} id={self.object_index}>'

    def __del__(self) -> None:
        try:
            _loaded_classes.pop(self.name, None)
        except Exception:
            pass
        if _java_popen is not None:
            try:
                _execute_command(Py2JCommand.FREE_OBJECT, self.object_index)
            except Exception:
                pass

    def get_static_method(self, name: str, *types: 'ClassProxy') -> 'MethodProxy':
        if (self, name) in _loaded_methods:
            return _loaded_methods[(self, name)]
        return MethodProxy(self, name, _execute_command(Py2JCommand.GET_METHOD, self.object_index, name, types))


jbyte = ClassProxy('byte', -1)
jboolean = ClassProxy('boolean', -2)
jshort = ClassProxy('short', -3)
jchar = ClassProxy('char', -4)
jint = ClassProxy('int', -5)
jfloat = ClassProxy('float', -6)
jlong = ClassProxy('long', -7)
jdouble = ClassProxy('double', -8)
jObject = ClassProxy('java.lang.Object', -9)
jString = ClassProxy('java.lang.String', -10)

_DEFAULT_CLASSES: Dict[str, ClassProxy] = {}
for _default_class in (
        jbyte,
        jboolean,
        jshort,
        jchar,
        jint,
        jfloat,
        jlong,
        jdouble,
        jObject,
        jString,
    ):
    _DEFAULT_CLASSES[_default_class.name] = _default_class
_loaded_classes: Dict[str, ClassProxy] = {}

def class_for_name(name: str) -> ClassProxy:
    if name in _DEFAULT_CLASSES:
        return _DEFAULT_CLASSES[name]
    if name in _loaded_classes:
        return _loaded_classes[name]
    return ClassProxy(name, _execute_command(Py2JCommand.GET_CLASS, name))


class MethodProxy(AbstractObjectProxy):
    owner: ClassProxy
    name: str
    object_index: int

    def __init__(self, owner: ClassProxy, name: str, index: int) -> None:
        self.name = name
        self.owner = owner
        self.object_index = index
        try:
            _loaded_methods[(owner, name)] = self
        except NameError:
            pass # This is a default class

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<MethodProxy name={self.name} id={self.object_index}>'

    def __del__(self) -> None:
        try:
            _loaded_methods.pop((self.owner, self.name), None)
        except Exception:
            pass
        if _java_popen is not None:
            try:
                _execute_command(Py2JCommand.FREE_OBJECT, self.object_index)
            except Exception:
                pass

_loaded_methods: Dict[Tuple[ClassProxy, str], MethodProxy] = {}


atexit.register(quit)
