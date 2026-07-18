#!/usr/bin/env python3
"""build-48 DIAGNOSTIC patch: turn on Blender's own event/handler tracing.

State of evidence after build-47: the input pipeline is verifiably correct up
to the GHOST boundary. The on-device log shows clean middle presses (no more
phantom LEFT pairs), GC deltas EMITting in real time DURING the drag
(starvation fixed), and correct GHOST_EventButton(GHOST_kButtonMaskMiddle)
generation (code-audited). Blender receives MIDDLE_DOWN + live CURSOR_MOVEs +
MIDDLE_UP -- and the viewport still does not orbit. The failure is therefore
INSIDE Blender's WM layer: event conversion, keymap matching, or operator
dispatch. wm_eventemulation was audited and only maps Alt+LMB -> MMB; it
never consumes real MIDDLEMOUSE.

Rather than guess further, this build enables the tracing Blender already
ships for exactly this purpose (the --debug-events / --debug-handlers
machinery, which cannot be passed as argv on iOS): G_DEBUG_EVENTS prints
every wmEvent as typed names (MIDDLEMOUSE, MOUSEMOVE, xy, modifiers) and
G_DEBUG_HANDLERS prints keymap/handler matching decisions. Everything lands
in blender_console.log via the build-19 redirect + build-39 unbuffering.

The next on-device log will show one of exactly three signatures:
  a) no MIDDLEMOUSE lines at all      -> GHOST->WM conversion drops it;
  b) MIDDLEMOUSE with no handler hit  -> keymap/prefs problem (binding,
     emulation flags, active tool);
  c) handler fires an operator        -> operator-level problem (and the
     name tells us which one ran instead of view3d.rotate).

Applies to source/creator/creator.cc AFTER fix_all_v27 (which provides the
b19 anchor context nearby but does not touch these lines).
"""
import sys

C = "blender/source/creator/creator.cc"

OLD = """#  ifdef WITH_APPLE_CROSSPLATFORM
    /* iOS Main loop handled differently. */
    WM_main_entry(C);
    GHOST_iosfinalize(C);
#  else
    WM_main(C);
#  endif
"""

NEW = """#  ifdef WITH_APPLE_CROSSPLATFORM
    /* build-48 DIAGNOSTIC: trace every wm event and handler decision to the
     * console log (equivalent to --debug-events --debug-handlers, which
     * cannot be passed as argv on iOS). Temporary; remove once the
     * middle-mouse dispatch question is answered. */
    G.debug |= G_DEBUG_EVENTS | G_DEBUG_HANDLERS;
    fprintf(stderr, "[b48-diag] WM event/handler tracing ENABLED\\n");
    /* iOS Main loop handled differently. */
    WM_main_entry(C);
    GHOST_iosfinalize(C);
#  else
    WM_main(C);
#  endif
"""

with open(C) as f:
    src = f.read()
n = src.count(OLD)
if n != 1:
    sys.stderr.write(f"FATAL b48: anchor found {n}x (expected 1)\n")
    sys.exit(1)
if "BKE_global.hh" not in src:
    sys.stderr.write("FATAL b48: BKE_global.hh not included in creator.cc\n")
    sys.exit(1)
with open(C, "w") as f:
    f.write(src.replace(OLD, NEW, 1))
print(f"{C}: applied b48-diag (G_DEBUG_EVENTS | G_DEBUG_HANDLERS at startup)")
print("BUILD-48 (WM event/handler tracing) APPLIED OK")
