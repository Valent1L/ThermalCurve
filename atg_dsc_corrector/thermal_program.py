"""Programme de consigne indépendant des températures expérimentales mesurées."""

from __future__ import annotations

import math
import re

from .i18n import tr as _t


def parse_duration(text: str) -> float:
    """Durée signée hh:mm:ss en minutes, sans limite à 24 heures."""
    match = re.fullmatch(r"(-?)(\d+):(\d{2,}):(\d{2,}(?:[.,]\d+)?)", text.strip())
    if match is None:
        raise ValueError(_t('Saisir une durée au format hh:mm:ss.'))
    sign, hours, minutes, seconds = match.groups()
    try:
        value = float(hours) * 60 + int(minutes) + float(seconds.replace(",", ".")) / 60
    except OverflowError:
        value = math.inf
    if not math.isfinite(value):
        raise ValueError(_t('La durée doit être finie et strictement positive.'))
    return -value if sign else value


def format_duration(minutes: float) -> str:
    seconds = round(abs(minutes) * 60, 9)
    hours, seconds = divmod(seconds, 3600)
    minutes_part, seconds = divmod(seconds, 60)
    seconds_text = f"{seconds:012.9f}".rstrip("0").rstrip(".")
    return f"{'-' if minutes < 0 else ''}{int(hours):02d}:{int(minutes_part):02d}:{seconds_text}"


def default_thermal_program() -> dict:
    return {
        "enabled": False,
        "temperature_unit": "°C",
        "t0_min": 0.0,
        "initial_temperature_c": 20.0,
        "segments": [],
    }


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(_t('{name} doit être un nombre fini.', name=name))
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    if not math.isfinite(number):
        raise ValueError(_t('{name} doit être un nombre fini.', name=name))
    return number


def segment_duration(kind: str, start: float, end: float, rate: float | None,
                     duration: float | None) -> float:
    """Valide un segment et calcule sa durée en minutes."""
    start = _number(start, "T_ini")
    end = _number(end, "T_f")
    if min(start, end) < -273.15:
        raise ValueError(_t('La température doit être supérieure ou égale à 0 K.'))
    if kind == "hold":
        if end != start:
            raise ValueError(_t('Un palier doit conserver la même température.'))
        result = _number(duration, _t('Temps'))
    elif kind in ("heating", "cooling"):
        beta = _number(rate, "β")
        if beta <= 0:
            raise ValueError(_t('β doit être strictement positif.'))
        if (kind == "heating" and end <= start) or (kind == "cooling" and end >= start):
            raise ValueError(_t('T_f doit respecter le sens de la montée ou de la descente.'))
        result = abs(end - start) / beta
    else:
        raise ValueError(_t('Type de segment thermique inconnu.'))
    if not math.isfinite(result) or result <= 0:
        raise ValueError(_t('La durée doit être finie et strictement positive.'))
    return result


def validate_thermal_program(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError(_t('Programme thermique invalide.'))
    enabled = value.get("enabled", False)
    unit = value.get("temperature_unit", "°C")
    if not isinstance(enabled, bool) or unit not in ("°C", "K"):
        raise ValueError(_t('Programme thermique invalide.'))
    t0 = _number(value.get("t0_min", 0.0), "t₀")
    initial = _number(value.get("initial_temperature_c", 20.0), "T_ini")
    if initial < -273.15:
        raise ValueError(_t('La température doit être supérieure ou égale à 0 K.'))
    segments = value.get("segments", [])
    if not isinstance(segments, list):
        raise ValueError(_t('Programme thermique invalide.'))
    checked = []
    start, elapsed = initial, t0
    for index, item in enumerate(segments, 1):
        try:
            if not isinstance(item, dict):
                raise ValueError(_t('Programme thermique invalide.'))
            kind = item.get("type")
            end = start if kind == "hold" else _number(item.get("target_temperature_c"), "T_f")
            duration = segment_duration(kind, start, end, item.get("rate_c_per_min"), item.get("duration_min"))
            next_time = elapsed + duration
            if not math.isfinite(next_time * 60) or next_time <= elapsed:
                raise ValueError(_t('La durée cumulée du programme est invalide.'))
            segment = {"type": kind}
            if kind == "hold":
                segment["duration_min"] = duration
            else:
                segment.update(target_temperature_c=end, rate_c_per_min=float(item["rate_c_per_min"]))
            checked.append(segment)
            start, elapsed = end, next_time
        except ValueError as exc:
            raise ValueError(_t('Ligne {row} : {error}', row=index, error=str(exc))) from exc
    if enabled and not checked:
        raise ValueError(_t('Ajouter au moins une ligne pour afficher le programme thermique.'))
    return dict(enabled=enabled, temperature_unit=unit, t0_min=t0,
                initial_temperature_c=initial, segments=checked)


def thermal_program_points(program: dict) -> tuple[list[float], list[float]]:
    """Sommets (minutes, °C) ; aucun rééchantillonnage des mesures."""
    program = validate_thermal_program(program)
    times = [program["t0_min"]]
    temperatures = [program["initial_temperature_c"]]
    for segment in program["segments"]:
        start = temperatures[-1]
        end = segment.get("target_temperature_c", start)
        duration = segment_duration(segment["type"], start, end,
                                    segment.get("rate_c_per_min"), segment.get("duration_min"))
        times.append(times[-1] + duration)
        temperatures.append(end)
    return times, temperatures
