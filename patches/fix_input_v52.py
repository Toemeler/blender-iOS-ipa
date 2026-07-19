#!/usr/bin/env python3
"""build-52: kill the phantom middle click, and instrument the UI click path.

--- FIX (b52-mmb-echo-guard) -------------------------------------------------
Proven by the build-51 console log. After a long middle drag the log shows:

    [b44-gcm] btn kind=2 pressed=0 (flag=1)
    [b50-mmb] drag end (travel 3890.1)
    [b50-mmb] press (trackpad emulation armed)     <-- nobody touched the mouse
    [b50-mmb] click (travel 0.0)

...on 3 of 6 drags, and Blender duly logged a MIDDLEMOUSE PRESS/RELEASE pair
for each. Cause: two independent sources drive the middle button. The GCMouse
handler (build-41/44) reports the release first and clears
g_ios_ptr_kind_down[2]; a raw UIKit touch event still carrying button 3 in its
`event.buttonMask` then reaches syncPointerButtons, sees the flag disagree, and
re-presses the button. The following touchesEnded releases it, and build-50's
zero-travel click path turns that into a real middle click.

Harmless before build-51 (the gate swallowed it), not harmless now: MIDDLEMOUSE
press invokes view3d.rotate/view3d.move for real, and both carry
OPTYPE_BLOCKING | OPTYPE_GRAB_CURSOR_XY, so every long drag ended by briefly
entering a blocking modal operator with a cursor grab.

Guard rising edges on the middle button inside build-50's intercept: a physical
button cannot be released and pressed again inside 150 ms, so an echo that
close is dropped. Only the middle button is touched; the right button and the
GCMouse path are untouched. Dropping the press leaves g_ios_mmb_active and
g_ios_mmb_click_pending false, so the echoed release logs a zero-travel drag end
and emits nothing.

--- DIAGNOSTIC (b52-ui-click-diag) -------------------------------------------
"Add Modifier works once, then stops" is a UI click-routing failure, and the
build-48 trace structurally cannot see it: Blender excludes MOUSEMOVE from
--debug-handlers, and ui_region_handler prints nothing at all.

What the log does establish: 14 of 15 left clicks had their PRESS consumed
before any region keymap was checked -- the normal path, since the UI handler
sits at the head of region->handlers. The failing click at (2206,709) is the
only one whose PRESS ran the full cascade (Screen Editing -> User Interface ->
Frames -> View2D Buttons List -> Property Editor), i.e. ui_region_handler
returned WM_UI_HANDLER_CONTINUE and no button took it.

From interface_handlers.cc there are exactly two ways that happens:

  (a) ui_handle_button_over() ran but found no button -- it only activates on
      event->type == MOUSEMOVE, so a press that arrives without a MOUSEMOVE
      having been delivered over the button first can never activate it; or
  (b) a STALE active button exists in that region, so ui_region_handler calls
      ui_handle_button_event() on it instead of ui_handle_button_over(), and
      that button ignores a press aimed elsewhere.

(b) matches "worked once, then never again" and matches the note in
fix_input_v39.py about wedged clicks. This patch logs which one it is: for every
mouse button press/release reaching ui_region_handler it prints the region type,
the active button (the suspected stale one) and the button under the cursor.
One session with this build settles it.

Anchors target the sources as they exist AFTER fix_input_v51.py.
"""
import sys

W = "blender/intern/ghost/intern/GHOST_WindowIOS.mm"
U = "blender/source/blender/editors/interface/interface_handlers.cc"

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


# --- 1. drop the stale buttonMask echo that re-presses the middle button -----
edit(W, "b52-mmb-echo-guard",
     """  if (kind == 2) {
    /* build-50: trackpad emulation owns the middle button. */
    if (down) {
      g_ios_mmb_active = true;
""",
     """  if (kind == 2) {
    /* build-50: trackpad emulation owns the middle button. */
    if (down) {
      /* build-52: the GCMouse path clears this button on release, then a raw
       * UIKit touch whose event.buttonMask still carries button 3 reaches
       * syncPointerButtons and re-presses it -- a phantom middle click at the
       * end of a drag. No physical button bounces inside 150 ms, so drop it.
       * g_ios_mmb_active / g_ios_mmb_click_pending stay false, so the echoed
       * release below reports a zero-travel drag end and emits nothing. */
      const uint64_t now_ms = GHOST_GetMilliSeconds((GHOST_SystemHandle)system);
      if (g_ios_mmb_release_ms != 0 && (now_ms - g_ios_mmb_release_ms) < 150) {
        fprintf(stderr, "[b52-mmb] dropped buttonMask echo (%llu ms after release)\\n",
                (unsigned long long)(now_ms - g_ios_mmb_release_ms));
        return;
      }
      g_ios_mmb_active = true;
""")

# The release side has to stamp the timestamp the guard reads.
edit(W, "b52-mmb-release-stamp",
     """    g_ios_mmb_active = false;
""",
     """    g_ios_mmb_active = false;
    g_ios_mmb_release_ms = GHOST_GetMilliSeconds((GHOST_SystemHandle)system);
""")

# Declare the timestamp next to the other build-50 middle-button globals.
edit(W, "b52-mmb-global",
     "static bool g_ios_mmb_click_pending = false;\n",
     "static bool g_ios_mmb_click_pending = false;\n"
     "static uint64_t g_ios_mmb_release_ms = 0; /* build-52: buttonMask echo guard */\n")

# --- 2. make the UI click decision visible ----------------------------------
edit(U, "b52-ui-click-diag",
     """  /* either handle events for already activated button or try to activate */
  uiBut *but = ui_region_find_active_but(region);
  uiBut *listbox = ui_list_find_mouse_over(region, event);
""",
     """  /* either handle events for already activated button or try to activate */
  uiBut *but = ui_region_find_active_but(region);
  uiBut *listbox = ui_list_find_mouse_over(region, event);

  /* build-52 DIAGNOSTIC: why does a click sometimes not reach a button?
   * ui_handle_button_over() only activates on MOUSEMOVE, and it is skipped
   * entirely while any button in this region is still active -- either failure
   * lets the press fall through to the region keymaps. Print both. */
  if (ELEM(event->type, LEFTMOUSE, MIDDLEMOUSE, RIGHTMOUSE) &&
      ELEM(event->val, KM_PRESS, KM_RELEASE))
  {
    const uiBut *over = ui_but_find_mouse_over(region, event);
    fprintf(stderr,
            "[b52-ui] %s %s at (%d,%d) region=%d active_but=%s over_but=%s\\n",
            (event->type == LEFTMOUSE) ? "LMB" :
                                         ((event->type == MIDDLEMOUSE) ? "MMB" : "RMB"),
            (event->val == KM_PRESS) ? "PRESS" : "RELEASE",
            event->xy[0],
            event->xy[1],
            int(region->regiontype),
            but ? (but->drawstr.empty() ? "<unnamed>" : but->drawstr.c_str()) : "none",
            over ? (over->drawstr.empty() ? "<unnamed>" : over->drawstr.c_str()) : "none");
  }
""")

print(f"BUILD-52 (middle-click echo guard + UI click-routing diagnostic) "
      f"APPLIED OK ({len(applied)} edits)")
