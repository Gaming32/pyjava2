import pyjava

# pyjava.init(debug=True)
object_value_of = pyjava.jString.get_static_method('valueOf', pyjava.jint)
print(object_value_of.invoke_static(5).java_to_string())
