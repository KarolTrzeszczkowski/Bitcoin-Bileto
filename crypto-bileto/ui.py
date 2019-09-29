from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from electroncash.i18n import _
from electroncash.address import Address
from electroncash_gui.qt.transaction_dialog import show_transaction
from electroncash.wallet import sweep
from electroncash_gui.qt.util import *
from electroncash.transaction import Transaction, TYPE_ADDRESS
from electroncash.util import PrintError, print_error, age, Weak, InvalidPassword, NotEnoughFunds
import random,  tempfile, string, os, queue
from electroncash.bitcoin import encrypt_message, deserialize_privkey, public_key_from_private_key
from enum import IntEnum


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


    def get_selected(self):
        return self.currentItem().data(0, Qt.UserRole)


    def do_sweep(self, selected):
        if not selected:
            return
        if isinstance(selected[0].data(2, Qt.UserRole), str):
            privkeys = [s.data(2, Qt.UserRole) for s in selected]
        elif isinstance(selected[0].data(2, Qt.UserRole),list):
            privkeys = selected[0].data(2, Qt.UserRole)
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
        menu.exec_(self.viewport().mapToGlobal(position))
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
        sum = ans["confirmed"]+ans["unconfirmed"]
        return sum


    def on_update(self):
        self.clear()
        tab = self.tab()
        batches = tab.batches
        addresses = tab.addresses 
        if not tab :
            return
        for label, batch_addr in addresses.items():
            item = QTreeWidgetItem([label, None])
            item.setFont(0, self.monospace_font)
            item.setTextAlignment(0, Qt.AlignLeft)
            item.setData(0,Qt.UserRole,label)
            item.setData(1, Qt.UserRole, batch_addr)
            item.setData(2,Qt.UserRole,batches[label])
            self.addChild(item)
            for i, a in enumerate(batch_addr):
                b = self.address_balance(a)
                addr_item = SortableTreeWidgetItem([a.to_ui_string(),str(b)])
                addr_item.setData(0,Qt.UserRole,label)
                addr_item.setData(1,Qt.UserRole, a)
                addr_item.setData(2,Qt.UserRole,batches[label][i])
                item.addChild(addr_item)

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
        self.batches = dict()
        self.addresses = dict()
        self.main_window = parent
        cancel = False
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
        self.sleeper = queue.Queue()


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

    def load(self):
        fileName = self.main_window.getOpenFileName("Load Biletoj", "*")
        try:
            with open(fileName, "r") as f:
                file_content = f.read()
                batch = self.decrypt(file_content)
                self.batches[batch[0]] = batch[1:] #the first element is batch label
                self.addresses[batch[0]] = self.generate_addresses(batch[1:])
            self.tu.update()
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
        return "InterWalletTransfer.Transfer"



    def switch_signal_slot(self):
        ''' Runs in GUI (main) thread '''
        self.plugin.switch_to(NewBatchTab, self.wallet_name, None, None, None)

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
