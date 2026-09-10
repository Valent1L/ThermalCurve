# ThermalCurve 1.0.1

[Français](README.md)

Installation and user guide
© 2026 Valentin Legrand
Contact: valentin.legrand@emse.fr

ThermalCurve analyses thermogravimetric data (TG, labelled ATG in the interface)
and coupled TG-DSC data. Standalone DSC is not supported in this version.

**This application is intended exclusively for files exported from SETARAM
instruments. Files from other manufacturers are not supported.**
A recognized extension does not guarantee compatibility with every SETARAM export:
column names, units and file structure must be recognized.

It supports blank correction, normalization, experiment comparison, analysis zones
and exports with provenance. Processing runs locally. The interface is available
in English and French. See [changelog.md](changelog.md) for changes.

## Contents

1. [Installation and startup](#1-installation-and-startup)
2. [Finding your way around](#2-finding-your-way-around)
3. [Your first processing session](#3-your-first-processing-session)
4. [Input files and units](#4-input-files-and-units)
5. [Blanks, normalization and signals](#5-blanks-normalization-and-signals)
6. [Comparing experiments and replicates](#6-comparing-experiments-and-replicates)
7. [Defining and quantifying zones](#7-defining-and-quantifying-zones)
8. [Customizing and exporting plots](#8-customizing-and-exporting-plots), [Thermal program](#thermal-program)
9. [Saving, moving and reopening projects](#9-saving-moving-and-reopening-projects)
10. [Stoichiometric calculations](#10-stoichiometric-calculations)
11. [Periodic table](#11-periodic-table)
12. [Troubleshooting](#12-troubleshooting)
13. [License and contact](#13-license-and-contact)

## 1. Installation and startup

### Windows folder with executable

Choose the Windows x64 archive for the required release. Extract its entire
contents into a folder you can write to, then open ThermalCurve.exe. Do not run
the application directly inside the ZIP archive. Keep the _internal directory
and all accompanying files next to the executable. Copy the entire folder when
moving the application.

This edition includes Python and the required libraries. You do not need to
install Python, create a .venv or have administrator rights to run it from your
personal folder. The binary targets Windows x64; it does not cover other systems.
The binary was checked locally on Windows 11 Enterprise, 64-bit.
An unsigned executable may trigger a Windows warning: check its origin and the
checksum supplied with the archive before deciding whether to run it.

### Running from Python sources

Requirement: Python 3.14.6, 64-bit. The declared range is >=3.14.6 and <3.15;
the verified version is 3.14.6. Install Python from python.org if needed.
Extract the sources to a personal folder and open PowerShell in that folder,
which contains run_qt.py and requirements.txt.

For a new installation with no existing .venv:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run_qt.py
```

The first two commands are only needed for installation. Use the third command
for subsequent launches. An internet connection is needed to obtain libraries
during installation, but not for subsequent calculations.

Verified direct libraries:

```text
PySide6 6.11.1       graphical interface
Matplotlib 3.11.1   plotting
NumPy 2.5.1         numerical calculations
pandas 3.0.3        data tables
openpyxl 3.1.5      XLSX reading and compatibility export
XlsxWriter 3.2.9    fast XLSX writing
xlrd 2.0.2          XLS reader
```

pip also installs their dependencies. requirements.txt pins these seven versions.

A .venv is recommended to isolate these libraries from other applications.
PowerShell activation is unnecessary. The environment is optional: a compatible
Python with the dependencies installed can run "py -3.14 run_qt.py" directly.
Do not copy a .venv between computers; recreate it at the new location. The
folder containing ThermalCurve.exe avoids this preparation.

## 2. Finding your way around

The top menu bar provides File, Thermal program, Stoichiometric calculations,
Periodic table, Options and About.

In Options > Language, choose English or Français. Close and restart the app
to apply the language throughout the interface.

Numeric input and display use a comma in French (`20,5`) and a dot in English
(`20.5`), independently of Windows settings, including calculator masses and gases,
zones, thermal programs and axes. Excel exports retain numeric cells and projects
retain their internal numeric format; hydrate formula dots remain unchanged.
The main toolbar places Import, Save, Export and Export figure on the left,
with "Analysis console" on the right.
Console (C) is the only interface: its compact layout is preserved, with subtly
rounded buttons and panels. Workspace
(A) and its selector have been removed; old Workspace preferences open Console.
Options > Appearance > Theme lets you choose Light or Dark. Panels can scroll or
collapse; drag their separators to adjust space. The theme persists between launches.
Horizontal and vertical separators have the same thickness. As panels narrow,
command rows wrap and selection fields adapt. A minimum usable width protects
controls from clipping; long file names no longer widen their panels.
Calculations remain the same.
In the light theme, checkboxes have a stronger outline, including in the
experiment list, to distinguish them from white backgrounds.

The ATG mode shows mass signals. ATG-DSC mode also allows you to work with
available heat flow. The main plot overlays the checked experiments. Selecting
a row makes that experiment active for editing without changing the checked
curves. Settings contains Preparation, Statistics and Curves tabs. Zones has its own panel.
Comparison no longer opens a separate window.

## 3. Your first processing session

Each experiment's tree and the curve selector in Curves offer only its available
signals. Heat flow appears only when its column is present, regardless of file
format. Missing dTG appears when its calculation from TG and time is enabled.

1) Click Add experiments and select one or more files. They are added to the
   list and plot. Check or uncheck an experiment to show or hide it; select
   its name to edit its settings.
2) Check its name, recognized signals and reader messages. Start with a
   representative copy when using a new instrument format.
3) In the associated blank selector, keep None to view data without correction,
   or select a suitable blank. Choose a file lets you load another blank.
4) Choose the horizontal axis: seconds/minutes, furnace temperature or sample
   temperature. Select TG, dTG and/or Heat flow according to available data.
5) Choose signal representations in Preparation, then use Process and display.
   Read the messages and check axis units before interpreting the curves.
6) Save a project through File > Save as, using a new .atgproj filename. Export
   results separately when you need to share numerical tables or figures.

Simple example: display TG without a blank, enter m0 in mg when needed, choose
Residual mass (%), process and inspect the curve. Only associate a blank when
its rows and acquisition times match the experiment.

### Try the included files

`Exemple/ATG-DSC` contains `MgCl2.6H2O.xls` (experiment) and `Blanc.xls` (associated
blank). Load the experiment, assign the blank and process in TG-DSC mode. Enable
"Compute dTG if missing" to compute the derivative absent from the source file.
The complete `Exemple` folder is included in both Windows and source archives,
including demonstration `.atgproj` projects and their associated files.
`Exemple/ATG` provides a CaCO3 experiment and its blank in text format.
Save your projects and exports under new names and preserve the supplied files.

## 4. Input files and units

Classic ATG text exports with a description, column names and a separate units row
are recognized by content, including files named `.XLS` or without an extension.
Leading-slash units (`/°C`, `/s`, `/mg`, `/mg/min`) and trailing tabs are supported.
For extensionless files, select "ATG text exports with or without an extension"
in the import dialog.

The file picker accepts XLS, XLSX, TXT, CSV and TSV. Content also matters: an .xls
file may contain a binary workbook, XLSX data or a text export. A listed extension
does not guarantee that every possible column arrangement is supported. The
reader searches for instrument headers and retains metadata. Supported text
encodings include UTF-8, UTF-16 with a BOM and Windows-1252.

A simple text layout has a description, column names, units and numeric rows.
Spaces below represent tab characters. The example keeps recognized column names:

```text
Synthetic example
Temps    Température du four    TG    HeatFlow
min      °C                     mg    mW
0        25                     20    2
1        35                     19    3
2        45                     18    4
```

Keep units in your files. Missing temperature cannot be used as an axis; missing
heat flow is not invented. Read warnings about ignored columns or incompatible
units. Processing does not rewrite original input files.

## 5. Blanks, normalization and signals

### Blank correction

Each experiment may have a different blank, or no blank. Ctrl+B associates a
file with the active experiment. Each Blank cell in the main list lets you
choose a file, reuse a loaded blank or choose None for that row, even when
another experiment is active.

**The blank must be acquired using the same experimental thermal program as
the experiment**: identical temperature setpoints, heating/cooling rates and
hold durations. It must also have the same acquisition time step and number
of points, with matching times point by point. The same thermal program alone
is therefore insufficient if the acquisition settings differ.

Subtraction is positional: corrected signal[i] = experiment[i] - blank[i].
The engine checks lengths and time compatibility. It does not interpolate or
resample the blank. Changing the display axis does not change this calculation.
A signal missing from the blank or having incompatible units remains identified
as uncorrected. A processed result without a blank is not blank-corrected data.

### Masses and TG

m0 is the initial experiment mass, in mg. Check its detected value and provenance;
use the manual m0 entry when necessary. m_ref is the normalization reference mass,
also in mg. For a custom reference, provide both a value and a name. Reusing m0
as the reference must be explicit; these masses have different roles.

TG representations include the original signal, mass change Δm zeroed at the
first valid point, Δm/m0 (%), remaining mass in mg, residual mass (%), and change
normalized by m_ref in mg/mg or %. Choose a representation, provide the required
masses and process. An invalid mass prevents the conversion that needs it;
the application does not substitute an arbitrary mass.

### dTG

Choose original, mass-normalized or relative (%) dTG and its time unit: Source,
min^-1, s^-1 or h^-1. Calculate dTG if missing produces a numerical derivative of the
available TG. This is calculated data, and measurement noise can be amplified.
Check the signal, units and messages.

"Calculated dTG smoothing (points)" appears when this calculation is enabled.
The default, "No smoothing" (1 point), preserves the current derivative. An odd
window of 3, 5, 7 points, etc. applies a centered moving average to calculated dTG
before mass normalization. At the ends, only available points are averaged.
Windows longer than the curve are rejected. Smoothing can attenuate or broaden
peaks and affects derived results and zones using this dTG. It changes neither
TG nor dTG supplied by the instrument. All points and times are retained. The
per-experiment setting is saved in the project and described in export metadata.

Time can be displayed in seconds, minutes or hours on plots, in zones,
reference ranges, thermal programs and exports. Files declaring hours are also
supported. dTG values are converted numerically: 1 mg/min = 60 mg/h. Temps_s
remains the internal time basis; original columns and blank correction are unchanged.

### Heat flow

Choose original heat flow, heat flow relative to reference, W, mW/mg, W/g or W/mg as
offered by the controls. Mass normalization uses the specified reference.
For zeroing, choose First valid point or Mean over a range. For a range, select
its axis and enter its bounds in the indicated units. A missing or unusable
reference does not produce a valid conversion. Relative heat flow is
`HF - HF_reference`, so the first valid point is zero by default. This helps
compare changes from a common origin. It neither replaces blank subtraction nor
corrects baseline drift.

Align zeros aligns the vertical axes visually without shifting data. Axis units
and original/corrected/normalized status identify the plotted values. Heat-flow
sign depends on the instrument convention; confirm that convention before
interpreting a signal as exothermic or endothermic.

## 6. Comparing experiments and replicates

Add experiments in the main list and check those to overlay. Expand an experiment
with its arrow to reveal TG, dTG and Heat flow. Child rows are indented, including
their checkboxes. Each checkbox
click changes only that curve.
Unchecking an experiment hides all its curves while preserving their individual
choices. The TG, dTG and Heat flow boxes above the plot remain global filters:
a curve appears when its experiment, its own box and its global filter are checked,
and the corresponding data are available.

Choose Original, Corrected or Normalized for each experiment. Select a row to edit
its normalization in Preparation. In Settings > Curves, choose TG, dTG, Heat flow
or All curves to edit color, width, line style, markers, marker spacing, legend name
and Y offset. Selecting a child curve directly selects its settings in that tab.
All curves applies each change to every signal of that experiment. Individual
curve settings and checkboxes are saved in the project.
The lists offer 10 line styles and 25 marker choices, with names and previews
matching the plot. When statistics display a mean, the Mean of checked experiments
target edits each mean signal independently of individual experiments. Its standard
deviation band follows its color and offset. Mean styles are saved in the project;
calculations and exported data remain independent of visual offsets.

Remove takes the experiment out of the project without deleting its file.
Move up and Move down change the list and plot order. Each curve keeps its own
X coordinates; there is no domain selector. In Stacking, select an axis then click
Stack to space the checked individual curves. Spacing can be automatic or entered
in that axis unit. After applying, the slider and numeric field adjust spacing
directly without shifting other axes. Reset to zero clears all offsets, including
mean offsets. Stacking is available when individual curves are displayed.

For replicates:

1) Check experiments and curves to include in statistics.
2) In Settings > Statistics, enable statistics mode. No group needs
   to be created: calculations automatically follow the checked curves for each
   signal. The active row only selects the settings being edited.
3) Choose Mean only, Mean with ±1 standard deviation band, Mean with individual
   curves, or Individual curves only.
4) Keep automatic spacing or specify the number of points. Read the included
   curve summary and check their units.
5) Use Export in the top toolbar to save data according to the displayed mode.
   Export figure, beside it, saves the plot.

Statistics may interpolate onto a common grid according to domains and settings.
This step is separate from individual plotting and blank correction. Sample
count can vary along the X axis. Standard deviation uses ddof=1 and is undefined
with fewer than two values. A ±1 standard deviation band is not a confidence
interval.

## 7. Defining and quantifying zones

The Zones panel below the plot has two tabs: Definition and Results. The former
Zones tab in Settings and separate text reports have been removed. The + button
in the header starts a drag selection on the plot; Escape cancels it. Disable
zoom/pan if those tools capture the gesture. A name is suggested automatically.

In Definition, double-click to edit the name, a bound, the baseline method or
its value; Enter commits the change. Edit starts editing the selected zone's
initial bound, and Delete removes that zone. A zone retains its definition axis;
changing the plot axis does not convert its bounds. The gear beside its name
controls its color, boundary width, fill opacity and baseline visibility.
The baseline color is adjustable separately.
Two buttons also select the calculated area colors above and below the baseline,
including areas drawn for the mean curve.
These visual settings are saved in the project and do not change calculations.

Choose None or Constant for the heat-flow baseline. For Constant, enter its value
in the relevant signal unit. A constant without an explicit value retains the
existing behavior: reference to the first point in the zone. Previously saved
linear baselines remain supported.

Results keeps a summary with Zone as its first column, followed by TG, dTG and
Heat flow. When several experiments are displayed, rows are grouped under each
experiment's name. Show all results, in the panel header, opens an independent
window with the complete table and horizontal scrolling, without recalculating
or replacing the summary. Display uses up to four significant digits and scientific
notation when needed; internal values remain unchanged. Units are readable plain
text, without raw LaTeX. Mixed units appear in individual cells. Warnings remain
available in tooltips and through Zone information. This dedicated window contains
bounds, references, states and warnings; Context is removed from the results table.
Initial dimensions fit the content;
drag header separators to resize columns manually afterwards.
Separators stay aligned between headers and rows, including while scrolling.
The table keeps a neutral border when focused; editors and drop-downs fit within
their cells.
Family headers (TG, dTG, Heat flow) span their columns and remain
readable during horizontal scrolling. Higher-contrast separators distinguish
these families in the header and data rows. Sizing uses the final displayed font after
opening or changing themes; spanning experiment names do not widen the Zone column.
Copy table copies every row in the active view, including off-screen rows,
with headers and readable row identifiers, for Excel or text files. Copies
retain the available precision rather than the rounded on-screen values.
The complete-results window has its own copy button.

The table distinguishes mass changes, extrema and available heat-flow information.

Δm/m₀ (%) uses each experiment's initial mass m₀, read from metadata or entered
in mg under Settings > Preparation, including when TG is displayed in mg.
Missing masses are explained in tooltips; the first TG point is never treated as
the initial mass because it may represent zero mass change. For a mean TG curve
in mg, the ratio is `100 × ΔTG_mean / mean(m₀)` over the included experiments,
whose masses must all be known. A mean already expressed as Δm/m₀ (%) gives the
relative change directly from its endpoint difference. Visual offsets are excluded.
Heat flow is integrated over time even when selection uses temperature. Areas
on either side of the baseline remain separate. Portions outside the zone are
not joined together.

A temperature zone may be crossed during both heating and cooling: all passages
are retained. Prefer a time zone to isolate one event. Do not interpret an
ambiguous overall change as a single passage.

Main plot reports follow the displayed individual/statistical mode and use
values without visual offsets. In statistics mode, the same summary combines TG,
dTG and Heat flow on one row per zone. The mean name appears above the table,
below Show all results, and remains included when copying. Indicators are
calculated on the displayed mean curve, rather than averaged from individual
indicators. Mean with individual curves also keeps their results grouped by experiment.

Heat-flow peaks account for the baseline. Signed, positive and negative areas
use the same integration rules as individual experiments. Mean area requires
a time axis: no duration is invented on a temperature axis. Zone boundaries are
interpolated without extrapolation or bridging gaps. Units follow the mean signal,
including normalized TG. Results requiring a mass reference for the mean
(percentages, final mass and residual) remain unavailable when that reference is undefined.

The complete table adds mean endpoints and extrema, plus endpoint standard
deviations and the change envelope in band mode, within the corresponding families.
This envelope is neither the standard deviation of the change nor a confidence
interval; no standard deviation of peaks or areas is inferred from it.

## 8. Customizing and exporting plots

The Matplotlib toolbar restores the initial view, navigates through views, pans,
zooms and saves an image. Clicking the Legend button opens "Edit legend" directly,
without a drop-down menu. The "Show legend" checkbox inside the dialog controls
visibility without changing curves; this choice is saved in the project.
The dialog has three tabs:

- "Frame": none, box or rounded; optional fill, fill color and transparency,
  border color and width, common or separate margins (% of font height), and
  text wrapping with an adjustable width in characters.
- "Position": corners, side centers and plot center; outside right, left, top and
  bottom positions calculated beyond axes, ticks and titles, including the thermal
  program axis. Custom placement uses % of plot or figure coordinates, starting
  at the bottom left, an anchor and anchoring on the frame or its contents.
  Mouse dragging can be locked horizontally or vertically.
- "Text": editable labels for each entry, font, size, color, rotation, line spacing,
  tab width, alignment, column count and column alignment, bold, italic
  and underline. Buttons insert subscripts, superscripts, Greek letters, accents
  and symbols. "Verbatim" disables mathematical interpretation; Origin-specific
  commands such as `\l(1)` are not interpreted. Curve samples remain automatic.

Text controls adapt to the window width, with vertical scrolling when needed.
Style applies to the whole legend; labels are edited entry by entry and share the
frame background, without separate white rectangles. Selected text, fill and border
colors are respected on screen in light and dark themes and in exports. The separate
white-out option has been removed. Labels may contain line breaks.
"Restore automatic label" restores the application's generated
name. Apply confirms settings; Cancel discards unapplied changes. Settings and
labels persist in the project and figure exports without renaming sources or
changing numeric data.

"Plot settings" combines the former Customize and Plot spacing tools in one
fully translated window. "General" contains the title and alignment. The legend
keeps its dedicated editor; the Curves tab has been removed.

- "Grid" separates major and minor grid lines: visibility, color, style and
  thickness. Minor lines follow the subdivisions defined for the axes.
- "Axes and ticks" selects the bottom, top, TG, dTG, heat flow or programmed
  temperature axis. Set line and label visibility, line color and thickness,
  side and arrows, then major and minor tick direction, length, color and width.
  "Automatic" keeps the default style and follows the theme. "All axes" or
  "Both X axes" copies appearance without moving axes. The second view contains
  labels, limits, scales and number formats for each measured quantity. The top
  axis shares the bottom abscissa and tick spacing, with independent appearance;
  it also follows zooming.
- "Spacing" combines automatic or manual plot margins with spacing between
  axes, axis titles and tick labels.
- Reference lines, fonts and annotations remain available in their tabs. The
  resizable window and scrollable pages adapt to smaller dimensions.

Settings persist in projects and PNG, SVG and PDF exports without changing data
or calculations. Logarithmic scales require compatible values. Apply confirms
settings; Cancel discards unapplied changes. Reset preserves the legend and
curve styles. An .atgstyle.json template allows presentation reuse.

Color buttons are fully filled with the selected color. Clicking opens the picker;
the hexadecimal code remains available in the tooltip.
Screen rendering reuses automatic legend placement for identical geometry within
the same frame. Dragging redraws only the legend when supported by the rendering
backend. No curve points or numerical precision are removed. The ThermalCurve icon
is supplied in multiple sizes and configured for Qt and the Windows executable build.
In the experiment list, the Blank column displays a single label per cell.
It can be resized, and the tooltip provides the full path.

File > Export result (Ctrl+E) creates an Excel `.xlsx` workbook with three sheets:

1. "Corrected data": coordinates and processed signals, including calculated
   conversions, without the internal `Dans_zone_commune` column.
2. "Original data": original experiment columns and values.
3. "Blank data": original blank columns and values, or an explicitly empty sheet
   if no blank is assigned.

The last two sheets show each source's full filename on row 1 and path on row 2.
Units appear in parentheses beside column names. Provenance remains available
in comments on block titles. No JSON sidecar
is created. Excel workbooks replace the former CSV/TSV exports.

The toolbar Export button and File > Export result (Ctrl+E) follow the same display mode
of the main plot:

- without statistics: all visible, compatible series;
- "Mean" or "Mean with standard deviation band": means, standard deviations and counts;
- "Mean with individual curves": those statistics and the admitted individual series;
- statistical "Individual curves": only checked, compatible series admitted by the calculation.

All plot exports share the same layout: filename above the block,
column names with units, then data. Column widths and row heights are fitted to
the content on each export, including long names and multiline cells. Comparison
headers no longer repeat the experiment name in every column.
Large-table exports calculate dimensions during writing and reuse data formatting
to reduce processing time while preserving all three sheets, values and provenance.
XlsxWriter speeds up writing without reducing the number of points or removing
formatting. The Windows distribution bundles the writer and its license;
users do not need to install it separately.
Export remains available through openpyxl when XlsxWriter is missing
or a provenance comment exceeds the fast writer's limit.
Duration depends on data volume and the computer; one-second exports are not guaranteed.

The first sheet preserves the displayed stage (original, corrected or normalized),
without cosmetic Y offsets. Original experiments remain on sheet 2 and blanks on
sheet 3. Blocks sit side by side with one empty column between datasets. Every
series retains its own X coordinates and length. A shared blank appears only once.
Four experiments sharing one blank therefore give four original blocks and one
blank block, even when exporting only their mean. Parameters and exclusions are
available in the comment on the first block title.

Export uses the same workbook structure for statistics of checked experiments.
Export figure in the top toolbar offers PNG, SVG and PDF. Never choose an input file or the open
project as an export destination.

### Thermal program

Open "Thermal program" from the main window's top menu bar. The program belongs
to the active experiment and is saved with the project. In overlays and statistics
mode, its program is shown when that experiment is checked; select another row
to display its program. Add as many hold, heating
or cooling sections as needed.

- `T_ini` automatically follows the previous section's `T_f`.
- Holds keep temperature constant; enter their duration as `hh:mm:ss`.
- For durations and `t₀`, `:` separators are inserted after two typed hour and minute digits: `006600` becomes `00:66:00`. Minutes and seconds may exceed 59 and are converted on confirmation (`00:66:00` = `01:06:00`, `00:00:90` = `00:01:30`). Complete durations can still be pasted, including fields with more than two digits.
- For ramps, enter `T_f` and a strictly positive β in °C/min or K/min. Duration
  is calculated as `abs(T_f - T_ini) / β`. Zero rates are rejected.
- Display temperature in °C or K. The editable origin `t₀` defaults to `00:00:00`.
- An entry of `01:06:00` displays as `66` minutes, `3960` seconds or `1.1` hours, following the X axis.

Enable the program and apply. It uses a right-hand temperature axis on time-based
plots (seconds, minutes or hours). This is the entered setpoint, not measured temperature.
Right-axis spacing and dTG scaling improve readability. Zero alignment follows
changes to bounds that enclose zero; conflicting zero positions are rejected.

## 9. Saving, moving and reopening projects

Ctrl+S saves; Ctrl+Shift+S chooses a new destination. Ctrl+O opens an .atgproj;
Ctrl+N starts a new project. An asterisk in the title indicates unsaved changes.

A project stores source references and hashes, blanks, settings, zones,
comparisons and tool inputs. It does not embed complete experimental tables.
To archive or share a session, retain the .atgproj AND all source and blank
files, preferably in the same folder or its subfolders. An Excel export is not
a session backup.

If a source moved, use the resolution workflow offered when opening the project.
If its hash changed, check the file before accepting it. Save under a new name
to preserve an earlier project version. Saving protects experimental files
against replacement.

## 10. Stoichiometric calculations

Open Stoichiometric calculations from the top menu bar:

1) Add an equation, for example: CaCO3(s) -> CaO(s) + CO2(g).
2) Click Verify. Check formulas, physical states and molar masses.
3) If necessary, Balance proposes coefficients; Use proposal applies them.
   Preserve entered proportions handles ratio constraints when a compatible
   solution exists.
4) Choose Individual masses and enter each reactant mass with its unit, or
   Total mass for an assumed stoichiometric condensed mixture.
5) Check the equations to calculate and click Calculate selection.
6) Read limiting reactants, excess amounts, products and condensed mass change.
   Adjust units and decimal/scientific notation, then Copy result.

Hydrates and adducts accept both `.` and `·`:
`MgCl2.6H2O = MgCl2.4H2O + 2H2O(g)`. A number after the separator multiplies
the following formula. Omitted states default to solid; specify `(g)` for
released water. Decimal coefficients remain unsupported; use a fraction.

For gaseous reactants, choose Finite mass, Partial pressure/volume/temperature,
molar ppm or ppmv, Gas in excess, or Flow × duration and composition. Check each field's unit. PVT conversions
use the ideal-gas model. Declaring excess gas assumes it does not limit the
reaction. Do not confuse ppmv with a mass fraction.

For a closed volume, enter the reactant partial pressure (or total pressure and
ppm content), volume and temperature. For flowing gas, enter total mixture
volumetric flow, exposure duration in s, min or h, reactant content as molar %,
molar ppm or ppmv, and the absolute total pressure and temperature used to reference
that flow. Use the flowmeter reference conditions, which may differ from furnace
conditions. Reference conventions vary; consult the instrument documentation,
for example [Bronkhorst reference conditions](https://www.bronkhorst.com/service-support/faq/?question=1925).
The calculation uses `n_gas = fraction × P_ref × Q × duration / (R × T_ref)`
with constant flow and composition, under the [ideal-gas model](https://goldbook.iupac.org/terms/view/I02935).
It quantifies gas supplied, not the amount actually reacted.

These are theoretical balances. Atomic balance does not demonstrate thermodynamic
feasibility or reaction speed under your experimental conditions. Correctly
distinguish gaseous and condensed species when interpreting mass loss or gain.
Kinetics, diffusion, mass and heat transfer and chemical equilibrium are not
modeled. The gain calculated for `4 Fe(s) + 3 O2(g) = 2 Fe2O3(s)` is therefore
a theoretical stoichiometric maximum.

## 11. Periodic table

Open Periodic table from the top menu. Search by name, symbol or atomic number,
then select an element to view its information. The detailed view and information
copy action allow reuse of displayed values. All 118 elements are included and
the table works offline.

The calculation reference masses remain those used by stoichiometry. Bundled
Mendeleev data enriches browsing; its masses or other enriched properties do not
silently replace the calculation reference. Missing properties remain unavailable.
Provenance and the MIT license for the Mendeleev v0.20.0 snapshot accompany the
distributed resources.

## 12. Troubleshooting

Executable will not start: extract the entire folder again, check that _internal
accompanies the executable, and use an accessible personal folder. Copying only
ThermalCurve.exe is insufficient.

Missing Python module: use the same interpreter for pip and run_qt.py. Repeat
the installation command with .venv\Scripts\python.exe.

Unrecognized file: check content, headers, encoding and units. Renaming an
extension cannot fix incompatible content. Prepare a working copy while keeping
the original instrument file intact.

Blank rejected: check times, row counts and units. A blank from a different
acquisition does not become compatible by changing the plot axis.

Missing curve: check the active experiment, visibility, selected signals, mode,
units and messages. A mean without a band may lack valid replicates.
Normalization requires valid masses and references.

Incomplete project after moving it: locate its source and blank files as well.
Language unchanged: close and restart after choosing Options > Language.

When reporting an issue, provide the version shown in About, reproduction steps,
the exact message and, if possible, a small anonymized example you are allowed
to share. Do not send confidential data by default.

## 13. License and contact

© 2026 Valentin Legrand. Original code is under PolyForm Noncommercial 1.0.0.
The full text is in LICENSE.txt and its terms apply. Source is available with
a noncommercial-use restriction. Third-party libraries and data retain their
own licenses, described in THIRD_PARTY_NOTICES.txt and the notices accompanying
the distribution.

Questions, suggestions and licensing enquiries:
[valentin.legrand@emse.fr](mailto:valentin.legrand@emse.fr)

References:
- <https://polyformproject.org/licenses/noncommercial/1.0.0>
- <https://docs.python.org/3/library/venv.html>
- <https://pyinstaller.org/en/stable/operating-mode.html>
