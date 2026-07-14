"""Integrate monochrome wavelength passes against CIE 1931 CMFs -> sRGB image."""
import json, math, numpy as np

# Wyman/Sloan/Shirley multi-lobe Gaussian fit of CIE 1931 2-deg CMFs
def g(x, m, s1, s2): 
    s = np.where(x < m, s1, s2); return np.exp(-0.5*((x-m)/s)**2)
def cie_xyz(l):
    x = 1.056*g(l,599.8,37.9,31.0) + 0.362*g(l,442.0,16.0,26.7) - 0.065*g(l,501.1,20.4,26.2)
    y = 0.821*g(l,568.8,46.9,40.5) + 0.286*g(l,530.9,16.3,31.1)
    z = 1.217*g(l,437.0,11.8,36.0) + 0.681*g(l,459.0,26.0,13.8)
    return x, y, z

waves = json.load(open("spectral_passes/waves.json"))
try:
    import OpenEXR, Imath
    def load_exr(p):
        f = OpenEXR.InputFile(p); dw = f.header()['dataWindow']
        w, h = dw.max.x-dw.min.x+1, dw.max.y-dw.min.y+1
        pt = Imath.PixelType(Imath.PixelType.FLOAT)
        r = np.frombuffer(f.channel('R', pt), np.float32).reshape(h, w)
        return r
except ImportError:
    import imageio.v3 as iio
    def load_exr(p): return iio.imread(p)[..., 0]

X = Y = Z = None
for i, wl in enumerate(waves):
    I = load_exr(f"spectral_passes/pass_{i:02d}.exr").astype(np.float64)
    cx, cy, cz = cie_xyz(np.array([wl]))
    if X is None: X = np.zeros_like(I); Y = np.zeros_like(I); Z = np.zeros_like(I)
    X += I*cx[0]; Y += I*cy[0]; Z += I*cz[0]

# XYZ -> linear sRGB
M = np.array([[ 3.2406, -1.5372, -0.4986],
              [-0.9689,  1.8758,  0.0415],
              [ 0.0557, -0.2040,  1.0570]])
xyz = np.stack([X, Y, Z], -1)
rgb = xyz @ M.T
# gamut-map: desaturate toward luminance rather than clipping hue
lum = (xyz @ np.array([0.0, 1.0, 0.0]))[..., None]
neg = rgb.min(-1, keepdims=True)
rgb = np.where(neg < 0, rgb - neg, rgb)  # simple additive lift preserves hue direction
rgb *= 0.55 / max(np.percentile(rgb, 99.7), 1e-9)   # exposure
rgb = np.clip(rgb, 0, 1) ** (1/2.2)
import imageio.v3 as iio
iio.imwrite("spectral_result.png", (rgb*255).astype(np.uint8))
print("INTEGRATED ->", rgb.shape)
