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
            for k in ['algorithm', 'chunk_size', 'jobs']:
                kwargs.pop(k)
            for leafpath in dirhash.included_paths(**kwargs):
                print(leafpath)
        else:
            print(dirhash.dirhash(**kwargs))
    except Exception as e:  # pragma: no cover (not picked up by coverage)
        sys.stderr.write('dirhash: {}\n'.format(e))
        sys.exit(1)


def get_kwargs(args):
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

    filter_options = parser.add_argument_group(
        title='Filtering options',
        description='TODO: what files and directories to include...'
    )
    filter_options.add_argument(
        '-m', '--match',
        type=str,
        default='*',
        help='String of match-patterns, separated by blank space.'
    )
    filter_options.add_argument(
        '-i', '--ignore',
        type=str,
        default=None,
        help='String of ignore-patterns, separated by blank space.',
    )
    filter_options.add_argument(
        '-d', '--ignore-hidden',
        action='store_true',
        default=False,
        help='Ignore hidden ("dot") files and directories (short for '
             '`-ignore ".*, "`).'
    )
    filter_options.add_argument(
        '-x', '--ignore-extensions',
        nargs='+',
        help='List of file extensions to ignore.',
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
        description='TODO: what properties to hash...'
    )
    protocol_options.add_argument(
        '-p', '--properties',
        nargs='+',
        help='List of properties of files and directories to include in the hash. '
             'Available properties are: {} and at least one of "name" and "data" '
             'must be included'.format(dirhash.Protocol.EntryProperties.options),
        metavar=''
    )
    protocol_options.add_argument(
        '-c', '--allow-cyclic-links',
        default=False,
        action='store_true',
        help='Allow presence of cyclic links.'
    )


    implementation_options = parser.add_argument_group(
        title='Implementation options',
        description='TODO'
    )
    implementation_options.add_argument(
        '-s', '--chunk-size',
        default=2**20,
        type=int,
        help='The chunk size (in bytes) for reading fo files.'
    )
    implementation_options.add_argument(
        '-j', '--jobs',
        type=int,
        default=1,  # TODO make default number of cores!
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

    return preprocess_kwargs(vars(parser.parse_args(args)))


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
    match_kwargs = {}
    for kwarg in ['match', 'ignore', 'ignore_extensions', 'ignore_hidden']:
        match_kwargs[kwarg] = kwargs.pop(kwarg)
    match_patterns = dirhash.get_match_patterns(**match_kwargs)

    filtering_kwargs = {
        'match': match_patterns,
        'linked_dirs': kwargs.pop('linked_dirs'),
        'linked_files': kwargs.pop('linked_files'),
        'empty_dirs': kwargs.pop('empty_dirs'),
    }
    protocol_kwargs = {
        'allow_cyclic_links': kwargs.pop('allow_cyclic_links'),
        'entry_properties': kwargs.pop('properties') or ["data", "name"]
    }
    kwargs['filtering'] = filtering_kwargs
    kwargs['protocol'] = protocol_kwargs

    # TODO remove!?
    # remote_ignorefile = os.environ.get('DIRHASH_IGNORE', None)
    # root_ignorefile_path = os.path.join(kwargs['directory'], dirhash.ignorefilename)
    # if os.path.exists(root_ignorefile_path):
    #     kwargs['ignore'] = (
    #         dirhash._parse_ignorefile(kwargs['directory']) + list(kwargs['ignore']))
    # elif remote_ignorefile:
    #     if not os.path.exists(remote_ignorefile):
    #         raise ValueError(
    #             'DIRHASH_IGNORE={}: No such file'.format(remote_ignorefile)
    #         )
    #     with open(remote_ignorefile) as f:
    #         kwargs['ignore'] = f.readlines() + kwargs['ignore']
    return kwargs


def parse_string_arg(string_arg):
    if string_arg is None or string_arg == '':
        return []
    return string_arg.split(' ')


if __name__ == '__main__':  # pragma: no cover
    main()
