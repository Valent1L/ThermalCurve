"""Fenêtre principale de la tranche verticale PySide6."""

from __future__ import annotations

from atg_dsc_corrector import APP_NAME, CONTACT, COPYRIGHT, LICENSE, __version__
from atg_dsc_corrector.i18n import language, tr as _t

from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable

import numpy as np
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector
from PySide6.QtCore import QEventLoop, QSettings, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from atg_dsc_corrector.analysis_zones import AnalysisZoneManager, axis_values, axis_unit
from atg_dsc_corrector.correction import CorrectionSettings
from atg_dsc_corrector.models import CorrectionResult, ExperimentData, unit_key
from atg_dsc_corrector.normalization import (
    HEAT_FLOW_REPRESENTATIONS,
    extract_initial_mass_mg,
)
from atg_dsc_corrector.comparison_exports import (
    ComparisonExportError,
    export_figure,
    export_visible_curves,
)
from atg_dsc_corrector.comparison import (
    ComparisonOptions,
    ComparisonPlot,
)
from atg_dsc_corrector.comparison_statistics import quantify_group_zone
from atg_dsc_corrector.mean_zone_quantification import quantify_mean_zone_signal, mean_heat_flow_profile
from atg_dsc_corrector.plotting import x_values, draw_graph_legend, draw_heat_flow_zone
from atg_dsc_corrector.labels import plain_display_label
from atg_dsc_corrector.projects import (
    ProjectError,
    ProjectOpenCancelled,
    ProjectValidationError,
    SourceFileRecord,
    default_comparison_settings,
)

from .adapters import ProjectWorkflow
from .comparison_panel import ComparisonPanel, STAT_DISPLAY_LABELS
from .graph_settings_dialog import GraphSettingsDialog
from .thermal_program_editor import ThermalProgramDialog
from .normalization_panel import NormalizationPanel
from .periodic_table_dialog import PeriodicTableDialog
from .stoichiometry_dialog import StoichiometryDialog
from .theme import PlotToolbar, ThemedFigureCanvas, appearance_palette, apply_application_theme, line_icon, style_plot_toolbar
from .zones_panel import ZoneAppearanceDialog, ZonesPanel
from .settings import application_settings


FILE_FILTER = _t('Données ATG / ATG-DSC (*.xls *.xlsx *.txt *.csv *.tsv);;Exports ATG texte avec ou sans extension (*);;Tous les fichiers (*)')

SIGNAL_LABELS = {
    "tg": "TG",
    "dtg": "dTG",
    "heat_flow": _t('Flux de chaleur'),
}

AXIS_LABELS = {
    "time_s": _t('Temps (s)'),
    "time_min": _t('Temps (min)'),
    "time_h": _t('Temps (h)'),
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
        QSizePolicy.Policy.Ignored,
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
        from .number_format import number_locale
        self.setLocale(number_locale())
        self._appearance_settings = (
            settings if settings is not None else application_settings()
        )
        self._appearance_settings.sync()
        self._last_messages = ""
        self._panels = {}
        self._panel_sizes = {"left": 350, "right": 300, "bottom": 230}
        self.interface_style = "console"
        self.color_theme = str(self._appearance_settings.value("appearance/theme", "light"))
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
        self._mode_context_keys: dict[str, tuple[int, ...] | None] = {
            "main": None,
        }
        self._atg_dsc_modes = {"main": False}
        self.setMinimumSize(900, 620)
        self.resize(1500, 900)

        self.figure = Figure(figsize=(9, 6), dpi=100, constrained_layout=True)
        self.canvas = ThemedFigureCanvas(self.figure)
        self.canvas.setObjectName("plotCanvas")
        self.plot = ComparisonPlot(self.figure)

        self._build_actions()
        self._build_window()
        self.set_appearance(self.color_theme, persist=False)
        self._connect_signals()
        self.canvas.mpl_connect(
            "key_press_event", self._on_plot_key_press
        )
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
        self.export_figure_action = QAction(_t("Exporter la figure"), self)
        self.quit_action = QAction(_t('Quitter'), self)
        self.quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self.stoichiometry_action = QAction(_t('Calculs stœchiométriques…'), self)
        self.periodic_table_action = QAction(_t('Tableau périodique…'), self)
        self.graph_settings_action = QAction(_t('Paramètres du graphique…'), self)
        self.graph_settings_action.setIcon(line_icon("settings"))
        self.thermal_program_action = QAction(_t('Programme thermique'), self)

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
        menu.addAction(self.export_figure_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        self.menuBar().addAction(self.thermal_program_action)
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
                    lambda checked, v=value: self.set_appearance(v) if checked else None
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
        self.comparison_panel = ComparisonPanel(self.workflow)
        visible = self.workflow.project_document.display["visible_signals"]
        for signal, check in self.comparison_panel.signal_checks.items():
            with QSignalBlocker(check):
                check.setChecked(signal in visible)
        self.workflow.project_document.comparison["signals"] = list(visible)
        self.stoichiometry_dialog = StoichiometryDialog(self.workflow, self)
        self.stoichiometry_dialog.project_changed.connect(self._stoichiometry_changed)
        self.periodic_table_dialog = PeriodicTableDialog(self)
        toolbar = QToolBar(_t('Projet'), self)
        toolbar.setObjectName("projectToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.interface_title = QLabel()
        self.interface_title.setObjectName("workspaceTitle")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        for action, label, icon in (
            (self.open_experiment_action, _t('Importer'), "import"),
            (self.save_project_action, _t('Enregistrer'), "save"),
            (self.export_action, _t('Exporter'), "export"),
            (self.export_figure_action, _t("Exporter la figure"), "export"),
        ):
            action.setIconText(label)
            action.setIcon(line_icon(icon))
            toolbar.addAction(action)
        toolbar.addWidget(spacer)
        toolbar.addWidget(self.interface_title)
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
        splitter.setSizes([350, 780, 300])
        self.setCentralWidget(splitter)
        self.main_splitter.setSizes([350, max(700, self.width() - 560), 300])
        self.plot_splitter.setSizes([max(400, self.height() - 300), 230])
        for layout in (self.files_layout, self.preparation_layout, self.plot_layout):
            layout.setSpacing(4)
            layout.setContentsMargins(4, 4, 4, 4)

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

    def set_appearance(self, theme: str, *, persist: bool = True) -> None:
        tokens = appearance_palette(theme)
        self.color_theme = theme
        apply_application_theme(QApplication.instance(), theme, set_font=False)
        for canvas in (self.canvas,):
            canvas.screen_theme = tokens if theme == "dark" else None
            canvas.draw_idle()
        self.appearance_actions["theme"][theme].setChecked(True)
        self.appearance_label.setText(
            f"{_t('Console')} · "
            f"{_t('Clair') if theme == 'light' else _t('Sombre')}"
        )
        self.interface_title.setText(_t("Console d'analyse"))
        self.comparison_panel.set_appearance()
        self.stoichiometry_dialog.set_appearance()
        if persist:
            self._appearance_settings.setValue("appearance/theme", theme)
            self._appearance_settings.sync()
            if self._appearance_settings.status() != QSettings.Status.NoError:
                QMessageBox.warning(self, _t('Préférences non enregistrées'),
                                    _t("Impossible d'enregistrer l'apparence dans :\n")
                                    + self._appearance_settings.fileName())



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
        # Keep the minimum usable control width, including the vertical scrollbar.
        scroll.setMinimumWidth(content.minimumSizeHint().width() + scroll.verticalScrollBar().sizeHint().width())
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
        for widget, title, name in (
            (content, _t('Préparation'), "controlsScrollArea"),
            (self.comparison_panel.statistics_group, _t('Statistiques'), "statisticsScrollArea"),
            (self.comparison_panel.display_group, _t('Courbes'), "displayScrollArea"),
        ):
            scroll = QScrollArea()
            scroll.setObjectName(name)
            scroll.setWidgetResizable(True)
            scroll.setWidget(widget)
            # Les longues options défilent dans le volet au lieu d'agrandir la fenêtre.
            scroll.setMinimumWidth(240)
            for label in widget.findChildren(QLabel):
                label.setWordWrap(True)
            scroll.setMinimumWidth(max(240, widget.minimumSizeHint().width() + scroll.verticalScrollBar().sizeHint().width()))
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
        group = self.comparison_panel
        self.experiments_table = group.table
        self.experiments_table.setObjectName("mainExperimentsTable")
        self.experiments_table.setAccessibleName(_t('Expériences et blancs associés'))
        self.experiments_table.setToolTip(_t("Cocher les expériences à afficher ; sélectionner une ligne pour modifier ses réglages."))
        self.experiment_path_label = _path_label()
        self.experiment_path_label.setObjectName("experimentPath")
        self.open_experiment_button = group.add_button
        group.layout().addWidget(self.experiment_path_label)
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
        layout = QFormLayout(group)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setContentsMargins(0, 0, 0, 0)
        self.display_stage_label = QLabel(_t('Aucune expérience'))
        self.display_stage_label.setObjectName("displayStage")
        from .flow_layout import FlowLayout
        options = QWidget()
        option_row = FlowLayout(options)
        layout.addRow(self.display_stage_label, options)

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
        option_row.addWidget(self.display_axis_combo)

        self.signal_checks = self.comparison_panel.signal_checks
        option_row.addWidget(self.comparison_panel.signal_bar)

        return group

    def _build_plot_panel(self) -> QWidget:
        self.plot_splitter = QSplitter(Qt.Orientation.Vertical)
        self.plot_splitter.setChildrenCollapsible(False)
        panel = QWidget()
        layout = self.plot_layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)
        layout.addWidget(self._build_display_controls())

        self.toolbar = PlotToolbar(self.canvas, panel)
        style_plot_toolbar(self.toolbar)
        self.legend_action = self.toolbar.addAction(line_icon("legend"), _t("Modifier la légende"))
        self.legend_action.triggered.connect(self._open_legend_settings)
        self.toolbar.setObjectName("matplotlibToolbar")
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.graph_settings_action)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, 1)

        self.plot_splitter.addWidget(panel)
        self.console_zone_group = self.zones_panel
        zone_frame = self._collapsible_panel("bottom", _t("Zones"), self.zones_panel)
        header = zone_frame.layout().itemAt(0).layout()
        from .flow_layout import FlowLayout
        zone_actions = FlowLayout()
        zone_actions.addWidget(header.takeAt(0).widget())
        header.insertLayout(0, zone_actions, 1)
        for button in (self.zones_panel.all_results_button, self.zones_panel.add_button, self.zones_panel.update_button,
                       self.zones_panel.delete_button, self.zones_panel.copy_button, self.zones_panel.information_button):
            zone_actions.addWidget(button)
        self.plot_splitter.addWidget(zone_frame)
        self.plot_splitter.setStretchFactor(0, 1)
        self.plot_splitter.setStretchFactor(1, 0)
        return self.plot_splitter

    def _connect_signals(self) -> None:
        self.new_project_action.triggered.connect(self.new_project)
        self.open_project_action.triggered.connect(self.choose_project)
        self.save_project_action.triggered.connect(self.save_project)
        self.save_project_as_action.triggered.connect(self.save_project_as)
        self.open_experiment_action.triggered.connect(self.choose_experiment)
        self.open_blank_action.triggered.connect(self.choose_blank)
        self.export_action.triggered.connect(self.choose_export)
        self.export_figure_action.triggered.connect(self._export_comparison_figure)
        self.quit_action.triggered.connect(self.close)
        self.stoichiometry_action.triggered.connect(self.show_stoichiometry_window)
        self.periodic_table_action.triggered.connect(self.show_periodic_table_window)
        self.thermal_program_action.triggered.connect(self._open_thermal_program)
        self.graph_settings_action.triggered.connect(
            lambda _checked=False: self._open_graph_settings(True)
        )
        self.open_experiment_button.clicked.connect(self.choose_experiment)
        self.comparison_panel.blank_button.clicked.connect(self.choose_comparison_blank)
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
        self.comparison_panel.stack_signal_combo.currentIndexChanged.connect(self._update_stack_unit)
        self.comparison_panel.model.modelReset.connect(self._refresh_blank_buttons)
        self.comparison_panel.auto_stack_requested.connect(
            self._auto_stack_comparison
        )
        self.comparison_panel.zero_offsets_requested.connect(
            self._zero_comparison_offsets
        )
        self.comparison_panel.active_row_changed.connect(
            self._select_main_experiment
        )
        self.display_axis_combo.currentIndexChanged.connect(self._sync_display_axis)
        self.show_subtraction_check.toggled.connect(self._show_subtraction_changed)
        self.normalization_panel.changed.connect(self._normalization_changed)
        self.normalization_panel.pending_changed.connect(
            self._normalization_pending
        )
        self.zones_panel.add_button.clicked.connect(self._add_analysis_zone)
        self.zones_panel.delete_button.clicked.connect(self._delete_analysis_zone)
        self.zones_panel.zone_edit_requested.connect(self._edit_analysis_zone)
        self.zones_panel.appearance_requested.connect(self._edit_zone_appearance)
        self.zones_panel.active_zone_changed.connect(self._on_active_analysis_zone_changed)
        self.process_button.clicked.connect(self.process_current)

    def _set_tab_order(self) -> None:
        dock_controls = self.zones_panel.tab_controls()
        controls = [
            self.main_atg_button,
            self.main_atg_dsc_button,
            self.experiments_table,
            self.open_experiment_button,
            self.comparison_panel.remove_button,
            self.comparison_panel.up_button,
            self.comparison_panel.down_button,
            self.comparison_panel.blank_button,
            self.display_axis_combo,
            *self.signal_checks.values(),
            *dock_controls,
            self.inspector_tabs.tabBar(),
            self.show_subtraction_check,
            self.process_button,
            *self.normalization_panel.tab_controls(),
        ]
        controls.extend(widget for widget in self.comparison_panel.tab_controls() if widget not in controls)
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
        # Les anciens projets conservent leurs réglages du graphique principal
        # lorsque le graphique de comparaison n'avait pas été personnalisé.
        display = self.workflow.project_document.display
        comparison = self.workflow.project_document.comparison
        defaults = default_comparison_settings()
        if comparison["graph"] == defaults["graph"]:
            comparison["graph"] = deepcopy(display["graph"])
        if comparison["limits"] == defaults["limits"]:
            comparison["limits"] = deepcopy(display["limits"])
        if display["alignment_mode"] != "none" and not comparison["align_zeros"]:
            comparison["align_zeros"] = display["alignment_mode"] == "zeros"
        comparison["signals"] = list(display["visible_signals"])
        self._comparison_curves = []
        self._comparison_statistics = []
        self.plot.draw([], ComparisonOptions())
        self.canvas.draw_idle()
        self._restoring_project = True
        try:
            display_axis = self.workflow.project_document.display["x_axis"]
            axis_index = self.display_axis_combo.findData(display_axis)
            self.display_axis_combo.setCurrentIndex(max(0, axis_index))
            visible = set(
                self.workflow.project_document.display["visible_signals"]
            )
            for role, checkbox in self.signal_checks.items():
                with QSignalBlocker(checkbox):
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
        self._update_source_views()
        self._refresh_zones_panel()

    def _mode_context_experiments(self, context: str) -> tuple[ExperimentData, ...]:
        return tuple(
            experiment for row, experiment in enumerate(self.workflow.experiments)
            if self.workflow.comparison_record(row)["visible"] and self.workflow.comparison_record(row)["selected"]
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
        heat_flow_visible = self._atg_dsc_modes["main"]
        self.comparison_panel.set_heat_flow_visible(heat_flow_visible)
        self.normalization_panel.set_heat_flow_visible(
            self.workflow.experiment is not None and _has_source_heat_flow(self.workflow.experiment)
        )
        self.zones_panel.set_heat_flow_visible(heat_flow_visible)

    def _mode_selected(self, context: str, atg_dsc: bool, checked: bool) -> None:
        if not checked:
            return
        experiments = self._mode_context_experiments(context)
        if atg_dsc and not any(_has_source_heat_flow(item) for item in experiments):
            return
        self._atg_dsc_modes[context] = atg_dsc
        self._mode_context_keys[context] = tuple(id(item) for item in experiments)
        self._apply_interface_mode(context)
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

    def _open_thermal_program(self) -> None:
        if self.workflow.experiment is None:
            return
        display = self.workflow.project_document.display
        dialog = ThermalProgramDialog(
            program=self.workflow.active_thermal_program(),
            time_axis=self.workflow.display_axis,
            apply_callback=lambda program: self._apply_graph_settings(False, [], {
                "graph": display["graph"], "limits": display["limits"],
                "alignment_mode": display["alignment_mode"], "thermal_program": program,
            }),
            parent=self,
        )
        dialog.exec()

    def _open_graph_settings(self, comparison: bool) -> None:
        if comparison:
            settings = self.workflow.project_document.comparison
            signals = self.comparison_panel.selected_signals()
            rows = self.comparison_panel.selected_rows()
            alignment_mode = "zeros" if settings["align_zeros"] else self.workflow.project_document.display["alignment_mode"]
            show_offsets = bool(settings["show_offsets_in_legend"])
        else:
            settings = self.workflow.project_document.display
            signals = self._visible_signals()
            rows = []
            alignment_mode = str(settings["alignment_mode"])
            show_offsets = False
        dialog = GraphSettingsDialog(
            graph=settings["graph"],
            limits=settings["limits"],
            signals=signals,
            alignment_mode=alignment_mode,
            comparison=comparison,
            show_offsets_in_legend=show_offsets,
            apply_callback=lambda values: self._apply_graph_settings(
                comparison, rows, values
            ),
            parent=self,
        )
        dialog.exec()

    def _apply_graph_settings(
        self,
        comparison: bool,
        rows: list[int],
        values: dict[str, object],
    ) -> None:
        previous_dirty = self.workflow.project_dirty
        if comparison:
            previous = deepcopy(self.workflow.project_document.comparison)
            previous_display = deepcopy(self.workflow.project_document.display)
            try:
                self.workflow.set_comparison_graph_settings(
                    graph=values["graph"],
                    limits=values["limits"],
                    align_zeros=values["alignment_mode"] == "zeros",
                    show_offsets_in_legend=values["show_offsets_in_legend"],
                    rows=rows,
                    curve_changes=values["curve_changes"],
                )
                self.workflow.set_main_graph_settings(
                    graph=values["graph"], limits=values["limits"],
                    alignment_mode=str(values["alignment_mode"]),
                )
                self.comparison_panel.model.refresh()
                self._draw_comparison(propagate_errors=True)
            except (OSError, ValueError) as exc:
                self.workflow.project_document.comparison = previous
                self.workflow.project_document.display = previous_display
                self.workflow.project_dirty = previous_dirty
                self.comparison_panel.model.refresh()
                self._draw_comparison()
                raise ValueError(_t(str(exc))) from exc
        else:
            previous = deepcopy(self.workflow.project_document.display)
            previous_comparison = deepcopy(self.workflow.project_document.comparison)
            try:
                self.workflow.set_main_graph_settings(
                    graph=values["graph"],
                    limits=values["limits"],
                    alignment_mode=str(values["alignment_mode"]),
                    thermal_program=values.get("thermal_program"),
                )
                settings = self.workflow.project_document.comparison
                self.workflow.set_comparison_graph_settings(
                    graph=values["graph"], limits=values["limits"],
                    align_zeros=values["alignment_mode"] == "zeros",
                    show_offsets_in_legend=settings["show_offsets_in_legend"],
                    rows=[], curve_changes={},
                )
                if self.workflow.result is not None:
                    self._draw_result(self.workflow.result)
            except ValueError as exc:
                self.workflow.project_document.display = previous
                self.workflow.project_document.comparison = previous_comparison
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
        self.workflow.project_document.comparison["align_zeros"] = enabled
        if self.workflow.result is not None:
            self._draw_result(self.workflow.result)
        self._update_action_state()
        self._update_title()

    def _update_title(self) -> None:
        marker = "*" if self.workflow.project_dirty else ""
        self.setWindowTitle(
            f"{self.workflow.project_document.project_name}{marker} - "
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
        if not active:
            self._draw_comparison()
        self._update_action_state()
        self._update_title()



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
        signal = self.comparison_panel.curve_signal_combo.currentData()
        target = self.workflow.move_comparison_experiment(rows[0], delta)
        self.comparison_panel.model.refresh()
        self.comparison_panel.select_row(target, signal)
        self._update_source_views()
        self._comparison_changed()

    def _activate_comparison_experiment(self, row: int) -> None:
        self.workflow.activate_comparison_experiment(row)
        self._restoring_project = True
        try:
            record = self.workflow.comparison_record(row)
            self.show_subtraction_check.setChecked(record["stage"] != "original" and record.get("show_subtraction", True))
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
            else:
                self._draw_comparison()
        return blank



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
        self._draw_comparison()
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
            self._set_active_stage(result)
            self._draw_result(result)
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
        self.workflow.set_visible_signals(self.comparison_panel.checked_signals())
        self._sync_interface_mode("main")
        self._draw_comparison()
        if self.workflow.experiment is not None:
            row = self.workflow.experiments.index(self.workflow.experiment)
            with QSignalBlocker(self.show_subtraction_check):
                record = self.workflow.comparison_record(row)
                self.show_subtraction_check.setChecked(record["stage"] != "original" and record.get("show_subtraction", True))
        self._update_action_state()
        self._update_title()

    def _update_stack_unit(self, *_args) -> None:
        signal = self.comparison_panel.stack_signal_combo.currentData()
        curves = getattr(self, '_comparison_curves', [])
        unit = ''
        if signal:
            curve = next((item.for_signal(signal) for item in curves if item.for_signal(signal).visible), None)
            if curve is not None:
                unit = ComparisonPlot._unit_for_curve(
                    curve, curve.plot_options or ComparisonOptions().plot_options, signal
                )
        self.comparison_panel.stack_spacing_spin.setSuffix(f" {plain_display_label(unit)}" if unit else '')

    def _auto_stack_comparison(self) -> None:
        panel = self.comparison_panel
        signal = panel.stack_signal_combo.currentData()
        signals = (signal,) if signal else ()
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
            spacing = None if panel.auto_spacing_check.isChecked() else panel.stack_spacing_spin.value()
            offsets = ComparisonPlot.automatic_offsets(curves, options, spacing=spacing)
            if len(offsets) < 2:
                self._set_messages(
                    [*warnings, _t('Au moins deux courbes compatibles doivent être cochées pour empiler.')]
                )
                return
            if spacing is None:
                spacing = max(offsets.values()) / (len(offsets) - 1)
            self.workflow.set_comparison_offsets(offsets, signal=signal, spacing=spacing)
            panel.set_stack_spacing(spacing)
        except (OSError, ValueError) as exc:
            self.comparison_panel.show_validation(_t(str(exc)))
            return
        self.comparison_panel.clear_validation()
        self.comparison_panel.model.refresh()
        self._comparison_changed()

    def _zero_comparison_offsets(self) -> None:
        self.comparison_panel.stack_timer.stop()
        self.comparison_panel._stack_active = False
        self.workflow.set_comparison_offsets(
            {
                self.workflow.comparison_key(experiment): 0.0
                for experiment in self.workflow.experiments
            }
        )
        self.workflow.set_mean_curve_settings(('tg', 'dtg', 'heat_flow'), {'y_offset': 0.0})
        self.comparison_panel.set_stack_spacing(0, active=False)
        self.comparison_panel.auto_spacing_check.setChecked(True)
        self.comparison_panel.model.refresh()
        self._comparison_changed()

    def _render_comparison(self, options, curves):
        options.plot_options.thermal_program = (
            self.workflow.active_thermal_program()
            if any(curve.result.experiment is self.workflow.experiment for curve in curves) else None
        )
        options.plot_options.x_limits = options.x_limits
        options.plot_options.graph_settings = options.graph_settings
        options.plot_options.alignment_mode = self.workflow.project_document.display["alignment_mode"]
        options.plot_options.analysis_zones = self.analysis_zones.zones
        options.plot_options.selected_analysis_zone_id = self._selected_zone_id
        statistics_settings = self.workflow.project_document.comparison["statistics"]
        if statistics_settings["enabled"]:
            statistics = self.workflow.comparison_statistics_data(curves, options)
            self.plot.draw_statistics(
                curves,
                options,
                statistics,
                statistics_settings["display_mode"],
            )
            self.comparison_panel.set_statistics_summary(statistics)
            self.plot.draw_zones(
                curves, options,
                show_heat_surfaces=statistics_settings["display_mode"] == "individual",
            )
            if statistics_settings["display_mode"] != "individual":
                self._draw_mean_zone_area(statistics, options)
            return statistics
        self.plot.draw(curves, options)
        self.plot.draw_zones(curves, options)
        self.comparison_panel.set_statistics_summary([])
        return []

    def _draw_mean_zone_area(self, statistics, options):
        zone = self.analysis_zones.get(self._selected_zone_id) if self._selected_zone_id else None
        axis = self.plot.axes.get("heat_flow")
        if zone is None or axis is None or zone.axis_type != self.workflow.display_axis:
            return
        x_limits, y_limits = axis.get_xlim(), axis.get_ylim()
        for item in statistics:
            if item.signal != "heat_flow" or self.plot._statistics_exclusion_reason(item, None):
                continue
            try:
                profile = mean_heat_flow_profile(item, zone, axis_type=self.workflow.display_axis,
                                                representation=self._mean_heat_representation(item))
            except ValueError:
                continue  # The results table carries the existing zone/context error.
            draw_heat_flow_zone(axis, profile, offset=options.mean_styles.get('heat_flow', {}).get('y_offset', 0.0),
                show_baseline=zone.show_baseline and options.plot_options.show_zone_baselines,
                show_surfaces=options.plot_options.show_zone_surfaces, positive_color=zone.positive_area_color or "#0072B2",
                negative_color=zone.negative_area_color or "#D55E00", baseline_color=zone.baseline_color or "#7A3E9D")
        axis.set_xlim(x_limits)
        axis.set_ylim(y_limits)
    def _open_legend_settings(self) -> None:
        from .legend_dialog import LegendDialog
        from atg_dsc_corrector.legend import legend_entries
        entries = getattr(self.plot.axis, "_thermalcurve_legend_entries", ())
        handles, labels = zip(*entries) if entries else ([], [])
        dialog = LegendDialog(self.workflow.project_document.comparison["graph"],
                              legend_entries(handles, labels), self._apply_legend_settings, self,
                              axes_bounds=self.plot.axis.get_position().bounds)
        dialog.exec()

    def _apply_legend_settings(self, graph) -> None:
        from atg_dsc_corrector.legend import validate_legend_text
        previous = deepcopy(self.workflow.project_document.comparison)
        previous_display = deepcopy(self.workflow.project_document.display)
        dirty = self.workflow.project_dirty
        entries = getattr(self.plot.axis, "_thermalcurve_legend_entries", ())
        handles, labels = zip(*entries) if entries else ([], [])
        try:
            validate_legend_text(graph)
            self.workflow.set_comparison_graph_settings(
                graph=graph, limits=previous["limits"], align_zeros=previous["align_zeros"],
                show_offsets_in_legend=previous["show_offsets_in_legend"], rows=[], curve_changes={})
            self.workflow.set_main_graph_settings(graph=graph, limits=previous_display["limits"],
                                                  alignment_mode=previous_display["alignment_mode"])
            draw_graph_legend(self.plot.axis, handles, labels, graph)
            self.canvas.draw()  # Validate mathematical text before keeping the settings.
        except (ValueError, OSError):
            self.workflow.project_document.comparison = previous
            self.workflow.project_document.display = previous_display
            self.workflow.project_dirty = dirty
            draw_graph_legend(self.plot.axis, handles, labels, previous["graph"])
            self._bind_legend_drag()
            self.canvas.draw_idle()
            raise ValueError(_t("La légende n'a pas pu être appliquée. Vérifiez le texte mathématique et les réglages.")) from None
        self._bind_legend_drag()
        self._update_title()

    def _bind_legend_drag(self) -> None:
        from atg_dsc_corrector.legend import LegendDrag
        legend = self.plot.axis.get_legend() if self.plot.axis is not None else None
        if legend is not None and legend._draggable is None:
            legend._draggable = LegendDrag(legend, self._legend_moved)

    def _legend_moved(self, style) -> None:
        for settings in (self.workflow.project_document.comparison, self.workflow.project_document.display):
            settings["graph"]["legend_position"] = "manual"
            settings["graph"]["legend_style"] = deepcopy(style)
        self.workflow.mark_dirty()
        self._update_title()

    def _draw_comparison(self, *, propagate_errors: bool = False) -> None:
        self._comparison_statistics = []
        self._cancel_graphical_zone_selection()
        self._sync_interface_mode("main")
        signals = self.comparison_panel.selected_signals()
        if not signals:
            message = _t('Sélectionnez au moins une courbe visible dans ce parcours.')
            self._set_comparison_messages(message)
            self._comparison_curves = []
            self.plot.draw(
                [],
                ComparisonOptions(
                    graph_settings=self.workflow.project_document.comparison[
                        "graph"
                    ]
                ),
            )
            self.canvas.draw_idle()
            self._refresh_zones_panel()
            return
        try:
            options, curves, warnings = self.workflow.comparison_plot_data(
                signals=signals,
                x_axis=self.workflow.display_axis,
                persist_signals=False,
            )
            self._comparison_curves = curves
            self._update_stack_unit()
            self._comparison_statistics = self._render_comparison(options, curves)
        except (OSError, ValueError) as exc:
            if propagate_errors:
                raise
            self._set_messages([_t(str(exc))])
            self._set_comparison_messages(_t(str(exc)))
            self._comparison_curves = []
            self.plot.draw(
                [],
                ComparisonOptions(
                    graph_settings=self.workflow.project_document.comparison[
                        "graph"
                    ]
                ),
            )
            self.canvas.draw_idle()
            self._refresh_zones_panel()
            return
        self.workflow.project_document.comparison["colors"] = dict(
            self.plot.colors
        )
        self._bind_legend_drag()
        self.canvas.draw_idle()
        statistics = self.workflow.project_document.comparison["statistics"]
        self.display_stage_label.setText(
            STAT_DISPLAY_LABELS[statistics["display_mode"]] if statistics["enabled"]
            else _t('{v0} expérience(s) affichée(s)', v0=len(curves))
        )
        messages = [*warnings, *self.plot.warnings]
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
        if curves:
            source = curves[0].result.experiment.source_path
            suffix = "export" if len(curves) == 1 else "comparaison"
            default_path = source.with_name(f"{source.stem}_{suffix}.xlsx")
        else:
            default_path = Path("comparaison.xlsx")
        destination, selected_filter = QFileDialog.getSaveFileName(
            self,
            _t('Exporter les séries tracées'),
            str(default_path),
            _t('Classeur Excel (*.xlsx)'),
        )
        if not destination:
            return
        requested = Path(destination)
        kind = "xlsx"
        target = requested.with_suffix(".xlsx")
        if not self._confirm_comparison_overwrite([target]):
            return
        try:
            settings = self.workflow.project_document.comparison["statistics"]
            statistics = (
                self.workflow.comparison_statistics_data(curves, options)
                if settings["enabled"] else []
            )
            data_path = export_visible_curves(
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
                *warnings,
            ]
        )
        self.statusBar().showMessage(_t('Export de comparaison terminé'), 5000)

    def _export_comparison_figure(self) -> None:
        payload = self._comparison_export_payload()
        if payload is None:
            return
        options, curves, warnings = payload
        self._render_comparison(options, curves)
        self.canvas.draw_idle()
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
                self.figure,
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
            if mark_normalization_dirty:
                self._set_active_stage(result)
            self._draw_result(result)
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
        if panel is None or panel is self.zones_panel:
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
        if panel is None or panel is self.zones_panel:
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

    def _add_analysis_zone(self, checked=False) -> None:
        self._panels["bottom"][3].setChecked(True)
        self.zones_panel.tabs.setCurrentIndex(0)
        self._toggle_graphical_zone_selection(checked)

    def _edit_analysis_zone(self, identifier: str, changes: dict) -> None:
        panel = self.zones_panel
        try:
            current = self.analysis_zones.get(identifier)
            fields = dict(changes)
            if "baseline_method" in fields or "baseline_value" in fields:
                method = fields.get("baseline_method", current.baseline_method)
                value = fields.get("baseline_value", current.baseline_value) if method == "constant" else None
                representation, unit = self._constant_baseline_context(panel, method, value)
                fields.update(baseline_method=method, baseline_value=value,
                              baseline_representation=representation, baseline_unit=unit)
            if current.axis_type in {"furnace_temperature", "sample_temperature"}:
                fields["start"], fields["end"] = sorted((fields.get("start", current.start), fields.get("end", current.end)))
            candidate = replace(current, **fields)
            zone = self.analysis_zones.update(identifier, name=candidate.name,
                start=candidate.start, end=candidate.end,
                displayed_domain=self._experimental_zone_domain(current.axis_type),
                baseline_method=candidate.baseline_method, baseline_value=candidate.baseline_value,
                baseline_representation=candidate.baseline_representation, baseline_unit=candidate.baseline_unit)
        except (KeyError, ValueError) as exc:
            panel.show_validation(_t(str(exc)))
            return
        panel.clear_validation()
        self._after_analysis_zone_change(zone.identifier)

    def _edit_zone_appearance(self, identifier: str) -> None:
        current = self.analysis_zones.get(identifier)
        dialog = ZoneAppearanceDialog(current, self)
        if dialog.exec() == ZoneAppearanceDialog.DialogCode.Accepted:
            updated = replace(current, **dialog.values())
            self.analysis_zones.replace(updated if zone.identifier == identifier else zone
                                        for zone in self.analysis_zones.zones)
            self._after_analysis_zone_change(identifier)
        dialog.deleteLater()

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
        axis = self.plot.axis
        toolbar = self.toolbar
        available = bool(self._comparison_curves)
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
        name = self.analysis_zones.next_name()
        try:
            baseline, baseline_value = "none", None
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

    def _on_plot_key_press(self, event) -> None:
        if event.key == "escape":
            self._cancel_graphical_zone_selection()
            self.statusBar().showMessage(_t('Sélection de zone annulée'), 3000)

    def _refresh_zones_panel(self) -> None:
        if not hasattr(self, "zones_panel"):
            return
        self.zones_panel.set_zones(self.analysis_zones.zones, self._selected_zone_id, self.workflow.display_axis)
        self.zones_panel.set_availability(bool(self._comparison_curves), bool(self._comparison_curves))
        self._refresh_zone_quantification()

    def _refresh_zone_quantification(self) -> None:
        records = [record for zone in self.analysis_zones.zones
                   for record in self._comparison_zone_results(zone)]
        self.zones_panel.set_records(records)

    def _comparison_zone_results(self, zone):
        """Structured presentation of the same individual and statistical calculations."""
        settings = self.workflow.project_document.comparison["statistics"]
        mode = settings["display_mode"] if settings["enabled"] else "individual"
        records, included, expected_units, means = [], set(), {}, {}
        for statistics in self._comparison_statistics if settings["enabled"] else ():
            if self.plot._statistics_exclusion_reason(statistics, expected_units.get(statistics.signal)):
                continue
            expected_units.setdefault(statistics.signal, statistics.scientific_unit)
            included.update(statistics.included)
            if mode == "individual":
                continue
            sample = next(curve.result.experiment for curve in self._comparison_curves if curve.identifier in statistics.included)
            record = means.setdefault(statistics.group.identifier, dict(
                experiment_key="mean:" + statistics.group.identifier,
                experiment_name=statistics.group.name, zone_name=zone.name, zone_id=zone.identifier,
                start=zone.start, end=zone.end, axis_type=zone.axis_type, axis_unit=axis_unit(sample, zone.axis_type),
                baseline_method=zone.baseline_method, baseline_value=zone.baseline_value,
                baseline_unit=zone.baseline_unit, baseline_representation=zone.baseline_representation,
                statistics={}, status="OK", warnings=[], signals=[]))
            signal = statistics.signal
            record["signals"].append(signal)
            detail = dict(stat_unit=statistics.unit, stat_delta_unit=_t("points de %") if statistics.unit == "%" else statistics.unit,
                          stat_count=len(statistics.included))
            record["statistics"][signal] = detail
            members = [curve for curve in self._comparison_curves if curve.identifier in statistics.included]
            representation = self._mean_heat_representation(statistics)
            references = ()
            if signal == 'tg':
                representations = {curve.plot_options.tg_representation if curve.stage == 'normalized' and curve.plot_options else 'raw' for curve in members}
                representation = next(iter(representations)) if len(representations) == 1 else None
                references = tuple(self.workflow.zone_references(curve.result)[0] for curve in members)
            quantified = quantify_mean_zone_signal(statistics, zone, axis_type=self.workflow.display_axis,
                axis_unit=record["axis_unit"], representation=representation, references=references)
            for key, value in asdict(quantified).items():
                if key.startswith(signal + "_") or (signal == "tg" and key in {
                    "delta_zone_mg", "delta_zone_pct_m0", "delta_zone_pct_reference", "remaining_mass_end_mg",
                    "residual_mass_end_pct", "initial_mass_mg"}):
                    record[key] = value
            detail["valid_point_count"] = quantified.valid_point_count
            counts = {item["valid_point_count"] for item in record["statistics"].values()}
            record["valid_point_count"] = counts.pop() if len(counts) == 1 else None
            record["warnings"].extend(_t(SIGNAL_LABELS[signal]) + " : " + _t(message) for message in quantified.warnings if message)
            try:
                summary = quantify_group_zone(statistics, zone, axis_type=self.workflow.display_axis)
                detail.update(stat_start_mean=summary.start_mean, stat_end_mean=summary.end_mean,
                              stat_delta=summary.delta, stat_minimum=summary.minimum, stat_maximum=summary.maximum)
                if signal == "tg":
                    record.update(mean_tg_delta=summary.delta, mean_tg_unit=statistics.unit)
                if mode == "mean_band":
                    detail.update(stat_start_std=summary.start_std, stat_end_std=summary.end_std)
                    bounds = summary.delta_bounds
                    if bounds is None:
                        record["warnings"].append(_t("Bande ±1 écart-type indisponible sur toute la zone."))
                    else:
                        detail.update(stat_delta_low=bounds[0], stat_delta_high=bounds[1])
                        record["warnings"].append(_t("L'enveloppe de variation combine les bandes aux bornes ; ce n'est ni l'écart-type de Δ ni un intervalle de confiance."))
            except ValueError as exc:
                record["warnings"].append(_t(str(exc)))
            if record["warnings"]:
                record["status"] = "Avertissement"
        records.extend(means.values())
        if mode in {"individual", "mean_individual"}:
            for curve in self._comparison_curves:
                if not curve.visible or (settings["enabled"] and curve.identifier not in included):
                    continue
                try:
                    result, error = self.workflow.quantify_analysis_zone(zone, curve=curve)
                    record = asdict(result)
                    record["warnings"] = list(result.warnings)
                    if error:
                        record["warnings"].append(_t('Références de normalisation : {v1}', v1=error))
                    if record["warnings"] and record["status"] == "OK":
                        record["status"] = "Avertissement"
                    options = curve.plot_options
                    record["representations"] = "; ".join((options.tg_representation, options.dtg_representation,
                                                           options.heat_flow_representation)) if options else ""
                except (ValueError, KeyError) as exc:
                    record = dict(zone_id=zone.identifier, zone_name=zone.name, start=zone.start, end=zone.end,
                                  axis_type=zone.axis_type, axis_unit=axis_unit(curve.result.experiment, zone.axis_type),
                                  status="Indisponible", warnings=[_t(str(exc))])
                record["experiment_name"] = curve.legend_name
                record["signals"] = self._zone_result_signals(curve)
                records.append(record)
        return records

    def _mean_heat_representation(self, statistics):
        representations = {curve.plot_options.heat_flow_representation if curve.stage == "normalized" and curve.plot_options else "raw"
                           for curve in self._comparison_curves if curve.identifier in statistics.included}
        return next(iter(representations)) if len(representations) == 1 else None

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
            if curve.signal_settings.get(signal, {}).get("visible", True)
            and (signal != "heat_flow" or _has_source_heat_flow(curve.result.experiment))
        )

    def _set_active_stage(self, result: CorrectionResult) -> None:
        row = self.workflow.experiments.index(result.experiment)
        record = self.workflow.comparison_record(row)
        subtraction = self.show_subtraction_check.isChecked()
        if record.get("show_subtraction", True) != subtraction:
            record["show_subtraction"] = subtraction
            self.workflow.mark_dirty()
        stage = "normalized" if "normalization" in result.parameters else (
            "corrected" if self.show_subtraction_check.isChecked() else "original"
        )
        self.workflow.set_comparison_value(row, "stage", stage)
        self._refresh_main_experiments()

    def _draw_result(self, result: CorrectionResult) -> None:
        self._draw_comparison()

    def _draw_placeholder(self, *, main_only: bool = False) -> None:
        self.display_stage_label.setText(_t('Aucun résultat'))
        self._cancel_graphical_zone_selection()
        self._comparison_curves = []
        self._comparison_statistics = []
        self.plot.draw([], ComparisonOptions(graph_settings=self.workflow.project_document.comparison["graph"]))
        self.canvas.draw_idle()
        self._refresh_zones_panel()

    def choose_export(self) -> None:
        self._export_comparison_data()

    def _update_source_views(self) -> None:
        self._refresh_main_experiments()
        self._set_source_view(
            self.workflow.experiment,
            self.experiment_path_label,
        )

    def _refresh_main_experiments(self) -> None:
        self.comparison_panel.model.refresh()

    def _refresh_blank_buttons(self) -> None:
        with QSignalBlocker(self.experiments_table):
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
                button = QToolButton(self.experiments_table)
                button.setObjectName("mainBlankButton")
                button.setText(blank.source_path.name if blank is not None else "-")
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
                self.experiments_table.setIndexWidget(self.comparison_panel.model.index(row, 3), button)

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
            self.align_zeros_check.setChecked(self.workflow.project_document.comparison["align_zeros"])
        self._sync_interface_mode("main")
        ready = self.workflow.experiment is not None
        self.open_blank_action.setEnabled(ready)
        has_result = self.workflow.result is not None
        self.process_button.setEnabled(ready and bool(self._visible_signals()))
        self.export_action.setEnabled(bool(self._comparison_curves))
        self.graph_settings_action.setEnabled(ready)
        self.thermal_program_action.setEnabled(ready)
        self.save_project_action.setEnabled(self.workflow.project_dirty)
        self.save_project_as_action.setEnabled(True)
        comparison_available = bool(self.workflow.experiments)
        self.comparison_panel.set_availability(comparison_available)
        self.export_figure_action.setEnabled(bool(self._comparison_curves))
        self.zones_panel.set_availability(
            bool(self._comparison_curves),
            bool(self._comparison_curves),
        )

    def _set_messages(self, lines: list[str]) -> None:
        self._last_messages = "\n".join(line for line in lines if line)
        self.messages_button.setToolTip(self._last_messages or _t('Aucun message.'))
        self.messages_button.setText(_t('Informations ({v1})', v1=len([line for line in lines if line])))

    def _set_comparison_messages(self, text: str) -> None:
        if text:
            self._set_messages(text.splitlines())

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
