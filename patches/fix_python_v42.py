#!/usr/bin/env python3
"""build-42 source patch: keep + export the CPython API symbols that numpy's
iOS extension libraries need, in the statically-linked Blender executable.

Context: Blender-iOS links CPython statically into the Blender binary, which
exports the Py* API (896 symbols in build-37's executable). The build-42
packaging step rewrites numpy's iOS extension .so files to bind Python
symbols via dyld FLAT-NAMESPACE lookup, which resolves them from the Blender
executable's export trie. Binary audit of the actual wheel vs the actual
shipped executable found exactly 15 API symbols the extensions import that
Blender itself never references -- so the linker dead-strips them from
libpython and flat lookup would fail with "symbol not found":

  PyExc_FloatingPointError, PyExc_FutureWarning, PyObject_GC_IsFinalized,
  PyObject_Init, PyObject_InitVar, PySequence_InPlaceRepeat,
  PySequence_Repeat, PyTraceMalloc_Track, PyTraceMalloc_Untrack,
  PyUnicode_Tailmatch, Py_EnterRecursiveCall, Py_IsInitialized,
  Py_LeaveRecursiveCall, Py_Version, _PyArg_VaParseTupleAndKeywords_SizeT

Fix: mark each with the linker's -u (force-undefined) flag on the blender
executable target, which forces the defining libpython objects to be kept;
Apple's ld exports all retained globals from executables by default, so they
land in the export trie where flat lookup finds them. Harmless on any other
platform this fork might build.

Applies to source/creator/CMakeLists.txt (append; the `blender` target is
defined earlier in the same file). Asserts the target exists in the file.
"""
import sys

C = "blender/source/creator/CMakeLists.txt"

SYMS = [
    "_PyExc_FloatingPointError",
    "_PyExc_FutureWarning",
    "_PyObject_GC_IsFinalized",
    "_PyObject_Init",
    "_PyObject_InitVar",
    "_PySequence_InPlaceRepeat",
    "_PySequence_Repeat",
    "_PyTraceMalloc_Track",
    "_PyTraceMalloc_Untrack",
    "_PyUnicode_Tailmatch",
    "_Py_EnterRecursiveCall",
    "_Py_IsInitialized",
    "_Py_LeaveRecursiveCall",
    "_Py_Version",
    "__PyArg_VaParseTupleAndKeywords_SizeT",
]

with open(C) as f:
    src = f.read()

if "add_executable(blender " not in src.replace("${EXETYPE}", "").replace("  ", " ") \
        and "add_executable(blender" not in src:
    sys.stderr.write("FATAL b42: blender executable target not found in creator CMakeLists\n")
    sys.exit(1)
if "b42-numpy-flat-symbols" in src:
    sys.stderr.write("FATAL b42: already applied\n")
    sys.exit(1)

flags = "\n".join(f'    "-Wl,-u,{s}"' for s in SYMS)
src += f"""

# b42-numpy-flat-symbols: numpy's iOS extension libraries bind these CPython
# API symbols via dyld flat-namespace lookup against this executable's
# statically-linked interpreter; Blender never references them itself, so
# without -u the linker dead-strips them and numpy fails to import with
# "symbol not found". (See patches/numpy_flat_namespace.py for the matching
# packaging-side rewrite.)
if(TARGET blender AND APPLE)
  target_link_options(blender PRIVATE
{flags}
  )
endif()
"""

with open(C, "w") as f:
    f.write(src)
print(f"{C}: appended b42-numpy-flat-symbols ({len(SYMS)} forced symbols)")
print("BUILD-42 (export CPython API for numpy flat-namespace binding) APPLIED OK")
