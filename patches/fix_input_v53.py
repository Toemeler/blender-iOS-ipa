#!/usr/bin/env python3
"""build-53: decisive probe + self-healing for dead clicks in UI regions.

WHAT THE BUILD-52 DIAGNOSTIC ESTABLISHED (two sessions, same signature):
Clicks in the Properties editor work until the Add Modifier search popup has
been used; afterwards a press in the main region reports

    [b52-ui] LMB PRESS at (2851,1285) region=0 active_but=none over_but=none

i.e. `ui_but_find_mouse_over()` finds NOTHING where the user visibly clicks a
button, while the nav-bar region keeps hit-testing fine. Draw activity
continued (39 make_drawable between the tab click and the dead click), so
blocks were rebuilt -- and the hit test still misses. This rules out the
build-52 hypotheses (stale active button; missing hover activation) and leaves
exactly three data-side mechanisms in `ui_but_find_mouse_over_ex`:

  (m1) `ui_region_contains_point_px()` rejects the point -- possible only via
       the View2D mask/scroller test, since the event was dispatched by winrct;
  (m2) `region->runtime->uiblocks` is empty -- layout freed blocks and never
       rebuilt them;
  (m3) blocks exist but `block->winmat` maps the click outside every button --
       the matrix snapshot was taken under a wrong viewport (the popup's?).

The build-52 line cannot distinguish these. This build makes any such press
self-explanatory AND recovers from it:

  [b53-ui] LMB PRESS at (x,y) region=R active=... over=... moves=N
  [b53-hit] MISS xy=(x,y) area=S region=R winrct=(..) contains=0/1
            mask=(..) local=(x,y) nblocks=K
  [b53-hit]   block[i] act=1 nbuts=37 'panel_name' brect=(..) wrect=(..)
  [b53-hit]   recovery: tagged region for rebuild + synthetic mousemove

Reading it: contains=0 with a sane mask -> (m1) and the mask values show why;
nblocks=0 -> (m2); blocks whose wrect does not contain the click although the
user sees the button there -> (m3), and brect-vs-wrect shows the transform.
`moves` counts MOUSEMOVEs this region handler has seen, so hover starvation is
visible too.

RECOVERY: on a miss-press the region is tagged for a full redraw (layout pass
rebuilds the block list and re-captures winmat) and a synthetic mouse-move is
queued so hover re-activates under the cursor. If the broken state is
rebuildable, the user loses exactly one click instead of the whole panel; if it
is not, the next dump says so (same state twice). The 3D viewport is untouched
by this: its main region has no ui_region_handler (confirmed: no b52-ui lines
for any viewport click in the logs), so empty-space viewport clicks cannot
trigger spurious redraws. Dumps are capped at 40/session.

Anchor targets the b52 diagnostic block exactly as fix_input_v52.py wrote it.
"""
import sys

U = "blender/source/blender/editors/interface/interface_handlers.cc"

OLD = """  /* build-52 DIAGNOSTIC: why does a click sometimes not reach a button?
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
"""

NEW = """  /* build-53 DIAGNOSTIC + RECOVERY (supersedes build-52): a press that lands
   * on no button in a region that handles UI is either a legitimate gap click
   * or the post-popup dead-panel state seen on device. Log enough to tell the
   * three possible mechanisms apart (v2d-mask reject / empty block list /
   * corrupt block->winmat), then rebuild the region so at most one click is
   * lost. The 3D viewport has no ui_region_handler, so this cannot cause
   * spurious viewport redraws. */
  {
    static int b53_moves = 0;
    static int b53_dumps = 0;
    if (event->type == MOUSEMOVE) {
      b53_moves++;
    }
    if (ELEM(event->type, LEFTMOUSE, MIDDLEMOUSE, RIGHTMOUSE) &&
        ELEM(event->val, KM_PRESS, KM_RELEASE))
    {
      const uiBut *over = ui_but_find_mouse_over(region, event);
      fprintf(stderr,
              "[b53-ui] %s %s at (%d,%d) region=%d active=%s over=%s moves=%d\\n",
              (event->type == LEFTMOUSE) ? "LMB" :
                                           ((event->type == MIDDLEMOUSE) ? "MMB" : "RMB"),
              (event->val == KM_PRESS) ? "PRESS" : "RELEASE",
              event->xy[0],
              event->xy[1],
              int(region->regiontype),
              but ? (but->drawstr.empty() ? "<unnamed>" : but->drawstr.c_str()) : "none",
              over ? (over->drawstr.empty() ? "<unnamed>" : over->drawstr.c_str()) : "none",
              b53_moves);

      if (over == nullptr && event->val == KM_PRESS && b53_dumps < 40) {
        b53_dumps++;
        ScrArea *b53_area = CTX_wm_area(C);
        const bool contains = ui_region_contains_point_px(region, event->xy);
        int nblocks = 0;
        LISTBASE_FOREACH (uiBlock *, b, &region->runtime->uiblocks) {
          (void)b;
          nblocks++;
        }
        fprintf(stderr,
                "[b53-hit] MISS xy=(%d,%d) area=%d region=%d "
                "winrct=(%d,%d,%d,%d) contains=%d mask=(%d,%d,%d,%d) "
                "local=(%d,%d) nblocks=%d\\n",
                event->xy[0],
                event->xy[1],
                b53_area ? int(b53_area->spacetype) : -1,
                int(region->regiontype),
                region->winrct.xmin,
                region->winrct.ymin,
                region->winrct.xmax,
                region->winrct.ymax,
                int(contains),
                region->v2d.mask.xmin,
                region->v2d.mask.ymin,
                region->v2d.mask.xmax,
                region->v2d.mask.ymax,
                event->xy[0] - region->winrct.xmin,
                event->xy[1] - region->winrct.ymin,
                nblocks);
        int shown = 0;
        LISTBASE_FOREACH (uiBlock *, b, &region->runtime->uiblocks) {
          if (shown++ >= 12) {
            fprintf(stderr, "[b53-hit]   (+%d more blocks)\\n", nblocks - 12);
            break;
          }
          rctf wrect;
          ui_block_to_window_rctf(region, b, &wrect, &b->rect);
          fprintf(stderr,
                  "[b53-hit]   block[%d] act=%d nbuts=%d '%s' "
                  "brect=(%.0f,%.0f,%.0f,%.0f) wrect=(%.0f,%.0f,%.0f,%.0f)\\n",
                  shown - 1,
                  int(b->active),
                  int(b->buttons.size()),
                  b->name.c_str(),
                  double(b->rect.xmin),
                  double(b->rect.ymin),
                  double(b->rect.xmax),
                  double(b->rect.ymax),
                  double(wrect.xmin),
                  double(wrect.ymin),
                  double(wrect.xmax),
                  double(wrect.ymax));
        }
        /* Recovery: rebuild this region's layout (block list + winmat are both
         * re-created in the layout/draw pass) and queue a mouse-move so hover
         * re-activates whatever is now under the cursor. */
        ED_region_tag_redraw(region);
        wmWindow *b53_win = CTX_wm_window(C);
        if (b53_win) {
          WM_event_add_mousemove(b53_win);
        }
        fprintf(stderr, "[b53-hit]   recovery: tagged region for rebuild + synthetic mousemove\\n");
      }
    }
  }
"""

with open(U) as f:
    src = f.read()
n = src.count(OLD)
if n != 1:
    sys.stderr.write(f"FATAL b53-hit-diag: anchor found {n}x (expected 1)\n")
    sys.exit(1)
with open(U, "w") as f:
    f.write(src.replace(OLD, NEW, 1))
print(f"{U}: applied 'b53-hit-diag'")
print("BUILD-53 (decisive hit-test probe + region self-heal) APPLIED OK (1 edit)")
