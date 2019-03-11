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
                {'filter_options': {'match_patterns': ['*', '!.*']}}
            ),
            (
                '. -a md5 --match "d1/* d2/*" --ignore "*.txt"',
                {'filter_options': {'match_patterns': ['d1/*', 'd2/*', '!*.txt']}}
            ),
            (
                '. -a md5 --empty-dirs',
                {'filter_options': {'empty_dirs': True}}
            ),
            (
                '. -a md5 --no-linked-dirs',
                {'filter_options': {'linked_dirs': False}}
            ),
            (
                '. -a md5 --no-linked-files',
                {'filter_options': {'linked_files': False}}
            ),
            # Protocol options
            (
                '. -a md5 --allow-cyclic-links',
                {'protocol_options': {'on_cyclic_link': 'hash_reference'}}
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
        filter_options = {
            'match_patterns': ['*'],
            'empty_dirs': False,
            'linked_dirs': True,
            'linked_files': True
        }
        protocol_options = {
            'entry_properties': ['data', 'name'],
            'on_cyclic_link': 'raise'
        }
        filter_options.update(non_default_kwargs.pop('filter_options', {}))
        protocol_options.update(non_default_kwargs.pop('protocol_options', {}))
        kwargs = {
            'list': False,
            'directory': '.',
            'algorithm': 'md5',
            'filter_options': filter_options,
            'protocol_options': protocol_options,
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

    # def test_root_dirhashignore(self, tmpdir):
    #     create_default_tree(tmpdir)
    #     with tmpdir.as_cwd():
    #         output, error, returncode = dirhash_run('. --list')
    #     assert returncode == 0
    #     assert error == ''
    #     assert output == (
    #         '.dir/file\n'
    #         '.file\n'
    #         'dir/file\n'
    #         'file\n'
    #         'file.ext1\n'
    #         'file.ext2\n'
    #     )
    #
    #     tmpdir.join(dirhash.ignorefilename).write('*.ext*')
    #     with tmpdir.as_cwd():
    #         output, error, returncode = dirhash_run('. --list')
    #     assert returncode == 0
    #     assert error == ''
    #     assert output == (
    #         '.dir/file\n'
    #         '.dirhashignore\n'
    #         '.file\n'
    #         'dir/file\n'
    #         'file\n'
    #     )
    #
    #     tmpdir.join(dirhash.ignorefilename).write('*.ext*\n#comment\n.*/\n')
    #     with tmpdir.as_cwd():
    #         output, error, returncode = dirhash_run('. --list')
    #     assert returncode == 0
    #     assert error == ''
    #     assert output == (
    #         '.dirhashignore\n'
    #         '.file\n'
    #         'dir/file\n'
    #         'file\n'
    #     )

    # def test_remote_dirhashignore(self, tmpdir):
    #     rootdir = tmpdir.mkdir('root')
    #     create_default_tree(rootdir)
    #     remote_dirhashignore = tmpdir.join('my_hashignore')
    #     remote_dirhashignore.write('*.ext*\n#comment\n.*/\n')
    #
    #     with rootdir.as_cwd():
    #         output, error, returncode = dirhash_run('. --list')
    #     assert returncode == 0
    #     assert error == ''
    #     assert output == (
    #         '.dir/file\n'
    #         '.file\n'
    #         'dir/file\n'
    #         'file\n'
    #         'file.ext1\n'
    #         'file.ext2\n'
    #     )
    #
    #     with rootdir.as_cwd():
    #         output, error, returncode = dirhash_run(
    #             '. --list', add_env={'DIRHASH_IGNORE': str(remote_dirhashignore)}
    #         )
    #     assert returncode == 0
    #     assert error == ''
    #     assert output == (
    #         '.file\n'
    #         'dir/file\n'
    #         'file\n'
    #     )
    #
    # def test_error_on_remote_dirhashignore_does_not_exist(self, tmpdir):
    #     rootdir = tmpdir.mkdir('root')
    #     create_default_tree(rootdir)
    #     remote_dirhashignore = tmpdir.join('non_existing_hashignore')
    #     with rootdir.as_cwd():
    #         output, error, returncode = dirhash_run(
    #             '. --list', add_env={'DIRHASH_IGNORE': str(remote_dirhashignore)}
    #         )
    #         assert returncode == 1
    #         assert error.startswith('dirhash: DIRHASH_IGNORE=')
    #         assert error.endswith(': No such file\n')
    #         assert output == ''

    @pytest.mark.parametrize(
        'argstring, kwargs, expected_hashes',
        [
            ('. -a md5',
             {'algorithm': 'md5'},
             ['ba33eb4db4635e13869a16da6370000c',
              '3399d0283d9c0806b9c17e78ab8b1370',
              '1cc055682c4534de503b4d2aee268116']
             ),
            ('. -a sha256',
             {'algorithm': 'sha256'},
             ['a06f832d280c4f75b6d5486a6590c5d5ac93540e491bcd9f563729375125a2c4',
              '743a273e5076d7e38d5da8e2bdb1addcb90ac281f023ed053b9d09a2d1ce139e',
              'a98fb1523b52800a3fa9a7629c4fccfb914e4d91150a10f9328fd2a06463eff4']),
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
                    {'protocol_options': {'entry_properties': ['data']}},
                    {'protocol_options': {'entry_properties': ['name']}},
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
