"""Verify screenshot dimensions and padding with FreeCAD's real Qt image API."""

from pathlib import Path
import sys
import tempfile

try:
    from PySide6 import QtGui
except ImportError:
    print("NATIVE_CAPTURE_QT6_UNAVAILABLE", flush=True)
else:
    sys.path.insert(0, ADDON_PATH)
    from rpc_server.view_manager import _fit_capture_image

    with tempfile.TemporaryDirectory() as folder:
        for source_size, target_size in (
            ((1600, 900), (800, 600)),
            ((900, 1600), (600, 800)),
            ((1600, 900), (800, 450)),
            ((100, 50), (101, 101)),
        ):
            for density in (1, 2):
                source = QtGui.QImage(*source_size, QtGui.QImage.Format_ARGB32)
                source.fill(QtGui.QColor("red"))
                source.setDevicePixelRatio(density)
                fitted = _fit_capture_image(source, *target_size)
                assert (fitted.width(), fitted.height()) == target_size
                assert fitted.devicePixelRatio() == 1
                path = str(Path(folder) / "capture.png")
                assert fitted.save(path, "PNG")
                saved = QtGui.QImage(path)
                width, height = target_size
                assert (saved.width(), saved.height()) == target_size
                assert saved.pixelColor(width // 2, height // 2) == QtGui.QColor("red")
                if source_size[0] * height != source_size[1] * width:
                    assert saved.pixelColor(0, 0).alpha() == 0
                    assert saved.pixelColor(width - 1, height - 1).alpha() == 0
                else:
                    assert saved.pixelColor(0, 0) == QtGui.QColor("red")
                    assert saved.pixelColor(width - 1, height - 1) == QtGui.QColor("red")
    print("NATIVE_CAPTURE_SIZE_OK", flush=True)
