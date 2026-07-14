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


# ============ build-19: comprehensive logging (Cycles kernel-load + all stdout/stderr to Documents/blender_console.log) ============
edit('blender/intern/ghost/GHOST_ISystem.hh', [
  ('  virtual GHOST_TSuccess stopSecurityScopedFileAccess(const char *filepath) = 0;\n#endif\n', '  virtual GHOST_TSuccess stopSecurityScopedFileAccess(const char *filepath) = 0;\n#endif\n\n  /* build-16/17: native iOS file picker (no-op on other platforms). */\n  virtual void iosPresentFilePicker(int /*mode*/, const char * /*suggested_name*/) {}\n  virtual void iosSetFilePickerCallback(void (* /*cb*/)(const char *)) {}\n', 'isys-ios-picker'),
])
edit('blender/intern/ghost/intern/GHOST_SystemIOS.hh', [
  ('  GHOST_TSuccess startSecurityScopedFileAccess(const char *filepath);\n  GHOST_TSuccess stopSecurityScopedFileAccess(const char *filepath);\n', '  GHOST_TSuccess startSecurityScopedFileAccess(const char *filepath);\n  GHOST_TSuccess stopSecurityScopedFileAccess(const char *filepath);\n\n  /* build-16/17: native iOS file picker. */\n  void iosPresentFilePicker(int mode, const char *suggested_name) override;\n  void iosSetFilePickerCallback(void (*cb)(const char *)) override;\n  void *ios_picker_delegate_ = nullptr;\n  void *ios_scoped_urls_ = nullptr;\n  void *ios_pending_save_name_ = nullptr;\n  void (*ios_file_picker_cb_)(const char *) = nullptr;\n  int ios_picker_mode_ = 0;\n', 'gsihh-ios-picker'),
])
edit('blender/intern/ghost/intern/GHOST_SystemIOS.mm', [
  ('GHOST_TSuccess GHOST_SystemIOS::stopSecurityScopedFileAccess(const char *filepath)\n{\n  NSURL *url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:filepath]];\n  [url stopAccessingSecurityScopedResource];\n\n  return GHOST_kSuccess;\n}\n', 'GHOST_TSuccess GHOST_SystemIOS::stopSecurityScopedFileAccess(const char *filepath)\n{\n  NSURL *url = [NSURL fileURLWithPath:[NSString stringWithUTF8String:filepath]];\n  [url stopAccessingSecurityScopedResource];\n\n  return GHOST_kSuccess;\n}\n\n\n/* ===== build-16/17/18: fully-native iOS file access (UIDocumentPickerViewController) ===== */\nextern bool g_ios_suppress_blender_keys; /* defined in GHOST_WindowIOS.mm */\n\nstatic void ios_file_log(NSString *msg)\n{\n  NSArray *dirs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES);\n  if (!dirs.count || !msg) {\n    return;\n  }\n  NSString *p = [[dirs firstObject] stringByAppendingPathComponent:@"blender_input.log"];\n  NSString *line = [NSString stringWithFormat:@"[fileaccess] %@\\n", msg];\n  NSFileHandle *fh = [NSFileHandle fileHandleForWritingAtPath:p];\n  if (fh) {\n    [fh seekToEndOfFile];\n    [fh writeData:[line dataUsingEncoding:NSUTF8StringEncoding]];\n    [fh closeFile];\n  }\n  else {\n    [line writeToFile:p atomically:YES encoding:NSUTF8StringEncoding error:nil];\n  }\n  NSLog(@"%@", line);\n}\n\nstatic UIViewController *ios_top_presenter(void)\n{\n  UIViewController *presenter = nil;\n  for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {\n    if ([scene isKindOfClass:[UIWindowScene class]]) {\n      for (UIWindow *w in ((UIWindowScene *)scene).windows) {\n        if (w.rootViewController) {\n          presenter = w.rootViewController;\n          if (w.isKeyWindow) {\n            break;\n          }\n        }\n      }\n    }\n  }\n  while (presenter.presentedViewController) {\n    presenter = presenter.presentedViewController;\n  }\n  return presenter;\n}\n\n@interface GHOSTFilePickerDelegate : NSObject <UIDocumentPickerDelegate>\n@property(nonatomic) GHOST_SystemIOS *system;\n@end\n\n@implementation GHOSTFilePickerDelegate\n\n- (void)documentPicker:(UIDocumentPickerViewController *)controller\n    didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls\n{\n  GHOST_SystemIOS *sys = self.system;\n  NSURL *url = urls.firstObject;\n  if (!sys) {\n    return;\n  }\n  if (!url) {\n    if (sys->ios_file_picker_cb_) {\n      sys->ios_file_picker_cb_(NULL);\n    }\n    return;\n  }\n  BOOL ok = [url startAccessingSecurityScopedResource];\n  NSString *finalPath = url.path;\n  if (sys->ios_pending_save_name_ != NULL) {\n    NSString *name = (__bridge_transfer NSString *)sys->ios_pending_save_name_;\n    sys->ios_pending_save_name_ = NULL;\n    finalPath = [url.path stringByAppendingPathComponent:name];\n  }\n  ios_file_log([NSString stringWithFormat:@"picked \'%@\' scope=%d", finalPath, (int)ok]);\n  if (sys->ios_scoped_urls_ == NULL) {\n    sys->ios_scoped_urls_ = (void *)CFBridgingRetain([NSMutableArray array]);\n  }\n  [(__bridge NSMutableArray *)sys->ios_scoped_urls_ addObject:url];\n  if (sys->ios_file_picker_cb_) {\n    sys->ios_file_picker_cb_(finalPath.fileSystemRepresentation);\n  }\n}\n\n- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller\n{\n  GHOST_SystemIOS *sys = self.system;\n  if (sys && sys->ios_pending_save_name_ != NULL) {\n    CFBridgingRelease(sys->ios_pending_save_name_);\n    sys->ios_pending_save_name_ = NULL;\n  }\n  ios_file_log(@"picker cancelled");\n  if (sys && sys->ios_file_picker_cb_) {\n    sys->ios_file_picker_cb_(NULL);\n  }\n}\n\n@end\n\nvoid GHOST_SystemIOS::iosSetFilePickerCallback(void (*cb)(const char *))\n{\n  this->ios_file_picker_cb_ = cb;\n}\n\nvoid GHOST_SystemIOS::iosPresentFilePicker(int mode, const char *suggested_name)\n{\n  this->ios_picker_mode_ = mode;\n  GHOST_SystemIOS *sys = this;\n  NSString *suggested = (suggested_name && suggested_name[0]) ?\n                            [NSString stringWithUTF8String:suggested_name] :\n                            @"untitled.blend";\n  dispatch_async(dispatch_get_main_queue(), ^{\n    UIViewController *presenter = ios_top_presenter();\n    if (!presenter) {\n      ios_file_log(@"no presenter view controller; cancelling");\n      if (sys->ios_file_picker_cb_) {\n        sys->ios_file_picker_cb_(NULL);\n      }\n      return;\n    }\n    if (sys->ios_picker_delegate_ == NULL) {\n      GHOSTFilePickerDelegate *del = [[GHOSTFilePickerDelegate alloc] init];\n      del.system = sys;\n      sys->ios_picker_delegate_ = (void *)CFBridgingRetain(del);\n    }\n    void (^showFolderPicker)(NSString *) = ^(NSString *saveName) {\n      if (saveName) {\n        sys->ios_pending_save_name_ = (void *)CFBridgingRetain(saveName);\n      }\n#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wdeprecated-declarations"\n      UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc]\n          initWithDocumentTypes:@[ @"public.folder" ]\n                         inMode:UIDocumentPickerModeOpen];\n#pragma clang diagnostic pop\n      picker.allowsMultipleSelection = NO;\n      picker.delegate = (__bridge id<UIDocumentPickerDelegate>)sys->ios_picker_delegate_;\n      picker.modalPresentationStyle = UIModalPresentationFormSheet;\n      UIViewController *p2 = ios_top_presenter();\n      [p2 presentViewController:picker animated:YES completion:nil];\n      ios_file_log(@"folder picker presented");\n    };\n    if (mode == 1) {\n      UIAlertController *alert =\n          [UIAlertController alertControllerWithTitle:@"Save As"\n                                              message:@"Enter a file name, then choose a folder."\n                                       preferredStyle:UIAlertControllerStyleAlert];\n      [alert addTextFieldWithConfigurationHandler:^(UITextField *tf) {\n        tf.text = suggested;\n        tf.clearButtonMode = UITextFieldViewModeWhileEditing;\n        tf.autocorrectionType = UITextAutocorrectionTypeNo;\n      }];\n      [alert addAction:[UIAlertAction actionWithTitle:@"Cancel"\n                                                style:UIAlertActionStyleCancel\n                                              handler:^(UIAlertAction *a) {\n                          g_ios_suppress_blender_keys = false;\n                          if (sys->ios_file_picker_cb_) {\n                            sys->ios_file_picker_cb_(NULL);\n                          }\n                        }]];\n      [alert addAction:[UIAlertAction actionWithTitle:@"Choose Folder"\n                                                style:UIAlertActionStyleDefault\n                                              handler:^(UIAlertAction *a) {\n                          NSString *name = alert.textFields.firstObject.text;\n                          if (!name || name.length == 0) {\n                            name = suggested;\n                          }\n                          g_ios_suppress_blender_keys = false;\n                          showFolderPicker(name);\n                        }]];\n      g_ios_suppress_blender_keys = true;\n      [presenter presentViewController:alert\n                              animated:YES\n                            completion:^{\n                              [alert.textFields.firstObject becomeFirstResponder];\n                            }];\n      ios_file_log([NSString stringWithFormat:@"save-as prompt (suggested=\'%@\')", suggested]);\n    }\n    else {\n#pragma clang diagnostic push\n#pragma clang diagnostic ignored "-Wdeprecated-declarations"\n      UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc]\n          initWithDocumentTypes:@[ @"public.item" ]\n                         inMode:UIDocumentPickerModeOpen];\n#pragma clang diagnostic pop\n      picker.allowsMultipleSelection = NO;\n      picker.delegate = (__bridge id<UIDocumentPickerDelegate>)sys->ios_picker_delegate_;\n      picker.modalPresentationStyle = UIModalPresentationFormSheet;\n      [presenter presentViewController:picker animated:YES completion:nil];\n      ios_file_log(@"open picker presented");\n    }\n  });\n}\n', 'gsimm-ios-picker'),
])
edit('blender/intern/ghost/GHOST_C-api.h', [
  ('extern GHOST_TSuccess GHOST_stopSecurityScopedFileAccess(const char *filepath);\n\n#endif\n', 'extern GHOST_TSuccess GHOST_stopSecurityScopedFileAccess(const char *filepath);\n\n#endif\n\nextern void GHOST_iosPresentFilePicker(int mode, const char *suggested_name);\nextern void GHOST_iosSetFilePickerCallback(void (*cb)(const char *));\n', 'capih-ios-picker'),
])
edit('blender/intern/ghost/intern/GHOST_C-api.cc', [
  ('extern GHOST_TSuccess GHOST_stopSecurityScopedFileAccess(const char *filepath)\n{\n  GHOST_ISystem *system = GHOST_ISystem::getSystem();\n  return system->stopSecurityScopedFileAccess(filepath);\n}\n\n#endif\n', 'extern GHOST_TSuccess GHOST_stopSecurityScopedFileAccess(const char *filepath)\n{\n  GHOST_ISystem *system = GHOST_ISystem::getSystem();\n  return system->stopSecurityScopedFileAccess(filepath);\n}\n\n#endif\n\nvoid GHOST_iosPresentFilePicker(int mode, const char *suggested_name)\n{\n  GHOST_ISystem *system = GHOST_ISystem::getSystem();\n  system->iosPresentFilePicker(mode, suggested_name);\n}\n\nvoid GHOST_iosSetFilePickerCallback(void (*cb)(const char *))\n{\n  GHOST_ISystem *system = GHOST_ISystem::getSystem();\n  system->iosSetFilePickerCallback(cb);\n}\n', 'capicc-ios-picker'),
])
edit('blender/source/blender/windowmanager/intern/wm_event_system.cc', [
  ('static eHandlerActionFlag wm_handler_fileselect_do(bContext *C,\n', '#if (WITH_APPLE_CROSSPLATFORM)\n/* build-16/17: route open/save/import/export file-select to the native iOS picker; feed the\n * async pick back through EVT_FILESELECT_EXEC / CANCEL. For save, GHOST prompts for name +\n * folder and returns the full destination path. */\nstatic wmWindowManager *g_ios_fsel_wm = nullptr;\nstatic wmOperator *g_ios_fsel_op = nullptr;\n\nstatic void wm_ios_set_op_path(wmOperator *op, const char *full)\n{\n  PropertyRNA *prop = RNA_struct_find_property(op->ptr, "filepath");\n  if (prop) {\n    RNA_property_string_set(op->ptr, prop, full);\n  }\n  const char *slash = strrchr(full, \'/\');\n  if (slash) {\n    char dir[1100];\n    size_t dlen = (size_t)(slash - full) + 1;\n    if (dlen >= sizeof(dir)) {\n      dlen = sizeof(dir) - 1;\n    }\n    memcpy(dir, full, dlen);\n    dir[dlen] = \'\\0\';\n    if ((prop = RNA_struct_find_property(op->ptr, "directory"))) {\n      RNA_property_string_set(op->ptr, prop, dir);\n    }\n    if ((prop = RNA_struct_find_property(op->ptr, "filename"))) {\n      RNA_property_string_set(op->ptr, prop, slash + 1);\n    }\n  }\n}\n\nstatic void wm_ios_fileselect_complete(const char *path)\n{\n  wmWindowManager *wm = g_ios_fsel_wm;\n  wmOperator *op = g_ios_fsel_op;\n  g_ios_fsel_op = nullptr;\n  if (!wm || !op) {\n    return;\n  }\n  if (!path || path[0] == \'\\0\') {\n    WM_event_fileselect_event(wm, op, EVT_FILESELECT_CANCEL);\n    return;\n  }\n  wm_ios_set_op_path(op, path);\n  WM_event_fileselect_event(wm, op, EVT_FILESELECT_EXEC);\n}\n\nstatic bool wm_ios_fileselect_begin(bContext * /*C*/,\n                                    wmWindowManager *wm,\n                                    wmEventHandler_Op *handler)\n{\n  wmOperator *op = handler->op;\n  bool save = false;\n  PropertyRNA *prop = RNA_struct_find_property(op->ptr, "check_existing");\n  if (prop && RNA_property_boolean_get(op->ptr, prop)) {\n    save = true;\n  }\n  char namebuf[512] = {0};\n  if (save) {\n    if ((prop = RNA_struct_find_property(op->ptr, "filename"))) {\n      RNA_property_string_get(op->ptr, prop, namebuf);\n    }\n    if (namebuf[0] == \'\\0\') {\n      char pathbuf[1100] = {0};\n      if ((prop = RNA_struct_find_property(op->ptr, "filepath"))) {\n        RNA_property_string_get(op->ptr, prop, pathbuf);\n      }\n      const char *slash = strrchr(pathbuf, \'/\');\n      BLI_strncpy(namebuf, slash ? slash + 1 : pathbuf, sizeof(namebuf));\n    }\n    if (namebuf[0] == \'\\0\') {\n      BLI_strncpy(namebuf, "untitled.blend", sizeof(namebuf));\n    }\n  }\n  g_ios_fsel_wm = wm;\n  g_ios_fsel_op = op;\n  GHOST_iosSetFilePickerCallback(wm_ios_fileselect_complete);\n  GHOST_iosPresentFilePicker(save ? 1 : 0, save ? namebuf : "");\n  return true;\n}\n#endif /* WITH_APPLE_CROSSPLATFORM */\n\nstatic eHandlerActionFlag wm_handler_fileselect_do(bContext *C,\n', 'wmev-ios-helpers'),
  ('    case EVT_FILESELECT_FULL_OPEN: {\n      ScrArea *area = ED_screen_temp_space_open(\n', '    case EVT_FILESELECT_FULL_OPEN: {\n#if (WITH_APPLE_CROSSPLATFORM)\n      if (wm_ios_fileselect_begin(C, wm, handler)) {\n        return WM_HANDLER_BREAK;\n      }\n#endif\n      ScrArea *area = ED_screen_temp_space_open(\n', 'wmev-ios-fullopen'),
])
edit('blender/intern/ghost/intern/GHOST_WindowIOS.mm', [
  ('    text_field.contentScaleFactor = window->getWindowScaleFactor();\n', '    text_field.contentScaleFactor = window->getWindowScaleFactor();\n\n    /* build-17: this field is only an input proxy for the on-screen (soft) keyboard; with a\n     * hardware keyboard Blender edits text in place. Make it visually inert so it never shows\n     * a caret (the stray blue vertical line) or the bottom shortcut/accessory bars. */\n    text_field.tintColor = [UIColor clearColor];\n    text_field.borderStyle = UITextBorderStyleNone;\n    text_field.backgroundColor = [UIColor clearColor];\n    text_field.inputAssistantItem.leadingBarButtonGroups = @[];\n    text_field.inputAssistantItem.trailingBarButtonGroups = @[];\n', 'win-field-inert'),
  ('      text_field.inputAccessoryView = toolbar;\n', '      text_field.inputAccessoryView = nil; /* build-17: suppress bottom input bar */\n', 'win-no-accessory-bar'),
  ('GHOST_TSuccess GHOST_WindowIOS::setWindowCursorVisibility(bool /*visible*/)\n{\n', "/* ===== build-17: trackpad pointer shapes for Blender's area resize / split cursors =====\n * setWindowCursorShape was a no-op on iOS, so the resize double-arrows and split cross never\n * appeared. Add a UIPointerInteraction whose style follows the cursor Blender last requested. */\nstatic GHOST_TStandardCursor g_ios_pointer_shape = GHOST_kStandardCursorDefault;\nstatic UIPointerInteraction *g_ios_pointer_interaction = nil;\nstatic id g_ios_pointer_delegate = nil;\n\nstatic UIBezierPath *ios_pointer_path_for_cursor(GHOST_TStandardCursor shape)\n{\n  const CGFloat L = 11.0;\n  const CGFloat H = 5.0;\n  const CGFloat T = 1.5;\n  UIBezierPath *path = nil;\n  switch (shape) {\n    case GHOST_kStandardCursorUpDown:\n    case GHOST_kStandardCursorNSScroll:\n    case GHOST_kStandardCursorTopSide:\n    case GHOST_kStandardCursorBottomSide: {\n      path = [UIBezierPath bezierPath];\n      [path moveToPoint:CGPointMake(0, -L)];\n      [path addLineToPoint:CGPointMake(-H, -L + H)];\n      [path addLineToPoint:CGPointMake(-T, -L + H)];\n      [path addLineToPoint:CGPointMake(-T, L - H)];\n      [path addLineToPoint:CGPointMake(-H, L - H)];\n      [path addLineToPoint:CGPointMake(0, L)];\n      [path addLineToPoint:CGPointMake(H, L - H)];\n      [path addLineToPoint:CGPointMake(T, L - H)];\n      [path addLineToPoint:CGPointMake(T, -L + H)];\n      [path addLineToPoint:CGPointMake(H, -L + H)];\n      [path closePath];\n      break;\n    }\n    case GHOST_kStandardCursorLeftRight:\n    case GHOST_kStandardCursorEWScroll:\n    case GHOST_kStandardCursorLeftSide:\n    case GHOST_kStandardCursorRightSide: {\n      path = [UIBezierPath bezierPath];\n      [path moveToPoint:CGPointMake(-L, 0)];\n      [path addLineToPoint:CGPointMake(-L + H, -H)];\n      [path addLineToPoint:CGPointMake(-L + H, -T)];\n      [path addLineToPoint:CGPointMake(L - H, -T)];\n      [path addLineToPoint:CGPointMake(L - H, -H)];\n      [path addLineToPoint:CGPointMake(L, 0)];\n      [path addLineToPoint:CGPointMake(L - H, H)];\n      [path addLineToPoint:CGPointMake(L - H, T)];\n      [path addLineToPoint:CGPointMake(-L + H, T)];\n      [path addLineToPoint:CGPointMake(-L + H, H)];\n      [path closePath];\n      break;\n    }\n    case GHOST_kStandardCursorVerticalSplit:\n    case GHOST_kStandardCursorHorizontalSplit:\n    case GHOST_kStandardCursorNSEWScroll:\n    case GHOST_kStandardCursorMove:\n    case GHOST_kStandardCursorCrosshair: {\n      path = [UIBezierPath bezierPath];\n      [path moveToPoint:CGPointMake(-T, -L)];\n      [path addLineToPoint:CGPointMake(T, -L)];\n      [path addLineToPoint:CGPointMake(T, -T)];\n      [path addLineToPoint:CGPointMake(L, -T)];\n      [path addLineToPoint:CGPointMake(L, T)];\n      [path addLineToPoint:CGPointMake(T, T)];\n      [path addLineToPoint:CGPointMake(T, L)];\n      [path addLineToPoint:CGPointMake(-T, L)];\n      [path addLineToPoint:CGPointMake(-T, T)];\n      [path addLineToPoint:CGPointMake(-L, T)];\n      [path addLineToPoint:CGPointMake(-L, -T)];\n      [path addLineToPoint:CGPointMake(-T, -T)];\n      [path closePath];\n      break;\n    }\n    default:\n      break;\n  }\n  return path;\n}\n\nAPI_AVAILABLE(ios(13.4))\n@interface GHOSTPointerDelegate : NSObject <UIPointerInteractionDelegate>\n@end\n\n@implementation GHOSTPointerDelegate\n- (UIPointerRegion *)pointerInteraction:(UIPointerInteraction *)interaction\n                       regionForRequest:(UIPointerRegionRequest *)request\n                          defaultRegion:(UIPointerRegion *)defaultRegion\n{\n  return defaultRegion;\n}\n- (UIPointerStyle *)pointerInteraction:(UIPointerInteraction *)interaction\n                        styleForRegion:(UIPointerRegion *)region\n{\n  UIBezierPath *path = ios_pointer_path_for_cursor(g_ios_pointer_shape);\n  if (!path) {\n    return nil;\n  }\n  UIPointerShape *shape = [UIPointerShape shapeWithPath:path];\n  return [UIPointerStyle styleWithShape:shape constrainedAxes:UIAxisNeither];\n}\n@end\n\nGHOST_TSuccess GHOST_WindowIOS::setWindowCursorVisibility(bool /*visible*/)\n{\n", 'win-pointer-block'),
  ('GHOST_TSuccess GHOST_WindowIOS::setWindowCursorShape(GHOST_TStandardCursor /*shape*/)\n{\n  return GHOST_kSuccess;\n}\n', 'GHOST_TSuccess GHOST_WindowIOS::setWindowCursorShape(GHOST_TStandardCursor shape)\n{\n  if (shape == g_ios_pointer_shape && g_ios_pointer_interaction != nil) {\n    return GHOST_kSuccess;\n  }\n  g_ios_pointer_shape = shape;\n  UIView *view = this->getView();\n  dispatch_async(dispatch_get_main_queue(), ^{\n    if (!view) {\n      return;\n    }\n    if (@available(iOS 13.4, *)) {\n      if (g_ios_pointer_interaction == nil) {\n        g_ios_pointer_delegate = [[GHOSTPointerDelegate alloc] init];\n        g_ios_pointer_interaction = [[UIPointerInteraction alloc]\n            initWithDelegate:(id<UIPointerInteractionDelegate>)g_ios_pointer_delegate];\n        [view addInteraction:g_ios_pointer_interaction];\n      }\n      [g_ios_pointer_interaction invalidate];\n    }\n  });\n  return GHOST_kSuccess;\n}\n', 'win-setcursorshape'),
  ('@implementation GHOSTUIWindow\n', '/* build-18: true while a native text dialog (Save As) is up, so hardware keys go to it.\n * Referenced (extern) from GHOST_SystemIOS.mm. */\nbool g_ios_suppress_blender_keys = false;\n/* build-20: counts created windows so secondary windows get a back button. */\nint g_ios_window_count = 0;\n\n@implementation GHOSTUIWindow\n', 'win-suppress-flag'),
  ('- (void)handleZoom:(GHOSTUIPinchGestureRecognizer *)sender\n{\n  /* build-13: trackpad/indirect pinch reports 0 touches; drive zoom from the gesture scale. */\n  if ([sender numberOfTouches] < 2) {\n    if (sender.state == UIGestureRecognizerStateBegan) {\n      [sender setCachedDistance:sender.scale];\n    }\n    else if (sender.state == UIGestureRecognizerStateChanged) {\n      CGFloat prev = [sender getCachedDistance];\n      CGFloat relative_dist = (sender.scale - prev) * 400.0;\n      [sender setCachedDistance:sender.scale];\n      if (fabs(relative_dist) > 0.0) {\n        CGPoint midPoint = [sender locationInView:window->getView()];\n        UserInputEvent event_info(&midPoint, nullptr, &relative_dist, false);\n        event_info.add_event(UserInputEvent::EventTypes::PINCH_GESTURE);\n        [self generateUserInputEvents:event_info];\n      }\n    }\n    return;\n  }\n\n  /* Pinch/Zoom gestures */\n  if (sender.state == UIGestureRecognizerStateBegan) {\n    /* Set an initial distance value. */\n    CGFloat point_distance = [sender getScaledDistance:window];\n    [sender setCachedDistance:point_distance];\n  }\n  else if (sender.state == UIGestureRecognizerStateChanged) {\n\n    /* Calculate change in distance since last event */\n    CGFloat point_distance = [sender getScaledDistance:window];\n    CGFloat relative_dist = point_distance - [sender getCachedDistance];\n\n    /* Updated cached distance. */\n    [sender setCachedDistance:point_distance];\n\n    /* Send pinch/zoom event. */\n    if (fabs(relative_dist) > 0.0) {\n      /* Calculate midpoint between the two touch points. */\n      CGPoint midPoint = [sender getPinchMidpoint:window];\n\n      UserInputEvent event_info(&midPoint, nullptr, &relative_dist, false);\n      event_info.add_event(UserInputEvent::EventTypes::PINCH_GESTURE);\n      [self generateUserInputEvents:event_info];\n    }\n  }\n  /* Nothing to do here. */\n  else if (sender.state == UIGestureRecognizerStateEnded ||\n           sender.state == UIGestureRecognizerStateCancelled ||\n           sender.state == UIGestureRecognizerStateFailed)\n  {\n  }\n}\n', "- (void)handleZoom:(GHOSTUIPinchGestureRecognizer *)sender\n{\n  /* build-18: one code path for finger AND trackpad pinch. Magnitude comes from the gesture's own\n   * .scale (robust against a finger momentarily lost mid-pinch, which used to spike the delta and\n   * fling the 3D view off-centre). Location is reported in WINDOW pixels via scalePointToWindow so\n   * the zoom is routed to whatever editor the pointer is over - build-17's trackpad branch forgot\n   * to scale, so it always landed in the 3D view. */\n  if (sender.state == UIGestureRecognizerStateBegan) {\n    [sender setCachedDistance:sender.scale];\n    return;\n  }\n  if (sender.state != UIGestureRecognizerStateChanged) {\n    return;\n  }\n  CGFloat prev = [sender getCachedDistance];\n  CGFloat cur = sender.scale;\n  [sender setCachedDistance:cur];\n  CGFloat relative_dist = (cur - prev) * 400.0;\n  /* Clamp so a single bad frame cannot fling the view far off-centre. */\n  const CGFloat max_step = 60.0;\n  if (relative_dist > max_step) {\n    relative_dist = max_step;\n  }\n  else if (relative_dist < -max_step) {\n    relative_dist = -max_step;\n  }\n  if (fabs(relative_dist) <= 0.0) {\n    return;\n  }\n  CGPoint midPoint = [sender locationInView:window->getView()];\n  midPoint = window->scalePointToWindow(midPoint);\n  UserInputEvent event_info(&midPoint, nullptr, &relative_dist, false);\n  event_info.add_event(UserInputEvent::EventTypes::PINCH_GESTURE);\n  [self generateUserInputEvents:event_info];\n}\n", 'win-handlezoom-unify'),
  ('- (void)pressesBegan:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event\n{\n  BOOL handled = NO;\n', '- (void)pressesBegan:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event\n{\n  /* build-18: while a native text dialog (Save As) is up, let the hardware keyboard\n   * type into it instead of routing keys to Blender. */\n  if (g_ios_suppress_blender_keys) {\n    [super pressesBegan:presses withEvent:event];\n    return;\n  }\n  BOOL handled = NO;\n', 'win-pressesbegan-passthrough'),
  ('- (void)pressesEnded:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event\n{\n', '- (void)pressesEnded:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event\n{\n  if (g_ios_suppress_blender_keys) {\n    [super pressesEnded:presses withEvent:event];\n    return;\n  }\n', 'win-pressesended-passthrough'),
  ('- (void)handleZoom:(GHOSTUIPinchGestureRecognizer *)sender;\n', '- (void)handleZoom:(GHOSTUIPinchGestureRecognizer *)sender;\n- (void)addBackButton;\n- (void)handleBackButton;\n', 'win-backbtn-iface'),
  ('- (void)endFrame\n{\n}\n', '- (void)endFrame\n{\n}\n\n- (void)addBackButton\n{\n  /* build-20: defer to the next run-loop so the window\'s view and safe area are ready, then add\n   * the button to the root view controller\'s content view - in build-18 it was added to the\n   * window itself, where it sat behind the Metal view and never appeared. Bring it to front and\n   * log placement so we can confirm. */\n  dispatch_async(dispatch_get_main_queue(), ^{\n    UIView *host = self.rootViewController ? self.rootViewController.view : (UIView *)self;\n    if (!host) {\n      IOS_INPUT_LOG(@"[backbtn] addBackButton: no host view");\n      return;\n    }\n    UIButton *backBtn = [UIButton buttonWithType:UIButtonTypeSystem];\n    UIImage *img = [UIImage systemImageNamed:@"chevron.backward"];\n    if (img) {\n      [backBtn setImage:img forState:UIControlStateNormal];\n    }\n    else {\n      [backBtn setTitle:@"Back" forState:UIControlStateNormal];\n    }\n    backBtn.tintColor = [UIColor whiteColor];\n    backBtn.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.55];\n    backBtn.layer.cornerRadius = 22.0;\n    backBtn.layer.masksToBounds = YES;\n    backBtn.translatesAutoresizingMaskIntoConstraints = NO;\n    [backBtn addTarget:self\n                action:@selector(handleBackButton)\n      forControlEvents:UIControlEventTouchUpInside];\n    [host addSubview:backBtn];\n    [host bringSubviewToFront:backBtn];\n    [NSLayoutConstraint activateConstraints:@[\n      [backBtn.leadingAnchor constraintEqualToAnchor:host.safeAreaLayoutGuide.leadingAnchor\n                                            constant:14.0],\n      [backBtn.topAnchor constraintEqualToAnchor:host.safeAreaLayoutGuide.topAnchor constant:14.0],\n      [backBtn.widthAnchor constraintEqualToConstant:44.0],\n      [backBtn.heightAnchor constraintEqualToConstant:44.0]\n    ]];\n    IOS_INPUT_LOG(@"[backbtn] addBackButton: added to %@",\n                  self.rootViewController ? @"rootVC.view" : @"window");\n  });\n}\n\n- (void)handleBackButton\n{\n  if (system && window) {\n    system->pushEvent(new GHOST_Event(\n        GHOST_GetMilliSeconds((GHOST_SystemHandle)system), GHOST_kEventWindowClose, window));\n  }\n}\n', 'win-backbtn-impl'),
  ('  [ghost_rootWindow registerGestureRecognizers];\n', '  [ghost_rootWindow registerGestureRecognizers];\n\n  /* build-20: secondary windows (render result, preferences, etc.) need a way back to\n   * the main window. Detect them by parent_window (set by createWindow) OR by not being\n   * the first window created, and log so we can see why the button does/doesn\'t show. */\n  g_ios_window_count++;\n  IOS_INPUT_LOG(@"[backbtn] window ctor count=%d parent=%p",\n                g_ios_window_count,\n                (void *)parent_window);\n  if (parent_window != nullptr || g_ios_window_count > 1) {\n    [ghost_rootWindow addBackButton];\n  }\n', 'win-backbtn-ctor'),
])
edit('blender/source/creator/creator.cc', [
  ('#include <cstdlib>\n', '#include <cstdlib>\n#ifdef WITH_APPLE_CROSSPLATFORM\n#  include <cstdio>\n#  include <unistd.h>\n#endif\n', 'creator-log-includes'),
  ('{\n  bContext *C;\n#ifndef WITH_PYTHON_MODULE\n  bArgs *ba;\n#endif\n', '{\n  bContext *C;\n#ifndef WITH_PYTHON_MODULE\n  bArgs *ba;\n#endif\n\n#ifdef WITH_APPLE_CROSSPLATFORM\n  /* build-19: capture all stdout/stderr (Blender + Cycles logging, and a crash\'s final\n   * messages) to a file the user can read in Files -> On My iPad -> Blender, for diagnosing\n   * GPU/Cycles kernel loading and any other issues. */\n  {\n    const char *blender_ios_home = getenv("HOME");\n    if (blender_ios_home) {\n      char blender_ios_logpath[1024];\n      snprintf(blender_ios_logpath,\n               sizeof(blender_ios_logpath),\n               "%s/Documents/blender_console.log",\n               blender_ios_home);\n      if (freopen(blender_ios_logpath, "w", stdout) != nullptr) {\n        dup2(fileno(stdout), fileno(stderr));\n        setvbuf(stdout, nullptr, _IONBF, 0);\n        setvbuf(stderr, nullptr, _IONBF, 0);\n        fprintf(stderr, "[blender-ios] build-19 console log started\\n");\n      }\n    }\n  }\n#endif\n', 'creator-log-redirect'),
])
edit('blender/intern/cycles/device/metal/device_impl.mm', [
  ('    kernel_features |= _kernel_features;\n', '    kernel_features |= _kernel_features;\n\n#ifdef WITH_APPLE_CROSSPLATFORM\n    /* build-19: raise Cycles log verbosity so the detailed Metal kernel-load messages (compile\n     * begin/end, archive use/skip, per-kernel timings, and failures) are emitted to the captured\n     * console log, to diagnose slow/failing GPU kernel loading on iOS. */\n    LOG_LEVEL = LOG_LEVEL_TRACE;\n    metal_printf("build-19: load_kernels start, kernel_features=0x%x, use_metalrt=%d",\n                 (unsigned int)kernel_features,\n                 (int)use_metalrt);\n#endif\n', 'cycles-metal-loglevel'),
])

# ================= build-21: system dark/light theme (base pinned to d9b6fe3) =================
edit('blender/source/blender/editors/interface/resources.cc', [
  ('  btheme->active_theme_area = active_theme_area;\n}\n\nvoid UI_style_init_default()', '  btheme->active_theme_area = active_theme_area;\n}\n\n/* ===== build-21: follow the iPadOS system dark/light appearance =====\n * Dark = the Blender built-in default (reset via UI_theme_init_default). Light = a simple light\n * override applied on top. Invoked at startup and on every system appearance change. */\nstatic void ios_set_col(unsigned char c[4], int r, int g, int b, int a)\n{\n  c[0] = (unsigned char)r;\n  c[1] = (unsigned char)g;\n  c[2] = (unsigned char)b;\n  c[3] = (unsigned char)a;\n}\n\nstatic void ios_set_wcol_light(uiWidgetColors *w)\n{\n  ios_set_col(w->outline, 175, 179, 188, 255);\n  ios_set_col(w->inner, 250, 251, 253, 255);\n  ios_set_col(w->inner_sel, 66, 135, 225, 255);\n  ios_set_col(w->item, 60, 62, 68, 255);\n  ios_set_col(w->text, 32, 34, 40, 255);\n  ios_set_col(w->text_sel, 255, 255, 255, 255);\n}\n\nvoid UI_theme_apply_ios_appearance(bool dark)\n{\n  UI_theme_init_default();\n  if (dark) {\n    return;\n  }\n  bTheme *btheme = static_cast<bTheme *>(U.themes.first);\n  if (btheme == nullptr) {\n    return;\n  }\n  for (ThemeSpace *ts = UI_THEMESPACE_START(btheme); ts != UI_THEMESPACE_END(btheme); ts++) {\n    ios_set_col(ts->back, 235, 237, 240, 255);\n    ios_set_col(ts->back_grad, 235, 237, 240, 255);\n    ios_set_col(ts->title, 32, 34, 40, 255);\n    ios_set_col(ts->text, 32, 34, 40, 255);\n    ios_set_col(ts->text_hi, 0, 0, 0, 255);\n    ios_set_col(ts->header, 223, 226, 231, 255);\n    ios_set_col(ts->header_text, 32, 34, 40, 255);\n    ios_set_col(ts->header_text_hi, 0, 0, 0, 255);\n    ios_set_col(ts->tab_back, 235, 237, 240, 255);\n    ios_set_col(ts->button, 223, 226, 231, 255);\n    ios_set_col(ts->list, 244, 246, 249, 255);\n    ios_set_col(ts->list_title, 32, 34, 40, 255);\n    ios_set_col(ts->list_text, 32, 34, 40, 255);\n    ios_set_col(ts->list_text_hi, 0, 0, 0, 255);\n  }\n  ThemeUI *tui = &btheme->tui;\n  ios_set_wcol_light(&tui->wcol_regular);\n  ios_set_wcol_light(&tui->wcol_tool);\n  ios_set_wcol_light(&tui->wcol_toolbar_item);\n  ios_set_wcol_light(&tui->wcol_text);\n  ios_set_wcol_light(&tui->wcol_radio);\n  ios_set_wcol_light(&tui->wcol_option);\n  ios_set_wcol_light(&tui->wcol_toggle);\n  ios_set_wcol_light(&tui->wcol_num);\n  ios_set_wcol_light(&tui->wcol_numslider);\n  ios_set_wcol_light(&tui->wcol_tab);\n  ios_set_wcol_light(&tui->wcol_menu);\n  ios_set_wcol_light(&tui->wcol_pulldown);\n  ios_set_wcol_light(&tui->wcol_menu_back);\n  ios_set_wcol_light(&tui->wcol_menu_item);\n  ios_set_wcol_light(&tui->wcol_tooltip);\n  ios_set_wcol_light(&tui->wcol_box);\n  ios_set_wcol_light(&tui->wcol_scroll);\n  ios_set_wcol_light(&tui->wcol_progress);\n  ios_set_wcol_light(&tui->wcol_list_item);\n  ios_set_wcol_light(&tui->wcol_pie_menu);\n  ios_set_col(tui->wcol_menu_back.inner, 249, 250, 252, 255);\n  ios_set_col(tui->wcol_tooltip.inner, 249, 250, 252, 255);\n  ios_set_col(tui->panel_header, 228, 231, 236, 255);\n  ios_set_col(tui->panel_back, 244, 246, 249, 255);\n  ios_set_col(tui->panel_sub_back, 238, 240, 244, 255);\n  ios_set_col(tui->panel_outline, 175, 179, 188, 255);\n  ios_set_col(tui->panel_title, 32, 34, 40, 255);\n  ios_set_col(tui->panel_text, 32, 34, 40, 255);\n  ios_set_col(tui->editor_border, 175, 179, 188, 255);\n  ios_set_col(tui->editor_outline, 175, 179, 188, 255);\n  ios_set_col(tui->widget_text_cursor, 20, 20, 24, 255);\n  ios_set_col(btheme->space_view3d.back, 222, 226, 232, 255);\n  ios_set_col(btheme->space_view3d.back_grad, 236, 238, 242, 255);\n  ios_set_col(btheme->space_view3d.wire, 55, 58, 64, 255);\n  ios_set_col(btheme->space_view3d.wire_edit, 35, 38, 44, 255);\n  ios_set_col(btheme->space_view3d.grid, 200, 203, 209, 255);\n  ios_set_col(btheme->space_view3d.text_hi, 20, 20, 24, 255);\n}\n\nvoid UI_style_init_default()', 'ios-theme-apply'),
])
edit('blender/source/blender/editors/include/UI_resources.hh', [
  ('void UI_SetTheme(int spacetype, int regionid);', 'void UI_SetTheme(int spacetype, int regionid);\n\n/* build-21: apply a light theme when the iOS system appearance is light (dark = the default). */\nvoid UI_theme_apply_ios_appearance(bool dark);', 'ios-theme-decl'),
])
edit('blender/intern/ghost/GHOST_C-api.h', [
  ('extern uint64_t GHOST_GetMilliSeconds(GHOST_SystemHandle systemhandle);', 'extern uint64_t GHOST_GetMilliSeconds(GHOST_SystemHandle systemhandle);\n\n/* build-21: iOS system dark/light appearance -> Blender theme. */\nextern int GHOST_iosUserInterfaceStyleIsDark(void);\nextern void GHOST_iosSetAppearanceCallback(void (*cb)(int is_dark));', 'ios-appearance-capi'),
])
edit('blender/intern/ghost/intern/GHOST_WindowIOS.mm', [
  ('int g_ios_window_count = 0;\n\n@implementation GHOSTUIWindow', 'int g_ios_window_count = 0;\n\n/* build-21: system dark/light appearance -> Blender theme, via a callback Blender registers. */\nvoid (*g_ios_appearance_cb)(int) = nullptr;\n\nextern "C" void GHOST_iosSetAppearanceCallback(void (*cb)(int))\n{\n  g_ios_appearance_cb = cb;\n}\n\nextern "C" int GHOST_iosUserInterfaceStyleIsDark(void)\n{\n  if (@available(iOS 13.0, *)) {\n    return (UITraitCollection.currentTraitCollection.userInterfaceStyle == UIUserInterfaceStyleDark) ?\n               1 :\n               0;\n  }\n  return 1;\n}\n\n@implementation GHOSTUIWindow', 'ios-appearance-globals'),
  ('- (void)handleBackButton\n{\n  if (system && window) {\n    system->pushEvent(new GHOST_Event(\n        GHOST_GetMilliSeconds((GHOST_SystemHandle)system), GHOST_kEventWindowClose, window));\n  }\n}', '- (void)handleBackButton\n{\n  if (system && window) {\n    system->pushEvent(new GHOST_Event(\n        GHOST_GetMilliSeconds((GHOST_SystemHandle)system), GHOST_kEventWindowClose, window));\n  }\n}\n\n- (void)traitCollectionDidChange:(UITraitCollection *)previousTraitCollection\n{\n  [super traitCollectionDidChange:previousTraitCollection];\n  if (@available(iOS 13.0, *)) {\n    UIUserInterfaceStyle now = self.traitCollection.userInterfaceStyle;\n    UIUserInterfaceStyle was = previousTraitCollection ? previousTraitCollection.userInterfaceStyle :\n                                                          UIUserInterfaceStyleUnspecified;\n    if (now != was && g_ios_appearance_cb) {\n      g_ios_appearance_cb((now == UIUserInterfaceStyleDark) ? 1 : 0);\n    }\n  }\n}', 'ios-appearance-trait'),
])
edit('blender/source/blender/windowmanager/intern/wm_init_exit.cc', [
  ('void WM_init(bContext *C, int argc, const char **argv)\n{', '#ifdef WITH_APPLE_CROSSPLATFORM\n/* build-21: re-apply the theme whenever the iOS system appearance flips (registered with GHOST). */\nstatic void wm_ios_appearance_cb(int is_dark)\n{\n  UI_theme_apply_ios_appearance(is_dark != 0);\n  WM_main_add_notifier(NC_WINDOW, nullptr);\n}\n#endif\n\nvoid WM_init(bContext *C, int argc, const char **argv)\n{', 'ios-appearance-cb'),
  ('    UI_init();\n    GPU_context_end_frame(GPU_context_active_get());', '    UI_init();\n#ifdef WITH_APPLE_CROSSPLATFORM\n    /* build-21: match the iOS system dark/light appearance now, and register for live changes. */\n    GHOST_iosSetAppearanceCallback(wm_ios_appearance_cb);\n    UI_theme_apply_ios_appearance(GHOST_iosUserInterfaceStyleIsDark() != 0);\n#endif\n    GPU_context_end_frame(GPU_context_active_get());', 'ios-appearance-apply'),
])

# ================= build-22: Cycles GPU fixes (serial compile + iOS binary archive + state cap) =================
edit('blender/intern/cycles/device/metal/kernel.mm', [
  ('      int max_mtlcompiler_threads = 2;\n', '      int max_mtlcompiler_threads = 2;\n#  ifdef WITH_APPLE_CROSSPLATFORM\n      /* build-22: iPadOS kills the MTLCompilerService XPC connection under memory pressure when\n       * two huge shade kernels compile concurrently (integrator_shade_volume/_shadow failed with\n       * XPC_ERROR_CONNECTION_INTERRUPTED after 130+s). Compile serially so each kernel gets the\n       * full compiler-service budget. */\n      max_mtlcompiler_threads = 1;\n#  endif\n', 'cycles-serial-compile'),
  ('#  ifdef WITH_APPLE_CROSSPLATFORM\n  return false;\n#  endif\n  /* Issues with binary archives in older macOS versions. */\n  if (@available(macOS 15.4, *)) {\n', "  /* build-22: binary archives are enabled on iOS so the expensive shade kernels (30-130+ s each\n   * on iPad) compile once and load near-instantly on subsequent launches. The MetalRT\n   * intersection-kernel exclusion below still applies (linked functions are not archivable).\n   * Note: @available(macOS 15.4, *) is TRUE on iOS builds - unlisted platforms match '*'. */\n  /* Issues with binary archives in older macOS versions. */\n  if (@available(macOS 15.4, *)) {\n", 'cycles-ios-binary-archive'),
])
edit('blender/intern/cycles/device/metal/queue.mm', [
  ('  result = 4194304;\n#  ifdef WITH_APPLE_CROSSPLATFORM\n  /* Return minimal default working set.\n   * TODO: Tune based on device and runtime status on iOS. */\n  return result;\n#  endif\n', '  result = 4194304;\n#  ifdef WITH_APPLE_CROSSPLATFORM\n  /* build-22: 4M path states is a 1.38GB SoA allocation on iPad, made BEFORE kernel compilation.\n   * That memory pressure starves MTLCompilerService (XPC compile failures seen on-device) and\n   * risks a jetsam kill shortly after rendering starts. 1M states (~350MB) still keeps an Apple\n   * GPU saturated (busy:total is 1:4, so 256K busy paths).\n   * TODO: Tune based on device and runtime status on iOS. */\n  result = 1048576;\n  return result;\n#  endif\n', 'cycles-ios-state-cap'),
])
print("BUILD-22 (Cycles: serial kernel compile + binary archive cache + 350MB state cap) APPLIED OK")


# ================= build-23: Bluetooth-mouse fixes (scroll wheel + exact-click resizing) =================
# Problem 1 - mouse scroll wheel did nothing: a wheel notch arrives as a nearly-instant
#   Began->Ended pan-scroll with its whole delta already present at Began. The old 0-touch path
#   cached the translation at Began (swallowing the delta) and only emitted PAN on Changed, so a
#   notch produced no scroll - and the LEFT_BUTTON_DOWN/UP pair sent around it produced a phantom
#   left click per notch. Trackpads worked only because continuous scrolling produces many Changed
#   states with fresh deltas.
# Problem 2 - area-edge resizing was near-impossible to grab: mouse/trackpad clicks were generated
#   by the pan recognizer, which enters Began only after ~10 pt of movement hysteresis, so
#   LEFT_BUTTON_DOWN reached Blender with the pointer already displaced from the ~2 px edge hot
#   zone. Additionally, the UIPointerInteraction used one whole-view region, so the resize arrow
#   latched on/off out of sync with the real hot zone.
# Fixes:
#   (a) 0-touch scroll path: pure scroll events; full delta at Began (cache starts at zero),
#       incremental deltas on Changed, residual on Ended, no button events.
#   (b) Raw touchesBegan/Moved/Ended handle the indirect pointer directly: button-down at the
#       EXACT press location with zero hysteresis, cursor moves while dragging, button-up on
#       release. The pan recognizer skips indirect-pointer drags (it only keeps its translation
#       cache fresh) and the tap recognizer no longer accepts the indirect pointer, so no
#       double events are generated.
#   (c) UIPointerInteraction returns a small per-location region so iOS re-queries the pointer
#       style as it moves, keeping the resize arrows in sync with Blender's hot zones.

# (b1) global for the active indirect-pointer touch.
edit(W, [
  ('bool g_ios_suppress_blender_keys = false;\n',
   'bool g_ios_suppress_blender_keys = false;\n'
   '/* build-23: the active indirect-pointer (mouse/trackpad) touch, driven by the raw\n'
   ' * touchesBegan/Moved/Ended overrides for hysteresis-free, pixel-exact clicks. */\n'
   'static UITouch *g_ios_pointer_touch = nil;\n',
   'b23-pointer-touch-global'),
])

# (b2) touchesBegan: exact-location button down for the indirect pointer.
TB_OLD = '''  [super touchesBegan:touches withEvent:event];

  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypePencil) {
      current_pencil_touch = touch;
      break;
    }
  }
}
'''
TB_NEW = '''  [super touchesBegan:touches withEvent:event];

  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypePencil) {
      current_pencil_touch = touch;
      break;
    }
  }

  /* build-23: deliver mouse/trackpad clicks at the exact press location. The pan recognizer
   * only enters Began after ~10 pt of movement hysteresis, so LEFT_BUTTON_DOWN used to arrive
   * with the pointer already displaced - Blender's ~2 px area-edge resize hot zone was
   * practically impossible to hit. Raw touches have no hysteresis. */
  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      g_ios_pointer_touch = touch;
      CGPoint p = [touch locationInView:window->getView()];
      p = window->scalePointToWindow(p);
      UserInputEvent event_info(&p, nullptr, nullptr, false);
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_DOWN);
      [self generateUserInputEvents:event_info];
      break;
    }
  }
}
'''
edit(W, [(TB_OLD, TB_NEW, 'b23-touchesbegan-pointer')])

# (b3) touchesMoved: precise cursor moves while the pointer button is held.
TM_OLD = '''        IOS_INPUT_LOG(
            @"TABLET: X:%f,Y:%f,P:%f", tablet_data.Xtilt, tablet_data.Ytilt, tablet_data.Pressure);
        break;
      }
    }
  }
}
'''
TM_NEW = '''        IOS_INPUT_LOG(
            @"TABLET: X:%f,Y:%f,P:%f", tablet_data.Xtilt, tablet_data.Ytilt, tablet_data.Pressure);
        break;
      }
    }
  }

  /* build-23: cursor moves for the held indirect pointer (click-drag). */
  if (g_ios_pointer_touch) {
    for (UITouch *touch in touches) {
      if (touch == g_ios_pointer_touch) {
        CGPoint p = [touch locationInView:window->getView()];
        p = window->scalePointToWindow(p);
        UserInputEvent event_info(&p, nullptr, nullptr, false);
        event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
        [self generateUserInputEvents:event_info];
        break;
      }
    }
  }
}
'''
edit(W, [(TM_OLD, TM_NEW, 'b23-touchesmoved-pointer')])

# (b4) touchesEnded / touchesCancelled: button up at the release location.
PTR_UP = '''  if (g_ios_pointer_touch && [touches containsObject:g_ios_pointer_touch]) {
    CGPoint p = [g_ios_pointer_touch locationInView:window->getView()];
    p = window->scalePointToWindow(p);
    g_ios_pointer_touch = nil;
    UserInputEvent event_info(&p, nullptr, nullptr, false);
    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
    event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_UP);
    [self generateUserInputEvents:event_info];
  }
'''
TE_OLD = '''- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  [super touchesEnded:touches withEvent:event];
  current_pencil_touch = nil;
  tablet_data = GHOST_TABLET_DATA_NONE;
}
'''
TE_NEW = ('''- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  [super touchesEnded:touches withEvent:event];
''' + PTR_UP + '''  current_pencil_touch = nil;
  tablet_data = GHOST_TABLET_DATA_NONE;
}
''')
TC_OLD = '''- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  [super touchesCancelled:touches withEvent:event];
  current_pencil_touch = nil;
  tablet_data = GHOST_TABLET_DATA_NONE;
}
'''
TC_NEW = ('''- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  [super touchesCancelled:touches withEvent:event];
''' + PTR_UP + '''  current_pencil_touch = nil;
  tablet_data = GHOST_TABLET_DATA_NONE;
}
''')
edit(W, [(TE_OLD, TE_NEW, 'b23-touchesended-pointer'), (TC_OLD, TC_NEW, 'b23-touchescancelled-pointer')])

# (b5) handlePan >=1-touch branch: skip indirect-pointer drags (handled by raw touches),
# but keep the translation cache fresh so the 0-touch tail never sees a stale delta.
PAN_GUARD_OLD = '''  if ([sender numberOfTouches] >= 1) {
    UserInputEvent event_info(&touch_point, nullptr, nullptr, pencil_pan);
'''
PAN_GUARD_NEW = '''  if ([sender numberOfTouches] >= 1) {
    /* build-23: indirect-pointer (mouse/trackpad) click-drags are fully handled by the raw
     * touches overrides at exact locations with no recognizer hysteresis; only keep the
     * translation cache fresh here so no stale delta leaks into the scroll path. */
    if (g_ios_pointer_touch) {
      [sender setCachedTranslation:translation];
      return;
    }
    UserInputEvent event_info(&touch_point, nullptr, nullptr, pencil_pan);
'''
edit(W, [(PAN_GUARD_OLD, PAN_GUARD_NEW, 'b23-pan-pointer-skip')])

# (b6) tap recognizer: stop accepting the indirect pointer (raw touches now produce the
# click), otherwise every mouse click would be delivered twice.
edit(W, [
  ('  tap_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect), @(UITouchTypeIndirectPointer) ];\n',
   '  /* build-23: indirect-pointer clicks come from the raw touches overrides; keeping the\n'
   '   * pointer here would double every mouse click. */\n'
   '  tap_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect) ];\n',
   'b23-tap-no-indirect'),
])

# (a) 0-touch scroll tail of handlePan: pure scroll, wheel-notch safe.
SCROLL_OLD = '''  UserInputEvent event_info(&touch_point, nullptr, nullptr, pencil_pan);

  if (sender.state == UIGestureRecognizerStateBegan ||
      sender.state == UIGestureRecognizerStateChanged)
  {
    /* Register initial click for click and drag support. */
    if (sender.state == UIGestureRecognizerStateBegan) {
      /* Set inital translation */
      [sender setCachedTranslation:translation];
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_DOWN);
    }

    /* Calculate translation change since last begin/change event */
    CGPoint relative_translation = [sender getRelativeTranslation:translation];
    /* Update cached translation */
    [sender setCachedTranslation:translation];
    /* Send pan event if non zero */
    if (!CGPointEqualToPoint(relative_translation, CGPointMake(0.0f, 0.0f))) {
      event_info.translation = relative_translation;
      event_info.add_event(UserInputEvent::EventTypes::PAN_GESTURE);
    }

    /* Update cursor position on change */
    if (sender.state == UIGestureRecognizerStateChanged) {
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
    }
  }

  /* Mouse release for pan. */
  if (sender.state == UIGestureRecognizerStateEnded ||
      sender.state == UIGestureRecognizerStateCancelled ||
      sender.state == UIGestureRecognizerStateFailed)
  {
    event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_UP);
  }
  [self generateUserInputEvents:event_info];
}'''
SCROLL_NEW = '''  /* build-23: 0 touches here = scroll events - a trackpad two-finger scroll OR a mouse scroll
   * wheel. A wheel notch arrives as a nearly-instant Began->Ended with its whole delta already
   * present at Began; the old path cached the translation at Began (swallowing the delta) and
   * only emitted PAN on Changed, so the wheel did nothing - and the LEFT_BUTTON_DOWN/UP pair
   * sent around it produced a phantom left click per notch. Emit pure scroll instead: full
   * delta at Began (the cache starts at zero), incremental deltas on Changed, any residual on
   * Ended, and no button events at all. */
  if (sender.state == UIGestureRecognizerStateBegan) {
    [sender setCachedTranslation:CGPointMake(0.0f, 0.0f)];
  }
  if (sender.state == UIGestureRecognizerStateBegan ||
      sender.state == UIGestureRecognizerStateChanged ||
      sender.state == UIGestureRecognizerStateEnded)
  {
    CGPoint relative_translation = [sender getRelativeTranslation:translation];
    [sender setCachedTranslation:translation];
    if (!CGPointEqualToPoint(relative_translation, CGPointMake(0.0f, 0.0f))) {
      UserInputEvent event_info(&touch_point, nullptr, nullptr, pencil_pan);
      event_info.translation = relative_translation;
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      event_info.add_event(UserInputEvent::EventTypes::PAN_GESTURE);
      [self generateUserInputEvents:event_info];
    }
  }
}'''
edit(W, [(SCROLL_OLD, SCROLL_NEW, 'b23-scroll-wheel')])

# (c) pointer region: micro-region so the resize arrow tracks the hot zone.
REGION_OLD = '''                          defaultRegion:(UIPointerRegion *)defaultRegion
{
  return defaultRegion;
}
'''
REGION_NEW = '''                          defaultRegion:(UIPointerRegion *)defaultRegion
{
  /* build-23: a per-location micro-region instead of the whole view, so iOS re-queries
   * styleForRegion as the pointer moves and the resize arrows appear/disappear exactly in
   * sync with the hot zone Blender reports, instead of latching across the entire view. */
  CGRect r = CGRectMake(request.location.x - 4.0, request.location.y - 4.0, 8.0, 8.0);
  return [UIPointerRegion regionWithRect:r identifier:@"ghost-pointer"];
}
'''
edit(W, [(REGION_OLD, REGION_NEW, 'b23-pointer-region')])

print("BUILD-23 (mouse scroll wheel + exact-click area resizing) APPLIED OK")


# ================= build-24: enable real pointer events (Info.plist) + fix Cycles kernel cache =================
# Root causes found via on-device logs:
# 1. Info.plist lacks UIApplicationSupportsIndirectInputEvents. Without it iPadOS delivers
#    mouse/trackpad clicks in COMPATIBILITY MODE as synthesized DIRECT (finger) touches:
#    touch.type is never UITouchTypeIndirectPointer, so build-23's exact-click path (and v22's
#    allowedTouchTypes additions) never ran. Clicks kept routing through the finger pipeline
#    (tap recognizer + pan with ~10 pt hysteresis) - hence "resize arrow shows but clicking
#    box-selects". Adding the key makes UIKit deliver real .indirectPointer touches, which the
#    build-23 raw-touch path then handles at the exact press pixel.
# 2. Cycles binary-archive saves all failed with "Invalid URL": on iOS (unlike macOS),
#    MTLBinaryArchive serializeToURL: does NOT create the destination file - it can only
#    overwrite an existing one. So no kernel ever persisted and every session recompiled from
#    scratch. Pre-create the directory and an empty file before serializing.

# (1) Info.plist: opt in to indirect input events.
PLIST = "blender/release/ios/Blender.app/Info.plist"
edit(PLIST, [
  ("\t<key>UIRequiresFullScreen</key>\n",
   "\t<key>UIApplicationSupportsIndirectInputEvents</key>\n"
   "\t<true/>\n"
   "\t<key>UIRequiresFullScreen</key>\n",
   "b24-indirect-input-events"),
])

# (2) kernel.mm: pre-create the archive file so serializeToURL can succeed on iOS.
KM = "blender/intern/cycles/device/metal/kernel.mm"
SER_OLD = """    if (creating_new_archive || recreate_archive) {
      if (![archive serializeToURL:[NSURL fileURLWithPath:@(metalbin_path.c_str())] error:&error])
"""
SER_NEW = """    if (creating_new_archive || recreate_archive) {
#  ifdef WITH_APPLE_CROSSPLATFORM
      /* build-24: on iOS serializeToURL does not create the destination file (it fails with
       * "Invalid URL") - it can only overwrite an existing one. Pre-create the directory and
       * an empty file so the archive can be saved and kernels persist across sessions. */
      {
        NSString *ios_bin_path = @(metalbin_path.c_str());
        NSFileManager *ios_fm = [NSFileManager defaultManager];
        [ios_fm createDirectoryAtPath:[ios_bin_path stringByDeletingLastPathComponent]
            withIntermediateDirectories:YES
                             attributes:nil
                                  error:nil];
        [ios_fm createFileAtPath:ios_bin_path contents:[NSData data] attributes:nil];
      }
#  endif
      if (![archive serializeToURL:[NSURL fileURLWithPath:@(metalbin_path.c_str())] error:&error])
"""
edit(KM, [(SER_OLD, SER_NEW, "b24-archive-precreate")])

print("BUILD-24 (indirect input events + Cycles kernel cache persistence) APPLIED OK")


# ================= build-26: Cycles compile time + crash + pointer clicks via long-press =================
# On-device findings from build-25 logs:
# - App crashed ~15 min in: PSO_SPECIALIZED_INTERSECT kernels were being recompiled DURING
#   rendering (render buffers + compiler memory = jetsam kill). -> Force PSO_GENERIC on iOS.
# - shade_volume/shade_shadow took 300s and failed with XPC_ERROR_CONNECTION_INTERRUPTED before
#   succeeding on retry. Apple's WWDC22 guidance (which cites Cycles by name) recommends
#   MTLLibraryOptimizationLevelSize for exactly this. -> Enable on iOS.
# - Binary-archive saves still fail with "Invalid URL" even against a pre-created file.
#   -> Serialize to a temp file then move into the cache, with full error-domain diagnostics.
# - Resize clicks still box-select: whether indirect-pointer touches reach the raw responder
#   overrides is unverified. -> Move pointer button handling to a UILongPressGestureRecognizer
#   (minimumPressDuration=0: fires at the exact press point, zero hysteresis, and gesture
#   recognizers are the documented delivery path for indirect-pointer touches). Raw overrides
#   become tracking/diagnostics only. On-device stderr logging added so the console log shows
#   exactly what arrives.

DI = "blender/intern/cycles/device/metal/device_impl.mm"
edit(DI, [
  ('    if (auto *envstr = getenv("CYCLES_METAL_SPECIALIZATION_LEVEL")) {\n',
   '#  ifdef WITH_APPLE_CROSSPLATFORM\n'
   '    /* build-26: specialized PSOs recompile kernels in the background DURING rendering; on\n'
   '     * iPad the combined memory pressure of rendering + MTLCompilerService got the app killed\n'
   '     * (crash at ~15 min observed on-device right as PSO_SPECIALIZED_INTERSECT compiles ran).\n'
   '     * Generic pipelines only: slightly slower renders, no mid-render compile storms. */\n'
   '    kernel_specialization_level = PSO_GENERIC;\n'
   '#  endif\n'
   '    if (auto *envstr = getenv("CYCLES_METAL_SPECIALIZATION_LEVEL")) {\n',
   'b26-no-specialization'),
  ('    options.fastMathEnabled = YES;\n',
   '    options.fastMathEnabled = YES;\n'
   '#  ifdef WITH_APPLE_CROSSPLATFORM\n'
   "    /* build-26: Apple's WWDC22 'Target and optimize GPU binaries' cites Cycles as the case\n"
   '     * where optimize-for-size fixes unexpectedly long compiles (less inlining/unrolling ->\n'
   '     * far smaller AIR for the backend). integrator_shade_volume/_shadow took ~300 s each on\n'
   '     * iPad and starved MTLCompilerService into XPC kills. */\n'
   '    if (@available(iOS 16.0, *)) {\n'
   '      options.optimizationLevel = MTLLibraryOptimizationLevelSize;\n'
   '    }\n'
   '#  endif\n',
   'b26-optimize-for-size'),
])

KM = "blender/intern/cycles/device/metal/kernel.mm"
SER24_OLD = '''    if (creating_new_archive || recreate_archive) {
#  ifdef WITH_APPLE_CROSSPLATFORM
      /* build-24: on iOS serializeToURL does not create the destination file (it fails with
       * "Invalid URL") - it can only overwrite an existing one. Pre-create the directory and
       * an empty file so the archive can be saved and kernels persist across sessions. */
      {
        NSString *ios_bin_path = @(metalbin_path.c_str());
        NSFileManager *ios_fm = [NSFileManager defaultManager];
        [ios_fm createDirectoryAtPath:[ios_bin_path stringByDeletingLastPathComponent]
            withIntermediateDirectories:YES
                             attributes:nil
                                  error:nil];
        [ios_fm createFileAtPath:ios_bin_path contents:[NSData data] attributes:nil];
      }
#  endif
      if (![archive serializeToURL:[NSURL fileURLWithPath:@(metalbin_path.c_str())] error:&error])
      {
        metal_printf("Failed to save binary archive to %s, error:\\n%s",
                     metalbin_path.c_str(),
                     [[error localizedDescription] UTF8String]);
      }
      else {
        path_cache_kernel_mark_added_and_clear_old(metalbin_path);
      }
    }
'''
SER26_NEW = '''    if (creating_new_archive || recreate_archive) {
#  ifdef WITH_APPLE_CROSSPLATFORM
      /* build-26: serializeToURL kept failing with "Invalid URL" even against a pre-created
       * file. Serialize to a guaranteed-writable temporary file instead, then move the result
       * into the kernel cache - and log every step (incl. NSError domain/code) so the
       * on-device console log pinpoints any remaining failure. */
      {
        NSFileManager *ios_fm = [NSFileManager defaultManager];
        NSString *ios_bin_path = @(metalbin_path.c_str());
        NSError *ios_dir_err = nil;
        BOOL ios_dir_ok = [ios_fm
                  createDirectoryAtPath:[ios_bin_path stringByDeletingLastPathComponent]
            withIntermediateDirectories:YES
                             attributes:nil
                                  error:&ios_dir_err];
        NSString *ios_tmp_path = [NSTemporaryDirectory()
            stringByAppendingPathComponent:[NSString stringWithFormat:@"cycles_%@.bin",
                                                                      [[NSUUID UUID] UUIDString]]];
        [ios_fm createFileAtPath:ios_tmp_path contents:[NSData data] attributes:nil];
        NSError *ios_ser_err = nil;
        BOOL ios_ser_ok = [archive serializeToURL:[NSURL fileURLWithPath:ios_tmp_path
                                                              isDirectory:NO]
                                            error:&ios_ser_err];
        metal_printf("build-26 archive: dir_ok=%d (%s) tmp_serialize_ok=%d domain=%s code=%d (%s)",
                     (int)ios_dir_ok,
                     ios_dir_err ? [[ios_dir_err localizedDescription] UTF8String] : "ok",
                     (int)ios_ser_ok,
                     ios_ser_err ? [[ios_ser_err domain] UTF8String] : "none",
                     ios_ser_err ? (int)[ios_ser_err code] : 0,
                     ios_ser_err ? [[ios_ser_err localizedDescription] UTF8String] : "ok");
        if (ios_ser_ok) {
          [ios_fm removeItemAtPath:ios_bin_path error:nil];
          NSError *ios_mv_err = nil;
          if ([ios_fm moveItemAtPath:ios_tmp_path toPath:ios_bin_path error:&ios_mv_err]) {
            path_cache_kernel_mark_added_and_clear_old(metalbin_path);
            metal_printf("build-26 archive: saved %s", metalbin_path.c_str());
          }
          else {
            metal_printf("build-26 archive: move failed: %s",
                         ios_mv_err ? [[ios_mv_err localizedDescription] UTF8String] : "?");
          }
        }
        else {
          [ios_fm removeItemAtPath:ios_tmp_path error:nil];
        }
      }
#  else
      if (![archive serializeToURL:[NSURL fileURLWithPath:@(metalbin_path.c_str())] error:&error])
      {
        metal_printf("Failed to save binary archive to %s, error:\\n%s",
                     metalbin_path.c_str(),
                     [[error localizedDescription] UTF8String]);
      }
      else {
        path_cache_kernel_mark_added_and_clear_old(metalbin_path);
      }
#  endif
    }
'''
edit(KM, [(SER24_OLD, SER26_NEW, "b26-archive-tmp-move")])

# --- pointer clicks via zero-delay long press + diagnostics ---
edit(W, [
  ('static UITouch *g_ios_pointer_touch = nil;\n',
   'static UITouch *g_ios_pointer_touch = nil;\n'
   '/* build-26: true while the mouse/trackpad button is held (set by the zero-delay long-press\n'
   ' * recognizer, which is the guaranteed delivery path for indirect-pointer touches). */\n'
   'static bool g_ios_pointer_button_down = false;\n',
   'b26-button-flag'),
  ('  /* Apple Pencil hover recognizer. */\n',
   '  /* build-26: mouse/trackpad button handling. A UILongPressGestureRecognizer with\n'
   '   * minimumPressDuration=0 enters Began at the exact press location with zero movement\n'
   '   * hysteresis, and gesture recognizers (unlike raw responder overrides) are the documented\n'
   '   * delivery path for indirect-pointer touches under\n'
   '   * UIApplicationSupportsIndirectInputEvents. */\n'
   '  if (@available(iOS 13.4, *)) {\n'
   '    UILongPressGestureRecognizer *pointer_press_recognizer = [[UILongPressGestureRecognizer alloc]\n'
   '        initWithTarget:self\n'
   '                action:@selector(handlePointerPress:)];\n'
   '    pointer_press_recognizer.minimumPressDuration = 0.0;\n'
   '    pointer_press_recognizer.allowableMovement = CGFLOAT_MAX;\n'
   '    pointer_press_recognizer.allowedTouchTypes = @[ @(UITouchTypeIndirectPointer) ];\n'
   '    pointer_press_recognizer.cancelsTouchesInView = false;\n'
   '    [window->getView() addGestureRecognizer:pointer_press_recognizer];\n'
   '  }\n'
   '\n'
   '  /* Apple Pencil hover recognizer. */\n',
   'b26-longpress-recognizer'),
  ('- (void)handleHover:(GHOSTUIHoverGestureRecognizer *)sender\n{\n',
   '- (void)handlePointerPress:(UILongPressGestureRecognizer *)sender\n'
   '{\n'
   '  CGPoint p = [sender locationInView:window->getView()];\n'
   '  p = window->scalePointToWindow(p);\n'
   '  if (sender.state == UIGestureRecognizerStateBegan) {\n'
   '    g_ios_pointer_button_down = true;\n'
   '    fprintf(stderr, "[b26-ptr] button DOWN %.1f,%.1f\\n", p.x, p.y);\n'
   '    UserInputEvent event_info(&p, nullptr, nullptr, false);\n'
   '    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n'
   '    event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_DOWN);\n'
   '    [self generateUserInputEvents:event_info];\n'
   '  }\n'
   '  else if (sender.state == UIGestureRecognizerStateChanged) {\n'
   '    UserInputEvent event_info(&p, nullptr, nullptr, false);\n'
   '    event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n'
   '    [self generateUserInputEvents:event_info];\n'
   '  }\n'
   '  else if (sender.state == UIGestureRecognizerStateEnded ||\n'
   '           sender.state == UIGestureRecognizerStateCancelled ||\n'
   '           sender.state == UIGestureRecognizerStateFailed)\n'
   '  {\n'
   '    if (g_ios_pointer_button_down) {\n'
   '      g_ios_pointer_button_down = false;\n'
   '      fprintf(stderr, "[b26-ptr] button UP %.1f,%.1f\\n", p.x, p.y);\n'
   '      UserInputEvent event_info(&p, nullptr, nullptr, false);\n'
   '      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);\n'
   '      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_UP);\n'
   '      [self generateUserInputEvents:event_info];\n'
   '    }\n'
   '  }\n'
   '}\n'
   '\n'
   '- (void)handleHover:(GHOSTUIHoverGestureRecognizer *)sender\n{\n',
   'b26-longpress-handler'),
])

# raw-touch overrides become tracking + diagnostics only (long-press emits the events).
RAW_TB_OLD = '''  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      g_ios_pointer_touch = touch;
      CGPoint p = [touch locationInView:window->getView()];
      p = window->scalePointToWindow(p);
      UserInputEvent event_info(&p, nullptr, nullptr, false);
      event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
      event_info.add_event(UserInputEvent::EventTypes::LEFT_BUTTON_DOWN);
      [self generateUserInputEvents:event_info];
      break;
    }
  }
}
'''
RAW_TB_NEW = '''  for (UITouch *touch in touches) {
    if (touch.type == UITouchTypeIndirectPointer) {
      g_ios_pointer_touch = touch;
      fprintf(stderr, "[b26-ptr] raw indirect touch began\\n");
      break;
    }
  }
}
'''
RAW_TM_OLD = '''  /* build-23: cursor moves for the held indirect pointer (click-drag). */
  if (g_ios_pointer_touch) {
    for (UITouch *touch in touches) {
      if (touch == g_ios_pointer_touch) {
        CGPoint p = [touch locationInView:window->getView()];
        p = window->scalePointToWindow(p);
        UserInputEvent event_info(&p, nullptr, nullptr, false);
        event_info.add_event(UserInputEvent::EventTypes::CURSOR_MOVE);
        [self generateUserInputEvents:event_info];
        break;
      }
    }
  }
}
'''
RAW_TM_NEW = '''  /* build-26: pointer drag cursor-moves are emitted by handlePointerPress (Changed). */
}
'''
PTR_UP_TRACK = '''  if (g_ios_pointer_touch && [touches containsObject:g_ios_pointer_touch]) {
    g_ios_pointer_touch = nil;
  }
'''
RAW_TE_OLD = '''  [super touchesEnded:touches withEvent:event];
''' + PTR_UP
RAW_TE_NEW = '''  [super touchesEnded:touches withEvent:event];
''' + PTR_UP_TRACK
RAW_TC_OLD = '''  [super touchesCancelled:touches withEvent:event];
''' + PTR_UP
RAW_TC_NEW = '''  [super touchesCancelled:touches withEvent:event];
''' + PTR_UP_TRACK
edit(W, [
  (RAW_TB_OLD, RAW_TB_NEW, 'b26-raw-tb-passive'),
  (RAW_TM_OLD, RAW_TM_NEW, 'b26-raw-tm-passive'),
  (RAW_TE_OLD, RAW_TE_NEW, 'b26-raw-te-passive'),
  (RAW_TC_OLD, RAW_TC_NEW, 'b26-raw-tc-passive'),
  ('    if (g_ios_pointer_touch) {\n      [sender setCachedTranslation:translation];\n      return;\n    }\n',
   '    if (g_ios_pointer_touch || g_ios_pointer_button_down) {\n      [sender setCachedTranslation:translation];\n      return;\n    }\n',
   'b26-pan-gate-flag'),
  ('  g_ios_pointer_shape = shape;\n',
   '  g_ios_pointer_shape = shape;\n'
   '  fprintf(stderr, "[b26-ptr] cursor shape -> %d\\n", (int)shape);\n',
   'b26-cursor-shape-diag'),
])

print("BUILD-26 (no in-render specialization + optimize-for-size + archive tmp/move diag + long-press pointer clicks) APPLIED OK")
