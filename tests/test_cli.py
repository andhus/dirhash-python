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
    @pytest.mark.parametrize(
        'argstring, non_default_kwargs',
        [
            (
                '. -a md5',
                {}
            ),
            (
                '.. -a md5',
                {'directory': '..'}
            ),
            (
                'target-dir -a md5',
                {'directory': 'target-dir'}
            ),
            (
                '. -a sha256',
                {'algorithm': 'sha256'}
            ),
            # Filtering options
            (
                '. -a md5 -m "* !.*"',
                {'filtering': {'match': ['*', '!.*']}}
            ),
            (
                '. -a md5 --match "d1/* d2/*" --ignore "*.txt"',
                {'filtering': {'match': ['d1/*', 'd2/*', '!*.txt']}}
            ),
            (
                '. -a md5 --empty-dirs',
                {'filtering': {'empty_dirs': True}}
            ),
            (
                '. -a md5 --no-linked-dirs',
                {'filtering': {'linked_dirs': False}}
            ),
            (
                '. -a md5 --no-linked-files',
                {'filtering': {'linked_files': False}}
            ),
            # Protocol options
            (
                '. -a md5 --allow-cyclic-links',
                {'protocol': {'on_cyclic_link': 'hash_reference'}}
            ),
            # Implementation
            (
                '. -a md5 -j 10',
                {'jobs': 10}
            ),
            (
                '. -a md5 -s 32000',
                {'chunk_size': 32000}
            ),
        ]
    )
    def test_get_kwargs(self, argstring, non_default_kwargs):
        from dirhash.cli import get_kwargs
        filter_kwargs = {
            'match': ['*'],
            'empty_dirs': False,
            'linked_dirs': True,
            'linked_files': True
        }
        protocol_kwargs = {
            'entry_properties': ['data', 'name'],
            'on_cyclic_link': 'raise'
        }
        filter_kwargs.update(non_default_kwargs.pop('filtering', {}))
        protocol_kwargs.update(non_default_kwargs.pop('protocol', {}))
        kwargs = {
            'list': False,
            'directory': '.',
            'algorithm': 'md5',
            'filtering': filter_kwargs,
            'protocol': protocol_kwargs,
            'chunk_size': 2 ** 20,
            'jobs': 1
        }
        kwargs.update(non_default_kwargs)
        assert kwargs == get_kwargs(shlex.split(argstring))

    @pytest.mark.parametrize(
        'description, argstrings, output',
        [
            ('ARGS WITHOUT EFFECT WHEN LISTING',
             ['. -l',
              '. --list',
              '. -a md5 --list',
              '. -a sha256 --list',
              '. --properties name --list',
              '. --jobs 2 --list',
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
             ['. --empty-dirs --list'],
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

    @pytest.mark.parametrize(
        'argstring, kwargs, expected_hashes',
        [
            ('. -a md5',
             {'algorithm': 'md5'},
             ['594c48dde0776b03eddeeb0232190be7',
              'd8ab965636d48e407b73b9dbba4cb928',
              '050e7bc9ffcb09c15186c04e0f8026df']
             ),
            ('. -a sha256',
             {'algorithm': 'sha256'},
             ['23a04964149889e932ba3348fe22442f4f6a3b3fec616a386a70579ee857ab7b',
              '7b76bac43e963f9561f37b96b92d7a174094bff230c6efbf1d8bf650e8b40b7a',
              '7156da2b2e5a2926eb4b72e65f389343cb6aca0578f0aedcd6f7457abd67d8f5']),
        ]
    )
    def test_hash_result(self, argstring, kwargs, expected_hashes, tmpdir):
        # verify same result from cmdline and library + regression test of actual
        # hashes
        create_default_tree(tmpdir)
        with tmpdir.as_cwd():
            for add_argstring, add_kwargs, expected_hash in zip(
                ['', ' -p data', ' -p name'],
                [
                    {},
                    {'protocol': {'entry_properties': ['data']}},
                    {'protocol': {'entry_properties': ['name']}},
                ],
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
                full_argstring_mp = argstring + add_argstring + ' --jobs 2'
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

    def test_error_bad_argument(self, tmpdir):
        with tmpdir.as_cwd():
            o, error, returncode = dirhash_run('. --chunk-size not_an_int')
            assert returncode > 0
            assert error != ''
