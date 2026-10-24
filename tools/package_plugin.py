import os
import shutil
import sys
import zipfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "plugin", "AIAssistant")
DIST_DIR = os.path.join(ROOT, "dist")
ARCHIVE_NAME = "AIAssistant.zip"


def should_skip(path):
    relative = os.path.relpath(path, PLUGIN_DIR)
    parts = relative.split(os.sep)
    return (
        "__pycache__" in parts
        or relative.endswith(".pyc")
        or relative.endswith(".pyo")
        or os.path.basename(path).startswith(".")
    )


def build_archive():
    if not os.path.isfile(os.path.join(PLUGIN_DIR, "plugin.json")):
        raise RuntimeError("plugin.json was not found")

    os.makedirs(DIST_DIR, exist_ok=True)
    archive_path = os.path.join(DIST_DIR, ARCHIVE_NAME)
    if os.path.exists(archive_path):
        os.remove(archive_path)

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for directory, subdirectories, filenames in os.walk(PLUGIN_DIR):
            subdirectories[:] = [
                name for name in subdirectories
                if name != "__pycache__" and not name.startswith(".")
            ]
            for filename in filenames:
                source = os.path.join(directory, filename)
                if should_skip(source):
                    continue
                relative = os.path.relpath(source, PLUGIN_DIR)
                archive.write(source, os.path.join("AIAssistant", relative))

    return archive_path


if __name__ == "__main__":
    path = build_archive()
    print(path)
