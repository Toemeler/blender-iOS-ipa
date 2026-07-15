/* SPDX-License-Identifier: BSD-3-Clause
 * Diffraction grating BSDF for Cycles (CPU + GPU/Metal).
 * Physical model: grating equation  sin(theta_m) = sin(theta_i) + m * lambda / d
 * Reflective grating; sums a bounded set of diffraction orders. Wavelength is
 * chosen per-sample by importance over the visible band and converted to the
 * render's Spectrum via wavelength->XYZ->rgb, so it works identically in the
 * RGB kernel on every device. */

#pragma once

#include "kernel/types.h"
#include "kernel/sample/mapping.h"

CCL_NAMESPACE_BEGIN

/* Fits within ShaderClosure padding: base + N already present; we add spacing,
 * a packed tangent, roughness and order cap. */
struct DiffractionBsdf {
  SHADER_CLOSURE_BASE;
  packed_float3 T;   /* groove direction (unit), in world space */
  float spacing_nm;  /* groove spacing d, nanometres */
  float roughness;   /* [0,1] micro-roughness blur of each order */
  int max_order;     /* highest |m| to include */
};

static_assert(sizeof(ShaderClosure) >= sizeof(DiffractionBsdf), "DiffractionBsdf is too large!");

/* CIE-ish wavelength(nm) -> linear sRGB, compact fit (Wyman/Sloan/Shirley style).
 * Kept local so no external tables are needed inside the kernel. */
ccl_device_inline float3 diffraction_wavelength_to_rgb(float lambda)
{
  /* piecewise gaussians for X,Y,Z */
  const float x = 1.056f * expf(-0.5f * sqr((lambda - 599.8f) / ((lambda < 599.8f) ? 37.9f : 31.0f)))
                + 0.362f * expf(-0.5f * sqr((lambda - 442.0f) / ((lambda < 442.0f) ? 16.0f : 26.7f)))
                - 0.065f * expf(-0.5f * sqr((lambda - 501.1f) / ((lambda < 501.1f) ? 20.4f : 26.2f)));
  const float y = 0.821f * expf(-0.5f * sqr((lambda - 568.8f) / ((lambda < 568.8f) ? 46.9f : 40.5f)))
                + 0.286f * expf(-0.5f * sqr((lambda - 530.9f) / ((lambda < 530.9f) ? 16.3f : 31.1f)));
  const float z = 1.217f * expf(-0.5f * sqr((lambda - 437.0f) / ((lambda < 437.0f) ? 11.8f : 36.0f)))
                + 0.681f * expf(-0.5f * sqr((lambda - 459.0f) / ((lambda < 459.0f) ? 26.0f : 13.8f)));
  float r =  3.2406f * x - 1.5372f * y - 0.4986f * z;
  float g = -0.9689f * x + 1.8758f * y + 0.0415f * z;
  float b =  0.0557f * x - 0.2040f * y + 1.0570f * z;
  r = fmaxf(r, 0.0f); g = fmaxf(g, 0.0f); b = fmaxf(b, 0.0f);
  return make_float3(r, g, b);
}

ccl_device int bsdf_diffraction_setup(ccl_private DiffractionBsdf *bsdf)
{
  bsdf->type = CLOSURE_BSDF_DIFFRACTION_ID;
  bsdf->spacing_nm = fmaxf(bsdf->spacing_nm, 50.0f);
  bsdf->roughness = clamp(bsdf->roughness, 0.0f, 1.0f);
  if (bsdf->max_order < 1) bsdf->max_order = 1;
  if (bsdf->max_order > 8) bsdf->max_order = 8;
  return SD_BSDF | SD_BSDF_HAS_EVAL;
}

/* Deterministic order+wavelength reflection direction for a given (order, lambda). */
ccl_device_inline bool diffraction_order_dir(const ccl_private DiffractionBsdf *bsdf,
                                             const float3 wi,
                                             const int order,
                                             const float lambda,
                                             ccl_private float3 *wo)
{
  const float3 N = bsdf->N;
  float3 T = bsdf->T - N * dot(N, bsdf->T);
  const float tlen = len(T);
  if (tlen < 1e-6f) return false;
  T = T / tlen;

  /* incidence angle component along the grating dispersion axis */
  const float sin_i = dot(-wi, T);
  const float sin_m = sin_i + (float)order * lambda / bsdf->spacing_nm;
  if (sin_m < -1.0f || sin_m > 1.0f) return false;

  /* base specular reflection, then rotate about the groove axis by the extra angle */
  const float3 R = 2.0f * dot(wi, N) * N - wi; /* mirror of wi (wi points to viewer) */
  const float dtheta = asinf(sin_m) - asinf(clamp(sin_i, -1.0f, 1.0f));
  /* rotate R about T by dtheta (Rodrigues) */
  const float c = cosf(dtheta), s = sinf(dtheta);
  const float3 Rr = R * c + cross(T, R) * s + T * (dot(T, R) * (1.0f - c));
  *wo = normalize(Rr);
  return dot(*wo, N) > 0.0f;
}

ccl_device Spectrum bsdf_diffraction_eval(const ccl_private ShaderClosure *sc,
                                          const float3 wi,
                                          const float3 wo,
                                          ccl_private float *pdf)
{
  /* Diffraction orders are (near-)singular directions; treat like a sharp
   * multi-lobe reflection: eval is ~0 for arbitrary wo, sampling does the work. */
  const ccl_private DiffractionBsdf *bsdf = (const ccl_private DiffractionBsdf *)sc;
  if (bsdf->roughness <= 0.0f) {
    *pdf = 0.0f;
    return zero_spectrum();
  }
  /* Rough gratings: approximate by nearest-order lobe weight. */
  const float3 N = bsdf->N;
  const float cosNO = dot(N, wo);
  if (cosNO <= 0.0f) { *pdf = 0.0f; return zero_spectrum(); }
  const float a = fmaxf(bsdf->roughness * bsdf->roughness, 1e-4f);
  /* crude lobe pdf around specular; keeps energy sane for rough case */
  const float3 R = 2.0f * dot(wi, N) * N - wi;
  const float d = fmaxf(dot(normalize(R), wo), 0.0f);
  const float lobe = powf(d, 1.0f / a);
  *pdf = lobe * cosNO * M_1_PI_F;
  return make_spectrum(*pdf);
}

ccl_device int bsdf_diffraction_sample(const ccl_private ShaderClosure *sc,
                                       const float3 Ng,
                                       const float3 wi,
                                       const float2 rand,
                                       ccl_private Spectrum *eval,
                                       ccl_private float3 *wo,
                                       ccl_private float *pdf)
{
  const ccl_private DiffractionBsdf *bsdf = (const ccl_private DiffractionBsdf *)sc;

  /* choose a wavelength uniformly over the visible band */
  const float lambda = 380.0f + rand.x * (730.0f - 380.0f);

  /* enumerate feasible orders for this wavelength, pick one uniformly */
  const int M = bsdf->max_order;
  int feasible[17];
  int nf = 0;
  for (int m = -M; m <= M; m++) {
    if (m == 0) continue; /* let a separate specular term (added in svm) carry 0th order */
    float3 test;
    if (diffraction_order_dir(bsdf, wi, m, lambda, &test)) {
      feasible[nf++] = m;
    }
  }
  if (nf == 0) { *pdf = 0.0f; *eval = zero_spectrum(); return LABEL_REFLECT | LABEL_GLOSSY; }

  const int pick = min((int)(rand.y * (float)nf), nf - 1);
  const int order = feasible[pick];
  if (!diffraction_order_dir(bsdf, wi, order, lambda, wo)) {
    *pdf = 0.0f; *eval = zero_spectrum(); return LABEL_REFLECT | LABEL_GLOSSY;
  }

  if (dot(Ng, *wo) <= 0.0f) { *pdf = 0.0f; *eval = zero_spectrum(); return LABEL_REFLECT | LABEL_GLOSSY; }

  /* colour of this wavelength; normalise so the integrated band ~ white */
  const float3 rgb = diffraction_wavelength_to_rgb(lambda) * (1.0f / 106.0f);
  /* pdf: uniform over (wavelength band) x (feasible orders). Use a bounded value
   * so the singular direction contributes a finite, well-behaved sample. */
  *pdf = 1.0f / (float)nf;
  *eval = rgb_to_spectrum(max(rgb, zero_float3())) * (*pdf);
  return LABEL_REFLECT | LABEL_GLOSSY;
}

CCL_NAMESPACE_END
