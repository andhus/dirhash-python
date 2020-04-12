#!/usr/bin/env python
"""dirhash - a python module (and CLI) for hashing of file system directories.

Provides the functions:
- `dirhash`
- `get_leafpaths`.
"""
from __future__ import print_function, division

import os
import hashlib
import pkg_resources

from functools import partial
from multiprocessing import Pool

from scantree import (
    scantree,
    RecursionFilter,
    CyclicLinkedDir,
)

__version__ = pkg_resources.require("dirhash")[0].version

algorithms_guaranteed = {'md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512'}
algorithms_available = hashlib.algorithms_available


def dirhash(
    directory,
    algorithm,
    filtering=None,
    protocol=None,
    chunk_size=2**20,
    jobs=1
):
    filter_ = _get_instance('filtering', filtering, Filter)
    protocol = _get_instance('protocol', protocol, Protocol)
    hasher_factory = _get_hasher_factory(algorithm)
    allow_cyclic_links = protocol.on_cyclic_link != protocol.OnCyclicLink.RAISE

    def dir_apply(dir_node):
        if not filter_.empty_dirs:
            if dir_node.path.relative == '' and dir_node.empty:
                # only check if root node is empty (other empty dirs are filter
                # before `dir_apply` with `filter_.empty_dirs=False`)
                raise ValueError('{}: Nothing to hash'.format(directory))
        descriptor = protocol.get_descriptor(dir_node)
        _dirhash = hasher_factory(descriptor.encode('utf-8')).hexdigest()

        return dir_node.path, _dirhash

    if jobs == 1:
        cache = {}

        def file_apply(path):
            return path, _get_filehash(
                path.real,
                hasher_factory,
                chunk_size=chunk_size,
                cache=cache
            )

        _, dirhash_ = scantree(
            directory,
            recursion_filter=filter_,
            file_apply=file_apply,
            dir_apply=dir_apply,
            follow_links=True,
            allow_cyclic_links=allow_cyclic_links,
            cache_file_apply=False,
            include_empty=filter_.empty_dirs,
            jobs=1
        )
    else:  # multiprocessing
        real_paths = set()

        def extract_real_paths(path):
            real_paths.add(path.real)
            return path

        root_node = scantree(
            directory,
            recursion_filter=filter_,
            file_apply=extract_real_paths,
            follow_links=True,
            allow_cyclic_links=allow_cyclic_links,
            cache_file_apply=False,
            include_empty=filter_.empty_dirs,
            jobs=1
        )
        real_paths = list(real_paths)
        # hash files in parallel
        file_hashes = _parmap(
            partial(
                _get_filehash,
                hasher_factory=hasher_factory,
                chunk_size=chunk_size
            ),
            real_paths,
            jobs=jobs
        )
        # prepare the mapping with precomputed file hashes
        real_path_to_hash = dict(zip(real_paths, file_hashes))

        def file_apply(path):
            return path, real_path_to_hash[path.real]

        _, dirhash_ = root_node.apply(file_apply=file_apply, dir_apply=dir_apply)

    return dirhash_


def get_included_paths(
    directory,
    filtering=None,
    protocol=None
):
    """Inspect what paths are included for the corresponding arguments to the
    `dirhash.dirhash` function.

    # Arguments:
        This function accepts the following subset of the function `dirhash.dirhash`
        arguments: `directory`, `match`, `ignore` `follow_links`, `include_empty`,
        `ignore_extensions` and `ignore_hidden`, with the same meaning. See docs of
        `dirhash.dirhash` for further details.

    # Returns
        A sorted list of the paths ([str]) that would be included in computing the
        hash of `directory` given the provided arguments.
    """
    protocol = _get_instance('protocol', protocol, Protocol)
    filter_ = _get_instance('filtering', filtering, Filter)
    allow_cyclic_links = protocol.on_cyclic_link != protocol.OnCyclicLink.RAISE

    leafpaths = scantree(
        directory,
        recursion_filter=filter_,
        follow_links=True,
        allow_cyclic_links=allow_cyclic_links,
        include_empty=filter_.empty_dirs
    ).leafpaths()

    return [
        path.relative if path.is_file() else os.path.join(path.relative, '.')
        for path in leafpaths
    ]


class Filter(RecursionFilter):

    def __init__(
        self,
        match_patterns=None,
        linked_dirs=True,
        linked_files=True,
        empty_dirs=False
    ):
        super(Filter, self).__init__(
            linked_dirs=linked_dirs,
            linked_files=linked_files,
            match=match_patterns
        )
        self.empty_dirs = empty_dirs


def get_match_patterns(
    match=None,
    ignore=None,
    ignore_extensions=None,
    ignore_hidden=False,
):
    """Combines the different arguments for providing match/ignore-patterns into a
    single list of match-patterns.
    """
    match = ['*'] if match is None else list(match)
    ignore = [] if ignore is None else list(ignore)
    ignore_extensions = [] if ignore_extensions is None else list(ignore_extensions)

    if ignore_hidden:
        ignore.extend(['.*', '.*/'])

    for ext in ignore_extensions:
        if not ext.startswith('.'):
            ext = '.' + ext
        ext = '*' + ext
        ignore.append(ext)

    match_spec = match + ['!' + ign for ign in ignore]

    def deduplicate(items):
        items_set = set([])
        dd_items = []
        for item in items:
            if item not in items_set:
                dd_items.append(item)
                items_set.add(item)

        return dd_items

    return deduplicate(match_spec)


class Protocol(object):

    class OnCyclicLink(object):
        RAISE = 'raise'
        HASH_REFERENCE = 'hash_reference'
        options = {RAISE, HASH_REFERENCE}

    class EntryProperties(object):
        NAME = 'name'
        DATA = 'data'
        IS_LINK = 'is_link'
        options = {NAME, DATA, IS_LINK}
        _DIRHASH = 'dirhash'

    _entry_property_separator = '\000'
    _entry_descriptor_separator = '\000\000'

    def __init__(
        self,
        entry_properties=('name', 'data'),
        on_cyclic_link='raise'
    ):
        entry_properties = set(entry_properties)
        if not entry_properties.issubset(self.EntryProperties.options):
            raise ValueError(
                'entry properties {} not supported'.format(
                    entry_properties - self.EntryProperties.options)
            )
        if not (
            self.EntryProperties.NAME in entry_properties or
            self.EntryProperties.DATA in entry_properties
        ):
            raise ValueError(
                'at least one of entry properties `name` and `data` must be used'
            )
        self.entry_properties = entry_properties
        self._include_name = self.EntryProperties.NAME in entry_properties
        self._include_data = self.EntryProperties.DATA in entry_properties
        self._include_is_link = self.EntryProperties.IS_LINK in entry_properties

        if on_cyclic_link not in self.OnCyclicLink.options:
            raise ValueError(
                '{}: not a valid on_cyclic_link option'.format(on_cyclic_link)
            )
        self.on_cyclic_link = on_cyclic_link

    def get_descriptor(self, dir_node):
        if isinstance(dir_node, CyclicLinkedDir):
            return self._get_cyclic_linked_dir_descriptor(dir_node)

        entries = dir_node.directories + dir_node.files
        entry_descriptors = [
            self._get_entry_descriptor(
                self._get_entry_properties(path, entry_hash)
            ) for path, entry_hash in entries
        ]
        return self._entry_descriptor_separator.join(sorted(entry_descriptors))

    @classmethod
    def _get_entry_descriptor(cls, entry_properties):
        entry_strings = [
            '{}:{}'.format(name, value)
            for name, value in entry_properties
        ]
        return cls._entry_property_separator.join(sorted(entry_strings))

    def _get_entry_properties(self, path, entry_hash):
        properties = []
        if path.is_dir():
            properties.append((self.EntryProperties._DIRHASH, entry_hash))
        elif self._include_data:  # path is file
            properties.append((self.EntryProperties.DATA, entry_hash))

        if self._include_name:
            properties.append((self.EntryProperties.NAME, path.name))
        if self._include_is_link:
            properties.append((self.EntryProperties.IS_LINK, path.is_symlink))

        return properties

    def _get_cyclic_linked_dir_descriptor(self, dir_node):
        relpath = dir_node.path.relative
        target_relpath = dir_node.target_path.relative
        path_to_target = os.path.relpath(
            # the extra '.' is needed if link back to root, because
            # an empty path ('') is not supported by os.path.relpath
            os.path.join('.', target_relpath),
            os.path.join('.', relpath)
        )
        # TODO normalize posix!
        return path_to_target


def _get_hasher_factory(algorithm):
    """Returns a "factory" of hasher instances corresponding to the given algorithm
    name. Bypasses input argument `algorithm` if it is already a hasher factory
    (verified by attempting calls to required methods).
    """
    if algorithm in algorithms_guaranteed:
        return getattr(hashlib, algorithm)

    if algorithm in algorithms_available:
        return partial(hashlib.new, algorithm)

    try:  # bypass algorithm if already a hasher factory
        hasher = algorithm(b'')
        hasher.update(b'')
        hasher.hexdigest()
        return algorithm
    except:
        pass

    raise ValueError(
        '`algorithm` must be one of: {}`'.format(algorithms_available))


def _parmap(func, iterable, jobs=1):
    if jobs == 1:
        return [func(element) for element in iterable]

    pool = Pool(jobs)
    try:
        results = pool.map(func, iterable)
    finally:
        pool.close()

    return results


_old_docs = """
    Computes the hash of a directory based on its structure and content.
    
    # Arguments
        directory (str | pathlib.Path): Path to the directory to hash.
        algorithm (str): The name of the hashing algorithm to use. It is also
            possible to provide a callable object that returns an instance
            implementing the `hashlib._hashlib.HASH` interface.
        match ([str] | None): A list (or iterable) of match-patterns for files to
            include when computing the hash. Default `None` which is equivalent to
            `['*']`, i.e. everything is included. See "Path Selection and Filtering"
            below for further details.
        ignore ([str] | None): A list (or iterable) of match-patterns for files to
            ignore when computing the hash. Default `None` (no ignore patterns). See
            "Path Selection and Filtering" below for further details.
        chunk_size (int): The number of bytes to read in one go from files while
            being hashed. A too small size will slow down the processing and a larger
            size consumes more working memory. Default 2**20 byte = 1 MiB.
        content_only (bool): Compute the hash only based on the content of files -
            *not* their names or the names of their parent directories. Default
            `False`.
                NOTE that the tree structure in which files are organized under the
            the `directory` root still influences the computed hash. As longs as all
            files have the same content and are organised the same way in relation to
            all other files in the Directed Acyclic Graph representing the file-tree,
            the hash will remain the same (but the "name of nodes" does not matter).
            This option can e.g. be used to verify that that data is unchanged after
            renaming files (change extensions etc.).
        paths_only (bool): Compute the hash only based on the name and location of
            files in the file tree under the `directory` root. Default `False`.
                This option can e.g. be used to check if any files have been
            added/moved/removed, ignoring the content of each file. This is
            considerably faster than including content.
        follow_links (bool): If true, follow symbolic links to other *directories*.
            NOTE that symbolic links to other *files* are always included (as if the
            link was the actual file). Default `False`.
        include_empty (bool): Include empty directories when computing the hash. A
            directory is considered empty if it does not contain any files *matching
            provided matching criteria*. Default `False`, i.e. empty directories are
            ignored (as with git version control).
        workers (int | None): The number of processes to use when computing the hash.
            Default `None`, equivalent to `1`, which means no multiprocessing is
            used. NOTE that using multiprocessing can significantly speed-up
            execution, see `https://github.com/andhus/dirhash/tree/master/benchmark`
            for further details.

    # Returns
        The hash/checksum as a string the of hexadecimal digits (the result of
        `hexdigest` method of the hashlib._hashlib.HASH object corresponding to the
        provided `algorithm`).

    # Raises
        ValueError: For incorrectly provided arguments.
        SymlinkRecursionError: In case the `directory` contains symbolic links that
            lead to (infinite) recursion.

    # Path Selection and Filtering
        Provided match-patterns determine what paths within the `directory` to
        include when computing the hash value. These follow the ".gitignore
        wildcard style" of path matching. Paths *relative to the root `directory`
        (excluding the name of the directory itself) are matched against the
        patterns.
            The `match` argument represent what should be *included* - as opposed
        to `ignore` patterns for which matches are *excluded*. Using `ignore` is
        just short for adding the same patterns to the `match` argument with the
        prefix "!", i.e. the calls bellow are equivalent:

            `dirhash(..., match=['*', '!<pattern>'])`
            `dirhash(..., match=['*', '!<pattern>'], ignore=[])`
            `dirhash(..., match=['*'], ignore=['<pattern>'])`
            `dirhash(..., ignore=['<pattern>'])`

        If a file named ".dirhashignore" (available by the `dirhash.ignorefilename`
        module attribute) exists *directly* under the provided `directory`, then each
        line (not starting with "#") of this file is added to the ignore patterns.

        The following kwargs can also be used (possibly together with `match` and/or
        `ignore`):
            `ignore_extensions` ([str]): list (iterable) of file extensions to
                exclude. Short for adding `'*[.]<extension>'`to the `ignore` patterns
                where the dot [.] is added if <extension> does not already start with
                a dot.
            `ignore_hidden` (bool): Short for adding `['.*', '.*/']` to the `ignore`
                patterns, which will exclude hidden files and directories.

        To validate which paths are included, call `dirhash.get_leafpaths` with
        the same values for the arguments: `match`, `ignore` `follow_links`,
        `include_empty`, `ignore_extensions` and `ignore_hidden` to get a list of all
        paths that will be included when computing the hash by this function.
    """


def _get_instance(argname, instance_or_kwargs, cls):
    if instance_or_kwargs is None:
        return cls()
    if isinstance(instance_or_kwargs, dict):
        return cls(**instance_or_kwargs)
    if isinstance(instance_or_kwargs, cls):
        return instance_or_kwargs
    raise TypeError(
        'argument {argname} must be an instance of, or kwargs for, '
        '{cls}'.format(argname=argname, cls=cls)
    )


def _get_filehash(filepath, hasher_factory, chunk_size, cache=None):
    """Compute the hash for given filepath.

    # Arguments
        filepath (str): Path to the file to hash.
        hasher_factory (f: f() -> hashlib._hashlib.HASH): Callable that returns an
            instance of the `hashlib._hashlib.HASH` interface.
        chunk_size (int): The number of bytes to read in one go from files while
            being hashed.
        cache ({str: str} | None): A mapping from `filepath` to hash (return value
            of this function). If not None, a lookup will be attempted before hashing
            the file and the result will be added after completion.

    # Returns
        The hash/checksum as a string the of hexadecimal digits.

    # Side-effects
        The `cache` is updated if not None.
    """
    if cache is not None:
        filehash = cache.get(filepath, None)
        if filehash is None:
            filehash = _get_filehash(filepath, hasher_factory, chunk_size)
            cache[filepath] = filehash
        return filehash

    hasher = hasher_factory()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            hasher.update(chunk)

    return hasher.hexdigest()

