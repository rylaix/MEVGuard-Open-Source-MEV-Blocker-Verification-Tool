# c_extension/setup.py

from setuptools import setup, Extension

setup(
    name='c_extension',
    version='1.0',
    ext_modules=[
        Extension(
            'c_extension',
            sources=['c_extension.c']
        )
    ]
)
