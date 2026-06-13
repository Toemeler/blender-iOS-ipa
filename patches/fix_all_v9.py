#!/usr/bin/env python3
"""build-9 source patches for the Blender ios branch.
Applies on the runner against a fresh checkout. Self-verifying: aborts if any
anchor does not match exactly once (so we never compile a half-applied patch)."""
import sys

def edit(path, replacements):
    s = open(path).read()
    for old, new, tag in replacements:
        if new and new in s and old not in s:
            print(f"{path}: '{tag}' already applied"); continue
        n = s.count(old)
        if n != 1:
            sys.stderr.write(f"FATAL {path}: anchor '{tag}' found {n} times (need 1)\n")
            sys.exit(1)
        s = s.replace(old, new, 1)
        print(f"{path}: applied '{tag}'")
    open(path, "w").write(s)

# ---------- 1) wm_add_default: allocate wm->runtime before use ----------
WM = "blender/source/blender/windowmanager/intern/wm.cc"
alloc = "  wm->runtime = MEM_new<blender::bke::WindowManagerRuntime>(__func__);\n"
edit(WM, [
 ("  BKE_reports_init(&wm->runtime->reports, RPT_STORE);\n",
  alloc + "  BKE_reports_init(&wm->runtime->reports, RPT_STORE);\n",
  "wm-runtime-alloc"),
 ("  wm->file_saved = 1;\n" + alloc + "  wm_window_make_drawable(wm, win);\n",
  "  wm->file_saved = 1;\n  wm_window_make_drawable(wm, win);\n",
  "wm-runtime-dedup"),
])

# ---------- 2) creator.cc: disable Blender crash handler (clean iOS reports) ----------
edit("blender/source/creator/creator.cc", [
 ("  app_state.signal.use_crash_handler = true;\n  app_state.signal.use_abort_handler = true;\n",
  "  app_state.signal.use_crash_handler = false;\n  app_state.signal.use_abort_handler = false;\n",
  "crash-handler-off"),
])

# ---------- 3) GHOST_WindowIOS.mm: keyboard + trackpad + input logging ----------
W = "blender/intern/ghost/intern/GHOST_WindowIOS.mm"

helpers = r'''#include <unordered_map>

/* ==== build-9 ADDED: iOS input diagnostics + hardware keyboard support ==== */
static void ghost_ios_log(NSString *msg)
{
  static dispatch_once_t once;
  static NSString *log_path = nil;
  dispatch_once(&once, ^{
    NSArray *dirs = NSSearchPathForDirectoriesInDomains(
        NSDocumentDirectory, NSUserDomainMask, YES);
    if (dirs.count) {
      log_path = [[dirs firstObject] stringByAppendingPathComponent:@"blender_input.log"];
    }
  });
  if (!log_path) {
    return;
  }
  FILE *f = fopen(log_path.fileSystemRepresentation, "a");
  if (f) {
    NSString *line = [msg stringByAppendingString:@"\n"];
    const char *c = line.UTF8String;
    fwrite(c, 1, strlen(c), f);
    fclose(f);
  }
}

static GHOST_TKey ghost_key_from_gc(GCKeyCode kc)
{
  if (kc == GCKeyCodeKeyA) return GHOST_kKeyA;
  if (kc == GCKeyCodeKeyB) return GHOST_kKeyB;
  if (kc == GCKeyCodeKeyC) return GHOST_kKeyC;
  if (kc == GCKeyCodeKeyD) return GHOST_kKeyD;
  if (kc == GCKeyCodeKeyE) return GHOST_kKeyE;
  if (kc == GCKeyCodeKeyF) return GHOST_kKeyF;
  if (kc == GCKeyCodeKeyG) return GHOST_kKeyG;
  if (kc == GCKeyCodeKeyH) return GHOST_kKeyH;
  if (kc == GCKeyCodeKeyI) return GHOST_kKeyI;
  if (kc == GCKeyCodeKeyJ) return GHOST_kKeyJ;
  if (kc == GCKeyCodeKeyK) return GHOST_kKeyK;
  if (kc == GCKeyCodeKeyL) return GHOST_kKeyL;
  if (kc == GCKeyCodeKeyM) return GHOST_kKeyM;
  if (kc == GCKeyCodeKeyN) return GHOST_kKeyN;
  if (kc == GCKeyCodeKeyO) return GHOST_kKeyO;
  if (kc == GCKeyCodeKeyP) return GHOST_kKeyP;
  if (kc == GCKeyCodeKeyQ) return GHOST_kKeyQ;
  if (kc == GCKeyCodeKeyR) return GHOST_kKeyR;
  if (kc == GCKeyCodeKeyS) return GHOST_kKeyS;
  if (kc == GCKeyCodeKeyT) return GHOST_kKeyT;
  if (kc == GCKeyCodeKeyU) return GHOST_kKeyU;
  if (kc == GCKeyCodeKeyV) return GHOST_kKeyV;
  if (kc == GCKeyCodeKeyW) return GHOST_kKeyW;
  if (kc == GCKeyCodeKeyX) return GHOST_kKeyX;
  if (kc == GCKeyCodeKeyY) return GHOST_kKeyY;
  if (kc == GCKeyCodeKeyZ) return GHOST_kKeyZ;
  if (kc == GCKeyCodeOne) return GHOST_kKey1;
  if (kc == GCKeyCodeTwo) return GHOST_kKey2;
  if (kc == GCKeyCodeThree) return GHOST_kKey3;
  if (kc == GCKeyCodeFour) return GHOST_kKey4;
  if (kc == GCKeyCodeFive) return GHOST_kKey5;
  if (kc == GCKeyCodeSix) return GHOST_kKey6;
  if (kc == GCKeyCodeSeven) return GHOST_kKey7;
  if (kc == GCKeyCodeEight) return GHOST_kKey8;
  if (kc == GCKeyCodeNine) return GHOST_kKey9;
  if (kc == GCKeyCodeZero) return GHOST_kKey0;
  if (kc == GCKeyCodeSpacebar) return GHOST_kKeySpace;
  if (kc == GCKeyCodeReturnOrEnter) return GHOST_kKeyEnter;
  if (kc == GCKeyCodeEscape) return GHOST_kKeyEsc;
  if (kc == GCKeyCodeDeleteOrBackspace) return GHOST_kKeyBackSpace;
  if (kc == GCKeyCodeDeleteForward) return GHOST_kKeyDelete;
  if (kc == GCKeyCodeTab) return GHOST_kKeyTab;
  if (kc == GCKeyCodeLeftShift) return GHOST_kKeyLeftShift;
  if (kc == GCKeyCodeRightShift) return GHOST_kKeyRightShift;
  if (kc == GCKeyCodeLeftControl) return GHOST_kKeyLeftControl;
  if (kc == GCKeyCodeRightControl) return GHOST_kKeyRightControl;
  if (kc == GCKeyCodeLeftAlt) return GHOST_kKeyLeftAlt;
  if (kc == GCKeyCodeRightAlt) return GHOST_kKeyRightAlt;
  if (kc == GCKeyCodeLeftGUI) return GHOST_kKeyLeftOS;
  if (kc == GCKeyCodeRightGUI) return GHOST_kKeyRightOS;
  if (kc == GCKeyCodeUpArrow) return GHOST_kKeyUpArrow;
  if (kc == GCKeyCodeDownArrow) return GHOST_kKeyDownArrow;
  if (kc == GCKeyCodeLeftArrow) return GHOST_kKeyLeftArrow;
  if (kc == GCKeyCodeRightArrow) return GHOST_kKeyRightArrow;
  if (kc == GCKeyCodeHyphen) return GHOST_kKeyMinus;
  if (kc == GCKeyCodeEqualSign) return GHOST_kKeyEqual;
  if (kc == GCKeyCodeOpenBracket) return GHOST_kKeyLeftBracket;
  if (kc == GCKeyCodeCloseBracket) return GHOST_kKeyRightBracket;
  if (kc == GCKeyCodeBackslash) return GHOST_kKeyBackslash;
  if (kc == GCKeyCodeSemicolon) return GHOST_kKeySemicolon;
  if (kc == GCKeyCodeQuote) return GHOST_kKeyQuote;
  if (kc == GCKeyCodeGraveAccentAndTilde) return GHOST_kKeyAccentGrave;
  if (kc == GCKeyCodeComma) return GHOST_kKeyComma;
  if (kc == GCKeyCodePeriod) return GHOST_kKeyPeriod;
  if (kc == GCKeyCodeSlash) return GHOST_kKeySlash;
  if (kc == GCKeyCodeF1) return GHOST_kKeyF1;
  if (kc == GCKeyCodeF2) return GHOST_kKeyF2;
  if (kc == GCKeyCodeF3) return GHOST_kKeyF3;
  if (kc == GCKeyCodeF4) return GHOST_kKeyF4;
  if (kc == GCKeyCodeF5) return GHOST_kKeyF5;
  if (kc == GCKeyCodeF6) return GHOST_kKeyF6;
  if (kc == GCKeyCodeF7) return GHOST_kKeyF7;
  if (kc == GCKeyCodeF8) return GHOST_kKeyF8;
  if (kc == GCKeyCodeF9) return GHOST_kKeyF9;
  if (kc == GCKeyCodeF10) return GHOST_kKeyF10;
  if (kc == GCKeyCodeF11) return GHOST_kKeyF11;
  if (kc == GCKeyCodeF12) return GHOST_kKeyF12;
  return GHOST_kKeyUnknown;
}
/* ==== end build-9 helpers ==== */
'''

mtd = r'''- (void)ghostInstallKeyboardHandler
{
  GCKeyboard *kbd = [GCKeyboard coalescedKeyboard];
  if (!kbd || !kbd.keyboardInput) {
    return;
  }
  GHOST_SystemIOS *sys = system;
  GHOST_WindowIOS *win = window;
  ghost_ios_log(@"HW keyboard handler installed");
  kbd.keyboardInput.keyChangedHandler =
      ^(GCKeyboardInput *kbi, GCControllerButtonInput *key, GCKeyCode kc, BOOL pressed) {
        GHOST_TKey gkey = ghost_key_from_gc(kc);
        ghost_ios_log([NSString stringWithFormat:@"KEY gccode=%ld pressed=%d -> ghost=%d",
                                                  (long)kc, (int)pressed, (int)gkey]);
        if (gkey != GHOST_kKeyUnknown) {
          sys->pushEvent(new GHOST_EventKey(GHOST_GetMilliSeconds((GHOST_SystemHandle)sys),
                                            pressed ? GHOST_kEventKeyDown : GHOST_kEventKeyUp,
                                            win,
                                            gkey,
                                            false,
                                            nullptr));
        }
      };
}

- (void)registerGestureRecognizers
{
'''

edit(W, [
 # helpers after the includes
 ("#include <unordered_map>\n", helpers, "ios-input-helpers"),
 # keyboard handler method, inserted before registerGestureRecognizers
 ("- (void)registerGestureRecognizers\n{\n", mtd, "keyboard-method"),
 # install hook at end of the keyboard-init method
 ("""                                             selector:@selector(externalKeyboardChange:)
                                                 name:GCKeyboardDidDisconnectNotification
                                               object:nil];
  }
}
""",
  """                                             selector:@selector(externalKeyboardChange:)
                                                 name:GCKeyboardDidDisconnectNotification
                                               object:nil];
  }

  /* build-9 ADDED: install hardware keyboard shortcut handler now + on connect. */
  [[NSNotificationCenter defaultCenter] addObserver:self
                                           selector:@selector(ghostInstallKeyboardHandler)
                                               name:GCKeyboardDidConnectNotification
                                             object:nil];
  [self ghostInstallKeyboardHandler];
}
""",
  "keyboard-install-hook"),
 # trackpad: allow indirect pointer (trackpad/mouse) on tap (fixes click-select)
 ("  tap_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect) ];\n",
  "  tap_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect), @(UITouchTypeIndirectPointer) ];\n",
  "tap-indirect"),
 # trackpad: allow indirect pointer on 1-finger pan (fixes trackpad drag)
 ("  pan_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect) ];\n",
  "  pan_gesture_recognizer.allowedTouchTypes = @[ @(UITouchTypePencil), @(UITouchTypeDirect), @(UITouchTypeIndirectPointer) ];\n",
  "pan-indirect"),
 # trackpad: enable scroll (two-finger trackpad swipe -> view navigation)
 ("  [window->getView() addGestureRecognizer:pan_gesture_recognizer];\n",
  "  if (@available(iOS 13.4, *)) {\n    pan_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskAll;\n  }\n  [window->getView() addGestureRecognizer:pan_gesture_recognizer];\n",
  "pan-scrolltypes"),
 ("  [window->getView() addGestureRecognizer:pan2f_gesture_recognizer];\n",
  "  if (@available(iOS 13.4, *)) {\n    pan2f_gesture_recognizer.allowedScrollTypesMask = UIScrollTypeMaskAll;\n  }\n  [window->getView() addGestureRecognizer:pan2f_gesture_recognizer];\n",
  "pan2f-scrolltypes"),
])
print("ALL PATCHES APPLIED OK")
