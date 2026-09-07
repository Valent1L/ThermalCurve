"""Référentiel atomique local issu de CIAAW 2024 et IUPAC 2022."""

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Iterator


SOURCE_ID: Final = "CIAAW-2024-abridged"
SOURCE_DATE: Final = "2024"
SOURCE_URL: Final = "https://ciaaw.org/abridged-atomic-weights.htm"
FRENCH_NAMES_SOURCE: Final = "Traduction française contrôlée dans ce module"
PERIODIC_TABLE_SOURCE_URL: Final = (
    "https://iupac.org/wp-content/uploads/2022/07/IUPAC_Periodic_Table-04May22_CRA.pdf"
)
PERIODIC_TABLE_SOURCE_DATE: Final = "2022-05-04"


class AtomicDataError(ValueError):
    """La clé atomique ou la masse demandée n'est pas disponible."""


@dataclass(frozen=True)
class AtomicElement:
    atomic_number: int
    symbol: str
    name_fr: str
    standard_atomic_weight: Decimal | None
    display_mass_number: int | None
    group: int | None
    period: int


def _element(
    atomic_number: int,
    symbol: str,
    name_fr: str,
    weight: str | None,
    display_mass_number: int | None,
    group: int | None,
    period: int,
) -> AtomicElement:
    return AtomicElement(
        atomic_number,
        symbol,
        name_fr,
        Decimal(weight) if weight is not None else None,
        display_mass_number,
        group,
        period,
    )


# Les masses viennent de la table CIAAW 2024. Les nombres entre crochets
# viennent du tableau IUPAC daté du 4 mai 2022 et ne sont pas des masses.
ELEMENTS: Final = (
    _element(1, "H", "hydrogène", "1.0080", None, 1, 1),
    _element(2, "He", "hélium", "4.0026", None, 18, 1),
    _element(3, "Li", "lithium", "6.94", None, 1, 2),
    _element(4, "Be", "béryllium", "9.0122", None, 2, 2),
    _element(5, "B", "bore", "10.81", None, 13, 2),
    _element(6, "C", "carbone", "12.011", None, 14, 2),
    _element(7, "N", "azote", "14.007", None, 15, 2),
    _element(8, "O", "oxygène", "15.999", None, 16, 2),
    _element(9, "F", "fluor", "18.998", None, 17, 2),
    _element(10, "Ne", "néon", "20.180", None, 18, 2),
    _element(11, "Na", "sodium", "22.990", None, 1, 3),
    _element(12, "Mg", "magnésium", "24.305", None, 2, 3),
    _element(13, "Al", "aluminium", "26.982", None, 13, 3),
    _element(14, "Si", "silicium", "28.085", None, 14, 3),
    _element(15, "P", "phosphore", "30.974", None, 15, 3),
    _element(16, "S", "soufre", "32.06", None, 16, 3),
    _element(17, "Cl", "chlore", "35.45", None, 17, 3),
    _element(18, "Ar", "argon", "39.95", None, 18, 3),
    _element(19, "K", "potassium", "39.098", None, 1, 4),
    _element(20, "Ca", "calcium", "40.078", None, 2, 4),
    _element(21, "Sc", "scandium", "44.956", None, 3, 4),
    _element(22, "Ti", "titane", "47.867", None, 4, 4),
    _element(23, "V", "vanadium", "50.942", None, 5, 4),
    _element(24, "Cr", "chrome", "51.996", None, 6, 4),
    _element(25, "Mn", "manganèse", "54.938", None, 7, 4),
    _element(26, "Fe", "fer", "55.845", None, 8, 4),
    _element(27, "Co", "cobalt", "58.933", None, 9, 4),
    _element(28, "Ni", "nickel", "58.693", None, 10, 4),
    _element(29, "Cu", "cuivre", "63.546", None, 11, 4),
    _element(30, "Zn", "zinc", "65.38", None, 12, 4),
    _element(31, "Ga", "gallium", "69.723", None, 13, 4),
    _element(32, "Ge", "germanium", "72.630", None, 14, 4),
    _element(33, "As", "arsenic", "74.922", None, 15, 4),
    _element(34, "Se", "sélénium", "78.971", None, 16, 4),
    _element(35, "Br", "brome", "79.904", None, 17, 4),
    _element(36, "Kr", "krypton", "83.798", None, 18, 4),
    _element(37, "Rb", "rubidium", "85.468", None, 1, 5),
    _element(38, "Sr", "strontium", "87.62", None, 2, 5),
    _element(39, "Y", "yttrium", "88.906", None, 3, 5),
    _element(40, "Zr", "zirconium", "91.222", None, 4, 5),
    _element(41, "Nb", "niobium", "92.906", None, 5, 5),
    _element(42, "Mo", "molybdène", "95.95", None, 6, 5),
    _element(43, "Tc", "technétium", None, 97, 7, 5),
    _element(44, "Ru", "ruthénium", "101.07", None, 8, 5),
    _element(45, "Rh", "rhodium", "102.91", None, 9, 5),
    _element(46, "Pd", "palladium", "106.42", None, 10, 5),
    _element(47, "Ag", "argent", "107.87", None, 11, 5),
    _element(48, "Cd", "cadmium", "112.41", None, 12, 5),
    _element(49, "In", "indium", "114.82", None, 13, 5),
    _element(50, "Sn", "étain", "118.71", None, 14, 5),
    _element(51, "Sb", "antimoine", "121.76", None, 15, 5),
    _element(52, "Te", "tellure", "127.60", None, 16, 5),
    _element(53, "I", "iode", "126.90", None, 17, 5),
    _element(54, "Xe", "xénon", "131.29", None, 18, 5),
    _element(55, "Cs", "césium", "132.91", None, 1, 6),
    _element(56, "Ba", "baryum", "137.33", None, 2, 6),
    _element(57, "La", "lanthane", "138.91", None, 3, 6),
    _element(58, "Ce", "cérium", "140.12", None, None, 6),
    _element(59, "Pr", "praséodyme", "140.91", None, None, 6),
    _element(60, "Nd", "néodyme", "144.24", None, None, 6),
    _element(61, "Pm", "prométhium", None, 145, None, 6),
    _element(62, "Sm", "samarium", "150.36", None, None, 6),
    _element(63, "Eu", "europium", "151.96", None, None, 6),
    _element(64, "Gd", "gadolinium", "157.25", None, None, 6),
    _element(65, "Tb", "terbium", "158.93", None, None, 6),
    _element(66, "Dy", "dysprosium", "162.50", None, None, 6),
    _element(67, "Ho", "holmium", "164.93", None, None, 6),
    _element(68, "Er", "erbium", "167.26", None, None, 6),
    _element(69, "Tm", "thulium", "168.93", None, None, 6),
    _element(70, "Yb", "ytterbium", "173.05", None, None, 6),
    _element(71, "Lu", "lutécium", "174.97", None, None, 6),
    _element(72, "Hf", "hafnium", "178.49", None, 4, 6),
    _element(73, "Ta", "tantale", "180.95", None, 5, 6),
    _element(74, "W", "tungstène", "183.84", None, 6, 6),
    _element(75, "Re", "rhénium", "186.21", None, 7, 6),
    _element(76, "Os", "osmium", "190.23", None, 8, 6),
    _element(77, "Ir", "iridium", "192.22", None, 9, 6),
    _element(78, "Pt", "platine", "195.08", None, 10, 6),
    _element(79, "Au", "or", "196.97", None, 11, 6),
    _element(80, "Hg", "mercure", "200.59", None, 12, 6),
    _element(81, "Tl", "thallium", "204.38", None, 13, 6),
    _element(82, "Pb", "plomb", "207.2", None, 14, 6),
    _element(83, "Bi", "bismuth", "208.98", None, 15, 6),
    _element(84, "Po", "polonium", None, 209, 16, 6),
    _element(85, "At", "astate", None, 210, 17, 6),
    _element(86, "Rn", "radon", None, 222, 18, 6),
    _element(87, "Fr", "francium", None, 223, 1, 7),
    _element(88, "Ra", "radium", None, 226, 2, 7),
    _element(89, "Ac", "actinium", None, 227, 3, 7),
    _element(90, "Th", "thorium", "232.04", None, None, 7),
    _element(91, "Pa", "protactinium", "231.04", None, None, 7),
    _element(92, "U", "uranium", "238.03", None, None, 7),
    _element(93, "Np", "neptunium", None, 237, None, 7),
    _element(94, "Pu", "plutonium", None, 244, None, 7),
    _element(95, "Am", "américium", None, 243, None, 7),
    _element(96, "Cm", "curium", None, 247, None, 7),
    _element(97, "Bk", "berkélium", None, 247, None, 7),
    _element(98, "Cf", "californium", None, 251, None, 7),
    _element(99, "Es", "einsteinium", None, 252, None, 7),
    _element(100, "Fm", "fermium", None, 257, None, 7),
    _element(101, "Md", "mendélévium", None, 258, None, 7),
    _element(102, "No", "nobélium", None, 259, None, 7),
    _element(103, "Lr", "lawrencium", None, 262, None, 7),
    _element(104, "Rf", "rutherfordium", None, 267, 4, 7),
    _element(105, "Db", "dubnium", None, 268, 5, 7),
    _element(106, "Sg", "seaborgium", None, 269, 6, 7),
    _element(107, "Bh", "bohrium", None, 270, 7, 7),
    _element(108, "Hs", "hassium", None, 269, 8, 7),
    _element(109, "Mt", "meitnérium", None, 277, 9, 7),
    _element(110, "Ds", "darmstadtium", None, 281, 10, 7),
    _element(111, "Rg", "roentgenium", None, 282, 11, 7),
    _element(112, "Cn", "copernicium", None, 285, 12, 7),
    _element(113, "Nh", "nihonium", None, 286, 13, 7),
    _element(114, "Fl", "flérovium", None, 290, 14, 7),
    _element(115, "Mc", "moscovium", None, 290, 15, 7),
    _element(116, "Lv", "livermorium", None, 293, 16, 7),
    _element(117, "Ts", "tennessine", None, 294, 17, 7),
    _element(118, "Og", "oganesson", None, 294, 18, 7),
)

_BY_SYMBOL: Final = MappingProxyType({element.symbol: element for element in ELEMENTS})


def element_by_symbol(symbol: str) -> AtomicElement:
    """Retourne un élément pour son symbole exact, sensible à la casse."""

    try:
        return _BY_SYMBOL[symbol]
    except KeyError as exc:
        raise AtomicDataError(f"Symbole chimique inconnu : {symbol!r}.") from exc


def iter_elements() -> Iterator[AtomicElement]:
    """Itère les éléments par numéro atomique croissant."""

    return iter(ELEMENTS)


def atomic_weight(symbol: str) -> Decimal:
    """Retourne la masse atomique standard disponible en g/mol."""

    element = element_by_symbol(symbol)
    if element.standard_atomic_weight is None:
        raise AtomicDataError(
            f"Aucune masse atomique standard n'est disponible pour {element.symbol}."
        )
    return element.standard_atomic_weight


def format_atomic_weight(element: AtomicElement) -> str:
    """Formate une masse pour l'affichage, jamais pour le calcul."""

    if element.standard_atomic_weight is None:
        return f"[{element.display_mass_number}]"
    return format(element.standard_atomic_weight, ".3g")
