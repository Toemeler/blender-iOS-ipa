#!/usr/bin/env python3
"""build-44 source patch: pin GCMouse handlers to ONE window and instrument
the delta path.

Evidence from the build-43 on-device log: "[b41-gcm] mouse attached" appears
THREE times. GCMouse handlers (mouseMovedHandler, pressedChangedHandler) are
single-slot properties -- every attach OVERWRITES the previous one -- and
build-41 attached from each GHOSTUIWindow instance that ran setup, capturing
that window. So the surviving handlers belong to whichever window attached
LAST; its emitted events carry that window's handle, and Blender ignores
events for inactive/hidden windows. Middle-drag DOWN/UP (raw-touch path on
the real window) worked; the GC motion between them was either emitted into
the wrong window's stream or never fired -- the log cannot distinguish
because build-41 logged nothing per-delta.

Fix + instrumentation:
  1. A process-wide primary window pointer (g_ios_gc_window) set by the
     FIRST window that runs setup; all GC handlers route through it,
     regardless of which window's setup ran last, and re-attachment is
     harmless because the captured pointer is the same.
  2. Log lines that settle the remaining question in one glance:
       [b44-gcm] attach (primary=1|0)      - which window attached
       [b44-gcm] btn kind=K pressed=P      - GC button backup firing
       [b44-gcm] dx=.. dy=.. -> x,y EMIT   - first 3 deltas per press
       [b44-gcm] dx=.. dy=.. GATED(l/r/m)  - deltas arriving but gated

Anchors target GHOST_WindowIOS.mm as it exists AFTER fix_input_v41.py.
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


# Primary-window global next to the other pointer globals.
edit(W, "b44-primary-global",
     """static CGPoint g_ios_ptr_view_pos = {0.0, 0.0};
""",
     """static CGPoint g_ios_ptr_view_pos = {0.0, 0.0};
/* build-44: GCMouse handlers are single-slot properties; every attach
 * overwrites the last. All handlers must route into ONE window (the first
 * created = Blender's main window), or a later window's attach would
 * redirect all raw mouse input into a stream Blender ignores. */
static GHOSTUIWindow *g_ios_gc_window = nil;
""")

# Bind attach to the primary window instead of whichever self runs last.
edit(W, "b44-attach-primary",
     """  if (@available(iOS 14.0, *)) {
    /* This file compiles under MRC (manual retain/release), so no __weak:
     * capture self directly. The window outlives the app session, so the
     * resulting handler->window reference is not a leak in practice. */
    GHOSTUIWindow *handler_window = self;
""",
     """  if (@available(iOS 14.0, *)) {
    /* This file compiles under MRC (manual retain/release), so no __weak:
     * capture directly. The window outlives the app session, so the
     * resulting handler->window reference is not a leak in practice.
     * build-44: always the PRIMARY window (see g_ios_gc_window). */
    if (g_ios_gc_window == nil) {
      g_ios_gc_window = self;
    }
    fprintf(stderr, "[b44-gcm] attach request (primary=%d)\\n", g_ios_gc_window == self);
    GHOSTUIWindow *handler_window = g_ios_gc_window;
""")

# Instrument the GC button backup.
edit(W, "b44-btn-log",
     """- (void)gcButton:(int)kind pressed:(BOOL)pressed
{
  if (g_ios_ptr_kind_down[kind] == (bool)pressed) {
    return;
  }
""",
     """- (void)gcButton:(int)kind pressed:(BOOL)pressed
{
  fprintf(stderr, "[b44-gcm] btn kind=%d pressed=%d (flag=%d)\\n",
          kind, pressed ? 1 : 0, g_ios_ptr_kind_down[kind] ? 1 : 0);
  if (g_ios_ptr_kind_down[kind] == (bool)pressed) {
    return;
  }
""")

# Instrument the delta path: first few deltas per button-press window.
edit(W, "b44-delta-log",
     """- (void)gcMouseMovedDX:(float)dx dy:(float)dy
{
  if (!((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0])) {
    return;
  }
  UIView *v = window->getView();
""",
     """- (void)gcMouseMovedDX:(float)dx dy:(float)dy
{
  static int log_budget = 0;
  if (!((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0])) {
    /* One line when deltas arrive while fully idle proves the handler is
     * alive; suppress the flood. */
    static bool idle_logged = false;
    if (!idle_logged) {
      idle_logged = true;
      fprintf(stderr, "[b44-gcm] deltas flowing (handler alive), gated while no R/M button\\n");
    }
    log_budget = 3;
    return;
  }
  if (log_budget > 0) {
    log_budget--;
    fprintf(stderr, "[b44-gcm] dx=%.2f dy=%.2f -> EMIT from %.1f,%.1f\\n",
            dx, dy, g_ios_ptr_view_pos.x, g_ios_ptr_view_pos.y);
  }
  UIView *v = window->getView();
""")

print(f"BUILD-44 (GC handlers pinned to primary window + delta instrumentation) "
      f"APPLIED OK ({len(applied)} edits)")
