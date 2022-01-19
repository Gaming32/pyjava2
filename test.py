import pyjava

# pyjava._execute_command(pyjava.Py2JCommand.SHUTDOWN)
object_value_of = pyjava.jString.get_static_method('valueOf', pyjava.jObject)
print(repr(object_value_of))
print(object_value_of.java_to_string())
