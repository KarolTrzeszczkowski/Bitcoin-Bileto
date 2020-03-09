from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from electroncash.i18n import _
from electroncash.address import Address
from electroncash_gui.qt.transaction_dialog import show_transaction
from electroncash.wallet import sweep, ImportedPrivkeyWallet
from electroncash.storage import WalletStorage
from electroncash_gui.qt.util import *
from electroncash.util import PrintError, print_error, age, Weak, InvalidPassword, NotEnoughFunds
import random,  tempfile, string, os, queue
from electroncash.bitcoin import encrypt_message, deserialize_privkey, public_key_from_private_key
from .create_dialog import save_private_keys
from enum import IntEnum
import threading


def get_name(utxo) -> str:
    return "{}:{}".format(utxo['prevout_hash'], utxo['prevout_n'])





class BiletojList(MessageBoxMixin, PrintError, MyTreeWidget):

    update_sig = pyqtSignal()

    class DataRoles(IntEnum):
        Time = Qt.UserRole+1
        Name = Qt.UserRole+2

    def __init__(self, parent, tab):
        MyTreeWidget.__init__(self, parent, self.create_menu,[
            _('Address'),
            _('Amount'),
        ], stretch_column=0, deferred_updates=True)
        self.tab = Weak.ref(tab)
        self.main_window = parent
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(False)
        self.sending = None
        self.update_sig.connect(self.update)
        self.monospace_font = QFont(MONOSPACE_FONT)
        self.italic_font = QFont(); self.italic_font.setItalic(True)
        self.loaded_icon= self._get_loaded_icon()
        self.collected_icon = self._get_collected_icon()
        self.wallet = tab.wallet
        self.balances = dict()
        self.synch_event = threading.Event()
        lock = threading.Lock()
        self.synch = threading.Thread(target=self.synchronize, daemon=True, args=(self.synch_event,lock,))
        self.synch.start()

    def synchronize(self,e, lock):
        tab = self.tab()
        while True:
            e.wait()
            with lock:
                items = tab.addresses.items()
            for i, addrs in items:
                for a in addrs:
                    self.balances[a] = self.address_balance(a)
                    self.update_sig.emit()



    def get_selected(self):
        return self.currentItem().data(0, Qt.UserRole)


    def do_sweep(self, selected):
        if not selected:
            return
        if isinstance(selected[0].data(2, Qt.UserRole), str):
            privkeys = [s.data(2, Qt.UserRole) for s in selected]
        elif isinstance(selected[0].data(2, Qt.UserRole),list):
            privkeys = selected[0].data(2, Qt.UserRole)
        else:
            privkeys = []
        tab = self.tab()
        target = tab.wallet.get_unused_address()
        label = selected[0].data(0,Qt.UserRole)
        try:
            tx = sweep(privkeys, self.main_window.network, self.main_window.config, target)
        except ValueError:
            self.show_error("No confirmed coins found!")
        else:
            show_transaction(tx, self.main_window,"Sweep "+ label)

    def create_menu(self, position):
        menu = QMenu()
        selected = self.selectedItems()
        tab = self.tab()
        f = lambda: tab.plugin.open_fund_dialog(tab.wallet_name, tab)
        menu.addAction(_("Fund"), f)
        menu.addAction(_("Sweep"), lambda:self.do_sweep(selected))
        menu.addAction(_("Export selected ("+str(len(selected))+")"), lambda:self.export(selected))
        menu.exec_(self.viewport().mapToGlobal(position))
        pass


    def export(self, selected):
        if isinstance(selected[0].data(2, Qt.UserRole), str):
            new_batch = [s.data(2, Qt.UserRole) for s in selected]
        elif isinstance(selected[0].data(2, Qt.UserRole),list):
            new_batch = selected[0].data(2, Qt.UserRole)
        else:
            new_batch = []
        tab = self.tab()
        label = selected[0].data(0,Qt.UserRole)
        path = tab.file_paths[label]
        old_batch = tab.batches[label]
        differ = [p for p in old_batch if p not in new_batch]
        differ.insert(0,label + 'remaining')
        new_batch.insert(0, label + 'exported')
        differ = '\n'.join(differ)
        new_batch = '\n'.join(new_batch)
        pk = self.wallet.get_pubkey(False,0)
        filename = os.path.join(os.path.dirname(path), label + 'exported' + '_encrypted_private_keys')
        print("filename", filename)
        save_private_keys(new_batch, pk, filename)
        tab.load(filename)
        filename = os.path.join(os.path.dirname(path),  label + 'remaining' + '_encrypted_private_keys')
        print("filename", filename)
        save_private_keys(differ, pk, filename)
        tab.load(filename)
        pass

    @staticmethod
    def _get_loaded_icon() -> QIcon:
        if QFile.exists(":icons/tab_coins.png"):
            # old EC version
            return QIcon(":icons/tab_coins.png")
        else:
            # newer EC version
            return QIcon(":icons/tab_coins.svg")

    @staticmethod
    def _get_collected_icon() -> QIcon:
        if QFile.exists(":icons/tab_receive.png"):
            # current EC version
            return QIcon(":icons/tab_receive.png")
        else:
            # future EC version
            return QIcon(":icons/tab_receive.svg")

    def address_balance(self, a):
        msg =('blockchain.scripthash.get_balance', [a.to_scripthash_hex()])
        ans = self.main_window.network.synchronous_get(msg)
        s = ans["confirmed"]+ans["unconfirmed"]
        return s


    def on_update(self):
        root = self.invisibleRootItem()
        def remember_expanded(root):
            expanded = set()
            for j in range(0,root.childCount()):
                it = root.child(j)
                if it.isExpanded():
                    expanded.add(it.data(0,Qt.UserRole))
            print("expanded: ",expanded)
            return expanded
        def restore_expanded(root, expanded_item_labels):
            for j in range(0, root.childCount()):
                it = root.child(j)
                if it.data(0,Qt.UserRole) in expanded_item_labels:
                    it.setExpanded(True)
                    print("restored")

        expanded_item_labels = remember_expanded(root)
        self.clear()
        tab = self.tab()
        batches = tab.batches
        addresses = tab.addresses 
        if not tab :
            return
        for label, batch_addr in addresses.items():
            item = QTreeWidgetItem([label, ''])
            item.setFont(0, self.monospace_font)
            item.setTextAlignment(0, Qt.AlignLeft)
            item.setData(0,Qt.UserRole,label)
            item.setData(1, Qt.UserRole, batch_addr)
            item.setData(2,Qt.UserRole,batches[label])
            self.addChild(item)
            print(item.isExpanded())
            for i, a in enumerate(batch_addr):
                try:
                    b = self.main_window.format_amount(self.balances[a])
                except KeyError:
                    b = "Synchronizing..."
                addr_item = QTreeWidgetItem([a.to_ui_string(),str(b)])
                addr_item.setData(0,Qt.UserRole,label)
                addr_item.setData(1,Qt.UserRole, a)
                addr_item.setData(2,Qt.UserRole,batches[label][i])
                item.addChild(addr_item)
        restore_expanded(root,expanded_item_labels)


class BiletojTab(MessageBoxMixin, PrintError, QWidget):

    switch_signal = pyqtSignal()
    done_signal = pyqtSignal(str)
    set_label_signal = pyqtSignal(str, str)

    def __init__(self, parent, plugin, wallet_name, recipient_wallet=None, time=None, password=None):
        QWidget.__init__(self, parent)
        self.password = None
        self.wallet = parent.wallet
        self.wallet_name = wallet_name
        self.plugin = plugin
        self.imported_wallets = dict()
        self.batches = dict()
        self.addresses = dict()
        self.file_paths = dict()
        self.main_window = parent
        self.tu = BiletojList(parent, self)
        vbox = QVBoxLayout()
        self.setLayout(vbox)
        vbox.addWidget(self.tu)
        self.tu.update()
        self.abort_but = QPushButton(_("Load from file"))
        self.new_but = QPushButton(_("Bileto Creator"))
        hbox = QHBoxLayout()
        vbox.addLayout(hbox)
        self.abort_but.clicked.connect(self.load)
        self.new_but.clicked.connect(lambda: self.plugin.open_create_dialog(self.wallet_name))
        hbox.addWidget(self.abort_but)
        hbox.addWidget(self.new_but)
        self.set_label_signal.connect(self.set_label_slot)

    def get_password(self):
        if self.wallet.has_password():
            self.password = self.main_window.password_dialog()
            if not self.password:
                return
            try:
                self.wallet.keystore.get_private_key((True,0), self.password)
            except:
                self.show_error("Wrong password.")
                return

    def load(self, file_name = False):
        if not file_name:
            file_name = self.main_window.getOpenFileName("Load Biletoj", "*")
        try:
            with open(file_name, "r") as f:
                file_content = f.read()
                batch = self.decrypt(file_content)
                self.batches[batch[0]] = batch[1:] #the first element is batch label
                storage = WalletStorage(None,in_memory_only=True)
                #text = str.join(batch[1:])
                #self.imported_wallets[batch[0]](ImportedPrivkeyWallet.from_text(storage, text))
                self.addresses[batch[0]] = self.generate_addresses(batch[1:])
                self.file_paths[batch[0]] = file_name
            self.tu.synch_event.set()
            self.tu.synch_event.clear()
        except Exception as ex:
            print(ex)
            return
    
    def decrypt(self, f):
        length = len(self.wallet.get_addresses())
        self.get_password()
        for i in range(length):
            try:
                decrypted = self.wallet.keystore.decrypt_message((False,i), f.encode('utf8'),self.password).decode('utf8')
            except Exception as ex:
                print(ex)
                pass
            else:
                return decrypted.strip().split('\n')
        return f.strip().split('\n')

    def generate_addresses(self, batch):
        addresses = []
        for k in batch:
            k_type, private_key, compressed = deserialize_privkey(k)
            pubkey = public_key_from_private_key(private_key, compressed)
            address= Address.from_pubkey(pubkey)
            addresses.append(address)
        return addresses
            

    def filter(self, *args):
        ''' This is here because searchable_list must define a filter method '''

    def diagnostic_name(self):
        return "BiletojTab.Transfer"



    def done_slot(self, msg):
        self.abort_but.setText(_("Back"))
        self.show_message(msg)


    def set_label_slot(self, txid: str, label: str):
        ''' Runs in GUI (main) thread '''
        self.wallet.set_label(txid, label)

    def abort(self):
        self.kill_join()
        self.switch_signal.emit()

    def kill_join(self):
        pass

    def on_delete(self):
        pass

    def on_update(self):
        pass
