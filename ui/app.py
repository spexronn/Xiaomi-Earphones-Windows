"""GUI uygulaması: sistem tepsisi + ana pencere + Bluetooth motoru."""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from services import autostart
from services.backend import Backend, LinkState
from services.config import Settings
from services.logging_setup import set_debug
from services.paths import APP_NAME
from services.single_instance import GUI_SERVER_NAME

from . import theme
from .dialogs import DiagnosticsDialog, LogViewer, SettingsDialog
from .find_dialog import FindDialog
from .graphics import app_icon, tray_icon, ui_icon
from .main_window import MainWindow

log = logging.getLogger("gui")


def notify_running_instance(message: bytes = b"show") -> bool:
    """Çalışan arayüze mesaj gönderir: show | find:LEFT|RIGHT|BOTH | stopfind."""
    sock = QLocalSocket()
    sock.connectToServer(GUI_SERVER_NAME)
    if sock.waitForConnected(800):
        sock.write(message)
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return True
    return False


class GuiApp:
    def __init__(self, app: QApplication, show_window: bool) -> None:
        self.app = app
        self.settings = Settings.load()
        set_debug(self.settings.diagnostic_mode)
        app.setWindowIcon(app_icon())
        app.setQuitOnLastWindowClosed(False)

        self.window = MainWindow(self.settings)
        self.window.refresh_requested.connect(self.refresh)
        self.window.settings_requested.connect(self.open_settings)
        self.window.diagnostics_requested.connect(self.open_diagnostics)
        self.window.find_requested.connect(self.open_find)
        self.window.close_requested.connect(self.on_window_close)

        self.backend = Backend(self.settings)
        self.backend.allow_exit_on_disconnect = not show_window  # manuel açılışta hemen kapanma
        self.backend.state_changed.connect(self.on_state, Qt.ConnectionType.QueuedConnection)
        self.backend.device_gone.connect(self.on_device_gone, Qt.ConnectionType.QueuedConnection)
        self.diag_dialog: DiagnosticsDialog | None = None
        self.settings_dialog: SettingsDialog | None = None
        self.find_dialog: FindDialog | None = None
        self._was_finding: str | None = None

        self._build_tray()
        self._server = QLocalServer()
        QLocalServer.removeServer(GUI_SERVER_NAME)
        self._server.newConnection.connect(self._on_ipc)
        self._server.listen(GUI_SERVER_NAME)

        self.manual = show_window
        self.backend.start()
        if show_window or self.settings.show_window_on_connect:
            self.show_window()
        else:
            QTimer.singleShot(4000, self._trim_if_hidden)
        log.info("Arayüz başladı (manuel=%s)", show_window)

    def _trim_if_hidden(self) -> None:
        """Pencere kapalıyken Qt'nin kullanılmayan bellek sayfalarını bırak."""
        if not self.window.isVisible():
            from services.efficiency import trim_working_set
            trim_working_set()

    # ------------------------------------------------------------- tepsi
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(tray_icon(None, False, False, "#888"))
        self.tray.setToolTip(f"{APP_NAME}\nBağlanıyor…")
        menu = QMenu()
        self.menu_status = QAction("Bağlanıyor…"); self.menu_status.setEnabled(False)
        menu.addAction(self.menu_status)
        menu.addSeparator()
        p = theme.get(self.settings.theme)
        find_menu = QMenu("Kulaklığı bul", menu)
        find_menu.setIcon(ui_icon("sound", p.text, 14))
        for text, key in (("Her iki kulaklık", "BOTH"), ("Sol kulaklık", "LEFT"), ("Sağ kulaklık", "RIGHT")):
            a = QAction(text, find_menu); a.triggered.connect(lambda _c=False, k=key: self.find_from_tray(k))
            find_menu.addAction(a)
        find_menu.addSeparator()
        a = QAction("Pencerede aç…", find_menu); a.triggered.connect(self.open_find); find_menu.addAction(a)
        self.menu_find = find_menu
        menu.addMenu(find_menu)
        self.menu_stop_find = QAction("Çalmayı durdur", menu)
        self.menu_stop_find.setIcon(ui_icon("stop", p.red, 14))
        self.menu_stop_find.triggered.connect(self.backend_stop_find)
        self.menu_stop_find.setVisible(False)
        menu.addAction(self.menu_stop_find)
        menu.addSeparator()
        for text, fn in (("Göster", self.show_window), ("Yenile", self.refresh),
                         ("Ayarlar", self.open_settings), ("Tanılama", self.open_diagnostics)):
            a = QAction(text, menu); a.triggered.connect(fn); menu.addAction(a)
        menu.addSeparator()
        q = QAction("Çıkış", menu); q.triggered.connect(self.quit); menu.addAction(q)
        menu.setStyleSheet(theme.stylesheet(p))
        find_menu.setStyleSheet(menu.styleSheet())
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.window.isVisible() and not self.window.isMinimized():
                self.window.hide()
            else:
                self.show_window()

    def _on_ipc(self) -> None:
        c = self._server.nextPendingConnection()
        if c:
            c.readyRead.connect(lambda: self._handle_ipc(bytes(c.readAll().data())))

    def _handle_ipc(self, data: bytes) -> None:
        msg = data.decode("ascii", "ignore").strip()
        if msg.startswith("find"):
            target = msg.partition(":")[2].upper() or "BOTH"
            self.find_from_tray(target if target in ("LEFT", "RIGHT", "BOTH") else "BOTH")
        elif msg == "stopfind":
            self.backend_stop_find()
        else:
            self.show_window()

    # ------------------------------------------------------- kulaklığı bul
    def open_find(self) -> FindDialog:
        if self.find_dialog is None:
            d = FindDialog(self.settings)
            d.find_requested.connect(self.backend.find_earbuds)
            d.stop_requested.connect(self.backend.stop_finding)
            self.find_dialog = d
        self.find_dialog.update_state(self.backend.state)
        self.find_dialog.show(); self.find_dialog.raise_(); self.find_dialog.activateWindow()
        return self.find_dialog

    def find_from_tray(self, target: str) -> None:
        """Tepsi menüsü / komut satırından: pencereyi aç ve hemen çalmaya başla."""
        d = self.open_find()
        if not self.backend.can_find():
            self.tray.showMessage(APP_NAME, "Kulaklık PC'ye bağlı değil ya da protokol oturumu hazır değil.",
                                  app_icon(), 3500)
            return
        d.start_now(target)

    def backend_stop_find(self) -> None:
        self.backend.stop_finding()

    def _find_from_settings(self, target: str) -> None:
        # Ayarlar'daki süre kaydedilmemiş olsa bile hemen geçerli olsun
        if self.settings_dialog:
            self.settings.find_duration = self.settings_dialog.find_dur.value()
        self.backend.find_earbuds(target)

    # ------------------------------------------------------------- eylemler
    def show_window(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def refresh(self) -> None:
        self.backend.refresh()

    def on_window_close(self) -> None:
        if self.settings.minimize_to_tray and (self.backend.state.acl_connected or not self.manual):
            self.window.hide()
            QTimer.singleShot(1500, self._trim_if_hidden)
            if not getattr(self, "_tray_hint_shown", False):
                self._tray_hint_shown = True
                self.tray.showMessage(APP_NAME, "Simge tepsisinde çalışmaya devam ediyor. "
                                      "Kulaklık bağlantısı kesilince otomatik kapanır.", app_icon(), 3500)
        else:
            self.quit()

    def open_settings(self) -> None:
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_(); return
        dlg = SettingsDialog(self.settings, self.window if self.window.isVisible() else None)
        self.settings_dialog = dlg
        self.backend.paired_list.connect(dlg.set_paired, Qt.ConnectionType.QueuedConnection)
        self.backend.request_paired_list()
        dlg.saved.connect(self.on_settings_saved)
        dlg.find_requested.connect(self._find_from_settings)
        dlg.stop_find_requested.connect(self.backend.stop_finding)
        dlg.set_find_state(self.backend.state)
        dlg.open_logs.connect(lambda: LogViewer(self.settings, dlg).exec())
        dlg.finished.connect(lambda _r: self._disconnect_paired(dlg))
        dlg.show()

    def _disconnect_paired(self, dlg) -> None:
        try:
            self.backend.paired_list.disconnect(dlg.set_paired)
        except (RuntimeError, TypeError):
            pass

    def on_settings_saved(self) -> None:
        set_debug(self.settings.diagnostic_mode)
        p = theme.get(self.settings.theme)
        self.window.apply_theme()
        self.tray_menu.setStyleSheet(theme.stylesheet(p))
        self.menu_find.setStyleSheet(self.tray_menu.styleSheet())
        self.menu_find.setIcon(ui_icon("sound", p.text, 14))
        self.menu_stop_find.setIcon(ui_icon("stop", p.red, 14))
        if self.find_dialog:
            self.find_dialog.apply_theme()
            self.find_dialog.update_state(self.backend.state)
        self.backend.settings_changed()
        log.info("Ayarlar kaydedildi")

    def open_diagnostics(self) -> None:
        if self.diag_dialog is None:
            d = DiagnosticsDialog(self.settings)
            d.start_requested.connect(self.backend.run_diagnostics)
            self.backend.diagnostic_progress.connect(d.on_progress, Qt.ConnectionType.QueuedConnection)
            self.backend.diagnostic_done.connect(d.on_done, Qt.ConnectionType.QueuedConnection)
            self.backend.packet.connect(d.on_packet, Qt.ConnectionType.QueuedConnection)
            self.diag_dialog = d
        self.diag_dialog.show(); self.diag_dialog.raise_(); self.diag_dialog.activateWindow()

    # ------------------------------------------------------------- durum
    def on_state(self, st: LinkState) -> None:
        self.window.update_state(st)
        if self.find_dialog:
            self.find_dialog.update_state(st)
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.set_find_state(st)
        self.menu_find.setEnabled(bool(st.acl_connected and st.protocol_ready))
        self.menu_stop_find.setVisible(bool(st.finding))
        if st.finding and st.finding != self._was_finding and not (self.find_dialog and self.find_dialog.isVisible()):
            self.tray.showMessage(APP_NAME, "Kulaklık çalıyor. Durdurmak için tepsi menüsünden "
                                  "'Çalmayı durdur'u seçin.", app_icon(), 3000)
        self._was_finding = st.finding
        p = theme.get(self.settings.theme)
        b = st.snapshot.battery
        live = st.acl_connected and (st.protocol_ready or st.fallback_active)
        levels = [x.level for x in (b.left, b.right) if x.level is not None] if live else []
        lvl = min(levels) if levels else None
        charging = live and (b.left.charging or b.right.charging)
        self.tray.setIcon(tray_icon(lvl, st.acl_connected, charging, theme.level_color(p, lvl)))

        def fmt(u):
            return "--" if (not live or u.level is None) else f"%{u.level}{' ⚡' if u.charging else ''}"
        name = st.snapshot.model or (st.device.name if st.device else "Xiaomi Buds")
        if live:
            line = f"Sol {fmt(b.left)}  ·  Sağ {fmt(b.right)}  ·  Kutu {fmt(b.case)}"
        else:
            line = st.status_text
        self.tray.setToolTip(f"{name}\n{line}"[:127])
        self.menu_status.setText(line)

    def on_device_gone(self) -> None:
        log.info("Kulaklık bağlantısı kesildi → arayüz kapanıyor")
        self.quit()

    def quit(self) -> None:
        log.info("Arayüz kapatılıyor")
        self.tray.hide()
        self._server.close()
        self.backend.stop()
        self.app.quit()


def run_gui(show_window: bool) -> int:
    from services.efficiency import normal_priority
    from services.single_instance import GUI_MUTEX, InstanceLock
    normal_priority()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("SPEXRON SOFT")
    lock = InstanceLock(GUI_MUTEX)
    if not lock.acquire():
        if show_window:
            notify_running_instance()
        return 0
    s = Settings.load()
    autostart.sync(s.run_at_startup)
    gui = GuiApp(app, show_window)
    code = app.exec()
    lock.release()
    del gui
    return code
