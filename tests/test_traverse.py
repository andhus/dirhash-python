from __future__ import print_function, division

import os
import re

from time import sleep, time
from functools import partial

import pytest

from dirhash.compat import scandir
from dirhash.traverse import (
    DirNode,
    traverse,
    RecursionPath,
    RecursionFilter,
    DirEntryReplacement,
    CyclicLinkedDir, SymlinkRecursionError, LinkedDir)


def assert_dir_entry_equal(de1, de2):
    assert de1.path == de2.path
    assert de1.name == de2.name
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
        assert getattr(de1, method)(**kwargs) == getattr(de2, method)(**kwargs)
        # done two times to verify caching!
        assert getattr(de1, method)(**kwargs) == getattr(de2, method)(**kwargs)


def create_basic_entries(local_path):
    d1 = local_path.join('d1')
    d1.mkdir()
    f1 = local_path.join('f1')
    f1.write('file1')
    local_path.join('ld1').mksymlinkto(d1)
    local_path.join('lf1').mksymlinkto(f1)


class TestDirEntryReplacement(object):
    from dirhash.traverse import DirEntryReplacement as test_class

    def test_equivalence(self, tmpdir):
        create_basic_entries(tmpdir)
        for de_true in scandir(tmpdir):
            de_rep_from_entry = self.test_class.from_dir_entry(de_true)
            de_rep_from_path = self.test_class.from_path(tmpdir.join(de_true.name))
            assert_dir_entry_equal(de_rep_from_entry, de_true)
            assert de_rep_from_entry == de_true
            assert_dir_entry_equal(de_rep_from_path, de_true)
            assert de_rep_from_path == de_true

            # test not equal
            de_rep = self.test_class.from_dir_entry(de_true)
            assert de_rep != 'other type'

            for attribute in ['path', 'name']:
                de_rep = self.test_class.from_dir_entry(de_true)
                setattr(de_rep, attribute, "wrong value")
                assert de_rep != de_true

            for bool_attr in ['_is_dir', '_is_file', '_is_symlink']:
                de_rep = self.test_class.from_dir_entry(de_true)
                assert de_rep == de_true  # must load cache values before negating
                setattr(de_rep, bool_attr, not getattr(de_rep, bool_attr))
                assert de_rep != de_true

            de_rep = self.test_class.from_dir_entry(de_true)
            assert de_rep == de_true
            de_rep._stat_sym = "wrong_value"
            assert de_rep != de_true

            de_rep = self.test_class.from_dir_entry(de_true)
            assert de_rep == de_true
            de_rep._stat_nosym = "wrong_value"
            assert de_rep != de_true

    def test_raise_on_not_exists(self, tmpdir):
        with pytest.raises(IOError):
            self.test_class.from_path(tmpdir.join('no such entry'))


class TestRecursionPath(object):
    from dirhash.traverse import RecursionPath as test_class

    def test_from_root(self, tmpdir):
        create_basic_entries(tmpdir)
        rpath = self.test_class.from_root(tmpdir.realpath())
        assert rpath.root == rpath.real == tmpdir.realpath()
        assert rpath.relative == ''
        d1 = rpath._join(DirEntryReplacement.from_path(tmpdir.join('d1')))
        assert d1.relative == 'd1'
        assert d1.real == tmpdir.join('d1').realpath()
        assert d1.root == rpath.root
        ld1 = rpath._join(DirEntryReplacement.from_path(tmpdir.join('ld1')))
        assert ld1.relative == 'ld1'
        assert ld1.real == tmpdir.join('d1').realpath()
        assert d1.root == rpath.root

    def test_dir_entry_interface(self, tmpdir):
        create_basic_entries(tmpdir)
        for de_true in scandir(tmpdir):
            de_repl = DirEntryReplacement.from_path(de_true.path)
            rpath_from_de_true = self.test_class.from_root(de_true)
            rpath_from_de_repl = self.test_class.from_root(de_repl)
            rpath_from_path = self.test_class.from_root(de_true.path)
            assert_dir_entry_equal(de_true, rpath_from_de_true)
            assert_dir_entry_equal(de_true, rpath_from_de_repl)
            assert_dir_entry_equal(de_true, rpath_from_path)

    def test_scandir(self, tmpdir):
        create_basic_entries(tmpdir)
        rpath = self.test_class.from_root(tmpdir)
        sub_rpaths = list(rpath.scandir())
        sub_des = list(scandir(rpath))
        assert len(sub_rpaths) == len(sub_des)
        for sub_de, sub_rpath in zip(sub_des, sub_rpaths):
            assert_dir_entry_equal(sub_de, sub_rpath)

    def test_picklable(self, tmpdir):
        rpath = self.test_class.from_root(tmpdir)
        state = rpath.__getstate__()
        dir_entry = state[-1]
        assert isinstance(dir_entry, DirEntryReplacement)
        rpath.__setstate__(state)
        assert rpath._dir_entry is dir_entry


def get_mock_recursion_path(relative, root=None, is_dir=False, is_symlink=False):
    dir_entry = DirEntryReplacement(
        path=relative,
        name=os.path.basename(relative)
    )
    dir_entry._is_dir = is_dir
    dir_entry._is_file = not is_dir
    dir_entry._is_symlink = is_symlink
    return RecursionPath(
        root=root,
        relative=relative,
        real=None,
        dir_entry=dir_entry
    )


class TestDirNode(object):
    from dirhash.traverse import DirNode as test_class

    def test_init(self):
        dn = self.test_class(RecursionPath.from_root('.'), [], [None])
        assert dn.directories == tuple()
        assert dn.files == (None,)

    def test_empty(self):
        dn = self.test_class(RecursionPath.from_root('.'), [], [])
        assert dn.empty

    def test_apply(self, tmpdir):
        create_basic_entries(tmpdir)
        root = RecursionPath.from_root(tmpdir)
        d1 = next((rp for rp in root.scandir() if rp.name == 'd1'))
        dn = self.test_class(
            path=root,
            directories=[self.test_class(d1, files=[1., 2.])],
            files=[0.5]
        )
        dn_new = dn.apply(
            file_apply=lambda x: x*2,
            dir_apply=lambda dn_: sum(dn_.directories) ** 2 + sum(dn_.files)
        )
        assert dn_new == ((2 + 4) ** 2 + 1)


class TestRecursionFilterBase(object):
    from dirhash.traverse import RecursionFilter as test_class

    @pytest.mark.parametrize(
        'description, filter_kwargs, expected_output',
        [
            (
                'include all',
                {'linked_dirs': True, 'linked_files': True},
                ['dir', 'dir/file.txt', 'ldir', 'dir/lfile']
            ),
            (
                'default include all',
                {},
                ['dir', 'dir/file.txt', 'ldir', 'dir/lfile']
            ),
            (
                'exclude linked dirs',
                {'linked_dirs': False, 'linked_files': True},
                ['dir', 'dir/file.txt', 'dir/lfile']
            ),
            (
                'exclude linked files',
                {'linked_dirs': True, 'linked_files': False},
                ['dir', 'dir/file.txt', 'ldir']
            ),
            (
                'exclude linked files and dirs',
                {'linked_dirs': False, 'linked_files': False},
                ['dir', 'dir/file.txt']
            ),
            (
                'include only .txt files (dirs always included)',
                {'match': ['*.txt']},
                ['dir', 'dir/file.txt', 'ldir']
            ),
            (
                'exclude .txt files (dirs always included)',
                {'match': ['*', '!*.txt']},
                ['dir', 'ldir', 'dir/lfile']
            ),
        ]
    )
    def test_call(
        self,
        description,
        filter_kwargs,
        expected_output
    ):
        paths = [
            get_mock_recursion_path('dir', is_dir=True),
            get_mock_recursion_path('dir/file.txt'),
            get_mock_recursion_path('ldir', is_dir=True, is_symlink=True),
            get_mock_recursion_path('dir/lfile', is_symlink=True),
        ]
        relpath_to_path = {path.relative: path for path in paths}
        rfilter = self.test_class(**filter_kwargs)
        filtered_paths = list(rfilter(paths))
        assert filtered_paths == [
            relpath_to_path[relpath] for relpath in expected_output
        ]


def _slow_identity(x, wait_time):
    sleep(wait_time)
    return x


def get_slow_identity_f(wait_time):
    return partial(_slow_identity, wait_time=wait_time)


class TestTraverse(object):

    def test_basic(self, tmpdir):
        tmpdir.ensure('root/f1')
        tmpdir.ensure('root/d1/f1')
        tmpdir.ensure('root/d1/d11/f1')
        tmpdir.ensure('root/d2/f1')
        root = tmpdir.join('root')

        tree = traverse(root)

        def rp(relative):
            recursion_path = RecursionPath.from_root(root.join(relative))
            recursion_path.relative = relative
            recursion_path.root = root.strpath

            return recursion_path

        tree_expected = DirNode(
            path=rp(''),
            files=[rp('f1')],
            directories=[
                DirNode(
                    path=rp('d1'),
                    files=[rp('d1/f1')],
                    directories=[
                        DirNode(
                            path=rp('d1/d11'),
                            files=[rp('d1/d11/f1')]
                        )
                    ]
                ),
                DirNode(
                    path=rp('d2'),
                    files=[rp('d2/f1')]
                )
            ]
        )

        assert tree == tree_expected

    def test_not_a_directory(self, tmpdir):
        tmpdir.ensure('root/f1')
        # does not exist
        with pytest.raises(ValueError):
            traverse(tmpdir.join('wrong_root'))
        # is a file
        with pytest.raises(ValueError):
            traverse(tmpdir.join('root/f1'))

    @pytest.mark.parametrize('include_empty', [True, False])
    def test_cyclic_links(self, tmpdir, include_empty):
        root = tmpdir.join('root')
        d1 = root.join('d1')
        d1.ensure(dir=True)
        d1.join('link_back_d1').mksymlinkto(d1)
        d1.join('link_back_root').mksymlinkto(root)

        tree = traverse(root, include_empty=include_empty)

        def rp(relative):
            recursion_path = RecursionPath.from_root(root.join(relative))
            recursion_path.relative = relative
            recursion_path.root = root.strpath

            return recursion_path

        tree_expected = DirNode(
            path=rp(''),
            directories=[
                DirNode(
                    path=rp('d1'),
                    directories=[
                        CyclicLinkedDir(
                            path=rp('d1/link_back_d1'),
                            target_path=rp('d1')
                        ),
                        CyclicLinkedDir(
                            path=rp('d1/link_back_root'),
                            target_path=rp('')
                        )
                    ]
                )
            ]
        )

        assert tree == tree_expected

        with pytest.raises(SymlinkRecursionError) as exc_info:
            traverse(root, allow_cyclic_links=False)

        assert re.match(
            re.compile(
                "Symlink recursion: Real path .*root/d1' "
                "was encountered at .*root/d1' "
                "and then .*root/d1/link_back_d1'."),
            str(exc_info.value)
        )

    @pytest.mark.parametrize('include_empty', [True, False])
    def test_follow_links(self, tmpdir, include_empty):
        root = tmpdir.join('root')
        root.join('f1').ensure(dir=False)
        external_d1 = tmpdir.join('d1')
        external_d1.join('f2').ensure(dir=False)
        root.join('link_to_d1').mksymlinkto(external_d1)

        def rp(relative):
            recursion_path = RecursionPath.from_root(root.join(relative))
            recursion_path.relative = relative
            recursion_path.root = root.strpath

            return recursion_path

        tree_follow_false = traverse(
            root,
            include_empty=include_empty,
            follow_links=False
        )
        tree_follow_true = traverse(
            root,
            include_empty=include_empty,
            follow_links=True
        )
        tree_follow_false_expected = DirNode(
            path=rp(''),
            files=[rp('f1')],
            directories=[
                LinkedDir(path=rp('link_to_d1'))
            ]
        )
        tree_follow_true_expected = DirNode(
            path=rp(''),
            files=[rp('f1')],
            directories=[
                DirNode(
                    path=rp('link_to_d1'),
                    files=[rp('link_to_d1/f2')]
                )
            ]
        )
        assert tree_follow_false == tree_follow_false_expected
        assert tree_follow_true == tree_follow_true_expected

    def test_include_empty(self, tmpdir):
        root = tmpdir.join('root')
        root.join('d1').ensure(dir=True)

        tree_default = traverse(root)
        tree_empty_true = traverse(root, include_empty=True)

        def rp(relative):
            recursion_path = RecursionPath.from_root(root.join(relative))
            recursion_path.relative = relative
            recursion_path.root = root.strpath

            return recursion_path

        tree_empty_true_expected = DirNode(
            path=rp(''),
            directories=[DirNode(path=rp('d1'))]
        )

        assert tree_default == tree_empty_true_expected
        assert tree_empty_true == tree_empty_true_expected

        with pytest.raises(ValueError):
            traverse(root, include_empty=False)

    def test_multiprocess_speedup(self, tmpdir):
        num_files = 10
        for i in range(num_files):
            tmpdir.join('file_{}'.format(i)).ensure()

        wait_time = 0.05
        expected_min_elapsed = wait_time * num_files
        slow_file_apply = get_slow_identity_f(wait_time)
        start = time()
        traverse(tmpdir, file_apply=slow_file_apply)
        end = time()
        elapsed_sequential = end - start
        assert elapsed_sequential > expected_min_elapsed

        start = time()
        traverse(tmpdir, file_apply=slow_file_apply, jobs=num_files)
        end = time()
        elapsed_muliproc = end - start
        assert elapsed_muliproc < expected_min_elapsed / 2
        # just require at least half to account for multiprocessing overhead

    def test_cache_by_real_path_speedup(self, tmpdir):
        target_file = tmpdir.join('target_file')
        target_file.ensure()
        num_links = 10
        for i in range(num_links):
            tmpdir.join('link_{}'.format(i)).mksymlinkto(target_file)

        wait_time = 0.01
        expected_min_elapsed = wait_time * (num_links + 1)
        slow_file_apply = get_slow_identity_f(wait_time)
        start = time()
        traverse(tmpdir, file_apply=slow_file_apply)
        end = time()
        elapsed_sequential = end - start
        assert elapsed_sequential > expected_min_elapsed
        overhead = elapsed_sequential - expected_min_elapsed

        overhead_margin_factor = 1.5
        expected_max_elapsed = overhead * overhead_margin_factor + wait_time
        assert expected_max_elapsed < expected_min_elapsed
        start = time()
        traverse(tmpdir, file_apply=slow_file_apply, cache_file_apply=True)
        end = time()
        elapsed_cache = end - start
        assert elapsed_cache < expected_max_elapsed

    def test_cache_together_with_multiprocess_speedup(self, tmpdir):
        target_file_names = ['target_file_1', 'target_file_2']
        num_links_per_file = 10
        for i, target_file_name in enumerate(target_file_names):
            target_file = tmpdir.join(target_file_name)
            target_file.ensure()
            for j in range(num_links_per_file):
                tmpdir.join('link_{}_{}'.format(i, j)).mksymlinkto(target_file)
        num_links = num_links_per_file * len(target_file_names)

        wait_time = 0.01
        jobs = 2
        expected_min_elapsed = (
            wait_time * (num_links + len(target_file_names))
        ) / jobs
        slow_file_apply = get_slow_identity_f(wait_time)
        start = time()
        traverse(tmpdir, file_apply=slow_file_apply, jobs=2)
        end = time()
        elapsed_mp = end - start
        assert elapsed_mp > expected_min_elapsed
        overhead = elapsed_mp - expected_min_elapsed

        overhead_margin_factor = 1.5
        expected_max_elapsed = overhead * overhead_margin_factor + wait_time * 2
        assert expected_max_elapsed < expected_min_elapsed
        start = time()
        traverse(tmpdir, file_apply=slow_file_apply, cache_file_apply=True, jobs=2)
        end = time()
        elapsed_mp_cache = end - start
        assert elapsed_mp_cache < expected_max_elapsed


class TestIncludedPaths(object):
    """Verify included leafpaths given combinations of options"""

    @staticmethod
    def get_leafpaths(directory, **kwargs):
        """Extract relative paths to leafs (with extra "/." for directories)"""
        return [
            path.relative if path.is_file() else os.path.join(path.relative, '.')
            for path in traverse(directory, **kwargs).leafpaths()
        ]

    def test_basic(self, tmpdir):
        tmpdir.ensure('root/f1')
        tmpdir.ensure('root/d1/f1')
        tmpdir.ensure('root/d1/d11/f1')
        tmpdir.ensure('root/d2/f1')

        expected_filepaths = ['d1/d11/f1', 'd1/f1', 'd2/f1', 'f1']
        filepaths = self.get_leafpaths(tmpdir.join('root'))
        assert filepaths == expected_filepaths

        # test pure string path as well
        filepaths = self.get_leafpaths(tmpdir.join('root').strpath)
        assert filepaths == expected_filepaths

    def test_symlinked_file(self, tmpdir):
        tmpdir.ensure('root/f1')
        tmpdir.ensure('linked_file')
        tmpdir.join('root/f2').mksymlinkto(tmpdir.join('linked_file'))
        root = tmpdir.join('root')

        # NOTE `follow_links` has no effect if linked files are included
        filepaths = self.get_leafpaths(root, follow_links=False)
        assert filepaths == ['f1', 'f2']

        filepaths = self.get_leafpaths(root, follow_links=True)
        assert filepaths == ['f1', 'f2']

        filepaths = self.get_leafpaths(
            root,
            recursion_filter=RecursionFilter(linked_files=False),
        )
        assert filepaths == ['f1']

    def test_symlinked_dir(self, tmpdir):
        tmpdir.ensure('root/f1')
        tmpdir.ensure('linked_dir/f1')
        tmpdir.ensure('linked_dir/f2')
        tmpdir.join('root/d1').mksymlinkto(tmpdir.join('linked_dir'))
        root = tmpdir.join('root')

        filepaths = self.get_leafpaths(root, follow_links=True)
        assert filepaths == ['d1/f1', 'd1/f2', 'f1']

        # default is `follow_links=True`
        filepaths = self.get_leafpaths(root)
        assert filepaths == ['d1/f1', 'd1/f2', 'f1']

        filepaths = self.get_leafpaths(root, follow_links=False)
        assert filepaths == ['d1/.', 'f1']

        # correct way to ignore linked dirs completely:
        filepaths = self.get_leafpaths(
            root,
            recursion_filter=RecursionFilter(linked_dirs=False),
        )
        assert filepaths == ['f1']
