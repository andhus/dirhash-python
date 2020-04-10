from __future__ import print_function, division

import os
import shutil
import hashlib
import tempfile
from time import sleep, time

import pytest

from dirhash import (
    _get_hasher_factory,
    _get_match_spec,
    get_included_paths,
    dirhash,
    algorithms_available,
    algorithms_guaranteed,
)
from scantree import SymlinkRecursionError


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
            filtering={'linked_files': True}
        )
        assert filepaths == ['f1', 'f2']

        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={'linked_files': False}
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
            filtering={'linked_dirs': False}
        )
        assert filepaths == ['f1']

        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={'linked_dirs': True}
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
                protocol={'on_cyclic_link': 'raise'}
            )
        assert exc_info.value.real_path == os.path.realpath(self.path_to('root'))
        assert exc_info.value.first_path == self.path_to('root/')
        assert exc_info.value.second_path == self.path_to('root/d1/link_back')
        assert str(exc_info.value).startswith('Symlink recursion:')

        filepaths = get_included_paths(
            self.path_to('root'),
            protocol={'on_cyclic_link': 'hash_reference'}
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
            filtering={'match_patterns': ['*', '!.*']}
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
            filtering={'match_patterns': ['*', '!.*/']}
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
            filtering={'match_patterns': ['*', '!.*/', '!.*']}
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
            filtering={'match_patterns': ['*', '!*.skip1', '!*.skip2']}
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
            filtering={'empty_dirs': False}
        )
        assert filepaths == ['d1/f', 'd3/d31/f']

        # `include_empty=False` is default
        filepaths = get_included_paths(self.path_to('root'))
        assert filepaths == ['d1/f', 'd3/d31/f']

        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={'empty_dirs': True}
        )
        assert filepaths == ['d1/f', 'd2/.', 'd3/d31/f', 'd4/d41/.']

    def test_empty_dirs_because_of_filter_include_vs_exclude(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/d2')

        self.mkfile('root/d1/f')
        self.mkfile('root/d2/.f')

        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={
                'match_patterns': ['*', '!.*'],
                'empty_dirs': False
            }
        )
        assert filepaths == ['d1/f']

        # `include_empty=False` is default
        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={'match_patterns': ['*', '!.*']},
        )
        assert filepaths == ['d1/f']

        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={
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
            filtering={
                'match_patterns': ['*', '!.*'],
                'empty_dirs': True
            }
        )
        assert filepaths == ['.d2/.', 'd1/.']

        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={
                'match_patterns': ['*', '!.*/'],
                'empty_dirs': True
            }
        )
        assert filepaths == ['.d2/.', 'd1/.']

        filepaths = get_included_paths(
            self.path_to('root'),
            filtering={
                'match_patterns': ['*', '!d1'],
                'empty_dirs': True
            }
        )
        assert filepaths == ['.d2/.', 'd1/.']


def dirhash_mp_comp(*args, **kwargs):
    res = dirhash(*args, **kwargs)
    res_mp = dirhash(jobs=2, *args, **kwargs)
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
            ('md5', 'cee9cf7d29f773f9df18a6712c54a7f2'),
            ('sha1', 'fc5256658bb21111d5d1a9879e6c2ce0fd00f713'),
            ('sha224', '7d8961337c06b27ba00baedd5587fb1f956cfb969d22497cee8651d5'),
            ('sha256', '785d448a0b92d4b87502e7c95951532d'
                       '41283362a5d36437769eb8351cab11c9'),
            ('sha384', 'deaae2d70c6d930eb30ca69d9f5ad110'
                       '0678de99743943eb627d378073a0896c'
                       'ab4d65129446ad16430abee4209cdee5'),
            ('sha512', '67e0334bf8d692c09b658c03fac7b515'
                       '4cd7171fd7672b150e505538ec634f30'
                       'c392aeaf2fe4cb8b2de1e7acc60c6ea51'
                       'd2e6284b1be30453ede0e87ef120044')
        ]:
            hash_value = dirhash_mp_comp(self.path_to('root'), algorithm)
            assert hash_value == expected_hash

    def test_recursive_descriptor(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/d2')
        self.mkfile('root/f1', 'a')
        self.mkfile('root/d1/f12', 'b')

        f1_desc = 'data:a\000name:f1'
        f12_desc = 'data:b\000name:f12'
        d1_desc = 'dirhash:{}\000name:d1'.format(f12_desc + '\n')
        d2_desc = 'dirhash:\000name:d2'

        empty_dirs_false_expected = '\n'.join([f1_desc, d1_desc, ''])
        empty_dirs_true_expected = '\n'.join([f1_desc, d2_desc, d1_desc, ''])

        empty_dirs_false = dirhash(
            self.path_to('root'),
            algorithm=IdentityHasher
        )
        assert empty_dirs_false == empty_dirs_false_expected

        empty_dirs_true = dirhash(
            self.path_to('root'),
            algorithm=IdentityHasher,
            filtering={'empty_dirs': True}
        )
        assert empty_dirs_true == empty_dirs_true_expected

    def test_symlinked_file(self):
        self.mkdirs('root1')
        self.mkfile('root1/f1', 'a')
        self.mkfile('linked_file', 'b')
        self.symlink('linked_file', 'root1/f2')

        self.mkdirs('root2')
        self.mkfile('root2/f1', 'a')
        self.mkfile('root2/f2', 'b')

        root1_linked_files_true = dirhash_mp_comp(
            self.path_to('root1'), algorithm='md5'
        )
        root1_linked_files_false = dirhash_mp_comp(
            self.path_to('root1'), algorithm='md5',
            filtering={'linked_files': False}
        )

        root2 = dirhash_mp_comp(
            self.path_to('root2'), algorithm='md5'
        )

        assert root1_linked_files_false != root1_linked_files_true
        assert root1_linked_files_true == root2

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

        root1_linked_dirs_true = dirhash_mp_comp(
            self.path_to('root1'),
            algorithm='md5',
            filtering={'linked_dirs': True}
        )
        root1_linked_dirs_false = dirhash_mp_comp(
            self.path_to('root1'),
            algorithm='md5',
            filtering={'linked_dirs': False}
        )
        root2 = dirhash_mp_comp(
            self.path_to('root2'), algorithm='md5'
        )

        assert root1_linked_dirs_false != root1_linked_dirs_true
        assert root1_linked_dirs_true == root2

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
        dirhash_ = dirhash_mp_comp(
            self.path_to('root'),
            'sha256',
            filtering={'empty_dirs': True}
        )
        expected_dirhash = hashlib.sha256(''.encode('utf-8')).hexdigest()
        assert dirhash_ == expected_dirhash

    def test_include_empty(self):
        self.mkdirs('root/d1')
        self.mkdirs('root/d2')
        self.mkfile('root/d1/f')

        args = (self.path_to('root'), 'sha256')
        dirhash_ = dirhash_mp_comp(
            *args,
            filtering={'empty_dirs': False})
        dirhash_empty = dirhash_mp_comp(
            *args,
            filtering={'empty_dirs': True}
        )
        assert dirhash_ != dirhash_empty

    def test_chunksize(self):
        self.mkdirs('root')
        self.mkfile('root/numbers.txt', str(range(1000)))

        hash_value = dirhash_mp_comp(self.path_to('root'), 'sha256')
        for chunk_size in [2**4, 2**8, 2**16]:
            assert dirhash_mp_comp(
                self.path_to('root'),
                'sha256',
                chunk_size=chunk_size
            ) == hash_value

    def test_data_only(self):
        self.mkdirs('root1')
        self.mkfile('root1/a.txt', 'abc')
        self.mkfile('root1/b.txt', 'def')
        self.mkdirs('root2')
        self.mkfile('root2/a.txt', 'abc')
        self.mkfile('root2/c.txt', 'def')

        hash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256')
        hash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256')
        assert hash1 != hash2

        # with entry hash remains the same as long as order of files is the
        # same
        [dhash1, dhash2] = [
            dirhash_mp_comp(
                self.path_to(root),
                'sha256',
                protocol={'entry_properties': ['data']}
            ) for root in ['root1', 'root2']
        ]
        assert dhash1 == dhash2

    def test_name_only(self):
        self.mkdirs('root1')
        self.mkfile('root1/a.txt', 'abc')
        self.mkfile('root1/b.txt', 'def')
        self.mkdirs('root2')
        self.mkfile('root2/a.txt', 'abc')
        self.mkfile('root2/b.txt', '___')

        hash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256')
        hash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256')
        assert hash1 != hash2

        [dhash1, dhash2] = [
            dirhash_mp_comp(
                self.path_to(root),
                'sha256',
                protocol={'entry_properties': ['name']}
            ) for root in ['root1', 'root2']
        ]
        assert dhash1 == dhash2

    def test_is_link_property(self):
        self.mkdirs('root1')
        self.mkfile('root1/a.txt', 'abc')
        self.mkfile('root1/b.txt', 'def')
        self.mkdirs('root2')
        self.mkfile('b_target', 'def')
        self.mkfile('root2/a.txt', 'abc')
        self.symlink('b_target', 'root2/b.txt')

        hash1 = dirhash_mp_comp(self.path_to('root1'), 'sha256')
        hash2 = dirhash_mp_comp(self.path_to('root2'), 'sha256')
        assert hash1 == hash2

        for entry_properties in [
            ['name', 'data', 'is_link'],
            ['name', 'is_link'],
            ['data', 'is_link'],
        ]:
            [hash1, hash2] = [
                dirhash_mp_comp(
                    self.path_to(root),
                    'sha256',
                    protocol={'entry_properties': entry_properties}
                ) for root in ['root1', 'root2']
            ]
            assert hash1 != hash2

    def test_raise_on_not_at_least_one_of_name_and_data(self):
        self.mkdirs('root1')
        self.mkfile('root1/a.txt', 'abc')
        dirhash_mp_comp(self.path_to('root1'), 'sha256')  # check ok
        with pytest.raises(ValueError):
            dirhash_mp_comp(
                self.path_to('root1'),
                'sha256',
                protocol={'entry_properties': []}
            )

        with pytest.raises(ValueError):
            dirhash_mp_comp(
                self.path_to('root1'),
                'sha256',
                protocol={'entry_properties': ['is_link']}
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
        dirhash(self.path_to('root'), algorithm=SlowHasher, jobs=num_files)
        end = time()
        elapsed_muliproc = end - start
        assert elapsed_muliproc < expected_min_elapsed
        # just check "any speedup", the overhead varies (and is high on Travis)

    def test_cache_by_real_path_speedup(self, tmpdir):
        num_links = 10

        # reference run without links
        root1 = tmpdir.join('root1')
        root1.ensure(dir=True)
        for i in range(num_links):
            file_i = root1.join('file_{}'.format(i))
            file_i.write('< one chunk content', ensure=True)

        wait_time = SlowHasher.wait_time
        expected_min_elapsed = wait_time * num_links
        start = time()
        dirhash(root1, algorithm=SlowHasher)
        end = time()
        elapsed_sequential = end - start
        assert elapsed_sequential > expected_min_elapsed
        overhead = elapsed_sequential - expected_min_elapsed

        # all links to same file
        root2 = tmpdir.join('root2')
        root2.ensure(dir=True)
        target_file = tmpdir.join('target_file')
        target_file.ensure()
        for i in range(num_links):
            root2.join('link_{}'.format(i)).mksymlinkto(target_file)

        overhead_margin_factor = 1.5
        expected_max_elapsed = overhead * overhead_margin_factor + wait_time
        assert expected_max_elapsed < expected_min_elapsed
        start = time()
        dirhash(root2, algorithm=SlowHasher)
        end = time()
        elapsed_cache = end - start
        assert elapsed_cache < expected_max_elapsed

    def test_cache_together_with_multiprocess_speedup(self, tmpdir):
        target_file_names = ['target_file_1', 'target_file_2']
        num_links_per_file = 10
        num_links = num_links_per_file * len(target_file_names)

        # reference run without links
        root1 = tmpdir.join('root1')
        root1.ensure(dir=True)
        for i in range(num_links):
            file_i = root1.join('file_{}'.format(i))
            file_i.write('< one chunk content', ensure=True)

        jobs = 2
        wait_time = SlowHasher.wait_time
        expected_min_elapsed = wait_time * num_links / jobs
        start = time()
        dirhash(root1, algorithm=SlowHasher, jobs=jobs)
        end = time()
        elapsed_sequential = end - start
        assert elapsed_sequential > expected_min_elapsed
        overhead = elapsed_sequential - expected_min_elapsed

        root2 = tmpdir.join('root2')
        root2.ensure(dir=True)
        for i, target_file_name in enumerate(target_file_names):
            target_file = tmpdir.join(target_file_name)
            target_file.write('< one chunk content', ensure=True)
            for j in range(num_links_per_file):
                root2.join('link_{}_{}'.format(i, j)).mksymlinkto(target_file)

        overhead_margin_factor = 1.5
        expected_max_elapsed = overhead * overhead_margin_factor + wait_time * 2
        assert expected_max_elapsed < expected_min_elapsed
        start = time()
        dirhash(root2, algorithm=SlowHasher, jobs=jobs)
        end = time()
        elapsed_mp_cache = end - start
        assert elapsed_mp_cache < expected_max_elapsed


class SlowHasher(object):
    wait_time = 0.05

    def __init__(self, *args, **kwargs):
        pass

    def update(self, data):
        if data != b'':
            sleep(self.wait_time)

    def hexdigest(self):
        return ''


class IdentityHasher(object):

    def __init__(self, initial_data=b''):
        self.datas = [initial_data.decode('utf-8')]

    def update(self, data):
        self.datas.append(data.decode('utf-8'))

    def hexdigest(self):
        return ''.join(self.datas)
