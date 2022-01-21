import timeit

import pyjava

iteration_count = 100_000
# pyjava.init(debug=True)
object_value_of = pyjava.jString.get_static_method('valueOf', pyjava.jint)
timing = timeit.timeit('object_value_of.invoke_static(5).java_to_string()', number=iteration_count, globals=globals())
print('Ran', iteration_count, 'iterations in', timing, 'seconds')
print('Average time:', timing / iteration_count * 1000, 'ms')
# print(object_value_of.invoke_static(5).java_to_string())
