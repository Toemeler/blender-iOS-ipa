#!/usr/bin/env python3
"""build-46 source patch: make middle/right drags actually move the viewport,
based on two defects PROVEN by the build-45 on-device log.

Defect 1 -- phantom LEFT presses. The log shows middle presses like:
    [b39-ptr] kind=0 DOWN 2261.1,597.2      <- LEFT ?!
    [b44-gcm] btn kind=2 pressed=1
    [b39-ptr] kind=2 DOWN 2261.1,597.2
    ...
    [b39-ptr] kind=2 UP  / kind=0 UP
On this iPadOS version the zero-delay long-press recognizer BEGINS for
non-primary buttons too (the opposite of the build-37-era behavior where it
never fired for them). build-39's handler assumed Began == left, so every
such middle press also delivered a LEFT+MIDDLE chord to Blender -- wrecking
the orbit operator -- and set the left flag, which closed the
"right/middle-without-left" gate on all GC motion.

Defect 2 -- main-queue starvation. On presses without the phantom left, GC
deltas EMIT exactly a few times right at press, then fall silent until
release, while the raw UP coordinates prove hundreds of points of travel.
GCMouse handlers default to the MAIN queue; while a touch is held, UIKit
runs the main run loop in UITrackingRunLoopMode, starving default-mode
main-queue blocks. The deltas flush only at release -- after MIDDLE_UP --
when the orbit modal is already gone.

Fixes:
  1. Gate the recognizer's Began on sender.buttonMask (a UIGestureRecognizer
     base property, compile-proven in build-37): only emit LEFT when the
     primary bit is actually set (mask 0 treated as primary for OS versions
     that do not populate it). Non-primary Begans are merely tracked.
  2. Turn that tracking into the PRIMARY middle/right motion source: the
     recognizer's Changed callbacks fire fine in tracking mode (that is how
     left drags already work), so route them through the deduping funnel as
     absolute positions. This also re-bases the GC integration position
     every frame, killing drift.
  3. Starvation-proof the GC backup: give GCMouse a dedicated background
     handlerQueue where deltas only accumulate into atomics, and drain them
     on the main thread from a CADisplayLink scheduled in
     NSRunLoopCommonModes -- which runs during tracking. Order of paths at
     release (raw touchesEnded clears the flags before queued deltas could
     emit) means stale deltas are dropped, not replayed.

Anchors target GHOST_WindowIOS.mm as it exists AFTER fix_input_v44.py.
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


# <atomic> for the cross-thread delta accumulator.
edit(W, "b46-include-atomic",
     "#import <UIKit/UIKit.h>\n",
     "#import <UIKit/UIKit.h>\n"
     "#include <atomic> /* build-46: GC delta accumulator */\n")

# Accumulator globals.
edit(W, "b46-accum-globals",
     "static GHOSTUIWindow *g_ios_gc_window = nil;\n",
     """static GHOSTUIWindow *g_ios_gc_window = nil;
/* build-46: GCMouse deltas accumulate here (micro-units, from a dedicated
 * background handlerQueue) and are drained on the main thread by a
 * CADisplayLink in NSRunLoopCommonModes -- the main queue itself is starved
 * in UITrackingRunLoopMode while a button is held, which is why build-44's
 * main-queue delivery only flushed after release. */
static std::atomic<long long> g_ios_gc_dx_mu(0);
static std::atomic<long long> g_ios_gc_dy_mu(0);
""")

# Declaration for the display-link tick.
edit(W, "b46-decl",
     "- (void)gcMouseMovedDX:(float)dx dy:(float)dy;\n",
     "- (void)gcMouseMovedDX:(float)dx dy:(float)dy;\n"
     "- (void)gcDisplayTick:(CADisplayLink *)link;\n")

# Display link, created once by the primary window.
edit(W, "b46-displaylink",
     """    if (g_ios_gc_window == nil) {
      g_ios_gc_window = self;
    }
""",
     """    if (g_ios_gc_window == nil) {
      g_ios_gc_window = self;
      /* build-46: drains the GC delta accumulator; common modes so it also
       * fires while UIKit tracks a held button. */
      CADisplayLink *gc_link = [CADisplayLink displayLinkWithTarget:self
                                                           selector:@selector(gcDisplayTick:)];
      [gc_link addToRunLoop:[NSRunLoop mainRunLoop] forMode:NSRunLoopCommonModes];
    }
""")

# Dedicated background handler queue for the mouse.
edit(W, "b46-handler-queue",
     """      GCMouseInput *mi = mouse.mouseInput;
      if (!mi) {
        return;
      }
""",
     """      GCMouseInput *mi = mouse.mouseInput;
      if (!mi) {
        return;
      }
      /* build-46: never the main queue -- it is starved in tracking mode
       * exactly when the deltas matter (button held). */
      static dispatch_queue_t gc_queue = NULL;
      if (gc_queue == NULL) {
        gc_queue = dispatch_queue_create("ghost.gcmouse", DISPATCH_QUEUE_SERIAL);
      }
      mouse.handlerQueue = gc_queue;
""")

# Moved handler: accumulate only (runs on the background queue).
edit(W, "b46-accumulate",
     """      mi.mouseMovedHandler = ^(GCMouseInput *mouse_input, float delta_x, float delta_y) {
        [handler_window gcMouseMovedDX:delta_x dy:delta_y];
      };
""",
     """      mi.mouseMovedHandler = ^(GCMouseInput *mouse_input, float delta_x, float delta_y) {
        /* build-46: background queue -- accumulate only; the display link
         * emits on the main thread. */
        g_ios_gc_dx_mu.fetch_add((long long)llroundf(delta_x * 1000.0f));
        g_ios_gc_dy_mu.fetch_add((long long)llroundf(delta_y * 1000.0f));
      };
""")

# The drain tick (inserted before gcMouseMovedDX, which stays the emitter).
edit(W, "b46-tick",
     "- (void)gcMouseMovedDX:(float)dx dy:(float)dy\n{\n",
     """- (void)gcDisplayTick:(CADisplayLink *)link
{
  long long dx_mu = g_ios_gc_dx_mu.exchange(0);
  long long dy_mu = g_ios_gc_dy_mu.exchange(0);
  if (dx_mu == 0 && dy_mu == 0) {
    return;
  }
  [self gcMouseMovedDX:(float)(dx_mu / 1000.0) dy:(float)(dy_mu / 1000.0)];
}

- (void)gcMouseMovedDX:(float)dx dy:(float)dy
{
""")

# Phantom-LEFT gate on the recognizer's Began.
edit(W, "b46-mask-gate",
     """  if (sender.state == UIGestureRecognizerStateBegan) {
    if (!g_ios_ptr_kind_down[0]) {
      [self emitPointerButton:0 down:YES at:p];
    }
  }
""",
     """  if (sender.state == UIGestureRecognizerStateBegan) {
    /* build-46: on this iPadOS version the recognizer begins for NON-primary
     * buttons too (build-45 log: every middle press also produced a LEFT
     * pair, wrecking orbit and gating the GC deltas). Only emit LEFT when
     * the primary button is actually in the mask; a zero mask is treated as
     * primary for OS versions that do not populate it. Non-primary Begans
     * are tracked silently -- their Changed states below become the motion
     * source for middle/right drags. */
    bool primary = true;
    if (@available(iOS 13.4, *)) {
      UIEventButtonMask mask = sender.buttonMask;
      if (mask != 0 && (mask & UIEventButtonMaskPrimary) == 0) {
        primary = false;
      }
    }
    if (primary) {
      if (!g_ios_ptr_kind_down[0]) {
        [self emitPointerButton:0 down:YES at:p];
      }
    }
    else {
      fprintf(stderr, "[b46-ptr] non-primary press: tracked, no LEFT emitted\\n");
    }
  }
""")

# Changed -> absolute position through the deduping funnel (also re-bases the
# GC integration position, so the two sources cannot diverge).
edit(W, "b46-changed-funnel",
     """  else if (sender.state == UIGestureRecognizerStateChanged) {
    UserInputEvent event_info(&p, nullptr, nullptr, false);
    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
    [self generateUserInputEvents:event_info];
  }
""",
     """  else if (sender.state == UIGestureRecognizerStateChanged) {
    /* build-46: genuine motion of whichever button this touch holds --
     * during middle/right drags these callbacks (which run fine in tracking
     * mode, unlike main-queue GC delivery) are the primary motion source.
     * Funnel-deduped, absolute, and re-bases the GC delta integration. */
    [self emitScaledPointerMoveFromViewPoint:[sender locationInView:window->getView()]];
  }
""")

print(f"BUILD-46 (phantom-LEFT mask gate + recognizer-Changed motion for M/R "
      f"drags + starvation-proof GC delta drain) APPLIED OK ({len(applied)} edits)")
