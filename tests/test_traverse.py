from __future__ import print_function, division

# from pathlib import Path
from functools import partial

from py._path.local import LocalPath

import os
import pytest

from dirhash.compat import scandir

from dirhash.traverse import RecursionPath, RecursionFilterBase, traverse, DirNode
from dirhash.traverse import DirEntryReplacement
from dirhash.traverse import get_included_paths


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


def get_mock_recursion_path(relative, root=None, is_dir=False, is_symlink=False):
    dir_entry = DirEntryReplacement(
        path=relative,
        name=os.path.basename(relative)
    )
    dir_entry._is_dir = is_dir
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
    from dirhash.traverse import RecursionFilterBase as test_class

    @pytest.mark.parametrize(
        'description, filter_kwargs, expected_output',
        [
            ('include all',
             {'linked_dirs': True, 'linked_files': True},
             ['dir', 'dir/file.txt', 'ldir', 'dir/lfile']),
            ('default include all',
             {},
             ['dir', 'dir/file.txt', 'ldir', 'dir/lfile']),
            ('exclude linked dirs',
             {'linked_dirs': False, 'linked_files': True},
             ['dir', 'dir/file.txt', 'dir/lfile']),
            ('exclude linked files',
             {'linked_dirs': True, 'linked_files': False},
             ['dir', 'dir/file.txt', 'ldir']),
            ('exclude linked files and dirs',
             {'linked_dirs': False, 'linked_files': False},
             ['dir', 'dir/file.txt']),
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
        filtered_paths = list(self.test_class(**filter_kwargs)(paths))
        assert filtered_paths == [
            relpath_to_path[relpath] for relpath in expected_output
        ]


class TestMatchPatterns(TestRecursionFilterBase):
    from dirhash.traverse import MatchPatterns as test_class

    @pytest.mark.parametrize(
        'description, filter_kwargs, expected_output',
        [
            ('default include all',
             {'match_patterns': ['*']},
             ['dir', 'dir/file.txt', 'ldir', 'dir/lfile']),
            ('include only .txt files (dirs always included)',
             {'match_patterns': ['*.txt']},
             ['dir', 'dir/file.txt', 'ldir']),
            ('exclude .txt files (dirs always included)',
             {'match_patterns': ['*', '!*.txt']},
             ['dir', 'ldir', 'dir/lfile']),
        ]
    )
    def test_call_match(
        self,
        description,
        filter_kwargs,
        expected_output
    ):
        self.test_call(description, filter_kwargs, expected_output)


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
                            files=[rp('d1/d11/f1')])]),
                DirNode(
                    path=rp('d2'),
                    files=[rp('d2/f1')])])

        assert tree == tree_expected


class TestGetIncludedPaths(object):

    def test_basic(self, tmpdir):
        tmpdir.ensure('root/f1')
        tmpdir.ensure('root/d1/f1')
        tmpdir.ensure('root/d1/d11/f1')
        tmpdir.ensure('root/d2/f1')

        expected_filepaths = ['d1/d11/f1', 'd1/f1', 'd2/f1', 'f1']
        filepaths = get_included_paths(tmpdir.join('root'))
        assert filepaths == expected_filepaths

        # test pure string path as well
        filepaths = get_included_paths(tmpdir.join('root').strpath)
        assert filepaths == expected_filepaths

    def test_not_a_directory(self, tmpdir):
        tmpdir.ensure('root/f1')
        # does not exist
        with pytest.raises(ValueError):
            get_included_paths(tmpdir.join('wrong_root'))
        # is a file
        with pytest.raises(ValueError):
            get_included_paths(tmpdir.join('root/f1'))

    def test_symlinked_file(self, tmpdir):
        tmpdir.ensure('root/f1')
        tmpdir.ensure('linked_file')
        tmpdir.join('root/f2').mksymlinkto(tmpdir.join('linked_file'))
        root = tmpdir.join('root')

        # NOTE `follow_links` hash no effect if linked files are included
        filepaths = get_included_paths(root, follow_links=False)
        assert filepaths == ['f1', 'f2']

        filepaths = get_included_paths(root, follow_links=True)
        assert filepaths == ['f1', 'f2']

        filepaths = get_included_paths(
            root,
            recursion_filter=RecursionFilterBase(linked_files=False),
        )
        assert filepaths == ['f1']

    def test_symlinked_dir(self, tmpdir):
        tmpdir.ensure('root/f1')
        tmpdir.ensure('linked_dir/f1')
        tmpdir.ensure('linked_dir/f2')
        tmpdir.join('root/d1').mksymlinkto(tmpdir.join('linked_dir'))
        root = tmpdir.join('root')

        filepaths = get_included_paths(root, follow_links=True)
        assert filepaths == ['d1/f1', 'd1/f2', 'f1']

        # default is `follow_links=True`
        filepaths = get_included_paths(root)
        assert filepaths == ['d1/f1', 'd1/f2', 'f1']

        filepaths = get_included_paths(root, follow_links=False)
        assert filepaths == ['d1/.', 'f1']

        # correct way to ignore linked dirs completely:
        filepaths = get_included_paths(
            root,
            recursion_filter=RecursionFilterBase(linked_dirs=False),
        )
        assert filepaths == ['f1']
