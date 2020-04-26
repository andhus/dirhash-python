[![Build Status](https://travis-ci.com/andhus/dirhash-python.svg?branch=master)](https://travis-ci.com/andhus/dirhash-python)
[![codecov](https://codecov.io/gh/andhus/dirhash-python/branch/master/graph/badge.svg)](https://codecov.io/gh/andhus/dirhash-python)

# dirhash
A lightweight python module and CLI for computing the hash of any
directory based on its files' structure and content.
- Supports all hashing algorithms of Python's built-in `hashlib` module.
- Glob/wildcard (".gitignore style") path matching for expressive filtering of files to include/exclude.
- Multiprocessing for up to [6x speed-up](#performance)

The hash is computed according to the [Dirhash Standard](https://github.com/andhus/dirhash), which is designed to allow for consistent and collision resistant generation/verification of directory hashes across implementations.

## Installation
From PyPI:
```commandline
pip install dirhash
```
Or directly from source:
```commandline
git clone git@github.com:andhus/dirhash-python.git
pip install dirhash/
```

## Usage
Python module:
```python
from dirhash import dirhash

dirpath = "path/to/directory"
dir_md5 = dirhash(dirpath, "md5")
pyfiles_md5 = dirhash(dirpath, "md5", match=["*.py"])
no_hidden_sha1 = dirhash(dirpath, "sha1", ignore=[".*", ".*/"])
```
CLI:
```commandline
dirhash path/to/directory -a md5
dirhash path/to/directory -a md5 --match "*.py"
dirhash path/to/directory -a sha1 --ignore ".*"  ".*/"
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

As a reference, let's compare the performance of the `dirhash` [CLI](https://github.com/andhus/dirhash-python/blob/master/src/dirhash/cli.py) 
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

The benchmark was run a MacBook Pro (2018), further details and source code [here](https://github.com/andhus/dirhash-python/tree/master/benchmark).

## Documentation
Please refer to `dirhash -h`, the python [source code](https://github.com/andhus/dirhash-python/blob/master/src/dirhash/__init__.py) and the [Dirhash Standard](https://github.com/andhus/dirhash).