from setuptools import setup, find_packages

VERSION = '0.1.0'

setup(
    name='dirhash',
    version=VERSION,
    description='',
    entry_points={
        'console_scripts': ['dirhash=dirhash.cli:main'],
    },
    url='https://github.com/andhus/dirhash',
    license='MIT',
    install_requires=[
        'pathspec>=0.5.9',
        'scandir>=1.9.0;python_version<"3.5"'
    ],
    packages=['dirhash'],
    tests_require=['pytest', 'pytest-cov']
)
