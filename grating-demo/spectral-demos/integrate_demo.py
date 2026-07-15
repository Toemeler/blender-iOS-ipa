import json, sys, numpy as np, imageio.v3 as iio, os
prefix = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
outdir = os.path.join(HERE, prefix + "_passes")
waves = json.load(open(os.path.join(outdir,"waves.json")))
def g(x,m,s1,s2): s=np.where(x<m,s1,s2); return np.exp(-0.5*((x-m)/s)**2)
def xyz(l):
    x=1.056*g(l,599.8,37.9,31.0)+0.362*g(l,442.0,16.0,26.7)-0.065*g(l,501.1,20.4,26.2)
    y=0.821*g(l,568.8,46.9,40.5)+0.286*g(l,530.9,16.3,31.1)
    z=1.217*g(l,437.0,11.8,36.0)+0.681*g(l,459.0,26.0,13.8)
    return x,y,z
X=Y=Z=None
for i,wl in enumerate(waves):
    im = iio.imread(os.path.join(outdir,f"p{i:02d}.exr"))
    I = im[...,0].astype(np.float64) if im.ndim==3 else im.astype(np.float64)
    cx,cy,cz = xyz(np.array([wl]))
    if X is None: X=np.zeros_like(I);Y=np.zeros_like(I);Z=np.zeros_like(I)
    X+=I*cx[0];Y+=I*cy[0];Z+=I*cz[0]
xyz_img=np.stack([X,Y,Z],-1)
M=np.array([[3.2406,-1.5372,-0.4986],[-0.9689,1.8758,0.0415],[0.0557,-0.2040,1.0570]])
rgb=xyz_img@M.T
neg=rgb.min(-1,keepdims=True); rgb=np.where(neg<0,rgb-neg,rgb)
p=np.percentile(rgb,99.5); rgb*=0.6/max(p,1e-9)
rgb=np.clip(rgb,0,1)**(1/2.2)
iio.imwrite(os.path.join(HERE,prefix+"_result.png"),(rgb*255).astype(np.uint8))
print(prefix,"integrated",rgb.shape)
