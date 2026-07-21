#!/usr/bin/env python3
"""build-54: kill the counter-productive v53 recovery, capture the decisive
panel geometry that names the real dead-click cause.

WHAT THE ON-DEVICE build-53 LOG (blender_console.log) FINALLY SHOWED
-------------------------------------------------------------------
7 dead-click presses were captured. Every one is in the Properties editor
MAIN region (area=4 SPACE_PROPERTIES, region=0 RGN_TYPE_WINDOW). The nav-bar
(region=9) and header (region=1) hit-test correctly every time. For each miss:

    contains=1      -> ui_region_contains_point_px() PASSES  => NOT mechanism m1
    nblocks=5..20   -> block list is NOT empty              => NOT mechanism m2

So by the build-53 decision procedure it is **mechanism m3**, but NOT the
"corrupt winmat" form the handoff imagined -- the block->window transforms are
numerically clean (unit scale, correct +winrct offset). Two concrete faults
show up instead, and they are the whole bug:

  1. INTER-PANEL GAPS. Consecutive panel blocks do not tile the region; there
     are ~header-height (~81px) vertical gaps between them. Example
     (MISS xy=(2029,1215)): block MOD_PT_Subdivision42 ends at wrect ymax=1187
     and the next block DATA_PT_modifiers starts at wrect ymin=1268 -> the
     click at y=1215 lands in an 81px band no block owns.

  2. UNDER-POPULATED / UNSTABLE BLOCKS. The SAME panel is rebuilt with a
     varying button count: MOD_PT_Subdivision44/43/42 appear as nbuts=21/22 in
     some dumps and nbuts=9 in others; CYCLES_RENDER_PT_sampling appears with
     nbuts=0. When the block carries 9 buttons instead of 21 (but is still
     fully drawn), a press over the "missing" rows finds no button -> dead
     click INSIDE the panel body (MISS xy=(2026,1138) landed inside
     MOD_PT_Subdivision42 with nbuts=9; MISS xy=(2037,990) inside
     CYCLES_RENDER_PT_sampling with nbuts=0).

Both faults mean the hit-test block/button list is out of sync with what is
drawn. That lines up with the redraw state in the same log: 14016
`wm_window_make_drawable` and 436 Metal `Double present` warnings -- the iOS
draw loop is running continuously/re-entrantly, so ui_but_find_mouse_over()
repeatedly walks a block list that is mid-rebuild (buttons not yet added,
panels not yet positioned).

CONSEQUENCES FOR THE PATCH CHAIN
--------------------------------
* The build-53 recovery (ED_region_tag_redraw + WM_event_add_mousemove on
  every miss) cannot help -- the layout is regenerated with the SAME gaps and
  the SAME under-population, and consecutive presses at one spot keep missing.
  Worse, it schedules MORE redraws, feeding the very churn that causes the
  race. This build REMOVES it.
* The fix does NOT belong in ui_but_find_mouse_over (coordinates/transform are
  correct). It belongs in whatever lets the Properties region be hit-tested
  while its panel layout is half-built. The most likely specific culprit is
  the panel button-build visibility/culling test (a panel that is only
  partially in view being built with a truncated button set), keyed off the
  View2D scroll rect vs each panel's ofsy/sizey.

WHAT THIS BUILD CAPTURES (so the one-line fix can be written next)
-----------------------------------------------------------------
On a miss, in addition to the existing [b53-hit] block dump, print the scroll
state and, per block, the owning panel's offset/size, the click transformed
into that block's space, and whether the block rect contains it:

    [b54-geo] v2d cur=(..) tot=(..)
    [b54-geo]   'MOD_PT_Subdivision42' open ofsy=.. sizey=.. nbuts=9 \
                clickblk=(x,y) in_block=0/1

Read it: if under-populated blocks (nbuts far below the drawn control count)
are exactly the panels whose ofsy/sizey put them partly outside v2d.cur, the
culling test is the bug and the fix is to build buttons for any panel that
INTERSECTS the view, not only those fully inside it. If instead in_block=1 with
a full nbuts yet still no `over`, the miss is button-level and the next probe
moves down to per-uiBut rects.

Anchor: the recovery block that fix_input_v53.py inserted (must run AFTER v53).

NOTE: if CI fails to compile on the `PNL_CLOSED` symbol on this branch, replace
the flag read with `(b54_b->panel->flag & 1)` or drop the panel= field; the
ofsy/sizey/nbuts/in_block data is what matters.
"""
import sys

U = "blender/source/blender/editors/interface/interface_handlers.cc"

OLD = """        /* Recovery: rebuild this region's layout (block list + winmat are both
         * re-created in the layout/draw pass) and queue a mouse-move so hover
         * re-activates whatever is now under the cursor. */
        ED_region_tag_redraw(region);
        wmWindow *b53_win = CTX_wm_window(C);
        if (b53_win) {
          WM_event_add_mousemove(b53_win);
        }
        fprintf(stderr, "[b53-hit]   recovery: tagged region for rebuild + synthetic mousemove\\n");
"""

NEW = """        /* build-54: the v53 redraw-recovery is removed. On device the click
         * kept missing after it, because the layout is regenerated with the
         * same inter-panel gaps and the same under-populated blocks (the SAME
         * panel rebuilt with 21 buttons then 9); tagging another redraw only
         * adds churn (this session: 14016 make_drawable, 436 Metal double
         * present). Capture instead the data that ties the miss to the panel
         * visibility/cull test: the View2D scroll rect, and per block the
         * owning panel's ofsy/sizey plus the click in block space. */
        View2D *b54_v2d = &region->v2d;
        fprintf(stderr,
                "[b54-geo] v2d cur=(%.0f,%.0f,%.0f,%.0f) tot=(%.0f,%.0f,%.0f,%.0f)\\n",
                double(b54_v2d->cur.xmin), double(b54_v2d->cur.ymin),
                double(b54_v2d->cur.xmax), double(b54_v2d->cur.ymax),
                double(b54_v2d->tot.xmin), double(b54_v2d->tot.ymin),
                double(b54_v2d->tot.xmax), double(b54_v2d->tot.ymax));
        int b54_i = 0;
        LISTBASE_FOREACH (uiBlock *, b54_b, &region->runtime->uiblocks) {
          if (b54_i >= 12) {
            break;
          }
          float b54_bx = float(event->xy[0]);
          float b54_by = float(event->xy[1]);
          ui_window_to_block_fl(region, b54_b, &b54_bx, &b54_by);
          const bool b54_in = BLI_rctf_isect_pt(&b54_b->rect, b54_bx, b54_by);
          const char *b54_pf = "no-panel";
          double b54_ofsy = 0.0;
          double b54_sizey = 0.0;
          if (b54_b->panel) {
            b54_ofsy = double(b54_b->panel->ofsy);
            b54_sizey = double(b54_b->panel->sizey);
            b54_pf = (b54_b->panel->flag & PNL_CLOSED) ? "CLOSED" : "open";
          }
          fprintf(stderr,
                  "[b54-geo]   '%s' %s ofsy=%.0f sizey=%.0f nbuts=%d "
                  "clickblk=(%.0f,%.0f) in_block=%d\\n",
                  b54_b->name.c_str(),
                  b54_pf,
                  b54_ofsy,
                  b54_sizey,
                  int(b54_b->buttons.size()),
                  double(b54_bx),
                  double(b54_by),
                  int(b54_in));
          b54_i++;
        }
"""

with open(U) as f:
    src = f.read()
n = src.count(OLD)
if n != 1:
    sys.stderr.write(f"FATAL b54-geo: anchor found {n}x (expected 1); run this AFTER fix_input_v53.py\n")
    sys.exit(1)
with open(U, "w") as f:
    f.write(src.replace(OLD, NEW, 1))
print(f"{U}: applied 'b54-geo' (removed v53 redraw-recovery, added panel-cull probe)")
print("BUILD-54 (panel geometry probe; recovery reverted) APPLIED OK (1 edit)")
