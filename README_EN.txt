ThermalCurve 1.0.0
Installation and user guide
© 2026 Valentin Legrand
Contact: valentin.legrand@emse.fr

ThermalCurve analyses thermogravimetric (TG, labelled ATG in parts of the
interface) and differential scanning calorimetry (DSC) data. It supports blank
correction, normalization, experiment comparison, analysis zones and exports
with provenance. Processing runs locally. The interface is available in English
and French.

Contents
1. Installation and startup
2. Finding your way around
3. Your first processing session
4. Input files and units
5. Blanks, normalization and signals
6. Comparing experiments and replicates
7. Defining and quantifying zones
8. Customizing and exporting plots
9. Saving, moving and reopening projects
10. Stoichiometric calculations
11. Periodic table
12. Troubleshooting
13. License and contact

1. Installation and startup
==========================

Windows folder with executable
------------------------------
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

Running from Python sources
---------------------------
Requirement: Python 3.14.6, 64-bit. The declared range is >=3.14.6 and <3.15;
the verified version is 3.14.6. Install Python from python.org if needed.
Extract the sources to a personal folder and open PowerShell in that folder,
which contains run_qt.py and requirements.txt.

For a new installation with no existing .venv:

    py -3.14 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    .venv\Scripts\python.exe run_qt.py

The first two commands are only needed for installation. Use the third command
for subsequent launches. An internet connection is needed to obtain libraries
during installation, but not for subsequent calculations.

Verified direct libraries:
    PySide6 6.11.1       graphical interface
    Matplotlib 3.11.1   plotting
    NumPy 2.5.1         numerical calculations
    pandas 3.0.3        data tables
    openpyxl 3.1.5      XLSX reader
    xlrd 2.0.2          XLS reader
pip also installs their dependencies. requirements.txt pins these six versions.

A .venv is recommended to isolate these libraries from other applications.
PowerShell activation is unnecessary. The environment is optional: a compatible
Python with the dependencies installed can run "py -3.14 run_qt.py" directly.
Do not copy a .venv between computers; recreate it at the new location. The
folder containing ThermalCurve.exe avoids this preparation.

2. Finding your way around
=========================

The top menu bar provides File, Experiment comparison, Stoichiometric calculations,
Periodic table, Options and About.

In Options > Language, choose English or Français. Close and restart the app
to apply the language throughout the interface. Options > Appearance lets you
choose the Atelier or Console style and Light or Dark theme. The layout changes;
calculations remain the same. Panels can scroll or collapse depending on the
style; drag their separators to adjust space. Preferences persist between launches.

The ATG mode shows mass signals. ATG-DSC mode also allows you to work with
available heat flow. The main plot shows one active experiment; the comparison
window has its own selection. Preparation, Zones and status/messages panels
accompany the plots.

3. Your first processing session
===============================

1) Click Add experiments and select one or more files. They are added to the
   list. Select the experiment you want to display.
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

4. Input files and units
=======================

The file picker accepts XLS, XLSX, TXT, CSV and TSV. Content also matters: an .xls
file may contain a binary workbook, XLSX data or a text export. A listed extension
does not guarantee that every possible column arrangement is supported. The
reader searches for instrument headers and retains metadata. Supported text
encodings include UTF-8, UTF-16 with a BOM and Windows-1252.

A simple text layout has a description, column names, units and numeric rows.
Spaces below represent tab characters. The example keeps recognized column names:

    Synthetic example
    Temps    Température du four    TG    HeatFlow
    min      °C                     mg    mW
    0        25                     20    2
    1        35                     19    3
    2        45                     18    4

Keep units in your files. Missing temperature cannot be used as an axis; missing
heat flow is not invented. Read warnings about ignored columns or incompatible
units. Processing does not rewrite original input files.

5. Blanks, normalization and signals
===================================

Blank correction
----------------
Each experiment may have a different blank, or no blank. Ctrl+B associates a
file with the active experiment. In the comparison window, Assign a blank
applies a blank to selected experiments.

Subtraction is positional: corrected signal[i] = experiment[i] - blank[i].
The engine checks lengths and time compatibility. It does not interpolate or
resample the blank. Changing the display axis does not change this calculation.
A signal missing from the blank or having incompatible units remains identified
as uncorrected. A processed result without a blank is not blank-corrected data.

Masses and TG
-------------
m0 is the initial experiment mass, in mg. Check its detected value and provenance;
use the manual m0 entry when necessary. m_ref is the normalization reference mass,
also in mg. For a custom reference, provide both a value and a name. Reusing m0
as the reference must be explicit; these masses have different roles.

TG representations include the original signal, mass change Δm zeroed at the
first valid point, Δm/m0 (%), remaining mass in mg, residual mass (%), and change
normalized by m_ref in mg/mg or %. Choose a representation, provide the required
masses and process. An invalid mass prevents the conversion that needs it;
the application does not substitute an arbitrary mass.

dTG
---
Choose original, mass-normalized or relative (%) dTG and its time unit: Source,
min^-1 or s^-1. Calculate dTG if missing produces a numerical derivative of the
available TG. This is calculated data, and measurement noise can be amplified.
Check the signal, units and messages.

Heat flow
---------
Choose original heat flow, a zeroed representation, W, mW/mg, W/g or W/mg as
offered by the controls. Mass normalization uses the specified reference.
For zeroing, choose First valid point or Mean over a range. For a range, select
its axis and enter its bounds in the indicated units. A missing or unusable
reference does not produce a valid conversion.

Align zeros aligns the vertical axes visually without shifting data. Axis units
and original/corrected/normalized status identify the plotted values. Heat-flow
sign depends on the instrument convention; confirm that convention before
interpreting a signal as exothermic or endothermic.

6. Comparing experiments and replicates
======================================

Open Experiment comparison from the top menu bar. Add the desired experiments,
enable their visibility and select Original, Corrected or Normalized state.
Select a row to adjust style, color or Y offset; edit the legend name and use
the arrows to change order. Blank and normalization settings belong to each
experiment individually.

Choose the axis, signals and Union of domains or Common overlap. Individual
curves retain their own X coordinates. Stack applies visual offsets; Reset to
zero removes them. These offsets do not change the measurements.

For replicate groups:
1) Select experiments belonging to the same physical group.
2) Create a named group with those members in the statistics panel.
3) Enable statistics mode and choose Mean only, Mean with ±1 standard deviation
   band, Mean with individual curves, or Individual curves only.
4) Keep automatic spacing or specify the number of points. Read the included
   and excluded curve summary, and check units before comparing groups.
5) Use Export in the statistics panel to save group statistics.

Statistics may interpolate onto a common grid according to domains and settings.
This step is separate from individual plotting and blank correction. Sample
count can vary along the X axis. Standard deviation uses ddof=1 and is undefined
with fewer than two values. A ±1 standard deviation band is not a confidence
interval.

7. Defining and quantifying zones
================================

In Zones, first choose a suitable display axis, name the zone, enter its bounds
and click Add. Select on plot also lets you set bounds by dragging across the
plot; disable zoom/pan if those tools capture the gesture. Update changes the
selected zone; Delete removes it. A zone retains the axis used to define it.

Choose None or Constant for the heat-flow baseline. For Constant, enter its value
in the relevant signal unit. Read the active zone summary or open Show all
results for the complete report.

Reports distinguish mass changes, extrema and available heat-flow information.
Heat flow is integrated over time even when selection uses temperature. Areas
on either side of the baseline remain separate. Portions outside the zone are
not joined together.

A temperature zone may be crossed during both heating and cooling: all passages
are retained. Prefer a time zone to isolate one event. Do not interpret an
ambiguous overall change as a single passage.

Comparison reports follow the displayed individual/statistical mode and use
values without visual offsets. For a group mean, the report gives endpoint
values, change and extrema of the mean signal. The change envelope derived
from the pointwise band is neither the standard deviation of the change nor
a confidence interval. It is not a calorimetric integral.

8. Customizing and exporting plots
=================================

The plot toolbar restores the initial view, navigates through views, pans,
zooms and saves an image. Plot settings provides title, legend, fonts, axes,
ticks, curve styles, reference lines and annotations. A logarithmic scale
requires compatible values. Apply confirms settings; cancelling preserves the
previous presentation. An .atgstyle.json template allows style reuse.

File > Export result (Ctrl+E) exports the active experiment's result. Choose CSV
or TSV and a new destination name. An accompanying JSON file records sources,
units, parameters, warnings and provenance.
CSV: semicolon separator, decimal comma, UTF-8 with BOM.
TSV: tab separator, decimal point, UTF-8.

In the comparison window, Export data saves the selected display mode's series.
Each column block retains its own X values and length; shorter series are padded
with empty cells. Export figure offers PNG, SVG and PDF. Keep JSON files with
the tables for later interpretation. Never choose an input file or the open
project as an export destination.

9. Saving, moving and reopening projects
=======================================

Ctrl+S saves; Ctrl+Shift+S chooses a new destination. Ctrl+O opens an .atgproj;
Ctrl+N starts a new project. An asterisk in the title indicates unsaved changes.

A project stores source references and hashes, blanks, settings, zones,
comparisons and tool inputs. It does not embed complete experimental tables.
To archive or share a session, retain the .atgproj AND all source and blank
files, preferably in the same folder or its subfolders. A CSV export is not
a session backup.

If a source moved, use the resolution workflow offered when opening the project.
If its hash changed, check the file before accepting it. Save under a new name
to preserve an earlier project version. Saving protects experimental files
against replacement.

10. Stoichiometric calculations
==============================

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

For gaseous reactants, choose Finite mass, Partial pressure/volume/temperature,
molar ppm or ppmv, or Gas in excess. Check each field's unit. PVT conversions
use the ideal-gas model. Declaring excess gas assumes it does not limit the
reaction. Do not confuse ppmv with a mass fraction.

These are theoretical balances. Atomic balance does not demonstrate thermodynamic
feasibility or reaction speed under your experimental conditions. Correctly
distinguish gaseous and condensed species when interpreting mass loss or gain.

11. Periodic table
==================

Open Periodic table from the top menu. Search by name, symbol or atomic number,
then select an element to view its information. The detailed view and information
copy action allow reuse of displayed values. All 118 elements are included and
the table works offline.

The calculation reference masses remain those used by stoichiometry. Bundled
Mendeleev data enriches browsing; its masses or other enriched properties do not
silently replace the calculation reference. Missing properties remain unavailable.
Provenance and the MIT license for the Mendeleev v0.20.0 snapshot accompany the
distributed resources.

12. Troubleshooting
===================

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

13. License and contact
======================

© 2026 Valentin Legrand. Original code is under PolyForm Noncommercial 1.0.0.
The full text is in LICENSE.txt and its terms apply. Source is available with
a noncommercial-use restriction. Third-party libraries and data retain their
own licenses, described in THIRD_PARTY_NOTICES.txt and the notices accompanying
the distribution.

Questions, suggestions and licensing enquiries:
valentin.legrand@emse.fr

References:
https://polyformproject.org/licenses/noncommercial/1.0.0
https://docs.python.org/3/library/venv.html
https://pyinstaller.org/en/stable/operating-mode.html
