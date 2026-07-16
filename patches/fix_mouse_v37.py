#!/usr/bin/env python3
"""build-37 source patches: external-mouse PC parity.

Problem (user report, build-35): with a Bluetooth mouse, wheel scrolling is
inverted, middle-click (wheel click) does not orbit, Shift+middle-click does
not pan -- while the Magic-Keyboard trackpad behaves fine.

Root causes in the iOS port:
  1. build-26 funnels EVERY pointer press through one path that always emits
     LEFT button events -- UserInputEvent has no MIDDLE/RIGHT/WHEEL types at
     all, so middle-click acted as left-click (stray box-select) and
     right-click never opened context menus.
  2. Mouse-wheel notches (discrete scrolls) were fed through the SAME
     UIPanGestureRecognizer -> GHOST trackpad-scroll mapping that is
     sign-tuned for natural trackpad scrolling, so a wheel feels inverted
     and never produces the WHEELUP/WHEELDOWN events desktop Blender's
     keymap uses for viewport zoom.

Fixes (all in GHOST_WindowIOS.mm):
  A. UserInputEvent: add MIDDLE_BUTTON_DOWN/UP, RIGHT_BUTTON_DOWN/UP and
     WHEEL_STEP event types; map them in generateUserInputEvents to
     GHOST_EventButton(GHOST_kButtonMaskMiddle/Right) and
     GHOST_EventWheel(GHOST_kEventWheelAxisVertical, steps).
     wm_event_system.cc already turns wheel value>0 into WHEELUPMOUSE and
     value<0 into WHEELDOWNMOUSE with multi-step support -- desktop parity
     for free (zoom in 3D view, Ctrl/Shift+wheel, list scrolling, ...).
  B. handlePointerPress: read UIGestureRecognizer.buttonMask (iOS 13.4+) at
     Began and route to the REAL button: primary=left, secondary=right,
     button 3 (UIEventButtonMaskForButtonNumber(3))=middle. The matching UP
     event is remembered so releases always pair with the press we sent.
     Result: LMB select/drag, MMB orbit, Shift+MMB pan, Ctrl+MMB dolly,
     RMB context menu -- identical to Blender on a PC. (Trackpad bonus:
     two-finger secondary click now opens context menus too.)
  C. Wheel: pan/pan2f recognizers now accept CONTINUOUS scrolls only, so
     trackpad two-finger scrolling keeps its current feel; a new dedicated
     GHOSTUIPanGestureRecognizer (allowedScrollTypesMask=Discrete,
     allowedTouchTypes=@[] per Apple's scroll-only guidance) turns wheel
     notches into WHEEL_STEP events. Sign: iPadOS delivers wheel translation
     in the trackpad's content-follows-fingers orientation, the opposite of
     the traditional desktop wheel mapping -- exactly the inversion the user
     hit -- hence steps = -sign(dy), i.e. wheel-away = WHEELUP = zoom in.
     ~10pt per notch; fast spins scale to multiple steps (capped at 6).
     A [b37-wheel] stderr line logs raw dy per notch so a console log
     verifies direction on real hardware immediately.

Anchors target the file as it exists AFTER fix_all_v27.py (build-31 chain);
neither v28 nor the build-36 step touches this file. Every edit asserts
exactly-once application and the script exits non-zero on any mismatch.
"""
import re
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


# --- A1: include GHOST_EventWheel ------------------------------------------
edit(W, "b37-include-wheel",
     '#include "GHOST_EventTrackpad.hh"\n',
     '#include "GHOST_EventTrackpad.hh"\n#include "GHOST_EventWheel.hh"\n')

# --- A2: extend the UserInputEvent type enum --------------------------------
edit(W, "b37-enum",
     """    LEFT_BUTTON_DOWN,
    LEFT_BUTTON_UP,
    PENCIL_TAP,
""",
     """    LEFT_BUTTON_DOWN,
    LEFT_BUTTON_UP,
    /* build-37: external-mouse PC parity. */
    MIDDLE_BUTTON_DOWN,
    MIDDLE_BUTTON_UP,
    RIGHT_BUTTON_DOWN,
    RIGHT_BUTTON_UP,
    /* Vertical mouse-wheel notches; step count rides in `distance`
     * (positive = wheel away from the user = WHEELUP = zoom in). */
    WHEEL_STEP,
    PENCIL_TAP,
""")

# --- A3: debug descriptions --------------------------------------------------
edit(W, "b37-desc",
     """      case PENCIL_TAP:
        return @"PENCIL-TAP";
""",
     """      case MIDDLE_BUTTON_DOWN:
        return @"MB-DOWN";
      case MIDDLE_BUTTON_UP:
        return @"MB-UP";
      case RIGHT_BUTTON_DOWN:
        return @"RB-DOWN";
      case RIGHT_BUTTON_UP:
        return @"RB-UP";
      case WHEEL_STEP:
        return @"WHEEL";
      case PENCIL_TAP:
        return @"PENCIL-TAP";
""")

# --- A4: generateUserInputEvents mappings -----------------------------------
edit(W, "b37-generate",
     """        case UserInputEvent::EventTypes::PINCH_GESTURE:
""",
     """        case UserInputEvent::EventTypes::MIDDLE_BUTTON_DOWN:
          system->pushEvent(
              new GHOST_EventButton(GHOST_GetMilliSeconds((GHOST_SystemHandle)system),
                                    GHOST_kEventButtonDown,
                                    window,
                                    GHOST_kButtonMaskMiddle,
                                    tablet_data));
          break;
        case UserInputEvent::EventTypes::MIDDLE_BUTTON_UP:
          system->pushEvent(
              new GHOST_EventButton(GHOST_GetMilliSeconds((GHOST_SystemHandle)system),
                                    GHOST_kEventButtonUp,
                                    window,
                                    GHOST_kButtonMaskMiddle,
                                    tablet_data));
          break;
        case UserInputEvent::EventTypes::RIGHT_BUTTON_DOWN:
          system->pushEvent(
              new GHOST_EventButton(GHOST_GetMilliSeconds((GHOST_SystemHandle)system),
                                    GHOST_kEventButtonDown,
                                    window,
                                    GHOST_kButtonMaskRight,
                                    tablet_data));
          break;
        case UserInputEvent::EventTypes::RIGHT_BUTTON_UP:
          system->pushEvent(
              new GHOST_EventButton(GHOST_GetMilliSeconds((GHOST_SystemHandle)system),
                                    GHOST_kEventButtonUp,
                                    window,
                                    GHOST_kButtonMaskRight,
                                    tablet_data));
          break;
        case UserInputEvent::EventTypes::WHEEL_STEP:
          /* build-37: real wheel event; wm_event_system maps value>0 to
           * WHEELUPMOUSE and value<0 to WHEELDOWNMOUSE with click_step. */
          system->pushEvent(
              new GHOST_EventWheel(GHOST_GetMilliSeconds((GHOST_SystemHandle)system),
                                   window,
                                   GHOST_kEventWheelAxisVertical,
                                   (int32_t)event_info.distance));
          break;
        case UserInputEvent::EventTypes::PINCH_GESTURE:
""")

# --- B1: pointer-press bookkeeping globals -----------------------------------
edit(W, "b37-globals",
     "static bool g_ios_pointer_button_down = false;\n",
     """static bool g_ios_pointer_button_down = false;
/* build-37: which mouse button the active pointer press is (0=left, 1=right,
 * 2=middle) and its matching release event, so the UP we emit always pairs
 * with the DOWN we sent even if the mask changes before release. */
static int g_ios_pointer_button_kind = 0;
static UserInputEvent::EventTypes g_ios_pointer_up_event =
    UserInputEvent::EventTypes::LEFT_BUTTON_UP;
""")

# --- B2: declare the wheel handler -------------------------------------------
edit(W, "b37-decl",
     "- (void)handlePan:(GHOSTUIPanGestureRecognizer *)sender;\n",
     "- (void)handlePan:(GHOSTUIPanGestureRecognizer *)sender;\n"
     "- (void)handleWheelScroll:(GHOSTUIPanGestureRecognizer *)sender;\n")

# --- B3: wheel recognizer ivar ------------------------------------------------
edit(W, "b37-ivar",
     """  GHOSTUIPanGestureRecognizer *pan_gesture_recognizer;
  GHOSTUIPanGestureRecognizer *pan2f_gesture_recognizer;
""",
     """  GHOSTUIPanGestureRecognizer *pan_gesture_recognizer;
  GHOSTUIPanGestureRecognizer *pan2f_gesture_recognizer;
  GHOSTUIPanGestureRecognizer *wheel_scroll_recognizer;
""")

# --- C1/C2: continuous-only masks on the trackpad pan recognizers ------------
edit(W, "b37-pan-continuous",
     """  if (@available(iOS 13.4, *)) {
    pan_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskAll;
  }
""",
     """  if (@available(iOS 13.4, *)) {
    /* build-37: CONTINUOUS scrolls only, so trackpad two-finger scrolling
     * keeps its current feel. Discrete mouse-wheel notches go to the
     * dedicated wheel recognizer and become real Blender wheel events. */
    pan_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskContinuous;
  }
""")

edit(W, "b37-pan2f-continuous",
     """  if (@available(iOS 13.4, *)) {
    pan2f_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskAll;
  }
""",
     """  if (@available(iOS 13.4, *)) {
    /* build-37: continuous only -- see pan_gesture_recognizer. */
    pan2f_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskContinuous;
  }
""")

# --- C3: register the wheel recognizer next to the pointer-press one ---------
edit(W, "b37-register-wheel",
     """    pointer_press_recognizer.cancelsTouchesInView = false;
    [window->getView() addGestureRecognizer:pointer_press_recognizer];
  }
""",
     """    pointer_press_recognizer.cancelsTouchesInView = false;
    [window->getView() addGestureRecognizer:pointer_press_recognizer];

    /* build-37: discrete scrolls = physical mouse-wheel notches. A dedicated
     * scroll-only recognizer (allowedTouchTypes = @[] per Apple's guidance)
     * turns them into real Blender WHEELUP/WHEELDOWN events: zoom in the 3D
     * viewport, line scrolling in editors, Ctrl/Shift+wheel -- exactly like
     * a PC -- while trackpad scrolling stays on the continuous path. */
    wheel_scroll_recognizer = [[GHOSTUIPanGestureRecognizer alloc]
        initWithTarget:self
                action:@selector(handleWheelScroll:)];
    wheel_scroll_recognizer.delegate = self;
    wheel_scroll_recognizer.cancelsTouchesInView = false;
    wheel_scroll_recognizer.allowedTouchTypes = @[];
    wheel_scroll_recognizer.allowedScrollTypesMask = UIScrollTypeMaskDiscrete;
    [window->getView() addGestureRecognizer:wheel_scroll_recognizer];
  }
""")

# --- B4: button-aware press handler + wheel handler ---------------------------
with open(W) as f:
    src = f.read()
pat = re.compile(
    r"- \(void\)handlePointerPress:\(UILongPressGestureRecognizer \*\)sender\n\{.*?\n\}\n\n(?=- \(void\)handleHover:)",
    re.S)
matches = pat.findall(src)
if len(matches) != 1:
    sys.stderr.write(f"FATAL b37-press-handler: handler match {len(matches)}x\n")
    sys.exit(1)

NEW_HANDLERS = r'''- (void)handlePointerPress:(UILongPressGestureRecognizer *)sender
{
  CGPoint p = [sender locationInView:window->getView()];
  p = window->scalePointToWindow(p);
  if (sender.state == UIGestureRecognizerStateBegan) {
    /* build-37: route the press to the REAL mouse button. buttonMask (iOS
     * 13.4+) reflects the event that started the gesture: primary = left,
     * secondary = right, button 3 = middle (wheel click). Priority
     * middle > right > left so a chord never degrades MMB navigation into a
     * stray select. Desktop parity: LMB select/drag, MMB orbit, Shift+MMB
     * pan, Ctrl+MMB dolly, RMB context menu. */
    UserInputEvent::EventTypes down_event = UserInputEvent::EventTypes::LEFT_BUTTON_DOWN;
    UserInputEvent::EventTypes up_event = UserInputEvent::EventTypes::LEFT_BUTTON_UP;
    g_ios_pointer_button_kind = 0;
    if (@available(iOS 13.4, *)) {
      UIEventButtonMask mask = sender.buttonMask;
      if (mask & UIEventButtonMaskForButtonNumber(3)) {
        g_ios_pointer_button_kind = 2;
      }
      else if (mask & UIEventButtonMaskSecondary) {
        g_ios_pointer_button_kind = 1;
      }
      fprintf(stderr,
              "[b37-ptr] mask=%ld kind=%d DOWN %.1f,%.1f\n",
              (long)mask,
              g_ios_pointer_button_kind,
              p.x,
              p.y);
    }
    if (g_ios_pointer_button_kind == 2) {
      down_event = UserInputEvent::EventTypes::MIDDLE_BUTTON_DOWN;
      up_event = UserInputEvent::EventTypes::MIDDLE_BUTTON_UP;
    }
    else if (g_ios_pointer_button_kind == 1) {
      down_event = UserInputEvent::EventTypes::RIGHT_BUTTON_DOWN;
      up_event = UserInputEvent::EventTypes::RIGHT_BUTTON_UP;
    }
    g_ios_pointer_up_event = up_event;
    g_ios_pointer_button_down = true;
    UserInputEvent event_info(&p, nullptr, nullptr, false);
    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
    event_info.add_event(down_event);
    [self generateUserInputEvents:event_info];
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
    if (g_ios_pointer_button_down) {
      g_ios_pointer_button_down = false;
      fprintf(stderr,
              "[b37-ptr] kind=%d UP %.1f,%.1f\n",
              g_ios_pointer_button_kind,
              p.x,
              p.y);
      UserInputEvent event_info(&p, nullptr, nullptr, false);
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      event_info.add_event(g_ios_pointer_up_event);
      [self generateUserInputEvents:event_info];
    }
  }
}

- (void)handleWheelScroll:(GHOSTUIPanGestureRecognizer *)sender
{
  /* build-37: physical mouse-wheel notches (discrete scrolls). Desktop
   * parity: wheel away from the user = WHEELUP = zoom in (3D viewport) /
   * scroll up (editors); wheel toward the user = WHEELDOWN = zoom out.
   * iPadOS delivers wheel translation in the trackpad's
   * content-follows-fingers orientation -- the OPPOSITE of the traditional
   * desktop wheel mapping (this exact mismatch made earlier builds feel
   * inverted on a mouse while the trackpad felt fine), hence the negated
   * sign below. One notch arrives as roughly 10pt of translation; fast
   * spins scale to multiple steps like a real wheel (capped at 6/event). */
  if (sender.state == UIGestureRecognizerStateBegan) {
    [sender setCachedTranslation:CGPointMake(0.0, 0.0)];
  }
  if (sender.state != UIGestureRecognizerStateBegan &&
      sender.state != UIGestureRecognizerStateChanged)
  {
    return;
  }
  CGPoint translation = [sender translationInView:window->getView()];
  CGPoint cached = [sender getCachedTranslation];
  CGFloat dy = translation.y - cached.y;
  [sender setCachedTranslation:translation];
  if (fabs(dy) < 0.01) {
    return;
  }
  int steps = (int)fmax(1.0, floor(fabs(dy) / 10.0 + 0.5));
  if (steps > 6) {
    steps = 6;
  }
  CGFloat signed_steps = (dy > 0.0) ? (CGFloat)(-steps) : (CGFloat)steps;
  CGPoint p = [sender locationInView:window->getView()];
  p = window->scalePointToWindow(p);
  fprintf(stderr, "[b37-wheel] dy=%.2f steps=%d at %.1f,%.1f\n", dy, (int)signed_steps, p.x, p.y);
  /* Cursor move first so "Zoom to Mouse Position" centres under the wheel. */
  UserInputEvent event_info(&p, nullptr, &signed_steps, false);
  event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
  event_info.add_event(UserInputEvent::EventTypes::WHEEL_STEP);
  [self generateUserInputEvents:event_info];
}

'''

src = pat.sub(lambda _m: NEW_HANDLERS, src, count=1)
with open(W, "w") as f:
    f.write(src)
applied.append("b37-press-and-wheel-handlers")
print(f"{W}: applied 'b37-press-and-wheel-handlers'")

print(f"BUILD-37 (external mouse PC parity: L/M/R buttons + real wheel) "
      f"APPLIED OK ({len(applied)} edits)")
