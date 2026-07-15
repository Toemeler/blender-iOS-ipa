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
create(f"{CY}/kernel/closure/bsdf_diffraction.h", open("bsdf_diffraction.h").read())

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
