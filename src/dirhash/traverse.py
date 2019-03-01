from __future__ import print_function, division

import os

from collections import namedtuple

# Use the built-in version of scandir/walk if possible (python > 3.5),
# otherwise use the scandir module version
from functools import partial
from multiprocessing.pool import Pool

from dirhash import _get_hasher_factory, _get_filehash

try:
    from os import scandir
    from posix import DirEntry
except ImportError:  # pragma: no cover
    from scandir import scandir, DirEntry

import attr


def identity(x):
    return x


def mpmap(func, iterable, jobs=1):
    if jobs == 1:
        return [func(element) for element in iterable]

    pool = Pool(jobs)
    try:
        results = pool.map(func, iterable)
    finally:
        pool.close()

    return results


def dirhash(
    directory,
    algorithm,
    chunksize=2**20,
    jobs=1
):
    hasher_factory = _get_hasher_factory(algorithm)
    realpaths = set()

    def extract_realpaths(path):
        realpaths.add(path.real)
        return path

    root_node = traverse(directory, file_apply=extract_realpaths)
    realpaths = list(realpaths)

    # hash files in parallel
    file_hashes = mpmap(
        partial(_get_filehash, hasher_factory=hasher_factory, chunk_size=chunksize),
        realpaths,
        jobs=jobs
    )
    # prepare the cache with precomputed file hashes
    realpath_to_hash = dict(zip(realpaths, file_hashes))

    def fetch_filehash(path):
        return path, realpath_to_hash[path.real]

    def get_dirhash(dir_node):
        descriptors = []
        for path, filehash in dir_node.files:
            descriptors.append('_'.join([path.name, filehash]))
        for path, sub_dirhash in dir_node.directories:
            descriptors.append('_'.join([path.name, sub_dirhash]))
        descriptor = '\n'.join(sorted(descriptors) + [''])
        dirhash_ = hasher_factory(descriptor.encode('utf-8')).hexdigest()

        return dir_node.path, dirhash_

    _, root_dirhash = root_node.apply(
        dir_apply=get_dirhash,
        file_apply=fetch_filehash
    )
    return root_dirhash


class DirhashProtocol(object):

    def __init__(self, entry_properties=('data', 'name')):
        self.entry_properties = entry_properties

    def get_descriptor(self, entry_descriptors):
        return '\n'.join(sorted(entry_descriptors) + [''])

    def get_entry_descriptor(self, entry_properties):
        entry_strings = ['{}:{}'.format(k, v) for k, v in entry_properties]
        return '\000'.join(sorted(entry_strings))

    def get_entry_properties(self, path, entry_hash):
        pass # TODO


def traverse(
    directory,
    recursion_filter=identity,
    file_apply=identity,
    dir_apply=identity,
    follow_symlinks=True,
    cache_file_apply=False,
    jobs=1
):
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
        follow_symlinks=follow_symlinks,
        parents={path.real: path},
    )
    result = dir_apply(root_dir_node)

    return result


def _traverse_multiprocess(**kwargs):
    file_apply = kwargs.pop('file_apply')
    dir_apply = kwargs.pop('dir_apply')
    jobs = kwargs.pop('jobs')

    # assume not cache by real
    file_paths = []

    def extract_paths(path):
        # hacky way to support pickling
        # (__set/getstate__ does not work for slotted attrs classes)
        path._dir_entry = DirEntryReplacement.from_dir_entry(path._dir_entry)
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


def _cached_by_realpath(file_apply):
    cache = {}

    def file_apply_cached(path):
        if path.real not in cache:
            cache[path.real] = file_apply(path)
        return cache[path]

    return file_apply_cached


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
            files.append(file_apply(subpath))

    if follow_symlinks:
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
        if isinstance(directory, DirEntry):
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
        return (self._join(dir_entry) for dir_entry in scandir(self.real))

    def _join(self, dir_entry):
        relative = os.path.join(self.relative, dir_entry.name)
        real = os.path.join(self.real, dir_entry.name)
        if dir_entry.is_symlink():
            real = os.path.realpath(real)

        return attr.evolve(self, relative=relative, real=real, dir_entry=dir_entry)

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

    # TODO bellow has no effect when pickling?
    # def __getstate__(self):
    #     return (
    #         self.root,
    #         self.relative,
    #         self.real,
    #         DirEntryReplacement.from_dir_entry(self._dir_entry)
    #     )
    #
    # def __setstate__(self, state):
    #     self.root, self.relative, self.real, self._dir_entry = state


@attr.s(slots=True)
class DirEntryReplacement(object):
    path = attr.ib()
    name = attr.ib()
    _is_dir = attr.ib(default=None)
    _is_file = attr.ib(default=None)
    _is_symlink = attr.ib(default=None)
    _stat_sym = attr.ib(default=None)
    _stat_nosym = attr.ib(default=None)

    @classmethod
    def from_path(cls, path):
        if not os.path.exists(path):
            raise ValueError('{} does not exist'.format(path))
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


class MatchPatterns(RecursionFilter):

    def __init__(self, match_patterns):
        pass


@attr.s(slots=True, frozen=True)
class DirNode(object):
    path = attr.ib(validator=attr.validators.instance_of(RecursionPath))
    directories = attr.ib(converter=tuple)
    files = attr.ib(converter=tuple)

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


@attr.s(slots=True, frozen=True)
class LinkedDir(object):
    path = attr.ib(validator=attr.validators.instance_of(RecursionPath))


@attr.s(slots=True, frozen=True)
class CyclicLinkedDir(object):
    path = attr.ib(validator=attr.validators.instance_of(RecursionPath))
    target_path = attr.ib(validator=attr.validators.instance_of(RecursionPath))
