from setuptools import setup, find_packages
import re
from pathlib import Path

# Read the contents of your README file
this_directory = Path(__file__).parent
long_description = (this_directory / "readme.md").read_text()


# Extract the version from the module file
def get_version():
    version_file = this_directory / "jsonlitedb.py"
    with open(version_file, "r") as f:
        for line in f:
            match = re.match(r"^__version__ = ['\"]([^'\"]*)['\"]", line)
            if match:
                return match.group(1)
    raise RuntimeError("Version not found in jsonlitedb.py")


setup(
    name="jsonlitedb",
    version=get_version(),
    author="Justin Winokur",
    author_email="Jwink3101@users.noreply.github.com",
    description="SQLite3-backed JSON document database with support for indices and advanced queries",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Jwink3101/jsonlitedb",
    packages=find_packages(),
    py_modules=["jsonlitedb"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",  # Specify the Python version compatibility
    install_requires=[],
)
