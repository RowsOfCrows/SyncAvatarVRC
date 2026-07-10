import asyncio
import json
from pathlib import Path
import platform
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QCheckBox, QSlider, QDoubleSpinBox, 
                             QLabel, QHBoxLayout, QScrollArea, QSpinBox, QTabWidget, QSizePolicy)
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from pythonosc import dispatcher, osc_server, udp_client
import qasync
import traceback


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self, osc_handler_import):
        super().__init__()

        self.osc_handler = osc_handler_import
        self.osc_handler.parameter_updated.connect(self.create_parameter_widget)
        self.osc_handler.parameter_value_changed.connect(self.update_parameter_widget)
        self.osc_handler.clear_parameters.connect(self.clear_all_parameters)

        self.setWindowTitle("VRChat Parameter Controller")
        self.resize(400, 1000)

        self.param_widgets = {}
        self.trashed_widgets = {}

        # Create the tabs
        tabs = QTabWidget()
        self.setCentralWidget(tabs)


        # --------------------
        # Parameters tab
        # --------------------
        parameters_tab = QWidget()
        parameters_layout = QVBoxLayout(parameters_tab)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        scroll_content = QWidget()
        self.params_layout = QVBoxLayout(scroll_content)

        scroll.setWidget(scroll_content)

        parameters_layout.addWidget(scroll)

        # --------------------
        # Trashed Params tab
        # --------------------
        trash_tab = QWidget()
        trash_layout = QVBoxLayout(trash_tab)

        scrolltrash = QScrollArea()
        scrolltrash.setWidgetResizable(True)
        scrolltrassh_content = QWidget()
        self.trash_layout = QVBoxLayout(scrolltrassh_content)
        scrolltrash.setWidget(scrolltrassh_content)
        trash_layout.addWidget(scrolltrash)
        self.trash_layout.addStretch()
        # --------------------
        # Settings tab
        # --------------------
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)

        settings_button = QPushButton("Test Button")
        settings_layout.addWidget(settings_button)

        # --------------------
        # Blacklist
        # --------------------
        blacklist_tab = QWidget()
        blacklist_layout = QVBoxLayout(blacklist_tab)

        # --------------------
        # Logs tab
        # --------------------
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)

        # --------------------
        # Add tabs
        tabs.addTab(parameters_tab, "Parameters")
        tabs.addTab(trash_tab, "Trashed")     
        tabs.addTab(blacklist_tab, "Blacklist")
        tabs.addTab(settings_tab, "Settings")
        tabs.addTab(logs_tab, "Logs")     

        # --------------------
        # opening message

        self.empty_label = QLabel("Change your avatar to load the parameters!\n" \
                                  "For this inconvenience, blame vrchat!\n\n" \
                                  "Waiting for avatar change . . .")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("font-size: 18px;")
        self.params_layout.addWidget(self.empty_label)
        self.params_layout.addStretch()


        #self.setStyleSheet("""
        #    QLabel { font-size: 13px; }
        #    QPushButton { border-radius: 4px; padding: 4px; }
        #    QScrollArea { border: none; }
        #""")

    def create_parameter_widget(self, param_name: str, param_type: str):
        """Create appropriate widget based on parameter type"""
        # Create a container for this parameter
        container = QWidget()
        layout = QHBoxLayout(container)
        
        # Add label
        label = QLabel(f"{param_name}:")
        label.setMinimumWidth(120)
        layout.addWidget(label)

        # Create appropriate widget based on type
        if param_type == 'Bool':
            widget_group = self.create_bool_widgets(param_name)
            layout.addWidget(widget_group)
        elif param_type == 'Int':
            widget_group = self.create_int_widgets(param_name)
            layout.addWidget(widget_group)
        elif param_type == 'Float':
            widget_group = self.create_float_widgets(param_name)
            layout.addWidget(widget_group)
        else:
            layout.addWidget(QLabel(f"Unknown type: {param_type}"))
        
        
        #-------------
        #Trash button
        #-------------
        # Add stretch so trash button stays on the right
        layout.addStretch()

        # Trash button
        delete_button = QPushButton("🗑")
        delete_button.setFixedWidth(35)

        delete_button.clicked.connect(
            lambda: self.trash_clicked(param_name, param_type, container)
        )

        layout.addWidget(delete_button)

        # Add to layout
        #self.params_layout.addWidget(container)
        self.params_layout.insertWidget(self.params_layout.count() - 1, container)
   
    def trash_clicked(self, param_name, param_type, widget):
        print(f"Removing {param_name}")

        # Remove from layout
        self.params_layout.removeWidget(widget)

        widget.setParent(None)
        old_layout = widget.layout()
        old_button = old_layout.itemAt(old_layout.count() - 1).widget()
        old_layout.removeWidget(old_button)
        old_button.deleteLater()

        restore_button = QPushButton("♻")
        restore_button.setFixedWidth(35)
        restore_button.clicked.connect(
            lambda: self.restore_clicked(param_name, param_type, widget)
        )
        old_layout.addWidget(restore_button)

        # Move it into the trash tab's layout
        #self.trash_layout.addWidget(widget)
        self.trash_layout.insertWidget(self.trash_layout.count() - 1, widget)

        # Track it as trashed instead of just deleting the reference
        if param_name in self.param_widgets:
            del self.param_widgets[param_name]
        self.trashed_widgets[param_name] = widget


    def restore_clicked(self, param_name, param_type, widget):
        #TODO this actually crashes if you try to use it after restoring. please fix.
        print(f"Restoring {param_name}")

        self.trash_layout.removeWidget(widget)
        widget.setParent(None)

        # Swap the restore button back for a trash button
        old_layout = widget.layout()
        old_button = old_layout.itemAt(old_layout.count() - 1).widget()
        old_layout.removeWidget(old_button)
        old_button.deleteLater()

        delete_button = QPushButton("🗑")
        delete_button.setFixedWidth(35)
        delete_button.clicked.connect(
            lambda: self.trash_clicked(param_name, param_type, widget)
        )
        old_layout.addWidget(delete_button)

        #self.params_layout.addWidget(widget)
        self.params_layout.insertWidget(self.params_layout.count() - 1, widget)
        
        del self.trashed_widgets[param_name]
        self.param_widgets[param_name] = widget
        
    def create_bool_widgets(self, param_name: str):
        """Create button and checkbox for boolean parameters"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create button that changes color
        button = QPushButton("OFF")
        button.setCheckable(True)
        button.setFixedWidth(80)
        self.update_button_color(button, False)
        
        # Create checkbox
        checkbox = QCheckBox("Enable")
        
        # Connect them together
        def on_button_clicked(checked):
            checkbox.setChecked(checked)
            self.update_button_color(button, checked)
            button.setText("ON" if checked else "OFF")
            #print(f"{param_name} set to {checked}")
            asyncio.create_task(self.osc_handler.send_parameter(param_name, checked))
            
        def on_checkbox_clicked(checked):
            button.setChecked(checked)
            self.update_button_color(button, checked)
            button.setText("ON" if checked else "OFF")
            #print(f"{param_name} set to {checked}")
            asyncio.create_task(self.osc_handler.send_parameter(param_name, checked))
        
        button.clicked.connect(on_button_clicked)
        checkbox.clicked.connect(on_checkbox_clicked)
        
        layout.addWidget(button)
        layout.addWidget(checkbox)
        layout.addStretch()
        
        # Store references
        self.param_widgets[param_name] = {'button': button, 'checkbox': checkbox}
        
        return container
    
    def create_int_widgets(self, param_name: str):
        """Create slider and spinbox for integer parameters"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Slider (0-100 range, adjust as needed)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(255)
        slider.setValue(0)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(10)
        
        # Integer spinbox
        spinbox = QSpinBox()
        spinbox.setMinimum(0)
        spinbox.setMaximum(255)
        spinbox.setValue(0)
        
        # Connect them together
        def on_slider_change(value):
            spinbox.blockSignals(True)  # Prevent recursive updates
            spinbox.setValue(value)
            spinbox.blockSignals(False)
            #print(f"{param_name} set to {value}")
            asyncio.create_task(self.osc_handler.send_parameter(param_name, value))
        
        def on_spinbox_change(value):
            slider.blockSignals(True)  # Prevent recursive updates
            slider.setValue(value)
            slider.blockSignals(False)
            #print(f"{param_name} set to {value}")
            asyncio.create_task(self.osc_handler.send_parameter(param_name, value))
        
        slider.valueChanged.connect(on_slider_change)
        spinbox.valueChanged.connect(on_spinbox_change)
        
        layout.addWidget(slider)
        layout.addWidget(spinbox)
        
        self.param_widgets[param_name] = {'slider': slider, 'spinbox': spinbox}
        
        return container
    
    def create_float_widgets(self, param_name: str):
        """Create slider and spinbox for float parameters"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Slider (will represent 0.0 to 1.0 as 0-100)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(100)
        slider.setValue(0)
        
        # Double spinbox
        spinbox = QDoubleSpinBox()
        spinbox.setMinimum(0.0)
        spinbox.setMaximum(1.0)
        spinbox.setSingleStep(0.01)
        spinbox.setDecimals(2)
        spinbox.setValue(0.0)
        
        # Connect them together
        def on_slider_change(value):
            float_value = value / 100.0
            spinbox.blockSignals(True)  # Prevent recursive updates
            spinbox.setValue(float_value)
            spinbox.blockSignals(False)
            asyncio.create_task(self.osc_handler.send_parameter(param_name, float_value))
        
        def on_spinbox_change(value):
            int_value = int(value * 100)
            slider.blockSignals(True)  # Prevent recursive updates
            slider.setValue(int_value)
            slider.blockSignals(False)
            asyncio.create_task(self.osc_handler.send_parameter(param_name, value))
        
        slider.valueChanged.connect(on_slider_change)
        spinbox.valueChanged.connect(on_spinbox_change)
        
        layout.addWidget(slider)
        layout.addWidget(spinbox)
        
        self.param_widgets[param_name] = {'slider': slider, 'spinbox': spinbox}
        
        return container
    
    def update_button_color(self, button: QPushButton, is_on: bool):
        """Update button color based on state"""
        if is_on:
            button.setStyleSheet("background-color: #4CAF50; color: white;")  # Green
        else:
            button.setStyleSheet("background-color: #f44336; color: white;")  # Red
    
    def update_parameter_widget(self, param_name: str, value):
        """Update widget when VRChat sends a parameter change"""
        if param_name not in self.param_widgets:
            return
        
        widgets = self.param_widgets[param_name]
    
        # Update the UI widget if it exists
        if param_name in self.param_widgets:
            widget_dict = self.param_widgets[param_name]
            
            # Update the appropriate widget based on type
            if 'checkbox' in widget_dict:
                # Boolean parameter
                checkbox = widget_dict['checkbox']
                checkbox.blockSignals(True)
                checkbox.setChecked(bool(value))
                checkbox.blockSignals(False)
                
            elif 'spinbox' in widget_dict:
                # Check if it's float or int
                spinbox = widget_dict['spinbox']
                slider = widget_dict['slider']
                
                spinbox.blockSignals(True)
                slider.blockSignals(True)
                
                if isinstance(spinbox, QDoubleSpinBox):
                    # Float parameter
                    spinbox.setValue(float(value))
                    slider.setValue(int(float(value) * 100))
                else:
                    # Int parameter
                    spinbox.setValue(int(value))
                    slider.setValue(int(value))
                
                spinbox.blockSignals(False)
                slider.blockSignals(False)

    def clear_all_parameters(self):
        """Remove all parameter widgets from the layout"""
        print("[DEBUG] Clearing all parameter widgets")
        #print(f"[DEBUG] Widget count before clear: {self.params_layout.count()}")
        
        # Remove and delete all widgets
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.setParent(None)  # Remove from parent first
                widget.deleteLater()
        
        # Clear the dictionary
        self.param_widgets.clear()
        
        # Force process events to ensure widgets are deleted
        QApplication.processEvents()
        
        #print(f"[DEBUG] Widget count after clear: {self.params_layout.count()}")
        self.params_layout.addStretch()