"""
package_submission.py — собирает итоговый ZIP для сдачи на платформу хакатона.

Структура архива:
  aurora.zip
  ├── plugin/          ← исходный код плагина + README (без __pycache__, .pyc, .env)
  └── results/
      └── <model_name>/
          ├── project.3mf    ← проект STE Slicer (добавьте вручную)
          ├── result.gcode   ← G-code (добавьте вручную)
          └── chat_*.png     ← скриншоты переписки (добавьте вручную)

Использование:
  python tools/package_submission.py
  python tools/package_submission.py --team aurora --model Dragon_2.5
"""

import argparse
import os
import sys
import zipfile

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_DIR = os.path.join(ROOT, "plugin", "AIAssistant")
RESULTS_DIR = os.path.join(ROOT, "results")
DIST_DIR   = os.path.join(ROOT, "dist")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_skip_plugin(path):
    """Skip cache, compiled, secrets and hidden files from the plugin folder."""
    relative = os.path.relpath(path, PLUGIN_DIR)
    parts    = relative.split(os.sep)
    basename = os.path.basename(path)
    if basename == ".env":          # never include secrets
        return True
    if basename.startswith("."):
        return True
    return (
        "__pycache__" in parts
        or relative.endswith(".pyc")
        or relative.endswith(".pyo")
    )


def _collect_plugin_files():
    """Yield (abs_path, archive_path) pairs for the plugin source."""
    for dirpath, subdirs, filenames in os.walk(PLUGIN_DIR):
        subdirs[:] = [d for d in subdirs
                      if d != "__pycache__" and not d.startswith(".")]
        for filename in filenames:
            src = os.path.join(dirpath, filename)
            if _should_skip_plugin(src):
                continue
            rel = os.path.relpath(src, ROOT)           # plugin/AIAssistant/…
            yield src, rel

    # README at repo root
    readme = os.path.join(ROOT, "README.md")
    if os.path.isfile(readme):
        yield readme, "README.md"


def _collect_results_files():
    """Yield (abs_path, archive_path) pairs for everything in results/."""
    if not os.path.isdir(RESULTS_DIR):
        return
    for dirpath, subdirs, filenames in os.walk(RESULTS_DIR):
        subdirs[:] = [d for d in subdirs if not d.startswith(".")]
        for filename in filenames:
            if filename == ".gitkeep":
                continue
            src = os.path.join(dirpath, filename)
            rel = os.path.relpath(src, ROOT)           # results/<model>/…
            yield src, rel


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_submission(team_name="aurora"):
    os.makedirs(DIST_DIR, exist_ok=True)
    archive_path = os.path.join(DIST_DIR, "{}.zip".format(team_name))

    if os.path.exists(archive_path):
        os.remove(archive_path)

    plugin_files  = list(_collect_plugin_files())
    results_files = list(_collect_results_files())

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in plugin_files:
            zf.write(src, arc)
        for src, arc in results_files:
            zf.write(src, arc)

    # Summary
    print("Архив создан: {}".format(archive_path))
    print("")
    print("  Файлов плагина : {}".format(len(plugin_files)))
    print("  Файлов results : {}".format(len(results_files)))
    print("")

    if results_files:
        print("Включены результаты:")
        for _, arc in results_files:
            print("  {}".format(arc))
    else:
        print("ВНИМАНИЕ: папка results/ пуста.")
        print("Добавьте в results/<название_модели>/ файлы:")
        print("  project.3mf   — проект STE Slicer")
        print("  result.gcode  — G-code")
        print("  chat_01.png   — скриншоты переписки с ботом")
        print("Затем запустите скрипт снова.")

    return archive_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Упаковать плагин + результаты для сдачи на хакатон."
    )
    parser.add_argument(
        "--team", default="aurora",
        help="Название команды (имя ZIP-архива, по умолчанию: aurora)"
    )
    args = parser.parse_args()
    build_submission(team_name=args.team)
