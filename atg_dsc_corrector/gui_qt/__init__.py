"""Interface Qt Widgets d'ATG-DSC Corrector."""

__all__ = ["MainWindow", "ScientificWorkflow"]


def __getattr__(name: str):
    # Load UI labels only after app.main has selected the saved language.
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    if name == "ScientificWorkflow":
        from .adapters import ScientificWorkflow
        return ScientificWorkflow
    raise AttributeError(name)
