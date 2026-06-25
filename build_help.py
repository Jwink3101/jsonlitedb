#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import shutil
import subprocess
import sys
from pathlib import Path

md = ["<!--- Auto Generated -->", "<!--- DO NOT MODIFY. WILL NOT BE SAVED -->"]

os.chdir(os.path.dirname(__file__))

DEMO_DIR = Path("Demo")
README_DEMO = DEMO_DIR / "Basic Usage.md"


def run_md_demo(file):
    subprocess.run(["md-demo", str(file)], check=True)


def read_readme_demo(file):
    return file.read_text().strip()


for demo_file in sorted(DEMO_DIR.glob("*.md")):
    run_md_demo(demo_file)

body = read_readme_demo(README_DEMO)
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
