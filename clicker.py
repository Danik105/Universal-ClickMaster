import time
import pyautogui
import keyboard
import pygetwindow as gw
import pickle
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QComboBox, QLabel, QTextEdit, QLineEdit, \
    QMessageBox, QDialog, QHBoxLayout
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QMutex

class WorkerThread(QThread):
    signal = pyqtSignal(str, float)  # Added timestamp parameter

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mutex = QMutex()

    def run(self):
        while True:
            self.mutex.lock()
            if self.parent().code_active and self.parent().selected_window_title:
                time.sleep(self.parent().cooldown)
                timestamp = time.time()
                self.signal.emit("клик", timestamp)
                window_list = gw.getWindowsWithTitle(self.parent().selected_window_title)
                if window_list:
                    target_window = window_list[0]
                    try:
                        if target_window.isMinimized:
                            target_window.restore()
                        target_window.activate()
                        target_rect = target_window._rect
                        center_x = target_rect.left + target_rect.width // 2
                        center_y = target_rect.top + target_rect.height // 2
                        for _ in range(self.parent().num_clicks):
                            if self.parent().stop_thread:
                                break
                            pyautogui.click(center_x, center_y)
                            time.sleep(1)
                    except gw.PyGetWindowException as e:
                        self.signal.emit(f"Ошибка активации окна: {str(e)}", timestamp)
            else:
                time.sleep(1)
            self.mutex.unlock()
            if self.parent().stop_thread:
                break

class ToggleCode:
    def __init__(self, window_selector):
        self.window_selector = window_selector

    def __call__(self):
        self.window_selector.code_active = not self.window_selector.code_active
        self.window_selector.stop_thread = False if self.window_selector.code_active else True

        if self.window_selector.code_active and not self.window_selector.selected_window_title:
            try:
                with open(self.window_selector.saved_window_path, 'rb') as file:
                    self.window_selector.selected_window_title = pickle.load(file)
                    self.window_selector.window_label.setText(
                        f"Выбрано окно: {self.window_selector.selected_window_title}")
            except FileNotFoundError:
                QMessageBox.warning(self.window_selector, 'Ошибка', 'Файл с сохраненным окном не найден.')

        self.window_selector.update_status_style()
        print("Код активирован" if self.window_selector.code_active else "Код выключен")

class SettingsDialog(QDialog):
    def __init__(self, window_selector):
        super().__init__()

        self.window_selector = window_selector

        self.setWindowTitle("Настройки")
        self.setGeometry(200, 200, 300, 150)

        layout = QVBoxLayout()

        self.cooldown_label = QLabel("КД (сек):")
        layout.addWidget(self.cooldown_label)

        self.cooldown_input = QLineEdit()
        layout.addWidget(self.cooldown_input)

        self.num_clicks_label = QLabel("Количество кликов:")
        layout.addWidget(self.num_clicks_label)

        self.num_clicks_input = QLineEdit()
        layout.addWidget(self.num_clicks_input)

        self.hotkey_label = QLabel("Горячая клавиша:")
        layout.addWidget(self.hotkey_label)

        self.hotkey_input = QLineEdit()
        layout.addWidget(self.hotkey_input)

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_settings)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def save_settings(self):
        try:
            new_cooldown = float(self.cooldown_input.text())
            new_num_clicks = int(self.num_clicks_input.text())
            new_hotkey = self.hotkey_input.text()

            if new_cooldown < new_num_clicks:
                QMessageBox.warning(self, 'Ошибка ввода', 'КД не может быть меньше количества кликов')
                return

            self.window_selector.cooldown, self.window_selector.num_clicks, self.window_selector.hotkey = \
                new_cooldown, new_num_clicks, new_hotkey

            if self.window_selector.hotkey != new_hotkey:
                keyboard.remove_hotkey(self.window_selector.hotkey)
                keyboard.add_hotkey(self.window_selector.hotkey, toggle_code_instance)

            self.window_selector.update_status_style()
            self.window_selector.cooldown_value_label.setText(str(self.window_selector.cooldown))
            self.window_selector.num_clicks_value_label.setText(str(self.window_selector.num_clicks))

        except ValueError:
            QMessageBox.warning(self, 'Ошибка ввода', 'Введите корректные значения для КД и Количества кликов')
            return
        self.accept()

class WindowSelector(QWidget):
    def __init__(self):
        super().__init__()

        self.code_active = False
        self.selected_window_title = None
        self.stop_thread = False
        self.cooldown = 0
        self.num_clicks = 0
        self.hotkey = 'F4'
        self.saved_window_path = 'saved_window.pkl'

        self.setWindowTitle("Window Selector")
        self.setGeometry(100, 100, 400, 250)

        layout = QVBoxLayout()

        self.window_label = QLabel("Выберите окно:")
        layout.addWidget(self.window_label)

        self.window_combo = QComboBox()
        layout.addWidget(self.window_combo)

        refresh_button = QPushButton("Обновить список окон")
        refresh_button.clicked.connect(self.refresh_windows)
        layout.addWidget(refresh_button)

        select_button = QPushButton("Выбрать окно")
        select_button.clicked.connect(self.select_window)
        layout.addWidget(select_button)

        settings_button = QPushButton("Настройки")
        settings_button.clicked.connect(self.show_settings)
        layout.addWidget(settings_button)

        self.cooldown_label = QLabel("КД (сек):")
        layout.addWidget(self.cooldown_label)

        self.cooldown_value_label = QLabel(str(self.cooldown))
        layout.addWidget(self.cooldown_value_label)

        self.num_clicks_label = QLabel("Количество кликов:")
        layout.addWidget(self.num_clicks_label)

        self.num_clicks_value_label = QLabel(str(self.num_clicks))
        layout.addWidget(self.num_clicks_value_label)

        self.output_text = QTextEdit()
        layout.addWidget(self.output_text)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        self.setLayout(layout)

        self.worker_thread = WorkerThread(self)
        self.worker_thread.signal.connect(self.update_output)

        self.update_status_style()

    def refresh_windows(self):
        self.window_combo.clear()
        open_windows = gw.getAllTitles()
        for window in open_windows:
            self.window_combo.addItem(window)

    def select_window(self):
        self.selected_window_title = self.window_combo.currentText()
        self.window_label.setText(f"Выбрано окно: {self.selected_window_title}")

        with open(self.saved_window_path, 'wb') as file:
            pickle.dump(self.selected_window_title, file)

        self.cooldown_value_label.setText(str(self.cooldown))
        self.num_clicks_value_label.setText(str(self.num_clicks))

        self.worker_thread.start()

    def update_output(self, message, timestamp):
        current_text = self.output_text.toPlainText()
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        self.output_text.setPlainText(current_text + f"\n{message} в {current_time}")

    def update_status_style(self):
        if self.code_active:
            self.status_label.setStyleSheet(
                "color: green; font-weight: bold; background-color: rgba(0, 255, 0, 50%);")
            self.status_label.setText("Запущено")
        else:
            self.status_label.setStyleSheet(
                "color: red; font-weight: bold; background-color: rgba(255, 0, 0, 50%);")
            self.status_label.setText("Не работает")

    def show_settings(self):
        settings_dialog = SettingsDialog(self)
        settings_dialog.cooldown_input.setText(str(self.cooldown))
        settings_dialog.num_clicks_input.setText(str(self.num_clicks))
        settings_dialog.hotkey_input.setText(self.hotkey)

        result = settings_dialog.exec_()

        if result == QDialog.Accepted:
            self.cooldown_value_label.setText(str(self.cooldown))
            self.num_clicks_value_label.setText(str(self.num_clicks))

if __name__ == "__main__":
    app = QApplication([])
    window_selector = WindowSelector()
    window_selector.show()

    toggle_code_instance = ToggleCode(window_selector)
    keyboard.add_hotkey(window_selector.hotkey, toggle_code_instance)

    app.exec_()
