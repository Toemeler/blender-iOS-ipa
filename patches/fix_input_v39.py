#!/usr/bin/env python3
"""build-39 source patches: external-keyboard numpad, mouse-vs-stylus hover,
per-button press pairing (fixes stuck clicks + RMB drag-cancel), and a
fail-safe, diagnosable Spectral Wave Optics registration.

User reports on build-37/38, with the on-device logs to match:

  1. Numpad shortcuts dead. blender_input.log shows keypad keys arriving as
     HID usages 84-99 with mods=0x200000 (UIKeyModifierNumericPad) and being
     mapped through the CHARACTER fallback -> main-row digit keys (ghost=49
     for keypad-1 etc.), while keypad +/-/NumLock map to ghost=-1 (Unknown).
     Blender's keymap binds viewport views to GHOST_kKeyNumpad*, so nothing
     fired. Fix: map every keypad HID usage to its GHOST numpad key.

  2. Eyedropper flaky, number fields sometimes refuse to edit, clicks
     ("Add Modifier") dying after a while. Two compounding causes:
       a) The stock handleHover: sets tablet_data.Active =
          GHOST_kTabletModeStylus on EVERY hover -- mouse included -- and it
          stays set until the pointer leaves the view. Every subsequent
          mouse click and move is therefore delivered to Blender as a PEN
          event with absolute tablet motion. Fix: restrict that recognizer
          to Apple Pencil and add a mouse hover recognizer that emits plain
          cursor moves without touching tablet_data.
       b) build-37/38 tracked the pressed button in a single global slot
          shared by all three press recognizers. A chord (e.g. RMB pressed
          while LMB held) overwrote the stored release event, so one button
          UP was emitted with the wrong mask and the other was lost --
          Blender was left with a permanently-held button and stopped
          reacting to clicks. Fix: derive the button from the recognizer's
          own immutable buttonMaskRequired and keep a per-button down flag,
          so DOWN/UP always pair per button.

  3. Right-click must cancel a slider drag like on a PC. The stock
     simultaneous-recognition delegate returns NO for everything except
     pan<->zoom, and the press recognizers had no delegate at all -- so a
     secondary-button press could not even BEGIN while the primary press
     gesture was active. Fix: give the press recognizers the window as
     delegate and allow simultaneous recognition whenever a long-press
     (button) recognizer is involved. With (2b), RMB during an LMB slider
     drag now delivers RIGHTMOUSE press -> Blender's own drag-cancel runs,
     and the later releases pair correctly.

  4. Spectral Wave Optics engine invisible, with ZERO "[spectral]" output in
     blender_console.log -- even though the IPA verifiably contains
     scripts/startup/spectral_wave_engine.py, scripts/modules/
     spectral_engine.py AND numpy. Python's stdout/stderr are block-buffered
     on iOS (the build-19 freopen redirect only unbuffers the C FILE*), so
     every Python print -- including a registration traceback -- is lost
     when the app is killed. Fixes:
       a) creator.cc: setenv("PYTHONUNBUFFERED", "1", 1) before Python ever
          initializes, so ALL Python output reaches blender_console.log.
       b) Rewrite the startup wrapper to log every step (import, register,
          failure tracebacks) both to stdout and to a direct, unbuffered
          Documents/spectral_startup.log file.
       c) If the physics module import OR its register() fails, register a
          minimal fallback engine under the same 'SPECTRAL_WAVE' id whose
          Render Properties panel shows the error -- the engine now ALWAYS
          appears next to Cycles/EEVEE and any failure becomes visible and
          reportable instead of silent.

Anchors target the sources as they exist AFTER fix_mouse_v38.py (and after
fix_all_v27/v28 + the build-36 script writer). Every edit asserts
exactly-once application; the script exits non-zero on any mismatch.
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
# (2a) Hover: pencil keeps the stylus path; the mouse gets a plain one
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
# (2b + 3) Per-button press pairing, driven by buttonMaskRequired
# =========================================================================
# Replace the shared single-slot globals from build-37 with per-button flags.
edit(W, "b39-globals",
     """/* build-37: which mouse button the active pointer press is (0=left, 1=right,
 * 2=middle) and its matching release event, so the UP we emit always pairs
 * with the DOWN we sent even if the mask changes before release. */
static int g_ios_pointer_button_kind = 0;
static UserInputEvent::EventTypes g_ios_pointer_up_event =
    UserInputEvent::EventTypes::LEFT_BUTTON_UP;
""",
     """/* build-39: per-button held flags (0=left, 1=right, 2=middle). Each press
 * recognizer serves exactly one button (its buttonMaskRequired), so DOWN/UP
 * always pair per button even during chords like RMB-cancel of an LMB drag.
 * build-37's single shared slot lost one UP in that case, leaving Blender
 * with a permanently-held button that ate all further clicks. */
static bool g_ios_ptr_kind_down[3] = {false, false, false};
""")

# Give all three press recognizers the window as delegate so the delegate
# method below can allow them to run simultaneously (RMB while LMB held).
edit(W, "b39-lmb-delegate",
     "    pointer_press_recognizer.cancelsTouchesInView = false;\n",
     "    pointer_press_recognizer.cancelsTouchesInView = false;\n"
     "    pointer_press_recognizer.delegate = self;\n")
edit(W, "b39-rmb-delegate",
     "    pointer_rmb_recognizer.cancelsTouchesInView = false;\n",
     "    pointer_rmb_recognizer.cancelsTouchesInView = false;\n"
     "    pointer_rmb_recognizer.delegate = self;\n")
edit(W, "b39-mmb-delegate",
     "    pointer_mmb_recognizer.cancelsTouchesInView = false;\n",
     "    pointer_mmb_recognizer.cancelsTouchesInView = false;\n"
     "    pointer_mmb_recognizer.delegate = self;\n")

# Allow simultaneous recognition whenever a button (long-press) recognizer is
# involved: chords, and press-during-pan, must not block each other.
edit(W, "b39-simultaneous",
     """  if (gestureRecognizer == pan_gesture_recognizer &&
      otherGestureRecognizer == zoom_gesture_recognizer)
  {
    return YES;
  }
  return NO;
}
""",
     """  if (gestureRecognizer == pan_gesture_recognizer &&
      otherGestureRecognizer == zoom_gesture_recognizer)
  {
    return YES;
  }
  /* build-39: pointer button (zero-delay long-press) recognizers must be able
   * to recognize alongside everything - especially each other - so e.g. a
   * right-click can begin while a left-drag is active and cancel it exactly
   * like on a PC. */
  if ([gestureRecognizer isKindOfClass:[UILongPressGestureRecognizer class]] ||
      [otherGestureRecognizer isKindOfClass:[UILongPressGestureRecognizer class]])
  {
    return YES;
  }
  return NO;
}
""")

# Rewrite handlePointerPress: kind from buttonMaskRequired + per-kind flags.
with open(W) as f:
    src = f.read()
pat = re.compile(
    r"- \(void\)handlePointerPress:\(UILongPressGestureRecognizer \*\)sender\n\{.*?\n\}\n\n(?=- \(void\)handleWheelScroll:)",
    re.S)
matches = pat.findall(src)
if len(matches) != 1:
    sys.stderr.write(f"FATAL b39-press-handler: handler match {len(matches)}x\n")
    sys.exit(1)

NEW_PRESS = r'''- (void)handlePointerPress:(UILongPressGestureRecognizer *)sender
{
  /* build-39: the button is a fixed property of the recognizer itself
   * (buttonMaskRequired, set at registration: primary=left, secondary=right,
   * button-3=middle), not of the volatile per-event buttonMask. Each button
   * keeps its own held flag, so DOWN/UP always pair per button and chords
   * (e.g. RMB pressed to cancel an LMB slider drag, releases in any order)
   * can no longer lose a release and wedge Blender's button state. */
  CGPoint p = [sender locationInView:window->getView()];
  p = window->scalePointToWindow(p);
  int kind = 0;
  if (@available(iOS 13.4, *)) {
    UIEventButtonMask req = sender.buttonMaskRequired;
    if (req & UIEventButtonMaskForButtonNumber(3)) {
      kind = 2;
    }
    else if (req & UIEventButtonMaskSecondary) {
      kind = 1;
    }
  }
  static const UserInputEvent::EventTypes k_downs[3] = {
      UserInputEvent::EventTypes::LEFT_BUTTON_DOWN,
      UserInputEvent::EventTypes::RIGHT_BUTTON_DOWN,
      UserInputEvent::EventTypes::MIDDLE_BUTTON_DOWN};
  static const UserInputEvent::EventTypes k_ups[3] = {
      UserInputEvent::EventTypes::LEFT_BUTTON_UP,
      UserInputEvent::EventTypes::RIGHT_BUTTON_UP,
      UserInputEvent::EventTypes::MIDDLE_BUTTON_UP};
  if (sender.state == UIGestureRecognizerStateBegan) {
    if (!g_ios_ptr_kind_down[kind]) {
      g_ios_ptr_kind_down[kind] = true;
      g_ios_pointer_button_down = true;
      fprintf(stderr, "[b39-ptr] kind=%d DOWN %.1f,%.1f\n", kind, p.x, p.y);
      UserInputEvent event_info(&p, nullptr, nullptr, false);
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      event_info.add_event(k_downs[kind]);
      [self generateUserInputEvents:event_info];
    }
  }
  else if (sender.state == UIGestureRecognizerStateChanged) {
    /* All recognizers of held buttons receive Changed; only the lowest held
     * kind forwards cursor moves so chords do not duplicate motion events. */
    int lowest = g_ios_ptr_kind_down[0] ? 0 : (g_ios_ptr_kind_down[1] ? 1 : 2);
    if (kind == lowest) {
      UserInputEvent event_info(&p, nullptr, nullptr, false);
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      [self generateUserInputEvents:event_info];
    }
  }
  else if (sender.state == UIGestureRecognizerStateEnded ||
           sender.state == UIGestureRecognizerStateCancelled ||
           sender.state == UIGestureRecognizerStateFailed)
  {
    if (g_ios_ptr_kind_down[kind]) {
      g_ios_ptr_kind_down[kind] = false;
      g_ios_pointer_button_down = g_ios_ptr_kind_down[0] || g_ios_ptr_kind_down[1] ||
                                  g_ios_ptr_kind_down[2];
      fprintf(stderr, "[b39-ptr] kind=%d UP %.1f,%.1f\n", kind, p.x, p.y);
      UserInputEvent event_info(&p, nullptr, nullptr, false);
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      event_info.add_event(k_ups[kind]);
      [self generateUserInputEvents:event_info];
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

print(f"BUILD-39 (numpad + mouse/stylus hover split + per-button pairing + "
      f"RMB drag-cancel + diagnosable spectral engine) APPLIED OK "
      f"({len(applied)} edits)")
