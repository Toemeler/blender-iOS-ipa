#!/usr/bin/env python3
"""build-57: THE dead-click fix -- the invisible keyboard-proxy UITextField
swallows clicks after the first popup search.

WHAT BUILD-56'S DIAGNOSTICS PROVED (session 2026-07-21 12:00)
-------------------------------------------------------------
With the raw-driven left button in place, every click that reaches the app
now delivers exactly one DOWN/UP ([b56-raw] mask=1 -> [b39-ptr] DOWN -> UP;
the value field cleanly stepped 1 -> 2 -> 3, one increment per click -- the
build-56 echo fix works). The remaining dead click on Add Modifier produced
NO log line of any kind: no [b56-raw] touch, no [b56-rec] recognizer state,
nothing -- while hover kept flowing (the final TIMER event shows the pointer
parked at (2989,1295), right over Add Modifier). iPadOS delivered the press
to SOMETHING ELSE.

THE CULPRIT (all in GHOST_WindowIOS.mm, upstream ios-branch code)
-----------------------------------------------------------------
initUITextField creates the soft-keyboard input proxy:
  * transparent (clear background/tint, no border)  -> invisible
  * userInteractionEnabled never set                -> defaults to YES
  * added to window->rootWindow                     -> ABOVE the MTKView in
                                                       hit-testing, in a
                                                       different subtree
popupOnscreenKeyboard runs setupKeyboard FIRST, which sets
  text_field.frame = <the Blender text box being edited>
(i.e. the popup's search field), and only THEN branches on
external_keyboard_connected. The hardware-keyboard branch (build-15) clears
the text and logs "KBD: hardware keyboard present ..." -- but leaves the
field's frame in place, leaves interaction enabled, and never sets
onscreen_keyboard_active. hideOnscreenKeyboard wraps its ENTIRE cleanup --
including 'text_field.userInteractionEnabled = NO' -- in
'if (onscreen_keyboard_active)', so on the hardware path nothing runs.

Net effect: after the first popup search with a hardware keyboard, an
invisible interaction-enabled UITextField stays parked over the search-field
rectangle forever. Every later click in that band hit-tests to it and is
consumed before our view's recognizers or the window's touches overrides can
see it. That band covers the Add Modifier button and the render-engine
dropdown -- exactly the reported dead clicks -- while the nav-bar and the
modifier value fields sit outside it and kept working. It also explains why
the FIRST Add Modifier click of every session works: the field has not been
positioned yet.

THE FIX (2 edits)
-----------------
 1. Create the proxy field inert: userInteractionEnabled = NO at creation.
    The soft-keyboard path already re-enables it explicitly right before
    becomeFirstResponder, so the on-screen keyboard flow is unchanged.
 2. In the hardware-keyboard branch of popupOnscreenKeyboard, park the field:
    disable interaction and zero its frame (setupKeyboard re-positions it on
    every popup, so this cannot starve a later soft-keyboard session). Log
    the parking so the console shows it happened.

With a hardware keyboard the field is a pure string buffer -- keystrokes
arrive via pressesBegan on the window (build-15) -- so neither edit can
affect text entry.

Runs after fix_input_v56.py. Anchors verified unique (1x) against the full
locally replayed patch chain on pinned blender commit d9b6fe34.
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


# --- 1. create the proxy field inert ----------------------------------------
edit(W, "b57-inert-create",
     """    text_field.tintColor = [UIColor clearColor];
    text_field.borderStyle = UITextBorderStyleNone;
    text_field.backgroundColor = [UIColor clearColor];
""",
     """    text_field.tintColor = [UIColor clearColor];
    text_field.borderStyle = UITextBorderStyleNone;
    text_field.backgroundColor = [UIColor clearColor];
    /* build-57: the field lives in the ROOT window, above the Metal view in
     * hit-testing, and is fully transparent. UIView defaults interaction to
     * YES, so once setupKeyboard parks it over an edited text box it silently
     * swallows every later click in that rectangle (the "dead" Add Modifier
     * button / render-engine dropdown after the first popup search). Create
     * it inert; the soft-keyboard path re-enables it explicitly. */
    text_field.userInteractionEnabled = NO;
""")

# --- 2. hardware-keyboard path: park the field ------------------------------
edit(W, "b57-hw-park",
     """    if (external_keyboard_connected) {
      text_field.text = nil;
      text_field_string = nullptr;
      ghost_ios_log(@"KBD: hardware keyboard present -> editing in place (on-screen field suppressed)");
    }
""",
     """    if (external_keyboard_connected) {
      text_field.text = nil;
      text_field_string = nullptr;
      /* build-57: setupKeyboard (just above) placed the invisible proxy over
       * the edited text box, and hideOnscreenKeyboard's cleanup is gated on
       * onscreen_keyboard_active, which this path never sets -- so the field
       * would stay there, interaction-enabled, eating every later click in
       * its rect. Park it: no interaction, no frame. setupKeyboard restores
       * the frame on the next popup, so the soft-keyboard flow is unharmed. */
      text_field.userInteractionEnabled = NO;
      text_field.frame = CGRectZero;
      ghost_ios_log(@"KBD: hardware keyboard present -> editing in place (on-screen field suppressed)");
      ghost_ios_log(@"[b57-kbd] proxy field parked (interaction off, frame zero)");
    }
""")

print(f"BUILD-57 (invisible keyboard-proxy field no longer swallows clicks "
      f"after popup search) APPLIED OK ({len(applied)} edits)")
