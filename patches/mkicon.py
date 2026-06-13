#!/usr/bin/env python3
# Non-fatal: render Blender logo on charcoal -> app icons + Info.plist keys.
import sys, os
app = sys.argv[1]; svg = sys.argv[2]
try:
    import io, cairosvg, plistlib
    from PIL import Image
    png = cairosvg.svg2png(url=svg, output_width=760, output_height=760)
    logo = Image.open(io.BytesIO(png)).convert("RGBA")
    bg = Image.new("RGBA", (1024, 1024), (38, 38, 38, 255))  # Blender charcoal
    bg.paste(logo, ((1024 - logo.width)//2, (1024 - logo.height)//2), logo)
    icon = bg.convert("RGB")
    sizes = {"AppIcon60x60@2x.png":120, "AppIcon76x76@2x~ipad.png":152,
             "AppIcon83.5x83.5@2x~ipad.png":167, "AppIcon1024x1024.png":1024}
    for name, px in sizes.items():
        icon.resize((px, px), Image.LANCZOS).save(os.path.join(app, name))
    plist_path = os.path.join(app, "Info.plist")
    with open(plist_path, "rb") as f:
        pl = plistlib.load(f)
    prim = {"CFBundlePrimaryIcon": {"CFBundleIconFiles": ["AppIcon60x60"]}}
    prim_ipad = {"CFBundlePrimaryIcon": {"CFBundleIconFiles": ["AppIcon76x76", "AppIcon83.5x83.5"]}}
    pl["CFBundleIcons"] = prim
    pl["CFBundleIcons~ipad"] = prim_ipad
    with open(plist_path, "wb") as f:
        plistlib.dump(pl, f, fmt=plistlib.FMT_BINARY)
    print("icon: installed AppIcon set + Info.plist keys")
except Exception as e:
    print("icon: skipped (", e, ")")
    sys.exit(0)
