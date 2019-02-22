[![Build Status](https://travis-ci.com/andhus/dirhash.svg?branch=master)](https://travis-ci.com/andhus/dirhash)
[![codecov](https://codecov.io/gh/andhus/dirhash/branch/master/graph/badge.svg)](https://codecov.io/gh/andhus/dirhash)

# dirhash
A lightweight python module and tool for computing the hash of any
directory based on its files' structure and content.
- Supports any hashing algorithm of Python's built-in `hashlib` module
- `.gitignore` style "wildmatch" patterns for expressive filtering of files to 
include/exclude.
- Multiprocessing for up to [6x speed-up](#performance)

## Installation
From PyPI:
```commandline
pip install dirhash
```
Or directly from source:
```commandline
git clone git@github.com:andhus/dirhash.git
pip install dirhash/
```

## Usage
Python module:
```python
from dirhash import dirhash

dirpath = 'path/to/directory'
dir_md5          = dirhash(dirpath, 'md5')
filtered_sha1    = dirhash(dirpath, 'sha1', ignore=['.*', '.*/', '*.pyc'])
pyfiles_sha3_512 = dirhash(dirpath, 'sha3_512', match=['*.py'])
```
CLI:
```commandline
dirhash path/to/directory -a md5
dirhash path/to/directory -a sha1 -i ".*  .*/  *.pyc"
dirhash path/to/directory -a sha3_512 -m "*.py"
```

## Why?
If you (or your application) need to verify the integrity of a set of files as well
as their name and location, you might find this useful. Use-cases range from 
verification of your image classification dataset (before spending GPU-$$$ on 
training your fancy Deep Learning model) to validation of generated files in
regression-testing.

There isn't really a standard way of doing this. There are plenty of recipes out 
there (see e.g. these SO-questions for [linux](https://stackoverflow.com/questions/545387/linux-compute-a-single-hash-for-a-given-folder-contents)
and [python](https://stackoverflow.com/questions/24937495/how-can-i-calculate-a-hash-for-a-filesystem-directory-using-python))
but I couldn't find one that is properly tested (there are some gotcha:s to cover!) 
and documented with a compelling user interface. `dirhash` was created with this as 
the goal.

[checksumdir](https://github.com/cakepietoast/checksumdir) is another python 
module/tool with similar intent (that inspired this project) but it lacks much of the
functionality offered here (most notably including file names/structure in the hash)
and lacks tests.

## Performance
The python `hashlib` implementation of common hashing algorithms are highly
optimised. `dirhash` mainly parses the file tree, pipes data to `hashlib` and 
combines the output. Reasonable measures have been taken to minimize the overhead 
and for common use-cases, the majority of time is spent reading data from disk 
and executing `hashlib` code.

The main effort to boost performance is support for multiprocessing, where the
reading and hashing is parallelized over individual files.

As a reference, let's compare the performance of the `dirhash` [CLI](https://github.com/andhus/dirhash/blob/master/dirhash/cli.py) 
with the shell command:

`find path/to/folder -type f -print0 | sort -z | xargs -0 md5 | md5` 

which is the top answer for the SO-question: 
[Linux: compute a single hash for a given folder & contents?](https://stackoverflow.com/questions/545387/linux-compute-a-single-hash-for-a-given-folder-contents)
Results for two test cases are shown below. Both have 1 GiB of random data: in 
"flat_1k_1MB", split into 1k files (1 MiB each) in a flat structure, and in 
"nested_32k_32kB", into 32k files (32 KiB each) spread over the 256 leaf directories 
in a binary tree of depth 8.

Implementation      | Test Case       | Time (s) | Speed up
------------------- | --------------- | -------: | -------:
shell reference     | flat_1k_1MB     | 2.29     | -> 1.0
`dirhash`           | flat_1k_1MB     | 1.67     | 1.36
`dirhash`(8 workers)| flat_1k_1MB     | 0.48     | **4.73**
shell reference     | nested_32k_32kB | 6.82     | -> 1.0
`dirhash`           | nested_32k_32kB | 3.43     | 2.00
`dirhash`(8 workers)| nested_32k_32kB | 1.14     | **6.00**

The benchmark was run a MacBook Pro (2018), further details and source code [here](https://github.com/andhus/dirhash/tree/master/benchmark).

## Documentation
Please refer to `dirhash -h` and the python [source code](https://github.com/andhus/dirhash/blob/master/dirhash/__init__.py).




# The Dirhash Standard

This sections suggests a standard for how to compute a single hash value, the
`DIRHASH`, of a filesystem directory.

---

*TL;DR*: Data and metadata of files and subdirectories are hashed recursively by any regular hash function. Options are provided for filtering of which files to include as well as which data and metadata to consider for the included files. A fixed set of such options, including the hash function, will under the Dirhash standard generate a deterministic hash value for any directory.

---

The standard is designed with the following objectives:
- *Platform and filesystem agnostic*.
- *Easy to understand and implement* in any language.
- *Extendable* - instead of trying to cover all possible use cases. 
- *Same collision resistance* as underlying hashing algorithm.

The process of computing the `DIRHASH` relies on the concepts below. Each concept is configurable by one or several options, which *affects the obtained hash value* (except for "Implementation" options):
1. **Hash Function**: The underlying hash function used to map any data to a fixed length hash value.
2. **Filtering**: The process of selecting what *entries* (sub directories and files) within the directory to include.
3. **Protocol**: Defines which data/metadata to include for each entry and precisely  how to it is fed to the hash function for a reproducible and collision resistant result.
4. **Implementation**: Additional, implementation specific, aspects of how the `DIRHASH` is programmatically obtained.

Since the configuration options for 1-3 above affects the obtained `DIRHASH`, they 
must be represented in a `DIRHASH`-checksum of a directory.
Subsequently, the naming and effect of these options must be standardized to allow 
for communication  and verification of such checksum:s.
It is not required that a given package/module, implementing the 
`DIRHASH` standard, strictly follows the option naming (to adhere 
to language specific convention e.g.) as long as they can be translated to the 
standard options in checksums.

Implementation options are naturally not covered by this standard as these *should
not affect the obtained* `DIRHASH`. Such options should be clearly distinguished 
from those in 1-3.



## Hash Function
All data and metadata which is the basis for the `DIRHASH` is hashed by a standard hash function. The Dirhash Standard defines precisely how data is fed to the hash function. The hash functions is specified using the single option `algorithm`. The following algorithms are covered in the Dirhash Standard: [`"md5"`](https://www.ietf.org/rfc/rfc1321.txt), [`"sha1"`](https://tools.ietf.org/html/rfc3174), [`"sha224"`, `"sha256"`, `"sha384"`, `"sha512"`](https://tools.ietf.org/html/rfc6234) but can naturally be extended.


### Hash function Options
Name  | Type             | Default             | Description 
----  | ---------------- | ------------------- | -----------
algorithm | String | (no default) | The standard hashing algorithm (function) to use. 




## Filtering
Mainly matching of file path


### Filtering Options
Name  | Type             | Default             | Description 
----  | ---------------- | ------------------- | -----------
match_patterns | Array of Strings | `["*"]` (match all) | Wildcard matching. Path relative to the dirhash root is matched against the provided patterns. The path must match at least on of the "match patterns" not starting `!` and non of the "ignore patterns" starting with `!`.
include_linked_dirs | Boolean | `true` | Include symbolic links to directories.
include_linked_files | Boolean | `true` | Include symbolic links to files.
include_empty_dirs | Boolean | `false` | Include empty directories. A directory is considered empty if it contains no files or directories to include *according the filtering criteria*.




## Protocol
The `DIRHASH` of a directory is obtained by taking the underlying hash function's
hexdigest of a `DIR-DESCRIPTOR` string.

The `DIR-DESCRIPTOR` is composed by concatenation of an ordered sequence of 
`ENTRY-DESCRIPTOR`:s, each followed by a newline:

```<entry-descriptor>\n<entry-descriptor>...<entry-descriptor>\n```,

in python:

```python
dir_descriptor = '\n'.join(sorted(entry_descriptors) + [''])
```

A *directory entry* is either a directory, a file or a symbolic link. Other 
file types (named pipe, socket, device file, door) are always excluded in the core 
version of the Dirhash Standard. No distinction is  made between files and 
"hard links" to files.

The `ENTRY-DESCRIPTOR` is composed by concatenation of an ordered sequence of entry
properties separated by the [null character](https://en.wikipedia.org/wiki/Null_character) `\000`, where each property is represented by its name 
and value separated by a colon `:`:

```<name>:<value> <name>:<value>...```,

```python
properties = {'property_1': 'value_1', ...}
descriptor = '\000'.join(['{}:{}'.format(k, v) for k, v in sorted(properties.items())])
```
Thus the null character is the only character not allowed in property names or 
values.


### Entry Properties
Refers to data or metadata of a Directory Entry.

Name  | Value | Inclusion | Comment/Rationale
----- | ----- | --------- | -----------------
dirhash | The `DIRHASH` of the directory. A special case is when the protocol option `on_cyclic_link` is `store reference` see [cyclic links](#cyclic-links) section below. | Always included for directories. *Not applicable to files*. | This is the recursive part of the Dirhash Protocol, all content of (sub) directories is summarized by the dirhash.
data | Hash function hexdigest of the binary data of the file, or the file linked to, if a symlink. | Optional, but one of `name` and `data` must always be included. *Not applicable to directories*. | For the typical use case, content should affect the hash. Without it, only the structure of the file tree is hashed. 
name | The name of the entry (the name of the link itself if a symlink, *not* the entry linked to). | Optional, but one of `name` and `data` must always be included. | For the typical use case, the entry name should affect the hash, so that content and other metadata is tied to the name and, subsequently, to the entry's relative path to the dirhash root (which follows from the recursive nature of the Dirhash Standard).
is_link | Whether the entry is a symlink; `true` or `false`. | Optional. | For the typical use case, it does *not* matter if a file or directory is linked or not - the file tree is "perceived the same" for many applications. If it matters, this property can be included. 


### Cyclic Links
When using symbolically linked directories it is possible to create cycles in the, otherwise acyclic, graph representing the file tree. If not handled properly, this leads to infinite recursion when traversing the file tree (this is e.g. the case for Python's built in [`os.walk(directory, followlinks=True)`](https://stackoverflow.com/questions/36977259/avoiding-infinite-recursion-with-os-walk/36977580)). Moreover, this breaks the recursive definition of the Dirhash Protocol, which offers two alternative ways of handling the special case, specified by the option `on_cyclic_link`.

#### `on_cyclic_link`: `"raise"`
The the first option is to consider cyclic links an [error condition](#error-conditions) and raise an appropriate exception when detected (preferably before reaching the recursion limit of language of implementation!).

#### `on_cyclic_link`: `"hash reference"`
The other option is to replace the dirhash value with the hash function hexdigest of the relative path from the link to the target. The path is normalized according the unix standard (with forward slash `/` separating directories) and without a leading or trailing slash. This is done for the *first symlink to a directory that has already been visited on the current branch of recursion*. This requires that the real path (or inode and device ID) of visited directories, together with the path relative to the dirhash root, is cached during traversal of the file tree.  

In the example below there are cycles all branches `root/A/B`, `root/A/C` and `root/D`.
```
root/
|__A/
|  |__B/
|  |  |__toA@ -> ..
|  |
|  |__C/
|     |__toA@ -> ..
|
|__D/
   |__toB@ -> ../A
```
In this case, the value of the dirhash property for the symlinks `root/A/B/toA`, `root/A/C/toA` and `root/D/toB/toA/B/toA` are replaced by the hash of `".."`. Note that for the third branch, the cyclic reference can be *detected* already at `root/D/toB/toA/B` (since `B` is already visited) but it is for `root/D/toB/toA/B/toA` that the replacement happens. This reflects the fact that it is the `toA` that's *causing* the cycle (not `root/D/toB` or `root/D/toB/toA/B`) and at `root/D/toB/toA/` it can not yet be detected.



### Protocol Options
Name  | Type             | Default             | Description 
----  | ---------------- | ------------------- | -----------
entry_properties | Array of Strings | `["name", "content"]` | Which Directory Entry properties to consider. NOTE that `type` is a mandatory property and should not be provided
on_cyclic_link | String, One of `"raise"` and `"hash reference"` | `"raise"` | ...

The Dirhash Protocol is designed so that the same hash should not be obtained with different protocol options (even if that would not necessarily be a problem, since when comparing checksums, the options must be provided as well). This is convenient since it means that when the same hash is obtained one can be sure that the same Protocol Options 



## Error Conditions
**Directory not accessible**: Not accessible sub directories results in an error, unless excluded by the `match` filtering option.

**File not accessible**: Not accessible files results in an error if `hash_content` is `true`, unless excluded by the `match` filtering option.

**Cyclic Symbolic Links**: TODO


## The `DIRSUM` JSON Object
```json
{
   "dirhash": "...",
   "algorithm": "...",
   "filtering_options": {
      "match_patterns": ["*"],
      "linked_dirs": true,
      "linked_files": true,
      "empty_dirs": false},
   "protocol_options": {
      "entry_properties": ["name", "data"],
      "on_cyclic_link": "raise"}
}
```

Recommended file extension: `<name>.dirsum.json`


## Possible Extensions
- **Permission Properties**: These are hard to get platform independent (different on windows/unix). The best option is probably to let go of platform independence here. Possible properties could be `permission-[owner|group|user]` or `permission-me` for permissions of current 
process, 
- **Owning User/Group**
- **Last Modified/Opened Properties**


## Open Questions
- ...