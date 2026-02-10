#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import shutil
import subprocess
import sys

import nbformat
from jupyter_client.kernelspec import NoSuchKernel
from nbconvert import MarkdownExporter
from nbconvert.preprocessors import ExecutePreprocessor

import jsonlitedb

md = ["<!--- Auto Generated -->", "<!--- DO NOT MODIFY. WILL NOT BE SAVED -->"]

os.chdir(os.path.dirname(__file__))


def notebook_kernel_name(nb):
    kernelspec = nb.metadata.get("kernelspec", {})
    if kernelspec.get("name"):
        return kernelspec["name"]
    return "python"


def run_replace_convert(file):
    # Load the Jupyter notebook
    with open(file, "r") as fp:
        nb = nbformat.read(fp, as_version=4)

    # Execute
    kernel_name = notebook_kernel_name(nb)
    executer = ExecutePreprocessor(timeout=600, kernel_name=kernel_name)
    try:
        executer.preprocess(nb, {"metadata": {"path": "./"}})
    except NoSuchKernel:
        executer = ExecutePreprocessor(timeout=600, kernel_name="python")
        executer.preprocess(nb, {"metadata": {"path": "./"}})

    # clean
    nb.metadata.get("language_info", {}).pop("version", None)
    for cell in nb.cells:
        nb.metadata.pop("signature", None)
        #         if 'execution_count' in cell:
        #            cell['execution_count'] = None
        #
        #         if 'outputs' in cell and 'execution_count' in cell['outputs']:
        #             cell['outputs']['execution_count'] = None

        # if 'prompt_number' in cell:
        #    cell['prompt_number'] = None

        if "metadata" in cell:
            cell["metadata"].pop("execution", None)

    # Save the executed notebook in place
    with open(file + ".swp", "w") as fp:
        nbformat.write(nb, fp)
    shutil.move(file + ".swp", file)

    # Create a Markdown exporter
    exporter = MarkdownExporter()

    # Convert the notebook to Markdown
    body, resources = exporter.from_notebook_node(nb)

    # This is a hack since I can't seem to get the exporter to properly use
    # a custom template. I will fix this eventually
    out = []
    body = iter(body.splitlines())
    for line in body:
        out.append(line)
        if line.startswith("```python"):
            for line in body:
                if line.startswith("```"):
                    out.append(line)
                    break
                else:
                    out.append(">>> " + line)
    body = "\n".join(out)

    return body


cmd = ["git", "ls-files", "*.ipynb"]
ipynb_files = subprocess.check_output(cmd).decode().strip().split("\n")
ipynbs = {ipynb_file: run_replace_convert(ipynb_file) for ipynb_file in ipynb_files}

body = ipynbs["Demo/Basic Usage.ipynb"]
md.append(body)

with open("readme.md", "r") as rmin, open(".readme.md.swp", "wt") as rmout:
    for line in rmin:
        rmout.write(line)

        if not line.startswith("<!--- BEGIN AUTO GENERATED -->"):
            continue

        rmout.write("\n".join(md))

        for line in rmin:  # keep reading until we get our line. This is older stuff
            if not line.startswith("<!--- END AUTO GENERATED -->"):
                continue
            rmout.write("\n<!--- END AUTO GENERATED -->\n")
            break
        else:
            raise ValueError("Did not find end sentinel")
shutil.move(".readme.md.swp", "readme.md")

### Documentation for the objects
if False:
    api = []
    api += ["# API Documentation"]
    api += ["Auto-generated documentation"]

    api += ["## JSONLiteDB"]
    doc = subprocess.check_output(
        [sys.executable, "-m", "pydoc", "jsonlitedb.JSONLiteDB"]
    ).decode()
    api.append("```text\n" + doc + "```")

    api += ["## Query"]
    doc = subprocess.check_output(
        [sys.executable, "-m", "pydoc", "jsonlitedb.Query"]
    ).decode()
    api.append("```text\n" + doc + "```")

    with open(".api.md.swp", "wt") as fp:
        fp.write("\n\n".join(api))
    shutil.move(".api.md.swp", "api.md")
