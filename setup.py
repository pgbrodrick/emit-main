"""
This is the setup file for managing the emit_main package

Author: Winston Olson-Duvall, winston.olson-duvall@jpl.nasa.gov
"""

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="emit_main",
    version="0.1.0",
    author="Winston Olson-Duvall",
    author_email="winston.olson-duvall@jpl.nasa.gov",
    description="Workflow and file management code for EMIT data processing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.jpl.nasa.gov/emit-sds/emit-main",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3",
    install_requires=[
        "gdal==2.3.3",
        "luigi==2.8.10",
        "pymongo==3.9.0",
        "mongodb==4.0.3",
        "spectral==0.21"
    ]
)