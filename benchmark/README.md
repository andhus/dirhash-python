# Benchmark

As a reference, the performance of `dirhash` is benchmarked against the shell command:

`find path/to/folder -type f -print0 | sort -z | xargs -0 md5 | md5` 

(top answer for the SO-question: 
[Linux: compute a single hash for a given folder & contents?](https://stackoverflow.com/questions/545387/linux-compute-a-single-hash-for-a-given-folder-contents))

Each test case contains 1 GiB of random data, split equally into 8, 1k or 32k files,
in a flat or nested (binary tree of depth 8) structure.

For a fair comparison, *the CLI version* of `dirhash` was used (including startup 
time for loading of python modules etc.).

For full details/reproducibility see/run the `run.py` script for which the output is 
found in `results.csv`. These results were generated on a MacBook Pro (2018): 
- 2,2 GHz Intel Core i7 (`sysctl -n hw.physicalcpu hw.logicalcpu`-> 6, 12)
- 16 GB 2400 MHz DDR4
- APPLE SSD AP0512M



## Sample results:

Implementation      | Test Case       | Time (s) | Speed up
------------------- | --------------- | -------: | -------:
shell reference     | flat_1k_1MB     | 2.29     | -> 1.0
`dirhash`           | flat_1k_1MB     | 1.67     | 1.36
`dirhash`(8 workers)| flat_1k_1MB     | 0.48     | **4.73**
shell reference     | nested_32k_32kB | 6.82     | -> 1.0
`dirhash`           | nested_32k_32kB | 3.43     | 2.00
`dirhash`(8 workers)| nested_32k_32kB | 1.14     | **6.00**
