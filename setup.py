import io
import os
from setuptools import setup

VERSION = '0.1.1'

DESCRIPTION = 'Python module and CLI for hashing of file system directories.'

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
try:
    with io.open(os.path.join(PROJECT_ROOT, 'README.md'), encoding='utf-8') as f:
        long_description = '\n' + f.read()
except IOError:
    long_description = DESCRIPTION

setup(
    name='dirhash',
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/andhus/dirhash',
    author="Anders Huss",
    author_email="andhus@kth.se",
    license='MIT',
    install_requires=[
        'pathspec>=0.5.9',
        'scandir>=1.9.0;python_version<"3.5"'
    ],
    packages=['dirhash'],
    include_package_data=True,
    entry_points={
        'console_scripts': ['dirhash=dirhash.cli:main'],
    },
    tests_require=['pytest', 'pytest-cov']
)
