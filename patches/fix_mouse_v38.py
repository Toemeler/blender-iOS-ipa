#!/usr/bin/env python3
"""build-38 source patch: make middle- and right-click actually fire.

Problem (user report, build-37): wheel scrolling now works, but middle-click
(orbit) and Shift+middle-click (pan) still do nothing.

Root cause: build-37's button routing lives inside handlePointerPress:, which
is driven by ONE UILongPressGestureRecognizer. On iPadOS, tap/long-press
recognizers have a `buttonMaskRequired` property (iOS 13.4+) whose DEFAULT is
UIEventButtonMaskPrimary -- the recognizer only ever begins for LEFT-button
presses. A middle or right click never starts the gesture, so the
buttonMask-reading code in the handler is dead for those buttons. That is why
there is no [b37-ptr] stderr line at all on MMB (not a wrong kind= value --
zero output).

Why not just widen buttonMaskRequired on the existing recognizer: the mask is
a REQUIRED set -- (Primary | Secondary | Button3) would demand all three
buttons held simultaneously. The correct fix is one recognizer per button.

Fix: register two additional zero-delay UILongPressGestureRecognizers, config
identical to the primary one from build-26 (minimumPressDuration=0,
allowableMovement=CGFLOAT_MAX, indirect-pointer touches only,
cancelsTouchesInView=false), differing only in buttonMaskRequired:
  - UIEventButtonMaskSecondary            -> right click / two-finger tap
  - UIEventButtonMaskForButtonNumber(3)   -> middle click (wheel click)
Both target the existing handlePointerPress:, whose build-37 buttonMask
routing (middle > right > left) then works unchanged. A [b38-ptr] stderr line
logs registration so the console log proves the recognizers exist on-device.

Anchors target GHOST_WindowIOS.mm as it exists AFTER fix_mouse_v37.py.
Every edit asserts exactly-once application; non-zero exit on any mismatch.
"""
import sys

W = "blender/intern/ghost/intern/GHOST_WindowIOS.mm"

applied = []


def edit(path, tag, old, new, count=1):
    with open(path) as f:
        src = f.read()
    n = src.count(old)
    if n != count:
        sys.stderr.write(f"FATAL {tag}: anchor found {n}x (expected {count})\n")
        sys.exit(1)
    with open(path, "w") as f:
        f.write(src.replace(old, new, count))
    applied.append(tag)
    print(f"{path}: applied '{tag}'")


# Register the secondary/middle-button recognizers right after build-37's
# wheel recognizer, still inside the b26 @available(iOS 13.4, *) block.
edit(W, "b38-per-button-recognizers",
     """    wheel_scroll_recognizer.allowedScrollTypesMask = UIScrollTypeMaskDiscrete;
    [window->getView() addGestureRecognizer:wheel_scroll_recognizer];
  }
""",
     """    wheel_scroll_recognizer.allowedScrollTypesMask = UIScrollTypeMaskDiscrete;
    [window->getView() addGestureRecognizer:wheel_scroll_recognizer];

    /* build-38: tap/long-press recognizers only begin for buttons in
     * buttonMaskRequired, and its DEFAULT is UIEventButtonMaskPrimary -- so
     * the recognizer above never fires for middle or right clicks and
     * build-37's buttonMask routing was dead code for them. The mask is a
     * REQUIRED set (a combined mask would demand chording all buttons at
     * once), so each extra button gets its own recognizer, identically
     * configured, all funnelling into handlePointerPress: where the
     * existing middle > right > left routing takes over. */
    UILongPressGestureRecognizer *pointer_rmb_recognizer = [[UILongPressGestureRecognizer alloc]
        initWithTarget:self
                action:@selector(handlePointerPress:)];
    pointer_rmb_recognizer.minimumPressDuration = 0.0;
    pointer_rmb_recognizer.allowableMovement = CGFLOAT_MAX;
    pointer_rmb_recognizer.allowedTouchTypes = @[ @(UITouchTypeIndirectPointer) ];
    pointer_rmb_recognizer.buttonMaskRequired = UIEventButtonMaskSecondary;
    pointer_rmb_recognizer.cancelsTouchesInView = false;
    [window->getView() addGestureRecognizer:pointer_rmb_recognizer];

    UILongPressGestureRecognizer *pointer_mmb_recognizer = [[UILongPressGestureRecognizer alloc]
        initWithTarget:self
                action:@selector(handlePointerPress:)];
    pointer_mmb_recognizer.minimumPressDuration = 0.0;
    pointer_mmb_recognizer.allowableMovement = CGFLOAT_MAX;
    pointer_mmb_recognizer.allowedTouchTypes = @[ @(UITouchTypeIndirectPointer) ];
    pointer_mmb_recognizer.buttonMaskRequired = UIEventButtonMaskForButtonNumber(3);
    pointer_mmb_recognizer.cancelsTouchesInView = false;
    [window->getView() addGestureRecognizer:pointer_mmb_recognizer];

    fprintf(stderr, "[b38-ptr] per-button recognizers registered (RMB, MMB)\\n");
  }
""")

print(f"BUILD-38 (per-button press recognizers: MMB orbit / Shift+MMB pan / "
      f"RMB context menu) APPLIED OK ({len(applied)} edits)")
