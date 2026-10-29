"""Shared neutral-charcoal Studio palette and compact desktop controls."""
STUDIO_STYLE = '''
    QWidget { background: #25292e; color: #e6e9ec; font-size: 14px; }
    QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {
        background: #1c2125; border: 1px solid #49535b; border-radius: 4px; padding: 6px;
        selection-background-color: #ed8093; selection-color: #191c20;
    }
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { min-height: 20px; }
    QPushButton { border: 1px solid #49535b; padding: 7px 10px; border-radius: 4px; }
    QPushButton:hover, QToolButton:hover { background: #343d43; }
    QPushButton:checked { background: #264248; border-color: #36bbc3; }
    QPushButton[primary="true"] { background: #36bbc3; color: #172025; border-color: #36bbc3; }
    QPushButton[primary="true"]:hover { background: #5ad0d5; }
    QPushButton:disabled, QLabel:disabled { color: #7f898f; }
    QMenu { border: 1px solid #49535b; }
    QMenu::item { padding: 8px 24px; }
    QMenu::item:selected, QMenuBar::item:selected, QMenuBar::item:pressed { background: #354c50; }
    QMenu::item:disabled { color: #8c949a; }
    QToolBar { border: none; spacing: 5px; }
    QToolButton { padding: 6px; border-radius: 4px; }
    QCheckBox { spacing: 7px; }
    QSplitter::handle { background: #3d464d; width: 1px; }
    QGroupBox { border: 1px solid #49535b; margin-top: 12px; padding-top: 12px; }
    QGroupBox::title { subcontrol-origin: margin; left: 8px; }
    QTabWidget::pane { border: 0; }
    QWidget#workflowHeader { background: #23282d; border-bottom: 1px solid #3a434a; }
    QWidget#workflowSidebar { background: #22272c; border-right: 1px solid #3a434a; }
    QPushButton#workflowStep { text-align: left; border: 0; padding: 10px; }
    QPushButton#workflowStep:checked { background: #2c373d; border-left: 3px solid #36bbc3; }
    QLabel#workflowHeading { font-size: 24px; font-weight: 600; }
    QLabel#workflowProposal { color: #e2b352; }
    QScrollArea { border: 0; }
'''
