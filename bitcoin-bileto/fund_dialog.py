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
from math import floor, ceil, sqrt




class FundDialog(QDialog,MessageBoxMixin, PrintError):

    def __init__(self, parent, plugin, wallet_name, password, tab):
        QDialog.__init__(self, parent)
        self.main_window = parent
        self.password = password
        self.wallet = parent.wallet
        self.plugin = plugin
        self.network = parent.network
        self.wallet_name = wallet_name
        self.distributions=["Regular Distribution", "TF Distribution", "TF-100", "TF-1000", "TF-N"]
        vbox = QVBoxLayout()
        self.setLayout(vbox)
        self.tab = Weak.ref(tab)
        self.total_amount = 0
        self.values = []
        self.distributions_combo = QComboBox()
        self.distributions_combo.addItems(self.distributions)
        self.distributions_combo.setCurrentIndex(0)
        self.selected_distribution = 0

        self.distributions_combo.currentIndexChanged.connect(self.on_distribution)

        l = QLabel("<b>%s</b>" % (_("Fund Biletoj (preview)")))
        vbox.addWidget(l)
        vbox.addWidget(self.distributions_combo)
        self.total_amount_wid = BTCAmountEdit(self.main_window.get_decimal_point)

        self.total_amount_wid.textEdited.connect(self.fund_parameters_changed)
        vbox.addWidget(self.total_amount_wid)
        self.total_amount_wid.setMaximumWidth(70)

        grid = QGridLayout()
        vbox.addLayout(grid)

        grid.addWidget(QLabel("Average: "), 0, 0)
        grid.addWidget(QLabel("Standard deviation: "),1 ,0)
        grid.addWidget(QLabel("Max: "), 2, 0)
        grid.addWidget(QLabel("Min: "),3,0)
        grid.addWidget(QLabel("Sum: "), 4, 0)
        self.stats = [QLabel('') for r in range(5)]
        #print(self.stats)
        for i, lab in enumerate(self.stats): grid.addWidget(lab,i,1)
        tab = self.tab()
        self.selected = tab.tu.selectedItems()
        selected = self.selected
        if not selected:
            print("nothing was selected")
            self.closeEvent()
            return
        if isinstance(selected[0].data(1, Qt.UserRole), Address):
            self.addresses = [s.data(1, Qt.UserRole) for s in selected]
        else:
            self.addresses = selected[0].data(1, Qt.UserRole)
        self.b = QPushButton(_("Fund"))
        self.b.clicked.connect(self.do_fund)
        vbox.addWidget(self.b)
        self.b.setDisabled(True)
        vbox.addStretch(1)

    def on_distribution(self):
        self.selected_distribution = self.distributions_combo.currentIndex()
        self.fund_parameters_changed()

    def fund_parameters_changed(self):
        try:
            self.total_amount = self.total_amount_wid.get_amount()
            self.make_outputs()
            self.update_stats()
        except ValueError:
            self.show_message("Not enough biletoj to use this distribution")
            self.b.setDisabled(True)
        except Exception as e:
            self.b.setDisabled(True)
            pass
        else:
            self.b.setDisabled(False)

    def update_stats(self):
        stats = [0]*5
        stats[0] = self.mean(self.values)
        stats[1] = self.stdev(self.values)
        stats[2] = max(self.values)
        stats[3] = min(self.values)
        stats[4] = sum(self.values)
        for s in stats: print(str(s))
        for i,s in enumerate(stats): self.stats[i].setText(str(self.main_window.format_amount(s)))

    def mean(self, data):
        return sum(data)/len(data)

    def stdev(self, data):
        if len(data) == 1:
            return 0
        m = self.mean(data)
        dev = [(d-m)**2 for d in data]
        return sqrt(sum(dev)/(len(data)-1))

    def make_outputs(self):
        if self.selected_distribution == 0:
            outputs = self.regular(self.addresses)
        if self.selected_distribution == 1:
            outputs = self.tf(self.addresses)
        if self.selected_distribution == 2:
            outputs = self.tf100(self.addresses)
        if self.selected_distribution == 3:
            outputs = self.tf1000(self.addresses)
        if self.selected_distribution == 4:
            outputs = self.tfN(self.addresses)
        return outputs

    def do_fund(self):
        print("funding")
        outputs = self.make_outputs()
        if outputs == []:
            return
        if not outputs:
            self.show_error("Minimum value too low to sweep with bitcoin.com")
            return
        tab = self.tab()
        tab.get_password()
        password = tab.password
        try:
            tx = self.wallet.mktx(outputs, password, tab.main_window.config)
        except NotEnoughFunds:
            return self.show_critical(_("Not enough balance to fund biletoj."))
        except Exception as e:
            return self.show_critical(repr(e))
        #self.main_window.show_message("Click \'broadcast\' to fund biletoj.")
        show_transaction(tx, self.main_window, "Fund biletoj", prompt_if_unsaved=True)

    def regular(self, addresses):
        outputs = []
        self.values = []
        am = self.total_amount // len(addresses)
        for a in addresses:
            outputs.append((TYPE_ADDRESS,a,am))
            self.values.append(am)
        if min(self.values) <= 1100:
            return None
        return outputs


    def tf(self, addresses):
        outputs = []
        percentage_amount = [0.01, 0.09, 0.15, 0.75 ]
        percentage_biletoj = [0.5, 0.25, 0.20, 0.05 ]
        totals = [(amt*self.total_amount)//ceil(bil*len(addresses)) for bil,amt in zip(percentage_biletoj,percentage_amount)]
        done=0
        self.values = []
        for i, j in zip(percentage_amount,percentage_biletoj):
            working_on=len(addresses)*j
            agroup = done + int(floor(working_on))
            for a in addresses[done:agroup]:
                am = int((self.total_amount * i)//ceil(working_on))
                outputs.append((TYPE_ADDRESS, a, am))
                self.values.append(am)
            done=agroup
        assert sum(totals) <= self.total_amount
        if min(self.values) <= 1100:
            return None
        return outputs


    def tf100(self, addresses):
        outputs = []
        if len(addresses)!= 100:
            raise ValueError()
        percentage_amount = [1/3., 1/3., 1/3.]
        percentage_biletoj = [0.01, 0.1, 0.89 ]
        totals = [(amt*self.total_amount)//ceil(bil*len(addresses)) for bil,amt in zip(percentage_biletoj,percentage_amount)]
        done=0
        self.values = []
        for i, j in zip(percentage_amount,percentage_biletoj):
            group_length=len(addresses)*j
            agroup = done + int(floor(group_length))
            for a in addresses[done:agroup]:
                am = int((self.total_amount * i)//ceil(group_length))
                outputs.append((TYPE_ADDRESS, a, am))
                self.values.append(am)
            done=agroup
        assert sum(totals) <= self.total_amount
        if min(self.values) <= 1100:
            return None
        return outputs

    def tf1000(self, addresses):
        outputs = []
        if len(addresses)!= 1000:
            raise ValueError()
        percentage_amount = [1/3., 1/3., 1/3.]
        percentage_biletoj = [0.001, 0.1, 0.899 ]
        totals = [(amt*self.total_amount)//ceil(bil*len(addresses)) for bil,amt in zip(percentage_biletoj,percentage_amount)]
        done=0
        self.values = []
        for i, j in zip(percentage_amount,percentage_biletoj):
            group_length=len(addresses)*j
            agroup = done + int(floor(group_length))
            for a in addresses[done:agroup]:
                am = int((self.total_amount * i)//ceil(group_length))
                outputs.append((TYPE_ADDRESS, a, am))
                self.values.append(am)
            done=agroup
        assert sum(totals) <= self.total_amount
        if min(self.values) <= 1100:
            return None
        return outputs

    def tfN(self, addresses):
        outputs = []
        s = len(addresses)
        percentage_amount = [1/3., 1/3., 1/3.]
        percentage_biletoj = [1./s, 0.1, 0.9-(1./s) ]
        totals = [(amt*self.total_amount)//ceil(bil*len(addresses)) for bil,amt in zip(percentage_biletoj,percentage_amount)]
        done=0
        self.values = []
        for i, j in zip(percentage_amount,percentage_biletoj):
            group_length=len(addresses)*j
            agroup = done + int(floor(group_length))
            for a in addresses[done:agroup]:
                am = int((self.total_amount * i)//ceil(group_length))
                outputs.append((TYPE_ADDRESS, a, am))
                self.values.append(am)
            done=agroup
        assert sum(totals) <= self.total_amount
        if min(self.values) <= 1100:
            return None
        return outputs

    def closeEvent(self, QCloseEvent):
        tab=self.tab()
        tab.plugin.on_fund_dialog_closed(self.wallet_name)