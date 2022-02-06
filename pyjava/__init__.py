import abc
import atexit
import enum
import os
import struct
from asyncio import subprocess
from subprocess import Popen
from typing import (Any, Callable, Dict, Generic, Iterable, List, Literal,
                    Mapping, Optional, Sequence, Tuple, Type, TypeVar, Union,
                    cast, overload)
from weakref import WeakValueDictionary

from pyjava.util import find_java_executable

_T = TypeVar('_T', int, float)
_java_popen: Optional[Popen[str]] = None

INTEGER_MAX_VALUE = (1 << 31) - 1


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
    INVOKE_METHOD = 7
    GET_OBJECT_CLASS = 8

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
    INT_STRING_PAIR_RESULT = 6

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
    if isinstance(obj, ClassProxy):
        if obj.object_index < 0:
            return _ArbitraryTemporaryProxy(obj.object_index - 8)
        return obj
    elif isinstance(obj, AbstractObjectProxy):
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


def _write_maybe_int(*s: Union[str, int], bit_size: int = 32) -> None:
    popen = _maybe_init()
    assert popen.stdin is not None
    for v in s:
        if isinstance(v, int):
            v = _int_to_str(v, bit_size)
        popen.stdin.write(v)
    popen.stdin.flush()


def _write_command(command: Py2JCommand) -> None:
    _write(command.command_char)


def _write_int(i: int, bit_size: int = 32) -> None:
    _write(_int_to_str(i, bit_size))


def _write_str(s: str) -> None:
    _write_maybe_int(len(s), s)


def _read_int() -> int:
    popen = _maybe_init()
    assert popen.stdout is not None
    value = int(popen.stdout.read(8), 16)
    if value > INTEGER_MAX_VALUE:
        value -= 1 << 32
    return value


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

@overload
def _execute_command(command: Literal[Py2JCommand.INVOKE_METHOD], method_index: int, object_index: int, method_args: Sequence['AbstractObjectProxy']) -> int: ...

@overload
def _execute_command(command: Literal[Py2JCommand.GET_OBJECT_CLASS], id: int) -> Tuple[int, str]: ...

def _execute_command(command: Py2JCommand, *args):
    _write_command(command)
    if command in (Py2JCommand.GET_CLASS, Py2JCommand.CREATE_STRING):
        assert len(args) == 1
        name_or_string = cast(str, args[0])
        _write_str(name_or_string)
    elif command in (Py2JCommand.FREE_OBJECT, Py2JCommand.TO_STRING, Py2JCommand.GET_OBJECT_CLASS):
        assert len(args) == 1
        index = cast(int, args[0])
        _write_int(index)
    elif command == Py2JCommand.GET_METHOD:
        assert len(args) == 3
        class_index = cast(int, args[0])
        name = cast(str, args[1])
        types = cast(Sequence[ClassProxy], args[2])
        _write_maybe_int(
            class_index,
            len(name), name,
            len(types),
            *(type.object_index for type in types)
        )
    elif command == Py2JCommand.INVOKE_STATIC_METHOD:
        assert len(args) == 2
        method_index = cast(int, args[0])
        method_args = cast(Sequence[ClassProxy], args[1])
        _write_maybe_int(method_index, len(method_args))
        for arg in method_args:
            arg.write()
    elif command == Py2JCommand.INVOKE_METHOD:
        assert len(args) == 3
        method_index = cast(int, args[0])
        object_index = cast(int, args[1])
        method_args = cast(Sequence[ClassProxy], args[2])
        _write_maybe_int(method_index, object_index, len(method_args))
        for arg in method_args:
            arg.write()
    popen = _maybe_init()
    assert popen.stdout is not None
    while True:
        command_str = popen.stdout.read(1)
        if command_str:
            recv_command = J2PyCommand(int(command_str, 36))
        else:
            recv_command = J2PyCommand.SHUTDOWN
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
            _loaded_classes_by_id.clear()
            _loaded_methods.clear()
            _loaded_objects.clear()
            popen.wait()
            return None
        elif recv_command == J2PyCommand.PRINT_OUT:
            print(_read_str())
        elif recv_command == J2PyCommand.STRING_RESULT:
            return _read_str()
        elif recv_command == J2PyCommand.INT_STRING_PAIR_RESULT:
            return _read_int(), _read_str()


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
        args.append('-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,quiet=y,address=8000')
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


class _ArbitraryTemporaryProxy(AbstractObjectProxy):
    def __init__(self, ix: int) -> None:
        self.object_index = ix

    def java_to_string(self) -> str:
        raise NotImplementedError

    def __del__(self) -> None:
        pass


class ClassProxy(AbstractObjectProxy):
    name: str
    object_index: int

    def __init__(self, name: str, index: int) -> None:
        self.name = name
        self.object_index = index
        _loaded_classes[name] = self
        _loaded_classes_by_id[index] = self

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f'<ClassProxy name={self.name} id={self.object_index}>'

    def __del__(self) -> None:
        try:
            _loaded_classes.pop(self.name, None)
        except Exception:
            pass
        try:
            _loaded_classes_by_id.pop(self.object_index, None)
        except Exception:
            pass
        if _java_popen is not None:
            try:
                _execute_command(Py2JCommand.FREE_OBJECT, self.object_index)
            except Exception:
                pass

    def get_method(self, name: str, *types: 'ClassProxy') -> 'MethodProxy':
        if (self, name) in _loaded_methods:
            return _loaded_methods[(self, name)]
        return MethodProxy(self, name, _execute_command(Py2JCommand.GET_METHOD, self.object_index, name, types), types)

_loaded_classes: WeakValueDictionary[str, ClassProxy] = WeakValueDictionary()
_loaded_classes_by_id: WeakValueDictionary[int, ClassProxy] = WeakValueDictionary()


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

def class_for_name(name: str) -> ClassProxy:
    if name in _DEFAULT_CLASSES:
        return _DEFAULT_CLASSES[name]
    if name in _loaded_classes:
        return _loaded_classes[name]
    return ClassProxy(name, _execute_command(Py2JCommand.GET_CLASS, name))

def _class_by_id(id: int, name: str) -> ClassProxy:
    if id in _loaded_classes_by_id:
        return _loaded_classes_by_id[id]
    return ClassProxy(name, id)


class ObjectMethodProxy:
    method: 'MethodProxy'
    on: Optional[AbstractObjectProxy]

    def __init__(self,
            method: 'MethodProxy',
            on: Optional[AbstractObjectProxy] = None
        ) -> None:
        self.method = method
        self.on = on

    def __call__(self, *args: Any) -> AbstractObjectProxy:
        if self.on is None:
            return self.method.invoke_static(*args)
        return self.method.invoke_instance(self.on, *args)


class MethodProxy(AbstractObjectProxy):
    owner: ClassProxy
    name: str
    object_index: int
    types: Sequence[ClassProxy]
    on: Optional[AbstractObjectProxy]

    def __init__(self,
            owner: ClassProxy,
            name: str,
            index: int,
            types: Sequence[ClassProxy]
        ) -> None:
        self.name = name
        self.owner = owner
        self.object_index = index
        self.types = types
        _loaded_methods[(owner, name)] = self

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

    def static_callable(self) -> ObjectMethodProxy:
        return ObjectMethodProxy(self)

    def invoke_instance(self, on: AbstractObjectProxy, *args: Any) -> AbstractObjectProxy:
        send_args: List[AbstractObjectProxy] = []
        for (arg, type) in zip(args, self.types):
            send_args.append(_pyobject_to_jobject(arg, type))
        return _get_proxied_object(_execute_command(Py2JCommand.INVOKE_METHOD, self.object_index, on.object_index, send_args))

    def instance_callable(self, on: AbstractObjectProxy) -> ObjectMethodProxy:
        return ObjectMethodProxy(self, on)

_loaded_methods: WeakValueDictionary[Tuple[ClassProxy, str], MethodProxy] = WeakValueDictionary()


class ObjectProxy(AbstractObjectProxy):
    _klass: Optional[ClassProxy]

    def __init__(self, index: int, klass: Optional[ClassProxy] = None) -> None:
        self.object_index = index
        self._klass = klass
        _loaded_objects[index] = self

    def get_class(self) -> ClassProxy:
        if self._klass is None:
            id, name = _execute_command(Py2JCommand.GET_OBJECT_CLASS, self.object_index)
            self._klass = _class_by_id(id, name)
            # raise ValueError('No class known') # TODO: Get class through call
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

    def get_method(self, name: str, *types: 'ClassProxy') -> ObjectMethodProxy:
        return self.get_class().get_method(name, *types).instance_callable(self)

_loaded_objects: WeakValueDictionary[int, ObjectProxy] = WeakValueDictionary()

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
