"""Auto-registration for the Spectral Wave Optics render engine.

This file lives in scripts/startup/, so Blender imports it and calls
register() at every launch -- the engine appears in Render Properties >
Render Engine next to Cycles and EEVEE with no addon installation, and
.blend files saved with engine 'SPECTRAL_WAVE' open ready to render.

The implementation lives in scripts/modules/spectral_engine.py. Guarded so
a missing dependency (numpy) degrades to a console message instead of a
startup traceback.
"""

try:
    import spectral_engine as _impl
    _IMPORT_ERROR = None
except Exception as _e:  # numpy missing, syntax issue, etc.
    _impl = None
    _IMPORT_ERROR = _e


def register():
    if _impl is None:
        print("[spectral] Spectral Wave Optics engine unavailable:",
              _IMPORT_ERROR)
        return
    _impl.register()


def unregister():
    if _impl is not None:
        _impl.unregister()
