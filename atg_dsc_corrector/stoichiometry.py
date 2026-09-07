"""Analyse minimale de formules et d'équations chimiques neutres."""

from dataclasses import dataclass, replace
from decimal import Decimal, DecimalException
from fractions import Fraction
from math import gcd, lcm
from types import MappingProxyType
from typing import Final, Mapping

from .atomic_data import SOURCE_ID, AtomicDataError, atomic_weight, element_by_symbol


MAX_INPUT_LENGTH: Final = 1_000
MAX_NESTING_DEPTH: Final = 32
MAX_INTEGER: Final = 1_000_000
MASS_UNIT_TO_GRAMS: Final = MappingProxyType(
    {"µg": Decimal("1e-6"), "mg": Decimal("1e-3"), "g": Decimal(1)}
)
# NIST CODATA 2022 and exact SI pressure definitions.
IDEAL_GAS_CONSTANT: Final = Decimal("8.31446261815324")
PRESSURE_UNIT_TO_PASCALS: Final = MappingProxyType(
    {"mbar": Decimal(100), "bar": Decimal(100_000), "atm": Decimal(101_325)}
)
VOLUME_UNIT_TO_CUBIC_METRES: Final = MappingProxyType(
    {"mL": Decimal("1e-6"), "L": Decimal("1e-3")}
)
CELSIUS_ZERO_IN_KELVIN: Final = Decimal("273.15")
NUMERIC_RELATIVE_TOLERANCE: Final = Decimal("1e-24")


class StoichiometryError(ValueError):
    """Erreur localisée dans une saisie chimique."""

    def __init__(self, message: str, source: str, position: int) -> None:
        self.position = max(0, min(position, len(source)))
        self.fragment = source[self.position : self.position + 12] or "<fin>"
        super().__init__(
            f"{message} Position {self.position + 1}, près de {self.fragment!r}."
        )


class BalanceError(ValueError):
    """Une équation ne possède pas une solution automatique unique admissible."""


class MassBalanceError(ValueError):
    """Les entrées ne permettent pas un bilan massique condensé valide."""


@dataclass(frozen=True)
class ChemicalSpecies:
    coefficient: Fraction
    formula: str
    state: str
    composition: Mapping[str, int]
    molar_mass: Decimal


@dataclass(frozen=True)
class ChemicalEquation:
    reactants: tuple[ChemicalSpecies, ...]
    products: tuple[ChemicalSpecies, ...]


@dataclass(frozen=True)
class MassValue:
    value: object
    unit: str


@dataclass(frozen=True)
class IdealGasConditions:
    pressure: object
    pressure_unit: str
    volume: object
    volume_unit: str
    temperature: object
    temperature_unit: str


@dataclass(frozen=True)
class GasByPartialPressure:
    conditions: IdealGasConditions


@dataclass(frozen=True)
class GasByFraction:
    value: object
    kind: str
    conditions: IdealGasConditions


@dataclass(frozen=True)
class ExcessGas:
    pass


@dataclass(frozen=True)
class IndividualMasses:
    values: tuple[object, ...]


@dataclass(frozen=True)
class StoichiometricTotalMass:
    value: MassValue
    gas_inputs: tuple[object, ...] = ()


@dataclass(frozen=True)
class SpeciesMassBalance:
    species: ChemicalSpecies
    initial_amount_mol: Decimal | None
    consumed_amount_mol: Decimal
    consumed_mass_g: Decimal
    produced_amount_mol: Decimal
    final_amount_mol: Decimal | None
    initial_mass_g: Decimal | None
    produced_mass_g: Decimal
    final_mass_g: Decimal | None
    initial_mass_fraction: Decimal | None
    input_mode: str | None = None


@dataclass(frozen=True)
class CondensedMassBalance:
    equation: ChemicalEquation
    equation_text: str
    atomic_data_source_id: str
    input_mode: str
    extent_mol: Decimal
    limiting_reactant_indices: tuple[int, ...]
    reactants: tuple[SpeciesMassBalance, ...]
    products: tuple[SpeciesMassBalance, ...]
    initial_condensed_mass_g: Decimal
    final_condensed_mass_g: Decimal
    delta_mass_g: Decimal
    variation_percent: Decimal
    direction: str
    magnitude_g: Decimal
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]


def _error(message: str, source: str, position: int) -> StoichiometryError:
    return StoichiometryError(message, source, position)


def _is_ascii_digit(character: str) -> bool:
    return "0" <= character <= "9"


def _bounded_positive_integer(
    digits: str,
    source: str,
    position: int,
    label: str,
) -> int:
    if not digits:
        raise _error(f"{label} attendu.", source, position)
    if len(digits) > len(str(MAX_INTEGER)):
        raise _error(f"{label} supérieur à {MAX_INTEGER}.", source, position)
    value = int(digits)
    if value <= 0:
        raise _error(f"{label} doit être strictement positif.", source, position)
    if value > MAX_INTEGER:
        raise _error(f"{label} supérieur à {MAX_INTEGER}.", source, position)
    return value


class _FormulaParser:
    def __init__(self, text: str, source: str, offset: int) -> None:
        self.text = text
        self.source = source
        self.offset = offset
        self.position = 0

    def parse(self) -> dict[str, int]:
        composition = self._parse_sequence(None, 0)
        if self.position != len(self.text):
            raise self._error("Caractère inattendu.", self.position)
        return composition

    def _parse_sequence(
        self, closing: str | None, depth: int
    ) -> dict[str, int]:
        composition: dict[str, int] = {}
        found_term = False
        while self.position < len(self.text):
            character = self.text[self.position]
            if character in ")]":
                if character == closing:
                    break
                expected = closing or "aucune fermeture"
                raise self._error(
                    f"Fermeture {character!r} inattendue, attendu : {expected!r}.",
                    self.position,
                )
            if character.isupper():
                self._parse_element(composition)
                found_term = True
                continue
            if character in "([":
                self._parse_group(composition, depth)
                found_term = True
                continue
            if character.isspace():
                raise self._error(
                    "Les espaces ne sont pas admis dans une formule.", self.position
                )
            raise self._error(f"Caractère interdit : {character!r}.", self.position)
        if not found_term:
            raise self._error("Un groupe chimique ne peut pas être vide.", self.position)
        return composition

    def _parse_element(self, composition: dict[str, int]) -> None:
        start = self.position
        self.position += 1
        if self.position < len(self.text) and self.text[self.position].islower():
            self.position += 1
        symbol = self.text[start : self.position]
        try:
            element = element_by_symbol(symbol)
        except AtomicDataError as exc:
            raise self._error(f"Symbole chimique inconnu : {symbol!r}.", start) from exc
        if element.standard_atomic_weight is None:
            raise self._error(
                f"Aucune masse atomique standard n'est disponible pour {symbol}.",
                start,
            )
        count = self._parse_count()
        composition[symbol] = composition.get(symbol, 0) + count

    def _parse_group(self, composition: dict[str, int], depth: int) -> None:
        opening_position = self.position
        opening = self.text[self.position]
        closing = ")" if opening == "(" else "]"
        if depth >= MAX_NESTING_DEPTH:
            raise self._error(
                f"Profondeur maximale de {MAX_NESTING_DEPTH} groupes dépassée.",
                opening_position,
            )
        self.position += 1
        nested = self._parse_sequence(closing, depth + 1)
        if self.position >= len(self.text):
            raise self._error(
                f"Groupe {opening!r} non fermé par {closing!r}.", opening_position
            )
        self.position += 1
        multiplier = self._parse_count()
        for symbol, count in nested.items():
            composition[symbol] = composition.get(symbol, 0) + count * multiplier

    def _parse_count(self) -> int:
        start = self.position
        while self.position < len(self.text) and _is_ascii_digit(
            self.text[self.position]
        ):
            self.position += 1
        if self.position == start:
            return 1
        return _bounded_positive_integer(
            self.text[start : self.position],
            self.source,
            self.offset + start,
            "L'indice",
        )

    def _error(self, message: str, position: int) -> StoichiometryError:
        return _error(message, self.source, self.offset + position)


def _check_length(text: str) -> None:
    if len(text) > MAX_INPUT_LENGTH:
        raise _error(
            f"La saisie dépasse la limite de {MAX_INPUT_LENGTH} caractères.",
            text,
            MAX_INPUT_LENGTH,
        )


def _parse_species(text: str, source: str, offset: int) -> ChemicalSpecies:
    leading_spaces = len(text) - len(text.lstrip())
    body = text.strip()
    body_offset = offset + leading_spaces
    if not body:
        raise _error("Une espèce chimique est attendue.", source, body_offset)

    position = 0
    coefficient = Fraction(1)
    if body[0] in "-.":
        raise _error(
            "Le coefficient doit être un entier positif ou une fraction positive.",
            source,
            body_offset,
        )
    if _is_ascii_digit(body[0]):
        start = position
        while position < len(body) and _is_ascii_digit(body[position]):
            position += 1
        numerator = _bounded_positive_integer(
            body[start:position], source, body_offset + start, "Le coefficient"
        )
        denominator = 1
        if position < len(body) and body[position] == "/":
            denominator_position = position + 1
            position += 1
            start = position
            while position < len(body) and _is_ascii_digit(body[position]):
                position += 1
            denominator = _bounded_positive_integer(
                body[start:position],
                source,
                body_offset + denominator_position,
                "Le dénominateur",
            )
        if position < len(body) and body[position] == ".":
            raise _error(
                "Les coefficients décimaux ne sont pas admis.",
                source,
                body_offset + position,
            )
        coefficient = Fraction(numerator, denominator)
        while position < len(body) and body[position].isspace():
            position += 1

    formula_and_state = body[position:]
    formula_offset = body_offset + position
    state = "s"
    if formula_and_state.endswith(("(s)", "(l)", "(g)")):
        state = formula_and_state[-2]
        formula = formula_and_state[:-3]
    else:
        formula = formula_and_state
    if not formula:
        raise _error("Une formule chimique est attendue.", source, formula_offset)

    composition = _FormulaParser(formula, source, formula_offset).parse()
    molar_mass = sum(
        (atomic_weight(symbol) * count for symbol, count in composition.items()),
        Decimal(0),
    )
    return ChemicalSpecies(
        coefficient=coefficient,
        formula=formula,
        state=state,
        composition=MappingProxyType(composition),
        molar_mass=molar_mass,
    )


def parse_species(text: str) -> ChemicalSpecies:
    """Analyse une espèce et consomme toute la chaîne."""

    _check_length(text)
    return _parse_species(text, text, 0)


def _parse_side(text: str, source: str, offset: int) -> tuple[ChemicalSpecies, ...]:
    species = []
    start = 0
    for end in (*[index for index, value in enumerate(text) if value == "+"], len(text)):
        part = text[start:end]
        species.append(_parse_species(part, source, offset + start))
        start = end + 1
    return tuple(species)


def parse_equation(text: str) -> ChemicalEquation:
    """Analyse une équation neutre possédant exactement un signe égal."""

    _check_length(text)
    if text.count("=") != 1:
        position = text.find("=", text.find("=") + 1) if "=" in text else len(text)
        raise _error("Une équation doit contenir exactement un signe '='.", text, position)
    separator = text.index("=")
    if not text[:separator].strip():
        raise _error("Le côté réactifs est vide.", text, 0)
    if not text[separator + 1 :].strip():
        raise _error("Le côté produits est vide.", text, separator + 1)
    return ChemicalEquation(
        reactants=_parse_side(text[:separator], text, 0),
        products=_parse_side(text[separator + 1 :], text, separator + 1),
    )


def element_residuals(equation: ChemicalEquation) -> Mapping[str, Fraction]:
    """Retourne, par élément, le bilan exact réactifs moins produits."""

    residuals: dict[str, Fraction] = {}
    for sign, species_list in ((1, equation.reactants), (-1, equation.products)):
        for species in species_list:
            for symbol, count in species.composition.items():
                residuals.setdefault(symbol, Fraction(0))
                residuals[symbol] += sign * species.coefficient * count
    return MappingProxyType(residuals)


def is_balanced(equation: ChemicalEquation) -> bool:
    """Vérifie la conservation atomique sans tolérance flottante."""

    return all(residual == 0 for residual in element_residuals(equation).values())


def _conservation_matrix(equation: ChemicalEquation) -> list[list[Fraction]]:
    species = (*equation.reactants, *equation.products)
    symbols = tuple(
        dict.fromkeys(
            symbol
            for item in species
            for symbol in item.composition
        )
    )
    reactant_count = len(equation.reactants)
    return [
        [
            Fraction(item.composition.get(symbol, 0))
            * (1 if column < reactant_count else -1)
            for column, item in enumerate(species)
        ]
        for symbol in symbols
    ]


def _reduced_row_echelon(
    matrix: list[list[Fraction]],
) -> tuple[list[list[Fraction]], tuple[int, ...]]:
    rows = [row.copy() for row in matrix]
    pivot_columns = []
    pivot_row = 0
    for column in range(len(rows[0])):
        selected = next(
            (row for row in range(pivot_row, len(rows)) if rows[row][column]),
            None,
        )
        if selected is None:
            continue
        rows[pivot_row], rows[selected] = rows[selected], rows[pivot_row]
        pivot = rows[pivot_row][column]
        rows[pivot_row] = [value / pivot for value in rows[pivot_row]]
        for row, values in enumerate(rows):
            if row == pivot_row or not values[column]:
                continue
            factor = values[column]
            rows[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(values, rows[pivot_row])
            ]
        pivot_columns.append(column)
        pivot_row += 1
        if pivot_row == len(rows):
            break
    return rows, tuple(pivot_columns)


def _smallest_integer_coefficients(
    equation: ChemicalEquation,
    *,
    preserve_reactant_ratios: bool = False,
) -> tuple[int, ...]:
    matrix = _conservation_matrix(equation)
    if preserve_reactant_ratios:
        for index, species in enumerate(equation.reactants[1:], start=1):
            constraint = [Fraction(0) for _ in matrix[0]]
            constraint[0] = species.coefficient
            constraint[index] = -equation.reactants[0].coefficient
            matrix.append(constraint)
    matrix, pivot_columns = _reduced_row_echelon(matrix)
    column_count = len(matrix[0])
    free_columns = [
        column for column in range(column_count) if column not in pivot_columns
    ]
    if not free_columns:
        raise BalanceError("Cette équation ne possède aucune solution non nulle.")
    if len(free_columns) != 1:
        raise BalanceError(
            "Cette équation est sous-déterminée : plusieurs familles de coefficients existent."
        )

    free_column = free_columns[0]
    vector = [Fraction(0) for _ in range(column_count)]
    vector[free_column] = Fraction(1)
    for row, pivot_column in enumerate(pivot_columns):
        vector[pivot_column] = -matrix[row][free_column]
    if all(value < 0 for value in vector):
        vector = [-value for value in vector]
    if any(value <= 0 for value in vector):
        raise BalanceError(
            "L'équilibrage exige un coefficient nul ou négatif."
        )

    common_denominator = 1
    for value in vector:
        common_denominator = lcm(common_denominator, value.denominator)
    integers = [
        value.numerator * (common_denominator // value.denominator)
        for value in vector
    ]
    common_divisor = 0
    for value in integers:
        common_divisor = gcd(common_divisor, abs(value))
    normalized = tuple(value // common_divisor for value in integers)
    if any(value > MAX_INTEGER for value in normalized):
        raise BalanceError(
            f"Un coefficient équilibré dépasse la limite de {MAX_INTEGER}."
        )
    return normalized


def balance_equation(
    equation: ChemicalEquation, *, preserve_reactant_ratios: bool = False
) -> ChemicalEquation:
    """Équilibre exactement, en conservant les rapports réactifs sur demande.

    Les coefficients produits saisis restent libres. Le résultat possède les
    plus petits coefficients entiers positifs ; une ambiguïté reste une erreur.
    """

    coefficients = _smallest_integer_coefficients(
        equation, preserve_reactant_ratios=preserve_reactant_ratios
    )
    reactant_count = len(equation.reactants)
    species = (*equation.reactants, *equation.products)
    balanced = tuple(
        replace(item, coefficient=Fraction(coefficient))
        for item, coefficient in zip(species, coefficients)
    )
    return ChemicalEquation(
        reactants=balanced[:reactant_count],
        products=balanced[reactant_count:],
    )


def _format_species(species: ChemicalSpecies) -> str:
    coefficient = species.coefficient
    if coefficient == 1:
        prefix = ""
    elif coefficient.denominator == 1:
        prefix = f"{coefficient.numerator} "
    else:
        prefix = f"{coefficient.numerator}/{coefficient.denominator} "
    state = "" if species.state == "s" else f"({species.state})"
    return f"{prefix}{species.formula}{state}"


def format_equation(equation: ChemicalEquation) -> str:
    """Produit une représentation canonique sans muter l'équation."""

    reactants = " + ".join(_format_species(item) for item in equation.reactants)
    products = " + ".join(_format_species(item) for item in equation.products)
    return f"{reactants} = {products}"


def _fraction_to_decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def _mass_in_grams(value: MassValue, label: str) -> Decimal:
    if value.unit not in MASS_UNIT_TO_GRAMS:
        raise MassBalanceError(
            f"Unité invalide pour {label} : {value.unit!r}. Utilisez µg, mg ou g."
        )
    try:
        mass = Decimal(str(value.value))
    except (DecimalException, ValueError) as exc:
        raise MassBalanceError(f"Masse non numérique pour {label}.") from exc
    if not mass.is_finite() or mass <= 0:
        raise MassBalanceError(
            f"La masse de {label} doit être finie et strictement positive."
        )
    try:
        return mass * MASS_UNIT_TO_GRAMS[value.unit]
    except DecimalException as exc:
        raise MassBalanceError(f"Masse hors limites pour {label}.") from exc


def _finite_decimal(value: object, label: str) -> Decimal:
    if value is None:
        raise MassBalanceError(f"Donnée requise manquante pour {label}.")
    try:
        result = Decimal(str(value))
    except (DecimalException, ValueError) as exc:
        raise MassBalanceError(f"Valeur non numérique pour {label}.") from exc
    if not result.is_finite():
        raise MassBalanceError(f"La valeur de {label} doit être finie.")
    return result


def _converted_positive_value(
    value: object,
    unit: str,
    conversions: Mapping[str, Decimal],
    label: str,
    allowed_units: str,
) -> Decimal:
    if unit is None or unit == "":
        raise MassBalanceError(f"Unité requise pour {label}.")
    if unit not in conversions:
        raise MassBalanceError(
            f"Unité invalide pour {label} : {unit!r}. Utilisez {allowed_units}."
        )
    number = _finite_decimal(value, label)
    if number <= 0:
        raise MassBalanceError(
            f"La valeur de {label} doit être strictement positive."
        )
    try:
        return number * conversions[unit]
    except DecimalException as exc:
        raise MassBalanceError(f"Valeur hors limites pour {label}.") from exc


def _temperature_in_kelvins(value: object, unit: str) -> Decimal:
    if unit is None or unit == "":
        raise MassBalanceError("Unité requise pour la température.")
    if unit not in {"°C", "K"}:
        raise MassBalanceError(
            f"Unité invalide pour la température : {unit!r}. Utilisez °C ou K."
        )
    temperature = _finite_decimal(value, "la température")
    try:
        kelvins = temperature + CELSIUS_ZERO_IN_KELVIN if unit == "°C" else temperature
    except DecimalException as exc:
        raise MassBalanceError("Température hors limites.") from exc
    if not kelvins.is_finite() or kelvins <= 0:
        raise MassBalanceError("La température doit être strictement supérieure à 0 K.")
    return kelvins


def _ideal_gas_amount(
    conditions: IdealGasConditions,
    *,
    pressure_fraction: Decimal = Decimal(1),
    pressure_label: str,
) -> Decimal:
    if not isinstance(conditions, IdealGasConditions):
        raise MassBalanceError(
            "La pression, le volume et la température sont requis pour le gaz."
        )
    pressure = _converted_positive_value(
        conditions.pressure,
        conditions.pressure_unit,
        PRESSURE_UNIT_TO_PASCALS,
        pressure_label,
        "mbar, bar ou atm",
    )
    volume = _converted_positive_value(
        conditions.volume,
        conditions.volume_unit,
        VOLUME_UNIT_TO_CUBIC_METRES,
        "le volume",
        "mL ou L",
    )
    temperature = _temperature_in_kelvins(
        conditions.temperature, conditions.temperature_unit
    )
    try:
        amount = pressure * pressure_fraction * volume / (
            IDEAL_GAS_CONSTANT * temperature
        )
    except DecimalException as exc:
        raise MassBalanceError("Conditions gazeuses hors limites.") from exc
    if not amount.is_finite() or amount <= 0:
        raise MassBalanceError(
            "Les conditions gazeuses doivent donner une quantité finie et positive."
        )
    return amount


def _gas_mass_from_amount(amount: Decimal, species: ChemicalSpecies) -> Decimal:
    try:
        mass = amount * species.molar_mass
    except DecimalException as exc:
        raise MassBalanceError(
            f"Quantité gazeuse hors limites pour {species.formula}."
        ) from exc
    if not mass.is_finite() or mass <= 0:
        raise MassBalanceError(
            f"La quantité gazeuse de {species.formula} doit donner une masse finie."
        )
    return mass


def _gas_initial_state(
    value: object, species: ChemicalSpecies, index: int
) -> tuple[Decimal | None, Decimal | None, str]:
    label = f"le réactif {index + 1} ({species.formula})"
    if isinstance(value, MassValue):
        mass = _mass_in_grams(value, label)
        return mass, mass / species.molar_mass, "mass"
    if isinstance(value, GasByPartialPressure):
        amount = _ideal_gas_amount(
            value.conditions, pressure_label="la pression partielle"
        )
        return _gas_mass_from_amount(amount, species), amount, "partial_pressure"
    if isinstance(value, GasByFraction):
        if value.kind == "ppm":
            raise MassBalanceError(
                "Le type générique 'ppm' est ambigu ; utilisez 'molar_ppm' ou 'ppmv'."
            )
        if value.kind not in {"molar_ppm", "ppmv"}:
            raise MassBalanceError(
                "Type de fraction gazeuse invalide ; utilisez 'molar_ppm' ou 'ppmv'."
            )
        fraction_value = _finite_decimal(value.value, "la fraction gazeuse")
        if fraction_value <= 0 or fraction_value > Decimal(1_000_000):
            raise MassBalanceError(
                "La fraction gazeuse doit être supérieure à 0 et au plus égale à 1 000 000."
            )
        amount = _ideal_gas_amount(
            value.conditions,
            pressure_fraction=fraction_value * Decimal("1e-6"),
            pressure_label="la pression totale",
        )
        return _gas_mass_from_amount(amount, species), amount, value.kind
    if isinstance(value, ExcessGas):
        return None, None, "excess"
    raise MassBalanceError(
        f"Mode gazeux invalide pour {label} : masse, pression partielle, "
        "fraction molaire/volumique ou excès attendu."
    )


def _clamp_near_zero(value: Decimal, scale: Decimal) -> Decimal:
    tolerance = max(Decimal("1e-30"), abs(scale) * NUMERIC_RELATIVE_TOLERANCE)
    return Decimal(0) if abs(value) <= tolerance else value


def _validate_condensed_reaction(equation: ChemicalEquation) -> None:
    if not is_balanced(equation):
        residues = ", ".join(
            f"{symbol}={value}"
            for symbol, value in element_residuals(equation).items()
            if value
        )
        raise MassBalanceError(f"L'équation n'est pas équilibrée : {residues}.")


def _individual_initial_state(equation: ChemicalEquation, values: tuple[object, ...]):
    if len(values) != len(equation.reactants):
        raise MassBalanceError(
            "Une entrée individuelle est requise pour chaque réactif."
        )
    masses = []
    amounts = []
    modes = []
    for index, (species, value) in enumerate(zip(equation.reactants, values)):
        if species.state == "g":
            mass, amount, mode = _gas_initial_state(value, species, index)
        else:
            if not isinstance(value, MassValue):
                raise MassBalanceError(
                    f"Une masse est requise pour le réactif condensé {index + 1} "
                    f"({species.formula})."
                )
            mass = _mass_in_grams(
                value, f"le réactif {index + 1} ({species.formula})"
            )
            amount = mass / species.molar_mass
            mode = "mass"
        masses.append(mass)
        amounts.append(amount)
        modes.append(mode)
    return (
        tuple(masses),
        tuple(amounts),
        tuple(None for _ in masses),
        tuple(modes),
    )


def _stoichiometric_initial_state(
    equation: ChemicalEquation, inputs: StoichiometricTotalMass
):
    condensed_indices = tuple(
        index
        for index, species in enumerate(equation.reactants)
        if species.state in {"s", "l"}
    )
    gaseous_indices = tuple(
        index for index, species in enumerate(equation.reactants) if species.state == "g"
    )
    if not condensed_indices:
        raise MassBalanceError(
            "Le mode masse totale requiert au moins un réactif condensé."
        )
    if len(inputs.gas_inputs) != len(gaseous_indices):
        raise MassBalanceError(
            "Une entrée gazeuse séparée est requise pour chaque réactif gazeux."
        )
    total_mass = _mass_in_grams(inputs.value, "la masse totale")
    contributions = tuple(
        _fraction_to_decimal(equation.reactants[index].coefficient)
        * equation.reactants[index].molar_mass
        for index in condensed_indices
    )
    contribution_sum = sum(contributions, Decimal(0))
    condensed_extent = total_mass / contribution_sum
    masses: list[Decimal | None] = [None] * len(equation.reactants)
    amounts: list[Decimal | None] = [None] * len(equation.reactants)
    fractions: list[Decimal | None] = [None] * len(equation.reactants)
    modes = ["stoichiometric_total"] * len(equation.reactants)
    for index, contribution in zip(condensed_indices, contributions):
        species = equation.reactants[index]
        amount = _fraction_to_decimal(species.coefficient) * condensed_extent
        masses[index] = amount * species.molar_mass
        amounts[index] = amount
        fractions[index] = contribution / contribution_sum
    for index, value in zip(gaseous_indices, inputs.gas_inputs):
        mass, amount, mode = _gas_initial_state(
            value, equation.reactants[index], index
        )
        masses[index] = mass
        amounts[index] = amount
        modes[index] = mode
    return tuple(masses), tuple(amounts), tuple(fractions), tuple(modes), condensed_extent


def calculate_condensed_mass_balance(
    equation: ChemicalEquation,
    inputs: IndividualMasses | StoichiometricTotalMass,
) -> CondensedMassBalance:
    """Calcule le maximum théorique et le bilan de la matière condensée."""

    _validate_condensed_reaction(equation)
    condensed_extent = None
    if isinstance(inputs, IndividualMasses):
        input_mode = "individual"
        initial_masses, initial_amounts, mass_fractions, species_input_modes = (
            _individual_initial_state(equation, inputs.values)
        )
    elif isinstance(inputs, StoichiometricTotalMass):
        input_mode = "stoichiometric_total"
        initial_masses, initial_amounts, mass_fractions, species_input_modes, condensed_extent = (
            _stoichiometric_initial_state(equation, inputs)
        )
    else:
        raise MassBalanceError(
            "Choisissez explicitement les masses individuelles ou la masse totale."
        )

    candidate_extents = tuple(
        (
            index,
            # Preserve the shared extent instead of rounding multiply/divide again.
            condensed_extent if condensed_extent is not None and species.state in {"s", "l"}
            else amount / _fraction_to_decimal(species.coefficient),
        )
        for index, (amount, species) in enumerate(
            zip(initial_amounts, equation.reactants)
        )
        if amount is not None
    )
    if not candidate_extents:
        raise MassBalanceError(
            "Au moins un réactif doit être fini ; tous les réactifs gazeux "
            "ne peuvent pas être en excès."
        )
    extent = min(candidate for _, candidate in candidate_extents)
    limiting_indices = tuple(
        index for index, candidate in candidate_extents if candidate == extent
    )
    if extent <= 0:
        raise MassBalanceError("Aucun avancement strictement positif n'est disponible.")

    reactant_details = []
    for species, initial_amount, initial_mass, fraction, species_input_mode in zip(
        equation.reactants,
        initial_amounts,
        initial_masses,
        mass_fractions,
        species_input_modes,
    ):
        consumed = _fraction_to_decimal(species.coefficient) * extent
        consumed_mass = consumed * species.molar_mass
        if initial_amount is None:
            final_amount = None
            final_mass = None
        else:
            final_amount = _clamp_near_zero(
                initial_amount - consumed, initial_amount
            )
            final_mass = final_amount * species.molar_mass
        reactant_details.append(
            SpeciesMassBalance(
                species=species,
                initial_amount_mol=initial_amount,
                consumed_amount_mol=consumed,
                consumed_mass_g=consumed_mass,
                produced_amount_mol=Decimal(0),
                final_amount_mol=final_amount,
                initial_mass_g=initial_mass,
                produced_mass_g=Decimal(0),
                final_mass_g=final_mass,
                initial_mass_fraction=fraction,
                input_mode=species_input_mode,
            )
        )

    product_details = []
    for species in equation.products:
        produced = _fraction_to_decimal(species.coefficient) * extent
        produced_mass = produced * species.molar_mass
        product_details.append(
            SpeciesMassBalance(
                species=species,
                initial_amount_mol=Decimal(0),
                consumed_amount_mol=Decimal(0),
                consumed_mass_g=Decimal(0),
                produced_amount_mol=produced,
                final_amount_mol=produced,
                initial_mass_g=Decimal(0),
                produced_mass_g=produced_mass,
                final_mass_g=produced_mass,
                initial_mass_fraction=None,
            )
        )

    initial_condensed_mass = sum(
        (
            mass
            for species, mass in zip(equation.reactants, initial_masses)
            if species.state in {"s", "l"} and mass is not None
        ),
        Decimal(0),
    )
    if initial_condensed_mass <= 0:
        raise MassBalanceError(
            "Le bilan condensé requiert au moins un réactif solide ou liquide."
        )
    condensed_reactant_mass = sum(
        (
            _fraction_to_decimal(species.coefficient) * species.molar_mass
            for species in equation.reactants
            if species.state in {"s", "l"}
        ),
        Decimal(0),
    )
    condensed_product_mass = sum(
        (
            _fraction_to_decimal(species.coefficient) * species.molar_mass
            for species in equation.products
            if species.state in {"s", "l"}
        ),
        Decimal(0),
    )
    delta_mass = _clamp_near_zero(
        extent * (condensed_product_mass - condensed_reactant_mass),
        initial_condensed_mass,
    )
    final_condensed_mass = initial_condensed_mass + delta_mass
    variation_percent = Decimal(100) * delta_mass / initial_condensed_mass
    direction = (
        "gain" if delta_mass > 0 else "perte" if delta_mass < 0 else "inchangée"
    )
    assumptions = (
        "Réaction théorique complète jusqu'au réactif limitant.",
        "Phases (s) et (l) retenues ; produits (g) entièrement dégagés.",
        "Delta m = masse finale condensée - masse initiale condensée.",
    )
    if input_mode == "stoichiometric_total":
        assumptions += (
            "Mélange condensé initial exactement stœchiométrique.",
        )
    gas_modes = {
        mode
        for species, mode in zip(equation.reactants, species_input_modes)
        if species.state == "g"
    }
    if gas_modes & {"partial_pressure", "molar_ppm", "ppmv"}:
        assumptions += (
            "Gaz parfait : pression absolue, température uniforme et volume disponible.",
        )
    if gas_modes & {"molar_ppm", "ppmv"}:
        assumptions += (
            "Sous le modèle du gaz parfait, ppm molaire et ppmv valent une fraction de 10^-6.",
        )
    if "excess" in gas_modes:
        assumptions += (
            "Un gaz déclaré en excès ne limite pas l'avancement.",
        )
    return CondensedMassBalance(
        equation=equation,
        equation_text=format_equation(equation),
        atomic_data_source_id=SOURCE_ID,
        input_mode=input_mode,
        extent_mol=extent,
        limiting_reactant_indices=limiting_indices,
        reactants=tuple(reactant_details),
        products=tuple(product_details),
        initial_condensed_mass_g=initial_condensed_mass,
        final_condensed_mass_g=final_condensed_mass,
        delta_mass_g=delta_mass,
        variation_percent=variation_percent,
        direction=direction,
        magnitude_g=abs(delta_mass),
        assumptions=assumptions,
        warnings=(),
    )
