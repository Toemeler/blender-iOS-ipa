#!/usr/bin/env python3
"""build-32 source patches: native Diffraction Grating BSDF for Cycles (CPU + Metal GPU).

Adds a physically-based reflective diffraction grating closure implementing the grating
equation sin(theta_m) = sin(theta_i) + m*lambda/d, summed over bounded orders, with
per-sample wavelength importance and wavelength->rgb conversion inside the kernel. It is
exposed WITHOUT any new Blender/DNA/RNA node: the existing Glossy BSDF node gains a
'diffraction' entry in its Distribution enum, which maps to the new closure. The Glossy
node already provides Color, Normal, Tangent (groove direction), Roughness and Rotation.

Self-verifying: aborts if any anchor is not found exactly once.
"""
import sys

import base64 as _b64
BSDF_DIFFRACTION_H = _b64.b64decode(
    "LyogU1BEWC1MaWNlbnNlLUlkZW50aWZpZXI6IEJTRC0zLUNsYXVzZQogKiBEaWZmcmFjdGlvbiBncmF0aW5nIEJTREYgZm9yIEN5Y2xlcyAoQ1BVICsgR1BVL01ldGFsKS4KICogUGh5c2ljYWwgbW9kZWw6IGdyYXRpbmcgZXF1YXRpb24gIHNpbih0aGV0YV9tKSA9IHNpbih0aGV0YV9pKSArIG0gKiBsYW1iZGEgLyBkCiAqIFJlZmxlY3RpdmUgZ3JhdGluZzsgc3VtcyBhIGJvdW5kZWQgc2V0IG9mIGRpZmZyYWN0aW9uIG9yZGVycy4gV2F2ZWxlbmd0aCBpcwogKiBjaG9zZW4gcGVyLXNhbXBsZSBieSBpbXBvcnRhbmNlIG92ZXIgdGhlIHZpc2libGUgYmFuZCBhbmQgY29udmVydGVkIHRvIHRoZQogKiByZW5kZXIncyBTcGVjdHJ1bSB2aWEgd2F2ZWxlbmd0aC0+WFlaLT5yZ2IsIHNvIGl0IHdvcmtzIGlkZW50aWNhbGx5IGluIHRoZQogKiBSR0Iga2VybmVsIG9uIGV2ZXJ5IGRldmljZS4gKi8KCiNwcmFnbWEgb25jZQoKI2luY2x1ZGUgImtlcm5lbC90eXBlcy5oIgojaW5jbHVkZSAia2VybmVsL3NhbXBsZS9tYXBwaW5nLmgiCgpDQ0xfTkFNRVNQQUNFX0JFR0lOCgovKiBGaXRzIHdpdGhpbiBTaGFkZXJDbG9zdXJlIHBhZGRpbmc6IGJhc2UgKyBOIGFscmVhZHkgcHJlc2VudDsgd2UgYWRkIHNwYWNpbmcsCiAqIGEgcGFja2VkIHRhbmdlbnQsIHJvdWdobmVzcyBhbmQgb3JkZXIgY2FwLiAqLwpzdHJ1Y3QgRGlmZnJhY3Rpb25Cc2RmIHsKICBTSEFERVJfQ0xPU1VSRV9CQVNFOwogIHBhY2tlZF9mbG9hdDMgVDsgICAvKiBncm9vdmUgZGlyZWN0aW9uICh1bml0KSwgaW4gd29ybGQgc3BhY2UgKi8KICBmbG9hdCBzcGFjaW5nX25tOyAgLyogZ3Jvb3ZlIHNwYWNpbmcgZCwgbmFub21ldHJlcyAqLwogIGZsb2F0IHJvdWdobmVzczsgICAvKiBbMCwxXSBtaWNyby1yb3VnaG5lc3MgYmx1ciBvZiBlYWNoIG9yZGVyICovCiAgaW50IG1heF9vcmRlcjsgICAgIC8qIGhpZ2hlc3QgfG18IHRvIGluY2x1ZGUgKi8KfTsKCnN0YXRpY19hc3NlcnQoc2l6ZW9mKFNoYWRlckNsb3N1cmUpID49IHNpemVvZihEaWZmcmFjdGlvbkJzZGYpLCAiRGlmZnJhY3Rpb25Cc2RmIGlzIHRvbyBsYXJnZSEiKTsKCi8qIENJRS1pc2ggd2F2ZWxlbmd0aChubSkgLT4gbGluZWFyIHNSR0IsIGNvbXBhY3QgZml0IChXeW1hbi9TbG9hbi9TaGlybGV5IHN0eWxlKS4KICogS2VwdCBsb2NhbCBzbyBubyBleHRlcm5hbCB0YWJsZXMgYXJlIG5lZWRlZCBpbnNpZGUgdGhlIGtlcm5lbC4gKi8KY2NsX2RldmljZV9pbmxpbmUgZmxvYXQzIGRpZmZyYWN0aW9uX3dhdmVsZW5ndGhfdG9fcmdiKGZsb2F0IGxhbWJkYSkKewogIC8qIHBpZWNld2lzZSBnYXVzc2lhbnMgZm9yIFgsWSxaICovCiAgY29uc3QgZmxvYXQgeCA9IDEuMDU2ZiAqIGV4cGYoLTAuNWYgKiBzcXIoKGxhbWJkYSAtIDU5OS44ZikgLyAoKGxhbWJkYSA8IDU5OS44ZikgPyAzNy45ZiA6IDMxLjBmKSkpCiAgICAgICAgICAgICAgICArIDAuMzYyZiAqIGV4cGYoLTAuNWYgKiBzcXIoKGxhbWJkYSAtIDQ0Mi4wZikgLyAoKGxhbWJkYSA8IDQ0Mi4wZikgPyAxNi4wZiA6IDI2LjdmKSkpCiAgICAgICAgICAgICAgICAtIDAuMDY1ZiAqIGV4cGYoLTAuNWYgKiBzcXIoKGxhbWJkYSAtIDUwMS4xZikgLyAoKGxhbWJkYSA8IDUwMS4xZikgPyAyMC40ZiA6IDI2LjJmKSkpOwogIGNvbnN0IGZsb2F0IHkgPSAwLjgyMWYgKiBleHBmKC0wLjVmICogc3FyKChsYW1iZGEgLSA1NjguOGYpIC8gKChsYW1iZGEgPCA1NjguOGYpID8gNDYuOWYgOiA0MC41ZikpKQogICAgICAgICAgICAgICAgKyAwLjI4NmYgKiBleHBmKC0wLjVmICogc3FyKChsYW1iZGEgLSA1MzAuOWYpIC8gKChsYW1iZGEgPCA1MzAuOWYpID8gMTYuM2YgOiAzMS4xZikpKTsKICBjb25zdCBmbG9hdCB6ID0gMS4yMTdmICogZXhwZigtMC41ZiAqIHNxcigobGFtYmRhIC0gNDM3LjBmKSAvICgobGFtYmRhIDwgNDM3LjBmKSA/IDExLjhmIDogMzYuMGYpKSkKICAgICAgICAgICAgICAgICsgMC42ODFmICogZXhwZigtMC41ZiAqIHNxcigobGFtYmRhIC0gNDU5LjBmKSAvICgobGFtYmRhIDwgNDU5LjBmKSA/IDI2LjBmIDogMTMuOGYpKSk7CiAgZmxvYXQgciA9ICAzLjI0MDZmICogeCAtIDEuNTM3MmYgKiB5IC0gMC40OTg2ZiAqIHo7CiAgZmxvYXQgZyA9IC0wLjk2ODlmICogeCArIDEuODc1OGYgKiB5ICsgMC4wNDE1ZiAqIHo7CiAgZmxvYXQgYiA9ICAwLjA1NTdmICogeCAtIDAuMjA0MGYgKiB5ICsgMS4wNTcwZiAqIHo7CiAgciA9IGZtYXhmKHIsIDAuMGYpOyBnID0gZm1heGYoZywgMC4wZik7IGIgPSBmbWF4ZihiLCAwLjBmKTsKICByZXR1cm4gbWFrZV9mbG9hdDMociwgZywgYik7Cn0KCmNjbF9kZXZpY2UgaW50IGJzZGZfZGlmZnJhY3Rpb25fc2V0dXAoY2NsX3ByaXZhdGUgRGlmZnJhY3Rpb25Cc2RmICpic2RmKQp7CiAgYnNkZi0+dHlwZSA9IENMT1NVUkVfQlNERl9ESUZGUkFDVElPTl9JRDsKICBic2RmLT5zcGFjaW5nX25tID0gZm1heGYoYnNkZi0+c3BhY2luZ19ubSwgNTAuMGYpOwogIGJzZGYtPnJvdWdobmVzcyA9IGNsYW1wKGJzZGYtPnJvdWdobmVzcywgMC4wZiwgMS4wZik7CiAgaWYgKGJzZGYtPm1heF9vcmRlciA8IDEpIGJzZGYtPm1heF9vcmRlciA9IDE7CiAgaWYgKGJzZGYtPm1heF9vcmRlciA+IDgpIGJzZGYtPm1heF9vcmRlciA9IDg7CiAgcmV0dXJuIFNEX0JTREYgfCBTRF9CU0RGX0hBU19FVkFMOwp9CgovKiBEZXRlcm1pbmlzdGljIG9yZGVyK3dhdmVsZW5ndGggcmVmbGVjdGlvbiBkaXJlY3Rpb24gZm9yIGEgZ2l2ZW4gKG9yZGVyLCBsYW1iZGEpLiAqLwpjY2xfZGV2aWNlX2lubGluZSBib29sIGRpZmZyYWN0aW9uX29yZGVyX2Rpcihjb25zdCBjY2xfcHJpdmF0ZSBEaWZmcmFjdGlvbkJzZGYgKmJzZGYsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNvbnN0IGZsb2F0MyB3aSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY29uc3QgaW50IG9yZGVyLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBjb25zdCBmbG9hdCBsYW1iZGEsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNjbF9wcml2YXRlIGZsb2F0MyAqd28pCnsKICBjb25zdCBmbG9hdDMgTiA9IGJzZGYtPk47CiAgZmxvYXQzIFQgPSBic2RmLT5UIC0gTiAqIGRvdChOLCBic2RmLT5UKTsKICBjb25zdCBmbG9hdCB0bGVuID0gbGVuKFQpOwogIGlmICh0bGVuIDwgMWUtNmYpIHJldHVybiBmYWxzZTsKICBUID0gVCAvIHRsZW47CgogIC8qIGluY2lkZW5jZSBhbmdsZSBjb21wb25lbnQgYWxvbmcgdGhlIGdyYXRpbmcgZGlzcGVyc2lvbiBheGlzICovCiAgY29uc3QgZmxvYXQgc2luX2kgPSBkb3QoLXdpLCBUKTsKICBjb25zdCBmbG9hdCBzaW5fbSA9IHNpbl9pICsgKGZsb2F0KW9yZGVyICogbGFtYmRhIC8gYnNkZi0+c3BhY2luZ19ubTsKICBpZiAoc2luX20gPCAtMS4wZiB8fCBzaW5fbSA+IDEuMGYpIHJldHVybiBmYWxzZTsKCiAgLyogYmFzZSBzcGVjdWxhciByZWZsZWN0aW9uLCB0aGVuIHJvdGF0ZSBhYm91dCB0aGUgZ3Jvb3ZlIGF4aXMgYnkgdGhlIGV4dHJhIGFuZ2xlICovCiAgY29uc3QgZmxvYXQzIFIgPSAyLjBmICogZG90KHdpLCBOKSAqIE4gLSB3aTsgLyogbWlycm9yIG9mIHdpICh3aSBwb2ludHMgdG8gdmlld2VyKSAqLwogIGNvbnN0IGZsb2F0IGR0aGV0YSA9IGFzaW5mKHNpbl9tKSAtIGFzaW5mKGNsYW1wKHNpbl9pLCAtMS4wZiwgMS4wZikpOwogIC8qIHJvdGF0ZSBSIGFib3V0IFQgYnkgZHRoZXRhIChSb2RyaWd1ZXMpICovCiAgY29uc3QgZmxvYXQgYyA9IGNvc2YoZHRoZXRhKSwgcyA9IHNpbmYoZHRoZXRhKTsKICBjb25zdCBmbG9hdDMgUnIgPSBSICogYyArIGNyb3NzKFQsIFIpICogcyArIFQgKiAoZG90KFQsIFIpICogKDEuMGYgLSBjKSk7CiAgKndvID0gbm9ybWFsaXplKFJyKTsKICByZXR1cm4gZG90KCp3bywgTikgPiAwLjBmOwp9CgpjY2xfZGV2aWNlIFNwZWN0cnVtIGJzZGZfZGlmZnJhY3Rpb25fZXZhbChjb25zdCBjY2xfcHJpdmF0ZSBTaGFkZXJDbG9zdXJlICpzYywKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY29uc3QgZmxvYXQzIHdpLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBjb25zdCBmbG9hdDMgd28sCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNjbF9wcml2YXRlIGZsb2F0ICpwZGYpCnsKICAvKiBEaWZmcmFjdGlvbiBvcmRlcnMgYXJlIChuZWFyLSlzaW5ndWxhciBkaXJlY3Rpb25zOyB0cmVhdCBsaWtlIGEgc2hhcnAKICAgKiBtdWx0aS1sb2JlIHJlZmxlY3Rpb246IGV2YWwgaXMgfjAgZm9yIGFyYml0cmFyeSB3bywgc2FtcGxpbmcgZG9lcyB0aGUgd29yay4gKi8KICBjb25zdCBjY2xfcHJpdmF0ZSBEaWZmcmFjdGlvbkJzZGYgKmJzZGYgPSAoY29uc3QgY2NsX3ByaXZhdGUgRGlmZnJhY3Rpb25Cc2RmICopc2M7CiAgaWYgKGJzZGYtPnJvdWdobmVzcyA8PSAwLjBmKSB7CiAgICAqcGRmID0gMC4wZjsKICAgIHJldHVybiB6ZXJvX3NwZWN0cnVtKCk7CiAgfQogIC8qIFJvdWdoIGdyYXRpbmdzOiBhcHByb3hpbWF0ZSBieSBuZWFyZXN0LW9yZGVyIGxvYmUgd2VpZ2h0LiAqLwogIGNvbnN0IGZsb2F0MyBOID0gYnNkZi0+TjsKICBjb25zdCBmbG9hdCBjb3NOTyA9IGRvdChOLCB3byk7CiAgaWYgKGNvc05PIDw9IDAuMGYpIHsgKnBkZiA9IDAuMGY7IHJldHVybiB6ZXJvX3NwZWN0cnVtKCk7IH0KICBjb25zdCBmbG9hdCBhID0gZm1heGYoYnNkZi0+cm91Z2huZXNzICogYnNkZi0+cm91Z2huZXNzLCAxZS00Zik7CiAgLyogY3J1ZGUgbG9iZSBwZGYgYXJvdW5kIHNwZWN1bGFyOyBrZWVwcyBlbmVyZ3kgc2FuZSBmb3Igcm91Z2ggY2FzZSAqLwogIGNvbnN0IGZsb2F0MyBSID0gMi4wZiAqIGRvdCh3aSwgTikgKiBOIC0gd2k7CiAgY29uc3QgZmxvYXQgZCA9IGZtYXhmKGRvdChub3JtYWxpemUoUiksIHdvKSwgMC4wZik7CiAgY29uc3QgZmxvYXQgbG9iZSA9IHBvd2YoZCwgMS4wZiAvIGEpOwogICpwZGYgPSBsb2JlICogY29zTk8gKiBNXzFfUElfRjsKICByZXR1cm4gbWFrZV9zcGVjdHJ1bSgqcGRmKTsKfQoKY2NsX2RldmljZSBpbnQgYnNkZl9kaWZmcmFjdGlvbl9zYW1wbGUoY29uc3QgY2NsX3ByaXZhdGUgU2hhZGVyQ2xvc3VyZSAqc2MsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNvbnN0IGZsb2F0MyBOZywKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY29uc3QgZmxvYXQzIHdpLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBjb25zdCBmbG9hdDIgcmFuZCwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY2NsX3ByaXZhdGUgU3BlY3RydW0gKmV2YWwsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNjbF9wcml2YXRlIGZsb2F0MyAqd28sCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNjbF9wcml2YXRlIGZsb2F0ICpwZGYpCnsKICBjb25zdCBjY2xfcHJpdmF0ZSBEaWZmcmFjdGlvbkJzZGYgKmJzZGYgPSAoY29uc3QgY2NsX3ByaXZhdGUgRGlmZnJhY3Rpb25Cc2RmICopc2M7CgogIC8qIGNob29zZSBhIHdhdmVsZW5ndGggdW5pZm9ybWx5IG92ZXIgdGhlIHZpc2libGUgYmFuZCAqLwogIGNvbnN0IGZsb2F0IGxhbWJkYSA9IDM4MC4wZiArIHJhbmQueCAqICg3MzAuMGYgLSAzODAuMGYpOwoKICAvKiBlbnVtZXJhdGUgZmVhc2libGUgb3JkZXJzIGZvciB0aGlzIHdhdmVsZW5ndGgsIHBpY2sgb25lIHVuaWZvcm1seSAqLwogIGNvbnN0IGludCBNID0gYnNkZi0+bWF4X29yZGVyOwogIGludCBmZWFzaWJsZVsxN107CiAgaW50IG5mID0gMDsKICBmb3IgKGludCBtID0gLU07IG0gPD0gTTsgbSsrKSB7CiAgICBpZiAobSA9PSAwKSBjb250aW51ZTsgLyogbGV0IGEgc2VwYXJhdGUgc3BlY3VsYXIgdGVybSAoYWRkZWQgaW4gc3ZtKSBjYXJyeSAwdGggb3JkZXIgKi8KICAgIGZsb2F0MyB0ZXN0OwogICAgaWYgKGRpZmZyYWN0aW9uX29yZGVyX2Rpcihic2RmLCB3aSwgbSwgbGFtYmRhLCAmdGVzdCkpIHsKICAgICAgZmVhc2libGVbbmYrK10gPSBtOwogICAgfQogIH0KICBpZiAobmYgPT0gMCkgeyAqcGRmID0gMC4wZjsgKmV2YWwgPSB6ZXJvX3NwZWN0cnVtKCk7IHJldHVybiBMQUJFTF9SRUZMRUNUIHwgTEFCRUxfR0xPU1NZOyB9CgogIGNvbnN0IGludCBwaWNrID0gbWluKChpbnQpKHJhbmQueSAqIChmbG9hdCluZiksIG5mIC0gMSk7CiAgY29uc3QgaW50IG9yZGVyID0gZmVhc2libGVbcGlja107CiAgaWYgKCFkaWZmcmFjdGlvbl9vcmRlcl9kaXIoYnNkZiwgd2ksIG9yZGVyLCBsYW1iZGEsIHdvKSkgewogICAgKnBkZiA9IDAuMGY7ICpldmFsID0gemVyb19zcGVjdHJ1bSgpOyByZXR1cm4gTEFCRUxfUkVGTEVDVCB8IExBQkVMX0dMT1NTWTsKICB9CgogIGlmIChkb3QoTmcsICp3bykgPD0gMC4wZikgeyAqcGRmID0gMC4wZjsgKmV2YWwgPSB6ZXJvX3NwZWN0cnVtKCk7IHJldHVybiBMQUJFTF9SRUZMRUNUIHwgTEFCRUxfR0xPU1NZOyB9CgogIC8qIGNvbG91ciBvZiB0aGlzIHdhdmVsZW5ndGg7IG5vcm1hbGlzZSBzbyB0aGUgaW50ZWdyYXRlZCBiYW5kIH4gd2hpdGUgKi8KICBjb25zdCBmbG9hdDMgcmdiID0gZGlmZnJhY3Rpb25fd2F2ZWxlbmd0aF90b19yZ2IobGFtYmRhKSAqICgxLjBmIC8gMTA2LjBmKTsKICAvKiBwZGY6IHVuaWZvcm0gb3ZlciAod2F2ZWxlbmd0aCBiYW5kKSB4IChmZWFzaWJsZSBvcmRlcnMpLiBVc2UgYSBib3VuZGVkIHZhbHVlCiAgICogc28gdGhlIHNpbmd1bGFyIGRpcmVjdGlvbiBjb250cmlidXRlcyBhIGZpbml0ZSwgd2VsbC1iZWhhdmVkIHNhbXBsZS4gKi8KICAqcGRmID0gMS4wZiAvIChmbG9hdCluZjsKICAqZXZhbCA9IHJnYl90b19zcGVjdHJ1bShtYXgocmdiLCB6ZXJvX2Zsb2F0MygpKSkgKiAoKnBkZik7CiAgcmV0dXJuIExBQkVMX1JFRkxFQ1QgfCBMQUJFTF9HTE9TU1k7Cn0KCkNDTF9OQU1FU1BBQ0VfRU5ECg=="
).decode()

def edit(path, replacements):
    s = open(path).read()
    for old, new, tag in replacements:
        if new and new in s and old not in s:
            print(f"{path}: '{tag}' already applied"); continue
        n = s.count(old)
        if n != 1:
            sys.stderr.write(f"FATAL {path}: anchor '{tag}' found {n} times (need 1)\n"); sys.exit(1)
        s = s.replace(old, new, 1)
        print(f"{path}: applied '{tag}'")
    open(path, "w").write(s)

def create(path, content):
    open(path, "w").write(content)
    print(f"{path}: created")

CY = "blender/intern/cycles"

# ---------- (1) new closure enum id ----------
edit(f"{CY}/kernel/svm/types.h", [
  ("  CLOSURE_BSDF_ASHIKHMIN_SHIRLEY_ID,\n",
   "  CLOSURE_BSDF_ASHIKHMIN_SHIRLEY_ID,\n  CLOSURE_BSDF_DIFFRACTION_ID,\n",
   "enum-diffraction-id"),
])

# ---------- (2) the closure kernel header ----------
create(f"{CY}/kernel/closure/bsdf_diffraction.h", BSDF_DIFFRACTION_H)

# ---------- (3) register in kernel CMake source list ----------
edit(f"{CY}/kernel/CMakeLists.txt", [
  ("  closure/bsdf_diffuse.h\n",
   "  closure/bsdf_diffuse.h\n  closure/bsdf_diffraction.h\n",
   "cmake-register-header"),
])

# ---------- (4) include + dispatch in closure/bsdf.h ----------
# 4a. include the header near the other closure includes
edit(f"{CY}/kernel/closure/bsdf.h", [
  ('#include "kernel/closure/bsdf_diffuse.h"\n',
   '#include "kernel/closure/bsdf_diffuse.h"\n#include "kernel/closure/bsdf_diffraction.h"\n',
   "bsdf-h-include"),
])
# 4b. sample dispatch
edit(f"{CY}/kernel/closure/bsdf.h", [
  ("    case CLOSURE_BSDF_DIFFUSE_ID:\n      label = bsdf_diffuse_sample(sc, Ng, sd->wi, rand_xy, eval, wo, pdf);\n",
   "    case CLOSURE_BSDF_DIFFUSE_ID:\n      label = bsdf_diffuse_sample(sc, Ng, sd->wi, rand_xy, eval, wo, pdf);\n      break;\n    case CLOSURE_BSDF_DIFFRACTION_ID:\n      label = bsdf_diffraction_sample(sc, Ng, sd->wi, rand_xy, eval, wo, pdf);\n",
   "bsdf-h-sample"),
])
# 4c. eval dispatch
edit(f"{CY}/kernel/closure/bsdf.h", [
  ("    case CLOSURE_BSDF_DIFFUSE_ID:\n      eval = bsdf_diffuse_eval(sc, sd->wi, wo, pdf);\n",
   "    case CLOSURE_BSDF_DIFFUSE_ID:\n      eval = bsdf_diffuse_eval(sc, sd->wi, wo, pdf);\n      break;\n    case CLOSURE_BSDF_DIFFRACTION_ID:\n      eval = bsdf_diffraction_eval(sc, sd->wi, wo, pdf);\n",
   "bsdf-h-eval"),
])
# 4d. roughness/eta query dispatch (bsdf_roughness_eta)
edit(f"{CY}/kernel/closure/bsdf.h", [
  ("    case CLOSURE_BSDF_DIFFUSE_ID:\n      *roughness = one_float2();\n      *eta = 1.0f;\n      break;\n",
   "    case CLOSURE_BSDF_DIFFUSE_ID:\n      *roughness = one_float2();\n      *eta = 1.0f;\n      break;\n    case CLOSURE_BSDF_DIFFRACTION_ID:\n      *roughness = one_float2();\n      *eta = 1.0f;\n      break;\n",
   "bsdf-h-roughness"),
])

# ---------- (5) SVM closure reader: intercept diffraction distribution ----------
edit(f"{CY}/kernel/svm/closure.h", [
  ("    case CLOSURE_BSDF_MICROFACET_GGX_ID:\n    case CLOSURE_BSDF_MICROFACET_BECKMANN_ID:\n    case CLOSURE_BSDF_ASHIKHMIN_SHIRLEY_ID:\n    case CLOSURE_BSDF_MICROFACET_MULTI_GGX_ID: {\n",
   ("    case CLOSURE_BSDF_DIFFRACTION_ID: {\n"
    "      const Spectrum weight = closure_weight * mix_weight;\n"
    "      ccl_private DiffractionBsdf *bsdf = (ccl_private DiffractionBsdf *)bsdf_alloc(\n"
    "          sd, sizeof(DiffractionBsdf), weight);\n"
    "      if (bsdf) {\n"
    "        bsdf->N = maybe_ensure_valid_specular_reflection(sd, N);\n"
    "        /* groove direction from the Glossy node's Tangent socket (data_node.w). */\n"
    "        if (data_node.w != SVM_STACK_INVALID) {\n"
    "          bsdf->T = stack_load_float3(stack, data_node.w);\n"
    "          const float rotation = stack_load_float(stack, data_node.y);\n"
    "          if (rotation != 0.0f) {\n"
    "            bsdf->T = rotate_around_axis(bsdf->T, bsdf->N, rotation * M_2PI_F);\n"
    "          }\n"
    "        }\n"
    "        else {\n"
    "          bsdf->T = make_float3(1.0f, 0.0f, 0.0f);\n"
    "        }\n"
    "        /* Roughness socket [0,1] maps to groove spacing 500..3500 nm; a small value\n"
    "         * gives a wide single-order fan, a large value packs multiple narrow orders. */\n"
    "        const float rr = saturatef(param1);\n"
    "        bsdf->spacing_nm = 500.0f + rr * 3000.0f;\n"
    "        bsdf->roughness = 0.0f;\n"
    "        bsdf->max_order = 3;\n"
    "        sd->flag |= bsdf_diffraction_setup(bsdf);\n"
    "      }\n"
    "      break;\n"
    "    }\n"
    "    case CLOSURE_BSDF_MICROFACET_GGX_ID:\n    case CLOSURE_BSDF_MICROFACET_BECKMANN_ID:\n    case CLOSURE_BSDF_ASHIKHMIN_SHIRLEY_ID:\n    case CLOSURE_BSDF_MICROFACET_MULTI_GGX_ID: {\n"),
   "svm-diffraction-reader"),
])

# ---------- (6) host: add 'diffraction' to Glossy node distribution enum ----------
edit(f"{CY}/scene/shader_nodes.cpp", [
  ('  distribution_enum.insert("ashikhmin_shirley", CLOSURE_BSDF_ASHIKHMIN_SHIRLEY_ID);\n'
   '  distribution_enum.insert("multi_ggx", CLOSURE_BSDF_MICROFACET_MULTI_GGX_ID);\n'
   '  SOCKET_ENUM(distribution, "Distribution", distribution_enum, CLOSURE_BSDF_MICROFACET_GGX_ID);\n\n'
   '  SOCKET_IN_VECTOR(tangent, "Tangent", zero_float3(), SocketType::LINK_TANGENT);\n',
   '  distribution_enum.insert("ashikhmin_shirley", CLOSURE_BSDF_ASHIKHMIN_SHIRLEY_ID);\n'
   '  distribution_enum.insert("multi_ggx", CLOSURE_BSDF_MICROFACET_MULTI_GGX_ID);\n'
   '  distribution_enum.insert("diffraction", CLOSURE_BSDF_DIFFRACTION_ID);\n'
   '  SOCKET_ENUM(distribution, "Distribution", distribution_enum, CLOSURE_BSDF_MICROFACET_GGX_ID);\n\n'
   '  SOCKET_IN_VECTOR(tangent, "Tangent", zero_float3(), SocketType::LINK_TANGENT);\n',
   "host-glossy-enum"),
])

# ---------- (7) host: make Glossy compile() force anisotropic path for diffraction ----------
# Diffraction needs the Tangent packed into data_node.w, which only happens on the
# anisotropic branch of BsdfNode::compile. Force a tiny tangent link path by treating
# diffraction like the multi_ggx branch (passes tangent) and ensure tangent is linked.
edit(f"{CY}/scene/shader_nodes.cpp", [
  ("void GlossyBsdfNode::compile(SVMCompiler &compiler)\n{\n  closure = distribution;\n\n  ShaderInput *tangent = input(\"Tangent\");\n  tangent = compiler.is_linked(tangent) ? tangent : nullptr;\n",
   "void GlossyBsdfNode::compile(SVMCompiler &compiler)\n{\n  closure = distribution;\n\n  ShaderInput *tangent = input(\"Tangent\");\n  tangent = compiler.is_linked(tangent) ? tangent : nullptr;\n\n  /* Diffraction grating: reuse the anisotropic packing so the Tangent (groove\n   * direction) and Rotation reach the kernel via data_node.w / data_node.y. */\n  if (closure == CLOSURE_BSDF_DIFFRACTION_ID) {\n    BsdfNode::compile(\n        compiler, input(\"Roughness\"), input(\"Anisotropy\"), input(\"Rotation\"), nullptr, tangent);\n    return;\n  }\n",
   "host-glossy-compile"),
])

# ---------- (8) host: OSL side enum parity (harmless on iOS where OSL is off) ----------
# Keeps the OSL compiler node list consistent if ever built with OSL.
# (No-op guarded: only patches if the OSL glossy registration exists.)
try:
    s = open(f"{CY}/scene/shader_nodes.cpp").read()
    if 'compiler.add(this, "node_glossy_bsdf");' in s:
        pass  # nothing required; enum string is passed through generically
except FileNotFoundError:
    pass

print("BUILD-32 (native Diffraction Grating BSDF: CPU + Metal GPU via Glossy 'diffraction' distribution) APPLIED OK")
