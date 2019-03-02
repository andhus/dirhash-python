from __future__ import print_function, division

from six import string_types


def fspath(path):
    """In python 2: os.path... and scandir does not support PathLike objects"""
    if isinstance(path, string_types):
        return path
    if hasattr(path, '__fspath__'):
        return path.__fspath__()
    raise TypeError('Object {} is not a path'.format(path))


# Use the built-in version of scandir if possible (python > 3.5),
# otherwise use the scandir module version
try:
    from os import scandir
    from posix import DirEntry
except ImportError:
    from scandir import scandir as _scandir
    from scandir import DirEntry

    def scandir(path, *args, **kwargs):
        if path is not None:
            path = fspath(path)
        return _scandir(path, *args, **kwargs)
