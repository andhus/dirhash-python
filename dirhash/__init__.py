#!/usr/bin/env python
"""dirhash - a python module (and CLI) for hashing of file system directories.

Provides the functions:
- `dirhash`
- `get_included_paths`.
"""
from __future__ import print_function, division

import os
import hashlib
import pkg_resources

from functools import partial
from multiprocessing import Pool

# Use the built-in version of scandir/walk if possible (python > 3.5),
# otherwise use the scandir module version
try:
    from os import scandir
except ImportError:  # pragma: no cover
    from scandir import scandir

from pathspec import PathSpec
from pathspec import RecursionError as _RecursionError
from pathspec.patterns import GitWildMatchPattern


__version__ = pkg_resources.require("dirhash")[0].version

algorithms_guaranteed = {'md5', 'sha1', 'sha224', 'sha256', 'sha384', 'sha512'}
algorithms_available = hashlib.algorithms_available

ignorefilename = '.dirhashignore'


def dirhash(
    directory,
    algorithm,
    match=None,
    ignore=None,
    chunk_size=2**20,
    content_only=False,
    paths_only=False,
    follow_links=True,
    include_empty=False,
    workers=None,
    **kwargs
):
    """Computes the hash of a directory based on its structure and content.

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

        To validate which paths are included, call `dirhash.get_included_paths` with
        the same values for the arguments: `match`, `ignore` `follow_links`,
        `include_empty`, `ignore_extensions` and `ignore_hidden` to get a list of all
        paths that will be included when computing the hash by this function.
    """
    abspath = os.path.abspath(directory)
    _verify_is_directory(abspath)

    if content_only and paths_only:
        raise ValueError(
            'only one of arguments `content_only` and `paths_only` can be True')

    hasher_factory = _get_hasher_factory(algorithm)
    match_filter = _get_match_filter(directory, match=match, ignore=ignore, **kwargs)

    cache = {}

    if workers is not None and workers > 1:
        # extract all (unique) files
        _, file_realpaths = _get_leafs(
            abspath=abspath,
            match_filter=match_filter,
            follow_links=follow_links,
            include_empty=False,
        )
        # hash files in parallel
        pool = Pool(workers)
        try:
            file_hashes = pool.map(
                partial(
                    _get_filehash,
                    hasher_factory=hasher_factory,
                    chunk_size=chunk_size
                ),
                file_realpaths
            )
        finally:
            pool.close()
        # prepare the cache with precomputed file hashes
        cache = dict(zip(file_realpaths, file_hashes))

    dirhash = _get_dirhash(
        abspath=abspath,
        relpath='',
        hasher_factory=hasher_factory,
        content_only=content_only,
        paths_only=paths_only,
        chunk_size=chunk_size,
        match_filter=match_filter,
        follow_links=follow_links,
        include_empty=include_empty,
        included_leafs=[],
        included_file_realpaths=set(),
        visited_dirs={},
        cache=cache
    )
    if dirhash is _EMPTY:
        if include_empty:
            return hasher_factory(_empty_dir_descriptor.encode('utf-8')).hexdigest()
        else:
            raise ValueError('{}: Nothing to hash'.format(directory))

    return dirhash


def get_included_paths(
    directory,
    match=None,
    ignore=None,
    follow_links=True,
    include_empty=False,
    **kwargs
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
    abspath = os.path.abspath(directory)
    _verify_is_directory(abspath)
    match_filter = _get_match_filter(abspath, match=match, ignore=ignore, **kwargs)
    included_leafs, _ = _get_leafs(
        abspath=abspath,
        match_filter=match_filter,
        follow_links=follow_links,
        include_empty=include_empty,
    )

    return sorted(included_leafs)


def _get_leafs(
    abspath,
    match_filter,
    follow_links=True,
    include_empty=False,
):
    """An inexpensive "dry-run" of the `_get_dirhash` function to get the leaf-paths
    that will be included in computing the hash.
    """
    included_leafs = []
    included_file_realpaths = set()
    _get_dirhash(
        abspath=abspath,
        relpath='',
        hasher_factory=_PlaceHolderHasher,  # avoid computing any hash
        content_only=False,
        paths_only=True,  # avoid opening files!
        chunk_size=None,  # never used
        match_filter=match_filter,
        follow_links=follow_links,
        include_empty=include_empty,
        included_leafs=included_leafs,
        included_file_realpaths=included_file_realpaths,
        visited_dirs={}
    )
    return included_leafs, included_file_realpaths


_null_chr = '\000'
_component_separator = _null_chr
_descriptor_separator = _null_chr * 2
_dirs_files_separator = _null_chr * 3
_empty_dir_descriptor = _dirs_files_separator


def _verify_is_directory(directory):
    if not os.path.exists(directory):
        raise ValueError('{}: No such directory'.format(directory))
    if not os.path.isdir(directory):
        raise ValueError('{}: Is not a directory'.format(directory))


def _get_match_filter(dir_abspath, ignore, **kwargs):
    """Helper to construct a function for filtering of paths.
    """
    ignore = [] if ignore is None else list(ignore)
    ignore = _parse_ignorefile(dir_abspath) + ignore

    match_spec = _get_match_spec(ignore=ignore, **kwargs)
    path_spec = PathSpec.from_lines(GitWildMatchPattern, match_spec)

    return path_spec.match_files


def _get_dirhash(abspath, *args, **kwargs):
    """Entry point of the recursive dirhash implementation, with the only purpose to
    provide a more informative error in case of (infinite) symlink recursion.
    """
    try:
        return _get_dirhash_recursive(os.path.realpath(abspath), *args, **kwargs)
    except SymlinkRecursionError as e:
        raise SymlinkRecursionError(
            real_path=e.real_path,
            first_path=os.path.join(abspath, e.first_path),
            second_path=os.path.join(abspath, e.second_path)
        )


def _get_dirhash_recursive(
    realpath,
    relpath,
    hasher_factory,
    content_only,
    paths_only,
    chunk_size,
    match_filter,
    include_empty,
    follow_links,
    included_leafs,
    included_file_realpaths,
    visited_dirs,
    cache=None
):
    """Recursive implementation for computing the hash of a directory based on its
    structure and content.

    # Arguments
        realpath (str): Real path to the current directory to hash.
        relpath (str): Path to the current directory relative to the root directory
            (entry point) for the recursion.
        hasher_factory (f: f() -> hashlib._hashlib.HASH): Callable that returns a
            instance of the hashlib._hashlib.HASH interface.
        match_filter (f: f(str) -> bool): Function for filtering leaf paths (files
            and possibly empty directories) to include.
        included_leafs ([str]): Continuously appended list of leaf paths (files
            and possibly empty directories) that are included. Used by
            `dirhash.get_included_paths`.
        included_file_realpaths ({str}): Continuously updated set of the real paths
            to included files. Used by `dirhash.dirhash` when files are hashed using
            multiprocessing.
        visited_dirs ({str: str}): Mapping from real path to root-relative path of
            directories visited previously in *current branch* of recursion. Used to
            detect if there are symlinks leading to infinite recursion.
        cache ({str: str}): Mapping from real file path to hash value of already
            hashed files. Used to avoid duplicating hash computations in the case of
            repeated occurrence of files by symlinks, as well as to inject
            precomputed hashes by the multiprocessing implementation

        For args: `content_only`, `paths_only`, `chunk_size`, `include_empty` and
        `follow_links` see docs of `dirhash.dirhash`.

    # Raises
        SymlinkRecursionError: in case the current directory has already been
            visited in current branch of recursion (i.e. would get infinite recursion
            if continuing).

    # Side-effects
        Continuously updates arguments: `included_leafs`, `included_file_realpaths`,
        `visited_dirs` and `cache`.

    # Returns
        The hash/checksum as a string the of hexadecimal digits of the current
        `directory` or `hahsdir._EMPTY` if there are no files or directories to
        include.
    """
    fwd_kwargs = vars()
    del fwd_kwargs['realpath']
    del fwd_kwargs['relpath']

    if follow_links:
        if realpath in visited_dirs:
            raise SymlinkRecursionError(
                real_path=realpath,
                # below will be replaced by full abspath in `_get_dirhash`
                first_path=visited_dirs[realpath],
                second_path=relpath
            )
        visited_dirs[realpath] = relpath

    subdirs, files = [], []
    symlink_files = set()
    for dir_entry in scandir(realpath):
        if dir_entry.is_dir(follow_symlinks=follow_links):
            subdirs.append(dir_entry)
        elif dir_entry.is_file(follow_symlinks=True):
            files.append(dir_entry)
            if dir_entry.is_symlink():
                symlink_files.add(dir_entry.name)

    subdir_descriptors = []
    for subdir in subdirs:
        if subdir.is_symlink():
            sub_realpath = os.path.realpath(subdir.path)
        else:
            sub_realpath = subdir.path
        sub_relpath = os.path.join(relpath, subdir.name)
        sub_dirhash = _get_dirhash_recursive(sub_realpath, sub_relpath, **fwd_kwargs)
        if sub_dirhash is _EMPTY:
            if not include_empty:
                continue
            if next(match_filter([sub_relpath]), None) is None:
                # dir is not a match
                continue
            # included empty (leaf) directories represented as `path/to/directory/.`
            included_leafs.append(os.path.join(sub_relpath, '.'))
            sub_dirhash = hasher_factory(
                _empty_dir_descriptor.encode('utf-8')
            ).hexdigest()

        if content_only:
            subdir_descriptor = sub_dirhash
        else:
            subdir_descriptor = _component_separator.join([sub_dirhash, subdir.name])
        subdir_descriptors.append(subdir_descriptor)

    subdirs_descriptor = _descriptor_separator.join(sorted(subdir_descriptors))

    file_descriptors = []
    for file_relpath in match_filter(
        os.path.join(relpath, file_.name) for file_ in files
    ):
        filename = os.path.basename(file_relpath)
        file_realpath = os.path.join(realpath, filename)
        if filename in symlink_files:
            file_realpath = os.path.realpath(file_realpath)
        included_leafs.append(file_relpath)
        included_file_realpaths.add(file_realpath)

        if paths_only:
            file_descriptors.append(filename)
            continue

        filehash = _get_filehash(file_realpath, hasher_factory, chunk_size, cache)

        if content_only:
            file_descriptors.append(filehash)
        else:
            file_descriptors.append(_component_separator.join([filehash, filename]))

    files_descriptor = _descriptor_separator.join(sorted(file_descriptors))

    is_empty = (subdirs_descriptor == '' and files_descriptor == '')
    if is_empty:
        return _EMPTY

    descriptor = ''.join(
        [subdirs_descriptor, _dirs_files_separator, files_descriptor]
    )

    dirhash = hasher_factory(descriptor.encode('utf-8')).hexdigest()

    if follow_links:
        del visited_dirs[realpath]

    return dirhash


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


class SymlinkRecursionError(_RecursionError):
    """Raised when symlinks cause a cyclic graph of directories.

    Extends the `pathspec.util.RecursionError` but with a different name (avoid
    overriding the built-in error!) and with a more informative string representation
    (used in `dirhash.cli`).
    """
    def __str__(self):
        # _RecursionError.__str__ prints args without context
        return 'Symlink recursion: {}'.format(self.message)


class _Empty(object):
    """The single instance of this class, `_EMPTY` below, is used as return value for
    `_get_dirhash_recursive` in the case of an empty directory.
    """
    pass


_EMPTY = _Empty()


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


class _PlaceHolderHasher(object):
    """A hasher that does nothing and always returns an empty string.

    Used in the `_get_leafs` "dry-run" of the `_get_dirhash_recursive` function.
    """

    def __init__(self, *args, **kwargs):
        pass

    def hexdigest(self):
        return ''


def _get_match_spec(
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


def _parse_ignorefile(directory):
    """Parse ignore file in `directory` (if exists) and return a list of ignore
    patterns."""
    ignorefilepath = os.path.join(directory, ignorefilename)
    if not os.path.exists(ignorefilepath):
        return []

    with open(ignorefilepath) as f:
        ignore = [p for p in f.read().splitlines() if not p.startswith('#')]

    return ignore
