import pyjava

pyjava.init(debug=True)
object_value_of = pyjava.jString.get_static_method('valueOf', pyjava.jObject)
print(object_value_of.invoke_static('Hello, world').java_to_string())
