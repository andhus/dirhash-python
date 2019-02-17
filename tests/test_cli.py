from __future__ import print_function, division

import os
import sys
import shlex
import subprocess

import dirhash

import pytest


console_script = os.path.join(
    os.path.dirname(sys.executable),
    'dirhash'
)


def dirhash_run(argstring, add_env=None):
    assert os.path.isfile(console_script)
    assert os.access(console_script, os.X_OK)
    if add_env:
        env = os.environ.copy()
        env.update(add_env)
    else:
        env = None
    process = subprocess.Popen(
        [console_script] + shlex.split(argstring),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    output, error = process.communicate()

    # in python3 output and error are `bytes` as opposed to `str` in python2
    if isinstance(output, bytes):
        output = output.decode('utf-8')
    if isinstance(error, bytes):
        error = error.decode('utf-8')

    return output, error, process.returncode


def create_default_tree(tmpdir):
    """
    tmpdir/
    |__.dir/
    |  |__file
    |__.file
    |__dir/
    |  |__file
    |__empty/
    |__file
    |__file.ext1
    |__file.ext2
    """
    dotdir = tmpdir.mkdir('.dir')
    dotdir.join('file').write('file in hidden sub-directory')
    tmpdir.join(".file").write('hidden file')
    dir = tmpdir.mkdir('dir')
    dir.join('file').write('file in sub-directory')
    tmpdir.mkdir('empty')
    tmpdir.join("file").write('file')
    tmpdir.join("file.ext1").write('file with extension .ext1')
    tmpdir.join("file.ext2").write('file with extension .ext2')


class TestCLI(object):

    def test_preprocess_kwargs(self):
        pass

    @pytest.mark.parametrize(
        'description, argstrings, output',
        [
            ('ARGS WITHOUT EFFECT WHEN LISTING',
             ['. -l',
              '. --list',
              '. -a md5 --list',
              '. -a sha256 --list',
              '. --content-only --list',
              '. --paths-only --list',
              '. --workers 2 --list',
              '. --chunk-size 2 --list'],
             ('.dir/file\n'
              '.file\n'
              'dir/file\n'
              'file\n'
              'file.ext1\n'
              'file.ext2\n')),
            ('IGNORE EXTENSION',
             ['. -x .ext1 --list',
              '. --ignore-extensions .ext1 --list',
              '. -i "*.ext1" --list',
              '. --ignore "*.ext1" --list',
              '. -m "* !*.ext1" --list',
              '. --match "* !*.ext1" --list'],
             ('.dir/file\n'
              '.file\n'
              'dir/file\n'
              'file\n'
              'file.ext2\n')),
            ('IGNORE MULTIPLE EXTENSIONS',
             ['. -x .ext1 .ext2 --list',
              '. -x ".ext1 .ext2" --list',
              '. --ignore-extensions .ext1 .ext2 --list',
              '. -i "*.ext1 *.ext2" --list',
              '. -i "*.ext*" --list'],
             ('.dir/file\n'
              '.file\n'
              'dir/file\n'
              'file\n')),
            ('IGNORE HIDDEN',
             ['. -d --list',
              '. --ignore-hidden --list',
              '. -i ".* .*/" --list'],
             ('dir/file\n'
              'file\n'
              'file.ext1\n'
              'file.ext2\n')),
            ('INCLUDE EMPTY',
             ['. --include-empty --list'],
             ('.dir/file\n'
              '.file\n'
              'dir/file\n'
              'empty/.\n'
              'file\n'
              'file.ext1\n'
              'file.ext2\n')),
        ]
    )
    def test_list(self, description, argstrings, output, tmpdir):
        create_default_tree(tmpdir)
        with tmpdir.as_cwd():
            for argstring in argstrings:
                o, error, returncode = dirhash_run(argstring)
                assert returncode == 0
                assert error == ''
                assert o == output

    def test_root_dirhashignore(self, tmpdir):
        create_default_tree(tmpdir)
        with tmpdir.as_cwd():
            output, error, returncode = dirhash_run('. --list')
        assert returncode == 0
        assert error == ''
        assert output == (
            '.dir/file\n'
            '.file\n'
            'dir/file\n'
            'file\n'
            'file.ext1\n'
            'file.ext2\n'
        )

        tmpdir.join(dirhash.ignorefilename).write('*.ext*')
        with tmpdir.as_cwd():
            output, error, returncode = dirhash_run('. --list')
        assert returncode == 0
        assert error == ''
        assert output == (
            '.dir/file\n'
            '.dirhashignore\n'
            '.file\n'
            'dir/file\n'
            'file\n'
        )

        tmpdir.join(dirhash.ignorefilename).write('*.ext*\n#comment\n.*/\n')
        with tmpdir.as_cwd():
            output, error, returncode = dirhash_run('. --list')
        assert returncode == 0
        assert error == ''
        assert output == (
            '.dirhashignore\n'
            '.file\n'
            'dir/file\n'
            'file\n'
        )

    def test_remote_dirhashignore(self, tmpdir):
        rootdir = tmpdir.mkdir('root')
        create_default_tree(rootdir)
        remote_dirhashignore = tmpdir.join('my_hashignore')
        remote_dirhashignore.write('*.ext*\n#comment\n.*/\n')

        with rootdir.as_cwd():
            output, error, returncode = dirhash_run('. --list')
        assert returncode == 0
        assert error == ''
        assert output == (
            '.dir/file\n'
            '.file\n'
            'dir/file\n'
            'file\n'
            'file.ext1\n'
            'file.ext2\n'
        )

        with rootdir.as_cwd():
            output, error, returncode = dirhash_run(
                '. --list', add_env={'DIRHASH_IGNORE': str(remote_dirhashignore)}
            )
        assert returncode == 0
        assert error == ''
        assert output == (
            '.file\n'
            'dir/file\n'
            'file\n'
        )

    def test_error_on_remote_dirhashignore_does_not_exist(self, tmpdir):
        rootdir = tmpdir.mkdir('root')
        create_default_tree(rootdir)
        remote_dirhashignore = tmpdir.join('non_existing_hashignore')
        with rootdir.as_cwd():
            output, error, returncode = dirhash_run(
                '. --list', add_env={'DIRHASH_IGNORE': str(remote_dirhashignore)}
            )
            assert returncode == 1
            assert error.startswith('dirhash: DIRHASH_IGNORE=')
            assert error.endswith(': No such file\n')
            assert output == ''

    @pytest.mark.parametrize(
        'argstring, kwargs, expected_hashes',
        [
            ('. -a md5',
             {'algorithm': 'md5'},
             ['e0d03dd48ab90d232ffabc0da9f08745',
              'fd1cc95ac2207c3f7d72c18fe01c675e',
              '0e4a5d4f8c1e4fda174a04c5693c6ea1']
             ),
            ('. -a sha256',
             {'algorithm': 'sha256'},
             ['f25c5dd69d60c1f127481407829c23e2be87df9d28d3c3e9d353b68cd4f7462d',
              'd444e19712ed1e318917b73a3623b9360e8489854d65586d3b74a6894e980b42',
              '8ab8e97f1bca5491c355c22f5f0236079f774e5d19454020d76becaf0c03c346']),
        ]
    )
    def test_hash_result(self, argstring, kwargs, expected_hashes, tmpdir):
        # verify same result from cmdline and library + regression test of actual
        # hashes
        create_default_tree(tmpdir)
        with tmpdir.as_cwd():
            for add_argstring, add_kwargs, expected_hash in zip(
                ['', ' --content-only', ' --paths-only'],
                [{}, {'content_only': True}, {'paths_only': True}],
                expected_hashes
            ):
                # run CLI
                full_argstring = argstring + add_argstring
                cli_out, error, returncode = dirhash_run(full_argstring)
                assert error == ''
                assert returncode == 0
                assert cli_out[-1] == '\n'
                cli_hash = cli_out[:-1]

                # run CLI multiproc
                full_argstring_mp = argstring + add_argstring + ' --workers 2'
                cli_out_mp, error_mp, returncode_mp = dirhash_run(full_argstring_mp)
                assert error_mp == ''
                assert returncode_mp == 0
                assert cli_out_mp[-1] == '\n'
                cli_hash_mp = cli_out_mp[:-1]

                # run lib function
                full_kwargs = kwargs.copy()
                full_kwargs.update(add_kwargs)
                lib_hash = dirhash.dirhash(str(tmpdir), **full_kwargs)

                assert cli_hash == cli_hash_mp == lib_hash == expected_hash
