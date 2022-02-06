import timeit
import time

import pyjava

# iteration_count = 100_000
pyjava.init(debug=True)
time.sleep(5)
# object_value_of = pyjava.jString.get_static_method('valueOf', pyjava.jint)
# # timer = timeit.Timer('object_value_of.invoke_static(5).java_to_string()', globals=globals())
# # iteration_count, timing = timer.autorange()
# # print('Ran', iteration_count, 'iterations in', timing, 'seconds')
# # print('Average time:', timing / iteration_count * 1000, 'ms')
# print(object_value_of.invoke_static(5).java_to_string())

array_class = pyjava.class_for_name('java.lang.reflect.Array')
array_new_instance = array_class.get_static_method('newInstance', pyjava.jClass, pyjava.jint)
array_set = array_class.get_static_method('set', pyjava.jObject, pyjava.jint, pyjava.jObject)

my_array = array_new_instance.invoke_static(pyjava.jString, 3)
array_set.invoke_static(my_array, 0, 'hello')
array_set.invoke_static(my_array, 1, 'world')
array_set.invoke_static(my_array, 2, '123')

print(my_array.java_to_string())
