"""Reading the API key from a .env file next to the project.

Exporting a variable into the shell works until the shell closes, and then the
site quietly loses half its features with no obvious cause. A file keeps it.
"""
import os


def load(path=None):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = path or os.path.join(here, ".env")
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        # os.environ wins, so an explicit export still overrides the file
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
