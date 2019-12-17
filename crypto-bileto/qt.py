from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5.QtWidgets import *
from electroncash_gui.qt.util import *


import weakref


import electroncash.version, os, threading
from electroncash.i18n import _
from electroncash.plugins import BasePlugin, hook
from electroncash.util import finalization_print_error, PrintError
from electroncash_gui.qt.main_window import ElectrumWindow




class Plugin(BasePlugin):
    electrumcash_qt_gui = None
    # There's no real user-friendly way to enforce this.  So for now, we just calculate it, and ignore it.
    is_version_compatible = True

    def __init__(self, parent, config, name):
        BasePlugin.__init__(self, parent, config, name)

        self.wallet_windows = {}
        self.lw_tabs = {}
        self.lw_tab = {}
        self.create_dialogs = {}
        self.settings_dialogs = {}
        self.fund_dialogs = {}
        self.weak_dialogs = weakref.WeakSet()


    def fullname(self):
        return 'Crypto Bileto'

    def diagnostic_name(self):
        return "CryptoBileto"

    def description(self):
        return _("Crypto Bileto plugin")


    def on_close(self):
        """
        BasePlugin callback called when the wallet is disabled among other things.
        """
        for window in list(self.wallet_windows.values()):
            self.close_wallet(window.wallet)

    @hook
    def update_contact(self, address, new_entry, old_entry):
        self.print_error("update_contact", address, new_entry, old_entry)

    @hook
    def delete_contacts(self, contact_entries):
        self.print_error("delete_contacts", contact_entries)


    @hook
    def init_qt(self, qt_gui):
        """
        Hook called when a plugin is loaded (or enabled).
        """
        self.electrumcash_qt_gui = qt_gui
        # We get this multiple times.  Only handle it once, if unhandled.
        if len(self.wallet_windows):
            return

        # These are per-wallet windows.
        for window in self.electrumcash_qt_gui.windows:
            self.load_wallet(window.wallet, window)

    @hook
    def load_wallet(self, wallet, window):
        """
        Hook called when a wallet is loaded and a window opened for it.
        """
        wallet_name = window.wallet.basename()
        self.wallet_windows[wallet_name] = window
        self.print_error("wallet loaded")
        self.add_ui_for_wallet(wallet_name, window)
        self.refresh_ui_for_wallet(wallet_name)


    @hook
    def close_wallet(self, wallet):
        wallet_name = wallet.basename()
        window = self.wallet_windows[wallet_name]
        del self.wallet_windows[wallet_name]
        self.remove_ui_for_wallet(wallet_name, window)

    def has_settings_dialog(self):
        return True

    @staticmethod
    def _get_icon() -> QtGui.QIcon:
        if QtCore.QFile.exists(":icons/status_lagging.png"):
            icon = QtGui.QIcon(":icons/status_lagging.png")
        else:
            # png not found, must be new EC; try new EC icon -- svg
            icon = QtGui.QIcon(":icons/status_lagging.svg")
        return icon

    def add_ui_for_wallet(self, wallet_name, window):
        from .ui import BiletojTab
        l = BiletojTab(window, self, wallet_name)
        tab = window.create_list_tab(l)
        self.lw_tabs[wallet_name] = tab
        self.lw_tab[wallet_name] = l

        window.tabs.addTab(tab, self._get_icon(), _('Crypto Bileto'))

    def remove_ui_for_wallet(self, wallet_name, window):
        self.print_error("starting removing UI")
        wallet_tab = self.lw_tabs.get(wallet_name)
        widget = self.lw_tab.get(wallet_name)
        if wallet_tab is not None:
            if widget and callable(getattr(widget, 'kill_join', None)):
                widget.kill_join()  # kill thread, wait for up to 2.5 seconds for it to exit
            if widget and callable(getattr(widget, 'clean_up', None)):
                widget.clean_up()  # clean up wallet and stop its threads
            del self.lw_tab[wallet_name]
            del self.lw_tabs[wallet_name]
            if wallet_tab:
                i = window.tabs.indexOf(wallet_tab)
                window.tabs.removeTab(i)
                wallet_tab.deleteLater()
                self.print_error("Removed UI for", wallet_name)

    def refresh_ui_for_wallet(self, wallet_name):
        wallet_tab = self.lw_tabs.get(wallet_name)
        if wallet_tab:
            wallet_tab.update()
        wallet_tab = self.lw_tab.get(wallet_name)
        if wallet_tab:
            wallet_tab.update()

    def switch_to(self, mode, wallet_name, recipient_wallet, time, password):
        window=self.wallet_windows[wallet_name]
        try:
            l = mode(window, self, wallet_name, recipient_wallet,time, password=password)

            tab = window.create_list_tab(l)
            destroyed_print_error(tab)  # track object lifecycle
            finalization_print_error(tab)  # track object lifecycle

            old_tab = self.lw_tabs.get(wallet_name)
            i = window.tabs.indexOf(old_tab)

            self.lw_tabs[wallet_name] = tab
            self.lw_tab[wallet_name] = l
            window.tabs.addTab(tab, self._get_icon(), _('Crypto Bileto'))
            if old_tab:
                window.tabs.removeTab(i)
                old_tab.searchable_list.deleteLater()
                old_tab.deleteLater()  # Qt (and Python) will proceed to delete this widget
        except Exception as e:
            self.print_error(repr(e))
            return

    def settings_dialog(self, window, settings_signal=None):
        def window_parent(w):
            # this is needed because WindowModalDialog overrides window.parent
            if callable(w.parent): return w.parent()
            return w.parent
        while not isinstance(window, ElectrumWindow) and window and window_parent(window):
            # MacOS fixups -- we can get into a situation where we are created without the ElectrumWindow being an immediate parent or grandparent
            window = window_parent(window)
        assert window and isinstance(window, ElectrumWindow)

        wallet_name = window.wallet.basename()
        d = self._open_dialog(wallet_name, SettingsDialog, self.settings_dialogs)
        d.settings_updated_signal = settings_signal

    def open_create_dialog(self, wallet_name, entry=None):
        from .create_dialog import NewBatchDialog
        self._open_dialog(wallet_name, NewBatchDialog, self.create_dialogs)
        return


    def open_fund_dialog(self, wallet_name, tab):
        from .fund_dialog import FundDialog
        self._open_dialog(wallet_name,FundDialog, self.fund_dialogs)
        return

    def _open_dialog(self, wallet_name, dialog_class, dialog_container):
        dialog = dialog_container.get(wallet_name, None)
        if dialog is None:
            window = self.wallet_windows[wallet_name]
            dialog = dialog_class(window, self, wallet_name, None)
            self.weak_dialogs.add(dialog)
            dialog_container[wallet_name] = dialog
            dialog.show()
            return dialog
        else:
            dialog.raise_()
            dialog.activateWindow()
            dialog.show()
            return dialog

class SettingsDialog(QWidget,MessageBoxMixin):
    def __init__(self, parent, plugin, wallet_name, password=None):
        QWidget.__init__(self)
        self.settings_updated_signal=None
        self.setWindowTitle("Crypto Bileto settings")
        self.wallet = parent.wallet
        self.set_dir = QPushButton("Change directory")
        self.set_dir.clicked.connect(self.get_dir)
        self.working_directory = self.wallet.storage.get("bileto_path")
        self.label = QLabel(self.working_directory)
        vbox= QVBoxLayout(self)
        vbox.addWidget(QLabel("Working Directory:"))
        vbox.addWidget(self.label)
        vbox.addWidget(self.set_dir)

    def get_dir(self):
        dirname = QFileDialog.getExistingDirectory(self, "Bileto working dir", self.working_directory)
        try:
            assert(os.path.isdir(dirname))
        except:
            pass
        else:
            self.working_directory = dirname
            self.label.setText(dirname)
            self.wallet.storage.put("bileto_path", dirname)
            if self.settings_updated_signal:
                self.settings_updated_signal.emit()
            print(dirname)