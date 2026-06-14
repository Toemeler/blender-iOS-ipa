#!/usr/bin/env python3
"""build-13 source patches for the Blender ios branch.
- Proper hardware keyboard via pressesBegan/UIKey (layout-aware; fixes QWERTZ Y/Z; delivers Cmd).
- Trackpad pinch-zoom using gesture .scale (handleZoom previously bailed on <2 touches).
- Keeps: wm->runtime fix, crash-handler-off, trackpad tap/pan indirect + scroll, zoom touch-types.
Self-verifying: aborts if any anchor does not match exactly once."""
import sys

def edit(path, replacements):
    s = open(path).read()
    for old, new, tag in replacements:
        if new and new in s and old not in s:
            print(f"{path}: '{tag}' already applied"); continue
        n = s.count(old)
        if n != 1:
            sys.stderr.write(f"FATAL {path}: anchor '{tag}' found {n} times (need 1)\n"); sys.exit(1)
        s = s.replace(old, new, 1)
        print(f"{path}: applied '{tag}'")
    open(path, "w").write(s)

# ---------- wm_add_default: allocate wm->runtime before use ----------
WM = "blender/source/blender/windowmanager/intern/wm.cc"
alloc = "  wm->runtime = MEM_new<blender::bke::WindowManagerRuntime>(__func__);\n"
edit(WM, [
 ("  BKE_reports_init(&wm->runtime->reports, RPT_STORE);\n",
  alloc + "  BKE_reports_init(&wm->runtime->reports, RPT_STORE);\n", "wm-runtime-alloc"),
 ("  wm->file_saved = 1;\n" + alloc + "  wm_window_make_drawable(wm, win);\n",
  "  wm->file_saved = 1;\n  wm_window_make_drawable(wm, win);\n", "wm-runtime-dedup"),
])

# ---------- creator.cc: disable Blender crash handler ----------
edit("blender/source/creator/creator.cc", [
 ("  app_state.signal.use_crash_handler = true;\n  app_state.signal.use_abort_handler = true;\n",
  "  app_state.signal.use_crash_handler = false;\n  app_state.signal.use_abort_handler = false;\n",
  "crash-handler-off"),
])

W = "blender/intern/ghost/intern/GHOST_WindowIOS.mm"

# ---------- helpers: logging (C-string path) + UIKey->GHOST mapping ----------
helpers = r'''#include <unordered_map>

/* ==== build-13 ADDED: iOS input log + layout-aware hardware keyboard mapping ==== */
static void ghost_ios_log(NSString *msg)
{
  static const char *log_path_c = NULL;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    NSArray *dirs = NSSearchPathForDirectoriesInDomains(
        NSDocumentDirectory, NSUserDomainMask, YES);
    if (dirs.count) {
      NSString *p = [[dirs firstObject] stringByAppendingPathComponent:@"blender_input.log"];
      const char *fsr = p.fileSystemRepresentation;
      if (fsr) {
        log_path_c = strdup(fsr);
      }
    }
  });
  if (!log_path_c || !msg) {
    return;
  }
  FILE *f = fopen(log_path_c, "a");
  if (f) {
    const char *c = msg.UTF8String;
    if (c) {
      fwrite(c, 1, strlen(c), f);
      fwrite("\n", 1, 1, f);
    }
    fclose(f);
  }
}

/* Map a UIKey to a GHOST key. Special keys use the (positional) HID usage; printable
 * keys use charactersIgnoringModifiers so the user's keyboard LAYOUT is respected
 * (this is what fixes the German QWERTZ Y/Z swap). */
static GHOST_TKey ghost_key_from_uikey(UIKey *key)
{
  switch (key.keyCode) {
    case UIKeyboardHIDUsageKeyboardLeftShift: return GHOST_kKeyLeftShift;
    case UIKeyboardHIDUsageKeyboardRightShift: return GHOST_kKeyRightShift;
    case UIKeyboardHIDUsageKeyboardLeftControl: return GHOST_kKeyLeftControl;
    case UIKeyboardHIDUsageKeyboardRightControl: return GHOST_kKeyRightControl;
    case UIKeyboardHIDUsageKeyboardLeftAlt: return GHOST_kKeyLeftAlt;
    case UIKeyboardHIDUsageKeyboardRightAlt: return GHOST_kKeyRightAlt;
    case UIKeyboardHIDUsageKeyboardLeftGUI: return GHOST_kKeyLeftOS;
    case UIKeyboardHIDUsageKeyboardRightGUI: return GHOST_kKeyRightOS;
    case UIKeyboardHIDUsageKeyboardReturnOrEnter: return GHOST_kKeyEnter;
    case UIKeyboardHIDUsageKeypadEnter: return GHOST_kKeyEnter;
    case UIKeyboardHIDUsageKeyboardEscape: return GHOST_kKeyEsc;
    case UIKeyboardHIDUsageKeyboardDeleteOrBackspace: return GHOST_kKeyBackSpace;
    case UIKeyboardHIDUsageKeyboardDeleteForward: return GHOST_kKeyDelete;
    case UIKeyboardHIDUsageKeyboardTab: return GHOST_kKeyTab;
    case UIKeyboardHIDUsageKeyboardSpacebar: return GHOST_kKeySpace;
    case UIKeyboardHIDUsageKeyboardUpArrow: return GHOST_kKeyUpArrow;
    case UIKeyboardHIDUsageKeyboardDownArrow: return GHOST_kKeyDownArrow;
    case UIKeyboardHIDUsageKeyboardLeftArrow: return GHOST_kKeyLeftArrow;
    case UIKeyboardHIDUsageKeyboardRightArrow: return GHOST_kKeyRightArrow;
    case UIKeyboardHIDUsageKeyboardF1: return GHOST_kKeyF1;
    case UIKeyboardHIDUsageKeyboardF2: return GHOST_kKeyF2;
    case UIKeyboardHIDUsageKeyboardF3: return GHOST_kKeyF3;
    case UIKeyboardHIDUsageKeyboardF4: return GHOST_kKeyF4;
    case UIKeyboardHIDUsageKeyboardF5: return GHOST_kKeyF5;
    case UIKeyboardHIDUsageKeyboardF6: return GHOST_kKeyF6;
    case UIKeyboardHIDUsageKeyboardF7: return GHOST_kKeyF7;
    case UIKeyboardHIDUsageKeyboardF8: return GHOST_kKeyF8;
    case UIKeyboardHIDUsageKeyboardF9: return GHOST_kKeyF9;
    case UIKeyboardHIDUsageKeyboardF10: return GHOST_kKeyF10;
    case UIKeyboardHIDUsageKeyboardF11: return GHOST_kKeyF11;
    case UIKeyboardHIDUsageKeyboardF12: return GHOST_kKeyF12;
    default: break;
  }
  NSString *chars = key.charactersIgnoringModifiers;
  if (chars.length == 1) {
    unichar c = [chars characterAtIndex:0];
    if (c >= 'a' && c <= 'z') return (GHOST_TKey)(GHOST_kKeyA + (c - 'a'));
    if (c >= 'A' && c <= 'Z') return (GHOST_TKey)(GHOST_kKeyA + (c - 'A'));
    if (c >= '0' && c <= '9') return (GHOST_TKey)(GHOST_kKey0 + (c - '0'));
    switch (c) {
      case ' ': return GHOST_kKeySpace;
      case '-': return GHOST_kKeyMinus;
      case '=': return GHOST_kKeyEqual;
      case '[': return GHOST_kKeyLeftBracket;
      case ']': return GHOST_kKeyRightBracket;
      case '\\': return GHOST_kKeyBackslash;
      case ';': return GHOST_kKeySemicolon;
      case '\'': return GHOST_kKeyQuote;
      case '`': return GHOST_kKeyAccentGrave;
      case ',': return GHOST_kKeyComma;
      case '.': return GHOST_kKeyPeriod;
      case '/': return GHOST_kKeySlash;
      default: break;
    }
  }
  return GHOST_kKeyUnknown;
}
/* ==== end build-13 helpers ==== */
'''

# pressesBegan/Ended/Cancelled methods, inserted before registerGestureRecognizers
kbd_methods = r'''- (void)pressesBegan:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event
{
  BOOL handled = NO;
  for (UIPress *press in presses) {
    UIKey *key = press.key;
    if (!key) {
      continue;
    }
    GHOST_TKey gkey = ghost_key_from_uikey(key);
    char utf8_buf[6] = {0};
    const bool suppress_text = ((key.modifierFlags & UIKeyModifierCommand) != 0) ||
                               gkey == GHOST_kKeyLeftArrow || gkey == GHOST_kKeyRightArrow ||
                               gkey == GHOST_kKeyUpArrow || gkey == GHOST_kKeyDownArrow;
    if (!suppress_text && key.characters.length > 0) {
      const char *kc = key.characters.UTF8String;
      if (kc) {
        strncpy(utf8_buf, kc, sizeof(utf8_buf) - 1);
      }
    }
    ghost_ios_log([NSString stringWithFormat:@"PRESS down hid=%ld chars='%@' mods=0x%lx -> ghost=%d utf8='%s'",
                                              (long)key.keyCode,
                                              key.charactersIgnoringModifiers ?: @"",
                                              (unsigned long)key.modifierFlags,
                                              (int)gkey,
                                              utf8_buf]);
    if (gkey != GHOST_kKeyUnknown) {
      system->pushEvent(new GHOST_EventKey(GHOST_GetMilliSeconds((GHOST_SystemHandle)system),
                                           GHOST_kEventKeyDown,
                                           window,
                                           gkey,
                                           false,
                                           utf8_buf));
      handled = YES;
    }
  }
  if (!handled) {
    [super pressesBegan:presses withEvent:event];
  }
}

- (void)pressesEnded:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event
{
  BOOL handled = NO;
  for (UIPress *press in presses) {
    UIKey *key = press.key;
    if (!key) {
      continue;
    }
    GHOST_TKey gkey = ghost_key_from_uikey(key);
    if (gkey != GHOST_kKeyUnknown) {
      system->pushEvent(new GHOST_EventKey(GHOST_GetMilliSeconds((GHOST_SystemHandle)system),
                                           GHOST_kEventKeyUp,
                                           window,
                                           gkey,
                                           false,
                                           nullptr));
      handled = YES;
    }
  }
  if (!handled) {
    [super pressesEnded:presses withEvent:event];
  }
}

- (void)pressesCancelled:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event
{
  [super pressesCancelled:presses withEvent:event];
}

- (void)registerGestureRecognizers
{
'''

# handleZoom: handle trackpad/indirect pinch (0 touches) via gesture .scale
zoom_guard_old = (
"  /* Ignore any calls where don't have two touches to work with. */\n"
"  if ([sender numberOfTouches] < 2) {\n"
"    return;\n"
"  }\n")
zoom_guard_new = (
"  /* build-13: trackpad/indirect pinch reports 0 touches; drive zoom from the gesture scale. */\n"
"  if ([sender numberOfTouches] < 2) {\n"
"    if (sender.state == UIGestureRecognizerStateBegan) {\n"
"      [sender setCachedDistance:sender.scale];\n"
"    }\n"
"    else if (sender.state == UIGestureRecognizerStateChanged) {\n"
"      CGFloat prev = [sender getCachedDistance];\n"
"      CGFloat relative_dist = (sender.scale - prev) * 400.0;\n"
"      [sender setCachedDistance:sender.scale];\n"
"      if (fabs(relative_dist) > 0.0) {\n"
"        CGPoint midPoint = [sender locationInView:window->getView()];\n"
"        UserInputEvent event_info(&midPoint, nullptr, &relative_dist, false);\n"
"        event_info.add_event(UserInputEvent::EventTypes::PINCH_GESTURE);\n"
"        [self generateUserInputEvents:event_info];\n"
"      }\n"
"    }\n"
"    return;\n"
"  }\n")

edit(W, [
 ("#include <unordered_map>\n", helpers, "ios-input-helpers"),
 ("- (void)registerGestureRecognizers\n{\n", kbd_methods, "keyboard-presses-methods"),
 # trackpad indirect pointer (click/drag/pan) + scroll
 ("  tap_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect) ];\n",
  "  tap_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect), @(UITouchTypeIndirectPointer) ];\n",
  "tap-indirect"),
 ("  pan_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect) ];\n",
  "  pan_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect), @(UITouchTypeIndirectPointer) ];\n",
  "pan-indirect"),
 ("  [window->getView() addGestureRecognizer:pan_gesture_recognizer];\n",
  "  if (@available(iOS 13.4, *)) {\n    pan_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskAll;\n  }\n  [window->getView() addGestureRecognizer:pan_gesture_recognizer];\n",
  "pan-scrolltypes"),
 ("  [window->getView() addGestureRecognizer:pan2f_gesture_recognizer];\n",
  "  if (@available(iOS 13.4, *)) {\n    pan2f_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskAll;\n  }\n  [window->getView() addGestureRecognizer:pan2f_gesture_recognizer];\n",
  "pan2f-scrolltypes"),
 # zoom recognizer accepts trackpad + handleZoom handles trackpad pinch
 ("  zoom_gesture_recognizer.cancelsTouchesInView = false;\n  [window->getView() addGestureRecognizer:zoom_gesture_recognizer];\n",
  "  zoom_gesture_recognizer.cancelsTouchesInView = false;\n  zoom_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect), @(UITouchTypeIndirectPointer) ];\n  [window->getView() addGestureRecognizer:zoom_gesture_recognizer];\n",
  "zoom-indirect-pointer"),
 (zoom_guard_old, zoom_guard_new, "zoom-trackpad-scale"),
])
print("ALL PATCHES APPLIED OK")


# ---------- build-14: slider/number-field scrub - deliver a single pointer drag
# (pencil / finger / trackpad click-drag, i.e. numberOfTouches >= 1) as a PURE left-button
# drag with no PAN_GESTURE, so Blender scrubs number buttons and box-selects exactly like a
# mouse or a Wacom pen on a PC. A 0-touch trackpad two-finger scroll keeps the build-13
# navigation path untouched. ----------
OLD_PAN = '- (void)handlePan:(GHOSTUIPanGestureRecognizer *)sender\n{\n  CGPoint touch_point = [sender getScaledTouchPoint:window];\n  CGPoint translation = [sender getScaledTranslation:window];\n  bool pencil_pan = current_pencil_touch ? true : false;\n\n  UserInputEvent event_info(&touch_point, nullptr, nullptr, pencil_pan);\n\n  if (sender.state == UIGestureRecognizerStateBegan ||\n      sender.state == UIGestureRecognizerStateChanged)\n  {\n    /* Register initial click for click and drag support. */\n    if (sender.state == UIGestureRecognizerStateBegan) {\n      /* Set inital translation */\n      [sender setCachedTranslation:translation];\n      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_DOWN);\n    }\n\n    /* Calculate translation change since last begin/change event */\n    CGPoint relative_translation = [sender getRelativeTranslation:translation];\n    /* Update cached translation */\n    [sender setCachedTranslation:translation];\n    /* Send pan event if non zero */\n    if (!CGPointEqualToPoint(relative_translation, CGPointMake(0.0f, 0.0f))) {\n      event_info.translation = relative_translation;\n      event_info.add_event(UserInputEvent::EventTypes::PAN_GESTURE);\n    }\n\n    /* Update cursor position on change */\n    if (sender.state == UIGestureRecognizerStateChanged) {\n      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n    }\n  }\n\n  /* Mouse release for pan. */\n  if (sender.state == UIGestureRecognizerStateEnded ||\n      sender.state == UIGestureRecognizerStateCancelled ||\n      sender.state == UIGestureRecognizerStateFailed)\n  {\n    event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_UP);\n  }\n  [self generateUserInputEvents:event_info];\n}\n'
NEW_PAN = "- (void)handlePan:(GHOSTUIPanGestureRecognizer *)sender\n{\n  CGPoint touch_point = [sender getScaledTouchPoint:window];\n  CGPoint translation = [sender getScaledTranslation:window];\n  bool pencil_pan = current_pencil_touch ? true : false;\n\n  /* build-14: a physical pointer drag - Apple Pencil, a finger on the glass, or a click-drag on the\n   * trackpad's indirect pointer - reports >= 1 touch and must behave like a mouse or a Wacom pen on\n   * a PC: a pure left-button drag, with no simultaneous scroll, so Blender itself decides\n   * scrub-vs-text-edit and box-select from the motion. A two-finger trackpad scroll reports 0\n   * touches and keeps the original navigation (pan/orbit) path below, unchanged from build-13. */\n  if ([sender numberOfTouches] >= 1) {\n    UserInputEvent event_info(&touch_point, nullptr, nullptr, pencil_pan);\n    if (sender.state == UIGestureRecognizerStateBegan) {\n      [sender setCachedTranslation:translation];\n      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_DOWN);\n    }\n    else if (sender.state == UIGestureRecognizerStateChanged) {\n      [sender setCachedTranslation:translation];\n      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n    }\n    else if (sender.state == UIGestureRecognizerStateEnded ||\n             sender.state == UIGestureRecognizerStateCancelled ||\n             sender.state == UIGestureRecognizerStateFailed)\n    {\n      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_UP);\n    }\n    [self generateUserInputEvents:event_info];\n    return;\n  }\n\n  UserInputEvent event_info(&touch_point, nullptr, nullptr, pencil_pan);\n\n  if (sender.state == UIGestureRecognizerStateBegan ||\n      sender.state == UIGestureRecognizerStateChanged)\n  {\n    /* Register initial click for click and drag support. */\n    if (sender.state == UIGestureRecognizerStateBegan) {\n      /* Set inital translation */\n      [sender setCachedTranslation:translation];\n      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_DOWN);\n    }\n\n    /* Calculate translation change since last begin/change event */\n    CGPoint relative_translation = [sender getRelativeTranslation:translation];\n    /* Update cached translation */\n    [sender setCachedTranslation:translation];\n    /* Send pan event if non zero */\n    if (!CGPointEqualToPoint(relative_translation, CGPointMake(0.0f, 0.0f))) {\n      event_info.translation = relative_translation;\n      event_info.add_event(UserInputEvent::EventTypes::PAN_GESTURE);\n    }\n\n    /* Update cursor position on change */\n    if (sender.state == UIGestureRecognizerStateChanged) {\n      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n    }\n  }\n\n  /* Mouse release for pan. */\n  if (sender.state == UIGestureRecognizerStateEnded ||\n      sender.state == UIGestureRecognizerStateCancelled ||\n      sender.state == UIGestureRecognizerStateFailed)\n  {\n    event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_UP);\n  }\n  [self generateUserInputEvents:event_info];\n}"
edit(W, [(OLD_PAN, NEW_PAN, "pan-pointer-drag")])
print("BUILD-14 (pan-pointer-drag) APPLIED OK")


# ===================== build-15: direct in-place text input (hardware keyboard) ==========
# pressesBegan now carries UTF-8 (above), the on-screen field is suppressed when a hardware
# keyboard is present, and the two ui_textedit_string_set calls are guarded so they neither
# clobber the in-place editstr nor crash on a null string. This also fixes Shift+A menu
# type-to-search, which reads event->utf8_buf. Build-14's pan-pointer-drag (sliders) is kept.
IH = "blender/source/blender/editors/interface/interface_handlers.cc"
POPUP_OLD = '    [self setupKeyboard:keyboard_properties];\n\n    if (!onscreen_keyboard_active) {\n      text_field.userInteractionEnabled = YES;\n      if (![text_field becomeFirstResponder]) {\n'
POPUP_NEW = '    [self setupKeyboard:keyboard_properties];\n\n    /* build-15: with a hardware keyboard attached, keep the GHOSTUIWindow as first responder and\n     * do NOT raise the on-screen text field. Keystrokes then arrive via pressesBegan (carrying\n     * UTF-8) and Blender edits the value in place with its own caret, exactly like the desktop\n     * build. The on-screen field is reserved for the soft (touch) keyboard. */\n    external_keyboard_connected = [GCKeyboard coalescedKeyboard] != nil;\n    if (external_keyboard_connected) {\n      text_field.text = nil;\n      text_field_string = nullptr;\n      ghost_ios_log(@"KBD: hardware keyboard present -> editing in place (on-screen field suppressed)");\n    }\n    else if (!onscreen_keyboard_active) {\n      text_field.userInteractionEnabled = YES;\n      if (![text_field becomeFirstResponder]) {\n'
END_OLD = '  if (but) {\n    ui_textedit_string_set(but, but->active->text_edit, keyboard_string);\n  }\n#endif'
END_NEW = '  if (but && keyboard_string) {\n    /* build-15: only overwrite from the on-screen field when it was actually used\n     * (soft keyboard, non-null string); with a hardware keyboard the value was typed\n     * into the editstr in place, so leave it untouched. Never pass a null string to\n     * ui_textedit_string_set (that path crashed on delete-all). */\n    ui_textedit_string_set(but, but->active->text_edit, keyboard_string);\n  }\n#endif'
EVT_OLD = '          if (but->active->text_edit.edit_string) {\n            ui_textedit_string_set(but, but->active->text_edit, keyboard_string);\n          }'
EVT_NEW = '          if (keyboard_string && but->active->text_edit.edit_string) {\n            ui_textedit_string_set(but, but->active->text_edit, keyboard_string);\n          }'
edit(W, [(POPUP_OLD, POPUP_NEW, "kbd-popup-hardware")])
edit(IH, [(END_OLD, END_NEW, "textedit-end-guard"), (EVT_OLD, EVT_NEW, "evt-textedit-guard")])
print("BUILD-15 (in-place text input + Shift+A search) APPLIED OK")
