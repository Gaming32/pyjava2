import timeit
import time

import pyjava

# iteration_count = 100_000
pyjava.init(debug=True)
time.sleep(5)
object_value_of = pyjava.jString.get_static_method('valueOf', pyjava.jint)
# timer = timeit.Timer('object_value_of.invoke_static(5).java_to_string()', globals=globals())
# iteration_count, timing = timer.autorange()
# print('Ran', iteration_count, 'iterations in', timing, 'seconds')
# print('Average time:', timing / iteration_count * 1000, 'ms')
print(object_value_of.invoke_static(5).java_to_string())
