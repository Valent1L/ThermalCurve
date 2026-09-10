"""Legend presentation only. Source artists and numeric series are never changed."""
from copy import deepcopy
from math import cos, sin, radians
import textwrap
import re

from matplotlib.colors import to_rgba
from matplotlib.cbook import is_math_text
from matplotlib.mathtext import MathTextParser
from matplotlib.legend import Legend, DraggableLegend
from matplotlib.lines import Line2D
from matplotlib.offsetbox import DrawingArea, HPacker, VPacker
from matplotlib.transforms import IdentityTransform

from .projects import default_legend_style


LEGEND_POSITIONS = (
    ("Automatique", "best"), ("Haut gauche", "upper left"), ("Haut centre", "upper center"),
    ("Haut droite", "upper right"), ("Centre gauche", "center left"), ("Centre", "center"),
    ("Centre droite", "center right"), ("Bas gauche", "lower left"), ("Bas centre", "lower center"),
    ("Bas droite", "lower right"), ("Extérieur droit", "outside"), ("Extérieur gauche", "outside left"),
    ("Extérieur haut", "outside top"), ("Extérieur bas", "outside bottom"), ("Personnalisée", "manual"),
)


def legend_entries(handles, labels):
    counts = {}
    entries = []
    for handle, label in zip(handles, labels):
        key = handle.get_gid() or "label:" + label
        counts[key] = counts.get(key, 0) + 1
        entries.append((key if counts[key] == 1 else f"{key}:{counts[key]}", label))
    return entries


def validate_legend_text(graph):
    style = graph.get("legend_style", default_legend_style())
    if style["verbatim"]:
        return
    parser = MathTextParser("path")
    for text in style["entries"].values():
        for line in text.split("\n"):
            if is_math_text(line):
                parser.parse(line)


def _anchor_fraction(anchor):
    return (0 if "left" in anchor else 1 if "right" in anchor else .5,
            1 if "upper" in anchor else 0 if "lower" in anchor else .5)


def _wrap_label(text, width, verbatim):
    # ponytail: widths are approximate character counts; keep math expressions indivisible.
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        tokens = re.findall(r"\$(?:\\.|[^$])*\$|\S+", paragraph) if not verbatim else paragraph.split()
        for token in tokens:
            parts = [token] if not verbatim and token.startswith("$") else textwrap.wrap(token, width, break_on_hyphens=False)
            for part in parts:
                if current and len(current) + len(part) + 1 > width:
                    lines.append(current)
                    current = ""
                current += (" " if current else "") + part
        lines.append(current)
    return "\n".join(lines)


class EditableLegend(Legend):
    """Native legend with asymmetric padding and placement beyond axis decorations.

    Matplotlib's packer and offset hooks are isolated here and covered by rendering
    tests; the public Legend API only offers a single symmetric border padding.
    """

    def __init__(self, parent, handles, labels, graph, font):
        self._position_cache = None
        self.style = deepcopy(graph.get("legend_style", default_legend_style()))
        self.position = graph.get("legend_position", "best")
        style = self.style
        entries = legend_entries(handles, labels)
        texts = []
        for key, label in entries:
            text = style["entries"].get(key, label).expandtabs(style["tab_width"])
            if style["wrap"]:
                text = _wrap_label(text, style["wrap_width"], style["verbatim"])
            texts.append(text)
        prop = {"size": font.get("fontsize") or "small", "weight": font.get("fontweight", "normal"),
                "style": font.get("fontstyle", "normal")}
        if font.get("fontfamily"):
            prop["family"] = font["fontfamily"]
        super().__init__(parent, handles, texts, loc=self.position if self.position in Legend.codes else "upper right",
                         prop=prop, frameon=style["frame"] != "none", fancybox=style["frame"] == "rounded",
                         framealpha=None, borderpad=0, labelspacing=.5 * (style["line_spacing"] or 100) / 100,
                         ncols=style["columns"], alignment=style["alignment"])
        frame = self.get_frame()
        frame.set_alpha(None)
        frame.set_facecolor(to_rgba(style["fill_color"], style["fill_alpha"]) if style["fill_color"] else "none")
        frame.set_edgecolor(style["border_color"])
        frame.set_linewidth(style["border_width"])
        for text in self.get_texts():
            text.set_color(style["text_color"])
            text.set_rotation(style["rotation"])
            if style["line_spacing"] is not None:
                text.set_linespacing(style["line_spacing"] / 100)
            text.set_multialignment(style["alignment"])
            text.set_parse_math(not style["verbatim"])
            # The shared frame is the only background, including for older white_out settings.
        # Handle/text alignment and column alignment remain native packer operations.
        for column in self._legend_handle_box.get_children():
            column.align = "baseline" if style["align_columns"] else style["alignment"]
        margins = {side: value * self._fontsize / 100 for side, value in style["margins"].items()}
        content = self._legend_box
        horizontal = HPacker(pad=0, sep=0, align="center", children=[DrawingArea(margins["left"], 0), content,
                                                                             DrawingArea(margins["right"], 0)])
        self._legend_box = VPacker(pad=0, sep=0, align="left", children=[DrawingArea(0, margins["top"]), horizontal,
                                                                      DrawingArea(0, margins["bottom"])])
        self._legend_box.set_figure(parent.figure)
        self._legend_box.axes = parent
        self._legend_box.set_offset(self._findoffset)

    def _margins_px(self, renderer):
        return {side: renderer.points_to_pixels(value * self._fontsize / 100)
                for side, value in self.style["margins"].items()}

    def _find_best_position(self, width, height, renderer):
        # One screen draw only. Layout may move the axes between its two passes.
        if self._position_cache is None:
            return super()._find_best_position(width, height, renderer)
        key = (width, height, tuple(self.axes.bbox.bounds), tuple(self.axes.get_xlim()),
               tuple(self.axes.get_ylim()), tuple(self.get_bbox_to_anchor().bounds))
        if key not in self._position_cache:
            self._position_cache[key] = super()._find_best_position(width, height, renderer)
        return self._position_cache[key]

    def _findoffset(self, width, height, xdescent, ydescent, renderer):
        if self.position == "manual":
            transform = self.axes.transAxes if self.style["unit"] == "axes_percent" else self.figure.transFigure
            x, y = transform.transform((self.style["x"] / 100, self.style["y"] / 100))
            ax, ay = _anchor_fraction(self.style["anchor"])
            margins = self._margins_px(renderer)
            left, right, top, bottom = (margins[side] for side in ("left", "right", "top", "bottom"))
            if self.style["anchor_frame"]:
                x, y = x - ax * width, y - ay * height
            else:
                x, y = x - left - ax * (width - left - right), y - bottom - ay * (height - top - bottom)
            return x + xdescent, y + ydescent
        if self.position.startswith("outside"):
            boxes = [self.axes.bbox]
            # Avoid Axes.get_tightbbox: it includes this legend and would recurse.
            for axis in [*self.figure.axes, *(child for parent in self.figure.axes for child in parent.child_axes)]:
                if not axis.get_visible():
                    continue
                for artist in (axis.xaxis, axis.yaxis, axis.title, *axis.spines.values()):
                    if artist.get_visible():
                        box = artist.get_tightbbox(renderer)
                        if box is not None:
                            boxes.append(box)
            gap = renderer.points_to_pixels(8)
            bounds = self.axes.bbox
            x, y = (bounds.x0 + bounds.x1 - width) / 2, (bounds.y0 + bounds.y1 - height) / 2
            if self.position == "outside":
                x = max(box.x1 for box in boxes) + gap
            elif self.position == "outside left":
                x = min(box.x0 for box in boxes) - gap - width
            elif self.position == "outside top":
                y = max(box.y1 for box in boxes) + gap
            else:
                y = min(box.y0 for box in boxes) - gap - height
            return x + xdescent, y + ydescent
        return super()._findoffset(width, height, xdescent, ydescent, renderer)

    def draw(self, renderer):
        super().draw(renderer)
        if self.get_visible() and self.style["underline"]:
            for text in self.get_texts():
                px, py = text.get_transform().transform(text.get_position())
                angle = radians(text.get_rotation())
                offset = renderer.points_to_pixels(text.get_fontsize() * .12)
                for row in text._get_layout(renderer)[1]:
                    _, metrics, *position = row
                    x, y = position[0] if len(position) == 1 else position
                    x, y = px + x + sin(angle) * offset, py + y - cos(angle) * offset
                    line = Line2D([x, x + cos(angle) * metrics[0]], [y, y + sin(angle) * metrics[0]],
                                  color=text.get_color(), linewidth=.7, transform=IdentityTransform())
                    line.set_figure(self.figure)
                    line.draw(renderer)


class LegendDrag(DraggableLegend):
    def __init__(self, legend, on_change):
        super().__init__(legend, use_blit=legend.figure.canvas.supports_blit)
        self.on_change = on_change

    def update_offset(self, dx, dy):
        super().update_offset(0 if self.legend.style["lock_x"] else dx,
                              0 if self.legend.style["lock_y"] else dy)

    def finalize_offset(self):
        legend = self.legend
        renderer = legend.figure._get_renderer()
        box = legend.get_window_extent(renderer)
        ax, ay = _anchor_fraction(legend.style["anchor"])
        x, y = box.x0 + ax * box.width, box.y0 + ay * box.height
        if not legend.style["anchor_frame"]:
            margins = legend._margins_px(renderer)
            x += margins["left"] * (1 - ax) - margins["right"] * ax
            y += margins["bottom"] * (1 - ay) - margins["top"] * ay
        transform = legend.axes.transAxes if legend.style["unit"] == "axes_percent" else legend.figure.transFigure
        x, y = transform.inverted().transform((x, y))
        legend.style.update(x=max(-1000.0, min(1000.0, float(x * 100))),
                            y=max(-1000.0, min(1000.0, float(y * 100))))
        legend.position = "manual"
        legend._legend_box.set_offset(legend._findoffset)
        self.on_change(deepcopy(legend.style))


def replace_legend(primary, handles, labels, graph, font):
    primary._thermalcurve_legend_entries = list(zip(handles, labels))
    previous = primary.get_legend()
    if previous is not None:
        if previous._draggable is not None:
            previous.set_draggable(False)
        previous.remove()
    if not handles or not graph.get("legend_visible", True):
        return None
    legend = EditableLegend(primary, handles, labels, graph, font)
    primary.legend_ = legend
    legend._remove_method = primary._remove_legend
    legend.set_visible(graph.get("legend_visible", True))
    return legend
