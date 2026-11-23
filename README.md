# NdevTools | Smart BIM Tools

## CAD Tools — CAD to Walls and CAD to Grids

Turn linked or imported CAD linework into Revit walls and grids. **CAD to Walls** scans wall thicknesses automatically and lets you map them to loaded wall types before placement. **CAD to Grids** reads grid labels where available, suggests missing names, and lets you create horizontal, vertical and sloped grids together. Open either command from **NdevTools → 3D Model → CAD Tools**.

## Sheet Clipboard — Cut, Copy, and Paste

**Copy and Paste between two open projects.** Open both projects in the same Revit session. Copy detail views, title blocks, lines, or images from a sheet in one project and paste them onto a sheet in the other. You can also copy selected details from a section into a section or drafting view in the other project.

Detail groups are included with their filled regions, lines, and notes. Matching destination type names are reused; missing types are copied.

**Cut and Paste within one project.** To move four detail views from S501 to S502, select their viewports, choose **Cut**, open S502, and choose **Paste**. Click to place the group with its spacing intact. One Revit **Undo** returns it to S501.

![Powerful tools, a more global experience. 20 languages supported.](media/NdevTools-20-Language-Support.png)

**NdevTools supports 20 language options** for pyRevit ribbon button titles and bundle tooltip descriptions, with black icons for light themes and white icons for dark themes. The tool commands remain the same across languages.

**NdevTools** is a collection of Autodesk Revit productivity commands built for **pyRevit**. The extension combines model-based detailing, view and sheet management, linked-model wall/opening tracing, CAD wall and grid mapping, structural framing, and personal productivity tools in one ribbon tab. It is developed by **Nataraj Devaraj**.

**GitHub:** [ndev16/NdevTools](https://github.com/ndev16/NdevTools)  
**Feedback and feature requests:** [GitHub Issues](https://github.com/ndev16/NdevTools/issues)

## Multilingual support — 20 languages

NdevTools includes localized **ribbon titles and bundle tooltip descriptions for all 21 commands** in the following 20 pyRevit locale options:

| Language | Locale code | Language | Locale code |
| --- | --- | --- | --- |
| Arabic | `ar` | Brazilian Portuguese | `pt_br` |
| Bulgarian | `bg` | Chinese (Simplified) | `chinese_s` |
| Chinese (Traditional) | `chinese_t` | Czech | `cs` |
| Dutch | `nl_nl` | English (Great Britain) | `en_gb` |
| English (USA) | `en_us` | Farsi (Persian) | `fa` |
| French | `fr_fr` | German | `de_de` |
| Hungarian | `hu` | Italian | `it_it` |
| Japanese | `ja` | Korean | `ko` |
| Polish | `pl` | Russian | `ru` |
| Spanish | `es_es` | Ukrainian | `uk` |

**Language selection:** An explicit **pyRevit Settings → Language** choice takes priority. With no override, NdevTools follows the active Revit interface language. Unavailable UI strings fall back to English. Revit's spelling-dictionary preference does not change its interface language.

**Localization scope:** The 20-language coverage applies to button titles and bundle tooltip descriptions for all 21 commands. Some longer, dynamically generated messages and custom dialog text may remain in English. Translations, especially specialized engineering terminology and right-to-left presentation, should be reviewed by native speakers. See [Bundle translations](BUNDLE_TRANSLATIONS.md) for details.

**Theme icons:** Each of the 21 commands includes `icon.png` (dark/black artwork for a light background) and `icon.dark.png` (white artwork for a dark background). Availability of theme switching depends on the Revit/pyRevit version.

## Ribbon layout

[![NdevTools ribbon with CAD Tools in 3D Model, Sheet Clipboard in Sheets, and Match Properties, Renumber and Tab Hider in Modify](media/NdevTools-Ribbon.png)](media/NdevTools-Ribbon.png)

[Open the full-size ribbon](media/NdevTools-Ribbon.png)

Open the **NdevTools** tab in Revit. Its six panels run from left to right: **Welcome → Annotation → Sheets → Modify → 3D Model → Handy**.

In **Sheets**, the third column has **Move Views** above **Sheet Clipboard**. Open the clipboard dropdown for **Cut**, **Copy**, and **Paste**. The next panel, **Modify**, stacks **Match Properties**, **Renumber**, and **Tab Hider** from top to bottom. In **3D Model**, **CAD Tools** follows **Wall Tracing** and **FramePilot** and contains **CAD to Walls** and **CAD to Grids**.

| Panel | Ribbon button | Purpose |
| --- | --- | --- |
| **Welcome** | Welcome | Show NdevTools information, useful links and contact details. |
| **Annotation** | Vulcraft Deck Region | Create a concrete filled region that follows a selected Vulcraft structural deck profile in section. |
| **Annotation** | Auto Detail Generator | Trace selected host-model geometry into 2D filled regions, lines and supported detail components. |
| **Sheets** | SheetPilot | Configure and place up to 25 unplaced views per sheet across multiple sheets using saved viewport positions. |
| **Sheets** | Sheet Manager | Create sheets in bulk or rename existing sheets. |
| **Sheets** | Match Crop Regions | Apply one plan view's crop region to multiple compatible plan views. |
| **Sheets** | Viewport Position Manager | Save, rename, manage and reuse named sheet viewport positions. |
| **Sheets** | ViewPilot | Review and batch rename, duplicate, and assign compatible view settings. |
| **Sheets** | Move Views | Arrange selected sheet items in two previews and open an item on its sheet for native Revit editing. |
| **Sheets** | Sheet Clipboard → Cut | Move selected sheet items together to another sheet in the same project. |
| **Sheets** | Sheet Clipboard → Copy | Copy placed views, sheet graphics, title blocks, or selected detail elements from a section. |
| **Sheets** | Sheet Clipboard → Paste | Place the copied group on a sheet or paste section details into a destination view in either open project. |
| **Modify** | Match Properties | Apply selected instance properties or the source type to compatible targets. |
| **Modify** | Renumber | Number elements in pick order with a configurable start, step and exclusions. |
| **Modify** | Tab Hider | Choose which editable ribbon tabs and add-in panels are visible. |
| **3D Model** | Wall Tracing | Trace supported structural walls and verified rectangular openings from an architectural link. |
| **3D Model** | FramePilot | Create structural framing for Roof, Flat Truss, Floor and Ceiling hosts, or sketch a beam system. |
| **3D Model** | CAD Tools → CAD to Walls | Automatically scan CAD wall thicknesses, map loaded wall types, and place walls with optional door/window openings. |
| **3D Model** | CAD Tools → CAD to Grids | Review CAD grid names, edit proposed names, and create horizontal, vertical and sloped grids together. |
| **Handy** | Notes | Write formatted, illustrated notes with multiple A4 portrait/landscape sheets and local saving. |
| **Handy** | Useful Links | Use Image to Text and Convert Case in a modeless embedded browser. |

## Tools and usage

### Welcome

Open the **Welcome** button in the Welcome panel to view the extension's information and the developer's GitHub, LinkedIn and feedback links. The Welcome command is for information and navigation; it does not modify the open Revit model.

### Annotation → Vulcraft Deck Region

Create a static **concrete filled region** based on the corrugated profile of structural metal decking in a straight Revit section view.

**Supported deck configurations:** Vulcraft **1.5C-36, 2C-36 and 3C-36**, with the selectable gages offered by the command. The profile uses deck dimensions such as depth, pitch, upper and lower flats.

**Typical workflow:** Open a straight section, select the structural floor, choose the deck profile and gage, pick the **left end of a lower flat** as the profile anchor, and select the desired Revit filled-region type. The command generates a concrete region aligned to the deck geometry, with profile extent clipped to the selected floor boundaries.

**Scope:** Requires a valid selected structural floor, visible deck geometry and an accurately picked anchor. The result is 2D view-specific annotation, not replacement 3D geometry.

### Annotation → Auto Detail Generator

Create 2D construction-detail representations from visible, supported host-model elements in **plan views and straight sections**.

**Supported model categories:** floors, walls, roofs, structural foundations and structural framing.

**Typical workflow:** Open a supported view, launch Auto Detail Generator, choose a filled-region type and outline style for each model category, select the model elements, and create the view-specific detailing. Choose **No Fill** with a line style where you prefer detail lines instead of filled regions.

**Additional detailing options:**

- **Roofs:** place compatible line-based detail components along straight roof slopes in sections or roof top-face edges in plans.
- **Floors:** place line-based detail components along traced horizontal floor segments, splitting at openings where applicable.
- **Structural framing:** choose a loaded point-based or line-based detail component, or **None**, and align detail components with the traced framing center.
- **CMU walls:** replicate repeating-detail instances horizontally or vertically in sections using an existing instance as a template.

**Scope:** Creates static 2D representations. Curved roof edges are not supported. The command traces host-model elements; plan wall tracing uses the main view cut height, not the cut heights of individual plan regions.

### Sheets → SheetPilot (Place Views on Sheet)

**Place and organize views.** Configure up to 25 views per sheet, choose viewport types, and reuse saved positions. Prepare multiple sheets in one window, then place the configured views together.

![SheetPilot: multi-sheet view placement with viewport types and saved positions](media/screenshots/SheetPilot.png)

**Sheet Pilot** automates placing unplaced views on multiple Revit sheets using named X/Y positions saved by **Viewport Position Manager** (or the compatible Crop Position Manager). Configure multiple sheets in one window, with up to **25 views per sheet**.

**Prerequisites — save a sheet position first:**

1. Manually place a reference view on a Revit sheet and arrange its viewport where you want it.
2. Open **Viewport Position Manager**, select the placed viewport, and use **Save New Position** or **Capture New Position + Apply** to acquire and save the viewport's X/Y sheet position under a recognizable name.
3. Repeat for any additional sheet locations needed. **At least one saved position is required** for Sheet Pilot. Saved positions are maintained separately by Revit version.

**Typical workflow:** Open Sheet Pilot, expand a target sheet, select **+ Add View**, choose an available unplaced view, its viewport type, and a saved position. Repeat for other views and sheets, then click **PLACE ALL VIEWS**. The same saved position can be selected again where appropriate; review placements to prevent overlaps.

**Placement and safety:** For standard viewports, the tool first creates a viewport at a temporary sheet location, then moves the existing viewport to the selected saved X/Y coordinate. For supported plan views it temporarily hides the four visibility category groups and Revit links during repositioning, then restores the original visibility and view template without repositioning again. Three-dimensional views, drafting views, legends and schedules bypass that visibility procedure; schedules use their insertion point. Each view's placement is independently rollback-protected on failure.

### Sheets → Sheet Manager

Two workflows are available within one command:

**Create Sheets:** Choose a title block, enter multiple sheet records such as `S1.1 - FOUNDATION SLAB PLAN`, and create them in a batch.

**Rename Sheets:** Select existing sheets, change their numbers or names, and apply the changes together. Validation catches duplicate or invalid sheet numbers; the rename workflow also supports number swaps and reports results.

Built-in help links provide access to the project's GitHub and developer information.

### Sheets → Match Crop Regions

Match model crop boundaries from one reference plan view to several target plan views.

**Typical workflow:** Choose a compatible reference plan with an enabled, **unsplit** crop region; select the target plan views; decide whether to copy the source view scale; and apply the crop regions. Target scales are preserved if scale copying is disabled.

The command uses model coordinates, handles compatible crop visibility and annotation-crop offsets, and removes target split crops where possible. Targets with scope-box-controlled crops are skipped. View-specific failures are reported without stopping the remaining targets.

### Sheets → Viewport Position Manager

Use named positions to standardize sheet layouts. The command supports **Apply Saved Position**, **Save New Position**, **Capture New Position + Apply**, **Show Saved Positions**, **Rename**, **Overwrite** and **Delete**.

**Typical workflow:** Start with a reference viewport already placed on a sheet. Save its X/Y coordinates as a named position, then apply that position to one or more selected viewports. You can also capture and immediately apply a new position.

The command stores up to **10 positions per Revit version** and maintains separate position sets for different Revit versions. When applying coordinates, it temporarily adjusts supported category and link visibility, then restores original visibility, templates and pinned state.

### Sheets → ViewPilot

**Manage views in one place.** Find, rename and duplicate project views with a live name preview. Manage scope boxes, view templates and common settings, then review your changes before applying them.

![ViewPilot: view filters, live rename previews, duplication and common settings](media/screenshots/ViewPilot.png)

Batch rename and duplicate views with previews, compatible View Template and Scope Box assignments, and a separate **Review Changes** step. Rename rules support Find/Replace, prefixes, suffixes, case changes, regular expressions, and numbering. Duplication supports Duplicate, With Detailing, and As Dependent where compatible.

**Typical workflow:** Check source views, configure names, copies and settings, open Review Changes, then select **Apply Checked Changes** and confirm. Common Duplication Method locks each checked compatible source to one copy; turn it off to reset copy quantities for selected or visible views. Reviewing pending changes and the Project Health Report are read-only. Revit writes use the command's undoable transaction workflow; template-controlled and dependent-view settings can be read-only.

### Sheets → Move Views

![Move Views showing S101 Framing Plans as the target on the left and S001 Title Sheet as the source on the right](media/screenshots/MoveViews.png)

*In this example, select Central Pile on S001 — Title Sheet (right), then drag it to the spot you want on S101 — Framing Plans (left).*

In **Move Views**, choose a target sheet on the left and a source sheet on the right. Ctrl-click items in the preview or open its **Views** list. Drag a selection within or between previews to set its position. **Move to target** keeps the original sheet coordinates. Double-click an item to select it on its Revit sheet for editing. **Swap** exchanges the two previews.

### Sheets → Sheet Clipboard

**Copy between projects.** Open both projects in the same Revit session and keep the source project open. Choose **Sheets → Sheet Clipboard → Copy** after selecting the source items.

| What you want to copy | Select in the source project | Where to use Paste |
| --- | --- | --- |
| Detailing inside a section | Select detail lines, text notes, filled regions, detail components, or imported or linked raster images in the open section. | Open a section or drafting view in the destination project. |
| A whole detail view | Select the viewport of a drafting view, section, or detail view on its sheet. | Open the destination sheet. Paste creates a view with its supported detailing and places it on the sheet. |
| Sheet graphics or a title block | Select sheet lines, arcs, annotations, raster images, or title blocks directly on the sheet. | Open the destination sheet. You can also paste on the same sheet or another sheet in the source project. |

Choose **Paste** and click where the center of the group should land. Items keep their relative spacing. Raster images retain their dimensions, rotation, and pin state. You can paste the same copy again or press **Esc** while picking a point to keep it for later.

If Revit opens tabs for newly pasted views, Sheet Clipboard closes those tabs. For a mixed selection, the paste result lists each skipped item and its reason. To duplicate a structural plan viewport or schedule, use sheets in the same project.

**Move items within one project.** With **Sheet Clipboard → Cut**, the selected views stay on their source sheet until you paste them onto another sheet in the same project. One Revit **Undo** restores the group.

Within the same project, Copy uses **Duplicate with Detailing** for supported plans, sections, elevations and detail or drafting views, and **Duplicate** for 3D views. Ordinary schedules get an independent copy with the original splits and only the selected segments placed. For legends and graphical column schedules, choose from the available placement or duplication options.

### Modify → Match Properties, Renumber and Tab Hider

- **Match Properties.** Pick a source element, check properties to apply, select compatible targets and click **Finish**. Review the results in the report. Text notes keep their wording and tags keep their references.
- **Renumber.** Choose the category, starting value, step and any exclusions. Click **Start picking**, select elements in sequence and press Esc to finish.
- **Tab Hider.** Check the tabs or add-in panels to show and uncheck those to hide. Click **Apply** to keep those choices across projects and Revit restarts. **Show All** shows all loaded, editable entries and saves that choice. The header includes Help, a GitHub star button for the project, and a link to Nataraj Devaraj on LinkedIn.

### 3D Model → Wall Tracing

Create supported host-model structural Basic Walls and verified rectangular openings from a selected architectural Revit link.

**Typical workflow:** Select a loaded link and source levels, map host bottom/top levels, review suggested host Basic Wall types, optionally enable **Combine Nearby Openings** and set Maximum Gap, then click **Create Walls** and review the per-item report. Choose **None** to exclude a source type. Type suggestions use structural-layer thickness; review material and structural suitability yourself.

The command reads the link without editing it. It supports straight vertical Basic Walls and horizontal translated, rotated or mirrored links; unsupported wall profiles and tilted/scaled links are skipped. Verified insert-local geometry is preferred for rectangular openings, with a controlled hosted Door/Window parameter fallback where geometry cannot resolve a cut. Nearby-opening combination is off by default and does not cross source walls. Matching host walls/openings are retained for reruns, while missing supported openings can be repaired.

Wall creation precedes openings in one undo group, with per-item rollback and a full rollback on fatal failure or cancellation. Selected host walls can also be processed with **Allow joins on selected walls**. See the [Wall Tracing usage guide](NdevTools.tab/3D%20Model.Panel/Create%20walls%20and%20opening.pushbutton/README_Wall_Tracing.md) for detection rules, mapping details and limitations.

### 3D Model → FramePilot

Create structural framing for **Roof, Flat Truss, Floor and Ceiling** hosts. Search loaded framing types, choose roof ridge framing when applicable, set Workplane and Z Justification independently, then choose **12, 16, 24 inches or Custom** spacing and edit Comments. Click **FRAME**, select matching hosts, and review the report.

For roof hosts, beam-system boundaries follow the actual selected top or bottom planar faces, including roof openings and cuts at joins. The report lists committed beam-system profiles; a failed host rolls back its replacement framing.

**Sketch Beam System** uses Revit's native sketch mode. Enter Elevation from Level in project units or feet/inches; this is an offset from the existing Revit work plane, not a level reassignment. After finishing the sketch, FramePilot applies the current framing settings where Revit permits it. Flat Truss creates Structural Framing beam systems rather than native Revit Truss families. Tracked framing is replaced only after a valid plan; failed host transactions roll back. Review warnings and member properties.

### 3D Model → CAD Tools → CAD to Walls

Create Revit walls from the faces in a linked or imported CAD drawing. The mapping window stays open while you work in Revit.

**Typical workflow:** Choose the **CAD drawing**, select **With Layers** and check the wall layers, or use **Without Layers**. Source changes scan automatically; there is no Scan button. Review the measured **Thickness**, **Candidates** and **Revit type / size** rows, set the bottom/top levels and offsets, then click **Place**.

**Mapping and placement options:**

- **Wall types:** Each thickness group has a searchable dropdown of loaded Revit wall types. Available width matches are suggested automatically; review the choice before placing. **None - do not trace** skips that group. **Refresh types** updates the list after you add or change types in the project.
- **Scan settings and units:** Adjust scan spacing, minimum overlap and the optional minimum wall-thickness exclusion. Imperial is the startup default, with level elevations in feet and inches and wall thicknesses in inches; metric units are also available.
- **Levels and offsets:** Set **Bottom level**, **Bottom offset**, **Top level** and **Top offset**. **Same as bottom** uses one level reference, with the offsets defining wall height.
- **Opening controls:** Separate **Door openings** and **Window openings** checkboxes enable or skip cuts. Both start checked. Walls are created before openings. Walls seven feet or shorter stay solid; on taller walls, detected doors extend from the actual wall bottom to seven feet, and detected windows from three to seven feet above that bottom.
- **Save and review:** **Save mapping** remembers the mappings and opening choices. **Trace report** shows created elements, skipped candidates and failure reasons, with a copy option. Matching previously traced elements are detected on repeat placement to avoid duplicates.

The window displays **NdevTools is scanning wall thickness...** while scanning and **Wall Tracing is placing your walls...** during placement. Review the proposed types, CAD-derived opening locations and trace report before using the result in production.

### 3D Model → CAD Tools → CAD to Grids

Create all mapped grid directions in one operation, retaining sloped CAD axes at their original angles. The modeless window lets you continue editing Revit before placement.

**Typical workflow:** Choose the **CAD drawing** and its **Grid layers**. Review **Horizontal grids** from bottom to top and **Vertical grids** from left to right, edit the proposed names, then click **Create grids** once to place both lists together.

**Naming and review options:**

- **Readable grids:** The read-only **Actual CAD name** shows the detected label. **Proposed Revit name** starts with that same value and is editable.
- **Unreadable grids:** Rows are grouped under neighboring labels, such as **Between B and C**. Missing names receive editable suggestions such as **B.1**, **B.2** and **B.3**. If a direction has no readable labels, horizontal names start at **A** and vertical names at **1**.
- **Source DWG:** Linked drawings supply the source file for reading bubble text. For an imported drawing, use **Source DWG…** to choose the original file. Review suggested names when labels cannot be read.
- **Existing grids:** Detected existing grids are shown read-only. Placement rechecks the model, and matching grids are retained on reruns to avoid duplicates.

### Handy → Notes

**Your notebook, inside Revit.**

**Ever wished you could write notes right inside Revit? Now you can.**

Capture design ideas, coordination comments and reminders while you work. Format your text, apply colors and highlights, and insert images to make your notes clear.

Create multiple A4 sheets within a single note, choosing portrait or landscape for each sheet. Search your notebook, save locally with autosave, and export notes in **Word-compatible RTF format**, including formatted text and images.

![Notes: formatted text, an inserted image and multiple A4 sheets inside Revit](media/screenshots/Notes.png)

**Sheet layout:** Use **+ Add sheet** to add sheets and the sheet dropdown to switch between them. Each sheet independently uses **A4 Portrait (210 × 297 mm)** or **Landscape (297 × 210 mm)**. Notes opens as a modeless window, with your notebook stored outside the Revit model.

Orientation changes the visible paper dimensions and export settings. **Fill window** expands the writing area; **Hide notes** and the draggable sidebar give you more space. Save manually or with autosave. RTF export includes every sheet in order with its selected A4 orientation and 20 mm margins; text export includes sheet headings. Previous saved files and deleted notes remain recoverable. Existing plain-text and rich-text notes remain supported.

Help includes usage and developer links. The footer has a GitHub button and optional BIM humor, enabled by default with a remembered On/Off choice. The Notes and Useful Links ribbon tooltips omit printed developer profile URLs. These tools do not modify the Revit model.

### Handy → Useful Links

Open **Image to Text** ([imagetotext.info](https://www.imagetotext.info/)) or **Convert Case** ([convertcase.net](https://convertcase.net/)) inside a modeless Revit window. Both pages stay open when switching tools. Back, Forward, Reload and **Open in browser** act on the selected site.

Embedded browsing requires an internet connection and the active Revit installation's WebView2 components/runtime. If unavailable, use Open in browser. You choose what to submit on each website; NdevTools does not automatically send model data. Help, developer links, and the default-on humor switch are also available.

## Installation

1. Install **Autodesk Revit** and **pyRevit**.
2. **Install directly from Extension Manager:** Open **pyRevit Extension Manager**, find **NdevTools**, and click **Install**. Then continue at step 6.
3. **Manual alternative:** Download this repository as a ZIP (or clone it).
4. Extract the repository files into a folder named **`NdevTools.extension`** inside a pyRevit extensions location. The `NdevTools.tab` folder and `extension.json` must sit directly inside `NdevTools.extension`.
5. If your folder is not already registered with pyRevit, add its parent extensions location using pyRevit's settings or extension configuration.
6. Reload pyRevit or restart Revit. The **NdevTools** ribbon tab displays the Welcome, Annotation, Sheets, Modify, 3D Model and Handy panels.

**Note:** NdevTools is registered in [pyRevit's official extension package registry](https://github.com/pyrevitlabs/pyRevit/blob/develop/extensions/extensions.json), so you can install the package directly through pyRevit Extension Manager. Steps 3-5 are only needed for manual installation.

**Folder structure (abbreviated):**

```text
NdevTools.extension/
├── extension.json
├── NdevTools.tab/
│   ├── bundle.yaml
│   ├── Welcome.panel/
│   │   └── Welcome.pushbutton/
│   ├── Annotation.panel/
│   │   └── col1.stack/
│   │       ├── Conc Slab on metal deck.pushbutton/
│   │       └── Detail Generator.pushbutton/
│   ├── Sheets.panel/
│   │   ├── col1.stack/
│   │   │   ├── BulkPlaceViews.pushbutton/   # Sheet Pilot
│   │   │   ├── Rename Sheets.pushbutton/
│   │   │   └── ViewPilot.pushbutton/
│   │   ├── col2.stack/
│   │   │   ├── Crop Extents.pushbutton/
│   │   │   └── Viewport Position Manager.pushbutton/
│   │   └── col3.stack/
│   │       ├── Move Views.pushbutton/
│   │       └── Clipboard.pulldown/      # Cut, Copy, Paste
│   ├── Modify.panel/
│   │   └── col1.stack/
│   │       ├── Match Properties.pushbutton/
│   │       ├── Renumber.pushbutton/
│   │       └── Tab Hider.pushbutton/
│   ├── 3D Model.Panel/
│   │   ├── Create walls and opening.pushbutton/
│   │   ├── FramePilot.pushbutton/
│   │   └── CAD Tools.pulldown/
│   │       ├── CAD to Walls.pushbutton/
│   │       ├── CAD to Grids.pushbutton/
│   │       └── lib/
│   └── Handy.panel/
│       ├── Notes.pushbutton/
│       └── Useful Links.pushbutton/
├── README.md
└── LICENSE
```

Each command includes its script, theme icons, bundle configuration, and any XAML, browser UI, images or support modules it uses. Keep the button folders intact.

## Compatibility

Commands are written for **pyRevit** and the IronPython 2.7 runtime, using Revit API patterns for **Revit 2022–2027** where supported by the individual tools. Move Views, Sheet Clipboard, CAD to Walls and CAD to Grids require Revit 2023 or later. The packaged CAD commands were tested in Revit 2025; this release has not been retested in the other supported Revit versions. Some commands have view, family, category or loaded-link prerequisites; review each tool's usage section above.

## What's new

### November 24, 2026 — CAD Tools

Added **CAD Tools** with **CAD to Walls** and **CAD to Grids**, including automatic wall-thickness scanning, editable mappings, grid-name review, and ribbon titles and tooltips in 20 language options.

### November 16, 2026 — Copy sheet and section details between projects

Copy a whole detail view between sheets, or copy just the lines, notes, and images inside a section into another project’s section or drafting view. Sheet graphics and title blocks can also travel between projects. These workflows passed in Revit 2023 through 2027.

### November 6, 2026 — Cut and paste placed views between sheets

- **Sheet Clipboard** lets you cut several placed detail views on one sheet and paste them together on another. Click the destination point to move the original views with their detailing and relative spacing intact. One Revit Undo returns the group. Choose **Copy** when you want to keep the originals.
- **Move Views** shows the source and target sheets side by side. Drag items between the previews, or double-click an item to select it on its sheet and continue editing in Revit.
- **Match Properties** applies selected properties to compatible elements. **Renumber** numbers elements in the order you pick them. Both are in the new **Modify** panel.
- **Tab Hider** remembers which ribbon tabs and add-in panels you show or hide. Click **Apply** to keep your choices across Revit restarts.

**Move Views**, **Sheet Clipboard**, **CAD to Walls** and **CAD to Grids** require Revit 2023 or later. The ribbon now has 21 commands across six panels, with titles and tooltips in 20 languages. [Full changelog](CHANGELOG.md)

## Support and feedback

Use [GitHub Issues](https://github.com/ndev16/NdevTools/issues/new) for bug reports and feature suggestions. When describing an issue, include the Revit and pyRevit versions, tool name, steps and any useful screenshots or error messages.

**Developer:** Nataraj Devaraj  
**GitHub:** https://github.com/ndev16  
**LinkedIn:** https://www.linkedin.com/in/nataraj016/  
**Email:** devnataraj39@gmail.com

## License

Copyright (C) 2026 Nataraj Devaraj. Released under the **GNU General Public License v3 (GPL-3.0-only)**. See [LICENSE](LICENSE) for details.
