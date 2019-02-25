from __future__ import print_function, division

import os

from collections import namedtuple

# Use the built-in version of scandir/walk if possible (python > 3.5),
# otherwise use the scandir module version
try:
    from os import scandir
    from posix import DirEntry
except ImportError:  # pragma: no cover
    from scandir import scandir, DirEntry


def identity(x):
    return x


def traverse(
    directory,
    recursion_filter=identity,
    file_apply=identity,
    dir_apply=identity,
    follow_symlinks=True
):
    path = RecursionPath.from_root(directory)
    dir_node = _traverse_recursive(
        path=path,
        filter_=recursion_filter,
        file_apply=file_apply,
        dir_apply=dir_apply,
        follow_symlinks=follow_symlinks,
        parents={path.real: path},
    )
    result = dir_apply(dir_node)
    return result


def _traverse_recursive(
    path,
    filter_,
    file_apply,
    dir_apply,
    follow_symlinks,
    parents,
):
    """TODO"""
    fwd_kwargs = vars()
    del fwd_kwargs['path']

    if path.is_symlink():
        if not follow_symlinks:
            return LinkedDir(path)
        previous_path = parents.get(path.real, None)
        if previous_path is not None:
            return CyclicLinkedDir(path, previous_path)

    if follow_symlinks:
        parents[path.real] = path

    dirs = []
    files = []
    for subpath in filter_(path.scandir()):
        if subpath.is_dir():
            dirs.append(dir_apply(_traverse_recursive(subpath, **fwd_kwargs)))
        if subpath.is_file():
            files.append(file_apply(FileNode(subpath)))

    if follow_symlinks:
        del parents[path.real]

    return DirNode(path=path, directories=dirs, files=files)


class RecursionPath(
    namedtuple(
        'RecursionPath',
        ['root', 'relative', 'real', 'dir_entry']
    )
):
    """Track the recursion path."""

    @classmethod
    def from_root(cls, directory):
        if isinstance(directory, DirEntry):
            dir_entry = directory
        else:
            dir_entry = DirEntryReplacement(directory)
        return cls(
            root=dir_entry.path,
            relative='',
            real=os.path.realpath(dir_entry.path),
            dir_entry=dir_entry
        )

    def scandir(self):
        return (self.join(dir_entry) for dir_entry in scandir(self.real))

    def join(self, dir_entry):
        relative = os.path.join(self.relative, dir_entry.name)
        real = os.path.join(self.real, dir_entry.name)
        if dir_entry.is_symlink():
            real = os.path.realpath(real)

        return self._replace(
            relative=relative,
            real=real,
            dir_entry=dir_entry
        )

    def is_dir(self, follow_symlinks=True):
        return self.dir_entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, follow_symlinks=True):
        return self.dir_entry.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self):
        return self.dir_entry.is_symlink()

    def stat(self, follow_symlinks=True):
        return self.dir_entry.stat(follow_symlinks=follow_symlinks)

    def inode(self):
        return self.dir_entry.inode()


class DirEntryReplacement(object):

    def __init__(self, path):
        if not os.path.exists(path):
            raise ValueError('{} does not exist'.format(path))
        self.path = path
        basename = os.path.basename(path)
        if basename in ['', '.', '..']:
            self.name = os.path.basename(os.path.realpath(path))
        else:
            self.name = basename
        self._is_dir = None
        self._is_file = None
        self._is_symlink = None
        self._stat_sym = None
        self._stat_nosym = None
        self._inode = None

    def is_dir(self, follow_symlinks=True):
        if self._is_dir is None:
            self._is_dir = os.path.isdir(self.path)
        if follow_symlinks:
            return self._is_dir
        else:
            return self._is_dir and not self.is_symlink()

    def is_file(self, follow_symlinks=True):
        if self._is_file is None:
            self._is_file = os.path.isfile(self.path)
        if follow_symlinks:
            return self._is_file
        else:
            return self._is_file and not self.is_symlink()

    def is_symlink(self):
        if self._is_symlink is None:
            self._is_symlink = os.path.islink(self.path)
        return self._is_symlink

    def stat(self, follow_symlinks=True):
        if follow_symlinks:
            if self._stat_sym is None:
                self._stat_sym = os.stat(self.path, follow_symlinks=True)
            return self._stat_sym

        if self._stat_nosym is None:
            self._stat_nosym = os.stat(self.path, follow_symlinks=False)
        return self._stat_nosym

    def inode(self):
        return self.stat(follow_symlinks=False).st_ino


class RecursionFilter(object):

    def __init__(self):
        pass

    def __call__(self, paths):
        raise NotImplementedError()


class _DirEntryInterface(object):

    # alt:
    # def __getattr__(self, item):
    #     if hasattr(self.path.dir_entry, item):
    #         return getattr(self.path.dir_entry, item)
    #     else:
    #         raise AttributeError('')

    def is_dir(self, follow_symlinks=True):
        return self.path.dir_entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, follow_symlinks=True):
        return self.path.dir_entry.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self):
        return self.path.dir_entry.is_symlink()

    def stat(self, follow_symlinks=True):
        return self.path.dir_entry.stat(follow_symlinks=follow_symlinks)

    def inode(self):
        return self.path.dir_entry.inode()


class DirNode(
    namedtuple('DirNode', ['path', 'directories', 'files']),
    _DirEntryInterface
):

    @property
    def empty(self):
        return not (self.directories or self.files)

    def apply(self, dir_apply, file_apply):
        dir_node = DirNode(
            self.path,
            [dir_.apply(dir_apply, file_apply) for dir_ in self.directories],
            [file_apply(file_) for file_ in self.files]
        )
        return dir_apply(dir_node)


class FileNode(namedtuple('FileNode', ['path']), _DirEntryInterface):
    pass


class LinkedDir(namedtuple('LinkedDir', ['path']), _DirEntryInterface):
    pass


class CyclicLinkedDir(
    namedtuple('CyclicLinkedDir', ['path', 'target_path']),
    _DirEntryInterface
):
    pass
