#!/usr/bin/env python
"""Get hash for the content and/or structure of a directory.
"""
from __future__ import print_function

import os
import sys
import argparse

import dirhash


def main():
    parser = argparse.ArgumentParser(description='Determine the hash for directory.')
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
            'Hashing algorithm to use. Always available: {}. Additionally available '
            'on current platform: {}. Note that the same algorithm may appear '
            'multiple times in this set under different names (thanks to '
            'OpenSSL) [https://docs.python.org/2/library/hashlib.html]'.format(
                sorted(dirhash.algorithms_guaranteed),
                sorted(dirhash.algorithms_available - dirhash.algorithms_guaranteed)
            )
        ),
        metavar=''
    )
    parser.add_argument(
        '-m', '--match',
        type=str,
        default='*',
        help='String of match-patterns, separated by blank space.'
    )
    parser.add_argument(
        '-i', '--ignore',
        type=str,
        default=None,
        help='String of ignore-patterns, separated by blank space.',
    )
    parser.add_argument(
        '-d', '--ignore-hidden',
        action='store_true',
        default=False,
        help='Ignore hidden ("dot") files and directories (short for '
             '`-ignore ".*, "`).'
    )
    parser.add_argument(
        '-x', '--ignore-extensions',
        nargs='+',
        help='List of file extensions to ignore.',
        metavar=''
    )

    target_group = parser.add_mutually_exclusive_group(required=False)
    target_group.add_argument(
        '-c', '--content-only',
        action='store_true',
        default=False,
        help='Hash only the content of files, not the name and location of files '
             'within the directory. NOTE (!) the hash will be different if the '
             '(alpha numerical) order of file paths changes.'
    )
    target_group.add_argument(
        '-p', '--paths-only',
        action='store_true',
        default=False,
        help='Hash only the file paths, i.e. the name and location of files '
             'within the directory.'
    )

    parser.add_argument(
        '--no-follow-links',
        dest='follow_links',
        action='store_false',
        help='Do not follow symbolic links to other *directories*. NOTE: directly '
             'linked files are always included.'
    )
    parser.set_defaults(follow_links=True)
    parser.add_argument(
        '--include-empty',
        action='store_true',
        default=False,
        help='Include empty directories (containing no files that meet the matching '
             'criteria). Note that the path to the directory itself must still meet '
             'the matching criteria (matched as if it was a file).'
    )
    parser.add_argument(
        '-s', '--chunk-size',
        default=2**20,
        type=int,
        help='The chunk size (in bytes) for reading fo files.'
    )
    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=1,
        help='Number of workers (parallel processes) to use.'
    )
    parser.add_argument(
        '-l', '--list',
        action='store_true',
        default=False,
        help='List the file paths that will be taken into account, followed by the '
             'hash of directory structure'
    )

    args = parser.parse_args()

    try:
        kwargs = preprocess_kwargs(vars(args))
        if kwargs.pop('list'):
            # kwargs below have no effect when listing
            for k in [
                'chunk_size', 'content_only', 'paths_only', 'algorithm', 'workers'
            ]:
                kwargs.pop(k)
            for leafpath in dirhash.get_included_paths(**kwargs):
                print(leafpath)
        else:
            print(dirhash.dirhash(**kwargs))
    except Exception as e:
        sys.stderr.write('dirhash: {}\n'.format(e))
        sys.exit(1)


def preprocess_kwargs(kwargs):
    kwargs['match'] = parse_string_arg(kwargs['match'])
    kwargs['ignore'] = parse_string_arg(kwargs['ignore'])
    # for consistency with `match` and `ignore`, we allow ignore_extensions to be a
    # space separate string (not the recommended usages).
    x = 'ignore_extensions'
    if kwargs[x] is not None:
        if len(kwargs[x]) == 1:
            kwargs[x] = parse_string_arg(kwargs[x][0])
    else:
        kwargs[x] = []

    remote_ignorefile = os.environ.get('DIRHASH_IGNORE', None)
    root_ignorefile_path = os.path.join(kwargs['directory'], dirhash.ignorefilename)
    if os.path.exists(root_ignorefile_path):
        kwargs['ignore'] = (
            dirhash._parse_ignorefile(kwargs['directory']) + list(kwargs['ignore']))
    elif remote_ignorefile:
        if not os.path.exists(remote_ignorefile):
            raise ValueError(
                'DIRHASH_IGNORE={}: No such file'.format(remote_ignorefile)
            )
        with open(remote_ignorefile) as f:
            kwargs['ignore'] = f.readlines() + kwargs['ignore']

    return kwargs


def parse_string_arg(string_arg):
    if string_arg is None or string_arg == '':
        return []
    return string_arg.split(' ')


if __name__ == '__main__':  # pragma: no cover
    main()
