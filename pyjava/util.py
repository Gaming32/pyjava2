import os


def find_java_executable(name: str) -> str:
    if 'JAVA_HOME' in os.environ:
        java_bin = os.path.join(os.environ['JAVA_HOME'], 'bin')
        if os.path.isdir(java_bin):
            path_ext = os.environ.get('PATHEXT', '').split(os.pathsep)
            exts = [''] + path_ext if (path_ext[0] or len(path_ext) > 1) else ()
            for ext in exts:
                fullname = os.path.join(java_bin, name + ext)
                if os.path.isfile(fullname):
                    return fullname
    return name
