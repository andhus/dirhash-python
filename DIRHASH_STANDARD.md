# The Dirhash Standard

[https://github.com/andhus/dirhash/DIRHASH_STANDARD.md](https://github.com/andhus/dirhash/DIRHASH_STANDARD.md
)

VERSION: 0.1.0


## Table of Content

- [Introduction](#introduction)
- [Hash Function](#hash-function)
- [Filtering](#filtering)
- [Protocol](#protocol)
- [Error Conditions](#error-conditions)
- [The `DIRSUM` Object](#the-dirsum-object)
- [Extensions](#extensions)
- [Contribute](#contribute)
- [Appendix](#appendix)

## Introduction
The Dirhash Standard describes a formal procedure for computing a single hash value, the `DIRHASH`, of a filesystem directory.

---

*TL;DR*: Data and metadata of files and subdirectories are hashed recursively by a standard hash function. The Dirhash Standard defines options for filtering of which files to include, which data and metadata to consider for the included files and a protocol for how any piece of information is fed to the hash function. A fixed set of options, including the hash function, yields a deterministic hash value for any directory under the Dirhash Standard.

---

The standard is designed with the following objectives:
- *Platform and filesystem agnostic*.
- *Easy to understand and implement* in any language.
- *Extendable* - instead of trying to cover all possible use cases. 
- *Same collision resistance* as the underlying hashing algorithm.

The process of computing the `DIRHASH` relies on the concepts below. Each concept is configurable by one or several options, which *affects the obtained hash value* (except for "Implementation" options):
1. **Hash Function**: The underlying hash function used to map any data to a fixed length hash value.
2. **Filtering**: The process of selecting what *entries* (subdirectories and files) within the directory to include.
3. **Protocol**: Defines which data and metadata to include for each entry and precisely how it is fed to the hash function for a reproducible and collision resistant result.
4. **Implementation**: Additional, implementation specific, aspects of how the `DIRHASH` is programmatically obtained.

Since the configuration options for 1-3 above affects the obtained `DIRHASH`, they must be represented in a [`DIRHASH` based checksum](#the-dirsum-object) of a directory. Subsequently, the naming and interpretation of these options must be standardized to allow for communication and verification of such checksums.
It is not required that a given package/module, implementing the `DIRHASH` standard, strictly follows the option naming (to adhere to language-specific convention e.g.) as long as they are properly translated to the standard options.

Implementation options are naturally not covered by the Dirhash Standard as these *should not affect the obtained* `DIRHASH`. Such options should be clearly distinguished from those in 1-3.



## Hash Function
All data and metadata which forms the basis for the `DIRHASH` is hashed by a standard hash function. The Dirhash Standard defines precisely how data is fed to the hash function. The hash function is specified using the single option `algorithm`. The following algorithms are covered in the Dirhash Standard: [`"md5"`](https://www.ietf.org/rfc/rfc1321.txt), [`"sha1"`](https://tools.ietf.org/html/rfc3174), [`"sha224"`, `"sha256"`, `"sha384"`, `"sha512"`](https://tools.ietf.org/html/rfc6234) but can naturally be extended.


### Hash function Options
Name  | Type             | Default             | Description 
----  | ---------------- | ------------------- | -----------
algorithm | String | (no default) | The standard hashing algorithm (function) to use. 




## Filtering
Filtering governs what files and subdirectories to include. This is done by matching of file paths as well as handling of symbolic links and empty directories.


### Filtering Options
Name  | Type             | Default             | Description 
----  | ---------------- | ------------------- | -----------
match_patterns | Array of Strings | `["*"]` (match all) | [Glob/Wildcard matching](https://en.wikipedia.org/wiki/Glob_(programming)). The path *relative to the Dirhash root* is matched against the provided patterns. The path must match at least one of the "match patterns" (*not* starting with `!`) and none of the "ignore patterns" (starting with `!`).
linked_dirs | Boolean | `true` | Include (i.e. follow) symbolic links to directories.
linked_files | Boolean | `true` | Include symbolic links to files.
empty_dirs | Boolean | `false` | Include empty directories. A directory is considered empty if it contains no files or directories to include *given the Filtering Options*.




## Protocol
The `DIRHASH` of a directory is obtained by taking the underlying hash function's hexdigest of a `DIR-DESCRIPTOR` string. The `DIR-DESCRIPTOR` is composed by concatenation of an ordered sequence of `ENTRY-DESCRIPTOR`:s, separated by two [null characters](https://en.wikipedia.org/wiki/Null_character):

```<entry-descriptor>\000\000[...]<entry-descriptor>```,

in python:

```python
# entry_descriptors: List[str]
dir_descriptor = '\000\000'.join(sorted(entry_descriptors))
```

A *directory entry* is either a subdirectory, a file or a symbolic link. Other file types (named pipe, socket, device file, door) are excluded in the core version of the Dirhash Standard. No distinction is made between files and "hard links" to files.

The `ENTRY-DESCRIPTOR` is composed by concatenation of an ordered sequence of entry properties separated by a single [null character](https://en.wikipedia.org/wiki/Null_character). Each property is represented by its name and value separated by a colon `:`:

```<name>:<value>\000[...]<name>:<value>```,

in python:

```python
# entry_properties: Dict[str, str]
entry_property_strings = [f'{k}:{v}' for k, v in entry_properties.items()]
entry_descriptor = '\000'.join(sorted(entry_property_strings))
```
The null character is (the only character) not allowed in property names or values according to the DIRHASH standard, to maintain [collision resistance](https://en.wikipedia.org/wiki/Collision_resistance).


### Entry Properties
An entry property refers to data or metadata of a directory entry.

Name  | Value | Inclusion | Comment/Rationale
----- | ----- | --------- | -----------------
dirhash | The `DIRHASH` of a subdirectory or the target directory in case of a symbolic link, except for [cyclic links](#cyclic-links). | Always included for directories. *Not applicable to files*. | This is the recursive part of the Dirhash Protocol; the content of each subdirectory is summarized by its `DIRHASH`.
data | Hash function hexdigest of the binary data of the file, or the file linked to, if a symlink. | Optional, but one of `name` and `data` must always be included. *Not applicable to directories*. | For the typical use case, the data should affect the hash. Without it, only the paths to files and subdirectories are hashed. 
name | The name of the entry (the name of the link itself if a symlink, *not* the entry linked to). | Optional, but one of `name` and `data` must always be included. | For the typical use case, the entry name should affect the hash, so that data and other metadata is tied to the name and, subsequently, to the entry's relative path to the Dirhash root (which follows from the recursive nature of the Dirhash Standard).
is_link | Whether the entry is a symlink, one of `"true"` or `"false"`. | Optional. | For the typical use case, it does *not* matter if a file or directory is linked or not - the file tree is "perceived the same" for many applications. If it matters, this property can be included. 


### Cyclic Links
Symbolically linked directories can create cycles in the, otherwise acyclic, graph representing the file tree. If not handled properly, this leads to infinite recursion when traversing the file tree (this is e.g. the case for Python's built-in [`os.walk(directory, followlinks=True)`](https://stackoverflow.com/questions/36977259/avoiding-infinite-recursion-with-os-walk/36977580)). Moreover, this breaks the recursive definition of the Dirhash Protocol, which offers two alternative solutions for the special case, specified by the option `allow_cyclic_links`.

#### `allow_cyclic_links: false`
The the first option is to consider cyclic links an [error condition](#error-conditions) and raise an appropriate exception when detected (preferably before reaching the recursion limit of the language of implementation!).

#### `allow_cyclic_links: true`
The other option is to replace the dirhash value for the cyclic link with the hash function hexdigest of the relative path from the link to the target. The path is normalized according to the unix standard (with a forward slash `/` separating directories) and without a leading or trailing slash. 

Sometimes multiple links form cycles together. Without loss of generality, cyclic links are defined as the *first occurrence of a link to a directory that has already been visited on the current branch of recursion*. The real path (or inode and device ID) of visited directories, together with the path relative to the Dirhash root, must typically be cached during traversal of the file tree to identify and resolve cyclic links. For further details, see these [examples](#cyclic-links-examples).


### Protocol Options
Name  | Type             | Default             | Description 
----  | ---------------- | ------------------- | -----------
entry_properties | Array of Strings | `["name", "data"]` | Which Directory Entry properties to consider. NOTE that `type` is a mandatory property and should not be provided
allow_cyclic_links | Boolean | `false` | Whether or not to allow the presence of [cyclic links](#cyclic-links).

The Dirhash Protocol is designed so that the same hash should not be obtained with different Protocol Options. Subsequently, when the same hash is obtained one can be sure that the same Protocol Options were used. The options must still be provided when comparing checksums, but this removes the risk of false positives (confirmation of the checksum) due to wrong options used.



## Error Conditions
**Directory Not Accessible**: A not accessible (sub)directory results in an error unless excluded by the `match_patterns` filtering option.

**File Not Accessible**: A not accessible file results in an error if the entry property `data` is used unless excluded by the `match_patterns` filtering option.

**Cyclic Symbolic Links**: Presence of cyclic links, with `allow_cyclic_links` set to `false`.

**Directory Empty**: No (non-empty) directory entries to hash in the Dirhash root directory, given provided Filtering Options and `empty_dirs` set to `false`.  



## The `DIRSUM` Object
Checksums based on the `DIRSHASH` must contain the additional configuration options to be properly validated (as was discussed in the [Introduction](#introduction)). For this purpose, the Dirhash Standard provides the `DIRSUM` object which contains the DIRHASH value as well as the necessary information for verification. It's structure is laid out in JSON below, with properties according [Hash Function Options](#hash-function-options), [Filtering Options](#filtering-options) and [Protocol Options](#protocol-options) and version (as stated in the top of this document) for which version of this standard the DIRHASH computation complies with.
```json
{
   "dirhash": "...",
   "algorithm": "...",
   "filtering": {
      "match_patterns": ["*"],
      "linked_dirs": true,
      "linked_files": true,
      "empty_dirs": false},
   "protocol": {
      "entry_properties": ["name", "data"],
      "allow_cyclic_links": false},
   "version": "0.1.0"
}
```
When saved to file, the recommended extension is `.dirsum.json`.


## Extending the Dirhash Standard
The Dirhash Standard can be extended by introducing additional Filtering Options and/or entry properties. A few possible examples below:
- **Permission Properties**: These are hard to get platform independent (different on windows/unix). The best option is probably to let go of platform independence here. Possible properties could be `permission-[owner|group|user]` or `permission-me` for permissions of current 
process, 
- **Owning User/Group**
- **Last Modified/Opened Properties**


## Contribute
If you find a bug, inconsistency or weakness in the Dirhash Standard, or that the documentation or the Standard itself can be simplified without loss of generality, please file an issue at [https://github.com/andhus/dirhash](https://github.com/andhus/dirhash). 


If you have a use case that is not covered, it can hopefully be supported by an extension of the Standard. Please file an issue or make a PR if you think that it can benefit others.

## Appendix

### Cyclic Links: Examples

In the example below there are cycles on all branches `A/B`, `A/C` and `D`.
```
root/
|__A/
|  |__B/
|  |  |__toA@ -> ..
|  |__C/
|     |__toA@ -> ..
|__D/
   |__toB@ -> ../A/B
```
In this case, the value of the dirhash property for the symlinks `A/B/toA`, `A/C/toA` and `D/toB/toA/B/toA` is replaced by the hash of `".."`. Note that for the third branch, the presence of cyclic links can be *detected* already at `D/toB/toA/B` (since `B` is already visited) but it is for `D/toB/toA/B/toA` that the replacement happens. This reflects the fact that it is the `toA` that's *causing* the cycle, not `D/toB` or `D/toB/toA/B` (which is not even a link), and at `D/toB/toA/` the cycle is not yet be detected.

Below is another example where multiple links are involved in forming cycles as well as links which absolute path is external to the Dirhash root. In this case the cyclic links and relative paths to hash are: `root/A/toB/toA` (`"../A"`), `root/B/toA/toB` (`"../B"`) and `root/C/toD/toC` (`"../.."`).

```
/path/to/root/
         |__A/
         |  |__toB@ -> ../B
         |__B/
         |  |__toA@ -> /path/to/root/A
         |__C/
            |__toD@ -> /path/to/D
         
/path/to/D/
         |__toC@ -> /path/to/root/C
```
