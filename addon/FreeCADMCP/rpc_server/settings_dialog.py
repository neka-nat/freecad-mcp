"""One dialog for every MCP setting, reachable from the gear on the MCP toolbar.

Previously each setting was its own toolbar entry: two checkable commands plus a
separate "Configure Allowed IPs" prompt. That spread related choices across
three controls, gave no view of the current state, and -- because the checkable
commands could not be trusted to report their own state -- was the surface where
the auto-start bug hid. A single dialog reads the settings file once, shows
everything together, and writes back atomically.
"""

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

from rpc_server.ip_filter import validate_allowed_ips
from rpc_server.settings import CAPABILITIES, load_settings, save_settings


_RESTART_KEYS = ("remote_enabled", "allowed_ips")


class MCPSettingsDialog(QtWidgets.QDialog):
    """Modal settings editor. Writes only on OK."""

    def __init__(self, parent=None):
        super().__init__(parent or FreeCADGui.getMainWindow())
        self.setWindowTitle("MCP Server Settings")
        self.setMinimumWidth(430)
        self._initial = load_settings()
        self._build_ui()
        self._load_values()

    # ---------------------------------------------------------------- building
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(self.status_label)
        layout.addSpacing(6)

        startup_box = QtWidgets.QGroupBox("Startup")
        startup_layout = QtWidgets.QVBoxLayout(startup_box)
        self.auto_start_check = QtWidgets.QCheckBox(
            "Start the MCP server automatically when FreeCAD launches"
        )
        startup_layout.addWidget(self.auto_start_check)
        layout.addWidget(startup_box)

        network_box = QtWidgets.QGroupBox("Network")
        network_layout = QtWidgets.QVBoxLayout(network_box)
        self.remote_check = QtWidgets.QCheckBox(
            "Allow remote connections (bind 0.0.0.0 instead of 127.0.0.1)"
        )
        self.remote_check.toggled.connect(self._on_remote_toggled)
        network_layout.addWidget(self.remote_check)

        ip_row = QtWidgets.QHBoxLayout()
        self.ip_label = QtWidgets.QLabel("Allowed IPs:")
        ip_row.addWidget(self.ip_label)
        self.ip_edit = QtWidgets.QLineEdit()
        self.ip_edit.setPlaceholderText("127.0.0.1, 192.168.1.0/24")
        ip_row.addWidget(self.ip_edit)
        network_layout.addLayout(ip_row)

        self.ip_hint = QtWidgets.QLabel(
            "Comma-separated addresses or CIDR subnets. Only these may connect."
        )
        self.ip_hint.setWordWrap(True)
        network_layout.addWidget(self.ip_hint)
        layout.addWidget(network_box)

        perms_box = QtWidgets.QGroupBox("What the MCP client is allowed to do")
        perms_layout = QtWidgets.QVBoxLayout(perms_box)
        intro = QtWidgets.QLabel(
            "Inspecting the model is always allowed. Everything below is off by "
            "default and applies to <i>any</i> client that reaches the server."
        )
        intro.setWordWrap(True)
        perms_layout.addWidget(intro)

        self.capability_checks = {}
        for key, label, gated in CAPABILITIES:
            check = QtWidgets.QCheckBox(label)
            check.setToolTip(f"Controls: {gated}")
            perms_layout.addWidget(check)
            self.capability_checks[key] = check

        self.capability_checks["allow_code_execution"].toggled.connect(
            self._on_code_execution_toggled
        )

        self.code_warning = QtWidgets.QLabel(
            "⚠ Executing arbitrary Python runs with FreeCAD's full privileges. It can "
            "read and write any file and start any process, so it overrides every other "
            "box here — leave it off unless you need it."
        )
        self.code_warning.setWordWrap(True)
        self.code_warning.setStyleSheet("color: #b35a00;")
        perms_layout.addWidget(self.code_warning)
        layout.addWidget(perms_box)

        self.warning_label = QtWidgets.QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        layout.addWidget(self.warning_label)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self):
        self.auto_start_check.setChecked(bool(self._initial.get("auto_start_rpc", False)))
        self.remote_check.setChecked(bool(self._initial.get("remote_enabled", False)))
        self.ip_edit.setText(str(self._initial.get("allowed_ips", "127.0.0.1")))
        for key, check in self.capability_checks.items():
            check.setChecked(bool(self._initial.get(key, False)))
        self._on_remote_toggled(self.remote_check.isChecked())
        self._on_code_execution_toggled(
            self.capability_checks["allow_code_execution"].isChecked()
        )
        self._refresh_status()

    def _on_code_execution_toggled(self, checked):
        # Make the override explicit rather than leaving a permanent warning the
        # user learns to ignore.
        self.code_warning.setVisible(checked)

    # ----------------------------------------------------------------- helpers
    def _refresh_status(self):
        from rpc_server import commands as C

        state = C._server_state()
        colour, text = {
            "on": ("#2ecc40", "running"),
            "off": ("#ff4136", "stopped"),
            "busy": ("#ff9500", "stopping"),
        }[state]
        self.status_label.setText(
            f'Server is <b><span style="color:{colour}">{text}</span></b> '
            f"&nbsp;&middot;&nbsp; {C._server_address()}"
        )

    def _on_remote_toggled(self, checked):
        for widget in (self.ip_label, self.ip_edit, self.ip_hint):
            widget.setEnabled(checked)

    # ------------------------------------------------------------------ saving
    def accept(self):
        allowed_ips = self.ip_edit.text().strip()

        # Only gate on IP validity when remote is actually on: an invalid string
        # left behind in a disabled field must not block turning remote OFF.
        if self.remote_check.isChecked():
            valid, errors = validate_allowed_ips(allowed_ips)
            if errors:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid IP Configuration",
                    "Fix these before enabling remote connections:\n\n"
                    + "\n".join(f"• {e}" for e in errors),
                )
                return
            allowed_ips = ", ".join(valid)

        new_settings = dict(self._initial)
        new_settings.update({
            "auto_start_rpc": self.auto_start_check.isChecked(),
            "remote_enabled": self.remote_check.isChecked(),
            "allowed_ips": allowed_ips or "127.0.0.1",
        })
        for key, check in self.capability_checks.items():
            new_settings[key] = check.isChecked()

        # Enabling code execution while listening on 0.0.0.0 hands remote
        # callers arbitrary code execution on this machine. Say so once, plainly,
        # at the moment the combination is created.
        if new_settings["allow_code_execution"] and new_settings["remote_enabled"]:
            answer = QtWidgets.QMessageBox.warning(
                self,
                "Remote code execution",
                "You are allowing arbitrary Python execution AND remote "
                f"connections ({new_settings['allowed_ips']}).\n\n"
                "Anyone who can reach this machine on port 9875 from those "
                "addresses can run any code as your user.\n\nContinue?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return

        save_settings(new_settings)

        from rpc_server import commands as C
        C.sync_toggle_states_now()

        changed = [k for k in _RESTART_KEYS if new_settings.get(k) != self._initial.get(k)]
        if changed and C._server_state() == "on":
            QtWidgets.QMessageBox.information(
                self,
                "Restart the MCP server",
                "Network settings changed while the server is running.\n\n"
                "The bind address and IP filter are only read when the server "
                "starts, so click MCP On/Off twice to apply them.",
            )
        FreeCAD.Console.PrintMessage(f"MCP settings saved: {new_settings}\n")
        super().accept()


def show_dialog():
    """Open the settings dialog modally."""
    try:
        MCPSettingsDialog().exec_()
    except Exception as e:
        FreeCAD.Console.PrintError(f"MCP: could not open settings dialog: {e}\n")
