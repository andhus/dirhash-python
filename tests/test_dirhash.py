from __future__ import print_function, division

import os
import shutil
import hashlib
import tempfile
from time import sleep, time

import pytest
from pathspec import RecursionError

from dirhash import (
    _get_hasher_factory,
    _get_match_spec,
    get_included_paths,
    dirhash,
    algorithms_available,
    algorithms_guaranteed,
)
from dirhash.traverse import SymlinkRecursionError


class TestGetHasherFactory(object):

    def test_get_guaranteed(self):
        algorithm_and_hasher_factory = [
            ('md5', hashlib.md5),
            ('sha1', hashlib.sha1),
            ('sha224', hashlib.sha224),
            ('sha256', hashlib.sha256),
            ('sha384', hashlib.sha384),
            ('sha512', hashlib.sha512)
        ]
        assert algorithms_guaranteed == {a for a, _ in algorithm_and_hasher_factory}
        for algorithm, expected_hasher_factory in algorithm_and_hasher_factory:
            hasher_factory = _get_hasher_factory(algorithm)
            assert hasher_factory == expected_hasher_factory

    def test_get_available(self):
        for algorithm in algorithms_available:
            hasher_factory = _get_hasher_factory(algorithm)
            hasher = hasher_factory()
            assert hasattr(hasher, 'update')
            assert hasattr(hasher, 'hexdigest')

    def test_not_available(self):
        with pytest.raises(ValueError):
            _get_hasher_factory('not available')

    def test_bypass_hasher_factory(self):

        # test standard hasher
        hasher_factory = _get_hasher_factory(hashlib.sha256)
        assert hasher_factory is hashlib.sha256

        # test raise on custom hasher with bad interface
        class IncompleteMockHasher(object):

            def __init__(self, *args, **kwargs):
                pass

            def update(self, *args, **kwargs):
                pass

        with pytest.raises(ValueError):
            _get_hasher_factory(IncompleteMockHasher)

        # test custom hasher with ok interface
        class MockHasher(IncompleteMockHasher):

            def hexdigest(self):
                return ''

        hasher_factory = _get_hasher_factory(MockHasher)
        assert hasher_factory is MockHasher


class TestGetMatchSpec(object):

    def test_default_match_all(self):
        ms = _get_match_spec()
        assert ms == ['*']

    def test_only_match(self):
        ms = _get_match_spec(match=['a*', 'b*'])
        assert ms == ['a*', 'b*']

    def test_only_ignore(self):
        ms = _get_match_spec(ignore=['a*', 'b*'])
        assert ms == ['*', '!a*', '!b*']

    def test_match_and_ignore(self):
        ms = _get_match_spec(match=['a*'], ignore=['*.ext'])
        assert ms == ['a*', '!*.ext']

    def test_ignore_hidden(self):
        ms = _get_match_spec(ignore_hidden=True)
        assert ms == ['*', '!.*', '!.*/']

        # should not duplicate if present in (general) ignore
        ms = _get_match_spec(ignore=['.*'], ignore_hidden=True)
        assert ms == ['*', '!.*', '!.*/']

        ms = _get_match_spec(ignore=['.*/'], ignore_hidden=True)
        assert ms == ['*', '!.*/', '!.*']

        ms = _get_match_spec(ignore=['.*', '.*/'], ignore_hidden=True)
        assert ms == ['*', '!.*', '!.*/']

    def test_ignore_extensions(self):
        ms = _get_match_spec(ignore_extensions=['.ext'])
        assert ms == ['*', '!*.ext']

        # automatically adds '.'
        ms = _get_match_spec(ignore_extensions=['ext'])
        assert ms == ['*', '!*.ext']

        # mixed also works
        ms = _get_match_spec(ignore_extensions=['ext1', '.ext2'])
        assert ms == ['*', '!*.ext1', '!*.ext2']

        # should not duplicate if present in (general) ignore
        ms = _get_match_spec(ignore=['*.ext'], ignore_extensions=['.ext'])
        assert ms == ['*', '!*.ext']

        ms = _get_match_spec(ignore=['*.ext'], ignore_extensions=['ext'])
        assert ms == ['*', '!*.ext']


class TempDirTest(object):

    def setup(self):
        self.dir = tempfile.mkdtemp()

    def tear_down(self):
        if os.path.exists(self.dir):
            shutil.rmtree(self.dir)

    def path_to(self, relpath):
        return os.path.join(self.dir, relpath)

    def mkdirs(self, dirpath):
        os.makedirs(self.path_to(dirpath))

    def mkfile(self, relpath, content=None):
        with open(self.path_to(relpath), 'w') as f:
            if content:
                f.write(content)

    def symlink(self, src, dst):
        os.symlink(self.path_to(src), self.path_to(dst))

    def remove(self, relpath):
        if os.path.isdir(self.path_to(relpath)):
            shutil.rmtree(self.path_to(relpath))
        os.remove(self.path_to(relpath))


class TestGetIncludedPaths(TempDirTest):
    # Integration tests with `pathspec` for basic use cases.

    def test_basic(self):
        self.mkdirs('root/d1/d11')
        self.mkdirs('root/d2')

        self.mkfile('root/f1')
        self.mkfile('root/d1/f1')
        self.mkfile('root/d1/d11/f1')
        self.mkfile('root/d2/f1')

        expected_filepaths = ['d1/d11/f1', 'd1/f1', 'd2/f1', 'f1']
        filepaths = get_included_paths(self.path_to('root'))
        assert filepaths == expected_filepaths

        # end with '/' or not should not matter
        filepaths = get_included_paths(self.path_to('root/'))
        assert filepaths == expected_filepaths

    def test_not_a_directory(self):
        self.mkdirs('root')
        self.mkfile('root/f1')
        # does not exist
        with pytest.raises(ValueError):
            get_included_paths(self.path_to('wrong_root'))
        with pytest.raises(ValueError):
            get_included_paths(self.path_to('root/f1'))

    def test_symlinked_file(self):
        self.mkdirs('root')
        self.mkfile('root/f1')
        self.mkfile('linked_file')
        self.symlink('linked_file', 'root/f2')

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'linked_files': True}
        )
        assert filepaths == ['f1', 'f2']

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'linked_files': False}
        )
        assert filepaths == ['f1']

        # default is 'linked_files': True
        filepaths = get_included_paths(self.path_to('root'),)
        assert filepaths == ['f1', 'f2']

    def test_symlinked_dir(self):
        self.mkdirs('root')
        self.mkfile('root/f1')
        self.mkdirs('linked_dir')
        self.mkfile('linked_dir/f1')
        self.mkfile('linked_dir/f2')
        self.symlink('linked_dir', 'root/d1')

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'linked_dirs': False}
        )
        assert filepaths == ['f1']

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'linked_dirs': True}
        )
        assert filepaths == ['d1/f1', 'd1/f2', 'f1']

        # default is 'linked_dirs': True
        filepaths = get_included_paths(self.path_to('root'))
        assert filepaths == ['d1/f1', 'd1/f2', 'f1']

    def test_cyclic_link(self):
        self.mkdirs('root/d1')
        self.symlink('root', 'root/d1/link_back')
        with pytest.raises(SymlinkRecursionError) as exc_info:
            get_included_paths(
                self.path_to('root'),
                protocol_options={'on_cyclic_link': 'raise'}
            )
        assert exc_info.value.real_path == os.path.realpath(self.path_to('root'))
        assert exc_info.value.first_path == self.path_to('root/')
        assert exc_info.value.second_path == self.path_to('root/d1/link_back')
        assert str(exc_info.value).startswith('Symlink recursion:')

        filepaths = get_included_paths(
            self.path_to('root'),
            protocol_options={'on_cyclic_link': 'hash_reference'}
        )
        assert filepaths == ['d1/link_back/.']

        # default is 'on_cyclic_link': 'raise'
        with pytest.raises(SymlinkRecursionError):
            filepaths = get_included_paths(self.path_to('root'))

    def test_ignore_hidden_files(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/.d2')

        self.mkfile('root/f1')
        self.mkfile('root/.f2')
        self.mkfile('root/d1/f1')
        self.mkfile('root/d1/.f2')
        self.mkfile('root/.d2/f1')

        # no ignore
        filepaths = get_included_paths(self.path_to('root'))
        assert filepaths == ['.d2/f1', '.f2', 'd1/.f2', 'd1/f1', 'f1']

        # with ignore
        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'match_patterns': ['*', '!.*']}
        )
        assert filepaths == ['.d2/f1', 'd1/f1', 'f1']

    def test_exclude_hidden_dirs(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/.d2')

        self.mkfile('root/f1')
        self.mkfile('root/.f2')
        self.mkfile('root/d1/f1')
        self.mkfile('root/d1/.f2')
        self.mkfile('root/.d2/f1')

        # no ignore
        filepaths = get_included_paths(self.path_to('root'))
        assert filepaths == ['.d2/f1', '.f2', 'd1/.f2', 'd1/f1', 'f1']

        # with ignore
        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'match_patterns': ['*', '!.*/']}
        )
        assert filepaths == ['.f2', 'd1/.f2', 'd1/f1', 'f1']

    def test_exclude_hidden_dirs_and_files(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/.d2')

        self.mkfile('root/f1')
        self.mkfile('root/.f2')
        self.mkfile('root/d1/f1')
        self.mkfile('root/d1/.f2')
        self.mkfile('root/.d2/f1')

        # no ignore
        filepaths = get_included_paths(self.path_to('root'))
        assert filepaths == ['.d2/f1', '.f2', 'd1/.f2', 'd1/f1', 'f1']

        # using ignore
        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'match_patterns': ['*', '!.*/', '!.*']}
        )
        assert filepaths == ['d1/f1', 'f1']

    def test_exclude_extensions(self):
        self.mkdirs('root/d1')

        self.mkfile('root/f')
        self.mkfile('root/f.txt')
        self.mkfile('root/f.skip1')
        self.mkfile('root/fskip1')
        self.mkfile('root/f.skip2')
        self.mkfile('root/f.skip1.txt')
        self.mkfile('root/f.skip1.skip2')
        self.mkfile('root/f.skip1skip2')
        self.mkfile('root/d1/f.txt')
        self.mkfile('root/d1/f.skip1')

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'match_patterns': ['*', '!*.skip1', '!*.skip2']}
        )
        assert filepaths == [
            'd1/f.txt', 'f', 'f.skip1.txt', 'f.skip1skip2', 'f.txt', 'fskip1']

    def test_empty_dirs_include_vs_exclude(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/d2')
        self.mkdirs('root/d3/d31')
        self.mkdirs('root/d4/d41')

        self.mkfile('root/d1/f')
        self.mkfile('root/d3/d31/f')

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'empty_dirs': False}
        )
        assert filepaths == ['d1/f', 'd3/d31/f']

        # `include_empty=False` is default
        filepaths = get_included_paths(self.path_to('root'))
        assert filepaths == ['d1/f', 'd3/d31/f']

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'empty_dirs': True}
        )
        assert filepaths == ['d1/f', 'd2/.', 'd3/d31/f', 'd4/d41/.']

    def test_empty_dirs_because_of_filter_include_vs_exclude(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/d2')

        self.mkfile('root/d1/f')
        self.mkfile('root/d2/.f')

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={
                'match_patterns': ['*', '!.*'],
                'empty_dirs': False
            }
        )
        assert filepaths == ['d1/f']

        # `include_empty=False` is default
        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={'match_patterns': ['*', '!.*']},
        )
        assert filepaths == ['d1/f']

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={
                'match_patterns': ['*', '!.*'],
                'empty_dirs': True
            }
        )
        assert filepaths == ['d1/f', 'd2/.']

    def test_empty_dir_inclusion_not_affected_by_match(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/.d2')

        # NOTE that empty dirs are not excluded by match_patterns:

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={
                'match_patterns': ['*', '!.*'],
                'empty_dirs': True
            }
        )
        assert filepaths == ['.d2/.', 'd1/.']

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={
                'match_patterns': ['*', '!.*/'],
                'empty_dirs': True
            }
        )
        assert filepaths == ['.d2/.', 'd1/.']

        filepaths = get_included_paths(
            self.path_to('root'),
            filter_options={
                'match_patterns': ['*', '!d1'],
                'empty_dirs': True
            }
        )
        assert filepaths == ['.d2/.', 'd1/.']


def dirhash_mp_comp(*args, **kwargs):
    res = dirhash(*args, **kwargs)
    res_mp = dirhash(workers=2, *args, **kwargs)
    assert res == res_mp
    return res


class Testdirhash(TempDirTest):

    def test_guaranteed_algorithms(self):
        self.mkdirs('root/d1/d11')
        self.mkdirs('root/d2')
        self.mkfile('root/f1', 'a')
        self.mkfile('root/d1/f1', 'b')
        self.mkfile('root/d1/d11/f1', 'c')
        self.mkfile('root/d2/f1', 'd')

        for algorithm, expected_hash in [
            ('md5', '23315916fc3a935b5ed3e120a202aea4'),
            ('sha1', '6119b22d2916a4af7032802cdb95c742a217fe9f'),
            ('sha224', 'cdb3a780741c08d6c4ffc6aa0725787f6fbef3e80d81c8850215ef61'),
            ('sha256', '6fa5594ea7fb6a05fd36c152e6576522'
                       'a5f37b07c2d797f2ed96527ae18f3fe3'),
            ('sha384', '453ebd36d95e24149f184589df49f69b'
                       'f289af3e889c916cc93f0e02367f4d48'
                       'aef2593ef29f0ecdf3b6e05572e90066'),
            ('sha512', 'f52ac9eeeb5160637afa91f1f20f1a60'
                       'ce80a55ac3757f8bb9225e10edc131b4'
                       '2da10497706ef4f06d36f13dae77540b'
                       'c0e5484c7f79f87a83c76ae103fff4fa')
        ]:
            hash_value = dirhash_mp_comp(self.path_to('root'), algorithm)
            assert hash_value == expected_hash

    def test_symlinked_file(self):
        self.mkdirs('root1')
        self.mkfile('root1/f1', 'a')
        self.mkfile('linked_file', 'b')
        self.symlink('linked_file', 'root1/f2')

        self.mkdirs('root2')
        self.mkfile('root2/f1', 'a')
        self.mkfile('root2/f2', 'b')

        root1_follow_true = dirhash_mp_comp(
            self.path_to('root1'), algorithm='md5', follow_links=True)
        root1_follow_false = dirhash_mp_comp(
            self.path_to('root1'), algorithm='md5', follow_links=False)
        root2 = dirhash_mp_comp(
            self.path_to('root2'), algorithm='md5')

        # NOTE `follow_links` hash no effect if only the file is linked (as is the
        # case here), linked _files_ are always included.
        assert root1_follow_false == root1_follow_true == root2

    def test_symlinked_dir(self):
        self.mkdirs('root1')
        self.mkfile('root1/f1', 'a')
        self.mkdirs('linked_dir')
        self.mkfile('linked_dir/f1', 'b')
        self.mkfile('linked_dir/f2', 'c')
        self.symlink('linked_dir', 'root1/d1')

        self.mkdirs('root2')
        self.mkfile('root2/f1', 'a')
        self.mkdirs('root2/d1')
        self.mkfile('root2/d1/f1', 'b')
        self.mkfile('root2/d1/f2', 'c')

        root1_follow_true = dirhash_mp_comp(
            self.path_to('root1'), algorithm='md5', follow_links=True)
        root1_follow_false = dirhash_mp_comp(
            self.path_to('root1'), algorithm='md5', follow_links=False)
        root2 = dirhash_mp_comp(
            self.path_to('root2'), algorithm='md5')

        assert root1_follow_false != root1_follow_true
        assert root1_follow_true == root2

    def test_cache_used_for_symlinks(self):

        self.mkdirs('root/dir')
        self.mkfile('root/file', '< one chunk content')
        for i in range(10):
            self.symlink('root/file', 'root/link_{}'.format(i))
        for i in range(10):
            self.symlink('root/file', 'root/dir/link_{}'.format(i))
        start = time()
        dirhash(self.path_to('root'), algorithm=SlowHasher)
        end = time()
        elapsed = end - start
        assert elapsed < SlowHasher.wait_time * 2

    def test_raise_on_empty_root_without_include_empty(self):
        self.mkdirs('root')
        with pytest.raises(ValueError):
            dirhash_mp_comp(self.path_to('root'), 'sha256')

    def test_empty_root_include_empty(self):
        self.mkdirs('root')
        dirhash = dirhash_mp_comp(self.path_to('root'), 'sha256', include_empty=True)
        assert False  # TODO
        # expected_dirhash = hashlib.sha256(
        #     _empty_dir_descriptor.encode('utf-8')
        # ).hexdigest()
        # assert dirhash == expected_dirhash

    def test_include_empty(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/d2')
        self.mkfile('root/d1/f')

        args = (self.path_to('root'), 'sha256')
        dirhash = dirhash_mp_comp(*args, include_empty=False)
        dirhash_empty = dirhash_mp_comp(*args, include_empty=True)
        assert dirhash != dirhash_empty

    def test_chunksize(self):
        self.mkdirs('root')
        self.mkfile('root/numbers.txt', str(range(1000)))

        hash_value = dirhash_mp_comp(self.path_to('root'), 'sha256')
        for chunk_size in [2**4, 2**8, 2**16]:
            assert (
                dirhash_mp_comp(self.path_to('root'), 'sha256', chunk_size=chunk_size) ==
                hash_value
            )

    def test_content_only(self):
        self.mkdirs('root1')
        self.mkfile('root1/a.txt', 'abc')
        self.mkfile('root1/b.txt', 'def')
        self.mkdirs('root2')
        self.mkfile('root2/a.txt', 'abc')
        self.mkfile('root2/c.txt', 'def')

        hash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256')
        hash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256')
        assert hash1 != hash2

        # with `content_only` hash remains the same as long as order of files is the
        # same (based on sorting of file paths)
        chash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256', content_only=True)
        chash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256', content_only=True)
        assert chash1 == chash2

    def test_paths_only(self):
        self.mkdirs('root1')
        self.mkfile('root1/a.txt', 'abc')
        self.mkfile('root1/b.txt', 'def')
        self.mkdirs('root2')
        self.mkfile('root2/a.txt', 'abc')
        self.mkfile('root2/b.txt', '___')

        hash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256')
        hash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256')
        assert hash1 != hash2

        chash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256', paths_only=True)
        chash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256', paths_only=True)
        assert chash1 == chash2

    def test_raise_on_content_only_and_paths_only(self):
        self.mkdirs('root1')
        self.mkfile('root1/a.txt', 'abc')
        dirhash_mp_comp(self.path_to('root1'), 'sha256')  # ok!
        with pytest.raises(ValueError):
            dirhash_mp_comp(
                self.path_to('root1'),
                'sha256',
                content_only=True,
                paths_only=True
            )

    def test_collision_attempt(self):
        self.mkdirs('root1')
        self.mkfile('root1/ab')
        self.mkfile('root1/c')
        hash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256')

        self.mkdirs('root2')
        self.mkfile('root2/a')
        self.mkfile('root2/bc')
        hash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256')

        assert not hash1 == hash2

    def test_ignorefile(self):
        self.mkdirs('root1')
        self.mkdirs('root2')
        for fname in ['a', '.b', 'c.txt']:
            self.mkfile(os.path.join('root1', fname))
            self.mkfile(os.path.join('root2', fname))

        ignorefile = (
            '# my dirhash ignore patterns\n'
            '.*\n'
        )
        self.mkfile('root1/.dirhashignore', ignorefile)
        assert (
            dirhash_mp_comp(self.path_to('root1'), 'sha256') ==
            dirhash_mp_comp(self.path_to('root2'), 'sha256', ignore=['.*'])
        )
        assert (
            dirhash_mp_comp(self.path_to('root1'), 'sha256', ignore=['*.txt']) ==
            dirhash_mp_comp(self.path_to('root2'), 'sha256', ignore=['.*', '*.txt'])
        )
        # ignore file should _not_ be ignored by default:
        self.mkfile('root1/.dirhashignore', '# empty ignorefile')
        assert (
            dirhash_mp_comp(self.path_to('root1'), 'sha256') !=
            dirhash_mp_comp(self.path_to('root2'), 'sha256')
        )

    def test_multiproc_speedup(self):

        self.mkdirs('root/dir')
        num_files = 10
        for i in range(num_files):
            self.mkfile('root/file_{}'.format(i), '< one chunk content')

        expected_min_elapsed = SlowHasher.wait_time * num_files

        start = time()
        dirhash(self.path_to('root'), algorithm=SlowHasher)
        end = time()
        elapsed_sequential = end - start
        assert elapsed_sequential > expected_min_elapsed

        start = time()
        dirhash(self.path_to('root'), algorithm=SlowHasher, workers=num_files)
        end = time()
        elapsed_muliproc = end - start
        assert elapsed_muliproc < expected_min_elapsed / 2  # at least half!


class SlowHasher(object):
    wait_time = 0.1

    def __init__(self, *args, **kwargs):
        pass

    def update(self, data):
        if data != b'':
            sleep(self.wait_time)

    def hexdigest(self):
        return ''
