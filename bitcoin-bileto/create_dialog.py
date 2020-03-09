from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from subprocess import call, check_output
from electroncash import keystore
from electroncash.wallet import Standard_Wallet, sweep
from electroncash.storage import WalletStorage
from electroncash.i18n import _

from electroncash_gui.qt.util import *
from electroncash.util import PrintError, print_error, age, Weak, InvalidPassword
import random, tempfile, string, os, threading, queue, qrcode
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
        self.batch_label = "BitcoinBiletoj1"
        self.template_file = ''
        self.working_directory = self.wallet.storage.get("bileto_path")
        if self.working_directory:
            if not os.path.exists(self.working_directory) :
                self.working_directory = None
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
        l = QLabel("<b>%s</b>" % (_("Bitcoin Bileto")))
        hbox.addStretch(1)
        hbox.addWidget(l)
        hbox.addStretch(1)
        vbox.addWidget(QLabel("Working directory:"))
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
        self.batch_label_wid.setPlaceholderText(_("Bitcoin biletoj batch label"))
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
        self.only_qrcodes_checkbox.stateChanged.connect(self.batch_info_changed)
        self.encrypt_checkbox = QCheckBox("Encrypt Batch.")
        vbox.addWidget(self.encrypt_checkbox)
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
            assert os.path.exists(self.working_directory)
            if not self.only_qrcodes_checkbox.isChecked():
                assert os.path.isfile(self.template_file)
        except AssertionError:
            self.times_wid.setText("1")
            self.b.setDisabled(True)
        except:
            self.b.setDisabled(True)
        else:
            self.b.setDisabled(False)

    def load_template(self):
        self.template_file = self.main_window.getOpenFileName("Load Latex template", "*.tex")
        self.template_path_label_wid.setText(self.template_file)
        self.batch_info_changed()


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
        if self.only_qrcodes_checkbox.isChecked():
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
            call(["mv", "tmp.pdf", os.path.join(self.working_directory,self.batch_label + '_biletoj' + '.pdf')],
                cwd=os.path.dirname(self.template_file), shell=False)
        filename = os.path.join(self.working_directory,
                                self.batch_label + '_encrypted_private_keys')

        save_private_keys(batch_privs,self.public_key,filename, self.encrypt_checkbox.isChecked())
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
        #self.plugin.on_create_dialog_closed(self.wallet_name)
        event.accept()

def save_private_keys(batch_privs, public_key, filename, encrypt):
    if(encrypt):
        encrypted_privs = encrypt_message(batch_privs.encode('utf8'), public_key)
        with open(filename, 'w') as file:
            file.write(encrypted_privs.decode('utf8'))
    else:
        with open(filename.replace('_encrypted','_unencrypted'), 'w') as file:
            file.write(batch_privs)



class QRCodeWidget(QWidget, PrintError):

    def __init__(self, data = None, fixedSize=False):
        QWidget.__init__(self)
        self.data = None
        self.qr = None
        self.fixedSize = fixedSize
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        if fixedSize:
            self.setFixedSize(fixedSize, fixedSize)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setData(data)


    def setData(self, data):
        if self.data != data:
            self.data = data
        if self.data:
            try:
                self.qr = qrcode.QRCode()
                self.qr.add_data(self.data)
                if not self.fixedSize:
                    k = len(self.qr.get_matrix())
                    self.setMinimumSize(k*5,k*5)
                    self.updateGeometry()
            except qrcode.exceptions.DataOverflowError:
                self._bad_data(data)  # sets self.qr = None
        else:
            self.qr = None

        self.update()


    def _paint_blank(self):
        qp = QPainter(self)
        r = qp.viewport()
        qp.fillRect(0, 0, r.width(), r.height(), self._white_brush)
        qp.end(); del qp

    def _bad_data(self, data):
        self.print_error("Failed to generate QR image -- data too long! Data length was: {} bytes".format(len(data or '')))
        self.qr = None

    _black_brush = QBrush(QColor(0, 0, 0, 255))
    _white_brush = QBrush(QColor(255, 255, 255, 255))
    _black_pen = QPen(_black_brush, 1.0, join = Qt.MiterJoin)
    _white_pen = QPen(_white_brush, 1.0, join = Qt.MiterJoin)

    def paintEvent(self, e):
        matrix = None

        if self.data and self.qr:
            try:
                matrix = self.qr.get_matrix()
            except qrcode.exceptions.DataOverflowError:
                self._bad_data(self.data)  # sets self.qr = None

        if not matrix:
            self._paint_blank()
            return

        k = len(matrix)
        qp = QPainter(self)
        r = qp.viewport()

        margin = 10
        framesize = min(r.width(), r.height())
        boxsize = int( (framesize - 2*margin)/k )
        size = k*boxsize
        left = (r.width() - size)/2
        top = (r.height() - size)/2

        # Make a white margin around the QR in case of dark theme use
        qp.setBrush(self._white_brush)
        qp.setPen(self._white_pen)
        #qp.drawRect(left-margin, top-margin, size+(margin*2), size+(margin*2))
        qp.setBrush(self._black_brush)
        qp.setPen(self._black_pen)

        for r in range(k):
            for c in range(k):
                if matrix[r][c]:
                    qp.drawRect(left+c*boxsize, top+r*boxsize, boxsize - 1, boxsize - 1)
        qp.end(); del qp