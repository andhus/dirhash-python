#!/usr/bin/env python
"""Get hash for the content and/or structure of a directory.
"""
from __future__ import print_function

import sys
import argparse

import dirhash


def main():
    try:
        kwargs = get_kwargs(sys.argv[1:])
        if kwargs.pop('list'):
            # kwargs below have no effect when listing
            for k in ['algorithm', 'chunk_size', 'jobs', 'entry_properties']:
                kwargs.pop(k)
            for leafpath in dirhash.included_paths(**kwargs):
                print(leafpath)
        else:
            print(dirhash.dirhash(**kwargs))
    except Exception as e:  # pragma: no cover (not picked up by coverage)
        sys.stderr.write('dirhash: {}\n'.format(e))
        sys.exit(1)


def get_kwargs(args):
    parser = argparse.ArgumentParser(
        description='Determine the hash for a directory.'
    )
    parser.add_argument(
        '-v', '--version',
        action='version',
        version='dirhash {}'.format(dirhash.__version__)
    )
    parser.add_argument(
        'directory',
        help='Directory to hash.'
    )
    parser.add_argument(
        '-a', '--algorithm',
        choices=dirhash.algorithms_available,
        default='md5',
        help=(
            'Hashing algorithm to use, by default "md5". Always available: {}. '
            'Additionally available on current platform: {}. Note that the same '
            'algorithm may appear multiple times in this set under different names '
            '(thanks to OpenSSL) '
            '[https://docs.python.org/2/library/hashlib.html]'.format(
                sorted(dirhash.algorithms_guaranteed),
                sorted(dirhash.algorithms_available - dirhash.algorithms_guaranteed)
            )
        ),
        metavar=''
    )

    filter_options = parser.add_argument_group(
        title='Filtering options',
        description=(
            'Specify what files and directories to include. All files and '
            'directories (including symbolic links) are included by default. The '
            '--match/--ignore arguments allows for selection using glob/wildcard '
            '(".gitignore style") path matching. Paths relative to the root '
            '`directory` (i.e. excluding the name of the root directory itself) are '
            'matched against the provided patterns. For example, to only include '
            'python source files, use: `dirhash path/to/dir -m "*.py"` or to '
            'exclude hidden files and directories use: '
            '`dirhash path/to.dir -i ".*" ".*/"` which is short for '
            '`dirhash path/to.dir -m "*" "!.*" "!.*/"`. By adding the --list '
            'argument, all included paths, for the given filtering arguments, are '
            'returned instead of the hash value. For further details see '
            'https://github.com/andhus/dirhash/README.md#filtering'
        )
    )
    filter_options.add_argument(
        '-m', '--match',
        nargs='+',
        default=['*'],
        help=(
            'One or several patterns for paths to include. NOTE: patterns '
            'with an asterisk must be in quotes ("*") or the asterisk '
            'preceded by an escape character (\*).'
        ),
        metavar=''
    )
    filter_options.add_argument(
        '-i', '--ignore',
        nargs='+',
        default=None,
        help=(
            'One or several patterns for paths to exclude. NOTE: patterns '
            'with an asterisk must be in quotes ("*") or the asterisk '
            'preceded by an escape character (\*).'
        ),
        metavar=''
    )
    filter_options.add_argument(
        '--empty-dirs',
        action='store_true',
        default=False,
        help='Include empty directories (containing no files that meet the matching '
             'criteria and no non-empty sub directories).'
    )
    filter_options.add_argument(
        '--no-linked-dirs',
        dest='linked_dirs',
        action='store_false',
        help='Do not include symbolic links to other directories.'
    )
    filter_options.add_argument(
        '--no-linked-files',
        dest='linked_files',
        action='store_false',
        help='Do not include symbolic links to files.'
    )
    parser.set_defaults(linked_dirs=True, linked_files=True)

    protocol_options = parser.add_argument_group(
        title='Protocol options',
        description=(
            'Specify what properties of files and directories to include and '
            'whether to allow cyclic links. For further details see '
            'https://github.com/andhus/dirhash/DIRHASH_STANDARD.md#protocol'
        )
    )
    protocol_options.add_argument(
        '-p', '--properties',
        nargs='+',
        dest='entry_properties',
        default=['data', 'name'],
        help=(
            'List of file/directory properties to include in the hash. Available '
            'properties are: {} and at least one of name and data must be '
            'included. Default is [data name] which means that both the name/paths'
            ' and content (actual data) of files and directories will be included'
        ).format(list(dirhash.Protocol.EntryProperties.options)),
        metavar=''
    )
    protocol_options.add_argument(
        '-c', '--allow-cyclic-links',
        default=False,
        action='store_true',
        help=(
            'Allow presence of cyclic links (by hashing the relative path to the '
            'target directory).'
        )
    )

    implementation_options = parser.add_argument_group(
        title='Implementation options',
        description=''
    )
    implementation_options.add_argument(
        '-s', '--chunk-size',
        default=2**20,
        type=int,
        help='The chunk size (in bytes) for reading of files.'
    )
    implementation_options.add_argument(
        '-j', '--jobs',
        type=int,
        default=1,  # TODO make default number of cores?
        help='Number of jobs (parallel processes) to use.'
    )

    special_options = parser.add_argument_group(title='Special options')
    special_options.add_argument(
        '-l', '--list',
        action='store_true',
        default=False,
        help='List the file paths that will be taken into account, given the '
             'provided filtering options.'
    )

    return vars(parser.parse_args(args))


if __name__ == '__main__':  # pragma: no cover
    main()
