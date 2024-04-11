import io
import os
from setuptools import setup, find_packages

import versioneer

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

DESCRIPTION = 'Python module and CLI for hashing of file system directories.'

try:
    with io.open(os.path.join(PROJECT_ROOT, 'README.md'), encoding='utf-8') as f:
        long_description = '\n' + f.read()
except IOError:
    long_description = DESCRIPTION

setup(
    name='dirhash',
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/andhus/dirhash-python',
    author="Anders Huss",
    author_email="andhus@kth.se",
    license='MIT',
    install_requires=['scantree>=0.0.2'],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    include_package_data=True,
    entry_points={
        'console_scripts': ['dirhash=dirhash.cli:main'],
    },
    tests_require=['pytest', 'pytest-cov']
)
