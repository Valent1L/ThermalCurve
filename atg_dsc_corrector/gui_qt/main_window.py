"""Fenêtre principale de la tranche verticale PySide6."""

from __future__ import annotations

from atg_dsc_corrector import APP_NAME, CONTACT, COPYRIGHT, LICENSE, __version__
from atg_dsc_corrector.i18n import language, tr as _t

from copy import deepcopy
from pathlib import Path
from typing import Callable

import numpy as np
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtCore import QEventLoop, QSettings, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from atg_dsc_corrector.analysis_zones import AnalysisZoneManager, axis_values
from atg_dsc_corrector.correction import CorrectionSettings
from atg_dsc_corrector.models import CorrectionResult, ExperimentData, unit_key
from atg_dsc_corrector.normalization import (
    HEAT_FLOW_REPRESENTATIONS,
    extract_initial_mass_mg,
)
from atg_dsc_corrector.comparison_exports import (
    ComparisonExportError,
    export_group_statistics,
    export_figure,
    export_visible_curves,
)
from atg_dsc_corrector.comparison import (
    COMPARISON_COLORS,
    ComparisonOptions,
    ComparisonPlot,
)
from atg_dsc_corrector.comparison_statistics import quantify_group_zone
from atg_dsc_corrector.plotting import CorrectionPlot, PlotOptions, x_values
from atg_dsc_corrector.projects import (
    ProjectError,
    ProjectOpenCancelled,
    ProjectValidationError,
    SourceFileRecord,
)

from .adapters import ProjectWorkflow
from .comparison_panel import ComparisonPanel, STAT_DISPLAY_LABELS
from .graph_settings_dialog import GraphSettingsDialog
from .normalization_panel import NormalizationPanel
from .periodic_table_dialog import PeriodicTableDialog
from .stoichiometry_dialog import StoichiometryDialog
from .theme import ThemedFigureCanvas, appearance_palette, apply_application_theme, line_icon, style_plot_toolbar
from .zones_panel import ZoneResultsDialog, ZonesPanel
from .workspace_widgets import FoldPanel, scroll_panel
from .settings import application_settings


FILE_FILTER = (
    _t('Données ATG / ATG-DSC (*.xls *.xlsx *.txt *.csv *.tsv);;Tous les fichiers (*)')
)

SIGNAL_LABELS = {
    "tg": "TG",
    "dtg": "dTG",
    "heat_flow": _t('Flux de chaleur'),
}

AXIS_LABELS = {
    "time_s": _t('Temps (s)'),
    "time_min": _t('Temps (min)'),
    "furnace_temperature": _t('Température du four'),
    "sample_temperature": _t("Température de l'échantillon"),
}

HEAT_FLOW_COLUMNS = {
    column for column, _label, _unit in HEAT_FLOW_REPRESENTATIONS.values()
}


def _has_source_heat_flow(experiment: ExperimentData | None) -> bool:
    if experiment is None or experiment.mapping.heat_flow is None:
        return False
    return experiment.mapping.heat_flow in experiment.data.columns


def _path_label() -> QLabel:
    label = QLabel(_t('Non chargé'))
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Preferred,
    )
    return label


class MainWindow(QMainWindow):
    """QMainWindow limitée au parcours fichier → correction → graphique."""

    def __init__(
        self,
        workflow: ProjectWorkflow | None = None,
        parent: QWidget | None = None,
        *,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._appearance_settings = (
            settings if settings is not None else application_settings()
        )
        self._appearance_settings.sync()
        self._last_messages = ""
        self._comparison_message_text = ""
        self._panels = {}
        self._panel_sizes = {"left": 260, "right": 300, "bottom": 150}
        self.interface_style = str(self._appearance_settings.value("appearance/style", "atelier"))
        self.color_theme = str(self._appearance_settings.value("appearance/theme", "light"))
        if self.interface_style not in {"atelier", "console"}:
            self.interface_style = "atelier"
        if self.color_theme not in {"light", "dark"}:
            self.color_theme = "light"
        self.workflow = workflow or ProjectWorkflow()
        self._restoring_project = False
        self.analysis_zones = AnalysisZoneManager(
            self.workflow.project_document.analysis_zones
        )
        selected_zone = self.workflow.project_document.display[
            "analysis_zone_selected_id"
        ]
        self._selected_zone_id = (
            selected_zone
            if selected_zone in {
                zone.identifier for zone in self.analysis_zones.zones
            }
            else None
        )
        self._zone_span_selector: SpanSelector | None = None
        self._zone_selection_panel: ZonesPanel | None = None
        self._comparison_curves = []
        self._comparison_statistics = []
        self._zone_results_context: str | None = None
        self._mode_context_keys: dict[str, tuple[int, ...] | None] = {
            "main": None,
            "comparison": None,
        }
        self._atg_dsc_modes = {"main": False, "comparison": False}
        self.setMinimumSize(900, 620)
        self.resize(1500, 900)

        self.figure = Figure(figsize=(9, 6), dpi=100, constrained_layout=True)
        self.canvas = ThemedFigureCanvas(self.figure)
        self.canvas.setObjectName("plotCanvas")
        self.plot = CorrectionPlot(self.figure)
        self.comparison_figure = Figure(figsize=(9, 6), dpi=100, constrained_layout=True)
        self.comparison_canvas = ThemedFigureCanvas(self.comparison_figure)
        self.comparison_canvas.setObjectName("comparisonPlotCanvas")
        self.comparison_plot = ComparisonPlot(self.comparison_figure)

        self._build_actions()
        self._build_window()
        self.set_appearance(self.interface_style, self.color_theme, persist=False)
        self._connect_signals()
        self._plot_key_connection = self.canvas.mpl_connect(
            "key_press_event", self._on_plot_key_press
        )
        self.comparison_canvas.mpl_connect("key_press_event", self._on_plot_key_press)
        self._set_tab_order()
        self._update_source_views()
        self._update_action_state()
        self._draw_placeholder()
        self._update_title()
        self.statusBar().showMessage(_t('Prêt'))

    def _build_actions(self) -> None:
        self.new_project_action = QAction(_t('Nouveau projet'), self)
        self.new_project_action.setShortcut(QKeySequence.StandardKey.New)
        self.open_project_action = QAction(_t('Ouvrir un projet…'), self)
        self.open_project_action.setShortcut(QKeySequence.StandardKey.Open)
        self.save_project_action = QAction(_t('Enregistrer'), self)
        self.save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_project_as_action = QAction(_t('Enregistrer sous…'), self)
        self.save_project_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.open_experiment_action = QAction(_t('Ajouter des expériences…'), self)
        self.open_blank_action = QAction(
            _t("Associer un fichier blanc à l'expérience active…"), self
        )
        self.open_blank_action.setShortcut(QKeySequence("Ctrl+B"))
        self.export_action = QAction(_t('Exporter le résultat…'), self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.quit_action = QAction(_t('Quitter'), self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.comparison_action = QAction(_t('Comparaison des expériences'), self)
        self.stoichiometry_action = QAction(_t('Calculs stœchiométriques…'), self)
        self.periodic_table_action = QAction(_t('Tableau périodique…'), self)
        self.graph_settings_action = QAction(_t('Paramètres du graphique…'), self)
        self.comparison_graph_settings_action = QAction(
            _t('Paramètres du graphique…'), self
        )

        menu = self.menuBar().addMenu(_t('&Fichier'))
        menu.addAction(self.new_project_action)
        menu.addAction(self.open_project_action)
        menu.addSeparator()
        menu.addAction(self.save_project_action)
        menu.addAction(self.save_project_as_action)
        menu.addSeparator()
        menu.addAction(self.open_experiment_action)
        menu.addAction(self.open_blank_action)
        menu.addSeparator()
        menu.addAction(self.export_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        self.menuBar().addAction(self.comparison_action)
        self.menuBar().addAction(self.stoichiometry_action)
        self.menuBar().addAction(self.periodic_table_action)
        self.options_menu = self.menuBar().addMenu(_t('&Options'))
        language_menu = self.options_menu.addMenu(_t('Langue'))
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        self.language_actions = {}
        requested_language = str(self._appearance_settings.value("interface/language", language()))
        if requested_language not in {"fr", "en"}:
            requested_language = language()
        for code, label in (("fr", "Français"), ("en", "English (Anglais)")):
            action = language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == requested_language)
            language_group.addAction(action)
            self.language_actions[code] = action
            action.triggered.connect(
                lambda checked, value=code: self.set_interface_language(value) if checked else None
            )
        language_menu.addSeparator()
        language_menu.addAction(_t('Appliqué au prochain lancement')).setEnabled(False)
        appearance = self.appearance_menu = self.options_menu.addMenu(_t('Apparence'))
        self.appearance_actions: dict[str, dict[str, QAction]] = {}
        for key, title, choices in (
            ("style", _t("Style d'interface"), (("atelier", _t('Atelier (A)')), ("console", _t('Console (C)')))),
            ("theme", _t('Thème'), (("light", _t('Clair')), ("dark", _t('Sombre')))),
        ):
            submenu = appearance.addMenu(title)
            group = QActionGroup(self)
            group.setExclusive(True)
            self.appearance_actions[key] = {}
            for value, label in choices:
                action = submenu.addAction(label)
                action.setCheckable(True)
                group.addAction(action)
                self.appearance_actions[key][value] = action
                action.triggered.connect(
                    lambda checked, k=key, v=value: self.set_appearance(
                        v if k == "style" else self.interface_style,
                        v if k == "theme" else self.color_theme,
                    ) if checked else None
                )

        self.about_action = self.menuBar().addAction(_t('À &propos'))
        self.about_action.triggered.connect(self.show_about)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            _t('À propos de {name}', name=APP_NAME),
            f"<h3>{APP_NAME}</h3>"
            f"<p>Version {__version__}<br>{COPYRIGHT}</p>"
            f"<p>{_t('Analyse de données ATG et ATG-DSC.')}</p>"
            f'<p><a href="https://polyformproject.org/licenses/noncommercial/1.0.0">{LICENSE}</a><br>'
            f"{_t('Utilisation non commerciale selon les termes de la licence.')}</p>"
            f"<p>{_t('Questions et propositions :')}<br>"
            f'<a href="mailto:{CONTACT}">{CONTACT}</a></p>'
            f"<p>{_t('Qt / PySide : © The Qt Company Ltd. et autres contributeurs. LGPL v3 ; textes GPL et LGPL dans les notices Qt.')}</p>"
            f"<p>{_t('Les composants tiers conservent leurs licences. Voir THIRD_PARTY_NOTICES.txt.')}</p>",
        )

    def set_interface_language(self, code: str) -> None:
        if code not in self.language_actions:
            raise ValueError(_t("Langue d'interface inconnue."))
        previous = self._appearance_settings.value("interface/language", language())
        self._appearance_settings.setValue("interface/language", code)
        self._appearance_settings.sync()
        if self._appearance_settings.status() != QSettings.Status.NoError:
            self.language_actions.get(str(previous), self.language_actions[language()]).setChecked(True)
            self._show_error(_t('Préférences non enregistrées'), OSError(_t("Impossible d'enregistrer la langue.")))
            return
        self.language_actions[code].setChecked(True)
        self.statusBar().showMessage(_t('Langue enregistrée. Fermez puis relancez l’application pour l’appliquer.'), 15000)

    def _build_window(self) -> None:
        self._build_comparison_window()
        self.stoichiometry_dialog = StoichiometryDialog(self.workflow, self)
        self.stoichiometry_dialog.project_changed.connect(self._stoichiometry_changed)
        self.periodic_table_dialog = PeriodicTableDialog(self)
        toolbar = QToolBar(_t('Projet'), self)
        toolbar.setObjectName("projectToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.interface_title = QLabel()
        self.interface_title.setObjectName("workspaceTitle")
        toolbar.addWidget(self.interface_title)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        for action, label, icon in (
            (self.open_experiment_action, _t('Importer'), "import"),
            (self.save_project_action, _t('Enregistrer'), "save"),
            (self.export_action, _t('Exporter'), "export"),
        ):
            action.setIconText(label)
            action.setIcon(line_icon(icon))
            toolbar.addAction(action)
        self.addToolBar(toolbar)
        self.appearance_label = QLabel()
        self.appearance_label.setProperty("secondary", True)
        self.statusBar().addPermanentWidget(self.appearance_label)
        self.messages_button = QToolButton()
        self.messages_button.setText(_t('Informations'))
        self.messages_button.setAccessibleName(_t('Consulter les informations et avertissements'))
        self.messages_button.clicked.connect(
            lambda: QMessageBox.information(self, _t('Informations'), self._last_messages or _t('Aucun message.'))
        )
        self.statusBar().addPermanentWidget(self.messages_button)
        splitter = self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._collapsible_panel("left", _t('Expériences'), self._build_left_panel()))
        inspector = self._build_inspector()
        splitter.addWidget(self._build_plot_panel())
        splitter.addWidget(self._collapsible_panel("right", _t('Réglages'), inspector))
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([250, 680, 350])
        self.setCentralWidget(splitter)
        self.zone_results_dialog = ZoneResultsDialog(self)

    def _collapsible_panel(self, key: str, title: str, content: QWidget) -> QWidget:
        frame = QWidget()
        frame.setObjectName(f"{key}Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QHBoxLayout()
        label = QLabel(title)
        label.setProperty("panelTitle", True)
        button = QToolButton()
        button.setObjectName(f"toggle{key.title()}Panel")
        button.setCheckable(True)
        button.setChecked(True)
        button.setIcon(line_icon("up"))
        button.setToolTip(_t('Masquer : {v1}', v1=title))
        button.setAccessibleName(_t('Masquer ou afficher : {v1}', v1=title))
        header.addWidget(label, 1)
        header.addWidget(button)
        layout.addLayout(header)
        layout.addWidget(content, 1)
        self._panels[key] = (frame, content, label, button)
        button.toggled.connect(lambda expanded, k=key: self._toggle_panel(k, expanded))
        return frame

    def _toggle_panel(self, key: str, expanded: bool) -> None:
        frame, content, label, button = self._panels[key]
        splitter = self.plot_splitter if key == "bottom" else self.main_splitter
        index = 1 if key == "bottom" else (0 if key == "left" else 2)
        sizes = splitter.sizes()
        if not expanded and sizes[index] > 32:
            self._panel_sizes[key] = sizes[index]
        content.setVisible(expanded)
        label.setVisible(expanded or key == "bottom")
        button.setIcon(line_icon("up" if expanded else "down"))
        button.setToolTip(f"{_t('Masquer') if expanded else _t('Afficher')} : {label.text()}")
        if key == "bottom":
            frame.setMaximumHeight(16777215 if expanded else 32)
        else:
            frame.setMaximumWidth(16777215 if expanded else 32)
        sizes[index] = self._panel_sizes[key] if expanded else 32
        center = 0 if key == "bottom" else 1
        total = splitter.height() if key == "bottom" else splitter.width()
        sizes[center] = max(1, total - sum(value for i, value in enumerate(sizes) if i != center))
        splitter.setSizes(sizes)

    def set_appearance(self, style: str, theme: str, *, persist: bool = True) -> None:
        tokens = appearance_palette(theme, style)
        style_changed = style != getattr(self, "_applied_style", None)
        self.interface_style, self.color_theme = style, theme
        apply_application_theme(QApplication.instance(), theme, style, set_font=False)
        for canvas in (self.canvas, self.comparison_canvas):
            canvas.screen_theme = tokens if theme == "dark" else None
            canvas.draw_idle()
        if style_changed:
            console = style == "console"
            table = self.zones_panel.zone_table
            if console:
                self.console_zone_layout.addWidget(table)
                for _, widget in self._zone_report_positions:
                    self.console_report_layout.addWidget(widget)
            else:
                self.zones_panel.layout().insertWidget(0, table)
                for position, widget in self._zone_report_positions:
                    self.zones_panel.layout().insertWidget(position, widget)
            table.show()
            for _, widget in self._zone_report_positions:
                widget.show()
            self.console_zone_group.setVisible(self._panels["bottom"][3].isChecked())
            self.zone_summary.setVisible(not console)
            self.zone_summary_layout.setStretch(0, 0 if console else 1)
            self.zone_summary_layout.setStretch(1, 1 if console else 0)
            self.zone_summary_layout.setStretch(2, 1 if console else 0)
            # Le graphique reçoit tout l'espace restant ; ne pas rouvrir un volet masqué.
            self.main_splitter.setSizes([
                self._panel_sizes["left"] if self._panels["left"][3].isChecked() else 32,
                max(700, self.width() - 560),
                self._panel_sizes["right"] if self._panels["right"][3].isChecked() else 32,
            ])
            self.plot_splitter.setSizes([max(500, self.height() - 220),
                                        150 if self._panels["bottom"][3].isChecked() else 32])
            for layout in (self.files_layout, self.preparation_layout, self.plot_layout):
                gap = 4 if console else 8
                layout.setSpacing(gap)
                layout.setContentsMargins(gap, gap, gap, gap)
            self.experiments_table.verticalHeader().setDefaultSectionSize(
                self.fontMetrics().height() * 2 + (8 if console else 24)
            )
            self._applied_style = style
            self._set_tab_order()
        for key, value in (("style", style), ("theme", theme)):
            self.appearance_actions[key][value].setChecked(True)
        self.appearance_label.setText(
            f"{_t('Atelier') if style == 'atelier' else _t('Console')} · "
            f"{_t('Clair') if theme == 'light' else _t('Sombre')}"
        )
        self.interface_title.setText(_t('Atelier scientifique') if style == "atelier" else _t("Console d'analyse"))
        self.comparison_style_title.setText(self.interface_title.text())
        self.comparison_panel.set_appearance(style)
        self.stoichiometry_dialog.set_appearance(style)
        self.experiments_table.setProperty("interfaceStyle", style)
        self.experiments_table.style().unpolish(self.experiments_table)
        self.experiments_table.style().polish(self.experiments_table)
        if persist:
            self._appearance_settings.setValue("appearance/style", style)
            self._appearance_settings.setValue("appearance/theme", theme)
            self._appearance_settings.sync()
            if self._appearance_settings.status() != QSettings.Status.NoError:
                QMessageBox.warning(self, _t('Préférences non enregistrées'),
                                    _t("Impossible d'enregistrer l'apparence dans :\n")
                                    + self._appearance_settings.fileName())

    def _build_comparison_window(self) -> None:
        self.comparison_dialog = QDialog(self)
        self.comparison_dialog.setWindowTitle(_t('Comparaison des résultats'))
        self.comparison_dialog.setModal(False)
        self.comparison_dialog.setWindowFlags(
            self.comparison_dialog.windowFlags()
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.comparison_dialog.setSizeGripEnabled(True)
        self.comparison_dialog.setMinimumSize(1000, 680)
        self.comparison_dialog.resize(1600, 1000)
        layout = QVBoxLayout(self.comparison_dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.comparison_style_title = QLabel()
        self.comparison_style_title.setObjectName("workspaceTitle")
        top.addWidget(self.comparison_style_title)
        top.addStretch(1)
        self.comparison_panel = ComparisonPanel(self.workflow)
        add = QPushButton(_t('Ajouter des essais'))
        add.setIcon(line_icon("add"))
        add.clicked.connect(self.comparison_panel.add_button.click)
        top.addWidget(add)
        top.addWidget(self.comparison_panel.export_bar)
        options = QToolButton()
        options.setText(_t('Options'))
        options.setIcon(line_icon("settings"))
        options.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        options.setMenu(self.options_menu)
        options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        top.addWidget(options)
        layout.addLayout(top)
        splitter = self.comparison_splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        content = QWidget()
        controls_layout = QVBoxLayout(content)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self._build_mode_selector("comparison"))
        controls_layout.addWidget(self.comparison_panel, 1)
        scroll = scroll_panel(content, "comparisonScrollArea")
        scroll.setMinimumWidth(330)
        left = FoldPanel(_t('Essais comparés'), scroll)
        splitter.addWidget(left)
        self.comparison_zones_panel = ZonesPanel(AXIS_LABELS)
        graph = QWidget()
        graph_layout = QVBoxLayout(graph)
        graph_layout.setContentsMargins(8, 4, 8, 4)
        self.comparison_axis_combo = QComboBox()
        for key, label in AXIS_LABELS.items():
            self.comparison_axis_combo.addItem(label, key)
        self.comparison_axis_combo.setAccessibleName(_t('Abscisse de comparaison'))
        graph_header = QHBoxLayout()
        graph_header.addStretch(1)
        graph_header.addWidget(self.comparison_axis_combo)
        graph_header.addWidget(self.comparison_panel.signal_bar)
        graph_layout.addLayout(graph_header)
        self.comparison_toolbar = NavigationToolbar2QT(self.comparison_canvas, graph)
        style_plot_toolbar(self.comparison_toolbar)
        self.comparison_toolbar.addSeparator()
        self.comparison_toolbar.addAction(self.comparison_graph_settings_action)
        graph_layout.addWidget(self.comparison_toolbar)
        graph_layout.addWidget(self.comparison_canvas, 1)
        self.comparison_messages_button = QToolButton()
        self.comparison_messages_button.setText(_t('Informations'))
        self.comparison_messages_button.clicked.connect(
            lambda: QMessageBox.information(self, _t('Comparaison : informations'),
                                           self._comparison_message_text or _t('Aucun message.'))
        )
        center = self.comparison_plot_splitter = QSplitter(Qt.Orientation.Vertical)
        center.setChildrenCollapsible(False)
        center.addWidget(graph)
        results = QWidget()
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(8, 4, 8, 4)
        self.comparison_results_table = QTableWidget(0, 6)
        self.comparison_results_table.setHorizontalHeaderLabels(
            (_t('Série'), _t('Zone'), _t('Début'), _t('Fin'), _t('Variation'), _t('Complément'))
        )
        self.comparison_results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.comparison_results_table.verticalHeader().hide()
        self.comparison_results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        results_layout.addWidget(self.comparison_results_table)
        results_layout.addWidget(self.comparison_zones_panel.all_results_button)
        bottom = FoldPanel(_t('Résultats des zones'), results, vertical=True, expanded_size=180)
        center.addWidget(bottom)
        center.setStretchFactor(0, 1)
        center.setSizes([760, 160])
        bottom.button.setChecked(False)
        splitter.addWidget(center)
        self.comparison_inspector = QTabWidget()
        self.comparison_inspector.addTab(scroll_panel(self.comparison_panel.display_group), _t('Affichage'))
        self.comparison_inspector.addTab(scroll_panel(self.comparison_zones_panel), _t('Zones'))
        self.comparison_inspector.addTab(scroll_panel(self.comparison_panel.statistics_group), _t('Statistiques'))
        right = FoldPanel(_t('Inspecteur'), self.comparison_inspector, expanded_size=320)
        splitter.addWidget(right)
        self.comparison_panels = {"left": left, "right": right, "bottom": bottom}
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 1050, 250])
        right.button.setChecked(False)
        layout.addWidget(splitter, 1)
        footer = QHBoxLayout()
        self.comparison_count_label = QLabel(_t('0 courbe visible'))
        footer.addWidget(self.comparison_count_label)
        footer.addStretch(1)
        footer.addWidget(self.comparison_messages_button)
        layout.addLayout(footer)
        self.comparison_dialog.finished.connect(self._cancel_graphical_zone_selection)
        controls = [
            self.comparison_atg_button,
            self.comparison_atg_dsc_button,
            *self.comparison_panel.tab_controls(),
            *self.comparison_zones_panel.tab_controls(),
            self.comparison_axis_combo,
        ]
        for first, second in zip(controls, controls[1:]):
            QWidget.setTabOrder(first, second)

    def _build_left_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("filesScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumWidth(180)

        content = QWidget()
        content.setObjectName("filesContent")
        layout = self.files_layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 14, 16, 18)
        layout.setSpacing(12)

        layout.addWidget(self._build_mode_selector("main"))
        layout.addWidget(self._build_files_group(), 1)
        provenance = QLabel(_t('Sources en lecture seule. Les résultats sont des données dérivées.'))
        provenance.setProperty("secondary", True)
        provenance.setWordWrap(True)
        layout.addWidget(provenance)
        scroll.setWidget(content)
        return scroll

    def _build_inspector(self) -> QTabWidget:
        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.setObjectName("inspectorTabs")
        self.inspector_tabs.setAccessibleName(_t("Préparation et zones d'analyse"))
        content = QWidget()
        content.setObjectName("controlsContent")
        layout = self.preparation_layout = QVBoxLayout(content)
        layout.addWidget(self._build_processing_group())
        self.normalization_panel = NormalizationPanel()
        self.normalization_panel.calculate_dtg_checkbox.setText(_t('Calculer dTG si absente'))
        self.normalization_panel.use_initial_mass_checkbox.setText(_t('Saisir m0 manuellement'))
        self.tg_representation_combo = self.normalization_panel.tg_combo
        self.dtg_representation_combo = self.normalization_panel.dtg_combo
        self.heat_flow_representation_combo = (
            self.normalization_panel.heat_flow_combo
        )
        self.initial_mass_entry = self.normalization_panel.initial_mass_entry
        self.reference_mass_entry = self.normalization_panel.reference_mass_entry
        self.reference_name_entry = self.normalization_panel.reference_name_entry
        layout.addWidget(self.normalization_panel)
        zero_group = QGroupBox(_t('Mise à zéro'))
        zero_layout = QVBoxLayout(zero_group)
        self.align_zeros_check = QCheckBox(_t('Aligner les zéros'))
        self.align_zeros_check.setAccessibleName(_t('Aligner les zéros des axes verticaux'))
        self.align_zeros_check.setToolTip(_t('Aligne visuellement les zéros des axes sans décaler les données.'))
        zero_layout.addWidget(self.align_zeros_check)
        layout.addWidget(zero_group)
        self.align_zeros_check.toggled.connect(self._set_main_zero_alignment)
        layout.addStretch(1)
        self.zones_panel = ZonesPanel(AXIS_LABELS)
        self._zone_report_positions = [
            (self.zones_panel.layout().indexOf(widget), widget)
            for widget in (
                self.zones_panel.findChild(QLabel, "zoneResultsLabel"),
                self.zones_panel.results,
                self.zones_panel.all_results_button,
            )
        ]
        for widget, title, name in (
            (content, _t('Préparation'), "controlsScrollArea"),
            (self.zones_panel, _t('Zones'), "zonesScrollArea"),
        ):
            scroll = QScrollArea()
            scroll.setObjectName(name)
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            # Les longues options défilent dans le volet au lieu d'agrandir la fenêtre.
            scroll.setMinimumWidth(240)
            self.inspector_tabs.addTab(scroll, title)
        return self.inspector_tabs

    def _build_mode_selector(self, context: str) -> QGroupBox:
        group = QGroupBox(_t('Parcours'))
        layout = QHBoxLayout(group)
        atg_button = QRadioButton("ATG")
        atg_dsc_button = QRadioButton("ATG-DSC")
        atg_button.setAccessibleName(_t('Afficher le parcours ATG'))
        atg_dsc_button.setAccessibleName(_t('Afficher le parcours ATG-DSC'))
        button_group = QButtonGroup(group)
        button_group.setExclusive(True)
        button_group.addButton(atg_button)
        button_group.addButton(atg_dsc_button)
        layout.addWidget(atg_button)
        layout.addWidget(atg_dsc_button)
        layout.addStretch(1)
        setattr(self, f"{context}_mode_group", button_group)
        setattr(self, f"{context}_atg_button", atg_button)
        setattr(self, f"{context}_atg_dsc_button", atg_dsc_button)
        atg_button.toggled.connect(
            lambda checked, selected=context: self._mode_selected(
                selected, False, checked
            )
        )
        atg_dsc_button.toggled.connect(
            lambda checked, selected=context: self._mode_selected(
                selected, True, checked
            )
        )
        return group

    def _build_files_group(self) -> QGroupBox:
        group = QGroupBox()
        group.setObjectName("filesGroup")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.experiments_table = QTableWidget(0, 2)
        self.experiments_table.setObjectName("mainExperimentsTable")
        self.experiments_table.setAccessibleName(_t('Expériences et blancs associés'))
        self.experiments_table.setHorizontalHeaderLabels([_t('Expérience'), _t('Blanc')])
        self.experiments_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.experiments_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.experiments_table.setColumnWidth(1, 65)
        self.experiments_table.verticalHeader().hide()
        self.experiments_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.experiments_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.experiments_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.experiments_table.setAlternatingRowColors(True)
        self.experiments_table.setMinimumHeight(130)
        self.experiments_table.setToolTip(_t("Cocher l'expérience active ; choisir son blanc dans la colonne associée."))
        self.experiment_path_label = _path_label()
        self.experiment_path_label.setObjectName("experimentPath")
        self.open_experiment_button = QPushButton(_t('+ Ajouter'))
        self.open_experiment_button.setAccessibleName(_t('Ajouter des expériences'))

        layout.addWidget(self.experiments_table, 1)
        layout.addWidget(self.open_experiment_button)
        layout.addWidget(self.experiment_path_label)
        return group

    def _build_processing_group(self) -> QGroupBox:
        group = QGroupBox(_t('Traitement'))
        layout = QFormLayout(group)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        layout.setVerticalSpacing(8)

        self.show_subtraction_check = QCheckBox(_t('Soustraire le blanc'))
        self.show_subtraction_check.setObjectName("showSubtractionCheck")
        self.show_subtraction_check.setChecked(True)
        layout.addRow(self.show_subtraction_check)

        self.process_button = QPushButton(_t('Traiter et afficher'))
        self.process_button.setObjectName("processButton")
        self.process_button.setProperty("primary", True)
        self.process_button.setAccessibleName(_t('Traiter et afficher les courbes'))
        layout.addRow(self.process_button)
        return group

    def _build_display_controls(self) -> QWidget:
        group = QWidget()
        layout = QHBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        self.display_stage_label = QLabel(_t('Aucune expérience'))
        self.display_stage_label.setObjectName("displayStage")
        layout.addWidget(self.display_stage_label)
        layout.addStretch(1)

        self.display_axis_combo = QComboBox()
        self.display_axis_combo.setObjectName("displayAxisCombo")
        self.display_axis_combo.setAccessibleName(_t("Axe d'affichage"))
        self.display_axis_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        for key, text in AXIS_LABELS.items():
            self.display_axis_combo.addItem(text, key)
        self.display_axis_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.display_axis_combo.setMinimumContentsLength(10)
        self.display_axis_combo.setToolTip(_t("Axe d'affichage"))
        layout.addWidget(self.display_axis_combo)

        signal_frame = QFrame()
        signal_layout = QHBoxLayout(signal_frame)
        signal_layout.setContentsMargins(0, 0, 0, 0)
        signal_layout.setSpacing(4)
        self.signal_checks: dict[str, QCheckBox] = {}
        for role, text in SIGNAL_LABELS.items():
            checkbox = QCheckBox(text)
            checkbox.setChecked(role in {"tg", "heat_flow"})
            self.signal_checks[role] = checkbox
            signal_layout.addWidget(checkbox)
        layout.addWidget(signal_frame)

        return group

    def _build_plot_panel(self) -> QWidget:
        self.plot_splitter = QSplitter(Qt.Orientation.Vertical)
        self.plot_splitter.setChildrenCollapsible(False)
        panel = QWidget()
        layout = self.plot_layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)
        layout.addWidget(self._build_display_controls())

        self.toolbar = NavigationToolbar2QT(self.canvas, panel)
        style_plot_toolbar(self.toolbar)
        self.toolbar.setObjectName("matplotlibToolbar")
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.graph_settings_action)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)

        self.plot_splitter.addWidget(panel)
        self.console_zone_group = QGroupBox()
        self.console_zone_group.setObjectName("zoneSummaryGroup")
        dock_layout = self.zone_summary_layout = QHBoxLayout(self.console_zone_group)
        dock_layout.setContentsMargins(8, 2, 8, 2)
        self.zone_summary = QLabel(_t('Sélectionnez une zone pour afficher ses résultats.'))
        self.zone_summary.setWordWrap(True)
        self.zone_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.zone_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dock_layout.addWidget(self.zone_summary, 1)
        self.console_zone_layout = QVBoxLayout()
        self.console_report_layout = QVBoxLayout()
        dock_layout.addLayout(self.console_zone_layout, 1)
        dock_layout.addLayout(self.console_report_layout, 1)
        self.zones_panel.results.setMinimumHeight(70)
        self.zones_panel.zone_table.setMinimumHeight(70)
        self.zones_panel.results.textChanged.connect(self._refresh_zone_summary)
        self.plot_splitter.addWidget(self._collapsible_panel("bottom", _t('Résultats des zones'), self.console_zone_group))
        self.plot_splitter.setStretchFactor(0, 1)
        self.plot_splitter.setStretchFactor(1, 0)
        return self.plot_splitter

    def _refresh_zone_summary(self) -> None:
        lines = self.zones_panel.results.toPlainText().splitlines()
        summary = [line.strip() for line in lines if line.startswith(_t('Axe :'))
                   or line.strip().startswith((_t('Variation dans la zone'), _t('Variation / m0')))]
        self.zone_summary.setText("\n".join([*lines[:1], *summary])
                                 or _t('Sélectionnez une zone pour afficher ses résultats.'))

    def _connect_signals(self) -> None:
        self.new_project_action.triggered.connect(self.new_project)
        self.open_project_action.triggered.connect(self.choose_project)
        self.save_project_action.triggered.connect(self.save_project)
        self.save_project_as_action.triggered.connect(self.save_project_as)
        self.open_experiment_action.triggered.connect(self.choose_experiment)
        self.open_blank_action.triggered.connect(self.choose_blank)
        self.export_action.triggered.connect(self.choose_export)
        self.quit_action.triggered.connect(self.close)
        self.comparison_action.triggered.connect(self.show_comparison_window)
        self.stoichiometry_action.triggered.connect(self.show_stoichiometry_window)
        self.periodic_table_action.triggered.connect(self.show_periodic_table_window)
        self.graph_settings_action.triggered.connect(
            lambda _checked=False: self._open_graph_settings(False)
        )
        self.comparison_graph_settings_action.triggered.connect(
            lambda _checked=False: self._open_graph_settings(True)
        )
        self.open_experiment_button.clicked.connect(self.choose_experiment)
        self.experiments_table.currentCellChanged.connect(
            lambda row, column, *_: column == 0
            and self._select_main_experiment(row)
        )
        self.experiments_table.itemChanged.connect(self._main_experiment_checked)
        self.comparison_panel.blank_button.clicked.connect(self.choose_comparison_blank)
        self.comparison_panel.add_button.clicked.connect(
            self.choose_comparison_experiments
        )
        self.comparison_panel.remove_button.clicked.connect(
            self._remove_comparison_experiments
        )
        self.comparison_panel.up_button.clicked.connect(
            lambda: self._move_comparison_experiment(-1)
        )
        self.comparison_panel.down_button.clicked.connect(
            lambda: self._move_comparison_experiment(1)
        )
        self.comparison_panel.changed.connect(self._comparison_changed)
        self.comparison_panel.auto_stack_requested.connect(
            self._auto_stack_comparison
        )
        self.comparison_panel.zero_offsets_requested.connect(
            self._zero_comparison_offsets
        )
        self.comparison_panel.active_row_changed.connect(
            self._activate_comparison_experiment
        )
        self.comparison_panel.export_data_requested.connect(
            self._export_comparison_data
        )
        self.comparison_panel.export_figure_requested.connect(
            self._export_comparison_figure
        )
        self.comparison_panel.export_statistics_requested.connect(
            self._export_comparison_statistics
        )
        self.display_axis_combo.currentIndexChanged.connect(self._sync_display_axis)
        self.comparison_axis_combo.currentIndexChanged.connect(
            lambda: self.display_axis_combo.setCurrentIndex(
                self.display_axis_combo.findData(self.comparison_axis_combo.currentData())
            )
        )
        for checkbox in self.signal_checks.values():
            checkbox.toggled.connect(self._sync_visible_signals)
        self.show_subtraction_check.toggled.connect(self._show_subtraction_changed)
        self.normalization_panel.changed.connect(self._normalization_changed)
        self.normalization_panel.pending_changed.connect(
            self._normalization_pending
        )
        for panel in (self.zones_panel, self.comparison_zones_panel):
            panel.add_button.clicked.connect(lambda checked=False, p=panel: self._add_analysis_zone(checked, panel=p))
            panel.update_button.clicked.connect(lambda checked=False, p=panel: self._update_analysis_zone(checked, panel=p))
            panel.delete_button.clicked.connect(lambda checked=False, p=panel: self._delete_analysis_zone(checked, panel=p))
            panel.graph_button.clicked.connect(lambda checked, p=panel: self._toggle_graphical_zone_selection(checked, panel=p))
            panel.active_zone_changed.connect(self._on_active_analysis_zone_changed)
        self.zones_panel.show_all_results_requested.connect(
            lambda: self._show_all_zone_results("main")
        )
        self.comparison_zones_panel.show_all_results_requested.connect(
            lambda: self._show_all_zone_results("comparison")
        )
        self.process_button.clicked.connect(self.process_current)

    def _set_tab_order(self) -> None:
        zone_controls = self.zones_panel.tab_controls()
        dock_controls = []
        if self.interface_style == "console":
            dock_controls = [self.zones_panel.zone_table, self.zones_panel.results,
                             self.zones_panel.all_results_button]
            zone_controls = [widget for widget in zone_controls if widget not in dock_controls]
        controls = [
            self.main_atg_button,
            self.main_atg_dsc_button,
            self.experiments_table,
            self.open_experiment_button,
            self.display_axis_combo,
            *self.signal_checks.values(),
            *dock_controls,
            self.inspector_tabs.tabBar(),
            self.show_subtraction_check,
            self.process_button,
            *self.normalization_panel.tab_controls(),
            *zone_controls,
        ]
        for first, second in zip(controls, controls[1:]):
            QWidget.setTabOrder(first, second)

    def new_project(self, _checked: bool = False) -> bool:
        if not self._confirm_unsaved_changes():
            return False
        self.workflow.new_project()
        self._restore_project_state()
        self._draw_placeholder()
        self._set_messages([_t('Nouveau projet créé.')])
        self.statusBar().showMessage(_t('Nouveau projet'), 5000)
        self._update_action_state()
        self._update_title()
        return True

    def choose_project(self, _checked: bool = False) -> bool:
        if not self._confirm_unsaved_changes():
            return False
        path, _ = QFileDialog.getOpenFileName(
            self,
            _t('Ouvrir un projet ATG-DSC'),
            "",
            _t('Projet ATG-DSC (*.atgproj);;Tous les fichiers (*)'),
        )
        if not path:
            return False
        return self.open_project_path(path, confirm_unsaved=False)

    def open_project_path(
        self,
        path: str | Path,
        *,
        confirm_unsaved: bool = True,
    ) -> bool:
        if confirm_unsaved and not self._confirm_unsaved_changes():
            return False
        self.statusBar().showMessage(_t('Ouverture du projet…'))
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            state = self.workflow.open_project(
                path,
                missing_handler=self._missing_source_handler,
                modified_handler=self._modified_source_handler,
            )
        except ProjectOpenCancelled:
            self.statusBar().showMessage(_t('Ouverture annulée'), 5000)
            return False
        except (ProjectValidationError, ProjectError, OSError, ValueError) as exc:
            self._show_error(_t('Projet invalide ou incompatible'), exc)
            return False
        finally:
            QApplication.restoreOverrideCursor()

        self._restore_project_state()
        result = None
        if self.workflow.experiment is not None:
            result = self.process_current(mark_normalization_dirty=False)
        else:
            self._draw_placeholder()
        messages = [_t('Projet ouvert : {v1}', v1=Path(path).name), *state.warnings]
        if result is not None:
            messages.extend(result.warnings)
        self._set_messages(messages)
        self.statusBar().showMessage(_t('Projet ouvert'), 5000)
        self._update_action_state()
        self._update_title()
        return True

    def save_project(self, _checked: bool = False) -> bool:
        if self.workflow.project_path is None:
            return self.save_project_as()
        return self.save_project_path(self.workflow.project_path)

    def save_project_as(self, _checked: bool = False) -> bool:
        initial_name = (
            self.workflow.project_path.name
            if self.workflow.project_path is not None
            else f"{self.workflow.project_document.project_name}.atgproj"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            _t('Enregistrer le projet'),
            initial_name,
            _t('Projet ATG-DSC (*.atgproj)'),
        )
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".atgproj":
            target = target.with_suffix(".atgproj")
        return self.save_project_path(target)

    def save_project_path(self, path: str | Path) -> bool:
        try:
            self.workflow.save_project(
                path,
                visible_signals=self._checked_signals(),
                modified_handler=self._modified_source_save_handler,
            )
        except ProjectOpenCancelled:
            self.statusBar().showMessage(_t('Enregistrement annulé'), 5000)
            return False
        except (ProjectError, OSError, ValueError) as exc:
            self._show_error(_t('Enregistrement impossible'), exc)
            return False
        self._set_messages([_t('Projet enregistré : {v1}', v1=Path(path))])
        self.statusBar().showMessage(_t('Projet enregistré'), 5000)
        self._update_action_state()
        self._update_title()
        return True

    def _confirm_unsaved_changes(self) -> bool:
        if not self.workflow.project_dirty:
            return True
        answer = QMessageBox.question(
            self,
            _t('Projet modifié'),
            _t("Le projet contient des changements non enregistrés.\n\nVoulez-vous l'enregistrer avant de continuer ?"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return answer == QMessageBox.StandardButton.Discard

    def _restore_project_state(self) -> None:
        self._comparison_curves = []
        self._comparison_statistics = []
        self.comparison_plot.draw([], ComparisonOptions())
        self.comparison_canvas.draw_idle()
        self._restoring_project = True
        try:
            display_axis = self.workflow.project_document.display["x_axis"]
            axis_index = self.display_axis_combo.findData(display_axis)
            self.display_axis_combo.setCurrentIndex(max(0, axis_index))
            visible = set(
                self.workflow.project_document.display["visible_signals"]
            )
            for role, checkbox in self.signal_checks.items():
                checkbox.setChecked(role in visible)
            self.show_subtraction_check.setChecked(
                bool(self.workflow.project_document.display["show_subtraction"])
            )
            normalization = self.workflow.project_document.normalization
            if self.workflow.experiment is not None:
                normalization = self.workflow._normalization_overrides.get(
                    id(self.workflow.experiment), normalization
                )
            initial_mass_mg, mass_source = self._active_initial_mass_context()
            self.normalization_panel.restore(
                normalization,
                manual_mass_mg=(
                    None
                    if self.workflow.experiment is None
                    else self.workflow._normalization_records.get(
                        id(self.workflow.experiment), {}
                    ).get("manual_mass_mg")
                ),
                initial_mass_mg=initial_mass_mg,
                mass_source=mass_source,
                experiment_loaded=self.workflow.experiment is not None,
            )
            self.analysis_zones.replace(
                self.workflow.project_document.analysis_zones
            )
            selected_zone = self.workflow.project_document.display[
                "analysis_zone_selected_id"
            ]
            self._selected_zone_id = (
                selected_zone
                if selected_zone in {
                    zone.identifier for zone in self.analysis_zones.zones
                }
                else None
            )
        finally:
            self._restoring_project = False
        self.comparison_panel.model.refresh()
        self.comparison_panel.restore(self.workflow.project_document.comparison)
        self.stoichiometry_dialog.restore_project_state()
        self.comparison_axis_combo.blockSignals(True)
        self.comparison_axis_combo.setCurrentIndex(self.comparison_axis_combo.findData(self.workflow.display_axis))
        self.comparison_axis_combo.blockSignals(False)
        self._update_source_views()
        self._refresh_zones_panel()

    def _mode_context_experiments(self, context: str) -> tuple[ExperimentData, ...]:
        if context == "main":
            return (() if self.workflow.experiment is None else (self.workflow.experiment,))
        return tuple(
            experiment
            for row, experiment in enumerate(self.workflow.experiments)
            if (
                self.workflow.comparison_record(row)["selected"]
                and self.workflow.comparison_record(row)["visible"]
            )
        )

    def _sync_interface_mode(self, context: str) -> None:
        experiments = self._mode_context_experiments(context)
        key = tuple(id(experiment) for experiment in experiments)
        has_heat_flow = any(_has_source_heat_flow(item) for item in experiments)
        if self._mode_context_keys[context] != key:
            self._mode_context_keys[context] = key
            self._atg_dsc_modes[context] = has_heat_flow
        atg_button = getattr(self, f"{context}_atg_button")
        atg_dsc_button = getattr(self, f"{context}_atg_dsc_button")
        enabled = bool(experiments)
        with QSignalBlocker(atg_button), QSignalBlocker(atg_dsc_button):
            atg_button.setChecked(not self._atg_dsc_modes[context])
            atg_dsc_button.setChecked(self._atg_dsc_modes[context])
        atg_button.setEnabled(enabled)
        atg_dsc_button.setEnabled(enabled and has_heat_flow)
        self._apply_interface_mode(context)

    def _apply_interface_mode(self, context: str) -> None:
        heat_flow_visible = self._atg_dsc_modes[context]
        if context == "main":
            self.signal_checks["heat_flow"].setVisible(heat_flow_visible)
            self.normalization_panel.set_heat_flow_visible(heat_flow_visible)
            self.zones_panel.set_heat_flow_visible(heat_flow_visible)
        else:
            self.comparison_panel.set_heat_flow_visible(heat_flow_visible)
            self.comparison_zones_panel.set_heat_flow_visible(heat_flow_visible)

    def _mode_selected(self, context: str, atg_dsc: bool, checked: bool) -> None:
        if not checked:
            return
        experiments = self._mode_context_experiments(context)
        if atg_dsc and not any(_has_source_heat_flow(item) for item in experiments):
            return
        self._atg_dsc_modes[context] = atg_dsc
        self._mode_context_keys[context] = tuple(id(item) for item in experiments)
        self._apply_interface_mode(context)
        if context == "main":
            if self.workflow.result is not None and self._visible_signals():
                self._draw_result(self.workflow.result)
            else:
                self._draw_placeholder(main_only=True)
        else:
            self._draw_comparison()
        self._update_action_state()

    def _checked_signals(self) -> tuple[str, ...]:
        return tuple(
            role
            for role, checkbox in self.signal_checks.items()
            if checkbox.isChecked()
        )

    def _visible_signals(self) -> tuple[str, ...]:
        return tuple(
            role
            for role in self._checked_signals()
            if role != "heat_flow" or self._atg_dsc_modes["main"]
        )

    def _open_graph_settings(self, comparison: bool) -> None:
        if comparison:
            settings = self.workflow.project_document.comparison
            signals = self.comparison_panel.selected_signals()
            rows = self.comparison_panel.selected_rows()
            selected_curves = []
            for row in rows:
                experiment = self.workflow.experiments[row]
                identifier = self.workflow.comparison_key(experiment)
                record = deepcopy(self.workflow.comparison_record(row))
                record["color"] = settings["colors"].get(
                    identifier,
                    COMPARISON_COLORS[row % len(COMPARISON_COLORS)],
                )
                selected_curves.append(record)
            alignment_mode = "zeros" if settings["align_zeros"] else "none"
            show_offsets = bool(settings["show_offsets_in_legend"])
        else:
            settings = self.workflow.project_document.display
            signals = self._visible_signals()
            rows = []
            selected_curves = []
            alignment_mode = str(settings["alignment_mode"])
            show_offsets = False
        dialog = GraphSettingsDialog(
            graph=settings["graph"],
            limits=settings["limits"],
            signals=signals,
            alignment_mode=alignment_mode,
            comparison=comparison,
            show_offsets_in_legend=show_offsets,
            selected_curves=selected_curves,
            apply_callback=lambda values: self._apply_graph_settings(
                comparison, rows, values
            ),
            parent=self.comparison_dialog if comparison else self,
        )
        self._graph_settings_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._graph_settings_dialog = None

    def _apply_graph_settings(
        self,
        comparison: bool,
        rows: list[int],
        values: dict[str, object],
    ) -> None:
        previous_dirty = self.workflow.project_dirty
        if comparison:
            previous = deepcopy(self.workflow.project_document.comparison)
            try:
                self.workflow.set_comparison_graph_settings(
                    graph=values["graph"],
                    limits=values["limits"],
                    align_zeros=values["alignment_mode"] == "zeros",
                    show_offsets_in_legend=values["show_offsets_in_legend"],
                    rows=rows,
                    curve_changes=values["curve_changes"],
                )
                self.comparison_panel.model.refresh()
                self._draw_comparison(propagate_errors=True)
            except (OSError, ValueError) as exc:
                self.workflow.project_document.comparison = previous
                self.workflow.project_dirty = previous_dirty
                self.comparison_panel.model.refresh()
                self._draw_comparison()
                raise ValueError(_t(str(exc))) from exc
        else:
            previous = deepcopy(self.workflow.project_document.display)
            try:
                self.workflow.set_main_graph_settings(
                    graph=values["graph"],
                    limits=values["limits"],
                    alignment_mode=str(values["alignment_mode"]),
                )
                if self.workflow.result is not None:
                    self._draw_result(self.workflow.result)
            except ValueError as exc:
                self.workflow.project_document.display = previous
                self.workflow.project_dirty = previous_dirty
                if self.workflow.result is not None:
                    self._draw_result(self.workflow.result)
                raise ValueError(_t(str(exc))) from exc
        self._update_action_state()
        self._update_title()

    def _set_main_zero_alignment(self, enabled: bool) -> None:
        if self._restoring_project:
            return
        self.workflow.set_align_zeros(enabled)
        if self.workflow.result is not None:
            self._draw_result(self.workflow.result)
        self._update_action_state()
        self._update_title()

    def _update_title(self) -> None:
        marker = "*" if self.workflow.project_dirty else ""
        self.setWindowTitle(
            f"{self.workflow.project_document.project_name}{marker} — "
            f"{APP_NAME}"
        )

    def choose_experiment(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            _t('Ajouter des expériences ATG ou ATG-DSC'),
            "",
            FILE_FILTER,
        )
        for path in paths:
            self.load_experiment_path(path)

    def choose_blank(self) -> None:
        if self.workflow.experiment is None:
            return
        row = self.workflow.experiments.index(self.workflow.experiment)
        self._choose_blank_for_row(row)

    def _choose_blank_for_row(self, row: int) -> None:
        if not 0 <= row < len(self.workflow.experiments):
            return
        experiment = self.workflow.experiments[row]
        path, _ = QFileDialog.getOpenFileName(
            self,
            _t('Associer un blanc à {v1}', v1=experiment.source_path.name),
            "",
            FILE_FILTER,
        )
        if path:
            self._load_blank_for_row(path, row)

    def choose_comparison_blank(self) -> None:
        rows = self.comparison_panel.selected_rows()
        if not rows:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, _t('Associer un blanc aux expériences sélectionnées'), "", FILE_FILTER
        )
        if not path:
            return
        blank = self._load_source(
            path,
            lambda selected: self.workflow.open_comparison_blank(selected, rows),
            _t('Blanc associé'),
        )
        if blank is not None:
            self.comparison_panel.model.refresh()
            self.process_current()

    def _select_main_experiment(self, row: int) -> None:
        if not 0 <= row < len(self.workflow.experiments):
            return
        if self.workflow.experiments[row] is not self.workflow.experiment:
            self._activate_comparison_experiment(row)

    def _main_experiment_checked(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._select_main_experiment(item.row())
        else:
            # La sélection est exclusive : décocher la ligne active la conserve.
            with QSignalBlocker(self.experiments_table):
                item.setCheckState(
                    Qt.CheckState.Checked
                    if self.workflow.experiments[item.row()] is self.workflow.experiment
                    else Qt.CheckState.Unchecked
                )

    def _assign_blank_to_row(
        self, row: int, blank: ExperimentData | None
    ) -> None:
        if not 0 <= row < len(self.workflow.experiments):
            return
        current = self.workflow.comparison_blank(row)
        if current is blank or (
            current is not None
            and blank is not None
            and current.source_path.resolve() == blank.source_path.resolve()
        ):
            return
        active = self.workflow.experiments[row] is self.workflow.experiment
        self.workflow.assign_blank_to_comparison([row], blank)
        self.comparison_panel.model.refresh()
        self._update_source_views()
        if active:
            self._draw_placeholder(main_only=True)
            self.process_current()
        self._update_action_state()
        self._update_title()

    def choose_comparison_experiments(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            _t('Ajouter des expériences à la comparaison'),
            "",
            FILE_FILTER,
        )
        for path in paths:
            self._load_source(
                path,
                self.workflow.add_comparison_experiment,
                _t('Expérience ajoutée'),
            )
        if paths:
            self.comparison_panel.model.refresh()
            self.comparison_panel.select_row(len(self.workflow.experiments) - 1)
            self._comparison_changed()

    def _remove_comparison_experiments(self) -> None:
        rows = self.comparison_panel.selected_rows()
        if not rows:
            return
        self.workflow.remove_comparison_experiments(rows)
        self.comparison_panel.model.refresh()
        if self.workflow.experiments:
            row = min(rows[0], len(self.workflow.experiments) - 1)
            self.comparison_panel.select_row(row)
            self._comparison_changed()
        else:
            self._draw_placeholder()
        self._update_source_views()
        self._update_action_state()
        self._update_title()

    def _move_comparison_experiment(self, delta: int) -> None:
        rows = self.comparison_panel.selected_rows()
        if len(rows) != 1:
            return
        target = self.workflow.move_comparison_experiment(rows[0], delta)
        self.comparison_panel.model.refresh()
        self.comparison_panel.select_row(target)
        self._comparison_changed()

    def _activate_comparison_experiment(self, row: int) -> None:
        self.workflow.activate_comparison_experiment(row)
        self._restoring_project = True
        try:
            settings = self.workflow._normalization_overrides.get(
                id(self.workflow.experiment),
                self.workflow.project_document.normalization,
            )
            initial_mass_mg, mass_source = self._active_initial_mass_context()
            self.normalization_panel.restore(
                settings,
                manual_mass_mg=self.workflow._normalization_records.get(
                    id(self.workflow.experiment), {}
                ).get("manual_mass_mg"),
                initial_mass_mg=initial_mass_mg,
                mass_source=mass_source,
                experiment_loaded=True,
            )
        finally:
            self._restoring_project = False
        self._update_source_views()
        self._update_action_state()
        self._draw_placeholder(main_only=True)
        self.process_current(mark_normalization_dirty=False)

    def _active_initial_mass_context(self) -> tuple[float | None, str | None]:
        experiment = self.workflow.experiment
        if experiment is None:
            return None, None
        record = self.workflow._normalization_records.get(id(experiment), {})
        try:
            metadata_mass = extract_initial_mass_mg(experiment)
        except ValueError:
            return None, "invalid"
        if metadata_mass is not None:
            return metadata_mass, "metadata"
        if record.get("mass_source") == "legacy" and record.get("m0_mg") is not None:
            try:
                return float(record["m0_mg"]), "legacy"
            except (TypeError, ValueError):
                return None, "invalid"
        return None, "absent"

    def load_experiment_path(self, path: str | Path) -> ExperimentData | None:
        for row, experiment in enumerate(self.workflow.experiments):
            if experiment.source_path.resolve() == Path(path).resolve():
                self._activate_comparison_experiment(row)
                return experiment
        data = self._load_source(
            path,
            lambda selected: self.workflow.add_comparison_experiment(selected, inherit_blank=False),
            _t('Expérience ajoutée'),
        )
        self.comparison_panel.model.refresh()
        if data is not None:
            self._activate_comparison_experiment(len(self.workflow.experiments) - 1)
        return data

    def load_blank_path(self, path: str | Path) -> ExperimentData | None:
        if self.workflow.experiment is None:
            return None
        row = self.workflow.experiments.index(self.workflow.experiment)
        return self._load_blank_for_row(path, row)

    def _load_blank_for_row(
        self, path: str | Path, row: int
    ) -> ExperimentData | None:
        if not 0 <= row < len(self.workflow.experiments):
            return None
        active = self.workflow.experiments[row] is self.workflow.experiment
        blank = self._load_source(
            path,
            lambda selected: self.workflow.open_comparison_blank(selected, [row]),
            _t('Blanc associé'),
            draw_placeholder=active,
        )
        if blank is not None:
            self.comparison_panel.model.refresh()
            if active:
                self.process_current()
        return blank

    def show_comparison_window(self, _checked: bool = False) -> None:
        self._draw_comparison()
        self.comparison_dialog.show()
        self.comparison_dialog.raise_()
        self.comparison_dialog.activateWindow()

    def show_stoichiometry_window(self, _checked: bool = False) -> None:
        self.stoichiometry_dialog.setWindowState(
            self.stoichiometry_dialog.windowState() & ~Qt.WindowState.WindowMinimized
        )
        self.stoichiometry_dialog.show()
        self.stoichiometry_dialog.raise_()
        self.stoichiometry_dialog.activateWindow()

    def show_periodic_table_window(self, _checked: bool = False) -> None:
        self.periodic_table_dialog.setWindowState(
            self.periodic_table_dialog.windowState() & ~Qt.WindowState.WindowMinimized
        )
        self.periodic_table_dialog.show()
        self.periodic_table_dialog.raise_()
        self.periodic_table_dialog.activateWindow()

    def _stoichiometry_changed(self) -> None:
        self._update_action_state()
        self._update_title()

    def _show_subtraction_changed(self, checked: bool) -> None:
        if self._restoring_project:
            return
        self.workflow.set_show_subtraction(checked)
        if self.workflow.experiment is not None:
            self.process_current()
        self._update_title()

    def _sync_display_axis(self, _index: int = -1) -> None:
        if self._restoring_project:
            return
        self.workflow.set_axes(
            display_axis=str(self.display_axis_combo.currentData()),
        )
        if self.workflow.result is not None:
            self._draw_result(self.workflow.result)
        else:
            self._refresh_zones_panel()
        self.comparison_axis_combo.blockSignals(True)
        self.comparison_axis_combo.setCurrentIndex(self.comparison_axis_combo.findData(self.workflow.display_axis))
        self.comparison_axis_combo.blockSignals(False)
        self._draw_comparison()
        self._update_action_state()
        self._update_title()

    def _sync_visible_signals(self, _checked: bool = False) -> None:
        if self._restoring_project:
            return
        signals = self._visible_signals()
        self.workflow.set_visible_signals(self._checked_signals())
        if self.workflow.result is not None and signals:
            self._draw_result(self.workflow.result)
        elif self.workflow.result is not None:
            self._draw_placeholder(main_only=True)
        self._update_action_state()
        self._update_title()

    def _normalization_changed(self) -> None:
        if self._restoring_project:
            return
        self.workflow.mark_dirty()
        try:
            settings, manual_mass = self.normalization_panel.values()
        except ValueError as exc:
            self._invalidate_normalization_result(_t(str(exc)))
            return
        try:
            result = self.workflow.set_normalization(settings, manual_mass)
        except ValueError as exc:
            self._invalidate_normalization_result(_t(str(exc)))
            return
        self.normalization_panel.clear_validation()
        if result is not None:
            self._draw_result(result)
            self._draw_comparison()
        self._update_action_state()
        self._update_title()

    def _normalization_pending(self) -> None:
        if self._restoring_project:
            return
        self.workflow.mark_dirty()
        self._invalidate_normalization_result(
            _t('Paramètres modifiés : validez la saisie pour recalculer.')
        )

    def _invalidate_normalization_result(self, message: str) -> None:
        if self.workflow.result is not None:
            self.workflow.result = None
            self._draw_placeholder(main_only=True)
        self.normalization_panel.show_validation(message)
        self._update_action_state()
        self._update_title()

    def _load_source(
        self,
        path: str | Path,
        loader: Callable[[str | Path], ExperimentData],
        success_message: str,
        *,
        draw_placeholder: bool = True,
    ) -> ExperimentData | None:
        self.statusBar().showMessage(_t('Chargement en cours…'))
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            data = loader(path)
        except (OSError, ValueError) as exc:
            self._show_error(_t('Chargement impossible'), exc)
            return None
        finally:
            QApplication.restoreOverrideCursor()

        self._update_source_views()
        self._update_action_state()
        self._update_title()
        if draw_placeholder:
            self._draw_placeholder()
        messages = [f"{success_message} : {data.source_path.name}"]
        messages.extend(data.warnings)
        self._set_messages(messages)
        self.statusBar().showMessage(success_message, 5000)
        return data

    def _comparison_changed(self) -> None:
        if self._restoring_project:
            return
        self._draw_comparison()
        self._update_action_state()
        self._update_title()

    def _auto_stack_comparison(self) -> None:
        signals = self.comparison_panel.selected_signals()
        if not signals:
            self.comparison_panel.show_validation(
                _t('Sélectionnez au moins une courbe visible dans ce parcours.')
            )
            return
        try:
            options, curves, warnings = self.workflow.comparison_plot_data(
                signals=signals,
                x_axis=self.workflow.display_axis,
                persist_signals=False,
            )
            offsets = ComparisonPlot.automatic_offsets(curves, options)
            if not offsets:
                self._set_messages(
                    [*warnings, _t('Aucune courbe compatible à empiler.')]
                )
                return
            self.workflow.set_comparison_offsets(offsets)
        except (OSError, ValueError) as exc:
            self.comparison_panel.show_validation(_t(str(exc)))
            return
        self.comparison_panel.clear_validation()
        self.comparison_panel.model.refresh()
        self._comparison_changed()

    def _zero_comparison_offsets(self) -> None:
        self.workflow.set_comparison_offsets(
            {
                self.workflow.comparison_key(experiment): 0.0
                for experiment in self.workflow.experiments
            }
        )
        self.comparison_panel.model.refresh()
        self._comparison_changed()

    def _render_comparison(self, options, curves):
        options.plot_options.analysis_zones = self.analysis_zones.zones
        options.plot_options.selected_analysis_zone_id = self._selected_zone_id
        statistics_settings = self.workflow.project_document.comparison["statistics"]
        if statistics_settings["enabled"]:
            statistics = self.workflow.comparison_statistics_data(curves, options)
            self.comparison_plot.draw_statistics(
                curves,
                options,
                statistics,
                statistics_settings["display_mode"],
            )
            self.comparison_panel.set_statistics_summary(statistics)
            self.comparison_plot.draw_zones(
                curves, options,
                show_heat_surfaces=statistics_settings["display_mode"] in {"individual", "mean_individual"},
            )
            return statistics
        self.comparison_plot.draw(curves, options)
        self.comparison_plot.draw_zones(curves, options)
        self.comparison_panel.set_statistics_summary([])
        return []
    def _draw_comparison(self, *, propagate_errors: bool = False) -> None:
        self._comparison_statistics = []
        self._cancel_graphical_zone_selection()
        self._sync_interface_mode("comparison")
        signals = self.comparison_panel.selected_signals()
        if not signals:
            message = _t('Sélectionnez au moins une courbe visible dans ce parcours.')
            self._set_comparison_messages(message)
            self._comparison_curves = []
            self.comparison_plot.draw(
                [],
                ComparisonOptions(
                    graph_settings=self.workflow.project_document.comparison[
                        "graph"
                    ]
                ),
            )
            self.comparison_canvas.draw_idle()
            self._refresh_zones_panel()
            return
        try:
            options, curves, warnings = self.workflow.comparison_plot_data(
                signals=signals,
                x_axis=self.workflow.display_axis,
                persist_signals=False,
            )
            self._comparison_curves = curves
            self._comparison_statistics = self._render_comparison(options, curves)
        except (OSError, ValueError) as exc:
            if propagate_errors:
                raise
            self._set_messages([_t(str(exc))])
            self._set_comparison_messages(_t(str(exc)))
            self._comparison_curves = []
            self.comparison_plot.draw(
                [],
                ComparisonOptions(
                    graph_settings=self.workflow.project_document.comparison[
                        "graph"
                    ]
                ),
            )
            self.comparison_canvas.draw_idle()
            self._refresh_zones_panel()
            return
        self.workflow.project_document.comparison["colors"] = dict(
            self.comparison_plot.colors
        )
        self.comparison_canvas.draw_idle()
        messages = [*warnings, *self.comparison_plot.warnings]
        if messages:
            self._set_messages(messages)
        self._set_comparison_messages("\n".join(messages))
        self._refresh_zones_panel()

    def _comparison_export_payload(self):
        signals = self.comparison_panel.selected_signals()
        if not signals:
            QMessageBox.information(
                self,
                _t('Export de comparaison'),
                _t('Sélectionnez au moins une courbe visible dans ce parcours.'),
            )
            return None
        try:
            options, curves, warnings = self.workflow.comparison_plot_data(
                signals=signals,
                x_axis=self.workflow.display_axis,
                persist_signals=False,
            )
        except (OSError, ValueError) as exc:
            self._show_error(_t('Export de comparaison impossible'), exc)
            return None
        compatible = False
        for signal in options.signals:
            for curve in curves:
                if not curve.visible:
                    continue
                plot_options = curve.plot_options or options.plot_options
                if ComparisonPlot._admitted_signal(
                    curve, plot_options, signal
                )[0] is not None:
                    compatible = True
                    break
            if compatible:
                break
        if not compatible:
            QMessageBox.information(
                self,
                _t('Export de comparaison'),
                _t("Aucune courbe visible compatible avec les signaux et l'axe demandés."),
            )
            return None
        return options, curves, warnings

    def _export_comparison_data(self) -> None:
        payload = self._comparison_export_payload()
        if payload is None:
            return
        options, curves, warnings = payload
        if self.workflow.experiments:
            source = self.workflow.experiments[0].source_path
            default_path = source.with_name(f"{source.stem}_comparaison.csv")
        else:
            default_path = Path("comparaison.csv")
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            _t('Exporter les séries tracées'),
            str(default_path),
            _t('CSV (*.csv);;TSV (*.tsv);;Tous les fichiers (*)'),
        )
        if not destination:
            return
        requested = Path(destination)
        kind = (
            "tsv"
            if requested.suffix.lower() == ".tsv" or selected_filter.startswith("TSV")
            else "csv"
        )
        target = requested.with_suffix(f".{kind}")
        metadata = target.with_suffix(".json")
        if not self._confirm_comparison_overwrite([target, metadata]):
            return
        try:
            settings = self.workflow.project_document.comparison["statistics"]
            statistics = (
                self.workflow.comparison_statistics_data(curves, options)
                if settings["enabled"] else []
            )
            data_path, json_path = export_visible_curves(
                curves,
                options,
                target,
                kind,
                statistics=statistics,
                statistics_settings=settings if settings["enabled"] else None,
                protected_paths=self.workflow.protected_paths(),
                overwrite=True,
            )
        except (OSError, ValueError, ComparisonExportError) as exc:
            self._show_error(_t('Export de comparaison impossible'), exc)
            return
        self._set_messages(
            [
                _t('Séries tracées exportées : {v1}', v1=data_path),
                _t('Métadonnées exportées : {v1}', v1=json_path),
                *warnings,
            ]
        )
        self.statusBar().showMessage(_t('Export de comparaison terminé'), 5000)

    def _export_comparison_statistics(self) -> None:
        payload = self._comparison_export_payload()
        if payload is None:
            return
        options, curves, warnings = payload
        settings = self.workflow.project_document.comparison["statistics"]
        if not settings["groups"]:
            QMessageBox.information(
                self,
                _t('Export des statistiques'),
                _t("Aucun groupe de répétitions n'est défini."),
            )
            return
        statistics = self.workflow.comparison_statistics_data(curves, options)
        if self.workflow.experiments:
            source = self.workflow.experiments[0].source_path
            default_path = source.with_name(f"{source.stem}_statistiques.csv")
        else:
            default_path = Path("statistiques.csv")
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            _t('Exporter les statistiques de répétitions'),
            str(default_path),
            _t('CSV (*.csv);;TSV (*.tsv);;Tous les fichiers (*)'),
        )
        if not destination:
            return
        requested = Path(destination)
        kind = (
            "tsv"
            if requested.suffix.lower() == ".tsv" or selected_filter.startswith("TSV")
            else "csv"
        )
        target = requested.with_suffix(f".{kind}")
        metadata = target.with_suffix(".json")
        if not self._confirm_comparison_overwrite([target, metadata]):
            return
        try:
            data_path, json_path = export_group_statistics(
                statistics,
                options,
                target,
                kind,
                grid_method=settings["grid_method"],
                manual_points=settings["manual_points"],
                curves=curves,
                protected_paths=self.workflow.protected_paths(),
                overwrite=True,
            )
        except (OSError, ValueError, ComparisonExportError) as exc:
            self._show_error(_t('Export des statistiques impossible'), exc)
            return
        self._set_messages(
            [
                _t('Statistiques exportées : {v1}', v1=data_path),
                _t('Métadonnées exportées : {v1}', v1=json_path),
                *warnings,
            ]
        )
        self.statusBar().showMessage(_t('Export des statistiques terminé'), 5000)
    def _export_comparison_figure(self) -> None:
        payload = self._comparison_export_payload()
        if payload is None:
            return
        options, curves, warnings = payload
        self._render_comparison(options, curves)
        self.comparison_canvas.draw_idle()
        if self.workflow.experiments:
            source = self.workflow.experiments[0].source_path
            default_path = source.with_name(f"{source.stem}_comparaison.png")
        else:
            default_path = Path("comparaison.png")
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            _t('Exporter la figure de comparaison'),
            str(default_path),
            _t('PNG (*.png);;SVG (*.svg);;PDF (*.pdf);;Tous les fichiers (*)'),
        )
        if not destination:
            return
        requested = Path(destination)
        suffix = requested.suffix.lower().lstrip(".")
        kind = suffix if suffix in {"png", "svg", "pdf"} else "png"
        if selected_filter.startswith("SVG"):
            kind = "svg"
        elif selected_filter.startswith("PDF"):
            kind = "pdf"
        target = requested.with_suffix(f".{kind}")
        if not self._confirm_comparison_overwrite([target]):
            return
        try:
            figure_path = export_figure(
                self.comparison_figure,
                target,
                kind,
                dpi=300,
                protected_paths=self.workflow.protected_paths(),
                overwrite=True,
            )
        except (OSError, ValueError, ComparisonExportError) as exc:
            self._show_error(_t('Export de comparaison impossible'), exc)
            return
        self._set_messages([_t('Figure exportée : {v1}', v1=figure_path), *warnings])
        self.statusBar().showMessage(_t('Figure de comparaison exportée'), 5000)

    def _confirm_comparison_overwrite(self, paths: list[Path]) -> bool:
        protected = [path for path in paths if self.workflow.is_protected_path(path)]
        if protected:
            self._show_error(
                _t('Destination protégée'),
                ValueError(
                    _t('Une source ou le projet ouvert ne peut pas être remplacé :\n')
                    + "\n".join(str(path) for path in protected)
                ),
            )
            return False
        existing = [path for path in paths if path.exists()]
        if not existing:
            return True
        names = "\n".join(str(path) for path in existing)
        answer = QMessageBox.question(
            self,
            _t('Remplacer les fichiers ?'),
            _t('Les fichiers suivants existent déjà :\n\n{v1}\n\nVoulez-vous les remplacer ?', v1=names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def process_current(
        self, *, mark_normalization_dirty: bool = True
    ) -> CorrectionResult | None:
        try:
            normalization_settings, manual_mass = self.normalization_panel.values()
            self.workflow.set_normalization(
                normalization_settings,
                manual_mass,
                mark_dirty=mark_normalization_dirty,
            )
        except ValueError as exc:
            self._invalidate_normalization_result(_t(str(exc)))
            self.statusBar().showMessage(_t('Paramètres de normalisation invalides'), 5000)
            return None
        self.normalization_panel.clear_validation()
        settings = CorrectionSettings(
            method="direct",
            interpolation_axis="time_s",
        )
        self.process_button.setEnabled(False)
        self.statusBar().showMessage(_t('Traitement en cours…'))
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self.workflow.process(
                settings,
                show_subtraction=self.show_subtraction_check.isChecked(),
            )
            self._draw_result(result)
            self._draw_comparison()
        except (OSError, ValueError) as exc:
            self.workflow.result = None
            self._draw_placeholder(main_only=True)
            self._show_error(_t('Traitement impossible'), exc)
            return None
        finally:
            QApplication.restoreOverrideCursor()
            self._update_action_state()

        messages = [_t('Traitement terminé.')]
        messages.extend(result.warnings)
        self._set_messages(messages)
        self.statusBar().showMessage(_t('Traitement terminé'), 5000)
        return result

    def _experimental_zone_domain(self, axis_type: str, *, panel: ZonesPanel | None = None) -> tuple[float, float]:
        experiment = self.workflow.experiment
        if experiment is None:
            raise ValueError(_t("Aucune expérience n'est chargée."))
        if panel is self.comparison_zones_panel:
            grids = [x_values(curve.result, axis_type) for curve in self._comparison_curves]
            grids = [grid for grid in grids if grid is not None]
            if not grids:
                raise ValueError(_t('Aucune courbe de comparaison ne possède cet axe.'))
            values = np.concatenate(grids)
        else:
            values = axis_values(experiment, axis_type).to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size < 2:
            raise ValueError(
                _t("L'axe de l'expérience ne contient pas assez de valeurs valides.")
            )
        start = float(finite.min())
        end = float(finite.max())
        if end <= start:
            raise ValueError(_t('Le domaine expérimental est nul sur cet axe.'))
        return start, end

    @staticmethod
    def _heat_flow_context(
        experiment: ExperimentData,
        representation: str,
    ) -> tuple[str, str]:
        if representation not in HEAT_FLOW_REPRESENTATIONS:
            raise ValueError(_t('Représentation Flux de chaleur inconnue.'))
        configured_unit = HEAT_FLOW_REPRESENTATIONS[representation][2]
        unit = configured_unit or experiment.unit_for("heat_flow")
        if not unit.strip():
            raise ValueError(
                _t('La constante Flux de chaleur exige une unité de signal connue.')
            )
        return representation, unit

    def _constant_baseline_context(
        self,
        panel: ZonesPanel,
        baseline_method: str,
        baseline_value: float | None,
    ) -> tuple[str | None, str | None]:
        if baseline_method != "constant" or baseline_value is None:
            return None, None
        if panel is self.comparison_zones_panel:
            contexts = [
                self._heat_flow_context(
                    curve.result.experiment,
                    curve.plot_options.heat_flow_representation,
                )
                for curve in self._comparison_curves
                if curve.visible and curve.plot_options is not None
            ]
            if not contexts:
                raise ValueError(
                    _t('Aucune courbe de comparaison ne définit le contexte Flux de chaleur.')
                )
            representation, unit = contexts[0]
            if any(
                candidate_representation != representation
                or unit_key(candidate_unit) != unit_key(unit)
                for candidate_representation, candidate_unit in contexts[1:]
            ):
                raise ValueError(
                    _t("Les courbes de comparaison n'ont pas une représentation et une unité Flux de chaleur communes.")
                )
            return representation, unit
        experiment = self.workflow.experiment
        if experiment is None:
            raise ValueError(_t("Aucune expérience Flux de chaleur n'est disponible."))
        result = self.workflow.result
        representation = (
            self.workflow.normalization_settings().heat_flow_representation
            if result is None or "normalization" in result.parameters
            else "raw"
        )
        return self._heat_flow_context(experiment, str(representation))

    def _add_analysis_zone(self, _checked: bool = False, *, panel: ZonesPanel | None = None) -> None:
        panel = panel or self.zones_panel
        try:
            name, start, end, baseline, baseline_value = panel.editor_values(self.workflow.display_axis)
            baseline_representation, baseline_unit = self._constant_baseline_context(
                panel,
                baseline,
                baseline_value,
            )
            zone = self.analysis_zones.create_manual(
                name,
                self.workflow.display_axis,
                start,
                end,
                self._experimental_zone_domain(self.workflow.display_axis, panel=panel),
                baseline,
                baseline_value,
                baseline_representation,
                baseline_unit,
            )
        except (KeyError, ValueError) as exc:
            panel.show_validation(_t(str(exc)))
            return
        panel.clear_validation()
        self._after_analysis_zone_change(zone.identifier)
        self.statusBar().showMessage(_t('Zone créée : {v1}', v1=zone.name), 5000)

    def _update_analysis_zone(self, _checked: bool = False, *, panel: ZonesPanel | None = None) -> None:
        panel = panel or self.zones_panel
        identifier = panel.selected_zone_id()
        if identifier is None:
            panel.show_validation(_t('Sélectionner une zone à modifier.'))
            return
        try:
            current = self.analysis_zones.get(identifier)
            name, start, end, baseline, baseline_value = panel.editor_values(current.axis_type)
            baseline_representation, baseline_unit = self._constant_baseline_context(
                panel,
                baseline,
                baseline_value,
            )
            zone = self.analysis_zones.update(
                identifier,
                name=name,
                start=start,
                end=end,
                displayed_domain=self._experimental_zone_domain(current.axis_type, panel=panel),
                baseline_method=baseline,
                baseline_value=baseline_value,
                baseline_representation=baseline_representation,
                baseline_unit=baseline_unit,
            )
        except (KeyError, ValueError) as exc:
            panel.show_validation(_t(str(exc)))
            return
        panel.clear_validation()
        self._after_analysis_zone_change(zone.identifier)
        self.statusBar().showMessage(_t('Zone modifiée : {v1}', v1=zone.name), 5000)

    def _delete_analysis_zone(self, _checked: bool = False, *, panel: ZonesPanel | None = None) -> None:
        panel = panel or self.zones_panel
        identifier = panel.selected_zone_id()
        if identifier is None:
            panel.show_validation(_t('Sélectionner une zone à supprimer.'))
            return
        try:
            name = self.analysis_zones.get(identifier).name
            self.analysis_zones.delete(identifier)
        except KeyError as exc:
            panel.show_validation(_t(str(exc)))
            return
        panel.clear_validation()
        self._after_analysis_zone_change(None)
        panel.prepare_new_zone(self.analysis_zones.next_name())
        self.statusBar().showMessage(_t('Zone supprimée : {v1}', v1=name), 5000)

    def _on_active_analysis_zone_changed(self, identifier: str) -> None:
        if self._restoring_project or identifier == self._selected_zone_id:
            return
        try:
            self.analysis_zones.get(identifier)
        except KeyError:
            return
        self._selected_zone_id = identifier
        self.workflow.project_document.display[
            "analysis_zone_selected_id"
        ] = identifier
        self.workflow.mark_dirty()
        if self.workflow.result is not None:
            self._draw_result(self.workflow.result)
        else:
            self._refresh_zones_panel()
        self._draw_comparison()
        self._update_action_state()
        self._update_title()

    def _after_analysis_zone_change(self, selected_id: str | None) -> None:
        self._selected_zone_id = selected_id
        self.workflow.project_document.analysis_zones = list(
            self.analysis_zones.zones
        )
        self.workflow.project_document.display[
            "analysis_zone_selected_id"
        ] = selected_id
        self.workflow.mark_dirty()
        if self.workflow.result is not None:
            self._draw_result(self.workflow.result)
        else:
            self._refresh_zones_panel()
        self._draw_comparison()
        self._update_action_state()
        self._update_title()

    def _toggle_graphical_zone_selection(self, checked: bool, *, panel: ZonesPanel | None = None) -> None:
        if not checked:
            self._cancel_graphical_zone_selection()
            return
        self._start_graphical_zone_selection(panel=panel)

    def _start_graphical_zone_selection(self, *, panel: ZonesPanel | None = None) -> None:
        self._cancel_graphical_zone_selection()
        panel = panel or self.zones_panel
        comparison = panel is self.comparison_zones_panel
        axis = self.comparison_plot.axis if comparison else self.plot.primary_axis
        toolbar = self.comparison_toolbar if comparison else self.toolbar
        available = bool(self._comparison_curves) if comparison else self.workflow.result is not None
        if not available or axis is None:
            panel.show_validation(
                _t("Traiter l'expérience avant de sélectionner une zone sur le graphe.")
            )
            return
        if toolbar.mode:
            panel.show_validation(
                _t('Désactiver le zoom ou le déplacement Matplotlib avant la sélection.')
            )
            return
        try:
            self._experimental_zone_domain(self.workflow.display_axis, panel=panel)
        except ValueError as exc:
            panel.show_validation(_t(str(exc)))
            return
        panel.clear_validation()
        self._zone_selection_panel = panel
        self._zone_span_selector = SpanSelector(
            axis,
            self._on_zone_span_selected,
            "horizontal",
            # Le callback reconstruit les axes : un ancien fond blité effacerait la nouvelle zone.
            useblit=False,
            props={"facecolor": "#6A5ACD", "alpha": 0.25},
            interactive=False,
            drag_from_anywhere=False,
        )
        panel.set_graph_selection_active(True)
        self.statusBar().showMessage(
            _t('Glisser sur le graphe pour créer une zone ; Échap pour annuler.')
        )

    def _on_zone_span_selected(self, first: float, second: float) -> None:
        if self._zone_span_selector is None:
            return
        panel = self._zone_selection_panel or self.zones_panel
        self._cancel_graphical_zone_selection()
        if not np.isfinite(first) or not np.isfinite(second) or first == second:
            panel.show_validation(_t('La sélection graphique est vide.'))
            return
        name = panel.name_entry.text().strip()
        try:
            baseline, baseline_value = panel.baseline_values()
            baseline_representation, baseline_unit = self._constant_baseline_context(
                panel,
                baseline,
                baseline_value,
            )
            zone = self.analysis_zones.create_from_drag(
                self.workflow.display_axis,
                float(first),
                float(second),
                self._experimental_zone_domain(self.workflow.display_axis, panel=panel),
                name=name,
                baseline_method=baseline,
                baseline_value=baseline_value,
                baseline_representation=baseline_representation,
                baseline_unit=baseline_unit,
            )
        except ValueError as exc:
            panel.show_validation(_t(str(exc)))
            return
        panel.clear_validation()
        self._after_analysis_zone_change(zone.identifier)
        self.statusBar().showMessage(_t('Zone créée : {v1}', v1=zone.name), 5000)

    def _cancel_graphical_zone_selection(self) -> None:
        selector = self._zone_span_selector
        self._zone_span_selector = None
        self._zone_selection_panel = None
        if selector is not None:
            selector.set_active(False)
            selector.disconnect_events()
        if hasattr(self, "zones_panel"):
            self.zones_panel.set_graph_selection_active(False)
        if hasattr(self, "comparison_zones_panel"):
            self.comparison_zones_panel.set_graph_selection_active(False)

    def _on_plot_key_press(self, event) -> None:
        if event.key == "escape":
            self._cancel_graphical_zone_selection()
            self.statusBar().showMessage(_t('Sélection de zone annulée'), 3000)

    def _refresh_zones_panel(self) -> None:
        if not hasattr(self, "zones_panel"):
            return
        for panel in (self.zones_panel, self.comparison_zones_panel):
            panel.set_zones(self.analysis_zones.zones, self._selected_zone_id, self.workflow.display_axis)
        self.zones_panel.set_availability(
            self.workflow.experiment is not None,
            self.workflow.result is not None,
        )
        self.comparison_zones_panel.set_availability(bool(self._comparison_curves), bool(self._comparison_curves))
        self._refresh_zone_quantification()

    def _refresh_zone_quantification(self) -> None:
        self._refresh_open_zone_results()
        self.comparison_results_table.setRowCount(0)
        self.comparison_count_label.setText(_t('{v0} courbe(s) visible(s)', v0=len(self._comparison_curves)))
        statistics_settings = self.workflow.project_document.comparison["statistics"]
        if statistics_settings["enabled"]:
            self.comparison_count_label.setText(_t('Affichage : ') + STAT_DISPLAY_LABELS[statistics_settings["display_mode"]])
        band = statistics_settings["enabled"] and statistics_settings["display_mode"] == "mean_band"
        self.comparison_results_table.setHorizontalHeaderLabels(
            (_t('Série'), _t('Zone'), _t('Début'), _t('Fin'), _t('Variation'), _t('Basse / haute') if band else _t('Complément'))
        )
        self.comparison_zones_panel.set_results("")
        identifier = self._selected_zone_id
        if identifier is None:
            self.zones_panel.set_results("")
            return
        try:
            zone = self.analysis_zones.get(identifier)
        except KeyError:
            self.zones_panel.set_results("")
            return
        records = self._comparison_zone_results(zone)
        for values, report in records:
            table = self.comparison_results_table
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(report)
                table.setItem(row, column, item)
        self.comparison_zones_panel.set_results("\n\n".join(report for _, report in records))
        if self.workflow.result is None:
            self.zones_panel.set_results(
                _t("Résultat corrigé indisponible. Traiter l'expérience pour quantifier la zone.")
            )
            return
        quantified, reference_error = self.workflow.quantify_analysis_zone(zone)
        self.zones_panel.set_results(
            self._format_zone_quantification(quantified, reference_error)
        )

    def _comparison_zone_results(self, zone):
        """Un même contenu pour la zone active et le rapport de toutes les zones."""
        settings = self.workflow.project_document.comparison["statistics"]
        mode = settings["display_mode"] if settings["enabled"] else "individual"
        records = []
        included = set()
        expected_units = {}
        for statistics in self._comparison_statistics if settings["enabled"] else ():
            # Même filtre d'unité et de disponibilité que le tracé des groupes.
            if self.comparison_plot._statistics_exclusion_reason(statistics, expected_units.get(statistics.signal)):
                continue
            expected_units.setdefault(statistics.signal, statistics.scientific_unit)
            included.update(statistics.included)
            if mode == "individual":
                continue
            label = _t('{v0} · {v2} · moyenne', v0=statistics.group.name, v2=SIGNAL_LABELS[statistics.signal])
            unit = statistics.unit
            delta_unit = _t('points de %') if unit == "%" else unit
            complement = "—"
            try:
                summary = quantify_group_zone(statistics, zone, axis_type=self.workflow.display_axis)
                variation = f"{summary.delta:.6g} {delta_unit}"
                report = (
                    _t(
                        ('{v0} · {v2}\n'
                         'Bornes : {v4:g} → {v6:g} ({v8})\n'
                         'Moyenne au début : {v10:.6g} {v12}\n'
                         'Moyenne à la fin : {v14:.6g} {v16}\n'
                         'Variation de la moyenne : {v18}\n'
                         'Minimum / maximum dans la zone : {v20:.6g} / {v22:.6g} {v24}\n'
                         "Répétitions incluses : {v26}. Valeurs dans l'unité du signal affiché, sans décalage "
                         'visuel.'),
                        v0=zone.name,
                        v2=label,
                        v4=zone.start,
                        v6=zone.end,
                        v8=AXIS_LABELS[zone.axis_type],
                        v10=summary.start_mean,
                        v12=unit,
                        v14=summary.end_mean,
                        v16=unit,
                        v18=variation,
                        v20=summary.minimum,
                        v22=summary.maximum,
                        v24=unit,
                        v26=len(statistics.included),
                    )
                )
                if mode == "mean_band":
                    bounds = summary.delta_bounds
                    if bounds is None:
                        report += _t('\nBande ±1 écart-type indisponible sur toute la zone (répétitions insuffisantes ou lacune).')
                    else:
                        complement = f"[{bounds[0]:.4g} ; {bounds[1]:.4g}]"
                        report += (
                            _t(
                                ('\n'
                                 'Bande au début (basse / haute) : {v1:.6g} / {v3:.6g} {v5}\n'
                                 'Bande à la fin (basse / haute) : {v7:.6g} / {v9:.6g} {v11}\n'
                                 'Enveloppe de variation (basse / haute) : [{v13:.6g} ; {v15:.6g}] {v17}\n'
                                 "Cette enveloppe combine les bornes de la bande ponctuelle ; ce n'est ni l'écart-type "
                                 'de Δ ni un intervalle de confiance.'),
                                v1=summary.start_mean - summary.start_std,
                                v3=summary.start_mean + summary.start_std,
                                v5=unit,
                                v7=summary.end_mean - summary.end_std,
                                v9=summary.end_mean + summary.end_std,
                                v11=unit,
                                v13=bounds[0],
                                v15=bounds[1],
                                v17=delta_unit,
                            )
                        )
            except ValueError as exc:
                variation = _t('Indisponible')
                report = f"{zone.name} · {label}\n{exc}"
            records.append(((label, zone.name, f"{zone.start:g}", f"{zone.end:g}", variation, complement), report))
        if mode in {"individual", "mean_individual"}:
            for curve in self._comparison_curves:
                if not curve.visible or (settings["enabled"] and curve.identifier not in included):
                    continue
                try:
                    result, error = self.workflow.quantify_analysis_zone(zone, curve=curve)
                    report = self._format_zone_quantification(result, error, curve=curve)
                    variation = "—" if result.delta_zone_mg is None else f"{result.delta_zone_mg:.6g} mg"
                    complement = "—" if result.delta_zone_pct_m0 is None else _t('{v0:.6g} % de m0', v0=result.delta_zone_pct_m0)
                except (ValueError, KeyError) as exc:
                    report = self._format_zone_error(zone, exc, experiment_name=curve.legend_name)
                    variation, complement = _t('Indisponible'), "—"
                records.append(((curve.legend_name, zone.name, f"{zone.start:g}", f"{zone.end:g}", variation, complement), report))
        return records

    def _format_zone_quantification(self, result, reference_error: str | None, *, curve=None) -> str:
        axis_unit = result.axis_unit
        normalization = self.workflow.project_document.normalization
        tg_mode = normalization["tg_representation"]
        dtg_mode = normalization["dtg_representation"]
        heat_mode = normalization["heat_flow_representation"]
        if curve is not None and curve.plot_options is not None:
            tg_mode = curve.plot_options.tg_representation
            dtg_mode = curve.plot_options.dtg_representation
            heat_mode = curve.plot_options.heat_flow_representation
        signals = self._zone_result_signals(curve)

        def scope(
            state: str,
            mode: str,
            normalized_modes: set[str],
        ) -> str:
            origin = {
                "original": "original",
                "corrected": _t('corrigé'),
                "calculated": _t('calculé'),
                "derived": _t('dérivé'),
                "unavailable": "indisponible",
            }.get(state, _t('indéterminé'))
            if mode == "raw":
                return _t('{v0}, représentation brute', v0=origin)
            if mode in normalized_modes:
                return _t('{v0}, représentation normalisée', v0=origin)
            return _t('{v0}, représentation dérivée', v0=origin)

        def number(value: float | None, unit: str = "") -> str:
            if value is None:
                return "—"
            rendered = f"{value:.8g}"
            return f"{rendered} {unit}" if unit else rendered

        lines = [
            f"{result.zone_name} — {_t(result.status)}",
            (
                _t(
                    'Axe : {v1} ; bornes {v3} à {v5}',
                    v1=AXIS_LABELS.get(result.axis_type, result.axis_type),
                    v3=number(result.start, axis_unit),
                    v5=number(result.end, axis_unit),
                )
            ),
            _t('Expérience : {v1} ; points valides : {v3}', v1=result.experiment_name, v3=result.valid_point_count),
            _t("Les coordonnées proviennent de l'expérience ; aucune donnée source n'est modifiée."),
        ]
        if "tg" in signals:
            lines.extend([
                "",
                f"TG ({scope(result.tg_state, tg_mode, {'normalized_mg_mg', 'normalized_pct'})})",
                _t('  Variation dans la zone : {v1}', v1=number(result.delta_zone_mg, 'mg')),
                _t('  Variation / m0 : {v1}', v1=number(result.delta_zone_pct_m0, '%')),
                _t('  Variation / référence : {v1}', v1=number(result.delta_zone_pct_reference, '%')),
                _t('  Masse restante en fin de zone : {v1}', v1=number(result.remaining_mass_end_mg, 'mg')),
                _t('  Masse résiduelle en fin de zone : {v1}', v1=number(result.residual_mass_end_pct, '%')),
            ])
        if "dtg" in signals:
            lines.extend([
                "",
                f"dTG ({scope(result.dtg_state, dtg_mode, {'per_mass', 'percent'})})",
                _t('  Minimum : {v1} à {v3}', v1=number(result.dtg_minimum, result.dtg_unit), v3=number(result.dtg_minimum_position, axis_unit)),
                _t('  Maximum : {v1} à {v3}', v1=number(result.dtg_maximum, result.dtg_unit), v3=number(result.dtg_maximum_position, axis_unit)),
                _t(
                    '  Pic principal : {v1} à {v3}',
                    v1=number(result.dtg_main_peak, result.dtg_unit),
                    v3=number(result.dtg_main_peak_position, axis_unit),
                ),
            ])
        if "heat_flow" in signals:
            lines.extend([
                "",
                (
                    _t(
                        'Flux de chaleur ({v1}; ligne de base {v3})',
                        v1=scope(result.heat_flow_state, heat_mode, {'mw_mg', 'zero_mw_mg', 'w_g', 'zero_w_g', 'w_mg', 'zero_w_mg'}),
                        v3=result.baseline_method,
                    )
                ),
                _t(
                    '  Minimum : {v1} à {v3}',
                    v1=number(result.heat_flow_minimum, result.heat_flow_unit),
                    v3=number(result.heat_flow_minimum_position, axis_unit),
                ),
                _t(
                    '  Maximum : {v1} à {v3}',
                    v1=number(result.heat_flow_maximum, result.heat_flow_unit),
                    v3=number(result.heat_flow_maximum_position, axis_unit),
                ),
                _t(
                    '  Pic principal : {v1} à {v3}',
                    v1=number(result.heat_flow_main_peak, result.heat_flow_unit),
                    v3=number(result.heat_flow_main_peak_position, axis_unit),
                ),
                _t('  Aire signée : {v1}', v1=number(result.heat_flow_area, result.heat_flow_area_unit)),
                _t('  Aire au-dessus de la ligne de base : {v1}', v1=number(result.heat_flow_positive_area, result.heat_flow_area_unit)),
                _t(
                    '  Aire au-dessous de la ligne de base (signée) : {v1}',
                    v1=number(result.heat_flow_negative_area, result.heat_flow_area_unit),
                ),
            ])
        warnings = list(result.warnings)
        if reference_error:
            warnings.append(_t('Références de normalisation : {v1}', v1=reference_error))
        if warnings:
            lines.extend(("", _t('Avertissements :')))
            lines.extend(f"  - {warning}" for warning in dict.fromkeys(warnings))
        return "\n".join(lines)

    def _zone_result_signals(self, curve=None) -> tuple[str, ...]:
        if curve is None:
            return tuple(
                signal
                for signal in ("tg", "dtg", "heat_flow")
                if signal != "heat_flow" or self._atg_dsc_modes["main"]
            )
        return tuple(
            signal
            for signal in self.comparison_panel.selected_signals()
            if signal != "heat_flow" or _has_source_heat_flow(curve.result.experiment)
        )

    @staticmethod
    def _format_zone_error(zone, error: Exception, *, experiment_name: str = "") -> str:
        axis = AXIS_LABELS.get(zone.axis_type, zone.axis_type)
        lines = [
            _t('{v0} — indisponible', v0=zone.name),
            _t('Axe : {v1} ; bornes {v3:.8g} à {v5:.8g}', v1=axis, v3=zone.start, v5=zone.end),
        ]
        if experiment_name:
            lines.append(_t('Expérience : {v1}', v1=experiment_name))
        lines.append(_t('Erreur : {v1}', v1=error))
        return "\n".join(lines)

    def _all_zone_results(self, context: str) -> tuple[str, str]:
        zones = self.analysis_zones.zones
        if context == "main":
            title = _t('Tous les résultats — expérience active')
            if self.workflow.experiment is None:
                return title, _t('Aucune expérience active.')
            if not zones:
                return title, _t("Aucune zone d'analyse définie.")
            blocks = []
            for zone in zones:
                try:
                    quantified, reference_error = self.workflow.quantify_analysis_zone(zone)
                    blocks.append(
                        self._format_zone_quantification(quantified, reference_error)
                    )
                except (ValueError, KeyError) as exc:
                    blocks.append(self._format_zone_error(zone, exc))
            return title, "\n\n".join(blocks)

        title = _t('Tous les résultats — comparaison')
        if not zones:
            return title, _t("Aucune zone d'analyse définie.")
        curves = [curve for curve in self._comparison_curves if curve.visible]
        if not curves:
            return title, _t('Aucune courbe sélectionnée et visible à comparer.')
        blocks = []
        for zone in zones:
            blocks.extend(report for _, report in self._comparison_zone_results(zone))
        return title, "\n\n".join(blocks)

    def _show_all_zone_results(self, context: str) -> None:
        self._zone_results_context = context
        self._refresh_open_zone_results(force=True)
        self.zone_results_dialog.show()
        self.zone_results_dialog.raise_()
        self.zone_results_dialog.activateWindow()

    def _refresh_open_zone_results(self, *, force: bool = False) -> None:
        if self._zone_results_context is None:
            return
        if not force and not self.zone_results_dialog.isVisible():
            return
        title, text = self._all_zone_results(self._zone_results_context)
        self.zone_results_dialog.set_report(title, text)

    def _draw_result(self, result: CorrectionResult) -> None:
        stage = _t('Normalisé') if "normalization" in result.parameters else (
            _t('Corrigé') if result.blank is not None else _t('Original')
        )
        self.display_stage_label.setText(stage)
        self.display_stage_label.setToolTip(result.experiment.source_path.name)
        self._cancel_graphical_zone_selection()
        self._sync_interface_mode("main")
        signals = self._visible_signals()
        if not signals:
            raise ValueError(_t('Sélectionner au moins une courbe à afficher.'))
        display = self.workflow.project_document.display
        limits = display["limits"]
        normalization = self.workflow.project_document.normalization
        normalized = "normalization" in result.parameters
        options = PlotOptions(
            x_axis=self.workflow.display_axis,
            signals=signals,
            x_limits=tuple(limits["x"]),
            y_limits={
                role: tuple(limits[role])
                for role in ("tg", "dtg", "heat_flow")
            },
            align_zeros=display["align_zeros"],
            alignment_mode=display["alignment_mode"],
            tg_representation=(
                normalization["tg_representation"] if normalized else "raw"
            ),
            dtg_representation=(
                normalization["dtg_representation"] if normalized else "raw"
            ),
            heat_flow_representation=(
                normalization["heat_flow_representation"] if normalized else "raw"
            ),
            reference_name=normalization["reference_name"] if normalized else "",
            analysis_zones=self.analysis_zones.zones,
            selected_analysis_zone_id=self._selected_zone_id,
            show_zone_surfaces=display["show_zone_surfaces"],
            show_zone_baselines=display["show_zone_baselines"],
            graph_settings=display["graph"],
        )
        self.plot.draw([result], options)
        self.canvas.draw()
        self._refresh_zones_panel()

    def _draw_placeholder(self, *, main_only: bool = False) -> None:
        self.display_stage_label.setText(_t('Aucun résultat'))
        self._cancel_graphical_zone_selection()
        self._sync_interface_mode("main")
        if not main_only:
            self._sync_interface_mode("comparison")
            self._comparison_curves = []
            self._comparison_statistics = []
            self.comparison_plot.draw(
                [],
                ComparisonOptions(
                    graph_settings=self.workflow.project_document.comparison[
                        "graph"
                    ]
                ),
            )
            self.comparison_canvas.draw_idle()
        display = self.workflow.project_document.display
        self.plot.draw(
            [],
            PlotOptions(
                signals=("tg",),
                x_limits=tuple(display["limits"]["x"]),
                y_limits={"tg": tuple(display["limits"]["tg"])},
                graph_settings=display["graph"],
            ),
        )
        self.canvas.draw_idle()
        self._refresh_zones_panel()

    def choose_export(self) -> None:
        result = self.workflow.result
        if result is None:
            QMessageBox.information(
                self,
                "Export",
                _t("Traiter d'abord une expérience avec un blanc."),
            )
            return
        filters = _t('CSV français + JSON (*.csv);;TSV international + JSON (*.tsv)')
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            _t('Exporter le résultat'),
            str(
                result.experiment.source_path.with_name(
                    f"{result.experiment.source_path.stem}_corrige.csv"
                )
            ),
            filters,
        )
        if not destination:
            return
        requested = Path(destination)
        selected_kind = "tsv" if selected_filter.startswith("TSV") else "csv"
        suffix = requested.suffix.lower()
        kind = suffix.lstrip(".") if suffix in {".csv", ".tsv"} else selected_kind
        target = requested.with_suffix(f".{kind}")
        if not self._confirm_comparison_overwrite(
            [target, target.with_suffix(".json")]
        ):
            return
        self.export_action.setEnabled(False)
        self.statusBar().showMessage(_t('Export en cours…'))
        QApplication.processEvents(
            QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        try:
            files = self.workflow.export_current(target, kind, overwrite=True)
        except (OSError, ValueError) as exc:
            self._show_error(_t('Export impossible'), exc)
            return
        finally:
            self._update_action_state()
        self._set_messages(
            [
                _t('Tableau exporté : {v1}', v1=files.data_path),
                _t('Métadonnées exportées : {v1}', v1=files.json_path),
                *(
                    [_t("Format {v1} retenu selon l'extension du fichier.", v1=kind.upper())]
                    if suffix in {".csv", ".tsv"} and kind != selected_kind
                    else []
                ),
            ]
        )
        self.statusBar().showMessage(_t('Export terminé'), 5000)

    def _update_source_views(self) -> None:
        self._refresh_main_experiments()
        self._set_source_view(
            self.workflow.experiment,
            self.experiment_path_label,
        )

    def _refresh_main_experiments(self) -> None:
        with QSignalBlocker(self.experiments_table):
            self.experiments_table.setRowCount(len(self.workflow.experiments))
            loaded_blanks: dict[Path, ExperimentData] = {}
            for row in range(len(self.workflow.experiments)):
                candidate = self.workflow.comparison_blank(row)
                if candidate is not None:
                    loaded_blanks.setdefault(
                        candidate.source_path.resolve(), candidate
                    )
            blank_name_counts: dict[str, int] = {}
            for candidate in loaded_blanks.values():
                name = candidate.source_path.name
                blank_name_counts[name] = blank_name_counts.get(name, 0) + 1
            for row, experiment in enumerate(self.workflow.experiments):
                blank = self.workflow.comparison_blank(row)
                active = experiment is self.workflow.experiment
                item = self.experiments_table.item(row, 0)
                if item is None:
                    item = QTableWidgetItem()
                    self.experiments_table.setItem(row, 0, item)
                kind = "ATG-DSC" if _has_source_heat_flow(experiment) else "ATG"
                item.setText(f"{experiment.source_path.name}\n{kind}")
                item.setToolTip(str(experiment.source_path))
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                item.setCheckState(
                    Qt.CheckState.Checked if active else Qt.CheckState.Unchecked
                )

                button = QToolButton(self.experiments_table)
                button.setObjectName("mainBlankButton")
                button.setText(blank.source_path.name if blank is not None else "—")
                button.setToolTip(
                    str(blank.source_path) if blank is not None else _t('Aucun blanc associé')
                )
                state = blank.source_path.name if blank is not None else _t('Aucun')
                button.setAccessibleName(
                    _t('Blanc associé à {v1} : {v3}', v1=experiment.source_path.name, v3=state)
                )
                button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
                button.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Preferred,
                )
                menu = QMenu(button)
                menu.setToolTipsVisible(True)
                choice_group = QActionGroup(menu)
                choice_group.setExclusive(True)
                none_action = menu.addAction(_t('Aucun'))
                none_action.setCheckable(True)
                none_action.setChecked(blank is None)
                choice_group.addAction(none_action)
                none_action.triggered.connect(
                    lambda _checked=False, target=row: self._assign_blank_to_row(
                        target, None
                    )
                )
                current_path = (
                    blank.source_path.resolve() if blank is not None else None
                )
                for path, candidate in loaded_blanks.items():
                    name = candidate.source_path.name
                    label = (
                        name
                        if blank_name_counts[name] == 1
                        else f"{name} ({candidate.source_path.parent})"
                    )
                    action = menu.addAction(label)
                    action.setCheckable(True)
                    action.setChecked(path == current_path)
                    action.setToolTip(str(candidate.source_path))
                    choice_group.addAction(action)
                    action.triggered.connect(
                        lambda _checked=False, target=row, selected=candidate: (
                            self._assign_blank_to_row(target, selected)
                        )
                    )
                menu.addSeparator()
                choose_action = menu.addAction(_t('Choisir un fichier…'))
                choose_action.triggered.connect(
                    lambda _checked=False, target=row: self._choose_blank_for_row(
                        target
                    )
                )
                button.setMenu(menu)
                self.experiments_table.setCellWidget(row, 1, button)
                if active:
                    self.experiments_table.setCurrentCell(row, 0)

    def _set_source_view(
        self,
        data: ExperimentData | None,
        path_label: QLabel,
    ) -> None:
        if data is None:
            path_label.setText(_t('Non chargé'))
            path_label.setToolTip("")
            return
        path_text = str(data.source_path)
        path_label.setText(data.source_path.name)
        path_label.setToolTip(path_text)

    def _update_action_state(self) -> None:
        with QSignalBlocker(self.align_zeros_check):
            self.align_zeros_check.setChecked(self.workflow.project_document.display["alignment_mode"] == "zeros")
        self._sync_interface_mode("main")
        self._sync_interface_mode("comparison")
        ready = self.workflow.experiment is not None
        self.open_blank_action.setEnabled(ready)
        has_result = self.workflow.result is not None
        self.process_button.setEnabled(ready and bool(self._visible_signals()))
        self.export_action.setEnabled(has_result)
        self.graph_settings_action.setEnabled(ready)
        self.save_project_action.setEnabled(self.workflow.project_dirty)
        self.save_project_as_action.setEnabled(True)
        comparison_available = bool(self.workflow.experiments)
        self.comparison_graph_settings_action.setEnabled(comparison_available)
        self.comparison_panel.set_availability(comparison_available)
        self.zones_panel.set_availability(
            self.workflow.experiment is not None,
            has_result,
        )

    def _set_messages(self, lines: list[str]) -> None:
        self._last_messages = "\n".join(line for line in lines if line)
        self.messages_button.setToolTip(self._last_messages or _t('Aucun message.'))
        self.messages_button.setText(_t('Informations ({v1})', v1=len([line for line in lines if line])))

    def _set_comparison_messages(self, text: str) -> None:
        self._comparison_message_text = text
        self.comparison_messages_button.setToolTip(text or _t('Aucun message.'))

    def _missing_source_handler(
        self,
        source: SourceFileRecord,
    ) -> tuple[str, Path | None]:
        answer = QMessageBox.warning(
            self,
            _t('Fichier source introuvable'),
            _t('Le fichier « {v1} » est introuvable.\n\nAncien chemin :\n{v3}', v1=source.name, v3=source.absolute_path),
            QMessageBox.StandardButton.Open
            | QMessageBox.StandardButton.Ignore
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Open,
        )
        if answer == QMessageBox.StandardButton.Ignore:
            return "ignore", None
        if answer != QMessageBox.StandardButton.Open:
            return "cancel", None
        path, _ = QFileDialog.getOpenFileName(
            self,
            _t('Localiser {v1}', v1=source.name),
            source.name,
            _t('Tous les fichiers (*)'),
        )
        return ("locate", Path(path)) if path else ("cancel", None)

    def _modified_source_handler(
        self,
        source: SourceFileRecord,
        path: Path,
    ) -> tuple[str, Path | None]:
        answer = QMessageBox.warning(
            self,
            _t('Fichier source modifié'),
            _t(
                ('Le fichier « {v1} » ne correspond plus à son empreinte SHA-256 enregistrée.\n'
                 '\n'
                 'Fichier trouvé :\n'
                 '{v3}'),
                v1=source.name,
                v3=path,
            ),
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.Open
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            return "continue", None
        if answer != QMessageBox.StandardButton.Open:
            return "cancel", None
        selected, _ = QFileDialog.getOpenFileName(
            self,
            _t("Localiser l'original de {v1}", v1=source.name),
            source.name,
            _t('Tous les fichiers (*)'),
        )
        return ("locate", Path(selected)) if selected else ("cancel", None)

    def _modified_source_save_handler(
        self,
        source: SourceFileRecord,
        path: Path,
    ) -> tuple[str, Path | None]:
        answer = QMessageBox.warning(
            self,
            _t('Source modifiée depuis le chargement'),
            _t(
                ('Le fichier « {v1} » a changé depuis son chargement. Les données en mémoire décrivent '
                 'encore la version chargée.\n'
                 '\n'
                 "Enregistrer le projet en conservant l'empreinte de cette version ? Le fichier sera "
                 'signalé comme modifié à la prochaine ouverture.\n'
                 '\n'
                 'Fichier actuel :\n'
                 '{v3}\n'
                 '\n'
                 'Pour utiliser sa version actuelle, annulez puis rechargez-la.'),
                v1=source.name,
                v3=path,
            ),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return "continue", None
        return "cancel", None

    def closeEvent(self, event: QCloseEvent) -> None:
        # Les widgets jamais affichés (notamment ceux de pytest-qt) peuvent être
        # détruits sans interaction. La fenêtre réelle est visible et conserve
        # donc intégralement la confirmation des changements non enregistrés.
        if not self.isVisible():
            event.accept()
            return
        if self._confirm_unsaved_changes():
            event.accept()
        else:
            event.ignore()

    def _show_error(self, title: str, error: Exception) -> None:
        message = _t(str(error))
        self._set_messages([f"{title} : {message}"])
        self.statusBar().showMessage(title, 5000)
        QMessageBox.critical(self, title, message)
