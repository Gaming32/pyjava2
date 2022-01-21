import abc
import atexit
import enum
import os
from asyncio import subprocess
import struct
from subprocess import Popen
from typing import Any, Dict, Generic, Iterable, List, Literal, Optional, Sequence, Tuple, Type, TypeVar, Union, cast, overload

from pyjava.util import find_java_executable

_T = TypeVar('_T', int, float)
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


_DIGIT_CHARS = '0123456789abcdefghijklmnopqrstuvwxyz'

class Py2JCommand(enum.IntEnum):
    SHUTDOWN = 0
    GET_CLASS = 1
    FREE_OBJECT = 2
    GET_METHOD = 3
    TO_STRING = 4
    CREATE_STRING = 5
    INVOKE_STATIC_METHOD = 6

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


def _int_to_str(i: int, bit_size: int = 32) -> str:
    result = []
    if i < 0:
        i += 1 << bit_size # Make unsigned
    bits_written = 0
    while i and bits_written < bit_size:
        next = i >> 4
        result.append(_DIGIT_CHARS[i - (next << 4)])
        i = next
        bits_written += 4
    return ''.join(reversed(result)).zfill(bit_size >> 2)


def _pyobject_to_jobject(obj: Any, preferred_type: Optional['ClassProxy'] = None) -> 'AbstractObjectProxy':
    if isinstance(obj, AbstractObjectProxy):
        return obj # Everything is casted anyway, so we don't need to cast here
    elif isinstance(obj, str):
        return _get_proxied_object(_execute_command(Py2JCommand.CREATE_STRING, obj))
    elif isinstance(obj, (int, float)):
        if preferred_type is None or preferred_type == jObject:
            return PrimitiveObjectProxy(
                jint.object_index if isinstance(obj, int) else jdouble.object_index,
                obj
            )
        elif preferred_type.object_index in (jfloat, jdouble):
            return PrimitiveObjectProxy(preferred_type.object_index, float(obj))
        elif 0 > preferred_type.object_index > jdouble.object_index:
            return PrimitiveObjectProxy(preferred_type.object_index, int(obj))
    raise ValueError(f'Currently unsupported type: {type(obj)}')


def _write(*s: str) -> None:
    popen = _maybe_init()
    assert popen.stdin is not None
    for v in s:
        popen.stdin.write(v)
    popen.stdin.flush()


def _write_command(command: Py2JCommand) -> None:
    _write(command.command_char)


def _write_int(i: int, bit_size: int = 32) -> None:
    _write(_int_to_str(i, bit_size))


def _write_str(s: str) -> None:
    _write(_int_to_str(len(s)), s)


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
def _execute_command(command: Literal[Py2JCommand.GET_METHOD], class_index: int, name: str, types: Sequence['ClassProxy']) -> int: ...

@overload
def _execute_command(command: Literal[Py2JCommand.TO_STRING], index: int) -> str: ...

@overload
def _execute_command(command: Literal[Py2JCommand.CREATE_STRING], s: str) -> int: ...

@overload
def _execute_command(command: Literal[Py2JCommand.INVOKE_STATIC_METHOD], method_index: int, method_args: Sequence['AbstractObjectProxy']) -> int: ...

def _execute_command(command: Py2JCommand, *args):
    _write_command(command)
    if command in (Py2JCommand.GET_CLASS, Py2JCommand.CREATE_STRING):
        assert len(args) == 1
        name_or_string = cast(str, args[0])
        _write_str(name_or_string)
    elif command in (Py2JCommand.FREE_OBJECT, Py2JCommand.TO_STRING):
        assert len(args) == 1
        index = cast(int, args[0])
        _write_int(index)
    elif command == Py2JCommand.GET_METHOD:
        assert len(args) == 3
        class_index = cast(int, args[0])
        name = cast(str, args[1])
        types = cast(Sequence[ClassProxy], args[2])
        _write_int(class_index)
        _write_str(name)
        _write_int(len(types))
        for type in types:
            _write_int(type.object_index)
    elif command == Py2JCommand.INVOKE_STATIC_METHOD:
        assert len(args) == 2
        method_index = cast(int, args[0])
        method_args = cast(Sequence[ClassProxy], args[1])
        _write_int(method_index)
        _write_int(len(method_args))
        for arg in method_args:
            arg.write()
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
            _loaded_objects.clear()
            return None
        elif recv_command == J2PyCommand.PRINT_OUT:
            print(_read_str())
        elif recv_command == J2PyCommand.STRING_RESULT:
            return _read_str()


def init(
    java_executable: Optional[str] = None,
    class_path: Optional[List[str]] = None,
    debug: bool = False
) -> Popen:
    global _java_popen
    if java_executable is None:
        java_executable = find_java_executable('java')
    if class_path is None:
        class_path = []
    class_path.insert(1, os.path.dirname(__file__))
    args = [java_executable]
    if debug:
        args.append('-Dpyjava.debug=true')
    args.extend((
        '-classpath', os.pathsep.join(class_path),
        'PyJavaExecutor'
    ))
    if debug:
        import shlex
        print(*(shlex.quote(arg) for arg in args))
    _java_popen = Popen(
        args,
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

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, AbstractObjectProxy):
            return self.object_index == other.object_index
        elif isinstance(other, int):
            return self.object_index == other
        return NotImplemented

    def __hash__(self) -> int:
        return self.object_index

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} id={self.object_index}>'

    def java_to_string(self) -> str:
        return _execute_command(Py2JCommand.TO_STRING, self.object_index)

    def write(self) -> None:
        _write_int(self.object_index)


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
        return MethodProxy(self, name, _execute_command(Py2JCommand.GET_METHOD, self.object_index, name, types), types)


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
jClass = ClassProxy('java.lang.Class', -11)

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
        jClass,
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
    types: Sequence[ClassProxy]

    def __init__(self, owner: ClassProxy, name: str, index: int, types: Sequence[ClassProxy]) -> None:
        self.name = name
        self.owner = owner
        self.object_index = index
        self.types = types
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

    def invoke_static(self, *args: Any) -> AbstractObjectProxy:
        send_args: List[AbstractObjectProxy] = []
        for (arg, type) in zip(args, self.types):
            send_args.append(_pyobject_to_jobject(arg, type))
        return _get_proxied_object(_execute_command(Py2JCommand.INVOKE_STATIC_METHOD, self.object_index, send_args))

_loaded_methods: Dict[Tuple[ClassProxy, str], MethodProxy] = {}


class ObjectProxy(AbstractObjectProxy):
    _klass: Optional[ClassProxy]

    def __init__(self, index: int, klass: Optional[ClassProxy] = None) -> None:
        self.object_index = index
        self._klass = klass
        _loaded_objects[index] = self

    def get_class(self) -> ClassProxy:
        if self._klass is None:
            raise ValueError('No class known') # TODO: Get class through call
        return self._klass

    def __del__(self) -> None:
        try:
            _loaded_objects.pop(self.object_index, None)
        except Exception:
            pass
        if _java_popen is not None:
            try:
                _execute_command(Py2JCommand.FREE_OBJECT, self.object_index)
            except Exception:
                pass
        del self._klass # Probably doesn't do anything lol

_loaded_objects: Dict[int, ObjectProxy] = {}

def _get_proxied_object(id: int) -> ObjectProxy:
    if id in _loaded_objects:
        return _loaded_objects[id]
    return ObjectProxy(id)


_FLOAT_STRUCT = struct.Struct('>f')
_DOUBLE_STRUCT = struct.Struct('>d')

class PrimitiveObjectProxy(AbstractObjectProxy, Generic[_T]):
    value: _T

    def __init__(self, type: int, value: _T) -> None:
        self.object_index = type
        self.value = value

    def __del__(self) -> None:
        pass # Override and do nothing

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, PrimitiveObjectProxy):
            return self.object_index == other.object_index and self.value == other.value
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.object_index, self.value))

    def __repr__(self) -> str:
        return f'<PrimitiveObjectProxy type={self.object_index} value={self.value}>'

    def write(self) -> None:
        _write_int(self.object_index)
        if self.object_index < jfloat.object_index:
            # Two words
            if self.object_index == jdouble:
                _write(_DOUBLE_STRUCT.pack(self.value).hex())
            else:
                _write_int(int(self.value), 64)
        else:
            # One word
            if self.object_index == jfloat:
                _write(_FLOAT_STRUCT.pack(self.value).hex())
            else:
                _write_int(int(self.value))


atexit.register(quit)
