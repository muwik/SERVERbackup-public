import os
import run
import sys
import json
import mail
import ftplib
import dbbckp
import wsbckp
import shutil
import MySQLdb
import surcron
import logging
import paramiko
import requests
import platform
import subprocess
from time import sleep
from requests import get
from croniter import croniter
from toggle import AnimatedToggle
from datetime import datetime, time, timedelta, date
from PyQt6.QtCore import QDateTime, Qt, QTimer, QRect, QSize, QTime, QObject, QThread, pyqtSignal, QUrl, QModelIndex
from PyQt6.QtGui import QPixmap, QFont, QIcon, QCursor, QBrush, QColor, QMovie, QDesktopServices, QStandardItemModel, QKeyEvent
from PyQt6.QtWidgets import QApplication, QCheckBox, QComboBox, QTextEdit, QGridLayout, QVBoxLayout, QHBoxLayout, QGroupBox, \
    QLabel, QLineEdit, QPushButton, QSizePolicy, QSpinBox, QTableWidget, QTabWidget, QWidget, QStatusBar, QMainWindow, \
    QFileDialog, QMessageBox, QMenu, QHeaderView, QTableWidgetItem, QFrame, QStyle, QStyleOptionComboBox

def resource_path(relative_path):
    # Преобразование путей ресурсов в пригодный для использования формат для PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath('.'), relative_path)

class Singleton(type(QObject), type):
    # Класс Синглтон - позволяет избежать повторную инициализацию класса (окна, в моём случае)
    def __init__(cls, name, bases, dict):
        super().__init__(name, bases, dict)
        cls._instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__call__(*args, **kwargs)
        return cls._instance

class ConsoleWindowLogHandler(logging.Handler, QObject):
    # Лог-хэндлер - получает и преобразует поток логов
    sigLog = pyqtSignal(str)
    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, logRecord):
        message = self.format(logRecord)
        self.sigLog.emit(message)

class CustomFormatter(logging.Formatter):
    # Преобразователь логов в цветной текст: выделяет ошибки и предупреждения
    black = '<span style="color:Black;">'
    yellow = '<span style="color:Orange;">'
    red = '<span style="color:OrangeRed;">'
    bold_red = '<span style="color:Crimson;">'
    reset = '</span>'
    format = '%(asctime)s %(levelname)s %(message)s'

    FORMATS = {
        logging.DEBUG: black + format + reset,
        logging.INFO: black + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: bold_red + format + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%d.%m.%Y %H:%M:%S')
        return formatter.format(record)

class Diagnostics(QWidget, metaclass=Singleton):
    # Класс интерфейса окна диагностики
    def __init__(self):
        super().__init__()

        # Флаг возникновения первой ошибки
        self.error_flag = False

        # Установка данного окна, как единственного модального. (Блокировка остальных окон)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Настройки окна диагностики
        self.setFixedSize(QSize(380, 280))
        self.dg_layout = QGridLayout()
        self.setLayout(self.dg_layout)
        self.dg_layout.setSpacing(0)

        # Заголовок
        self.label = QLabel("Diagnostics:")
        self.label.setToolTip("Diagnostics of WEB, SSH, FTP, MySQL и SMTP")
        self.l_font = self.label.font()
        self.l_font.setWeight(500)
        self.label.setFont(self.l_font)

        # Кнопка "Проверить"
        self.ok_btn = QPushButton("Сheck out")

        # Иконка диагностики интернет-соединения
        self.label_di_nw = QLabel(self)
        self.label_di_nw.setText("")
        self.label_di_nw.setHidden(True)

        # Иконка диагностики соединения с сервером по SSH
        self.label_di_sh = QLabel(self)
        self.label_di_sh.setText("")
        self.label_di_sh.setHidden(True)

        # Иконка диагностики соединения с сервером по FTP
        self.label_di_fp = QLabel(self)
        self.label_di_fp.setText("")
        self.label_di_fp.setHidden(True)

        # Иконка диагностики соединения с БД MySQL
        self.label_di_db = QLabel(self)
        self.label_di_db.setText("")
        self.label_di_db.setHidden(True)

        # Иконка диагностики соединения с почтовым сервером
        self.label_di_ml = QLabel(self)
        self.label_di_ml.setText("")
        self.label_di_ml.setHidden(True)

        # Поле для вывода ошибок
        self.errors_textbox = QTextEdit(self)
        self.errors_textbox.setReadOnly(True)
        self.errors_textbox.setMaximumHeight(110)
        self.errors_textbox.setObjectName('ErrorTextBox')

        # Добавляем виджеты в макет окна
        self.dg_layout.addWidget(self.label, 0, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.dg_layout.addWidget(QLabel("Internet connection"), 1, 0)
        self.dg_layout.addWidget(QLabel("Connecting to the server via SSH"), 2, 0)
        self.dg_layout.addWidget(QLabel("Connecting to the server via FTP"), 3, 0)
        self.dg_layout.addWidget(QLabel("Connecting to the MySQL DB"), 4, 0)
        self.dg_layout.addWidget(QLabel("Connecting to a mail server"), 5, 0)
        self.dg_layout.addWidget(self.errors_textbox, 6, 0, 1, 2)

        # Изображения иконок: зелёная и красная
        self.pixmap_yes = QPixmap(resource_path("assets/di-g.png")).scaled(12, 12, Qt.AspectRatioMode.KeepAspectRatio,
                                                         Qt.TransformationMode.FastTransformation)

        self.pixmap_no = QPixmap(resource_path("assets/di-r.png")).scaled(12, 12, Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.FastTransformation)

    def nw_con(self):
        # Тест интернет-соединения
        url = "https://www.google.com/"
        timeout = 5
        sleep(0.1)
        try:
            request = requests.get(url, timeout=timeout)
            self.label_di_nw.setPixmap(self.pixmap_yes)
            self.dg_layout.addWidget(self.label_di_nw, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        except Exception as e:
            self.label_di_nw.setPixmap(self.pixmap_no)
            self.dg_layout.addWidget(self.label_di_nw, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self.error_flag = True
            self.errors_textbox.append(f'Web (Test website: {url}) -> {e}')
        self.label_di_nw.setHidden(False)

    def sh_con(self):
        # Тест соединения с сервером по SSH
        config = SUSLIK_Admin().json_adder()
        sleep(0.1)
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=config['ssh_host'], username=config['ssh_login'],
                           password=config['ssh_password'], port=config['ssh_port'])

            stdin, stdout, stderr = client.exec_command('ls')
            data = stdout.read()
            client.close()
            self.label_di_sh.setPixmap(self.pixmap_yes)
            self.dg_layout.addWidget(self.label_di_sh, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        except Exception as e:
            self.label_di_sh.setPixmap(self.pixmap_no)
            self.dg_layout.addWidget(self.label_di_sh, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self.error_flag = True
            self.errors_textbox.append(f'SSH -> {e}')
        self.label_di_sh.setHidden(False)

    def fp_con(self):
        # Тест соединения с сервером по FTP
        config = SUSLIK_Admin().json_adder()
        sleep(0.1)
        try:
            server = ftplib.FTP()
            server.connect(config['ftp_host'], int(config['ftp_port']))
            server.login(config['ftp_login'], config['ftp_password'])
            server.quit()
            self.label_di_fp.setPixmap(self.pixmap_yes)
            self.dg_layout.addWidget(self.label_di_fp, 3, 1, alignment=Qt.AlignmentFlag.AlignRight)
        except Exception as e:
            self.label_di_fp.setPixmap(self.pixmap_no)
            self.dg_layout.addWidget(self.label_di_fp, 3, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self.error_flag = True
            self.errors_textbox.append(f'FTP -> {e}')
        self.label_di_fp.setHidden(False)

    def db_con(self):
        # Тест БД соединения
        config = SUSLIK_Admin().json_adder()
        sleep(0.1)
        try:
            connection = MySQLdb.connect(
                host=config['host'],
                user=config['login'],
                password=config['password'],
                db=config['db_name'],
                ssl={'key': config["path_to_ckc"], 'ca': config["path_to_scc"], 'cert': config["path_to_ccc"]}
            )
            cursor = connection.cursor()
            cursor.execute("SELECT VERSION()")
            results = cursor.fetchone()
            connection.close()
            if results:
                self.label_di_db.setPixmap(self.pixmap_yes)
                self.dg_layout.addWidget(self.label_di_db, 4, 1, alignment=Qt.AlignmentFlag.AlignRight)
            else:
                self.label_di_db.setPixmap(self.pixmap_no)
                self.dg_layout.addWidget(self.label_di_db, 4, 1, alignment=Qt.AlignmentFlag.AlignRight)
                self.error_flag = True
                self.errors_textbox.append(f'MySQL DB -> Test request execution error')
        except Exception as e:
            self.label_di_db.setPixmap(self.pixmap_no)
            self.dg_layout.addWidget(self.label_di_db, 4, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self.error_flag = True
            self.errors_textbox.append(f'MySQL DB -> {e}')
        self.label_di_db.setHidden(False)

    def ml_con(self):
        # Тест соединения с почтовым сервером
        sleep(0.1)
        try:
            mail.diag()
            self.label_di_ml.setPixmap(self.pixmap_yes)
            self.dg_layout.addWidget(self.label_di_ml, 5, 1, alignment=Qt.AlignmentFlag.AlignRight)
        except Exception as e:
            self.label_di_ml.setPixmap(self.pixmap_no)
            self.dg_layout.addWidget(self.label_di_ml, 5, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self.error_flag = True
            self.errors_textbox.append(f'Mail server -> {e}')
        self.label_di_ml.setHidden(False)
        if not self.error_flag:
            self.errors_textbox.append('--NO ERRORS--')

    def closeEvent(self, event):
        # Сценарий закрытия окна
        self.error_flag = False
        self.errors_textbox.clear()
        self.label_di_nw.setPixmap(QPixmap())
        self.label_di_sh.setPixmap(QPixmap())
        self.label_di_fp.setPixmap(QPixmap())
        self.label_di_db.setPixmap(QPixmap())
        self.label_di_ml.setPixmap(QPixmap())

class Last_backup_info(QWidget, metaclass=Singleton):
    # Класс интерфейса окна информации о последнем бэкапе
    def __init__(self):
        super().__init__()

        # Установка данного окна, как единственного модального. (Блокировка остальных окон)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Настройки окна выбора бэкапа
        self.setFixedWidth(480)
        self.bi_layout = QGridLayout()
        self.bi_layout.setSpacing(5)
        self.bi_layout.setColumnMinimumWidth(0, 180)
        self.bi_layout.setColumnMinimumWidth(1, 120)
        self.bi_layout.setRowStretch(0, 2)
        self.setLayout(self.bi_layout)

        # Заголовок
        self.label = QLabel("Dates of the latest backup versions (Time - Local):")
        self.l_font = self.label.font()
        self.l_font.setWeight(500)
        self.label.setFont(self.l_font)
        self.label.setFixedHeight(40)

        # Изображения иконка-индикаторов наличия/отсутствия актуальной версии бэкапа
        self.pixmap_act_a = QPixmap(resource_path("assets/a-act.png")).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                                                            Qt.TransformationMode.FastTransformation)
        self.pixmap_act_o = QPixmap(resource_path("assets/o-act.png")).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                                                            Qt.TransformationMode.FastTransformation)

    def add_last_backups_data(self):
        # Очищаем таблицу от прежних значений
        for i in reversed(range(self.bi_layout.count())):
            self.bi_layout.itemAt(i).widget().setParent(None)

        # Добавляем виджеты в макет окна
        self.bi_layout.addWidget(self.label, 0, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignCenter)
        projects_dbs = {db: SUSLIK_Admin().json_adder()['backups_create'][db] for db in SUSLIK_Admin().json_adder()['backups_create'] if '.sql' in db}
        projects_wss = {ws: SUSLIK_Admin().json_adder()['backups_create'][ws] for ws in SUSLIK_Admin().json_adder()['backups_create'] if not '.sql' in ws}
        dbs_ids = SUSLIK_Admin().json_adder()['latest_dbs']
        wss_ids = SUSLIK_Admin().json_adder()['latest_wss']

        for i, project in enumerate(projects_dbs):
            self.bi_layout.addWidget(QLabel(project), i+1, 0)
            self.bi_layout.addWidget(QLabel(projects_dbs[project]), i+1, 1)
            if project in dbs_ids:
                label_act_a = QLabel(self)
                label_act_a.setText("")
                label_act_a.setPixmap(self.pixmap_act_a)
                self.bi_layout.addWidget(label_act_a, i+1, 2)
            else:
                label_act_o = QLabel(self)
                label_act_o.setText("")
                label_act_o.setPixmap(self.pixmap_act_o)
                self.bi_layout.addWidget(label_act_o, i+1, 2)

        for i, project in enumerate(projects_wss):
            r_c = self.bi_layout.rowCount()
            self.bi_layout.addWidget(QLabel(project), i+1+r_c, 0)
            self.bi_layout.addWidget(QLabel(projects_wss[project]), i+1+r_c, 1)
            if project in wss_ids:
                label_act_a = QLabel(self)
                label_act_a.setText("")
                label_act_a.setPixmap(self.pixmap_act_a)
                self.bi_layout.addWidget(label_act_a, i+1+r_c, 2)
            else:
                label_act_o = QLabel(self)
                label_act_o.setText("")
                label_act_o.setPixmap(self.pixmap_act_o)
                self.bi_layout.addWidget(label_act_o, i+1+r_c, 2)

class Choose_backup(QWidget):
    # Класс интерфейса окна выбора бэкапа
    def __init__(self):
        super().__init__()

        # Установка данного окна, как единственного модального. (Блокировка остальных окон)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Инициализация окна запуска бэкапов как изначально закрытого
        self.b_con = None

        # Настройки окна выбора бэкапа
        self.setFixedSize(QSize(380, 220))
        self.ch_layout = QVBoxLayout()
        self.setLayout(self.ch_layout)

        # Заголовок
        self.label = QLabel("Choose which backup you want to create:")
        self.l_font = self.label.font()
        self.l_font.setWeight(500)
        self.label.setFont(self.l_font)

        # Чекбоксы выбора бэкапов
        self.dbb = QCheckBox("Backup database(s)")
        self.wsb = QCheckBox("Backup website(s)")
        self.svb = QCheckBox("Backup всего сервера (!)")
        self.svb.setDisabled(True)
        self.dbb.setChecked(False)
        self.wsb.setChecked(False)
        self.svb.setChecked(False)
        self.svb.setVisible(False)
        self.dbb.stateChanged.connect(self.cron_or_chck_db)
        self.wsb.stateChanged.connect(self.cron_or_chck_db)
        self.svb.stateChanged.connect(self.cron_or_chck_sv)

        # Кнопка "ОК"
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(lambda: self.check_state(self.dbb.isChecked(), self.wsb.isChecked(), self.svb.isChecked()))

        # Подсказка внизу окна
        self.ok_tip = QLabel("After clicking on the button, additional confirmation will be required.")
        self.ok_tip.setObjectName("tooltip")
        self.ok_tip.setMaximumHeight(10)

        # Добавляем виджеты в макет окна
        self.ch_layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.ch_layout.addWidget(self.dbb, alignment=Qt.AlignmentFlag.AlignLeft)
        self.ch_layout.addWidget(self.wsb, alignment=Qt.AlignmentFlag.AlignLeft)
        # self.ch_layout.addWidget(QLabel('-ИЛИ-'), alignment=Qt.AlignmentFlag.AlignHCenter)
        self.ch_layout.addWidget(self.svb, alignment=Qt.AlignmentFlag.AlignLeft)
        self.ch_layout.addWidget(self.ok_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.ch_layout.addWidget(self.ok_tip, alignment=Qt.AlignmentFlag.AlignHCenter)

    def cron_or_chck_db(self, new_state):
        # Сделать активн. чекбокс бэкапа всего сервера при неактивности двух других и наоборот
        if self.dbb.isChecked() or self.wsb.isChecked():
            self.svb.setChecked(False)

    def cron_or_chck_sv(self, new_state):
        # Сделать активн. чекбокс бэкапа всего сервера при неактивности двух других и наоборот
        if self.svb.isChecked():
            self.dbb.setChecked(False)
            self.wsb.setChecked(False)
            self.svb.setChecked(True)

    def check_state(self, db_flag, ws_flag, svflag):
        # Считывание состояния чекбоксов и отправки значений в следующее окно
        if db_flag or ws_flag or svflag:
            self.open_bckp_confirmation(db_flag, ws_flag, svflag) # Открываем окно выбора бэкапов
        else:
            # Окно предупреждения, в случае невыбора ни одного чекбокса
            self.messageC = QMessageBox()
            self.messageC.setIcon(QMessageBox.Icon.Warning)
            self.messageC.setInformativeText("Choose at least one backup!")
            self.view = self.messageC.exec()

    def open_bckp_confirmation(self, db_flag, ws_flag, sv_flag):
        # Отображение окна запуска бэкапа
        self.b_con = Confirm_backup(db_flag, ws_flag, sv_flag)
        self.close()
        self.b_con.show()


class CheckableComboBox(QComboBox):
    # Класс выпадающего списка с чекбоксами
    def __init__(self, parent=None):
        super(CheckableComboBox, self).__init__(parent)
        self.view().pressed.connect(self.handle_item_pressed)
        self.view().pressed.connect(lambda: self.activateWindow())
        self.setModel(QStandardItemModel(self))
        # self.set_item_checked(0) # При инициации вып. списка, делаем его первый элемент невыбранным (unchecked)
        self.last_clicked = False # Флаг клика по вып. списку или выбора его содержимого
        self.activated.connect(self.change_last_state)

    # Обрабатываем нажатие элемента
    def handle_item_pressed(self, index):
        item = self.model().itemFromIndex(index)
        if item.checkState() == Qt.CheckState.Checked:
            item.setCheckState(Qt.CheckState.Unchecked)
        else:
            item.setCheckState(Qt.CheckState.Checked)

    # Действие по нажатию на кнопку мыши
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.last_clicked = True

    # Действие при изменении состояния выпадающего списка
    def change_last_state(self):
        self.last_clicked = True

    # Переписанная ф-ия закрытия выпадающего списка - не закрывать, если последний клик был на элементах вып. списка или список был изменен (выбор нового элемента списка)
    def hidePopup(self):
        if not self.last_clicked:
            super(CheckableComboBox, self).hidePopup()
        else:
            super(CheckableComboBox, self).showPopup()
            self.last_clicked = False

    def item_checked(self, index):
        item = self.model().item(index, 0)
        return item.checkState() == Qt.CheckState.Checked

    def give_all_checked_items(self):
        checked_items = []
        for i in range(self.count()):
            if self.item_checked(i):
                checked_items.append(self.model().item(i, 0).text())
        return checked_items

class Confirm_backup(QWidget):
    # Класс интерфейса окна запуска бэкапа
    def __init__(self, db_flag, ws_flag, sv_flag):
        super().__init__()

        # Установка данного окна, как единственного модального. (Блокировка остальных окон)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Полученные флаги-значения чекбоксов
        self.db_flag = db_flag
        self.ws_flag = ws_flag
        self.sv_flag = sv_flag

        # Определение значения сценария бэкапа, согласно значениям чекбоксов
        self.scenario = 0
        if not self.sv_flag:
            if self.db_flag and not self.ws_flag:
                self.scenario = 1
            elif not self.db_flag and self.ws_flag:
                self.scenario = 2
            else:
                self.scenario = 3
        else:
            self.scenario = 4

        # Настройки окна запуска бэкапа
        self.setFixedSize(QSize(670, 576))
        self.strt_layout = QVBoxLayout()
        self.setLayout(self.strt_layout)

        # Выбор приложений и БД для бэкапа
        self.label_vyb = QLabel("Сhoice:")
        self.l_font = self.label_vyb.font()
        self.l_font.setWeight(500)
        self.label_vyb.setFont(self.l_font)

        # Выпадающий список названий сайтов
        self.all_ws_combo = CheckableComboBox(self)
        self.all_ws_combo.setFixedHeight(22)
        self.all_ws_combo.setFixedWidth(190)
        SUSLIK_Admin().update_ws_list_new(self.all_ws_combo)
        item = self.all_ws_combo.model().item(0, self.all_ws_combo.modelColumn())
        item.setCheckState(Qt.CheckState.Unchecked)

        # Выпадающий список названий бд
        self.all_db_combo = CheckableComboBox(self)
        self.all_db_combo.setFixedHeight(22)
        self.all_db_combo.setFixedWidth(190)
        SUSLIK_Admin().update_db_list_new(self.all_db_combo)
        item = self.all_db_combo.model().item(0, self.all_db_combo.modelColumn())
        item.setCheckState(Qt.CheckState.Unchecked)

        # Тумблер "всё" для сайтов
        self.tmblr_ws = AnimatedToggle(checked_color="#0F5774")
        self.tmblr_ws.bar_checked_brush = QBrush(QColor('#A3B7C7'))
        self.tmblr_ws.setFixedSize(QSize(38, 25))
        self.tmblr_ws.toggled.connect(lambda: self.ws_toogle_changed_state())

        # Тумблер "всё" для БД
        self.tmblr_db = AnimatedToggle(checked_color="#0F5774")
        self.tmblr_db.bar_checked_brush = QBrush(QColor('#A3B7C7'))
        self.tmblr_db.setFixedSize(QSize(38, 25))
        self.tmblr_db.toggled.connect(lambda: self.db_toogle_changed_state())

        # Макет ряда "Выбора"
        self.vyb_row = QGridLayout()
        self.vyb_row.setContentsMargins(0, 0, 0, 0)
        self.vyb_row.setSpacing(5)
        self.vyb_row.setColumnStretch(0, 1)
        self.vyb_row.addWidget(self.label_vyb, 0, 1, 1, 5, alignment=Qt.AlignmentFlag.AlignHCenter)
        if self.scenario == 3:
            self.vyb_row.addWidget(self.all_db_combo, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
            self.vyb_row.addWidget(self.all_ws_combo, 2, 2, alignment=Qt.AlignmentFlag.AlignRight)
            self.vyb_row.addWidget(QLabel('-OR-'), 1, 3, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.vyb_row.addWidget(QLabel('-OR-'), 2, 3, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.vyb_row.addWidget(self.tmblr_db, 1, 4, alignment=Qt.AlignmentFlag.AlignLeft)
            self.vyb_row.addWidget(self.tmblr_ws, 2, 4, alignment=Qt.AlignmentFlag.AlignLeft)
            self.vyb_row.addWidget(QLabel('  All'), 1, 5, alignment=Qt.AlignmentFlag.AlignLeft)
            self.vyb_row.addWidget(QLabel('  All'), 2, 5, alignment=Qt.AlignmentFlag.AlignLeft)
        elif self.scenario == 2:
            self.vyb_row.addWidget(self.all_ws_combo, 1, 2, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self.all_db_combo.setHidden(True)
            self.vyb_row.addWidget(QLabel('-OR-'), 1, 3, 2, 1, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.vyb_row.addWidget(self.tmblr_ws, 1, 4, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            self.tmblr_db.setHidden(True)
            self.vyb_row.addWidget(QLabel('  All'), 1, 5, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        elif self.scenario == 1:
            self.vyb_row.addWidget(self.all_db_combo, 1, 2, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
            self.all_ws_combo.setHidden(True)
            self.vyb_row.addWidget(QLabel('-OR-'), 1, 3, 2, 1, alignment=Qt.AlignmentFlag.AlignHCenter)
            self.vyb_row.addWidget(self.tmblr_db, 1, 4, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            self.tmblr_ws.setHidden(True)
            self.vyb_row.addWidget(QLabel('  All'), 1, 5, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        else:
            pass
        self.vyb_row.setColumnMinimumWidth(2, 200)
        self.vyb_row.setColumnMinimumWidth(3, 50)
        self.vyb_row.setColumnMinimumWidth(5, 50)
        self.vyb_row.setColumnStretch(self.vyb_row.columnCount(), 1)

        # Виджет ряда "Выбора"
        self.vyb_wdgt = QWidget(self)
        self.vyb_wdgt.setLayout(self.vyb_row)

        # Опции (Скачать или Скачать и удалить на сервере)
        self.label_opt = QLabel("Options:")
        self.label_opt.setFont(self.l_font)

        # Чекбокс скачивания файла на ПК
        self.dow_local_cb = QCheckBox("Download file(s) to local PC?")
        self.dow_local_cb.setChecked(True)
        self.dow_local_cb.setFixedHeight(28)
        self.dow_local_cb.setToolTip("Download files also to local PC?")
        self.dow_local_cb.stateChanged.connect(lambda: self.del_dow_state_chngd())

        # Чекбокс удаления файла(ов) на сервере после скачивания
        self.del_serv_cb = QCheckBox("Delete the backup file(s) on the server?")
        self.del_serv_cb.setFixedHeight(28)
        self.del_serv_cb.setToolTip("Delete backup files(s) on the server after downloading to a PC?")

        # Макет ряда "Опций"
        self.opt_row = QGridLayout()
        self.opt_row.setContentsMargins(0, 0, 0, 0)
        self.opt_row.setSpacing(5)
        self.opt_row.setColumnStretch(0, 1)
        self.opt_row.addWidget(self.label_opt, 0, 0, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.opt_row.addWidget(self.dow_local_cb, 1, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        self.opt_row.addWidget(self.del_serv_cb, 2, 0, alignment=Qt.AlignmentFlag.AlignLeft)

        # Виджет ряда "Выбора"
        self.opt_wdgt = QWidget(self)
        self.opt_wdgt.setLayout(self.opt_row)

        # Линия-сепаратор "Выбора" и "Опций"
        self.v_line = QFrame()
        self.v_line.setFrameShape(QFrame.Shape.VLine)
        self.v_line.setFrameShadow(QFrame.Shadow.Raised)

        # Макет рядов "Выбора" и "Опций"
        self.vyb_opt_row = QHBoxLayout()
        self.vyb_opt_row.setContentsMargins(0, 0, 0, 0)
        self.vyb_opt_row.setSpacing(5)
        self.vyb_opt_row.addWidget(self.vyb_wdgt)
        self.vyb_opt_row.addWidget(self.v_line)
        self.vyb_opt_row.addWidget(self.opt_wdgt)

        # Виджет ряда "Выбора"
        self.vyb_opt_wdgt = QWidget(self)
        self.vyb_opt_wdgt.setLayout(self.vyb_opt_row)

        # Контрольный лист (предупреждения, уведомления)
        self.label_cntrl = QLabel("Checklist:")
        self.label_cntrl.setFont(self.l_font)

        # Макет контрольного листа
        self.war_layout = QGridLayout()
        self.war_layout.setContentsMargins(0, 0, 0, 0)
        self.war_layout.setSpacing(10)

        # Лейблы предупреждений
        self.cron_warn = QLabel()
        self.cron_warn_d = QLabel()
        self.db_ws_bckp_warn = QLabel()

        # Иконка предупреждения CRON
        self.label_wr_cron = QLabel(self)
        self.label_wr_cron.setText("")

        # Иконка предупреждения БД-ВС
        self.label_wr_db_ws = QLabel(self)
        self.label_wr_db_ws.setText("")

        # Изображения иконок предупреждений, уведомлений
        self.pixmap_wr_g = QPixmap(resource_path("assets/wr-g.png")).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                                          Qt.TransformationMode.FastTransformation)
        self.pixmap_wr_y = QPixmap(resource_path("assets/wr-y.png")).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                                          Qt.TransformationMode.FastTransformation)
        self.pixmap_wr_b = QPixmap(resource_path("assets/wr-b.png")).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                                          Qt.TransformationMode.FastTransformation)
        self.pixmap_wr_r = QPixmap(resource_path("assets/wr-r.png")).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                                          Qt.TransformationMode.FastTransformation)
        self.pixmap_wr_p = QPixmap(resource_path("assets/wr-p.png")).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                                          Qt.TransformationMode.FastTransformation)

        # Инициализация CRON-предупреждения, с условиями
        if not SUSLIK_Admin().json_adder()['cron']:
            self.cron_warn.setText('There are no scheduled CRON scripts. Overlays and conflicts excluded.')
            self.label_wr_cron.setPixmap(self.pixmap_wr_g)
            self.war_layout.addWidget(self.cron_warn, 0, 1)
        else:
            self.cron_warn.setText('Scheduled CRON script via: ')
            self.cron_warn_d.setText("CRON off for the duration of the backup")

            # Макет ряда с лейблом обратного отсчёта из соседнего класса
            SUSLIK_Admin().cron_countdown_job_brother.setHidden(False)
            self.cw_cntdwn_row = QHBoxLayout()
            self.cw_cntdwn_row.addWidget(self.cron_warn)
            self.cw_cntdwn_row.addWidget(SUSLIK_Admin().cron_countdown_job_brother)
            self.cw_cntdwn_row.addWidget(self.cron_warn_d)
            self.cw_cntdwn_row.setContentsMargins(0, 0, 0, 0)
            self.cw_cntdwn_row.setSpacing(0)

            # Виджет ряда с лейблом обратного отсчёта из соседнего класса
            self.cw_cntdwn_wdgt = QWidget(self)
            self.cw_cntdwn_wdgt.setLayout(self.cw_cntdwn_row)

            self.label_wr_cron.setPixmap(self.pixmap_wr_y)
            self.war_layout.addWidget(self.cw_cntdwn_wdgt, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.war_layout.addWidget(self.label_wr_cron, 0, 0)

        # Инициализация БД-предупреждения, с условиями
        if self.db_flag or self.ws_flag:
            self.db_ws_bckp_warn.setText('DB or Websites backup is selected. Make sure you run the procedure outside business hours.')
            self.label_wr_db_ws.setPixmap(self.pixmap_wr_b)
            self.war_layout.addWidget(self.label_wr_db_ws, 1, 0)
            self.war_layout.addWidget(self.db_ws_bckp_warn, 1, 1)

        # Виджет с макетом контрольного листа
        self.warnings = QWidget()
        self.warnings.setLayout(self.war_layout)

        # Кнопка запуска сценария бэкапа
        self.go_btn = QPushButton("Start")
        self.go_btn.clicked.connect(self.date_check)
        self.go_btn.setMinimumWidth(90)

        # Кнопка останова сценария бэкапа
        self.st_btn = QPushButton("Abort")
        self.st_btn.setDisabled(True)
        self.st_btn.clicked.connect(self.manual_stp)
        self.st_btn.setMinimumWidth(90)

        # Макет ряда с двумя кнопками
        self.btn_row = QHBoxLayout()
        self.btn_row.addWidget(self.go_btn)
        self.btn_row.addWidget(self.st_btn)
        self.btn_row.setContentsMargins(0, 0, 0, 0)
        self.btn_row.setSpacing(5)

        # Виджет ряда с двумя кнопками
        self.btn_wdgt = QWidget(self)
        self.btn_wdgt.setLayout(self.btn_row)

        # Окно вывода логов
        self.log_textbox = QTextEdit()
        self.log_textbox.setReadOnly(True)
        self.log_textbox.setMinimumWidth(600)

        # Макет окна вывода логов
        self.log_layout = QVBoxLayout()
        self.log_layout.addWidget(self.log_textbox)

        # Груп-бокс вывода логов
        self.log_log = QGroupBox(self)
        self.log_log.setTitle("Progress log")
        self.log_log.setLayout(self.log_layout)

        # Поток для вывода логов
        self.bee = Worker(self.manual_strt, ())
        self.bee.finished.connect(self.restoreUi)

        # Настройки логгера и его хэндлера
        self.logger = logging.getLogger('logger')
        self.consoleHandler = ConsoleWindowLogHandler()
        self.consoleHandler.sigLog.connect(self.log_textbox.append)
        self.consoleHandler.setFormatter(CustomFormatter())

        # Добавляем виджеты в макет окна
        self.strt_layout.addWidget(self.vyb_opt_wdgt)
        self.strt_layout.addWidget(self.label_cntrl, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.strt_layout.addWidget(self.warnings, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.strt_layout.addWidget(self.btn_wdgt, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.strt_layout.addWidget(self.log_log, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.strt_layout.setSpacing(10)

        # Окно предупреждения о запуске бэкапа раз в минуту
        self.messageW = QMessageBox()
        self.messageW.setIcon(QMessageBox.Icon.Warning)
        self.messageW.setInformativeText("Backup can be started no more than once a minute!")

        # Окно подтверждения остановки сценария бэкапа
        self.messageS = QMessageBox()
        self.messageS.setIcon(QMessageBox.Icon.Question)
        self.messageS.setInformativeText("Are you sure you want to abort the backup script? All files of this session will be deleted! And also the program can go into standby mode for a while!")
        self.messageS.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        # Окно уведомления об остановке сценария бэкапа и удалении файлов
        self.messageI = QMessageBox()
        self.messageI.setIcon(QMessageBox.Icon.Information)
        self.messageI.setInformativeText("Scenario aborted. The files have been removed.")

        # Окно уведомления о неправильной настройке почтовой отправки логов
        self.messageME = QMessageBox()
        self.messageME.setIcon(QMessageBox.Icon.Critical)
        self.messageME.setInformativeText("Email sending error! Run diagnostics and check the address(es)!")

        # Окно уведомления о невыборе ни одного бэкапа (сайты или бд)
        self.messageTT = QMessageBox()
        self.messageTT.setIcon(QMessageBox.Icon.Warning)

        self.tmblr_cron_flag = None # Флаг положения тумблера CRON'a перед бэкапом

    def del_dow_state_chngd(self):
        # Делаем неактивным чекбокс удаления файлов на сервере, если не включен чекбокс скачивания на ПК
        if not self.dow_local_cb.isChecked():
            self.del_serv_cb.setDisabled(True)
            self.del_serv_cb.setChecked(False)
        else:
            self.del_serv_cb.setEnabled(True)

    def ws_toogle_changed_state(self):
        if self.tmblr_ws.isChecked():
            for i in range(self.all_ws_combo.count()):
                item = self.all_ws_combo.model().item(i, self.all_ws_combo.modelColumn())
                item.setCheckState(Qt.CheckState.Checked)
        else:
            for i in range(self.all_ws_combo.count()):
                item = self.all_ws_combo.model().item(i, self.all_ws_combo.modelColumn())
                item.setCheckState(Qt.CheckState.Unchecked)

    def db_toogle_changed_state(self):
        if self.tmblr_db.isChecked():
            for i in range(self.all_db_combo.count()):
                item = self.all_db_combo.model().item(i, self.all_db_combo.modelColumn())
                item.setCheckState(Qt.CheckState.Checked)
        else:
            for i in range(self.all_db_combo.count()):
                item = self.all_db_combo.model().item(i, self.all_db_combo.modelColumn())
                item.setCheckState(Qt.CheckState.Unchecked)

    def date_check(self):
        # Проверка даты последнего запуска, во избежание записи в лог предыдушего запуска
        if SUSLIK_Admin().json_adder()['latest_run'] != datetime.now().strftime(SUSLIK_Admin().json_adder()['dateFormat']):
            # Запуск потока для логгирования
            self.tmblr_cron_flag = SUSLIK_Admin().tmblr_cron.isChecked()
            SUSLIK_Admin().tmblr_cron.setChecked(False)
            self.log_textbox.clear()
            self.go_btn.setEnabled(False)
            self.st_btn.setDisabled(False)
            self.logger.addHandler(self.consoleHandler)
            self.null_bckp_check()
        else:
            # Окно предупреждения о частом запуске
            self.view = self.messageW.exec()

    def null_bckp_check(self):
        if self.scenario == 1 and len(self.all_db_combo.give_all_checked_items()) < 1:
            self.messageTT.setInformativeText("Please select at least one database!")
            view = self.messageTT.exec()
            self.go_btn.setEnabled(True)
            self.st_btn.setDisabled(True)

        elif self.scenario == 2 and len(self.all_ws_combo.give_all_checked_items()) < 1:
            self.messageTT.setInformativeText("Please select at least one website!")
            view = self.messageTT.exec()
            self.go_btn.setEnabled(True)
            self.st_btn.setDisabled(True)

        elif self.scenario == 3 and (len(self.all_ws_combo.give_all_checked_items()) < 1 or len(self.all_db_combo.give_all_checked_items()) < 1):
            if len(self.all_db_combo.give_all_checked_items()) < 1 and not len(self.all_ws_combo.give_all_checked_items()) < 1:
                self.messageTT.setInformativeText("Select at least one database!")
                view = self.messageTT.exec()
            elif not len(self.all_db_combo.give_all_checked_items()) < 1 and len(self.all_ws_combo.give_all_checked_items()) < 1:
                self.messageTT.setInformativeText("Select at least one website!")
                view = self.messageTT.exec()
            else:
                self.messageTT.setInformativeText("Choose at least one database and at least one website!")
                view = self.messageTT.exec()
            self.go_btn.setEnabled(True)
            self.st_btn.setDisabled(True)

        else:
            self.bee.start()

    def manual_strt(self):
        # Ручной старт бэкапа
        try:
            if self.scenario == 1:
                run.manual_start(self.scenario, db_tuple=self.all_db_combo.give_all_checked_items(), ws_tuple=None, opt_dow=self.dow_local_cb.isChecked(), opt_del=self.del_serv_cb.isChecked())
            elif self.scenario == 2:
                run.manual_start(self.scenario, db_tuple=None, ws_tuple=self.all_ws_combo.give_all_checked_items(), opt_dow=self.dow_local_cb.isChecked(), opt_del=self.del_serv_cb.isChecked())
            elif self.scenario == 3:
                run.manual_start(self.scenario, db_tuple=self.all_db_combo.give_all_checked_items(), ws_tuple=self.all_ws_combo.give_all_checked_items(), opt_dow=self.dow_local_cb.isChecked(), opt_del=self.del_serv_cb.isChecked())
            else:
                pass
        except Exception:
            pass
        check_log_file = open(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/" + SUSLIK_Admin().json_adder()['latest_run'] + ".log", 'r')
        check_log = check_log_file.read()
        check_log_file.close()
        if SUSLIK_Admin().json_adder()['mail_alerts']:
            if 'WARNING' in check_log or 'ERROR' in check_log or 'CRITICAL' in check_log:
                try:
                    mail.run()  # Отсылаем отчёт письмом
                except Exception:
                    view = self.messageME.show()
        if self.tmblr_cron_flag:
            SUSLIK_Admin().tmblr_cron.setChecked(True)
        SUSLIK_Admin().update_edit_line()

    def manual_stp(self):
        # Ручной останов бэкапа
        self.stp_que = self.messageS.exec()
        if self.stp_que == QMessageBox.StandardButton.Yes:
            if self.scenario == 1:
                dbbckp.EOFFlag = True
            elif self.scenario == 2:
                wsbckp.EOFFlag = True
            elif self.scenario == 3:
                dbbckp.EOFFlag = True
                wsbckp.EOFFlag = True
            else:
                pass
            self.bee.wait()
            handlers = self.logger.handlers[:]
            for handler in handlers:
                self.logger.removeHandler(handler)
                handler.close()
            self.delete_files_stp()
            fh = logging.FileHandler(f"{SUSLIK_Admin().json_adder()['path_to_local_backups']}/logs/{SUSLIK_Admin().json_adder()['latest_run']}.log", mode='a', encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%d.%m.%Y %H:%M:%S'))
            self.logger.addHandler(self.consoleHandler)
            self.logger.addHandler(fh)
            self.logger.info('-------BACKUP ABORTED | FILES REMOVED-------')
            handlers = self.logger.handlers[:]
            for handler in handlers:
                self.logger.removeHandler(handler)
                handler.close()
            self.delete_files_stp()
            # При наличии ошибок в отчёте, высылаем его письмом по почте
            check_log_file = open(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/" + SUSLIK_Admin().json_adder()['latest_run'] + ".log", 'r')
            check_log = check_log_file.read()
            check_log_file.close()
            if SUSLIK_Admin().json_adder()['mail_alerts']:
                if 'WARNING' in check_log or 'ERROR' in check_log or 'CRITICAL' in check_log:
                    try:
                        mail.run()  # Отсылаем отчёт письмом
                    except Exception:
                        view = self.messageME.show()
            self.stp_inf = self.messageI.show()
            # Возвращаем крон во вкл. состояние, если он был вк. до запуска сценария бэкапа
            if self.tmblr_cron_flag:
                SUSLIK_Admin().tmblr_cron.setChecked(True)
            SUSLIK_Admin().update_edit_line()

    def restoreUi(self):
        # Восстановление кнопки "Начать" после завершения сценария бэкапа
        self.go_btn.setEnabled(True)
        self.st_btn.setDisabled(True)

    @staticmethod
    def delete_files_stp():
        # Удаление файлов прерванного бэкапа на локальном ПК
        for path, subdirs, files in os.walk(SUSLIK_Admin().json_adder()['path_to_local_backups']):
            if not path.endswith('/server') and not path.endswith('/logs'):
                for file in files:
                    if file.startswith(SUSLIK_Admin().json_adder()['latest_run']):
                        full_path = os.path.join(path, file)
                        os.remove(full_path)

        # Удаление файлов прерванного бэкапа на сервере
        temp_for_del_list = []
        client_del = paramiko.SSHClient()
        # Создаём соединение
        client_del.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client_del.connect(hostname=SUSLIK_Admin().json_adder()['ssh_host'],
                                   username=SUSLIK_Admin().json_adder()['ssh_login'],
                                   password=SUSLIK_Admin().json_adder()['ssh_password'],
                                   port=int(SUSLIK_Admin().json_adder()['ssh_port']))

        for subdir in SUSLIK_Admin().json_adder()['sys_dirs']:
            if subdir != 'server':
                ls_stdin, ls_stdout, ls_stderr = client_del.exec_command(f'cd ../{SUSLIK_Admin().json_adder()["path_to_server_backups"].strip("/")}/{subdir}; ls')
                data = ls_stdout.read()
                temp_for_del_list.extend([f'{subdir}/{file}' for file in data.decode('utf-8').strip('\n').split('\n')])

        for subdir_file in temp_for_del_list:
            if subdir_file.split('/')[1].startswith(SUSLIK_Admin().json_adder()['latest_run']):
                if not subdir_file.split('/')[1].endswith('.tar.gz'):
                    rem_stdin, rem_stdout, rem_stderr = client_del.exec_command(f'cd ../{SUSLIK_Admin().json_adder()["path_to_server_backups"].strip("/")}/{subdir_file.split("/")[0]}; rm -r {subdir_file.split("/")[1]}')
                    exit_status = rem_stdout.channel.recv_exit_status()
                else:
                    rem_stdin, rem_stdout, rem_stderr = client_del.exec_command(f'cd ../{SUSLIK_Admin().json_adder()["path_to_server_backups"].strip("/")}/{subdir_file.split("/")[0]}; rm {subdir_file.split("/")[1]}')
                    exit_status = rem_stdout.channel.recv_exit_status()

        client_del.close()

    def closeEvent(self, event):
        # Сценарий закрытия окна
        if self.bee.isRunning():
            self.manual_stp()
            event.ignore()
        else:
            event.accept()

class Worker(QThread):
    # Поток для работы окна вывода логов
    def __init__(self, func, args):
        super(Worker, self).__init__()
        self.func = func
        self.args = args

    def run(self):
        self.func(*self.args)

class IndexedButtonWidget(QPushButton):
    # Класс кнопок "опций"
    def __init__(self, parent=None):
        super(QPushButton, self).__init__(parent=parent)
        self.button_row = 0
        self.button_column = 0

class Server_finder(QWidget, metaclass=Singleton):
    # Класс интерфейса окна управления файлами бэкапов на сервере
    update_download_progress = pyqtSignal(str) # Сигнал обновления данных messagebox для скачивания
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SERVER") # Название окна

        # Установка данного окна, как единственного модального. (Блокировка остальных окон)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Настройки окна управления файлами бэкапов на сервере
        self.setFixedSize(QSize(700, 340))

        self.current_page = '1' # Номер последней открытой страницы пагинатора
        self.table_filter = '' # Фильтр таблицы
        self.table_sort = '-t' # Сортировка таблицы

        # Создаём кастомное верхнее меню кнопок
        self.menubar = QHBoxLayout()
        self.menubar.setSpacing(10)
        self.menubar.setContentsMargins(4, 0, 4, 0)

        # Кнопка "Обновить"
        self.reload_menu_btn = QPushButton(self)
        self.reload_menu_btn.setText('Update')
        self.reload_menu_btn.setIcon(QIcon(resource_path("assets/reload.png")))
        self.reload_menu_btn.clicked.connect(lambda: self.refresh_all_values())
        self.reload_menu_btn.setFixedWidth(100)
        self.reload_menu_btn.setFixedHeight(40)

        # Меню выбора фильтра для кнопки "Фильтры"
        self.filter_menu_menu = QMenu(self)
        l_font = self.reload_menu_btn.font()
        l_font.setBold(True)
        self.filter_menu_menu.addAction("All", lambda: self.filter_table()).setFont(l_font)
        self.filter_menu_menu.addAction("Websites", lambda: self.filter_table('_ws_'))
        self.filter_menu_menu.addAction("DB", lambda: self.filter_table('_db_'))
        self.filter_menu_menu.addAction("Server", lambda: self.filter_table('_sv_'))
        # Кнопка "Фильтры"
        self.filter_menu_btn = QPushButton(self)
        self.filter_menu_btn.setText('Filters')
        self.filter_menu_btn.setMenu(self.filter_menu_menu)
        self.filter_menu_btn.setIcon(QIcon(resource_path("assets/filter.png")))
        self.filter_menu_btn.setFixedWidth(100)
        self.filter_menu_btn.setFixedHeight(40)

        # Меню выбора фильтра для кнопки "Сортировка"
        self.sort_menu_menu = QMenu(self)
        self.sort_menu_menu.addAction("Date ▲", lambda: self.sort_table('-tr'))
        self.sort_menu_menu.addAction("Date ▼", lambda: self.sort_table('-t')).setFont(l_font)
        self.sort_menu_menu.addAction("Name ▲", lambda: self.sort_table(''))
        self.sort_menu_menu.addAction("Name ▼", lambda: self.sort_table('-r'))
        self.sort_menu_menu.addAction("Size ▲", lambda: self.sort_table('-Sr'))
        self.sort_menu_menu.addAction("Size ▼", lambda: self.sort_table('-S'))

        # Кнопка "Сортировка"
        self.sort_menu_btn = QPushButton(self)
        self.sort_menu_btn.setText('Sort')
        self.sort_menu_btn.setMenu(self.sort_menu_menu)
        self.sort_menu_btn.setIcon(QIcon(resource_path("assets/sort.png")))
        self.sort_menu_btn.setFixedWidth(100)
        self.sort_menu_btn.setFixedHeight(40)

        # Кнопка "Лог"
        self.log_menu_btn = QPushButton(self)
        self.log_menu_btn.setText('Log+')
        self.log_menu_btn.setIcon(QIcon(resource_path("assets/log.png")))
        self.log_menu_btn.clicked.connect(lambda: SUSLIK_Admin().open_file(f'{SUSLIK_Admin().json_adder()["path_to_local_backups"]}/logs/!log.log'))
        self.log_menu_btn.setFixedWidth(70)
        self.log_menu_btn.setFixedHeight(40)

        # Добавляем кнопки в горизонтальный шаблон
        self.menubar.addWidget(self.filter_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addWidget(self.sort_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addWidget(self.reload_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addWidget(self.log_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addStretch(1)

        # Виджет шаблона кнопок
        self.menubar_widget = QWidget()
        self.menubar_widget.setLayout(self.menubar)

        # Таблица файлов бэкапов на сервере
        self.sf_table = QTableWidget()
        self.sf_table.setColumnCount(5)
        self.sf_table.setIconSize(QSize(50, 31))
        self.sf_table.setSortingEnabled(False)

        # Настройка хеадера таблицы
        self.header = self.sf_table.horizontalHeader()
        self.header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.header.resizeSection(1, 90)
        self.header.resizeSection(2, 148)
        self.header.resizeSection(3, 60)
        self.header.resizeSection(4, 80)

        # Шаблон окна и его настройка
        self.sf_layout = QVBoxLayout()
        self.setLayout(self.sf_layout)
        self.sf_layout.setSpacing(0)
        self.sf_layout.setContentsMargins(0, 0, 0, 0)

        # Строка и кнопка поиска для фильтрации результатов
        self.filter_search_edit = QLineEdit()
        self.filter_search_edit.setPlaceholderText('Search by file name:')
        self.filter_search_edit.returnPressed.connect(lambda: self.filter_table(self.filter_search_edit.text(), type='search'))
        self.filter_search_btn = QPushButton()
        self.filter_search_btn.setIcon(QIcon(resource_path("assets/magn.png")))
        self.filter_search_btn.setFixedWidth(40)
        self.filter_search_btn.clicked.connect(lambda: self.filter_table(self.filter_search_edit.text(), type='search'))

        # Создаём кастомное верхнее поле поиска
        self.searchbar = QHBoxLayout()
        self.searchbar.setSpacing(10)
        self.searchbar.setContentsMargins(4, 0, 4, 0)

        # Добавляем строку и кнопку поиска в горизонтальный шаблон
        self.searchbar.addWidget(self.filter_search_edit)
        self.searchbar.addWidget(self.filter_search_btn)

        # Виджет шаблона поля поиска
        self.searchbar_widget = QWidget()
        self.searchbar_widget.setLayout(self.searchbar)

        # Создаём кастомное нижнее меню пагинатора
        self.paginator = QHBoxLayout()
        self.paginator.setSpacing(10)
        self.paginator.setContentsMargins(4, 0, 4, 0)

        # Строка с номером страницы
        self.cur_page_edit = QLineEdit()
        self.cur_page_edit.setText('1')
        self.cur_page_edit.returnPressed.connect(lambda: self.handle_page_return_pressed())
        self.cur_page_edit.setFixedWidth(20)

        # Кнопка стр. назад
        self.back_page_btn = QPushButton(self)
        self.back_page_btn.setObjectName('options_btn')
        self.back_page_btn.setIcon(QIcon(resource_path("assets/b-back.png")))
        self.back_page_btn.clicked.connect(lambda: self.page_move('back'))
        self.back_page_btn.setFixedWidth(14)
        self.back_page_btn.setFixedHeight(10)

        # Кнопка стр. вперёд
        self.forw_page_btn = QPushButton(self)
        self.forw_page_btn.setObjectName('options_btn')
        self.forw_page_btn.setIcon(QIcon(resource_path("assets/b-forw.png")))
        self.forw_page_btn.clicked.connect(lambda: self.page_move('forw'))
        self.forw_page_btn.setFixedWidth(14)
        self.forw_page_btn.setFixedHeight(10)

        # Выпадающий список доступных значенией "строк на страницу"
        self.rows_per_page_combo = QComboBox(self)
        self.rows_per_page_combo.setFixedHeight(22)
        self.rows_per_page_combo.setFixedWidth(68)
        self.rows_per_page_combo.addItems(["25", "50", "100", "999"])
        self.rows_per_page_combo.setCurrentIndex(0)
        self.rows_per_page_combo.currentIndexChanged.connect(lambda: self.refresh_all_values())

        # Плейсхолдер на 68 px
        self.paginator_placeholder = QLabel('')
        self.paginator_placeholder.setFixedHeight(22)
        self.paginator_placeholder.setFixedWidth(68)

        # Добавление эл-тов в шаблон пагинатора
        self.paginator.addWidget(self.paginator_placeholder)
        self.paginator.addStretch(1)
        self.paginator.addWidget(self.back_page_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.paginator.addWidget(self.cur_page_edit)
        self.paginator.addWidget(self.forw_page_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        # self.paginator.addWidget(QLabel('с.т.с'), alignment=Qt.AlignmentFlag.AlignRight)
        self.paginator.addStretch(1)
        self.paginator.addWidget(self.rows_per_page_combo, alignment=Qt.AlignmentFlag.AlignRight)

        # Виджет шаблона пагинатора
        self.paginator_widget = QWidget()
        self.paginator_widget.setLayout(self.paginator)

        # Добавление элементов на странице
        self.sf_layout.addWidget(self.menubar_widget)
        self.sf_layout.addWidget(self.searchbar_widget)
        self.sf_layout.addWidget(self.sf_table)
        self.sf_layout.addWidget(self.paginator_widget)

        self.get_all_values()  # Заполняем таблицу файлов бэкапов на сервере

        # Включаем логирование
        self.logger = logging.getLogger('logger')  # Логирование
        self.log_conf()

    def filter_table(self, filter = '', type='filter'):
        # Фильтруем таблицу по заданному фильтру
        if self.table_filter != filter:
            self.current_page = '1'
            self.cur_page_edit.setText(self.current_page)
            self.table_filter = filter
            self.refresh_all_values()
            if type != 'search':
                # Делаем шрифт bold для нажатого пункта меню кнопки
                l_font = self.sender().font()
                for item in self.filter_menu_menu.actions():
                    item.setFont(l_font)
                l_font.setBold(True)
                self.sender().setFont(l_font)
            else:
                # Сброс bold'a
                l_font = self.sender().font()
                for item in self.filter_menu_menu.actions():
                    item.setFont(l_font)

    def sort_table(self, sort = ''):
        # Сортируем таблицу по заданной сортировке
        if self.table_sort != sort:
            self.current_page = '1'
            self.cur_page_edit.setText(self.current_page)
            self.table_sort = sort
            self.refresh_all_values()
            # Делаем шрифт bold для нажатого пункта меню кнопки
            l_font = self.sender().font()
            for item in self.sort_menu_menu.actions():
                item.setFont(l_font)
            l_font.setBold(True)
            self.sender().setFont(l_font)

    def page_move(self, vector):
        # Функция передвижения по страницам с помощью стрелочек
        if vector == 'back':
            if int(self.cur_page_edit.text()) > 1:
                self.cur_page_edit.setText(str(int(self.cur_page_edit.text()) - 1))
                self.current_page = self.cur_page_edit.text()
                self.refresh_all_values()
        else:
            if self.sf_table.rowCount() == int(self.rows_per_page_combo.currentText()):
                self.cur_page_edit.setText(str(int(self.cur_page_edit.text()) + 1))
                self.current_page = self.cur_page_edit.text()
                self.refresh_all_values()

    def handle_page_return_pressed(self):
        # Функция передвижения по страницам с помощью ффода номера страницы вручную
        if not int(self.cur_page_edit.text()) == int(self.current_page):
            try:
                if int(self.cur_page_edit.text()) < 1:
                    self.cur_page_edit.setText('1')
                    self.current_page = self.cur_page_edit.text()
                    self.refresh_all_values()
                else:
                    if self.sf_table.rowCount() < int(self.rows_per_page_combo.currentText()):
                        if int(self.cur_page_edit.text()) < int(self.current_page):
                            self.current_page = self.cur_page_edit.text()
                            self.refresh_all_values()
                        else:
                            self.cur_page_edit.setText(self.current_page)
                    else:
                        self.current_page = self.cur_page_edit.text()
                        self.refresh_all_values()
            except Exception:
                self.cur_page_edit.setText('1')
                self.current_page = self.cur_page_edit.text()
                self.refresh_all_values()

    def page_calc(self, page):
        # Высчитываем границы номеров строк для конкретной страницы
        min_row = (page - 1) * int(self.rows_per_page_combo.currentText()) + 1
        max_row = page * int(self.rows_per_page_combo.currentText())
        return min_row, max_row

    # def filter(self, filter_text):
    #     for i in range(self.sf_table.rowCount()):
    #         item = self.sf_table.item(i, 0)
    #         self.sf_table.setRowHidden(i, True)
    #         match = filter_text.lower() not in item.text().lower()
    #         if not match:
    #             self.sf_table.setRowHidden(i, match)

    def sizeof_fmt(self, num, suffix="B"):
        # Перевод байтов в Кб, Мб, Гб и т.п.
        for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Y{suffix}"

    def get_all_values(self):
        # Путь папки с бэкапами на сервере
        self.serv_path = SUSLIK_Admin().json_adder()['path_to_server_backups']
        self.serv_path.lstrip('/')
        self.serv_path.rstrip('/')
        # Создаём соединение с cервером по SSH
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=SUSLIK_Admin().json_adder()['ssh_host'], username=SUSLIK_Admin().json_adder()['ssh_login'],
                       password=SUSLIK_Admin().json_adder()['ssh_password'], port=int(SUSLIK_Admin().json_adder()['ssh_port']))

        # Создаём список подпапок (если таковые есть) и их х-ки
        stdin_dirs, stdout_dirs, stderr_dirs = client.exec_command(f'cd ../{self.serv_path}; ls -d */')
        data_dirs = stdout_dirs.read()
        pdata_dirs = data_dirs.decode('utf-8').strip('\n').split('\n')
        pdata_dirs = [x.rstrip('/') for x in pdata_dirs]

        # Иконка дублирующегося файла
        self.dubl_img_icn = QIcon()
        self.dubl_img_icn.addFile(resource_path("assets/d-sign.png"))

        # Иконка уникального файла
        self.uniq_img_icn = QIcon()
        self.uniq_img_icn.addFile(resource_path("assets/y-sign.png"))

        # Иконка кнопки "опций" -удалить-
        self.file_delete_icn = QIcon()
        self.file_delete_icn.addFile(resource_path("assets/o-del.png"))

        # Иконка кнопки "опций" -скачать-
        self.file_download_icn = QIcon()
        self.file_download_icn.addFile(resource_path("assets/o-dow.png"))

        # Инфо-окно на время скачивания бэкапа
        self.messageDoSF_text = 'File download in progress.\nPlease wait...\nProgress: 0%'
        self.messageDoSF = Server_Download_Message()
        self.messageDoSF.setIcon(QMessageBox.Icon.Information)
        self.messageDoSF.setInformativeText(self.messageDoSF_text)
        self.messageDoSF.setStandardButtons(QMessageBox.StandardButton.NoButton)
        self.break_button = self.messageDoSF.addButton(QPushButton('Abort'), QMessageBox.ButtonRole.RejectRole)

        self.update_download_progress.connect(self.messageDoSF.setInformativeText)

        sys_dirs = SUSLIK_Admin().json_adder()['sys_dirs'] # Список папок, которые создаются и рассматриваются программой: site, databaыe, server (на момент написания кода)

        session_row_index = 0
        session_row_min_index, session_row_max_index = self.page_calc(int(self.cur_page_edit.text()))
        break_flag = False
        for dir in pdata_dirs:
            if not break_flag: # Проверка на достижения лимита записей на страницу
                # Перебираем папки из набора (site-database-server)
                if dir in sys_dirs:
                    stdin_dir_con, stdout_dir_con, stderr_dir_con = client.exec_command(f'cd ../{self.serv_path}/{dir}; ls {self.table_sort}')
                    data_dir_con = stdout_dir_con.read()
                    pdata_dir_con = data_dir_con.decode('utf-8').strip('\n').split('\n')
                    for file in pdata_dir_con:
                        # Перебираем файлы в папке
                        if file:
                            if self.table_filter in file:
                                session_row_index += 1 # Увеличиваем счётчик рассмотренных файлов (строк таблицы)
                                if session_row_index < session_row_min_index:
                                    pass
                                elif session_row_index > session_row_max_index:
                                    break_flag = True
                                    break
                                else:
                                    rowPosition = self.sf_table.rowCount()  # Актуальное кол-во строк таблицы
                                    stdin_dir_file, stdout_dir_file, stderr_dir_file = client.exec_command(f'cd ../{self.serv_path}/{dir}; stat --printf="%s¤%y" {file}')
                                    data_dir_file = stdout_dir_file.read()
                                    pdata_dir_file = data_dir_file.decode('utf-8').strip('\n').split('\n')
                                    file_size = self.sizeof_fmt(int(pdata_dir_file[0].split('¤')[0])) # Получаем человеко-читаемый размер файла
                                    file_mod_time = pdata_dir_file[0].split('¤')[1].split('.')[0] # Получаем значение даты и времени изменения файла

                                    # Объект иконки дублирующегося файла
                                    dubl_img_item = QTableWidgetItem()
                                    dubl_img_item.setIcon(self.dubl_img_icn)
                                    dubl_img_item.setSizeHint(QSize(50, 31))

                                    # Объект иконки уникального файла
                                    uniq_img_item = QTableWidgetItem()
                                    uniq_img_item.setIcon(self.uniq_img_icn)
                                    uniq_img_item.setSizeHint(QSize(50, 31))

                                    # Кнопка "опций" -удалить-
                                    file_delete_btn = IndexedButtonWidget()
                                    file_delete_btn.button_row = rowPosition
                                    file_delete_btn.button_column = 3
                                    file_delete_btn.setIcon(self.file_delete_icn)
                                    file_delete_btn.setFixedSize(QSize(25, 25))
                                    file_delete_btn.setObjectName('options_btn_delete')
                                    file_delete_btn.clicked.connect(lambda: self.handle_button_click(file_delete_btn.objectName()))

                                    # Кнопка "опций" -скачать-
                                    file_download_btn = IndexedButtonWidget()
                                    file_download_btn.button_row = rowPosition
                                    file_download_btn.button_column = 3
                                    file_download_btn.setIcon(self.file_download_icn)
                                    file_download_btn.setFixedSize(QSize(25, 25))
                                    file_download_btn.setObjectName('options_btn_download')
                                    file_download_btn.clicked.connect(lambda: self.handle_button_click(file_download_btn.objectName()))

                                    # Создаём кастомную ячейку кнопок "опций"
                                    options = QHBoxLayout()
                                    options.setSpacing(0)
                                    options.setContentsMargins(4, 0, 4, 0)

                                    # Добавляем кнопки "опций" в горизонтальный шаблон
                                    options.addWidget(file_delete_btn)
                                    options.addWidget(file_download_btn)

                                    # Виджет шаблона кнопок "опций"
                                    options_widget = QWidget()
                                    options_widget.setLayout(options)
                                    options_widget.setFixedWidth(80)

                                    # Позиционируем элементы и записываем данные в ячейки
                                    self.sf_table.setHorizontalHeaderLabels(["Name", "Size", "Date of change", "Unique", "Action"])
                                    self.sf_table.insertRow(rowPosition)
                                    self.sf_table.setItem(rowPosition, 0, QTableWidgetItem(file))
                                    self.sf_table.setItem(rowPosition, 1, QTableWidgetItem(file_size))
                                    self.sf_table.setItem(rowPosition, 2, QTableWidgetItem(file_mod_time))
                                    try:
                                        # Скрипт проверки на уникальность файла + сравнение размера
                                        self.local_path = SUSLIK_Admin().json_adder()['path_to_local_backups']
                                        f = open(f'{self.local_path}/{dir}/{file}')
                                        f.close()
                                        self.sf_table.setItem(rowPosition, 3, dubl_img_item)
                                        file_download_btn.setDisabled(True) # Кнопка скачивания становится неактивной, если файл уже имеется на локальном ПК
                                        local_stat_size = int(os.stat(f'{self.local_path}/{dir}/{file}').st_size) # Размер файла на локальном ПК
                                        serv_stat_size = int(pdata_dir_file[0].split('¤')[0]) # Размер файла на сервере
                                        if local_stat_size != serv_stat_size:
                                            self.sf_table.item(rowPosition, 1).setBackground(QColor(251, 241, 102))
                                            self.sf_table.item(rowPosition, 1).setToolTip(f'Server Size: {self.sizeof_fmt(serv_stat_size)} PC size: {self.sizeof_fmt(local_stat_size)}')
                                    except Exception:
                                        self.sf_table.setItem(rowPosition, 3, uniq_img_item)
                                    self.sf_table.setCellWidget(rowPosition, 4, options_widget)
        client.close()

    def handle_button_click(self, action):
        # Обработка сигнала от клика по кнопке удаления/скачивания файла на сервере
        button = self.sender()
        self.filename = self.sf_table.item(button.button_row, 0).text()
        # Окно подтверждения удаления файла бэкапа на ПК, если таковой есть
        self.messageDLF = QMessageBox()
        self.messageDLF.setIcon(QMessageBox.Icon.Question)
        self.messageDLF.setInformativeText(f'This file is also present on the local PC. Delete duplicate on PC?')
        self.messageDLF.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # Выьор папки в зависимости от суфикса в названии файла
        self.final_folder = ''
        if '_db_' in self.filename:
            self.final_folder = 'database'
        elif '_ws_' in self.filename:
            self.final_folder = 'site'
        else:
            self.final_folder = 'server'
        if action == 'options_btn_delete':
            self.delete_serv_file()
        else:
            self.download_serv_file()

    def delete_serv_file(self):
        # Удаляем файл на сервере по SSH
        # Окно подтверждения удаления файла бэкапа на сервере
        self.messageDeSF = Server_Delete_Message()
        self.messageDeSF.setIcon(QMessageBox.Icon.Question)
        self.messageDeSF.setInformativeText(f'Are you sure you want to delete the file <b>"{self.filename}"</b> on server? This action cannot be undone!')
        self.messageDeSF.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        # Окно ожидания во время удаления файла
        self.messageDwSF = Server_Delete_Message()
        self.messageDwSF.setIcon(QMessageBox.Icon.Information)
        self.messageDwSF.setInformativeText(f'File deletion in progress.\nPlease wait...')
        self.messageDwSF.setStandardButtons(QMessageBox.StandardButton.NoButton)
        self.delete_serv_act = self.messageDeSF.exec()
        if self.delete_serv_act == QMessageBox.StandardButton.Yes:
            self.messageDwSF.show()
            QApplication.processEvents()
            # Поток для удаления
            self.serv_delete_thread = Server_Delete_Thread(self.server_delete)
            self.serv_delete_thread.finished.connect(self.messageDwSF.close)
            self.serv_delete_thread.finished.connect(lambda: self.on_thread_finish('delete'))
            self.serv_delete_thread.start()

    def server_delete(self):
        # Создаём соединение
        self.client_del = paramiko.SSHClient()
        self.client_del.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client_del.connect(hostname=SUSLIK_Admin().json_adder()['ssh_host'],
                       username=SUSLIK_Admin().json_adder()['ssh_login'],
                       password=SUSLIK_Admin().json_adder()['ssh_password'],
                       port=int(SUSLIK_Admin().json_adder()['ssh_port']))

        # Указываем конечную папку, в зависимости от типа файла бэкапа
        stdin, stdout, stderr = self.client_del.exec_command(f'cd {self.serv_path}/{self.final_folder}; rm {self.filename}')
        exit_status = stdout.channel.recv_exit_status()
        self.client_del.close()

    def download_serv_file(self):
        # Скачиваем файл по FTP
        # Инфо-окно на время скачивания бэкапа
        self.download_alive = True
        self.messageDoSF.show()
        self.messageDoSF.repaint()
        self.messageDoSF.buttonClicked.connect(lambda: self.break_serv_file_download())
        QApplication.processEvents()
        # Поток для скачивания
        self.serv_download_thread = Server_Download_Thread(self.server_download)
        self.serv_download_thread.finished.connect(self.messageDoSF.close)
        self.serv_download_thread.finished.connect(lambda: self.on_thread_finish('download'))
        self.serv_download_thread.start()

    def server_download(self):
        # Создаём соединение, находим файл
        self.server_dow = ftplib.FTP()
        self.server_dow.connect(SUSLIK_Admin().json_adder()['ftp_host'], int(SUSLIK_Admin().json_adder()['ftp_port']))
        self.server_dow.login(SUSLIK_Admin().json_adder()['ftp_login'], SUSLIK_Admin().json_adder()['ftp_password'])
        self.server_dow.encoding = "utf-8"
        self.server_dow.cwd(f'/{self.serv_path}/{self.final_folder}')
        self.dynamic_file_to_download_size = 0 # Динамический размер файла (обновляется при прогрессе скачивания)
        self.file_to_download_size = self.server_dow.size(self.filename) # Полный достижимый размер скачиваемого файла
        if not os.path.isdir(f'{self.local_path}/{self.final_folder}'):
            os.makedirs(f'{self.local_path}/{self.final_folder}')
        with open(f'{self.local_path}/{self.final_folder}/{self.filename}', 'wb') as self.my_file:
            self.server_dow.retrbinary('RETR ' + self.filename, self.file_download_write)
        self.server_dow.quit()
        QApplication.processEvents()
        sleep(0.2) # Пауза чтобы прочитать текст messagebox о завершении скачивания

    def file_download_write(self, data):
        # Функция записи потока данных в файл при скачивании
        if self.download_alive:
            self.my_file.write(data)
            self.dynamic_file_to_download_size += len(data) # Обновление значения скачанных байтов файла
            messageDoSF_text = f'File downloading.\nPlease wait...\nProgress: {round(((self.dynamic_file_to_download_size / self.file_to_download_size) * 100), 2)}%'
            self.update_download_progress.emit(messageDoSF_text) # Сигнал классу окна управления файлов сервера для обновления значения в % скачанного файла
        else:
            self.serv_download_thread.terminate()
            try:
                os.remove(f'{self.local_path}/{self.final_folder}/{self.filename}')
            except Exception:
                pass

    def on_thread_finish(self, type):
        # Ф-ия по завершению потока
        if type == 'download':
            QApplication.processEvents()
            self.logger.info(f'⁙"SERVER" WINDOW⁙ Backup file downloaded from server to local PC: "{self.filename}"')
        else:
            QApplication.processEvents()
            self.logger.info(f'⁙"SERVER" WINDOW⁙ Deleted backup file on the server: "{self.filename}"')
            try:
                # Если файл дублируется, предложить удалить на локальном ПК
                f = open(f'{self.local_path}/{self.final_folder}/{self.filename}')
                f.close()
                delete_local_act = self.messageDLF.exec()
                if delete_local_act == QMessageBox.StandardButton.Yes:
                    self.messageDwSF.show()
                    QApplication.processEvents()
                    os.remove(f'{self.local_path}/{self.final_folder}/{self.filename}')
                    self.logger.info(f'⁙"SERVER" WINDOW⁙ Deleted backup file on local PC: "{self.filename}"')
                    self.messageDwSF.close()
                    QApplication.processEvents()
            except Exception:
                pass
        self.refresh_all_values()

    def break_serv_file_download(self):
        # Ф-ия прерывания скачивания файла
        self.download_alive = False

    def refresh_all_values(self):
        # Обновление таблицы
        self.sf_table.clear()
        self.sf_table.setRowCount(0)
        self.get_all_values()

    def log_conf(self):
        # Создаём лог-файл
        try:
            os.stat(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/")
        except Exception:
            os.makedirs(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/")
        open(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/!log.log", 'a+').close()

        handlers = self.logger.handlers[:]
        for handler in handlers:
            self.logger.removeHandler(handler)
            handler.close()

        # Конфигурация логирования
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%d.%m.%Y %H:%M:%S')
        fh = logging.FileHandler(f"{SUSLIK_Admin().json_adder()['path_to_local_backups']}/logs/!log.log", mode='a', encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def closeEvent(self, event):
        # Сценарий закрытия окна
        # Удаляем хендлеры логирования
        handlers = self.logger.handlers[:]
        for handler in handlers:
            self.logger.removeHandler(handler)
            handler.close()

        logging.shutdown()  # Выключаем логирование
        event.accept()

class Server_Download_Message(QMessageBox):
    # Класс окна сообщений о скачивании файла
    def __init__(self, parent=None):
        super(Server_Download_Message, self).__init__(parent)

    def closeEvent(self, event):
        # Сценарий закрытия окна
        Server_finder().break_serv_file_download()
        event.accept()

class Server_Delete_Message(QMessageBox):
    # Класс окна сообщений об удалении файла
    def __init__(self, parent=None):
        super(Server_Delete_Message, self).__init__(parent)

    def closeEvent(self, event):
        # Сценарий закрытия окна
        if Server_finder().serv_delete_thread.isRunning():
            event.ignore()
        else:
            event.accept()

class Server_Download_Thread(QThread):
    # Поток для работы скачивания файла с сервера
    def __init__(self, func):
        super(Server_Download_Thread, self).__init__()
        self.func = func

    def run(self):
        self.func()

class Server_Delete_Thread(QThread):
    # Поток для работы удаления файла с сервера
    def __init__(self, func):
        super(Server_Delete_Thread, self).__init__()
        self.func = func

    def run(self):
        self.func()


class Local_finder(QWidget, metaclass=Singleton):
    # Класс интерфейса окна управления файлами бэкапов на локальном ПК
    def __init__(self):
        super().__init__()

        self.setWindowTitle("LOCAL PC") # Название окна

        # Установка данного окна, как единственного модального. (Блокировка остальных окон)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Настройки окна управления файлами бэкапов на сервере
        self.setFixedSize(QSize(700, 340))

        self.current_page = '1' # Номер последней открытой страницы пагинатора
        self.table_filter = '' # Фильтр таблицы
        self.table_sort = '-t'  # Сортировка таблицы

        # Создаём кастомное верхнее меню кнопок
        self.menubar = QHBoxLayout()
        self.menubar.setSpacing(10)
        self.menubar.setContentsMargins(4, 0, 4, 0)

        # Кнопка "Обновить"
        self.reload_menu_btn = QPushButton(self)
        self.reload_menu_btn.setText('Update')
        self.reload_menu_btn.setIcon(QIcon(resource_path("assets/reload.png")))
        self.reload_menu_btn.clicked.connect(lambda: self.refresh_all_values())
        self.reload_menu_btn.setFixedWidth(100)
        self.reload_menu_btn.setFixedHeight(40)

        # Меню выбора фильтра для кнопки "Фильтры"
        self.filter_menu_menu = QMenu(self)
        l_font = self.reload_menu_btn.font()
        l_font.setBold(True)
        self.filter_menu_menu.addAction("All", lambda: self.filter_table()).setFont(l_font)
        self.filter_menu_menu.addAction("Websites", lambda: self.filter_table('_ws_'))
        self.filter_menu_menu.addAction("DB", lambda: self.filter_table('_db_'))
        self.filter_menu_menu.addAction("Server", lambda: self.filter_table('_sv_'))

        # Кнопка "Фильтры"
        self.filter_menu_btn = QPushButton(self)
        self.filter_menu_btn.setText('Filters')
        self.filter_menu_btn.setMenu(self.filter_menu_menu)
        self.filter_menu_btn.setIcon(QIcon(resource_path("assets/filter.png")))
        self.filter_menu_btn.setFixedWidth(100)
        self.filter_menu_btn.setFixedHeight(40)

        # Меню выбора фильтра для кнопки "Сортировка"
        self.sort_menu_menu = QMenu(self)
        self.sort_menu_menu.addAction("Date ▲", lambda: self.sort_table('-tr'))
        self.sort_menu_menu.addAction("Date ▼", lambda: self.sort_table('-t')).setFont(l_font)
        self.sort_menu_menu.addAction("Name ▲", lambda: self.sort_table(''))
        self.sort_menu_menu.addAction("Name ▼", lambda: self.sort_table('-r'))
        self.sort_menu_menu.addAction("Size ▲", lambda: self.sort_table('-Sr'))
        self.sort_menu_menu.addAction("Size ▼", lambda: self.sort_table('-S'))

        # Кнопка "Сортировка"
        self.sort_menu_btn = QPushButton(self)
        self.sort_menu_btn.setText('Sort')
        self.sort_menu_btn.setMenu(self.sort_menu_menu)
        self.sort_menu_btn.setIcon(QIcon(resource_path("assets/sort.png")))
        self.sort_menu_btn.setFixedWidth(100)
        self.sort_menu_btn.setFixedHeight(40)

        # Кнопка "Лог"
        self.log_menu_btn = QPushButton(self)
        self.log_menu_btn.setText('Log+')
        self.log_menu_btn.setIcon(QIcon(resource_path("assets/log.png")))
        self.log_menu_btn.clicked.connect(lambda: SUSLIK_Admin().open_file(f'{SUSLIK_Admin().json_adder()["path_to_local_backups"]}/logs/!log.log'))
        self.log_menu_btn.setFixedWidth(70)
        self.log_menu_btn.setFixedHeight(40)

        # Добавляем кнопки в горизонтальный шаблон
        self.menubar.addWidget(self.filter_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addWidget(self.sort_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addWidget(self.reload_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addWidget(self.log_menu_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self.menubar.addStretch(1)

        # Виджет шаблона кнопок
        self.menubar_widget = QWidget()
        self.menubar_widget.setLayout(self.menubar)

        # Таблица файлов бэкапов на сервере
        self.sf_table = QTableWidget()
        self.sf_table.setColumnCount(5)
        self.sf_table.setIconSize(QSize(50, 31))
        self.sf_table.setSortingEnabled(False)

        # Настройка хеадера таблицы
        self.header = self.sf_table.horizontalHeader()
        self.header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.header.resizeSection(1, 90)
        self.header.resizeSection(2, 148)
        self.header.resizeSection(3, 60)
        self.header.resizeSection(4, 80)

        # Шаблон окна и его настройка
        self.sf_layout = QVBoxLayout()
        self.setLayout(self.sf_layout)
        self.sf_layout.setSpacing(0)
        self.sf_layout.setContentsMargins(0, 0, 0, 0)

        # Строка и кнопка поиска для фильтрации результатов
        self.filter_search_edit = QLineEdit()
        self.filter_search_edit.setPlaceholderText('Search by file name:')
        self.filter_search_edit.returnPressed.connect(lambda: self.filter_table(self.filter_search_edit.text(), type='search'))
        self.filter_search_btn = QPushButton()
        self.filter_search_btn.setIcon(QIcon(resource_path("assets/magn.png")))
        self.filter_search_btn.setFixedWidth(40)
        self.filter_search_btn.clicked.connect(lambda: self.filter_table(self.filter_search_edit.text(), type='search'))

        # Создаём кастомное верхнее поле поиска
        self.searchbar = QHBoxLayout()
        self.searchbar.setSpacing(10)
        self.searchbar.setContentsMargins(4, 0, 4, 0)

        # Добавляем строку и кнопку поиска в горизонтальный шаблон
        self.searchbar.addWidget(self.filter_search_edit)
        self.searchbar.addWidget(self.filter_search_btn)

        # Виджет шаблона поля поиска
        self.searchbar_widget = QWidget()
        self.searchbar_widget.setLayout(self.searchbar)

        # Создаём кастомное нижнее меню пагинатора
        self.paginator = QHBoxLayout()
        self.paginator.setSpacing(10)
        self.paginator.setContentsMargins(4, 0, 4, 0)

        # Строка с номером страницы
        self.cur_page_edit = QLineEdit()
        self.cur_page_edit.setText('1')
        self.cur_page_edit.returnPressed.connect(lambda: self.handle_page_return_pressed())
        self.cur_page_edit.setFixedWidth(20)

        # Кнопка стр. назад
        self.back_page_btn = QPushButton(self)
        self.back_page_btn.setObjectName('options_btn')
        self.back_page_btn.setIcon(QIcon(resource_path("assets/b-back.png")))
        self.back_page_btn.clicked.connect(lambda: self.page_move('back'))
        self.back_page_btn.setFixedWidth(14)
        self.back_page_btn.setFixedHeight(10)

        # Кнопка стр. вперёд
        self.forw_page_btn = QPushButton(self)
        self.forw_page_btn.setObjectName('options_btn')
        self.forw_page_btn.setIcon(QIcon(resource_path("assets/b-forw.png")))
        self.forw_page_btn.clicked.connect(lambda: self.page_move('forw'))
        self.forw_page_btn.setFixedWidth(14)
        self.forw_page_btn.setFixedHeight(10)

        # Выпадающий список доступных значенией "строк на страницу"
        self.rows_per_page_combo = QComboBox(self)
        self.rows_per_page_combo.setFixedHeight(22)
        self.rows_per_page_combo.setFixedWidth(68)
        self.rows_per_page_combo.addItems(["25", "50", "100", "999"])
        self.rows_per_page_combo.setCurrentIndex(0)
        self.rows_per_page_combo.currentIndexChanged.connect(lambda: self.refresh_all_values())

        # Плейсхолдер на 68 px
        self.paginator_placeholder = QLabel('')
        self.paginator_placeholder.setFixedHeight(22)
        self.paginator_placeholder.setFixedWidth(68)

        # Добавление эл-тов в шаблон пагинатора
        self.paginator.addWidget(self.paginator_placeholder)
        self.paginator.addStretch(1)
        self.paginator.addWidget(self.back_page_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.paginator.addWidget(self.cur_page_edit)
        self.paginator.addWidget(self.forw_page_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        # self.paginator.addWidget(QLabel('с.т.с'), alignment=Qt.AlignmentFlag.AlignRight)
        self.paginator.addStretch(1)
        self.paginator.addWidget(self.rows_per_page_combo, alignment=Qt.AlignmentFlag.AlignRight)

        # Виджет шаблона пагинатора
        self.paginator_widget = QWidget()
        self.paginator_widget.setLayout(self.paginator)

        # Добавление элементов на странице
        self.sf_layout.addWidget(self.menubar_widget)
        self.sf_layout.addWidget(self.searchbar_widget)
        self.sf_layout.addWidget(self.sf_table)
        self.sf_layout.addWidget(self.paginator_widget)

        self.get_all_values()  # Заполняем таблицу файлов бэкапов на сервере

        # Включаем логирование
        self.logger = logging.getLogger('logger')  # Логирование
        self.log_conf()

    def filter_table(self, filter='', type='filter'):
        # Фильтруем таблицу по заданному фильтру
        if self.table_filter != filter:
            self.current_page = '1'
            self.cur_page_edit.setText(self.current_page)
            self.table_filter = filter
            self.refresh_all_values()
            if type != 'search':
                # Делаем шрифт bold для нажатого пункта меню кнопки
                l_font = self.sender().font()
                for item in self.filter_menu_menu.actions():
                    item.setFont(l_font)
                l_font.setBold(True)
                self.sender().setFont(l_font)
            else:
                # Сброс bold'a
                l_font = self.sender().font()
                for item in self.filter_menu_menu.actions():
                    item.setFont(l_font)

    def sort_table(self, sort = ''):
        # Сортируем таблицу по заданной сортировке
        if self.table_sort != sort:
            self.current_page = '1'
            self.cur_page_edit.setText(self.current_page)
            self.table_sort = sort
            self.refresh_all_values()
            # Делаем шрифт bold для нажатого пункта меню кнопки
            l_font = self.sender().font()
            for item in self.sort_menu_menu.actions():
                item.setFont(l_font)
            l_font.setBold(True)
            self.sender().setFont(l_font)

    def page_move(self, vector):
        # Функция передвижения по страницам с помощью стрелочек
        if vector == 'back':
            if int(self.cur_page_edit.text()) > 1:
                self.cur_page_edit.setText(str(int(self.cur_page_edit.text()) - 1))
                self.current_page = self.cur_page_edit.text()
                self.refresh_all_values()
        else:
            if self.sf_table.rowCount() == int(self.rows_per_page_combo.currentText()):
                self.cur_page_edit.setText(str(int(self.cur_page_edit.text()) + 1))
                self.current_page = self.cur_page_edit.text()
                self.refresh_all_values()

    def handle_page_return_pressed(self):
        # Функция передвижения по страницам с помощью ффода номера страницы вручную
        if not int(self.cur_page_edit.text()) == int(self.current_page):
            try:
                if int(self.cur_page_edit.text()) < 1:
                    self.cur_page_edit.setText('1')
                    self.current_page = self.cur_page_edit.text()
                    self.refresh_all_values()
                else:
                    if self.sf_table.rowCount() < int(self.rows_per_page_combo.currentText()):
                        if int(self.cur_page_edit.text()) < int(self.current_page):
                            self.current_page = self.cur_page_edit.text()
                            self.refresh_all_values()
                        else:
                            self.cur_page_edit.setText(self.current_page)
                    else:
                        self.current_page = self.cur_page_edit.text()
                        self.refresh_all_values()
            except Exception:
                self.cur_page_edit.setText('1')
                self.current_page = self.cur_page_edit.text()
                self.refresh_all_values()

    def page_calc(self, page):
        # Высчитываем границы номеров строк для конкретной страницы
        min_row = (page - 1) * int(self.rows_per_page_combo.currentText()) + 1
        max_row = page * int(self.rows_per_page_combo.currentText())
        return min_row, max_row

    # def filter(self, filter_text):
    #     for i in range(self.sf_table.rowCount()):
    #         item = self.sf_table.item(i, 0)
    #         self.sf_table.setRowHidden(i, True)
    #         match = filter_text.lower() not in item.text().lower()
    #         if not match:
    #             self.sf_table.setRowHidden(i, match)

    def sizeof_fmt(self, num, suffix="B"):
        # Перевод байтов в Кб, Мб, Гб и т.п.
        for unit in ["", "K", "M", "G", "T", "P", "E", "Z"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Y{suffix}"

    def get_all_values(self):
        # Путь папки с бэкапами на сервере
        self.serv_path = SUSLIK_Admin().json_adder()['path_to_server_backups']
        self.serv_path.lstrip('/')
        self.serv_path.rstrip('/')
        # Путь папки с бэкапами на локальном ПК
        self.local_path = SUSLIK_Admin().json_adder()['path_to_local_backups']
        # Создаём соединение с cервером по SSH
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=SUSLIK_Admin().json_adder()['ssh_host'], username=SUSLIK_Admin().json_adder()['ssh_login'],
                       password=SUSLIK_Admin().json_adder()['ssh_password'], port=int(SUSLIK_Admin().json_adder()['ssh_port']))

        # Создаём список подпапок (если таковые есть) и их х-ки
        stdin_dirs, stdout_dirs, stderr_dirs = client.exec_command(f'cd ../{self.serv_path}; ls -d */')
        data_dirs = stdout_dirs.read()
        pdata_dirs = data_dirs.decode('utf-8').strip('\n').split('\n')
        pdata_dirs = [x.rstrip('/') for x in pdata_dirs]

        # Папки в каталоге локального ПК
        root, dirs, files = os.walk(self.local_path).__next__()

        # Иконка дублирующегося файла
        self.dubl_img_icn = QIcon()
        self.dubl_img_icn.addFile(resource_path("assets/d-sign.png"))

        # Иконка уникального файла
        self.uniq_img_icn = QIcon()
        self.uniq_img_icn.addFile(resource_path("assets/y-sign.png"))

        # Иконка кнопки "опций" -удалить-
        self.file_delete_icn = QIcon()
        self.file_delete_icn.addFile(resource_path("assets/o-del.png"))

        sys_dirs = SUSLIK_Admin().json_adder()['sys_dirs'] # Список папок, которые создаются и рассматриваются программой: site, database, server (на момент написания кода)

        session_row_index = 0
        session_row_min_index, session_row_max_index = self.page_calc(int(self.cur_page_edit.text()))
        break_flag = False
        for dir in dirs:
            if not break_flag:  # Проверка на достижения лимита записей на страницу
                # Перебираем папки из набора (site-database-server)
                if dir in sys_dirs:

                    # Файлы на локальном ПК
                    process = subprocess.Popen(f'cd {SUSLIK_Admin().json_adder()["path_to_local_backups"]}/{dir} ; ls {self.table_sort}', stdout=subprocess.PIPE, shell=True)
                    soutput, serror = process.communicate()
                    pdata_dir_local = [str(file) for file in soutput.decode('utf-8').strip('\n').split('\n') if not str(file).startswith('.')]

                    for file in pdata_dir_local:
                        if file:
                            if self.table_filter in file:
                                session_row_index += 1  # Увеличиваем счётчик рассмотренных файлов (строк таблицы)
                                if session_row_index < session_row_min_index:
                                    pass
                                elif session_row_index > session_row_max_index:
                                    break_flag = True
                                    break
                                else:
                                    # Перебираем файлы в папке
                                    rowPosition = self.sf_table.rowCount()  # Актуальное кол-во строк таблицы

                                    stdin_dir_file, stdout_dir_file, stderr_dir_file = client.exec_command(f'cd ../{self.serv_path}/{dir}; stat --printf="%s¤%y" {file}')
                                    data_dir_file = stdout_dir_file.read()
                                    pdata_dir_file = data_dir_file.decode('utf-8').strip('\n').split('\n')

                                    # Объект иконки дублирующегося файла
                                    dubl_img_item = QTableWidgetItem()
                                    dubl_img_item.setIcon(self.dubl_img_icn)
                                    dubl_img_item.setSizeHint(QSize(50, 31))

                                    # Объект иконки уникального файла
                                    uniq_img_item = QTableWidgetItem()
                                    uniq_img_item.setIcon(self.uniq_img_icn)
                                    uniq_img_item.setSizeHint(QSize(50, 31))

                                    # Кнопка "опций" -удалить-
                                    file_delete_btn = IndexedButtonWidget()
                                    file_delete_btn.button_row = rowPosition
                                    file_delete_btn.button_column = 3
                                    file_delete_btn.setIcon(self.file_delete_icn)
                                    file_delete_btn.setFixedSize(QSize(80, 29))
                                    file_delete_btn.setObjectName('options_btn_delete')
                                    file_delete_btn.clicked.connect(lambda: self.handle_button_click(file_delete_btn.objectName()))

                                    local_stat_size = int(os.stat(f'{self.local_path}/{dir}/{file}').st_size)  # Размер файла на локальном ПК
                                    local_stat_date = str(datetime.fromtimestamp(os.path.getmtime(f'{self.local_path}/{dir}/{file}'))).split('.')[0] # Время создания/изменения файла на локальном ПК
                                    # Позиционируем элементы и записываем данные в ячейки
                                    self.sf_table.setHorizontalHeaderLabels(["Name", "Size", "Date of change", "Unique", "Action"])
                                    self.sf_table.insertRow(rowPosition)
                                    self.sf_table.setItem(rowPosition, 0, QTableWidgetItem(file))
                                    self.sf_table.setItem(rowPosition, 1, QTableWidgetItem(self.sizeof_fmt(local_stat_size)))
                                    self.sf_table.setItem(rowPosition, 2, QTableWidgetItem(local_stat_date))
                                    if not pdata_dir_file[0].startswith('stat: cannot stat') and pdata_dir_file[0]:
                                        # Скрипт проверки на уникальность файла + сравнение размера
                                        self.sf_table.setItem(rowPosition, 3, dubl_img_item)
                                        local_stat_size = int(os.stat(f'{self.local_path}/{dir}/{file}').st_size) # Размер файла на локальном ПК
                                        serv_stat_size = int(pdata_dir_file[0].split('¤')[0]) # Размер файла на сервере
                                        if local_stat_size != serv_stat_size:
                                            self.sf_table.item(rowPosition, 1).setBackground(QColor(251, 241, 102))
                                            self.sf_table.item(rowPosition, 1).setToolTip(f'Server Size: {self.sizeof_fmt(serv_stat_size)} PC Size: {self.sizeof_fmt(local_stat_size)}')
                                    else:
                                        self.sf_table.setItem(rowPosition, 3, uniq_img_item)
                                    self.sf_table.setCellWidget(rowPosition, 4, file_delete_btn)
        client.close()

    def handle_button_click(self, action):
        # Обработка сигнала от клика по кнопке удаления/скачивания файла на локальном ПК
        button = self.sender()
        self.filename = self.sf_table.item(button.button_row, 0).text()
        # Окно подтверждения удаления файла бэкапа на сервере, если таковой есть
        self.messageDSF = QMessageBox()
        self.messageDSF.setIcon(QMessageBox.Icon.Question)
        self.messageDSF.setInformativeText(f'This file is also present on the server. Remove duplicate on server?')
        self.messageDSF.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        # Выбор папки в зависимости от суфикса в названии файла
        self.final_folder = ''
        if '_db_' in self.filename:
            self.final_folder = 'database'
        elif '_ws_' in self.filename:
            self.final_folder = 'site'
        else:
            self.final_folder = 'server'
        self.delete_local_file()

    def delete_local_file(self):
        # Удаляем файл на локальном ПК
        # Окно подтверждения удаления файла бэкапа на локальном ПК
        self.messageDeLF = Local_Delete_Message()
        self.messageDeLF.setIcon(QMessageBox.Icon.Question)
        self.messageDeLF.setInformativeText(f'Are you sure you want to delete the file <b>"{self.filename}"</b> on PC? This action cannot be undone!')
        self.messageDeLF.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        # Окно ожидания во время удаления файла
        self.messageDwLF = Local_Delete_Message()
        self.messageDwLF.setIcon(QMessageBox.Icon.Information)
        self.messageDwLF.setInformativeText(f'File deletion in progress.\nPlease wait...')
        self.messageDwLF.setStandardButtons(QMessageBox.StandardButton.NoButton)
        self.delete_local_act = self.messageDeLF.exec()
        if self.delete_local_act == QMessageBox.StandardButton.Yes:
            self.messageDwLF.show()
            QApplication.processEvents()
            # Поток для удаления
            self.local_delete_thread = Local_Delete_Thread(self.local_delete)
            self.local_delete_thread.finished.connect(self.messageDwLF.close)
            self.local_delete_thread.finished.connect(lambda: self.on_thread_finish())
            self.local_delete_thread.start()

    def local_delete(self):
        # Удаляем файл на локальном ПК
        os.remove(f'{self.local_path}/{self.final_folder}/{self.filename}')

    def on_thread_finish(self):
        # Ф-ия по завершению потока
        QApplication.processEvents()
        self.logger.info(f'⁙"LOCAL PC" WINDOW⁙ Deleted backup file on local PC: "{self.filename}"')
        # Если файл дублируется, предложить удалить на сервере
        self.client_del = paramiko.SSHClient()
        self.client_del.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client_del.connect(hostname=SUSLIK_Admin().json_adder()['ssh_host'],
                                username=SUSLIK_Admin().json_adder()['ssh_login'],
                                password=SUSLIK_Admin().json_adder()['ssh_password'],
                                port=int(SUSLIK_Admin().json_adder()['ssh_port']))
        stdin_dir_file, stdout_dir_file, stderr_dir_file = self.client_del.exec_command(f'cd ../{self.serv_path}/{self.final_folder}; stat --printf="%s¤%y" {self.filename}')
        data_dir_file = stdout_dir_file.read()
        pdata_dir_file = data_dir_file.decode('utf-8').strip('\n').split('\n')
        if not pdata_dir_file[0].startswith('stat: cannot stat') and pdata_dir_file[0]:
            delete_serv_act = self.messageDSF.exec()
            if delete_serv_act == QMessageBox.StandardButton.Yes:
                self.messageDwLF.show()
                QApplication.processEvents()
                # Указываем конечную папку, в зависимости от типа файла бэкапа
                stdin, stdout, stderr = self.client_del.exec_command(f'cd {self.serv_path}/{self.final_folder}; rm {self.filename}')
                exit_status = stdout.channel.recv_exit_status()
                self.logger.info(f'⁙"LOCAL PC" WINDOW"⁙ Deleted backup file on the server: "{self.filename}"')
                self.messageDwLF.close()
                QApplication.processEvents()
        self.client_del.close()
        self.refresh_all_values()

    def refresh_all_values(self):
        # Обновление таблицы и возврат к заданной сортировке
        self.sf_table.clear()
        self.sf_table.setRowCount(0)
        self.get_all_values()

    def log_conf(self):
        # Создаём лог-файл
        try:
            os.stat(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/")
        except Exception:
            os.makedirs(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/")
        open(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/!log.log", 'a+').close()

        handlers = self.logger.handlers[:]
        for handler in handlers:
            self.logger.removeHandler(handler)
            handler.close()

        # Конфигурация логирования
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%d.%m.%Y %H:%M:%S')
        fh = logging.FileHandler(f"{SUSLIK_Admin().json_adder()['path_to_local_backups']}/logs/!log.log", mode='a', encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def closeEvent(self, event):
        # Сценарий закрытия окна
        # Удаляем хендлеры логирования
        handlers = self.logger.handlers[:]
        for handler in handlers:
            self.logger.removeHandler(handler)
            handler.close()

        logging.shutdown()  # Выключаем логирование
        event.accept()

class Local_Delete_Message(QMessageBox):
    # Класс окна сообщений об удалении файла
    def __init__(self, parent=None):
        super(Local_Delete_Message, self).__init__(parent)

    def closeEvent(self, event):
        # Сценарий закрытия окна
        if Local_finder().local_delete_thread.isRunning():
            event.ignore()
        else:
            event.accept()

class Local_Delete_Thread(QThread):
    # Поток для работы удаления файла с сервера
    def __init__(self, func):
        super(Local_Delete_Thread, self).__init__()
        self.func = func

    def run(self):
        self.func()

class SUSLIK_Admin(QMainWindow, metaclass=Singleton):
    # Класс интерфейса главного окна СУРКА
    def __init__(self):
        super().__init__()

        # Инициализация окна выбора бэкапов как изначально закрытого
        self.b_sel = Choose_backup()
        self.b_sel.close()

        # Настройки главного окна
        self.setWindowTitle('IHostBackup')
        self.setFixedSize(QSize(770, 576))

        # Список изменений для текущего сеанса
        self.message_list = []
        # Старое изменяемое значение
        self.old_json_value = None
        # Новое изменяемое значение
        self.new_json_value = None

        # Хеадер
        self.headerWidget = QTableWidget(self)
        self.headerWidget.setGeometry(QRect(0, 0, 770, 50))
        self.headerWidget.setStyleSheet("background-color: rgb(15, 87, 116);")

        # Логотип
        self.label_logo = QLabel(self)
        self.pixmap_logo = QPixmap(resource_path("assets/Logo.png")).scaled(133, 38, Qt.AspectRatioMode.KeepAspectRatio,
                                                        Qt.TransformationMode.SmoothTransformation)
        self.label_logo.setGeometry(QRect(10, 6, 133, 38))
        self.label_logo.setText("")
        self.label_logo.setPixmap(self.pixmap_logo)
        self.label_logo.setToolTip(f'"Automated backup system for hosting resources, with reporting v.1.1.0 - © {date.today().year} IvNoch"')

        # Кнопка диагностики
        self.label_trblshtng = QPushButton(self)
        self.label_trblshtng.setGeometry(QRect(605, 10, 100, 30))
        self.label_trblshtng.setIconSize(QSize(30, 30))
        self.label_trblshtng.setText("Diagnosis")
        self.label_trblshtng.setObjectName('trblshtng')
        self.label_trblshtng.clicked.connect(self.open_diagnostics)

        # Кнопка уведомлений
        self.label_alerts = QPushButton(self)
        self.label_alerts.setGeometry(QRect(715, 10, 40, 30))
        if self.json_adder()['mail_alerts']:
            self.label_alerts.setIcon(QIcon(resource_path('assets/alert-on.png')))
        else:
            self.label_alerts.setIcon(QIcon(resource_path('assets/alert-off.png')))
        self.label_alerts.setIconSize(QSize(30, 30))
        self.label_alerts.setObjectName('log_btn')
        self.label_alerts.clicked.connect(self.set_alerts)

        # Макет и наполнение таблицы внутри журнала изменений
        self.layout_log = QGridLayout()
        self.layout_log.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        self.layout_log.setColumnMinimumWidth(0, 70)
        self.layout_log.setColumnMinimumWidth(1, 546)

        # Груп-бокс журнала изменений
        self.change_log = QGroupBox(self)
        self.change_log.setTitle("Change log")
        self.change_log.setLayout(self.layout_log)

        # Кнопка ручного бэкапа
        self.manual_strt_btn = QPushButton(self)
        self.manual_strt_btn.setText('Make a backup now')
        self.manual_strt_btn.clicked.connect(self.open_bckp_selection)

        # Дата последнего запуска
        self.last_launch = QLabel(self)
        self.last_launch.setText(f'Lastest app run: {self.json_adder()["latest_run"]}<span style="color:Grey;">⠀-</span>')
        self.last_launch.setToolTip("Lastest app run: both manual and CRON")
        self.last_launch.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.last_launch.setCursor(QCursor(Qt.CursorShape.IBeamCursor))

        # Данные работы последнего запуска
        self.latest_backups_info = QPushButton(self)
        self.latest_backups_info.setIcon(QIcon(resource_path('assets/i-info.png')))
        self.latest_backups_info.setIconSize(QSize(18, 18))
        self.latest_backups_info.setFixedWidth(28)
        self.latest_backups_info.setFixedHeight(44)
        self.latest_backups_info.setObjectName('log_btn')
        self.latest_backups_info.clicked.connect(self.open_latest_backups_info)

        # Кнопка разворачивания поля последнего лога
        self.last_log_btn = QPushButton(self)
        self.last_log_btn.setIcon(QIcon(resource_path('assets/arrow-d.png')))
        self.last_log_btn.setObjectName('log_btn')
        self.last_log_btn.setFixedWidth(40)
        self.last_log_btn.setFixedHeight(40)
        self.last_log_btn.clicked.connect(lambda: self.set_last_log_visible())

        # Поле с текстом последнего бэкапа
        self.last_log_textbox = QTextEdit(self)
        self.last_log_textbox.setReadOnly(True)
        self.last_log_textbox.setFixedHeight(0)
        self.last_log_textbox.setFixedWidth(740)

        # Макет и наполнение таблицы снаружи журнала изменений
        self.bottom_grid = QGridLayout()
        self.bottom_grid.setContentsMargins(10, 0, 10, 0)
        self.bottom_grid.addWidget(self.change_log, 0, 0, 1, 3)
        self.bottom_grid.addWidget(self.last_launch, 1, 0)
        self.bottom_grid.addWidget(self.last_log_btn, 1, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.bottom_grid.addWidget(self.latest_backups_info, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.bottom_grid.addWidget(self.manual_strt_btn, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
        self.bottom_grid.addWidget(self.last_log_textbox, 2, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.bottom_grid.setRowMinimumHeight(1, 40)
        self.bottom_grid.setGeometry(QRect(5, 290, 760, 255))

        # Онлайн-время
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.showtime)
        self.timer.setInterval(1000)
        self.timer.start()

        # Лейбл часов
        self.label_datetime = QLabel(self)
        self.label_datetime.setFont(QFont("consolas", 10))

        # Cтатусбар
        self.setStatusBar(QStatusBar(self))

        # Изменение статуса CRON'a
        self.chng_cron = QLabel(self)
        self.chng_cron.setFont(QFont("consolas", 10))
        self.statusBar().addWidget(self.chng_cron)

        if self.json_adder()['cron']:
            self.chng_cron.setText('¦ CRON: on')
        else:
            self.chng_cron.setText('¦ CRON: off')
        self.statusBar().setFont(QFont("consolas", 10))
        self.statusBar().addPermanentWidget(self.showip())
        self.statusBar().addPermanentWidget(self.label_datetime)
        self.tab_widget()
        self.show()

    def set_last_log_visible(self):
        # Функция разворачивания окна с текстом последнего бэкапа
        if self.last_log_textbox.height() == 0:
            self.last_log_textbox.clear()
            self.last_log_btn.setIcon(QIcon(resource_path('assets/arrow-u.png')))

            # Текст лога из файла
            last_log_file = open(SUSLIK_Admin().json_adder()['path_to_local_backups'] + "/logs/" + SUSLIK_Admin().json_adder()['latest_run'] + ".log", 'r')
            last_log_text = last_log_file.readlines()
            last_log_file.close()

            # Формат для окрашивания разного рода ошибок
            black = '<span style="color:Black;">'
            yellow = '<span style="color:Orange;">'
            red = '<span style="color:OrangeRed;">'
            bold_red = '<span style="color:Crimson;">'
            reset = '</span>'

            for line in last_log_text:
                if "DEBUG" in line:
                    self.last_log_textbox.append(f'{black}{line}{reset}')
                elif "INFO" in line:
                    self.last_log_textbox.append(f'{black}{line}{reset}')
                elif "WARNING" in line:
                    self.last_log_textbox.append(f'{yellow}{line}{reset}')
                elif "ERROR" in line:
                    self.last_log_textbox.append(f'{red}{line}{reset}')
                elif "CRITICAL" in line:
                    self.last_log_textbox.append(f'{bold_red}{line}{reset}')
                else:
                    self.last_log_textbox.append(line)

            self.setFixedSize(QSize(770, 776))
            self.last_log_textbox.setFixedHeight(200)
        else:
            self.last_log_btn.setIcon(QIcon(resource_path('assets/arrow-d.png')))
            self.last_log_textbox.setFixedHeight(0)
            self.setFixedSize(QSize(770, 576))


    def open_bckp_selection(self):
        # Отображение окна выбора бэкапа
        self.b_sel.show()

    def open_latest_backups_info(self):
        # Отображение окна информации и последнем бэкапе
        Last_backup_info().show()
        QApplication.processEvents()
        Last_backup_info().add_last_backups_data()

    def set_alerts(self):
        # Установка или снятие уведослений по почте
        if self.json_adder()['mail_alerts']:
            self.label_alerts.setIcon(QIcon(resource_path('assets/alert-off.png')))
            self.json_quiet_adder('mail_alerts', False)
        else:
            self.label_alerts.setIcon(QIcon(resource_path('assets/alert-on.png')))
            self.json_quiet_adder('mail_alerts', True)

    def open_serv_finder(self):
        # Отображение окна управления файлами бэкапов на сервере
        Server_finder().show()

    def open_local_finder(self):
        # Отображение окна управления файлами бэкапов на локальном ПК
        Local_finder().show()

    @staticmethod
    def open_diagnostics():
        # Отображение окна диагностики
        Diagnostics().show()
        QApplication.processEvents()
        Diagnostics().nw_con()
        QApplication.processEvents()
        Diagnostics().sh_con()
        QApplication.processEvents()
        Diagnostics().fp_con()
        QApplication.processEvents()
        Diagnostics().db_con()
        QApplication.processEvents()
        Diagnostics().ml_con()
        QApplication.processEvents()

    def showtime(self):
        # Онлайн-часы
        try:
            self.datetime = QDateTime.currentDateTime()
            self.text = self.datetime.toString()
            self.label_datetime.setText("   " + self.text)
        except KeyboardInterrupt:
            pass

    def showip(self):
        # Определение публичного ip-адреса
        self.ip_data = QLabel()
        self.ip_data.setFont(QFont("consolas", 10))
        try:
            # !!! В случае прекращения работы API, изменить ссылку !!!
            self.ip_data.setText("Your IP: " + get('https://api.ipify.org').content.decode('utf8'))
        except Exception:
            self.ip_data.setText("ERROR IP API CON.")
        return self.ip_data

    def open_file(self, path_dir):
        # Открытие папки в терминале, учитывая ОС
        if platform.system() == "Windows":
            os.startfile(path_dir)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path_dir])
        else:
            subprocess.Popen(["xdg-open", path_dir])

    @staticmethod
    def json_quiet_adder(element, value):
        # "Тихая" версия функции ниже, изменяет JSON-файл настроек, без вмешательства в историю изменений
        json_file = open(resource_path("settings.json"), "r+", encoding='utf8')
        db_data = json.load(json_file)
        db_data[element] = value
        json_file.seek(0)
        json.dump(db_data, json_file, ensure_ascii=False, indent=4)
        json_file.truncate()
        json_file.close()

    def json_adder(self, element=None, value=None, multi=False):
        # Многоцелевая ф-ия, которая читает json-файл настроек, добавляет в него значения, возвращает его, и т.п.
        json_file = open(resource_path("settings.json"), "r+", encoding='utf8')
        db_data = json.load(json_file)
        if element and value and not multi:
            db_data["asked_value"] = value
            if value != db_data[element]:
                self.old_json_value = db_data[element]
                db_data[element] = value
                json_file.seek(0)
                json.dump(db_data, json_file, ensure_ascii=False, indent=4)
                json_file.truncate()
                self.new_json_value = value
                self.message_list.append(dict(old=self.old_json_value, new=self.new_json_value, el=element))
                json_file.close()
            else:
                db_data["asked_value"] = "STOP_ROLLBACK"
                json_file.seek(0)
                json.dump(db_data, json_file, ensure_ascii=False, indent=4)
                json_file.truncate()
                self.new_json_value = value
                json_file.close()
        elif element and value and multi:
            if not all(item in db_data[element] for item in value.replace(' ', '').split(",")):
                db_data["asked_value"] = value
                self.old_json_value = db_data[element].copy()
                list_value = value.replace(' ', '').split(",")
                db_data[element].extend(list_value)
                db_data[element] = list(dict.fromkeys(db_data[element]))
                json_file.seek(0)
                json.dump(db_data, json_file, ensure_ascii=False, indent=4)
                json_file.truncate()
                self.new_json_value = db_data[element]
                self.message_list.append(dict(old=self.old_json_value, new=self.new_json_value, el=element))
                json_file.close()
            else:
                db_data["asked_value"] = "STOP_ROLLBACK"
                json_file.seek(0)
                json.dump(db_data, json_file, ensure_ascii=False, indent=4)
                json_file.truncate()
                self.new_json_value = value
                json_file.close()
        else:
            json_file.close()
        return db_data

    def json_remover(self, element, value, multi=False):
        # Удаление значений в json-файле настроек
        json_file = open(resource_path("settings.json"), "r+", encoding='utf8')
        db_data = json.load(json_file)
        self.old_json_value = db_data[element].copy()
        if value != self.json_adder()[element]:
            if not multi:
                try:
                    db_data["asked_value"] = value
                    db_data[element].remove(value)
                except ValueError:
                    pass
            else:
                db_data["asked_value"] = value
                db_data[element] = value
            json_file.seek(0)
            json.dump(db_data, json_file, ensure_ascii=False, indent=4)
            json_file.truncate()
            self.new_json_value = db_data[element]
            self.message_list.append(dict(old=self.old_json_value, new=self.new_json_value, el=element))
            json_file.close()
        else:
            db_data["asked_value"] = "STOP_ROLLBACK"
            json_file.seek(0)
            json.dump(db_data, json_file, ensure_ascii=False, indent=4)
            json_file.truncate()
            self.new_json_value = db_data[element]
            json_file.close()

    def ws_getter(self):
        # Создаём соединение с cервером по SSH
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=self.json_adder()['ssh_host'], username=self.json_adder()['ssh_login'], password=self.json_adder()['ssh_password'], port=int(self.json_adder()['ssh_port']))

        # Создаём список сайтов (директорий сайтов)
        stdin, stdout, stderr = client.exec_command('cd ../www/wwwroot; ls')
        data = stdout.read()
        client.close()
        ws_res = [ws for ws in data.decode('utf-8').strip('\n').split('\n') if '.' in ws]
        return ws_res

    def db_getter(self):
        # Создаём соединение с cервером по SSH
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=self.json_adder()['ssh_host'], username=self.json_adder()['ssh_login'], password=self.json_adder()['ssh_password'], port=int(self.json_adder()['ssh_port']))

        # Создаём список БД
        stdin, stdout, stderr = client.exec_command('ls')
        data = stdout.read()
        client.close()
        fdata = data.decode('utf-8').strip('\n').split('\n')
        rdata = [db for db in fdata if '.sql' in db]
        return rdata

    def pem_dialog(self, element):
        # Выбор pem-файла ssl-сертификата
        file, check = QFileDialog.getOpenFileName(None, "QFileDialog.getOpenFileName()",
                                                  "", "PEM Files (*.pem)")
        if check:
            self.json_adder(element=element, value=file)
            self.roll_back_msg(felement=element)

    def folder_dialog(self, element):
        # Выбор папки сохранения бэкапов
        folder = QFileDialog.getExistingDirectory(self, 'Select Folder')
        if folder:
            self.json_adder(element=element, value=folder)
            self.roll_back_msg(felement=element)

    def ftp_folder_open(self, element):
        # Выбор папки сохранения бэкапов
        url = QUrl(f"ftp://{self.json_adder()['ftp_login']}:{self.json_adder()['ftp_password']}@{self.json_adder()['ftp_host']}:{self.json_adder()['ftp_port']}", QUrl.ParsingMode.TolerantMode)
        url.setScheme("ftp")
        QDesktopServices.openUrl(url)

    def update_db_list_new(self, db_list):
        # Обновление списка названий бд для бэкапа в интерфейсе
        db_list.clear()
        for num, db in enumerate(self.db_getter()):
            db_list.addItem("")
            db_list.setItemText(num, db)
        return db_list

    def update_ws_list_new(self, ws_list):
        # Обновление списка названий сайтов для бэкапа в интерфейсе
        ws_list.clear()
        for num, db in enumerate(self.ws_getter()):
            ws_list.addItem("")
            ws_list.setItemText(num, db)
        return ws_list

    def update_edit_line(self):
        # Обновление значений всех текстовых строк в интерфейсе
        # 1-ый таб
        self.serv_bckp_path_edit.setText(self.json_adder()["path_to_server_backups"])
        self.server_limit_save_edit.setValue(int(self.json_adder()["backup_server_age"]))
        # 2-ой таб
        self.local_bckp_path_label.setText(self.json_adder()["path_to_local_backups"])
        self.local_limit_save_edit.setValue(int(self.json_adder()["backup_local_age"]))
        # 3-тий таб
        self.ssh_host_edit.setText(self.json_adder()["ssh_host"])
        self.ssh_login_edit.setText(self.json_adder()["ssh_login"])
        self.ssh_pass_edit.setText(self.json_adder()["ssh_password"])
        self.ssh_port_edit.setText(self.json_adder()["ssh_port"])
        # 4-ый таб
        self.ftp_host_edit.setText(self.json_adder()["ftp_host"])
        self.ftp_login_edit.setText(self.json_adder()["ftp_login"])
        self.ftp_pass_edit.setText(self.json_adder()["ftp_password"])
        self.ftp_port_edit.setText(self.json_adder()["ftp_port"])
        # 5-тый таб
        self.db_name_edit.setText(self.json_adder()["db_name"])
        self.db_host_edit.setText(self.json_adder()["host"])
        self.db_login_edit.setText(self.json_adder()["login"])
        self.db_pass_edit.setText(self.json_adder()["password"])
        self.ckc_path_label.setText(self.json_adder()["path_to_ckc"])
        self.scc_path_label.setText(self.json_adder()["path_to_scc"])
        self.ccc_path_label.setText(self.json_adder()["path_to_ccc"])
        # 6-той таб
        self.mail_email_edit.setText(self.json_adder()["mail_email"])
        self.mail_id_edit.setText(self.json_adder()["mail_user_id"])
        self.mail_secret_edit.setText(self.json_adder()["mail_user_secret"])
        self.rprts_email_edit.setText(self.json_adder()["report_email"])
        # 7-ой таб
        self.cron_hours_combo.setCurrentText(self.json_adder()["cron_hour"])
        self.cron_minutes_combo.setCurrentText(self.json_adder()["cron_minute"])
        self.cron_date_combo.setCurrentText(self.json_adder()['cron_mode'])
        self.cron_day_combo.setCurrentText(self.json_adder()['cron_dow'])
        # Низ страницы
        self.last_launch.setText(f"Lastest app run: {self.json_adder()['latest_run']}")

    def roll_back_msg(self, rollback=False, roll_new="", felement="", multi=False, delete=False, not_the_last_change_for_one_button=False):
        # Многоцелевая ф-ия, которая обеспечивает корректную отмену (откат, возврат) значения по нажатию кнопки в интерфейсе
        if str(self.json_adder()["asked_value"]) != "STOP_ROLLBACK" and self.old_json_value != None and self.new_json_value != None:
            time_msg = QTime.currentTime().toString()
            fvalue = self.json_adder()
            fold = fvalue[felement]
            if not rollback and not multi:
                data_msg = f'Value {"·" * len(self.old_json_value) if "password" in felement or "secret" in felement else self.old_json_value} changed to {"·" * len(self.new_json_value) if "password" in felement or "secret" in felement else self.new_json_value}'
            elif rollback and not multi:
                data_msg = f'Value {"·" * len(self.old_json_value) if "password" in felement or "secret" in felement else self.old_json_value} rolled back to {"·" * len(roll_new) if "password" in felement or "secret" in felement else roll_new}'
                if 'cron' in felement:
                    self.tmblr_cron.setChecked(False)
            elif not rollback and multi:
                fadded = [item for item in self.json_adder()["asked_value"].replace(' ', '').split(",") if
                          item not in self.old_json_value]
                data_msg = f'To value "{self.old_json_value}" added "{fadded}"'
            else:
                if not delete:
                    data_msg = f'Value {self.old_json_value} rolled back to {roll_new}'
                else:
                    data_msg = f'From value {self.old_json_value} deleted "{self.json_adder()["asked_value"]}"'
            if not multi:
                if str(self.json_adder()["asked_value"]) == str(fold):
                    if self.layout_log.rowCount() > 5:
                        to_delete1 = self.layout_log.itemAtPosition(self.layout_log.rowCount() - 5, 0).widget()
                        to_delete2 = self.layout_log.itemAtPosition(self.layout_log.rowCount() - 5, 1).widget()
                        to_delete3 = self.layout_log.itemAtPosition(self.layout_log.rowCount() - 5, 2).widget()
                        to_delete1.deleteLater()
                        to_delete2.deleteLater()
                        to_delete3.deleteLater()
                    else:
                        pass
                    self.layout_log.addWidget(QLabel(time_msg), self.layout_log.rowCount(), 0,
                                              alignment=Qt.AlignmentFlag.AlignLeft)
                    self.layout_log.addWidget(QLabel(data_msg), self.layout_log.rowCount() - 1, 1,
                                              alignment=Qt.AlignmentFlag.AlignLeft)
                    undo_button = QPushButton(f"Undo {self.layout_log.rowCount() - 1}")
                    undo_button.setFixedSize(90, 35)
                    undo_button.setObjectName("undo_btn")
                    undo_button.clicked.connect(lambda: self.json_adder(
                        element=self.message_list[int(undo_button.text().split(' ')[1]) - 1]["el"],
                        value=self.message_list[int(undo_button.text().split(' ')[1]) - 1]["old"]))
                    undo_button.clicked.connect(lambda: self.roll_back_msg(rollback=True, roll_new=
                    self.message_list[int(undo_button.text().split(' ')[1]) - 1]["old"], felement=self.message_list[
                        int(undo_button.text().split(' ')[1]) - 1]["el"]))
                    # undo_button.clicked.connect(lambda: self.update_db_list(self.all_db_combo))
                    self.layout_log.addWidget(undo_button, self.layout_log.rowCount() - 1, 2,
                                              alignment=Qt.AlignmentFlag.AlignRight)
                if not not_the_last_change_for_one_button:
                    self.update_edit_line()
                else:
                    pass
            else:
                if self.layout_log.rowCount() > 5:
                    to_delete1 = self.layout_log.itemAtPosition(self.layout_log.rowCount() - 5, 0).widget()
                    to_delete2 = self.layout_log.itemAtPosition(self.layout_log.rowCount() - 5, 1).widget()
                    to_delete3 = self.layout_log.itemAtPosition(self.layout_log.rowCount() - 5, 2).widget()
                    to_delete1.deleteLater()
                    to_delete2.deleteLater()
                    to_delete3.deleteLater()
                else:
                    pass
                if not all(item in fold for item in self.json_adder()["asked_value"]) or str(
                        self.message_list[-1]["old"] == []):
                    self.layout_log.addWidget(QLabel(time_msg), self.layout_log.rowCount(), 0,
                                              alignment=Qt.AlignmentFlag.AlignLeft)
                    self.layout_log.addWidget(QLabel(data_msg), self.layout_log.rowCount() - 1, 1,
                                              alignment=Qt.AlignmentFlag.AlignLeft)
                    undo_button = QPushButton(f"Undo {self.layout_log.rowCount() - 1}")
                    undo_button.setFixedSize(90, 35)
                    undo_button.setObjectName("undo_btn")
                    undo_button.clicked.connect(lambda: self.json_remover(
                        element=self.message_list[int(undo_button.text().split(' ')[1]) - 1]["el"],
                        value=self.message_list[int(undo_button.text().split(' ')[1]) - 1]["old"], multi=True))
                    undo_button.clicked.connect(lambda: self.roll_back_msg(rollback=True, roll_new=
                    self.message_list[int(undo_button.text().split(' ')[1]) - 1]["old"], felement=self.message_list[
                        int(undo_button.text().split(' ')[1]) - 1]["el"], multi=True))
                    # undo_button.clicked.connect(lambda: self.update_db_list(self.all_db_combo))
                    self.layout_log.addWidget(undo_button, self.layout_log.rowCount() - 1, 2,
                                              alignment=Qt.AlignmentFlag.AlignRight)
                if not not_the_last_change_for_one_button:
                    self.update_edit_line()
                else:
                    pass
        else:
            pass

    def tab_widget(self):
        # Создание табов вверху окна

        # Создаём табы
        self.group1 = QWidget()
        self.group2 = QWidget()
        self.group3 = QWidget()
        self.group4 = QWidget()
        self.group5 = QWidget()
        self.group6 = QWidget()
        self.group7 = QWidget()
        self.group7.setDisabled(True)

        # Виджет таба
        self.tab_wdgt = QTabWidget(self)
        self.tab_wdgt.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Ignored)
        self.tab_wdgt.move(15, 55)
        self.tab_wdgt.setFixedSize(QSize(740, 225))

        ### --- CЕРВЕР ПЕРВЫЙ ТАБ --- ###

        # Выпадающий список названий бд
        self.all_db_combo = QComboBox(self)
        self.all_db_combo.setFixedHeight(22)
        self.update_db_list_new(self.all_db_combo)

        # Выпадающий список названий сайтов
        self.all_ws_combo = QComboBox(self)
        self.all_ws_combo.setFixedHeight(22)
        self.update_ws_list_new(self.all_ws_combo)

        # Строка ввода пути сохранения бэкапов на сервере
        self.serv_bckp_path_edit = QLineEdit(self)
        self.serv_bckp_path_edit.setText(self.json_adder()["path_to_server_backups"])
        self.serv_bckp_path_edit.setFixedWidth(280)

        # Кнопка изменения пути сохранения бэкапов на сервере
        self.serv_bckp_path_btn = QPushButton('Change')
        self.serv_bckp_path_btn.setObjectName("path_to_server_backups")
        self.serv_bckp_path_btn.clicked.connect(lambda: self.json_adder(element=self.serv_bckp_path_btn.objectName(), value=str(self.serv_bckp_path_edit.text())))
        self.serv_bckp_path_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.serv_bckp_path_btn.objectName()))
        self.serv_bckp_path_btn.setFixedWidth(92)

        # Кнопка обновления названия(-ий) бд
        self.db_ref_btn = QPushButton('Update')
        self.db_ref_btn.clicked.connect(lambda: self.update_db_list_new(self.all_db_combo))
        self.db_ref_btn.setFixedWidth(92)

        # Кнопка обновления названия(-ий) сайтов
        self.ws_ref_btn = QPushButton('Update')
        self.ws_ref_btn.clicked.connect(lambda: self.update_ws_list_new(self.all_ws_combo))
        self.ws_ref_btn.setFixedWidth(92)

        # Кнопка выбора папки для сохранения бэкапов на сервере
        self.serv_bckp_open_btn = QPushButton('Check')
        self.serv_bckp_open_btn.setObjectName("path_to_server_backups")
        self.serv_bckp_open_btn.clicked.connect(lambda: self.ftp_folder_open(element=self.serv_bckp_open_btn.objectName()))
        self.serv_bckp_open_btn.clicked.connect(lambda: self.json_adder(element=self.serv_bckp_open_btn.objectName(), value=self.serv_bckp_path_edit.text()))
        self.serv_bckp_open_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.serv_bckp_open_btn.objectName()))
        self.serv_bckp_open_btn.setFixedWidth(74)

        # Кнопка открытия окна управления файлами бэкапов на сервере
        self.serv_finder_btn = QPushButton('Server backups management')
        self.serv_finder_btn.clicked.connect(lambda: self.open_serv_finder())
        self.serv_finder_btn.setFixedWidth(250)

        # Строка ввода ограничения по автоудалению старых бэкапов на сервере (дн.)
        self.server_limit_save_edit = QSpinBox(self)
        self.server_limit_save_edit.setRange(0, 9999)
        self.server_limit_save_edit.setValue(int(self.json_adder()["backup_server_age"]))
        self.server_limit_save_edit.setToolTip('Backup files older than this value will be automatically deleted.')

        # Кнопка изменения ограничения по автоудалению старых бэкапов на сервере (дн.)
        self.server_limit_save_btn = QPushButton('Change')
        self.server_limit_save_btn.setObjectName("backup_server_age")
        self.server_limit_save_btn.clicked.connect(lambda: self.json_adder(element=self.server_limit_save_btn.objectName(), value=str(self.server_limit_save_edit.text())))
        self.server_limit_save_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.server_limit_save_btn.objectName()))
        self.server_limit_save_btn.setFixedWidth(92)

        ### --- ЛОКАЛ. ВТОРОЙ ТАБ --- ###

        # Строка ввода ограничения по автоудалению старых бэкапов на локальном ПК (дн.)
        self.local_limit_save_edit = QSpinBox(self)
        self.local_limit_save_edit.setRange(0, 9999)
        self.local_limit_save_edit.setValue(int(self.json_adder()["backup_local_age"]))
        self.local_limit_save_edit.setToolTip('Backup files older than this value will be automatically deleted.')

        # Кнопка изменения ограничения по автоудалению старых бэкапов на локальном ПК (дн.)
        self.local_limit_save_btn = QPushButton('Change')
        self.local_limit_save_btn.setObjectName("backup_local_age")
        self.local_limit_save_btn.clicked.connect(lambda: self.json_adder(element=self.local_limit_save_btn.objectName(), value=str(self.local_limit_save_edit.text())))
        self.local_limit_save_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.local_limit_save_btn.objectName()))
        self.local_limit_save_btn.setFixedWidth(92)

        # Лейбл пути сохранения локальных бэкапов
        self.local_bckp_path_label = QLabel(self)
        self.local_bckp_path_label.setText(self.json_adder()["path_to_local_backups"])

        # Меню выбора открытия папки с бэкапами или логами
        self.local_open_menu = QMenu(self)
        self.local_open_menu.addAction("Backups", lambda: self.open_file(self.local_bckp_path_label.text()))
        self.local_open_menu.addAction("Logs", lambda: self.open_file(f'{self.local_bckp_path_label.text()}/logs'))
        self.local_open_menu.addAction("Log+", lambda: self.open_file(f'{self.local_bckp_path_label.text()}/logs/!log.log'))

        # Кнопка открытия локальной папки с сохранёнными бэкапами или логами
        self.local_bckp_open_btn = QPushButton('Open')
        self.local_bckp_open_btn.setObjectName("open_bckp")
        self.local_bckp_open_btn.setMenu(self.local_open_menu)
        self.local_bckp_open_btn.setFixedWidth(74)

        # Кнопка выбора папки для сохранения бэкапов на сервере
        self.local_bckp_path_btn = QPushButton('Choose')
        self.local_bckp_path_btn.setObjectName("path_to_local_backups")
        self.local_bckp_path_btn.clicked.connect(lambda: self.folder_dialog(element=self.local_bckp_path_btn.objectName()))
        self.local_bckp_path_btn.clicked.connect(lambda: self.json_adder(element=self.local_bckp_path_btn.objectName(), value=self.local_bckp_path_label.text()))
        self.local_bckp_path_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.local_bckp_path_btn.objectName()))
        self.local_bckp_path_btn.setFixedWidth(92)

        # Кнопка открытия окна управления локальными файлами бэкапов
        self.local_finder_btn = QPushButton('Local PC backups management')
        self.local_finder_btn.clicked.connect(lambda: self.open_local_finder())
        self.local_finder_btn.setFixedWidth(270)

        ### --- SSH ТРЕТИЙ ТАБ --- ###

        # Строка ввода хоста SSH
        self.ssh_host_edit = QLineEdit(self)
        self.ssh_host_edit.setText(self.json_adder()["ssh_host"])

        # Строка ввода логина SSH
        self.ssh_login_edit = QLineEdit(self)
        self.ssh_login_edit.setText(self.json_adder()["ssh_login"])

        # Строка ввода секрета SSH
        self.ssh_pass_edit = QLineEdit(self)
        self.ssh_pass_edit.setText(self.json_adder()["ssh_password"])
        self.ssh_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # Строка ввода порта SSH
        self.ssh_port_edit = QLineEdit(self)
        self.ssh_port_edit.setText(self.json_adder()["ssh_port"])

        # Кнопка изменения хоста SSH
        self.ssh_host_btn = QPushButton('Change')
        self.ssh_host_btn.setObjectName("ssh_host")
        self.ssh_host_btn.clicked.connect(lambda: self.json_adder(element=self.ssh_host_btn.objectName(), value=self.ssh_host_edit.text()))
        self.ssh_host_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ssh_host_btn.objectName()))
        self.ssh_host_btn.setFixedWidth(92)

        # Кнопка изменения логина SSH
        self.ssh_login_btn = QPushButton('Change')
        self.ssh_login_btn.setObjectName("ssh_login")
        self.ssh_login_btn.clicked.connect(lambda: self.json_adder(element=self.ssh_login_btn.objectName(), value=self.ssh_login_edit.text()))
        self.ssh_login_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ssh_login_btn.objectName()))
        self.ssh_login_btn.setFixedWidth(92)

        # Кнопка изменения секрета SSH
        self.ssh_pass_btn = QPushButton('Change')
        self.ssh_pass_btn.setObjectName("ssh_password")
        self.ssh_pass_btn.clicked.connect(lambda: self.json_adder(element=self.ssh_pass_btn.objectName(), value=self.ssh_pass_edit.text()))
        self.ssh_pass_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ssh_pass_btn.objectName()))
        self.ssh_pass_btn.setFixedWidth(92)

        # Кнопка изменения порта SSH
        self.ssh_port_btn = QPushButton('Change')
        self.ssh_port_btn.setObjectName("ssh_port")
        self.ssh_port_btn.clicked.connect(lambda: self.json_adder(element=self.ssh_port_btn.objectName(), value=self.ssh_port_edit.text()))
        self.ssh_port_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ssh_port_btn.objectName()))
        self.ssh_port_btn.setFixedWidth(92)

        ### --- FTP ЧЕТВËРТЫЙ ТАБ --- ###
        # Строка ввода адреса FTP
        self.ftp_host_edit = QLineEdit(self)
        self.ftp_host_edit.setText(self.json_adder()["ftp_host"])

        # Строка ввода логина FTP
        self.ftp_login_edit = QLineEdit(self)
        self.ftp_login_edit.setText(self.json_adder()["ftp_login"])

        # Строка ввода пароля FTP
        self.ftp_pass_edit = QLineEdit(self)
        self.ftp_pass_edit.setText(self.json_adder()["ftp_password"])
        self.ftp_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # Строка ввода порта FTP
        self.ftp_port_edit = QLineEdit(self)
        self.ftp_port_edit.setText(self.json_adder()["ftp_port"])

        # Кнопка изменения хоста SQL
        self.ftp_host_btn = QPushButton('Change')
        self.ftp_host_btn.setObjectName("ftp_host")
        self.ftp_host_btn.clicked.connect(lambda: self.json_adder(element=self.ftp_host_btn.objectName(), value=self.ftp_host_edit.text()))
        self.ftp_host_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ftp_host_btn.objectName()))
        self.ftp_host_btn.setFixedWidth(92)

        # Кнопка изменения логина SQL
        self.ftp_login_btn = QPushButton('Change')
        self.ftp_login_btn.setObjectName("ftp_login")
        self.ftp_login_btn.clicked.connect(lambda: self.json_adder(element=self.ftp_login_btn.objectName(), value=self.ftp_login_edit.text()))
        self.ftp_login_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ftp_login_btn.objectName()))
        self.ftp_login_btn.setFixedWidth(92)

        # Кнопка изменения пароля SQL
        self.ftp_pass_btn = QPushButton('Change')
        self.ftp_pass_btn.setObjectName("ftp_password")
        self.ftp_pass_btn.clicked.connect(lambda: self.json_adder(element=self.ftp_pass_btn.objectName(), value=self.ftp_pass_edit.text()))
        self.ftp_pass_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ftp_pass_btn.objectName()))
        self.ftp_pass_btn.setFixedWidth(92)

        # Кнопка изменения порта SQL
        self.ftp_port_btn = QPushButton('Change')
        self.ftp_port_btn.setObjectName("ftp_port")
        self.ftp_port_btn.clicked.connect(lambda: self.json_adder(element=self.ftp_port_btn.objectName(), value=self.ftp_port_edit.text()))
        self.ftp_port_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ftp_port_btn.objectName()))
        self.ftp_port_btn.setFixedWidth(92)

        ### --- MYSQL ПЯТЫЙ ТАБ --- ###

        # Строка ввода имени БД
        self.db_name_edit = QLineEdit(self)
        self.db_name_edit.setText(self.json_adder()["db_name"])

        # Строка ввода хоста SQL
        self.db_host_edit = QLineEdit(self)
        self.db_host_edit.setText(self.json_adder()["host"])

        # Строка ввода логина SQL
        self.db_login_edit = QLineEdit(self)
        self.db_login_edit.setText(self.json_adder()["login"])

        # Строка ввода пароля SQL
        self.db_pass_edit = QLineEdit(self)
        self.db_pass_edit.setText(self.json_adder()["password"])
        self.db_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # Лейбл пути файла ssl-сертификата (key)
        self.ckc_path_label = QLabel(self)
        self.ckc_path_label.setText(self.json_adder()["path_to_ckc"])

        # Лейбл пути файла ssl-сертификата (cert)
        self.ccc_path_label = QLabel(self)
        self.ccc_path_label.setText(self.json_adder()["path_to_ccc"])

        # Лейбл пути файла ssl-сертификата (serv. ca)
        self.scc_path_label = QLabel(self)
        self.scc_path_label.setText(self.json_adder()["path_to_scc"])

        # Кнопка изменения имени БД
        self.db_name_btn = QPushButton('Change')
        self.db_name_btn.setObjectName("db_name")
        self.db_name_btn.clicked.connect(lambda: self.json_adder(element=self.db_name_btn.objectName(), value=self.db_name_edit.text()))
        self.db_name_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.db_name_btn.objectName()))
        self.db_name_btn.setFixedWidth(92)

        # Кнопка изменения хоста SQL
        self.db_host_btn = QPushButton('Change')
        self.db_host_btn.setObjectName("host")
        self.db_host_btn.clicked.connect(lambda: self.json_adder(element=self.db_host_btn.objectName(), value=self.db_host_edit.text()))
        self.db_host_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.db_host_btn.objectName()))
        self.db_host_btn.setFixedWidth(92)

        # Кнопка изменения логина SQL
        self.db_login_btn = QPushButton('Change')
        self.db_login_btn.setObjectName("login")
        self.db_login_btn.clicked.connect(lambda: self.json_adder(element=self.db_login_btn.objectName(), value=self.db_login_edit.text()))
        self.db_login_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.db_login_btn.objectName()))
        self.db_login_btn.setFixedWidth(92)

        # Кнопка изменения пароля SQL
        self.db_pass_btn = QPushButton('Change')
        self.db_pass_btn.setObjectName("password")
        self.db_pass_btn.clicked.connect(lambda: self.json_adder(element=self.db_pass_btn.objectName(), value=self.db_pass_edit.text()))
        self.db_pass_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.db_pass_btn.objectName()))
        self.db_pass_btn.setFixedWidth(92)

        # Кнопка выбора pem-файла ssl-сертификата (key)
        self.ckc_path_btn = QPushButton('Choose')
        self.ckc_path_btn.setObjectName("path_to_ckc")
        self.ckc_path_btn.clicked.connect(lambda: self.pem_dialog(element=self.ckc_path_btn.objectName()))
        self.ckc_path_btn.clicked.connect(lambda: self.json_adder(element=self.ckc_path_btn.objectName(), value=self.ckc_path_label.text()))
        self.ckc_path_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ckc_path_btn.objectName()))
        self.ckc_path_btn.setFixedWidth(92)

        # Кнопка выбора pem-файла ssl-сертификата (cert)
        self.ccc_path_btn = QPushButton('Choose')
        self.ccc_path_btn.setObjectName("path_to_ccc")
        self.ccc_path_btn.clicked.connect(lambda: self.pem_dialog(element=self.ccc_path_btn.objectName()))
        self.ccc_path_btn.clicked.connect(lambda: self.json_adder(element=self.ccc_path_btn.objectName(), value=self.ccc_path_label.text()))
        self.ccc_path_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.ccc_path_btn.objectName()))
        self.ccc_path_btn.setFixedWidth(92)

        # Кнопка выбора pem-файла ssl-сертификата (serv. ca)
        self.scc_path_btn = QPushButton('Choose')
        self.scc_path_btn.setObjectName("path_to_scc")
        self.scc_path_btn.clicked.connect(lambda: self.pem_dialog(element=self.scc_path_btn.objectName()))
        self.scc_path_btn.clicked.connect(lambda: self.json_adder(element=self.scc_path_btn.objectName(), value=self.scc_path_label.text()))
        self.scc_path_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.scc_path_btn.objectName()))
        self.scc_path_btn.setFixedWidth(92)

        ### --- SMTP ШЕСТОЙ ТАБ --- ###

        # Строка ввода email'a приложения
        self.mail_email_edit = QLineEdit(self)
        self.mail_email_edit.setText(self.json_adder()["mail_email"])

        # Строка ввода ID пользователя
        self.mail_id_edit = QLineEdit(self)
        self.mail_id_edit.setText(self.json_adder()["mail_user_id"])

        # Строка ввода Secret'a пользователя
        self.mail_secret_edit = QLineEdit(self)
        self.mail_secret_edit.setText(self.json_adder()["mail_user_secret"])
        self.mail_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)

        # Строка ввода email-адреса для получения лог-отчётов
        self.rprts_email_edit = QLineEdit(self)
        self.rprts_email_edit.setText(self.json_adder()["report_email"])
        self.rprts_email_edit.setFixedWidth(246)

        # Кнопка изменения email'a приложения
        self.mail_email_btn = QPushButton('Change')
        self.mail_email_btn.setObjectName("mail_email")
        self.mail_email_btn.clicked.connect(lambda: self.json_adder(element=self.mail_email_btn.objectName(), value=self.mail_email_edit.text()))
        self.mail_email_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.mail_email_btn.objectName()))
        self.mail_email_btn.setFixedWidth(92)

        # Кнопка изменения ID приложения
        self.mail_id_btn = QPushButton('Change')
        self.mail_id_btn.setObjectName("mail_user_id")
        self.mail_id_btn.clicked.connect(lambda: self.json_adder(element=self.mail_id_btn.objectName(), value=self.mail_id_edit.text()))
        self.mail_id_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.mail_id_btn.objectName()))
        self.mail_id_btn.setFixedWidth(92)

        # Кнопка изменения Secret'a пользователя
        self.mail_secret_btn = QPushButton('Change')
        self.mail_secret_btn.setObjectName("mail_user_secret")
        self.mail_secret_btn.clicked.connect(lambda: self.json_adder(element=self.mail_secret_btn.objectName(), value=self.mail_secret_edit.text()))
        self.mail_secret_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.mail_secret_btn.objectName()))
        self.mail_secret_btn.setFixedWidth(92)

        # Сообщение об отправке тестового письма
        self.messageM = QMessageBox()
        self.messageM.setIcon(QMessageBox.Icon.Information)
        self.messageM.setInformativeText("Test email has been sent!")

        # Кнопка отправки тестового сообщения на указанный email-адрес
        self.rprts_test_btn = QPushButton('Test')
        self.rprts_test_btn.setObjectName("report_test")
        self.rprts_test_btn.clicked.connect(lambda: self.send_test_letter())
        self.rprts_test_btn.setFixedWidth(74)

        # Кнопка изменения email-адреса для отправки лог-отчётов
        self.rprts_email_btn = QPushButton('Change')
        self.rprts_email_btn.setObjectName("report_email")
        self.rprts_email_btn.clicked.connect(lambda: self.json_adder(element=self.rprts_email_btn.objectName(), value=self.rprts_email_edit.text()))
        self.rprts_email_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.rprts_email_btn.objectName()))
        self.rprts_email_btn.setFixedWidth(92)

        ### --- CRON СЕДЬМОЙ ТАБ --- ###

        # Выпадающий список CRON: день недели (опционный)
        self.cron_day_combo = QComboBox(self)
        self.cron_day_combo.setObjectName('cron_dow')
        self.cron_day_combo.addItems(["Monday", "Tuesday", "Wednwsday", "Thursday", "Friday", "Sunday", "Saturday"])
        self.cron_day_combo.setFixedWidth(130)
        self.cron_day_combo.setFixedHeight(22)
        self.cron_day_combo.setCurrentText(self.json_adder()['cron_dow'])
        if self.json_adder()['cron_mode'] == 'Weekly':
            self.cron_day_combo.setDisabled(False)
        else:
            self.cron_day_combo.setDisabled(True)

        # Выпадающий список CRON: неделя-день
        self.cron_date_combo = QComboBox(self)
        self.cron_date_combo.setObjectName('cron_mode')
        self.cron_date_combo.addItems(["Daily", "Weekly"])
        self.cron_date_combo.setFixedWidth(130)
        self.cron_date_combo.setFixedHeight(22)
        self.cron_date_combo.currentIndexChanged.connect(self.cron_period_change)
        self.cron_date_combo.setCurrentText(self.json_adder()['cron_mode'])

        # Выпадающий список CRON: час
        self.cron_hours_combo = QComboBox(self)
        self.cron_hours_combo.setObjectName('cron_hour')
        self.cron_hours_combo.setToolTip("Hours")
        self.cron_hours_array = [(time(i).strftime('%H')) for i in range(24)]
        self.cron_hours_combo.addItems(self.cron_hours_array)
        self.cron_hours_combo.setCurrentText(self.json_adder()['cron_hour'])
        self.cron_hours_combo.setFixedHeight(22)

        # Выпадающий список CRON: минута
        self.cron_minutes_combo = QComboBox(self)
        self.cron_minutes_combo.setObjectName('cron_minute')
        self.cron_minutes_combo.setToolTip("Minutes")
        self.cron_minutes_array = [datetime.strptime(str(i*timedelta(minutes=15)),'%H:%M:%S').strftime('%M') for i in range(60//15)]
        self.cron_minutes_combo.addItems(self.cron_minutes_array)
        self.cron_minutes_combo.setCurrentText(self.json_adder()['cron_minute'])
        self.cron_minutes_combo.setFixedHeight(22)

        # Кнопка изменения параметров CRON'а
        self.cron_edit_btn = QPushButton('Change')
        self.cron_edit_btn.setObjectName("cron_edit")
        self.cron_edit_btn.setFixedWidth(92)
        self.cron_edit_btn.clicked.connect(lambda: self.json_adder(element=self.cron_date_combo.objectName(), value=self.cron_date_combo.currentText()))
        self.cron_edit_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.cron_date_combo.objectName(), not_the_last_change_for_one_button=True))
        self.cron_edit_btn.clicked.connect(lambda: self.json_adder(element=self.cron_day_combo.objectName(), value=self.cron_day_combo.currentText()))
        self.cron_edit_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.cron_day_combo.objectName(), not_the_last_change_for_one_button=True))
        self.cron_edit_btn.clicked.connect(lambda: self.json_adder(element=self.cron_hours_combo.objectName(), value=self.cron_hours_combo.currentText()))
        self.cron_edit_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.cron_hours_combo.objectName(), not_the_last_change_for_one_button=True))
        self.cron_edit_btn.clicked.connect(lambda: self.json_adder(element=self.cron_minutes_combo.objectName(), value=self.cron_minutes_combo.currentText()))
        self.cron_edit_btn.clicked.connect(lambda: self.roll_back_msg(felement=self.cron_minutes_combo.objectName()))
        self.cron_edit_btn.clicked.connect(lambda: self.tmblr_cron.setChecked(False))
        self.cron_edit_btn.clicked.connect(lambda: self.cron_turn_new())

        # Чекбокс выбора бэкапа БД CRON
        self.db_cron_cb = QCheckBox("б.БД")
        self.db_cron_cb.setToolTip("Бэкап баз данных")
        self.db_cron_cb.setChecked(self.json_adder()['cron_db'])
        self.db_cron_cb.stateChanged.connect(lambda: self.json_quiet_adder('cron_db', self.db_cron_cb.isChecked()))
        self.db_cron_cb.stateChanged.connect(lambda: self.cron_pars_chck('db'))

        # Чекбокс выбора бэкапа ФС CRON
        self.fs_cron_cb = QCheckBox("б.ФС")
        self.fs_cron_cb.setToolTip("Бэкап файловой системы")
        self.fs_cron_cb.setChecked(self.json_adder()['cron_fs'])
        self.fs_cron_cb.stateChanged.connect(self.cron_fs_chck)
        self.fs_cron_cb.stateChanged.connect(lambda: self.cron_pars_chck('fs'))

        # Чекбокс вкл/выкл проверку актуальности бэкапа
        self.fs_cron_ac = QCheckBox("Проверка актуальности б.ФС")
        self.fs_cron_ac.setToolTip("Проверка актуальности файлов Бэкапа файловой системы")
        self.fs_cron_ac.setChecked(self.json_adder()['cron_act_check'])
        self.fs_cron_ac.setDisabled(not self.json_adder()['cron_fs'])
        self.fs_cron_ac.stateChanged.connect(lambda: self.json_quiet_adder('cron_act_check', self.fs_cron_ac.isChecked()))

        # Макет ячейки с двумя чекбоксами
        self.cron_cb_cell = QHBoxLayout()
        self.cron_cb_cell.addWidget(self.db_cron_cb)
        self.cron_cb_cell.addWidget(self.fs_cron_cb)
        self.cron_cb_cell.setContentsMargins(0, 0, 0, 0)
        self.cron_cb_cell.setSpacing(37)

        # Виджет ячейки с двумя чекбоксами
        self.cron_cb_wdgt = QWidget(self)
        self.cron_cb_wdgt.setLayout(self.cron_cb_cell)

        # Тумблер включения CRON'а
        self.tmblr_cron = AnimatedToggle(checked_color="#0F5774")
        self.tmblr_cron.bar_checked_brush = QBrush(QColor('#A3B7C7'))
        self.tmblr_cron.setObjectName('cron_toogle')
        self.tmblr_cron.setFixedSize(QSize(38, 25))
        self.tmblr_cron.setChecked(self.json_adder()['cron'])
        self.tmblr_cron.toggled.connect(lambda: self.cron_turn_new())

        # Макет ячейки с тумблером включения
        self.cron_tmblr_cell = QHBoxLayout()
        self.cron_tmblr_cell.addWidget(QLabel('⠀⠀Вкл/Выкл CRON:'))
        self.cron_tmblr_cell.addWidget(self.tmblr_cron)
        self.cron_tmblr_cell.setContentsMargins(0, 0, 0, 0)
        self.cron_tmblr_cell.setSpacing(10)

        # Виджет ячейки с тумблером включения
        self.cron_tmblr_wdgt = QWidget(self)
        self.cron_tmblr_wdgt.setLayout(self.cron_tmblr_cell)

        # Лейбл предыдущей работы крона
        self.cron_count_job_dateP = QLabel(self)
        self.cron_count_job_dateP.setText(self.update_cron_dates()[0])

        # Лейбл следующей работы крона
        self.cron_count_job_dateN = QLabel(self)
        self.cron_count_job_dateN.setText(self.update_cron_dates()[1])

        # Обратный отсчёт - часы
        self.downtimer = QTimer()
        self.downtimer.timeout.connect(self.countdown)
        self.downtimer.setInterval(1000)
        self.downtimer.start()

        # Лейбл обратного отсчёта до следующей работы крона
        self.cron_countdown_job = QLabel(self)
        self.cron_countdown_job_brother = QLabel(self) # брат-близнец для другого окна (окно с предупреждениями-уведомлениями перед началом бэкапа)
        self.cron_countdown_job_brother.setHidden(True)
        if not self.json_adder()['cron']:
            self.cron_countdown_job.setHidden(True)

        # Макет ячейки с датами запусков CRON'a
        self.cron_dates_cell = QHBoxLayout()
        self.cron_dates_cell.addWidget(QLabel('Предыдущий запуск:'))
        self.cron_dates_cell.addWidget(self.cron_count_job_dateP)
        self.cron_dates_cell.addWidget(QLabel('  ¦  '))
        self.cron_dates_cell.addWidget(QLabel('Следующий запуск:'))
        self.cron_dates_cell.addWidget(self.cron_count_job_dateN)
        self.cron_dates_cell.setContentsMargins(0, 0, 0, 0)
        self.cron_dates_cell.setSpacing(10)

        # Виджет ячейки с датами запусков CRON'a
        self.cron_dates_wdgt = QWidget(self)
        self.cron_dates_wdgt.setLayout(self.cron_dates_cell)

        ### *** МАКЕТЫ ТАБОВ *** ###

        # Макет и наполнение таблицы первого таба
        self.grid1 = QGridLayout(self.group1)
        self.grid1.setColumnMinimumWidth(1, 360)
        self.grid1.setColumnMinimumWidth(2, 103)
        self.grid1.setContentsMargins(0, 0, 0, 0)
        self.grid1.setSpacing(10)
        self.grid1.addWidget(QLabel("Websites list for backup:"), 0, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid1.addWidget(self.all_ws_combo, 0, 1)
        self.grid1.addWidget(self.ws_ref_btn, 0, 2)
        self.grid1.addWidget(QLabel("DBs list for backup:"), 1, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid1.addWidget(self.all_db_combo, 1, 1)
        self.grid1.addWidget(self.db_ref_btn, 1, 2)
        self.grid1.addWidget(QLabel("Backup save path (server):"), 2, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid1.addWidget(self.serv_bckp_path_edit, 2, 1)
        self.grid1.addWidget(self.serv_bckp_open_btn, 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid1.addWidget(self.serv_bckp_path_btn, 2, 2)
        self.grid1.addWidget(QLabel("Deleting backups on the server (days):"), 3, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid1.addWidget(self.server_limit_save_edit, 3, 1)
        self.grid1.addWidget(self.server_limit_save_btn, 3, 2)
        self.grid1.addWidget(self.serv_finder_btn, 4, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Макет и наполнение таблицы второго таба
        self.grid2 = QGridLayout(self.group2)
        self.grid2.setColumnMinimumWidth(1, 360)
        self.grid2.setColumnMinimumWidth(2, 103)
        self.grid2.setContentsMargins(0, 0, 0, 0)
        self.grid2.setSpacing(10)
        self.grid2.addWidget(QLabel("Backup save path (local):"), 0, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid2.addWidget(self.local_bckp_path_label, 0, 1)
        self.grid2.addWidget(self.local_bckp_open_btn, 0, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid2.addWidget(self.local_bckp_path_btn, 0, 2)
        self.grid2.addWidget(QLabel("Deleting backups on the local PC (days):"), 1, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid2.addWidget(self.local_limit_save_edit, 1, 1)
        self.grid2.addWidget(self.local_limit_save_btn, 1, 2)
        self.grid2.addWidget(self.local_finder_btn, 2, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Макет и наполнение таблицы третьего таба
        self.grid3 = QGridLayout(self.group3)
        self.grid3.setColumnMinimumWidth(0, 212)
        self.grid3.setColumnMinimumWidth(2, 172)
        self.grid3.setContentsMargins(0, 0, 0, 0)
        self.grid3.setSpacing(10)
        self.grid3.addWidget(QLabel("Server:"), 1, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid3.addWidget(self.ssh_host_edit, 1, 1)
        self.grid3.addWidget(self.ssh_host_btn, 1, 2)
        self.grid3.addWidget(QLabel("Login:"), 2, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid3.addWidget(self.ssh_login_edit, 2, 1)
        self.grid3.addWidget(self.ssh_login_btn, 2, 2)
        self.grid3.addWidget(QLabel("Password:"), 3, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid3.addWidget(self.ssh_pass_edit, 3, 1)
        self.grid3.addWidget(self.ssh_pass_btn, 3, 2)
        self.grid3.addWidget(QLabel("Port:"), 4, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid3.addWidget(self.ssh_port_edit, 4, 1)
        self.grid3.addWidget(self.ssh_port_btn, 4, 2)

        # Макет и наполнение таблицы третьего таба
        self.grid4 = QGridLayout(self.group4)
        self.grid4.setColumnMinimumWidth(0, 212)
        self.grid4.setColumnMinimumWidth(2, 172)
        self.grid4.setContentsMargins(0, 0, 0, 0)
        self.grid4.setSpacing(10)
        self.grid4.addWidget(QLabel("Server:"), 1, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid4.addWidget(self.ftp_host_edit, 1, 1)
        self.grid4.addWidget(self.ftp_host_btn, 1, 2)
        self.grid4.addWidget(QLabel("Login:"), 2, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid4.addWidget(self.ftp_login_edit, 2, 1)
        self.grid4.addWidget(self.ftp_login_btn, 2, 2)
        self.grid4.addWidget(QLabel("Password:"), 3, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid4.addWidget(self.ftp_pass_edit, 3, 1)
        self.grid4.addWidget(self.ftp_pass_btn, 3, 2)
        self.grid4.addWidget(QLabel("Port:"), 4, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid4.addWidget(self.ftp_port_edit, 4, 1)
        self.grid4.addWidget(self.ftp_port_btn, 4, 2)

        # Макет и наполнение таблицы пятого таба
        self.grid5 = QGridLayout(self.group5)
        self.grid5.setColumnMinimumWidth(0, 212)
        self.grid5.setColumnMinimumWidth(2, 172)
        self.grid5.setContentsMargins(0, 0, 0, 0)
        self.grid5.setHorizontalSpacing(10)
        self.grid5.setVerticalSpacing(0)
        self.grid5.addWidget(QLabel("DB name:"), 1, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid5.addWidget(self.db_name_edit, 1, 1)
        self.grid5.addWidget(self.db_name_btn, 1, 2)
        self.grid5.addWidget(QLabel("Server:"), 2, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid5.addWidget(self.db_host_edit, 2, 1)
        self.grid5.addWidget(self.db_host_btn, 2, 2)
        self.grid5.addWidget(QLabel("Login:"), 3, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid5.addWidget(self.db_login_edit, 3, 1)
        self.grid5.addWidget(self.db_login_btn, 3, 2)
        self.grid5.addWidget(QLabel("Password:"), 4, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid5.addWidget(self.db_pass_edit, 4, 1)
        self.grid5.addWidget(self.db_pass_btn, 4, 2)
        self.grid5.addWidget(QLabel("Client key:"), 5, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid5.addWidget(self.ckc_path_label, 5, 1)
        self.grid5.addWidget(self.ckc_path_btn, 5, 2)
        self.grid5.addWidget(QLabel("Client cert.:"), 6, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid5.addWidget(self.ccc_path_label, 6, 1)
        self.grid5.addWidget(self.ccc_path_btn, 6, 2)
        self.grid5.addWidget(QLabel("Server CA:"), 7, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid5.addWidget(self.scc_path_label, 7, 1)
        self.grid5.addWidget(self.scc_path_btn, 7, 2)

        # Макет и наполнение таблицы шестого таба
        self.grid6 = QGridLayout(self.group6)
        self.grid6.setColumnMinimumWidth(0, 212)
        self.grid6.setColumnMinimumWidth(2, 172)
        self.grid6.setContentsMargins(0, 0, 0, 0)
        self.grid6.setSpacing(10)
        self.grid6.addWidget(QLabel('Application email:'), 0, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid6.addWidget(self.mail_email_edit, 0, 1)
        self.grid6.addWidget(self.mail_email_btn, 0, 2)
        self.grid6.addWidget(QLabel('User ID:'), 1, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid6.addWidget(self.mail_id_edit, 1, 1)
        self.grid6.addWidget(self.mail_id_btn, 1, 2)
        self.grid6.addWidget(QLabel('User secret:'), 2, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid6.addWidget(self.mail_secret_edit, 2, 1)
        self.grid6.addWidget(self.mail_secret_btn, 2, 2)
        self.grid6.addWidget(QLabel("Reporting email:"), 3, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid6.addWidget(self.rprts_email_edit, 3, 1)
        self.grid6.addWidget(self.rprts_test_btn, 3, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid6.addWidget(self.rprts_email_btn, 3, 2)

        # Макет и наполнение таблицы седьмого таба
        self.grid7 = QGridLayout(self.group7)
        self.grid7.setColumnMinimumWidth(0, 236)
        self.grid7.setColumnMinimumWidth(1, 130)
        self.grid7.setColumnMinimumWidth(2, 60)
        self.grid7.setColumnMinimumWidth(3, 60)
        self.grid7.setContentsMargins(0, 0, 0, 0)
        self.grid7.setSpacing(10)
        self.grid7.addWidget(QLabel(''), 0, 0, 0, 7)
        self.grid7.addWidget(self.cron_date_combo, 1, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid7.addWidget(self.cron_day_combo, 1, 1)
        self.grid7.addWidget(self.cron_hours_combo, 1, 2)
        self.grid7.addWidget(self.cron_minutes_combo, 1, 3)
        self.grid7.addWidget(self.cron_edit_btn, 1, 4)
        self.grid7.addWidget(self.cron_cb_wdgt, 2, 0, alignment=Qt.AlignmentFlag.AlignRight)
        self.grid7.addWidget(self.fs_cron_ac, 2, 1, 1, 2)
        self.grid7.addWidget(self.cron_tmblr_wdgt, 2, 3, 1, 4, alignment=Qt.AlignmentFlag.AlignLeft)
        self.grid7.addWidget(self.cron_dates_wdgt, 3, 0, 3, 7, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.grid7.addWidget(self.cron_countdown_job, 4, 0, 4, 7, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Добавление табов
        self.tab_wdgt.addTab(self.group1, "Server")
        self.tab_wdgt.addTab(self.group2, "Local")
        self.tab_wdgt.addTab(self.group3, "SSH")
        self.tab_wdgt.addTab(self.group4, "FTP")
        self.tab_wdgt.addTab(self.group5, "MYSQL")
        self.tab_wdgt.addTab(self.group6, "SMTP")
        self.tab_wdgt.addTab(self.group7, "CRON")
        self.tab_wdgt.setTabEnabled(6, False)
        self.tab_wdgt.setTabToolTip(0, 'Data for backup on inside the server + backup management window on the server')
        self.tab_wdgt.setTabToolTip(1, 'Data for backup to local PC + backup management window on local PC')
        self.tab_wdgt.setTabToolTip(2, 'Data for connecting to the server via SSH')
        self.tab_wdgt.setTabToolTip(3, 'Data for connecting to the server via FTP')
        self.tab_wdgt.setTabToolTip(4, 'Data for connecting to the MySQL database for sending reports')
        self.tab_wdgt.setTabToolTip(5, 'Data for connecting to the SMTP server for sending reports')
        self.tab_wdgt.setTabToolTip(6, 'Data for installing CRON for a scheduled backup')

        # Окно уведомления о неправильной настройке почтовой отправки логов
        self.messageME = QMessageBox()
        self.messageME.setIcon(QMessageBox.Icon.Critical)
        self.messageME.setInformativeText("Email sending error! Run diagnostics and check the spelling of the address(es)!")

        self.count_from_date = datetime.strptime(self.update_cron_dates()[-1], "%Y-%m-%d %H:%M:%S") - datetime.strptime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "%Y-%m-%d %H:%M:%S") # Переменная класса вычтенного значения между планируемой датой-временем бэкапа и нынешней датой-временем

    def renew_subtracted_datetime(self):
        self.count_from_date = datetime.strptime(self.update_cron_dates()[-1], "%Y-%m-%d %H:%M:%S") - datetime.strptime(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "%Y-%m-%d %H:%M:%S") # Обновление переменной класса вычтенного значения между планируемой датой-временем бэкапа и нынешней датой-временем

    def countdown(self):
        # Каждую секунду отнимаем по 1 секунде от разницы нынешней даты и даты следующего бэкапа
        try:
            self.count_from_date = self.count_from_date - timedelta(seconds=1)
            self.cron_countdown_job.setText(str(self.count_from_date))
            self.cron_countdown_job_brother.setText(str(self.count_from_date))
            if "day" in str(self.count_from_date):
                self.cron_countdown_job_brother.setFixedWidth(105)
                self.cron_countdown_job.setFixedWidth(101)
            else:
                self.cron_countdown_job_brother.setFixedWidth(60)
                self.cron_countdown_job.setFixedWidth(56)
        except KeyboardInterrupt:
            pass

    def send_test_letter(self):
        # Отправка тестового письма
        try:
            mail.run(test=True)
            self.view = self.messageM.exec()
        except Exception:
            view = self.messageME.show()

    def cron_period_change(self, new_index):
        # Сделать неактивн. вып. список дней недели при определённом сигнале вып. списка выбора частоты бэкапа
        if new_index == 1:
            self.cron_day_combo.setDisabled(False)
        elif new_index == 0:
            self.cron_day_combo.setDisabled(True)

    def cron_fs_chck(self, new_state):
        # Сделать активн. опцию проверки актуальности бэкапа ФС при выборе данного бэкапа
        if new_state == 0:
            self.fs_cron_ac.setDisabled(True)
            self.fs_cron_ac.setChecked(False)
        else:
            self.fs_cron_ac.setDisabled(False)
        self.json_quiet_adder('cron_fs', self.fs_cron_cb.isChecked())

    def cron_pars_chck(self, cur_tmblr):
        # Выключение тумблера, если отключается последний чекбокс выбора бэкапа
        if cur_tmblr == 'db':
            state = self.fs_cron_cb.isChecked()
        else:
            state = self.db_cron_cb.isChecked()
        if not state:
            self.tmblr_cron.setChecked(False)

    def update_cron_dates(self):
        # Функция обновления значений времени запусков CRON (предыдущий - следующий)
        now = datetime.now()
        sched = self.json_adder()['cron_last_schedule']
        cron = croniter(sched, now)
        previousdate = cron.get_prev(datetime)
        cron_schedule_time = datetime.strptime(self.json_adder()['cron_schedule_time'], "%Y-%m-%d %H:%M:%S")
        nextdate = cron.get_next(datetime)

        if cron_schedule_time < previousdate:
            cron_dates_tuple = (str(previousdate), str(nextdate))
        else:
            cron_dates_tuple = ('never', str(nextdate))
        if self.json_adder()['cron']:
            return cron_dates_tuple
        else:
            return ('CRON is scheduled', 'CRON is not scheduled', str(nextdate))

    def cron_turn_new(self):
        # Функция включения/выключения CRON'a
        if not self.json_adder()['cron_db'] and not self.json_adder()['cron_fs'] and self.tmblr_cron.isChecked():
            self.messageT = QMessageBox()
            self.messageT.setIcon(QMessageBox.Icon.Warning)
            self.messageT.setInformativeText("Choose at least one backup!")
            self.view = self.messageT.exec()
            self.tmblr_cron.setCheckable(False)
            self.tmblr_cron.setCheckable(True)
        elif not self.json_adder()['cron_db'] and not self.json_adder()['cron_fs'] and not self.tmblr_cron.isChecked():
            self.json_quiet_adder('cron', False)
            surcron.remove_cron()
            self.chng_cron.setText('¦ CRON: off')
            self.cron_count_job_dateP.setText(self.update_cron_dates()[0])
            self.cron_count_job_dateN.setText(self.update_cron_dates()[1])
            self.cron_countdown_job.setHidden(True)
        else:
            if not self.tmblr_cron.isChecked():
                self.json_quiet_adder('cron', False)
                surcron.remove_cron()
                self.chng_cron.setText('¦ CRON: off')
                self.cron_count_job_dateP.setText(self.update_cron_dates()[0])
                self.cron_count_job_dateN.setText(self.update_cron_dates()[1])
                self.cron_countdown_job.setHidden(True)
            else:
                self.json_quiet_adder('cron', True)
                app_path = os.path.abspath(__file__)
                surcron.create_cron(path_to_app=app_path)
                self.chng_cron.setText('¦ CRON: on')
                self.cron_count_job_dateP.setText(self.update_cron_dates()[0])
                self.cron_count_job_dateN.setText(self.update_cron_dates()[1])
                self.cron_countdown_job.setHidden(False)
                self.renew_subtracted_datetime()

class MinWorker(QThread):
    # Поток для работы CRON - бэкапа
    def __init__(self, func, args):
        super(MinWorker, self).__init__()
        self.func = func
        self.args = args

    def run(self):
        self.func(*self.args)

class CRON_Widget(QWidget):
    # Класс интерфейса окна CRON-бэкапа
    def __init__(self):
        super().__init__()
        self.setWindowTitle('IHostBackup')
        self.setFixedSize(QSize(250, 56))

        # Установка окна в правом нижнем углу экрана
        self.bottom_right()

        # Макет окна - таблица
        self.cron_grid = QGridLayout()
        self.cron_grid.setSpacing(5)
        self.cron_grid.setContentsMargins(4, 0, 4, 0)

        # Установка макета
        self.setLayout(self.cron_grid)

        # Мини - лого
        self.label_logo_min = QLabel(self)
        self.pixmap_logo_min = QPixmap(resource_path("assets/logo-min.png")).scaled(46, 42, Qt.AspectRatioMode.KeepAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation)
        self.label_logo_min.setGeometry(QRect(0, 0, 38, 36))
        self.label_logo_min.setText("")
        self.label_logo_min.setPixmap(self.pixmap_logo_min)
        self.label_logo_min.setToolTip(f'"Automated backup system for hosting resources, with reporting v.1.1.0 - © {date.today().year} IvNoch"')

        # Сообщение об активном плановом бэкапе
        self.label_after_run = QLabel(self)
        self.label_after_run.setText('Scheduled backup CRON in progress')

        # Анимация трёх точек
        self.label_anim_gif = QMovie(resource_path("assets/dots.gif"))
        self.label_anim_gif.setScaledSize(QSize(10, 10))
        self.label_anim_label = QLabel(self)
        self.label_anim_label.setFixedSize(10, 10)
        self.label_anim_label.setMovie(self.label_anim_gif)
        self.label_anim_gif.start()

        # Добавление виджетов в макет
        self.cron_grid.addWidget(self.label_logo_min, 0, 0)
        self.cron_grid.addWidget(self.label_after_run, 0, 1)
        self.cron_grid.addWidget(self.label_anim_label, 0, 2)

        # Окно подтверждения остановки сценария бэкапа
        self.messageCS = QMessageBox()
        self.messageCS.setIcon(QMessageBox.Icon.Warning)
        self.messageCS.setInformativeText("Вы действительно хотите прервать сценарий бэкапа? Все файлы этой сессии будут удалены! А также программа может перейти в режим ожидания на некоторое время!")
        self.messageCS.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        # Окно уведомления об остановке сценария бэкапа и удалении файлов
        self.messageCI = QMessageBox()
        self.messageCI.setIcon(QMessageBox.Icon.Information)
        self.messageCI.setInformativeText("Сценарий прерван. Файлы удалены.")

        # Поток для работы бэкапа
        self.min_bee = MinWorker(self.cron_strt, ())
        self.min_bee.start()
        self.min_bee.finished.connect(self.cron_on_finish)

        # Настройки логгера и его хэндлера
        self.logger = logging.getLogger('logger')
        self.consoleHandler = ConsoleWindowLogHandler()
        self.consoleHandler.setFormatter(CustomFormatter())

    def bottom_right(self):
        # Позиционируем окно по правому нижнему углу экрана
        bottom_right_point = QApplication.primaryScreen().availableGeometry().bottomRight()
        self.move(bottom_right_point)

    def cron_on_finish(self):
        # Закрытие окна по окончании бэкапа
        sleep(4)
        self.close()

    def db_getter(self):
        # Создаём соединение с cервером по SSH
        pass
        # client = paramiko.SSHClient()
        # client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # client.connect(hostname=host, username=user, password=secret, port=port)
        #
        # # Создаём список сайтов (директорий сайтов)
        # stdin, stdout, stderr = client.exec_command('ls -l')
        # data = stdout.read()
        # client.close()

    # def cron_strt(self):
    #     # CRON старт бэкапа
    #     try:
    #         run.cron_start(db_tuple=self.db_getter()[0], db_combo=self.db_getter()[1])
    #     except Exception:
    #         pass
    #     config_file = open(resource_path("settings.json"), 'r')
    #     config = json.load(config_file)  # json-файл конфигурации
    #     config_file.close()
    #     check_log_file = open(config['path_to_local_backups'] + "/logs/" + config['latest_run'] + ".log", 'r')
    #     check_log = check_log_file.read()
    #     check_log_file.close()
    #     if config['mail_alerts']:
    #         if 'WARNING' in check_log or 'ERROR' in check_log or 'CRITICAL' in check_log:
    #             try:
    #                 mail.run()  # Отсылаем отчёт письмом
    #             except Exception:
    #                 pass
    #     self.label_anim_label.hide()
    #     self.label_after_run.setText('DONE')

    @staticmethod
    def delete_files_stp():
        # Удаление файлов прерванного бэкапа
        config_file = open(resource_path("settings.json"), 'r')
        config = json.load(config_file)  # json-файл конфигурации
        config_file.close()
        my_dir = config['path_to_local_backups']
        for fname in os.listdir(my_dir):
            if fname.startswith(config['latest_run']):
                try:
                    os.remove(os.path.join(my_dir, fname))
                except PermissionError:
                    shutil.rmtree(os.path.join(my_dir, fname))

    def closeEvent(self, event):
        # Сценарий закрытия окна
        if self.min_bee.isRunning():
            self.manual_stp()
            event.ignore()
        else:
            event.accept()

    def manual_stp(self):
        # Ручной останов бэкапа
        config_file = open(resource_path("settings.json"), 'r')
        config = json.load(config_file)  # json-файл конфигурации
        config_file.close()
        self.stp_que = self.messageCS.exec()
        if self.stp_que == QMessageBox.StandardButton.Yes:
            self.label_anim_label.hide()
            self.label_after_run.setText('ПРЕРЫВАНИЕ...')
            if config['cron_db']:
                dbbckp.EOFFlag = True
                try:
                    if not dbbckp.dump_call.poll():
                        dbbckp.dump_call.kill()
                except AttributeError:
                    pass
                try:
                    if not dbbckp.arch_call.poll():
                        dbbckp.arch_call.kill()
                except AttributeError:
                    pass
            if config['cron_fs']:
                wsbckp.EOFFlag = True
            self.min_bee.wait()
            handlers = self.logger.handlers[:]
            for handler in handlers:
                self.logger.removeHandler(handler)
                handler.close()
            self.logger.addHandler(self.consoleHandler)
            fh = logging.FileHandler(
                f"{config['path_to_local_backups']}/logs/{config['latest_run']}.log",
                mode='a', encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%d.%m.%Y %H:%M:%S'))
            self.logger.addHandler(fh)
            # 1. Удаляем данные о бэкапе из таблицы backup_tables, по полученным ID бэкапов, относительно времени последнего бэкапа
            # 2. Удаляем данные о бэкапе из таблицы backups, от имени второго бэкапера
            try:
                # Получаем форматированное значение даты и времени последнего бэкапа, в часовой зоне UTC
                q_d = datetime.strptime(datetime.now().strftime('%Y-%m-%d %H:%M'),
                                        '%Y-%m-%d %H:%M') - datetime.strptime(
                    datetime.utcnow().strftime('%Y-%m-%d %H:%M'), '%Y-%m-%d %H:%M')  # Сдвиг по UTC
                r_d = datetime.strptime(config["latest_run"], '%Y_%m_%d_%H_%M') - q_d
                formatted_cur_datetime_tuple = str(r_d.strftime('%Y_%m_%d_%H_%M')).split('_')
                formatted_cur_datetime = f'{formatted_cur_datetime_tuple[0]}-{formatted_cur_datetime_tuple[1]}-{formatted_cur_datetime_tuple[2]} {formatted_cur_datetime_tuple[3]}:{formatted_cur_datetime_tuple[4]}'

                connection = MySQLdb.connect(
                    host=config['host'],
                    user=config['login'],
                    password=config['password'],
                    db=config['fs_db'],
                    ssl={'key': config["path_to_ckc"], 'ca': config["path_to_scc"], 'cert': config["path_to_ccc"]}
                )
                cursor = connection.cursor()
                # Получаем ID всех бэкапов, где время создания бэкапа совпадает с форматированным значением нашего последнего бэкапа
                cursor.execute('''SELECT Backup_ID
                    FROM backups
                    WHERE Backup_Create = %s''', [formatted_cur_datetime])
                cur_backups_ids = cursor.fetchall()
                formatted_cur_backups_ids = [x[0] for x in cur_backups_ids]

                for id in formatted_cur_backups_ids:
                    # Удаляем записи о всех бэкапах, где ID  совпадают с полученными выше
                    cursor.execute('''DELETE FROM backup_tables
                        WHERE Backup_Table_Backup_ID=%s;''', [id])
                    connection.commit()
                    cursor.execute('''DELETE FROM backup_files
                        WHERE Backup_File_Backup_ID=%s;''', [id])
                    connection.commit()

                # Удаляем записи из таблицы backups, где время создания бэкапа совпадает с форматированным значением нашего последнего бэкапа
                cursor.execute('''DELETE FROM backups
                            WHERE Backup_Create=%s;''', [formatted_cur_datetime])
                connection.commit()
                connection.close()
                dbbckp.EOFFlag = False
                wsbckp.EOFFlag = False
                self.logger.info('-------БЭКАП ПРЕРВАН | ФАЙЛЫ УДАЛЕНЫ-------')
            except Exception as e:
                self.logger.error(f'P.S. Ошибка удаления записи о бэкапах в БД {e}')
                self.logger.info('-------ПРЕРЫВАНИЕ БЭКАПА ФАЙЛОВОЙ СИСТЕМЫ С ОШИБКОЙ-------')

            handlers = self.logger.handlers[:]
            for handler in handlers:
                self.logger.removeHandler(handler)
                handler.close()
            self.delete_files_stp()
            # При наличии ошибок в отчёте, высылаем его письмом по почте
            check_log_file = open(config['path_to_local_backups'] + "/logs/" + config['latest_run'] + ".log", 'r')
            check_log = check_log_file.read()
            check_log_file.close()
            if config['mail_alerts']:
                if 'WARNING' in check_log or 'ERROR' in check_log or 'CRITICAL' in check_log:
                    try:
                        mail.run()  # Отсылаем отчёт письмом
                    except Exception:
                        pass
            self.stp_inf = self.messageCI.exec()
            self.close()

# Стили
qss = f""" 
        QLineEdit {{
            padding-left: 2px;
        }}
        QPushButton::menu-indicator {{
            image: url('{resource_path("assets/arrow-b.png")}');
            subcontrol-position: right center;
            subcontrol-origin: padding;
            width: 10px;
            height: 10px;
            left: -4px; 
        }}
        QMenu::item:selected {{
            background-color: rgb(15, 87, 116);
        }}
        QGroupBox {{
            background-color: transparent;
            border: 1px solid #b5b5b5;
            border-radius: 8px;
            margin-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top center;
            padding: 0px 10px;
        }}
        QTabBar::tab {{
            background-color: #ffffff;
            border: 0.5px solid #ededed;
            padding: 3px 5px;
            width: 65px;
        }}
        QTabBar::tab:selected {{
            background-color: rgb(15, 87, 116);
            color: #ffffff;
        }}
        QComboBox {{
            border-radius: 5.5px;
            padding-left: 5px;
            margin-top: 1.5px;
        }}
        QComboBox:editable {{
            background: #ffffff;
        }}
        QComboBox QAbstractItemView {{
            padding: 1px;
            margin: 1px, 1px, 1px, 1px;
        }}
        QComboBox::drop-down {{
            background-color: rgb(15, 87, 116); 
            border-top-right-radius: 5px;
            border-bottom-right-radius: 5px;
            width: 22px;
            margin: 0;
            padding: 0;
        }}
        QComboBox::down-arrow {{
            image: url('{resource_path("assets/arrow.png")}');
            width: 10px;
            height: 10px;
        }}
        QListView {{
            background-color: rgb(255, 255, 255);
            selection-background-color: rgb(15, 87, 116);
        }}
        QLabel#tooltip {{
            font-size: 9px;
            color: #787878;
        }}
        QPushButton#trblshtng {{
            border: 1px solid #ffffff;
            background-color: rgb(15, 87, 116);
            color: #ffffff;
        }}
        QPushButton#trblshtng:hover {{
            background-color: rgb(21, 105, 139);
        }}
        QPushButton#trblshtng:pressed {{
            color: #2684aa;
            background-color: rgb(21, 105, 139);
        }}
        QPushButton#options_btn_delete {{
            background-color: #ffffff;
            border: 0px solid #ffffff;
        }}
        QPushButton#options_btn_download {{
            background-color: #ffffff;
            border: 0px solid #ffffff;
        }}
        QPushButton#options_btn_delete {{
            background-color: #ffffff;
            border: 0px solid #ffffff;
        }}
        QPushButton#options_btn {{
            background-color: transparent;
            border: 0px solid transparent;
        }}
        QPushButton#log_btn {{
            border-radius: 100%;
        }}
        QCheckBox::indicator {{
            width: 15px;
            height: 15px;
            border: 0.5px solid #c9c9c9;
            border-radius: 2px;
            background-color: rgb(255, 255, 255);
            margin: 2px;
        }}
        QCheckBox::indicator:checked {{
            background-color: rgb(15, 87, 116);
            image: url('{resource_path("assets/check.png")}');
        }}
        QTabWidget::tab-bar {{
            alignment: center;
        }}
      """

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # app.setWindowIcon(QIcon(resource_path("assets/marmot_logo.png")))
    app.setStyleSheet(qss)
    if len(sys.argv) == 2 and sys.argv[1] == 'CRON':
        cron_suslik = CRON_Widget()
        cron_suslik.show()
    else:
        suslik_app = SUSLIK_Admin()
        suslik_app.show()
    sys.exit(app.exec())