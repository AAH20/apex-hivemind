from setuptools import setup, find_packages

setup(
    name="apex-hivemind",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "hivemind = apex_hivemind.cli:main",
        ],
    },
)
