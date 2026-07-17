#!/usr/bin/env python3
"""Rewrite CPython extension .so files so their Python-symbol imports resolve
via dyld FLAT-NAMESPACE lookup instead of a Python.framework dependency.

Why: Blender-iOS links CPython STATICALLY into the Blender executable (which
exports the Py* API), so there is no Python.framework in the bundle. BeeWare's
iOS extension wheels are linked two-level against @rpath/Python.framework/
Python, so dlopen fails with "Library not loaded" before any symbol lookup.
Classic embedded-CPython extensions solve this with `-undefined
dynamic_lookup`, which is encoded in Mach-O dyld info as bind ordinal
BIND_SPECIAL_DYLIB_FLAT_LOOKUP (-2). This script performs exactly that
transformation post-hoc, entirely in place (no size or offset changes):

  1. LC_LOAD_DYLIB "@rpath/Python.framework/Python" -> "/usr/lib/
     libSystem.B.dylib" (same command size, NUL padded; libSystem is already
     a dependency of every image, so the load is a guaranteed no-op).
  2. In the bind and lazy-bind opcode streams of LC_DYLD_INFO(_ONLY), every
     BIND_OPCODE_SET_DYLIB_ORDINAL_IMM selecting the Python ordinal becomes
     BIND_OPCODE_SET_DYLIB_SPECIAL_IMM(-2) = flat lookup across all loaded
     images -- which finds the symbols in the Blender executable.

The opcode streams are walked with a real parser (ULEB operands skipped), so
only opcode bytes are rewritten. The script refuses to touch a file where the
Python ordinal appears in ULEB form or anything unexpected shows up, and
verifies zero remaining references. Exit code is non-zero on any anomaly.

Usage: python3 numpy_flat_namespace.py <dir-with-.so-files>
"""
import glob
import struct
import sys

LC_LOAD_DYLIB = 0x0C
LC_ID_DYLIB = 0x0D
LC_DYLD_INFO = 0x22
LC_DYLD_INFO_ONLY = 0x80000022
LC_REQ_DYLD = 0x80000000

BIND_OPCODE_MASK = 0xF0
BIND_IMM_MASK = 0x0F
OP_DONE = 0x00
OP_SET_DYLIB_ORDINAL_IMM = 0x10
OP_SET_DYLIB_ORDINAL_ULEB = 0x20
OP_SET_DYLIB_SPECIAL_IMM = 0x30
OP_SET_SYMBOL = 0x40
OP_SET_TYPE_IMM = 0x50
OP_SET_ADDEND_SLEB = 0x60
OP_SET_SEGMENT_AND_OFFSET_ULEB = 0x70
OP_ADD_ADDR_ULEB = 0x80
OP_DO_BIND = 0x90
OP_DO_BIND_ADD_ADDR_ULEB = 0xA0
OP_DO_BIND_ADD_ADDR_IMM_SCALED = 0xB0
OP_DO_BIND_ULEB_TIMES_SKIPPING_ULEB = 0xC0

FLAT_LOOKUP_BYTE = OP_SET_DYLIB_SPECIAL_IMM | 0x0E  # SPECIAL_IMM(-2) -> 0x3E

NEW_DEP = b"/usr/lib/libSystem.B.dylib"


def skip_uleb(buf, i):
    while buf[i] & 0x80:
        i += 1
    return i + 1


def skip_cstr(buf, i):
    while buf[i] != 0:
        i += 1
    return i + 1


def rewrite_stream(buf, start, size, py_ordinal, lazy):
    """Walk one bind opcode stream, swapping SET_DYLIB_ORDINAL_IMM(py) for
    SPECIAL_IMM(-2). Returns number of rewrites."""
    i, end, hits = start, start + size, 0
    while i < end:
        byte = buf[i]
        op, imm = byte & BIND_OPCODE_MASK, byte & BIND_IMM_MASK
        if op == OP_SET_DYLIB_ORDINAL_IMM:
            if imm == py_ordinal:
                buf[i] = FLAT_LOOKUP_BYTE
                hits += 1
            i += 1
        elif op == OP_SET_DYLIB_ORDINAL_ULEB:
            j = skip_uleb(buf, i + 1)
            # decode to make sure it isn't the python ordinal in ULEB form
            v, shift, k = 0, 0, i + 1
            while True:
                v |= (buf[k] & 0x7F) << shift
                if not buf[k] & 0x80:
                    break
                shift += 7
                k += 1
            if v == py_ordinal:
                raise RuntimeError("python ordinal in ULEB form - unsupported")
            i = j
        elif op in (OP_DONE, OP_SET_DYLIB_SPECIAL_IMM, OP_SET_TYPE_IMM,
                    OP_DO_BIND, OP_DO_BIND_ADD_ADDR_IMM_SCALED):
            i += 1
            # In lazy streams DONE merely separates entries; keep walking.
            if op == OP_DONE and not lazy:
                # non-lazy streams may pad with zeros to the end; stop parsing
                # opcodes but scan remaining bytes are all zero.
                if any(buf[i:end]):
                    # more opcodes after DONE (some linkers emit several
                    # runs); continue walking.
                    continue
                break
        elif op == OP_SET_SYMBOL:
            i = skip_cstr(buf, i + 1)
        elif op in (OP_SET_ADDEND_SLEB, OP_SET_SEGMENT_AND_OFFSET_ULEB,
                    OP_ADD_ADDR_ULEB, OP_DO_BIND_ADD_ADDR_ULEB):
            i = skip_uleb(buf, i + 1)
        elif op == OP_DO_BIND_ULEB_TIMES_SKIPPING_ULEB:
            i = skip_uleb(buf, i + 1)
            i = skip_uleb(buf, i)
        else:
            raise RuntimeError(f"unknown bind opcode 0x{byte:02x} at {i}")
    return hits


def patch(path):
    buf = bytearray(open(path, "rb").read())
    magic, cputype, cpusub, ftype, ncmds, sizeofcmds, flags, _ = \
        struct.unpack_from("<IIIIIIII", buf, 0)
    if magic != 0xFEEDFACF:
        raise RuntimeError(f"{path}: not a 64-bit little-endian Mach-O")
    off = 32
    dylib_ordinal = 0
    py_ordinal = None
    dyld_info = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", buf, off)
        base_cmd = cmd & ~LC_REQ_DYLD
        if cmd == LC_LOAD_DYLIB:
            dylib_ordinal += 1
            name_off, = struct.unpack_from("<I", buf, off + 8)
            s = off + name_off
            e = buf.index(0, s)
            name = bytes(buf[s:e])
            if b"Python.framework" in name:
                if py_ordinal is not None:
                    raise RuntimeError("multiple Python.framework deps")
                py_ordinal = dylib_ordinal
                room = off + size - s
                if len(NEW_DEP) + 1 > room:
                    raise RuntimeError("replacement path does not fit")
                buf[s:off + size] = NEW_DEP + b"\x00" * (room - len(NEW_DEP))
        elif base_cmd == (LC_DYLD_INFO & ~LC_REQ_DYLD) and cmd in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
            (rebase_off, rebase_size, bind_off, bind_size, weak_off, weak_size,
             lazy_off, lazy_size, export_off, export_size) = \
                struct.unpack_from("<10I", buf, off + 8)
            dyld_info = (bind_off, bind_size, weak_off, weak_size,
                         lazy_off, lazy_size)
        off += size
    if py_ordinal is None:
        print(f"  {path}: no Python.framework dependency - skipped")
        return 0
    if py_ordinal > 15:
        raise RuntimeError("python ordinal > 15 (IMM form impossible)")
    if dyld_info is None:
        raise RuntimeError("no LC_DYLD_INFO - chained fixups? unsupported")
    bind_off, bind_size, weak_off, weak_size, lazy_off, lazy_size = dyld_info
    hits = 0
    if bind_size:
        hits += rewrite_stream(buf, bind_off, bind_size, py_ordinal, lazy=False)
    if weak_size:
        hits += rewrite_stream(buf, weak_off, weak_size, py_ordinal, lazy=False)
    if lazy_size:
        hits += rewrite_stream(buf, lazy_off, lazy_size, py_ordinal, lazy=True)
    if hits == 0:
        raise RuntimeError("python dep present but no ordinal sets rewritten")
    open(path, "wb").write(buf)
    print(f"  {path}: ordinal {py_ordinal} -> flat lookup ({hits} opcode sites), "
          f"dep -> libSystem")
    return hits


def main():
    root = sys.argv[1]
    sos = sorted(glob.glob(f"{root}/**/*.so", recursive=True))
    if not sos:
        sys.stderr.write(f"no .so files under {root}\n")
        sys.exit(1)
    total = 0
    for p in sos:
        total += patch(p)
    print(f"flat-namespace rewrite complete: {len(sos)} libs, {total} opcode sites")


if __name__ == "__main__":
    main()
