#! /usr/bin/env python

import os
import pathlib
import shutil
import tempfile

from absl import app
from absl import flags

FLAG_PORT = flags.DEFINE_string("port", "/dev/tty.usbserial-0001", "The /dev port to use")
FLAG_MAKE_CLEAN = flags.DEFINE_boolean("make-clean", True, "Whether to run 'make clean' on Micropython. Useful if src or lib code was changed.")
FLAG_BUILD_MICROPYTHON = flags.DEFINE_boolean("build-micropython", True, "Whether to build micropython or just reflash the existing version.")

_ESP_IDF_FOLDER = "../esp-idf"
PROJECT_ROOT_FOLDER = pathlib.Path(__file__).parents[1]

BUILD_FOLDER = pathlib.Path("build")
BUILD_FOLDER.mkdir(exist_ok=True, parents=True)
MPY_DIR = BUILD_FOLDER / "micropython"

def main(argv):
    print(f"Installing SweetYaar2.0 on {FLAG_PORT.value}")

    setup_micropython()
    if FLAG_BUILD_MICROPYTHON.value:
        build_custom_micropython(FLAG_PORT.value)
    flash_custom_micropython(FLAG_PORT.value)
    copy_other_code(FLAG_PORT.value)

    print("Done")


def _run_command(cmd):
    rc = os.system(cmd)
    if rc != 0:
        raise RuntimeError(f"Command failed: {cmd}")


def setup_micropython():
    if shutil.which("idf.py") is None:
        raise RuntimeError(f"Can't find idf.py. Try to run the following in the shell window before running this script:\nsource {_ESP_IDF_FOLDER}/export.sh")
    
    if not MPY_DIR.exists():
        _run_command(f"git clone https://github.com/wemos/micropython.git {MPY_DIR}")

    _run_command(f"cd {MPY_DIR}; make -C mpy-cross")  # will not recompile if exists.
    _run_command(f"cd {MPY_DIR}/ports/esp32; make submodules")
    
    # Set links to custom modules (lib and src from SweetYaar)
    _run_command(f"ln -sf $(pwd)/src {MPY_DIR}/ports/esp32/modules/.")
    _run_command(f"ln -sf $(pwd)/lib/* {MPY_DIR}/ports/esp32/modules/.")


def build_custom_micropython(port):
    # Build the image
    if FLAG_MAKE_CLEAN.value:
        _run_command(f"cd {MPY_DIR}/ports/esp32; make clean")
    _run_command(f"cd {MPY_DIR}/ports/esp32; make")


def flash_custom_micropython(port):
    # Flash it
    build_generic = f"{MPY_DIR}/ports/esp32/build-GENERIC"
    _run_command(f"esptool.py -p {port} -b 460800 --before default_reset --after hard_reset "
                 "--chip esp32  write_flash --flash_mode dio --flash_size detect --flash_freq 40m "
                 f"0x1000 {build_generic}/bootloader/bootloader.bin "
                 f"0x8000 {build_generic}/partition_table/partition-table.bin "
                 f"0x10000 {build_generic}/micropython.bin")


def copy_other_code(port):
    with tempfile.TemporaryDirectory() as tempdir:
        tempdir = pathlib.Path(tempdir)
        etcdir = tempdir / "etc"

        # Creating a local dir with all src files
        os.system(f"cp {PROJECT_ROOT_FOLDER}/*.py {tempdir}")
        os.system(f"mkdir {etcdir} && cp {PROJECT_ROOT_FOLDER}/etc/* {etcdir}")
        
        # Copy to board
        _run_command(f"rshell -p {port} 'rm -rf /pyboard/*; rsync {tempdir} /pyboard; ls -l /pyboard'")


if __name__ == "__main__":
    app.run(main)