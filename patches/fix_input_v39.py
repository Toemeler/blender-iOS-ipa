#!/usr/bin/env python3
"""build-39 source patches (supersedes the never-compiled build-38):
external-keyboard numpad, mouse-vs-stylus hover, middle/right mouse buttons
via the raw touch stream, RMB drag-cancel, and a fail-safe, diagnosable
Spectral Wave Optics registration.

Why build-38 failed (CI run 29565413557): it set `buttonMaskRequired` on
UILongPressGestureRecognizer, but that property only exists on
UITapGestureRecognizer -- 2 compile errors, no IPA. Lesson applied here:
non-primary buttons are tracked WITHOUT any gesture-recognizer button API,
using only `UIEvent.buttonMask` (iOS 13.4, on the UIEvent delivered to the
raw touchesBegan/Moved/Ended overrides -- the same overrides whose
"[b26-ptr] raw indirect touch began" lines prove in the on-device log that
middle/right presses DO arrive there). `sender.buttonMask` in build-37
compiled fine (UIGestureRecognizer base property), confirming the mask APIs
exist; only the long-press *gate* property does not.

User reports on build-37, with the on-device logs to match:

  1. Numpad shortcuts dead. blender_input.log shows keypad keys arriving as
     HID usages 84-99 with mods=0x200000 (UIKeyModifierNumericPad) and being
     mapped through the CHARACTER fallback -> main-row digit keys, while
     keypad +/- map to ghost=-1 (Unknown). Blender's keymap binds viewport
     views to GHOST_kKeyNumpad*, so nothing fired. Fix: map every keypad HID
     usage to its GHOST numpad key.

  2. Middle click (orbit) / Shift+middle (pan) dead. The single long-press
     recognizer only ever begins for the PRIMARY button (every [b37-ptr]
     line in the log is mask=1; MMB produced none). Fix: LEFT stays on the
     proven long-press path; RIGHT/MIDDLE state is diffed from
     UIEvent.buttonMask in the raw touch overrides, emitting proper
     DOWN/UP/CURSOR_MOVE streams. Raw touches keep flowing during recognizer
     drags (every recognizer here has cancelsTouchesInView = false), so
     chords work too: RMB pressed during an LMB slider drag delivers
     RIGHTMOUSE press -> Blender's own drag-cancel runs, exactly like a PC.
     Per-button held flags keep DOWN/UP paired in any release order, so no
     button can get stuck and wedge clicks (the "Add Modifier stopped
     working" failure).

  3. Eyedropper flaky, number fields sometimes refusing to edit: the stock
     handleHover sets tablet_data.Active = GHOST_kTabletModeStylus on EVERY
     hover -- mouse included -- and it stays set until the pointer leaves
     the view, so all mouse clicks/moves were delivered to Blender as PEN
     events with absolute tablet motion. Fix: restrict that recognizer to
     the Apple Pencil; the mouse gets its own plain-motion hover recognizer
     that never touches tablet_data.

  4. Spectral Wave Optics engine invisible with ZERO "[spectral]" output --
     even though the build-37 IPA verifiably contains both scripts AND
     numpy. Python's stdout/stderr are block-buffered on iOS (the build-19
     freopen only unbuffers the C FILE*), so every Python print -- including
     a registration traceback -- was lost when the app was killed. Fixes:
     setenv("PYTHONUNBUFFERED", "1", 1) before the interpreter initializes;
     rewrite the startup wrapper to also log each step directly to
     Documents/spectral_startup.log; and on ANY import/register failure,
     register a fallback engine under the same 'SPECTRAL_WAVE' id whose
     Render Properties panel shows the error -- the engine now always
     appears next to Cycles/EEVEE and failures become visible instead of
     silent.

Anchors target the sources as they exist AFTER fix_mouse_v37.py (build-38's
step is removed from the workflow). Every edit asserts exactly-once (or an
explicitly stated count); the script exits non-zero on any mismatch.
"""
import os
import re
import sys

W = "blender/intern/ghost/intern/GHOST_WindowIOS.mm"
C = "blender/source/creator/creator.cc"
WRAPPER = "blender/scripts/startup/spectral_wave_engine.py"

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


# =========================================================================
# (1) Numpad: keypad HID usages -> GHOST numpad keys
# =========================================================================
edit(W, "b39-numpad-map",
     "    case UIKeyboardHIDUsageKeypadEnter: return GHOST_kKeyEnter;\n",
     """    /* build-39: keypad HID usages -> GHOST numpad keys. These previously fell
     * through to the character fallback (main-row digits) or Unknown, so no
     * NUMPAD_* keymap entry (viewport views, numpad enter, +/-) ever fired. */
    case UIKeyboardHIDUsageKeypadEnter: return GHOST_kKeyNumpadEnter;
    case UIKeyboardHIDUsageKeypad0: return GHOST_kKeyNumpad0;
    case UIKeyboardHIDUsageKeypad1: return GHOST_kKeyNumpad1;
    case UIKeyboardHIDUsageKeypad2: return GHOST_kKeyNumpad2;
    case UIKeyboardHIDUsageKeypad3: return GHOST_kKeyNumpad3;
    case UIKeyboardHIDUsageKeypad4: return GHOST_kKeyNumpad4;
    case UIKeyboardHIDUsageKeypad5: return GHOST_kKeyNumpad5;
    case UIKeyboardHIDUsageKeypad6: return GHOST_kKeyNumpad6;
    case UIKeyboardHIDUsageKeypad7: return GHOST_kKeyNumpad7;
    case UIKeyboardHIDUsageKeypad8: return GHOST_kKeyNumpad8;
    case UIKeyboardHIDUsageKeypad9: return GHOST_kKeyNumpad9;
    case UIKeyboardHIDUsageKeypadPeriod: return GHOST_kKeyNumpadPeriod;
    case UIKeyboardHIDUsageKeypadPlus: return GHOST_kKeyNumpadPlus;
    case UIKeyboardHIDUsageKeypadHyphen: return GHOST_kKeyNumpadMinus;
    case UIKeyboardHIDUsageKeypadAsterisk: return GHOST_kKeyNumpadAsterisk;
    case UIKeyboardHIDUsageKeypadSlash: return GHOST_kKeyNumpadSlash;
""")

# =========================================================================
# (3) Hover: pencil keeps the stylus path; the mouse gets a plain one
# =========================================================================
edit(W, "b39-hover-split",
     """  hover_gesture_recognizer.delegate = self;
  [window->getView() addGestureRecognizer:hover_gesture_recognizer];
""",
     """  hover_gesture_recognizer.delegate = self;
  /* build-39: handleHover marks tablet_data as an ACTIVE STYLUS and leaves it
   * set until the pointer exits the view, so with a mouse EVERY subsequent
   * click and cursor move was delivered to Blender as a pen event (absolute
   * tablet motion + pen pressure) - breaking eyedropper sampling, number
   * field editing and assorted clicks. Keep the stylus path for the Pencil
   * only; the indirect pointer gets its own plain-motion recognizer below. */
  hover_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil) ];
  [window->getView() addGestureRecognizer:hover_gesture_recognizer];

  if (@available(iOS 13.4, *)) {
    UIHoverGestureRecognizer *mouse_hover_recognizer = [[UIHoverGestureRecognizer alloc]
        initWithTarget:self
                action:@selector(handleMouseHover:)];
    mouse_hover_recognizer.delegate = self;
    mouse_hover_recognizer.allowedTouchTypes = @[ @(UITouchTypeIndirectPointer) ];
    [window->getView() addGestureRecognizer:mouse_hover_recognizer];
  }
""")

# =========================================================================
# (2) Per-button state + right/middle from the raw touch stream
# =========================================================================
# Replace build-37's shared single-slot globals with per-button held flags.
edit(W, "b39-globals",
     """/* build-37: which mouse button the active pointer press is (0=left, 1=right,
 * 2=middle) and its matching release event, so the UP we emit always pairs
 * with the DOWN we sent even if the mask changes before release. */
static int g_ios_pointer_button_kind = 0;
static UserInputEvent::EventTypes g_ios_pointer_up_event =
    UserInputEvent::EventTypes::LEFT_BUTTON_UP;
""",
     """/* build-39: per-button held flags (0=left, 1=right, 2=middle). Left is
 * driven by the long-press recognizer (which only ever begins for the
 * primary button); right/middle are diffed from UIEvent.buttonMask in the
 * raw touch overrides. Per-button pairing means no chord or release order
 * can lose an UP and wedge Blender with a stuck button. */
static bool g_ios_ptr_kind_down[3] = {false, false, false};
""")

# Raw touchesBegan: track right/middle from the event's button mask.
edit(W, "b39-raw-began",
     """  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      g_ios_pointer_touch = touch;
      fprintf(stderr, "[b26-ptr] raw indirect touch began\\n");
      break;
    }
  }
}
""",
     """  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      g_ios_pointer_touch = touch;
      /* build-39: right/middle buttons never begin the primary-button-only
       * long-press recognizer; their state is tracked from the raw event's
       * buttonMask instead. */
      [self syncPointerButtons:event touch:touch];
      break;
    }
  }
}
""")

# Raw touchesMoved: keep the mask in sync (catches chords mid-drag) and emit
# cursor moves for right/middle-only drags (orbit / pan), which have no
# recognizer feeding them.
edit(W, "b39-raw-moved",
     "  /* build-26: pointer drag cursor-moves are emitted by handlePointerPress (Changed). */\n}\n",
     """  /* build-26: LEFT drag cursor-moves are emitted by handlePointerPress
   * (Changed). build-39: right/middle drags never begin that recognizer, so
   * their button state and cursor moves are driven from the raw stream. */
  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      [self syncPointerButtons:event touch:touch];
      if ((g_ios_ptr_kind_down[1] || g_ios_ptr_kind_down[2]) && !g_ios_ptr_kind_down[0]) {
        CGPoint p = [touch locationInView:window->getView()];
        p = window->scalePointToWindow(p);
        UserInputEvent event_info(&p, nullptr, nullptr, false);
        event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
        [self generateUserInputEvents:event_info];
      }
      break;
    }
  }
}
""")

# Raw touchesEnded + touchesCancelled (identical text, count=2): force-release
# any held right/middle buttons when the pointer touch sequence ends.
edit(W, "b39-raw-ended",
     """  if (g_ios_pointer_touch && [touches containsObject:g_ios_pointer_touch]) {
    g_ios_pointer_touch = nil;
  }
""",
     """  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      [self releasePointerButtons:touch];
      break;
    }
  }
  if (g_ios_pointer_touch && [touches containsObject:g_ios_pointer_touch]) {
    g_ios_pointer_touch = nil;
  }
""", count=2)

# New helper methods + left-only press handler. Replace the whole build-37
# handler (bounded by the wheel handler that follows it).
with open(W) as f:
    src = f.read()
pat = re.compile(
    r"- \(void\)handlePointerPress:\(UILongPressGestureRecognizer \*\)sender\n\{.*?\n\}\n\n(?=- \(void\)handleWheelScroll:)",
    re.S)
matches = pat.findall(src)
if len(matches) != 1:
    sys.stderr.write(f"FATAL b39-press-handler: handler match {len(matches)}x\n")
    sys.exit(1)

NEW_PRESS = r'''/* build-39: shared emitter for mouse button transitions. kind: 0=left,
 * 1=right, 2=middle. Updates the per-button flags and the pan-gate flag,
 * then delivers CURSOR_MOVE + the button event at the given point. */
- (void)emitPointerButton:(int)kind down:(BOOL)down at:(CGPoint)p
{
  static const UserInputEvent::EventTypes k_downs[3] = {
      UserInputEvent::EventTypes::LEFT_BUTTON_DOWN,
      UserInputEvent::EventTypes::RIGHT_BUTTON_DOWN,
      UserInputEvent::EventTypes::MIDDLE_BUTTON_DOWN};
  static const UserInputEvent::EventTypes k_ups[3] = {
      UserInputEvent::EventTypes::LEFT_BUTTON_UP,
      UserInputEvent::EventTypes::RIGHT_BUTTON_UP,
      UserInputEvent::EventTypes::MIDDLE_BUTTON_UP};
  g_ios_ptr_kind_down[kind] = down ? true : false;
  g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                              g_ios_ptr_kind_down[2];
  fprintf(stderr, "[b39-ptr] kind=%d %s %.1f,%.1f\n", kind, down ? "DOWN" : "UP", p.x, p.y);
  UserInputEvent event_info(&p, nullptr, nullptr, false);
  event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
  event_info.add_event(down ? k_downs[kind] : k_ups[kind]);
  [self generateUserInputEvents:event_info];
}

/* build-39: diff right/middle button state from the live UIEvent.buttonMask
 * of the raw indirect-pointer touch stream. The long-press recognizer only
 * ever begins for the PRIMARY button (its tap-family gate property is not
 * exposed on long-press -- build-38's attempt to set it did not compile),
 * but the raw event mask carries every button. */
- (void)syncPointerButtons:(UIEvent *)event touch:(UITouch *)touch
{
  if (@available(iOS 13.4, *)) {
    CGPoint p = [touch locationInView:window->getView()];
    p = window->scalePointToWindow(p);
    UIEventButtonMask mask = event.buttonMask;
    bool right = (mask & UIEventButtonMaskSecondary) != 0;
    bool middle = (mask & UIEventButtonMaskForButtonNumber(3)) != 0;
    if (right != g_ios_ptr_kind_down[1]) {
      [self emitPointerButton:1 down:(right ? YES : NO) at:p];
    }
    if (middle != g_ios_ptr_kind_down[2]) {
      [self emitPointerButton:2 down:(middle ? YES : NO) at:p];
    }
  }
}

/* build-39: the pointer touch sequence ended/cancelled - release any held
 * right/middle button so Blender's button state can never wedge. */
- (void)releasePointerButtons:(UITouch *)touch
{
  CGPoint p = [touch locationInView:window->getView()];
  p = window->scalePointToWindow(p);
  for (int kind = 1; kind <= 2; kind++) {
    if (g_ios_ptr_kind_down[kind]) {
      [self emitPointerButton:kind down:NO at:p];
    }
  }
}

- (void)handlePointerPress:(UILongPressGestureRecognizer *)sender
{
  /* build-39: this recognizer only ever begins for the PRIMARY button, so it
   * is the LEFT-button path (down / drag-moves / up). Right/middle are
   * driven from the raw touch stream (syncPointerButtons). Per-button flags
   * keep DOWN/UP paired even during chords like RMB-cancel of an LMB drag. */
  CGPoint p = [sender locationInView:window->getView()];
  p = window->scalePointToWindow(p);
  if (sender.state == UIGestureRecognizerStateBegan) {
    if (!g_ios_ptr_kind_down[0]) {
      [self emitPointerButton:0 down:YES at:p];
    }
  }
  else if (sender.state == UIGestureRecognizerStateChanged) {
    UserInputEvent event_info(&p, nullptr, nullptr, false);
    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
    [self generateUserInputEvents:event_info];
  }
  else if (sender.state == UIGestureRecognizerStateEnded ||
           sender.state == UIGestureRecognizerStateCancelled ||
           sender.state == UIGestureRecognizerStateFailed)
  {
    if (g_ios_ptr_kind_down[0]) {
      [self emitPointerButton:0 down:NO at:p];
    }
  }
}

'''
src = pat.sub(lambda _m: NEW_PRESS, src, count=1)
with open(W, "w") as f:
    f.write(src)
applied.append("b39-press-handler")
print(f"{W}: applied 'b39-press-handler'")

# Plain-motion mouse hover handler, inserted just before the pencil one.
edit(W, "b39-mouse-hover-handler",
     "- (void)handleHover:(GHOSTUIHoverGestureRecognizer *)sender\n{\n",
     """- (void)handleMouseHover:(UIHoverGestureRecognizer *)sender
{
  /* build-39: mouse/trackpad hover = plain cursor motion. Must NOT touch
   * tablet_data (see registration comment): faking an active stylus here is
   * what corrupted every subsequent mouse click into a pen event. */
  if (sender.state == UIGestureRecognizerStateBegan ||
      sender.state == UIGestureRecognizerStateChanged)
  {
    CGPoint p = [sender locationInView:window->getView()];
    p = window->scalePointToWindow(p);
    UserInputEvent event_info(&p, nullptr, nullptr, false);
    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
    [self generateUserInputEvents:event_info];
  }
}

- (void)handleHover:(GHOSTUIHoverGestureRecognizer *)sender
{
""")

# =========================================================================
# (4a) Unbuffered Python so registration output reaches the console log
# =========================================================================
edit(C, "b39-python-unbuffered",
     '        fprintf(stderr, "[blender-ios] build-19 console log started\\n");\n',
     '        fprintf(stderr, "[blender-ios] build-19 console log started\\n");\n'
     '        /* build-39: Python\'s own stdout/stderr are BLOCK-buffered when not a\n'
     '         * tty; every print() from startup scripts (including registration\n'
     '         * tracebacks) was lost when the app was killed. Must be set before\n'
     '         * the interpreter initializes. */\n'
     '        setenv("PYTHONUNBUFFERED", "1", 1);\n')

# =========================================================================
# (4b/4c) Fail-safe, diagnosable startup wrapper for the spectral engine
# =========================================================================
WRAPPER_SRC = '''"""Auto-registration for the Spectral Wave Optics render engine (build-39).

Lives in scripts/startup/, so Blender imports it and calls register() at
every launch. build-36's wrapper was silent on failure (and Python output
was block-buffered on iOS anyway), so a registration problem produced NO
trace and NO engine. This version:

  * logs every step to stdout AND directly to Documents/spectral_startup.log
    (opened per line, so it survives the app being killed);
  * catches failures of both the physics-module import and register();
  * on any failure registers a minimal fallback engine under the same
    'SPECTRAL_WAVE' id whose Render Properties panel shows the error --
    the engine ALWAYS appears next to Cycles/EEVEE, and failures become
    visible instead of silent.
"""

import os
import traceback


def _slog(msg):
    line = "[spectral] " + msg
    print(line, flush=True)
    try:
        home = os.environ.get("HOME")
        if home:
            docs = os.path.join(home, "Documents")
            if os.path.isdir(docs):
                with open(os.path.join(docs, "spectral_startup.log"), "a") as f:
                    f.write(line + "\\n")
    except Exception:
        pass


_slog("startup wrapper imported")

_impl = None
_IMPORT_TB = None
try:
    import spectral_engine as _impl
    _slog("physics module imported (numpy OK)")
except Exception:
    _IMPORT_TB = traceback.format_exc()


def _register_fallback(error_text):
    import bpy

    short = [ln for ln in error_text.strip().splitlines() if ln.strip()][-4:]

    class SPECTRAL_WAVE_fallback_engine(bpy.types.RenderEngine):
        bl_idname = "SPECTRAL_WAVE"
        bl_label = "Spectral Wave Optics (load error)"
        bl_use_preview = False

        def render(self, depsgraph):
            self.report({'ERROR'},
                        "Spectral engine failed to load - see "
                        "Documents/spectral_startup.log")
            print("[spectral] stored failure:\\n" + error_text, flush=True)

    class RENDER_PT_spectral_error(bpy.types.Panel):
        bl_idname = "RENDER_PT_spectral_error"
        bl_label = "Spectral Wave Optics - load error"
        bl_space_type = 'PROPERTIES'
        bl_region_type = 'WINDOW'
        bl_context = "render"
        COMPAT_ENGINES = {'SPECTRAL_WAVE'}

        @classmethod
        def poll(cls, context):
            return context.engine == 'SPECTRAL_WAVE'

        def draw(self, context):
            col = self.layout.column()
            col.label(text="Engine failed to load.", icon='ERROR')
            col.label(text="Full trace: Documents/spectral_startup.log")
            for ln in short:
                col.label(text=ln.strip()[:64])

    bpy.utils.register_class(SPECTRAL_WAVE_fallback_engine)
    bpy.utils.register_class(RENDER_PT_spectral_error)


def register():
    if _impl is None:
        _slog("physics module import FAILED:\\n" + (_IMPORT_TB or "?"))
        try:
            _register_fallback(_IMPORT_TB or "unknown import error")
            _slog("fallback engine registered (visible, non-rendering)")
        except Exception:
            _slog("fallback registration FAILED:\\n" + traceback.format_exc())
        return
    try:
        _impl.register()
        _slog("Spectral Wave Optics registered OK "
              "(Render Properties > Render Engine)")
    except Exception:
        tb = traceback.format_exc()
        _slog("register() FAILED:\\n" + tb)
        try:
            _register_fallback(tb)
            _slog("fallback engine registered after register() failure")
        except Exception:
            _slog("fallback registration FAILED:\\n" + traceback.format_exc())


def unregister():
    try:
        if _impl is not None:
            _impl.unregister()
    except Exception:
        pass
'''

if not os.path.exists(WRAPPER):
    sys.stderr.write(f"FATAL b39-wrapper: {WRAPPER} missing (build-36 step must run first)\n")
    sys.exit(1)
import ast
ast.parse(WRAPPER_SRC)
with open(WRAPPER, "w") as f:
    f.write(WRAPPER_SRC)
applied.append("b39-wrapper")
print(f"{WRAPPER}: rewritten (fail-safe, {len(WRAPPER_SRC)} bytes)")

print(f"BUILD-39 (numpad + raw-touch M/R buttons + RMB drag-cancel + "
      f"mouse/stylus hover split + diagnosable spectral engine) APPLIED OK "
      f"({len(applied)} edits)")
