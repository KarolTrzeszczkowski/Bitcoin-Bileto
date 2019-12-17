from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from subprocess import call, check_output
from electroncash_gui.qt.qrcodewidget import QRCodeWidget
from electroncash import keystore
from electroncash.wallet import Standard_Wallet, sweep
from electroncash.storage import WalletStorage
from electroncash.i18n import _

from electroncash_gui.qt.util import *
from electroncash.util import PrintError, print_error, age, Weak, InvalidPassword
import random, tempfile, string, os, threading, queue
from electroncash.bitcoin import encrypt_message, deserialize_privkey, public_key_from_private_key




class NewBatchDialog(QDialog,MessageBoxMixin, PrintError):
    settings_updated_signal = pyqtSignal()

    def __init__(self, parent, plugin, wallet_name, password=None):
        QDialog.__init__(self, parent)
        self.main_window = parent
        self.password = password
        self.wallet = parent.wallet
        self.plugin = plugin
        self.network = parent.network
        self.wallet_name = wallet_name
        self.batch_label = "CryptoBiletoj1"
        self.template_file = ''
        self.working_directory = self.wallet.storage.get("bileto_path")

        self.number = 0
        self.times = 1
        self.public_key = ''
        for x in range(10):
            name = 'tmp_wo_wallet' + ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            self.file = os.path.join(tempfile.gettempdir(), name)
            if not os.path.exists(self.file):
                break
        else:
            raise RuntimeError('Could not find a unique temp file in tmp directory', tempfile.gettempdir())
        self.tmp_pass = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

        from electroncash import mnemonic
        seed = mnemonic.Mnemonic('en').make_seed('standard')
        self.keystore = keystore.from_seed(seed, self.tmp_pass, False)
        self.storage = WalletStorage(self.file)
        self.storage.set_password(self.tmp_pass, encrypt=True)
        self.storage.put('keystore', self.keystore.dump())
        self.recipient_wallet = Standard_Wallet(self.storage)
        self.recipient_wallet.start_threads(self.network)
        Weak.finalize(self.recipient_wallet, self.delete_temp_wallet_file, self.file)
        vbox = QVBoxLayout()
        self.setLayout(vbox)
        hbox = QHBoxLayout()
        vbox.addLayout(hbox)
        l = QLabel("<b>%s</b>" % (_("Crypto Bileto")))
        hbox.addStretch(1)
        hbox.addWidget(l)
        hbox.addStretch(1)
        vbox.addWidget(QLabel("Working dir:"))
        hbox=QHBoxLayout()
        vbox.addLayout(hbox)
        self.wd_label = QLabel(self.working_directory)
        hbox.addWidget(self.wd_label)
        b= QPushButton("Set")
        b.clicked.connect(lambda: self.plugin.settings_dialog(self, self.settings_updated_signal))
        self.settings_updated_signal.connect(self.on_settings_updated)
        hbox.addWidget(b)
        data = "prywatny klucz do portfela"
        self.qrw = QRCodeWidget(data)
        qrw_layout = QVBoxLayout(self.qrw)
        qrw_layout.addStretch(1)
        self.number_label=QLabel("LOL")
        qrw_layout.addWidget(self.number_label)
        self.batch_label_wid = QLineEdit()
        self.batch_label_wid.setPlaceholderText(_("Crypto biletoj batch label"))
        self.batch_label_wid.textEdited.connect(self.batch_info_changed)
        vbox.addWidget(self.batch_label_wid)

        grid = QGridLayout()
        vbox.addLayout(grid)
        self.number_wid = QLineEdit()
        self.number_wid.setPlaceholderText(_("Number of biletoj"))
        self.number_wid.textEdited.connect(self.batch_info_changed)
        self.times_wid = QLineEdit()
        self.times_wid.textEdited.connect(self.batch_info_changed)
        self.times_wid.setText("1")
        hbox = QHBoxLayout()
        vbox.addLayout(hbox)
        hbox.addWidget(self.number_wid)
        #hbox.addWidget(QLabel("x"))
        #hbox.addWidget(self.times_wid)
        hbox.addStretch(1)
        self.times_wid.setMaximumWidth(120)
        self.number_wid.setMaximumWidth(140)
        self.only_qrcodes_checkbox = QCheckBox("Only make QR codes.")
        vbox.addWidget(self.only_qrcodes_checkbox)
        b = QPushButton(_("Load .tex template"))
        b.clicked.connect(self.load_template)
        b.setMaximumWidth(130)
        grid.addWidget(b, 0, 0)
        self.template_path_label_wid = QLabel('set path')
        grid.addWidget(self.template_path_label_wid, 0, 1)
        self.public_key_wid = QLineEdit()
        self.public_key_wid.setPlaceholderText(_("Public Key") + _(" for encryption"))
        self.public_key_wid.textEdited.connect(self.batch_info_changed)
        #vbox.addWidget(self.public_key_wid)
        self.b = QPushButton(_("Generate biletoj"))
        self.b.clicked.connect(self.generate_biletoj)
        self.prog_bar = QProgressBar()
        self.prog_bar.setVisible(False)
        vbox.addWidget(self.b)
        vbox.addWidget(self.prog_bar)
        self.b.setDisabled(True)
        vbox.addStretch(1)

    def on_settings_updated(self):
        self.working_directory = self.wallet.storage.get("bileto_path")
        self.wd_label.setText(self.working_directory)

    def save_qrcode(self, qrw, name):
        print_error("saving...")
        p = qrw and qrw.grab()
        filename = os.path.join(self.working_directory, name)
        print_error("filename ")
        if p and not p.isNull():
            if filename:
                print_error("saving")
                p.save(filename, 'png')

    def batch_info_changed(self):
        # string = self.recipient_wallet.get_unused_address().to_ui_string()
        try:
            self.batch_label = str(self.batch_label_wid.text())
            self.number = int(self.number_wid.text())
            self.times = int(self.times_wid.text())
            assert self.times > 0
            # self.public_key = str(self.public_key_wid.text())
            self.public_key = self.wallet.get_pubkey(False,0)
        except AssertionError:
            self.times_wid.setText("1")
        except:
            self.b.setDisabled(True)
            pass
        else:
            self.b.setDisabled(False)

    def load_template(self):
        self.template_file = self.main_window.getOpenFileName("Load Latex template", "*.tex")
        self.template_path_label_wid.setText(self.template_file)


    def generate_biletoj(self):
        self.b.setDisabled(True)
        self.b.setText("In progress...")
        self.prog_bar.setRange(0,self.number)
        self.prog_bar.setVisible(True)
        QCoreApplication.processEvents()
        try:
            path_to_latex = check_output(["which", "pdflatex"], shell=False).strip()
        except:
            path_to_latex = '/Library/Tex/texbin/pdflatex'
        batch_privs = self.batch_label + '\n'
        if self.only_qrcodes_checkbox:
            os.mkdir(os.path.join(self.working_directory,self.batch_label+"_qrcodes"))
        for i in range(self.number):
            add = self.recipient_wallet.create_new_address()
            data = self.recipient_wallet.export_private_key(add, None)
            batch_privs += data + '\n'
            self.number_label.setText('  '+ str(i+1))
            if not self.only_qrcodes_checkbox.isChecked():
                self.qrw.setData(data)
                self.save_qrcode(self.qrw, "priv_key.png")
                self.qrw.setData(add.to_ui_string())
                self.save_qrcode(self.qrw, "address.png")
                call([path_to_latex, self.template_file], cwd=os.path.dirname(self.template_file), shell=False)
                call(["mv", self.template_file[:-4] + '.pdf', "tmp.pdf"],
                     cwd=os.path.dirname(self.template_file), shell=False)
            else:
                self.qrw.setData(data)
                self.save_qrcode(self.qrw, self.batch_label+"_qrcodes/priv_key_"+str(i+1)+".png")
                self.qrw.setData(add.to_ui_string())
                self.save_qrcode(self.qrw,self.batch_label+"_qrcodes/address_"+str(i+1)+".png")
            self.prog_bar.setValue(i+1)
        if not self.only_qrcodes_checkbox.isChecked():
            call(["mv", "tmp.pdf", os.join(self.working_directory,self.batch_label + '_biletoj' + '.pdf')],
                cwd=os.path.dirname(self.template_file), shell=False)
        filename = os.path.join(os.path.dirname(self.working_directory),
                                self.batch_label + '_encrypted_private_keys')

        save_private_keys(batch_privs,self.public_key,filename)
        self.prog_bar.setVisible(False)
        self.main_window.show_message("Done!")
        self.b.setDisabled(False)
        self.b.setText(_("Generate biletoj"))

    def filter(self, *args):
        ''' This is here because searchable_list must define a filter method '''

    @staticmethod
    def delete_temp_wallet_file(file):
        ''' deletes the wallet file '''
        if file and os.path.exists(file):
            try:
                os.remove(file)
                print_error("[InterWalletTransfer] Removed temp file", file)
            except Exception as e:
                print_error("[InterWalletTransfer] Failed to remove temp file", file, "error: ", repr(e))

    def closeEvent(self, event):
        self.plugin.on_create_dialog_closed(self.wallet_name)
        event.accept()

def save_private_keys(batch_privs, public_key, filename):
    encrypted_privs = encrypt_message(batch_privs.encode('utf8'), public_key)
    with open(filename, 'w') as file:
        file.write(encrypted_privs.decode('utf8'))