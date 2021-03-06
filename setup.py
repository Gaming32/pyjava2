import subprocess
import sys

from setuptools import setup

from pyjava.util import find_java_executable

ARGS = [
    find_java_executable('javac'),
    '-source', '1.8',
    '-target', '1.8',
    '-d', 'pyjava',
    'PyJavaExecutor.java'
]
print('Running javac with the following arguments:', ' '.join(repr(arg) for arg in ARGS))
subprocess.check_call(ARGS)

if '--no-setup' in sys.argv:
    sys.exit()

# with open('README.md') as fp:
#     LONG_DESCRIPTION = fp.read()

setup(
    name='pyjava2',
    version='0.1',
    description='Call Java from Python',
    # long_description=LONG_DESCRIPTION
    long_description_content_type='text/markdown',
    author='Gaming32',
    author_email='gaming32i64@gmail.com',
    url='https://github.com/Gaming32/pyjava2',
    packages=['pyjava'],
    license='License :: OSI Approved :: MIT License',
    zip_safe=False,
    include_package_data=True,
    package_data={
        'pyjava': ['pyjava/*.class']
    }
)
