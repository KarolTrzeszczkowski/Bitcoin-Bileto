from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from electroncash.i18n import _
from electroncash.address import Address
from electroncash_gui.qt.util import *
from electroncash.util import PrintError, print_error, age, Weak, InvalidPassword, NotEnoughFunds
from electroncash.transaction import Transaction, TYPE_ADDRESS
from electroncash_gui.qt.transaction_dialog import show_transaction
from electroncash_gui.qt.amountedit  import BTCAmountEdit




class FundDialog(QDialog,MessageBoxMixin, PrintError):

    def __init__(self, parent, plugin, wallet_name, password, tab):
        QDialog.__init__(self, parent)
        self.main_window = parent
        self.password = password
        self.wallet = parent.wallet
        self.plugin = plugin
        self.network = parent.network
        self.wallet_name = wallet_name
        distributions=['Regular Distribution', 'Poisson']
        vbox = QVBoxLayout()
        self.setLayout(vbox)
        self.tab = Weak.ref(tab)
        self.number = 0
        distributions_combo = QComboBox()
        distributions_combo.addItems(distributions)
        distributions_combo.setCurrentIndex(0)
        self.selected_distribution = 0
        def on_distribution():
            self.selected_distribution = distributions[distributions_combo.currentIndex()]
        distributions_combo.currentIndexChanged.connect(on_distribution)

        l = QLabel("<b>%s</b>" % (_("Fund Biletoj")))
        vbox.addWidget(l)
        vbox.addWidget(distributions_combo)
        self.number_wid = BTCAmountEdit(self.main_window.get_decimal_point)

        self.number_wid.textEdited.connect(self.fund_parameters_changed)
        vbox.addWidget(self.number_wid)
        self.number_wid.setMaximumWidth(70)
        tab = self.tab()
        self.selected = tab.tu.selectedItems()
        self.b = QPushButton(_("Fund"))
        self.b.clicked.connect(self.do_fund)
        vbox.addWidget(self.b)
        self.b.setDisabled(True)
        vbox.addStretch(1)

    def fund_parameters_changed(self):
        try:
            self.number = self.number_wid.get_amount()
        except Exception as e:
            print(e)
            self.b.setDisabled(True)
            pass
        else:
            self.b.setDisabled(False)

    def closeEvent(self, QCloseEvent):
        tab=self.tab()
        tab.plugin.on_fund_dialog_closed(self.wallet_name)

    def do_fund(self):
        print("funding")
        selected = self.selected
        if not selected:
            return
        if isinstance(selected[0].data(1, Qt.UserRole), Address):
            addresses = [s.data(1, Qt.UserRole) for s in selected]
        else:
            addresses = selected[0].data(1, Qt.UserRole)
        outputs = []
        am = self.number//len(addresses)
        tab = self.tab()
        tab.get_password()
        password = tab.password
        for a in addresses:
            outputs.append((TYPE_ADDRESS,a,am))
        try:
            tx = self.wallet.mktx(outputs, password, tab.main_window.config)
        except NotEnoughFunds:
            return self.show_critical(_("Not enough balance to fund biletoj."))
        except Exception as e:
            return self.show_critical(repr(e))
        #self.main_window.show_message("Click \'broadcast\' to fund biletoj.")
        show_transaction(tx, self.main_window, "Fund biletoj", prompt_if_unsaved=True)
