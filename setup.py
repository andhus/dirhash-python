import os

import versioneer
from setuptools import find_packages, setup

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

DESCRIPTION = "Python module and CLI for hashing of file system directories."

try:
    with open(os.path.join(PROJECT_ROOT, "README.md"), encoding="utf-8") as f:
        long_description = "\n" + f.read()
except OSError:
    long_description = DESCRIPTION

setup(
    name="dirhash",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/andhus/dirhash-python",
    author="Anders Huss",
    author_email="andhus@kth.se",
    license="MIT",
    python_requires=">=3.8",
    install_requires=["scantree"],
    packages=find_packages("src"),
    package_dir={"": "src"},
    include_package_data=True,
    entry_points={
        "console_scripts": ["dirhash=dirhash.cli:main"],
    },
    tests_require=["pre-commit", "pytest", "pytest-cov"],
)
