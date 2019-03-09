from __future__ import print_function, division

import os

from multiprocessing.pool import Pool

import attr

from pathspec import PathSpec
from pathspec.util import normalize_file, match_file
from pathspec.patterns import GitWildMatchPattern
from pathspec import RecursionError as _RecursionError

from dirhash.compat import scandir, DirEntry, fspath


def identity(x):
    return x


def traverse(  # TODO rename scantree
    directory,
    recursion_filter=identity,
    file_apply=identity,
    dir_apply=identity,
    follow_links=True,
    allow_cyclic_links=True,
    cache_file_apply=False,
    include_empty=True,
    jobs=1
):
    _verify_is_directory(directory)

    if jobs is None or jobs > 1:
        return _traverse_multiprocess(**vars())

    path = RecursionPath.from_root(directory)

    if cache_file_apply:
        file_apply = _cached_by_realpath(file_apply)

    root_dir_node = _traverse_recursive(
        path=path,
        filter_=recursion_filter,
        file_apply=file_apply,
        dir_apply=dir_apply,
        follow_links=follow_links,
        allow_cyclic_links=allow_cyclic_links,
        include_empty=include_empty,
        parents={path.real: path},
    )
    result = dir_apply(root_dir_node)

    return result


def _traverse_multiprocess(**kwargs):
    file_apply = kwargs.pop('file_apply')
    dir_apply = kwargs.pop('dir_apply')
    jobs = kwargs.pop('jobs')

    file_paths = []

    def extract_paths(path):
        result_idx = len(file_paths)
        file_paths.append(path)
        return result_idx

    root_dir_node = traverse(file_apply=extract_paths, dir_apply=identity, **kwargs)

    pool = Pool(jobs)
    try:
        file_results = pool.map(file_apply, file_paths)
    finally:
        pool.close()

    def fetch_result(result_idx):
        return file_results[result_idx]

    return root_dir_node.apply(dir_apply=dir_apply, file_apply=fetch_result)


def _verify_is_directory(directory):
    directory = fspath(directory)
    if not os.path.exists(directory):
        raise ValueError('{}: No such directory'.format(directory))
    if not os.path.isdir(directory):
        raise ValueError('{}: Is not a directory'.format(directory))


def _cached_by_realpath(file_apply):
    cache = {}

    def file_apply_cached(path):
        if path.real not in cache:
            cache[path.real] = file_apply(path)
        return cache[path.real]

    return file_apply_cached


def _traverse_recursive(
    path,
    filter_,
    file_apply,
    dir_apply,
    follow_links,
    allow_cyclic_links,
    include_empty,
    parents,
):
    """TODO"""
    fwd_kwargs = vars()
    del fwd_kwargs['path']

    if path.is_symlink():
        if not follow_links:
            return LinkedDir(path)
        previous_path = parents.get(path.real, None)
        if previous_path is not None:
            if allow_cyclic_links:
                return CyclicLinkedDir(path, previous_path)
            else:
                raise SymlinkRecursionError(path, previous_path)

    if follow_links:
        parents[path.real] = path

    dirs = []
    files = []
    for subpath in filter_(path.scandir()):
        if subpath.is_dir():
            dir_node = _traverse_recursive(subpath, **fwd_kwargs)
            if (  # linked dirs does not implement `empty`
                isinstance(dir_node, LinkedDir) or
                include_empty or not dir_node.empty
            ):
                dirs.append(dir_apply(dir_node))
        if subpath.is_file():
            files.append(file_apply(subpath))

    if follow_links:
        del parents[path.real]

    return DirNode(path=path, directories=dirs, files=files)


@attr.s(slots=True)
class RecursionPath(object):
    root = attr.ib()
    relative = attr.ib()
    real = attr.ib()
    _dir_entry = attr.ib()
    """Track the recursion path.

    So why not use pathlib.Path:
    - keep track of real path but only do fs check on follow link
    - use scandir/DirEntry's caching of e.g. is_dir/is_file for speedup.
    """
    @classmethod
    def from_root(cls, directory):
        if isinstance(directory, (DirEntry, DirEntryReplacement)):
            dir_entry = directory
        else:
            dir_entry = DirEntryReplacement.from_path(directory)
        return cls(
            root=dir_entry.path,
            relative='',
            real=os.path.realpath(dir_entry.path),
            dir_entry=dir_entry
        )

    def scandir(self):
        return (self._join(dir_entry) for dir_entry in scandir(self.absolute))

    def _join(self, dir_entry):
        relative = os.path.join(self.relative, dir_entry.name)
        real = os.path.join(self.real, dir_entry.name)
        if dir_entry.is_symlink():
            real = os.path.realpath(real)

        return attr.evolve(self, relative=relative, real=real, dir_entry=dir_entry)

    @property
    def absolute(self):
        return os.path.join(self.root, self.relative)

    @property
    def path(self):
        return self._dir_entry.path

    @property
    def name(self):
        return self._dir_entry.name

    def is_dir(self, follow_symlinks=True):
        return self._dir_entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, follow_symlinks=True):
        return self._dir_entry.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self):
        return self._dir_entry.is_symlink()

    def stat(self, follow_symlinks=True):
        return self._dir_entry.stat(follow_symlinks=follow_symlinks)

    def inode(self):
        return self._dir_entry.inode()

    def __fspath__(self):
        return self.real

    @staticmethod
    def _getstate(self):
        return (
            self.root,
            self.relative,
            self.real,
            DirEntryReplacement.from_dir_entry(self._dir_entry)
        )

    @staticmethod
    def _setstate(self, state):
        self.root, self.relative, self.real, self._dir_entry = state


# Attrs overrides __get/setstate__ for slotted classes, see:
# https://github.com/python-attrs/attrs/issues/512
RecursionPath.__getstate__ = RecursionPath._getstate
RecursionPath.__setstate__ = RecursionPath._setstate


@attr.s(slots=True, cmp=False)
class DirEntryReplacement(object):
    path = attr.ib(converter=fspath)
    name = attr.ib()
    _is_dir = attr.ib(init=False, default=None)
    _is_file = attr.ib(init=False, default=None)
    _is_symlink = attr.ib(init=False, default=None)
    _stat_sym = attr.ib(init=False, default=None)
    _stat_nosym = attr.ib(init=False, default=None)

    @classmethod
    def from_path(cls, path):
        path = fspath(path)
        if not os.path.exists(path):
            raise IOError('{} does not exist'.format(path))
        basename = os.path.basename(path)
        if basename in ['', '.', '..']:
            name = os.path.basename(os.path.realpath(path))
        else:
            name = basename
        return cls(path, name)

    @classmethod
    def from_dir_entry(cls, dir_entry):
        return cls(dir_entry.path, dir_entry.name)

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
                self._stat_sym = os.stat(self.path)
            return self._stat_sym

        if self._stat_nosym is None:
            self._stat_nosym = os.lstat(self.path)
        return self._stat_nosym

    def inode(self):
        return self.stat(follow_symlinks=False).st_ino

    def __eq__(self, other):
        if not isinstance(other, (DirEntryReplacement, DirEntry)):
            return False
        if not self.path == other.path:
            return False
        if not self.name == other.name:
            return False
        for method, kwargs in [
            ('is_dir', {'follow_symlinks': True}),
            ('is_dir', {'follow_symlinks': False}),
            ('is_file', {'follow_symlinks': True}),
            ('is_file', {'follow_symlinks': False}),
            ('is_symlink', {}),
            ('stat', {'follow_symlinks': True}),
            ('stat', {'follow_symlinks': False}),
            ('inode', {})
        ]:
            this_res = getattr(self, method)(**kwargs)
            other_res = getattr(other, method)(**kwargs)
            if not this_res == other_res:
                return False

        return True


class SymlinkRecursionError(_RecursionError):
    """Raised when symlinks cause a cyclic graph of directories.

    Extends the `pathspec.util.RecursionError` but with a different name (avoid
    overriding the built-in error!) and with a more informative string representation
    (used in `dirhash.cli`).
    """
    def __init__(self, path, target_path):
        super(SymlinkRecursionError, self).__init__(
            real_path=path.real,
            first_path=os.path.join(target_path.root, target_path.relative),
            second_path=os.path.join(path.root, path.relative)
        )

    def __str__(self):
        # _RecursionError.__str__ prints args without context
        return 'Symlink recursion: {}'.format(self.message)


@attr.s(slots=True, frozen=True)
class DirNode(object):
    path = attr.ib(validator=attr.validators.instance_of(RecursionPath))
    directories = attr.ib(default=tuple(), converter=tuple)
    files = attr.ib(default=tuple(), converter=tuple)

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

    def leafpaths(self):
        leafs = []

        def file_apply(path):
            leafs.append(path)

        def dir_apply(dir_node):
            if isinstance(dir_node, (LinkedDir, CyclicLinkedDir)) or dir_node.empty:
                leafs.append(dir_node.path)

        self.apply(dir_apply=dir_apply, file_apply=file_apply)

        return sorted(leafs, key=lambda path: path.relative)

    def filepaths(self):  # TODO test
        files = []

        def file_apply(path):
            files.append(path)

        self.apply(dir_apply=identity, file_apply=file_apply)

        return sorted(files, key=lambda path: path.relative)


@attr.s(slots=True, frozen=True)
class LinkedDir(object):
    path = attr.ib(validator=attr.validators.instance_of(RecursionPath))

    @property
    def empty(self):
        raise NotImplementedError('`empty` is undefined for `LinkedDir` nodes.')

    def apply(self, dir_apply, file_apply=None):
        return dir_apply(self)


@attr.s(slots=True, frozen=True)
class CyclicLinkedDir(object):
    path = attr.ib(validator=attr.validators.instance_of(RecursionPath))
    target_path = attr.ib(validator=attr.validators.instance_of(RecursionPath))

    @property
    def empty(self):
        """A cyclic linked dir is never empty."""
        return False

    def apply(self, dir_apply, file_apply=None):
        return dir_apply(self)


class RecursionFilter(object):

    def __init__(
        self,
        linked_dirs=True,
        linked_files=True,
        match=None,
    ):
        self.linked_dirs = linked_dirs
        self.linked_files = linked_files
        self._match_patterns = tuple('*') if match is None else tuple(match)
        if self._match_patterns != tuple('*'):
            self._path_spec = PathSpec.from_lines(
                GitWildMatchPattern,
                self.match_patterns
            )
        else:
            self._path_spec = None

    @property
    def match_patterns(self):
        return self._match_patterns

    def include(self, recursion_path):
        if recursion_path.is_symlink():
            if recursion_path.is_dir() and not self.linked_dirs:
                return False
            if recursion_path.is_file() and not self.linked_files:
                return False

        if recursion_path.is_dir():
            # only filepaths matched against patterns
            return True

        return self.match_file(recursion_path.relative)

    def match_file(self, filepath):
        if self._path_spec is None:
            return True
        return match_file(self._path_spec.patterns, normalize_file(filepath))

    def __call__(self, paths):
        for path in paths:
            if self.include(path):
                yield path
