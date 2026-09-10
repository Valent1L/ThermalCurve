"""Shared curve style names and their Matplotlib rendering values."""

LINE_STYLES = {
    '-': ('Continue', '-'), '--': ('Tirets', '--'), '-.': ('Mixte', '-.'),
    ':': ('Pointillés', ':'), 'long_dash': ('Tirets longs', (0, (8, 3))),
    'short_dash': ('Tirets courts', (0, (2, 2))),
    'dash_dot_dot': ('Tiret et deux points', (0, (6, 2, 1, 2, 1, 2))),
    'sparse_dots': ('Points espacés', (0, (1, 4))),
    'dense_dots': ('Points rapprochés', (0, (1, 1))),
    'none': ('Sans ligne', 'None'),
}
MARKERS = {
    '': 'Aucun', 'o': 'Cercle', 's': 'Carré', '^': 'Triangle haut',
    'v': 'Triangle bas', '<': 'Triangle gauche', '>': 'Triangle droite',
    'D': 'Losange', 'd': 'Losange étroit', 'p': 'Pentagone', '*': 'Étoile',
    'h': 'Hexagone', 'H': 'Hexagone tourné', '+': 'Plus', 'x': 'Croix',
    'P': 'Plus plein', 'X': 'Croix pleine', '.': 'Point', ',': 'Pixel',
    '|': 'Trait vertical', '_': 'Trait horizontal',
    '1': 'Trépied bas', '2': 'Trépied haut', '3': 'Trépied gauche', '4': 'Trépied droite',
}


def mpl_line_style(name):
    return LINE_STYLES[name][1]


def mean_curve_style(signal, overrides):
    return {
        'color': {'tg': '#0072B2', 'dtg': '#D55E00', 'heat_flow': '#009E73'}[signal],
        'legend_name': '', 'line_style': '-', 'line_width': 2.0,
        'marker': '', 'markevery': None, 'y_offset': 0.0,
        **overrides.get(signal, {}),
    }
