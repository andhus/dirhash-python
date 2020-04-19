# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
NIL

## [0.2.0] - 2019-04-18
Complies with [Dirhash Standard](https://github.com/andhus/dirhash) Version [0.1.0](https://github.com/andhus/dirhash/releases/0.1.0)

### Added
- A first implementation based on the formalized [Dirhash Standard](https://github.com/andhus/dirhash).
- This changelog.
- Results form a new benchmark run after changes. The `benchmark/run.py` now outputs results files which names include the `dirhash.__version__`.

### Changed
- **Significant breaking changes** from version 0.1.1 - both regarding API and the 
underlying method/protocol for computing the hash. This means that **hashes 
computed with this version will differ from hashes computed with version < 0.2.0 for 
same directory**.
- The dirhash python implementation has moved to here 
[github.com/andhus/dirhash](https://github.com/andhus/dirhash) from the previous re