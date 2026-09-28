# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms, script
from System.Collections.Generic import List
import json


# ============================================================
# VIEWPORT POSITION MANAGER
#
# REVIT 2022 - 2027
# IronPython / Python 2.7 Compatible
#
#
# WORKFLOW
# ------------------------------------------------------------
#
# MAIN MENU:
#
# 1. Apply Saved Position
# 2. Save New Position
# 3. Capture New Position + Apply
# 4. Rename Saved Position
# 5. Overwrite Saved Position
# 6. Delete Saved Position
# 7. Show Saved Positions
#
#
# SAVE NEW POSITION:
#
#   Select reference viewport from views ALREADY ON SHEETS
#       ↓
#   Read exact viewport X/Y
#       ↓
#   Ask for position name
#       ↓
#   Save
#
#
# APPLY SAVED POSITION:
#
#   Choose saved position
#       ↓
#   Select MULTIPLE target viewports already on sheets
#       ↓
#   Apply same X/Y to all
#
#
# Maximum:
#
#   10 positions PER REVIT VERSION
#
# Revit 2022 has separate memory
# Revit 2023 has separate memory
# ...
# Revit 2027 has separate memory
#
# ============================================================


doc = revit.doc
uidoc = revit.uidoc


# ============================================================
# SETTINGS
# ============================================================

MAX_POSITIONS = 10


SUPPORTED_VERSIONS = [
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
    "2027"
]


# ============================================================
# CURRENT REVIT VERSION
# ============================================================

REVIT_VERSION = str(
    doc.Application.VersionNumber
)


if REVIT_VERSION not in SUPPORTED_VERSIONS:

    forms.alert(
        "This tool supports:\n\n"
        "Revit 2022\n"
        "Revit 2023\n"
        "Revit 2024\n"
        "Revit 2025\n"
        "Revit 2026\n"
        "Revit 2027\n\n"
        "Current Version: {}".format(
            REVIT_VERSION
        ),
        title="Viewport Position Manager",
        exitscript=True
    )


# ============================================================
# VERSION-SPECIFIC MEMORY
# ============================================================

CONFIG_SECTION = (
    "NDEV_VIEWPORT_POSITION_MANAGER_{}"
    .format(
        REVIT_VERSION
    )
)


# ============================================================
# ELEMENT ID VALUE
#
# Works with old and newer Revit APIs.
# ============================================================

def id_value(element_id):

    try:

        return element_id.IntegerValue

    except:

        return element_id.Value


# ============================================================
# LOAD SAVED POSITIONS
# ============================================================

def load_positions():

    cfg = script.get_config(
        CONFIG_SECTION
    )

    try:

        raw_data = cfg.get_option(
            "positions_json",
            "[]"
        )

        positions = json.loads(
            raw_data
        )

        if not isinstance(
            positions,
            list
        ):

            positions = []

    except:

        positions = []


    return positions[
        :MAX_POSITIONS
    ]


# ============================================================
# SAVE POSITIONS
# ============================================================

def save_positions(
        positions
):

    cfg = script.get_config(
        CONFIG_SECTION
    )

    cfg.positions_json = json.dumps(
        positions[
            :MAX_POSITIONS
        ]
    )

    script.save_config()


# ============================================================
# CHECK DUPLICATE NAME
# ============================================================

def name_exists(
        positions,
        name,
        ignore_index=None
):

    check_name = (
        name
        .strip()
        .lower()
    )


    for index, position in enumerate(
            positions
    ):

        if (
            ignore_index is not None
            and
            index == ignore_index
        ):

            continue


        existing_name = (
            position
            .get(
                "name",
                ""
            )
            .strip()
            .lower()
        )


        if existing_name == check_name:

            return True


    return False


# ============================================================
# GET ALL VIEWPORTS THAT ARE ACTUALLY ON SHEETS
# ============================================================

def get_placed_viewports():

    viewports = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    result = []


    for viewport in viewports:

        try:

            sheet = doc.GetElement(
                viewport.OwnerViewId
            )


            view = doc.GetElement(
                viewport.ViewId
            )


            if sheet is None:
                continue


            if view is None:
                continue


            if not isinstance(
                sheet,
                DB.ViewSheet
            ):

                continue


            result.append(
                {
                    "viewport":
                        viewport,

                    "view":
                        view,

                    "sheet":
                        sheet
                }
            )


        except:

            pass


    return result


# ============================================================
# CREATE DISPLAY NAME
# ============================================================

def viewport_display_name(
        viewport_data
):

    viewport = viewport_data[
        "viewport"
    ]

    view = viewport_data[
        "view"
    ]

    sheet = viewport_data[
        "sheet"
    ]


    return (
        "{} | {} | {} | Scale 1:{} | VP ID {}"
        .format(
            sheet.SheetNumber,
            sheet.Name,
            view.Name,
            view.Scale,
            id_value(
                viewport.Id
            )
        )
    )


# ============================================================
# SELECT ONE REFERENCE VIEWPORT
# ============================================================

def select_reference_viewport():

    placed_viewports = (
        get_placed_viewports()
    )


    if not placed_viewports:

        forms.alert(
            "No views are currently placed on sheets.",
            title="Viewport Position Manager"
        )

        return None


    display_items = []
    lookup = {}


    for viewport_data in placed_viewports:

        display_name = (
            viewport_display_name(
                viewport_data
            )
        )


        display_items.append(
            display_name
        )


        lookup[
            display_name
        ] = viewport_data


    display_items.sort()


    selected = forms.SelectFromList.show(
        display_items,
        title="Select Reference Viewport",
        button_name="Acquire Position",
        multiselect=False
    )


    if not selected:

        return None


    return lookup[
        selected
    ]


# ============================================================
# SELECT MULTIPLE TARGET VIEWPORTS
# ============================================================

def select_target_viewports(
        exclude_viewport_id=None
):

    placed_viewports = (
        get_placed_viewports()
    )


    display_items = []
    lookup = {}


    for viewport_data in placed_viewports:

        viewport = viewport_data[
            "viewport"
        ]


        if exclude_viewport_id is not None:

            if (
                id_value(
                    viewport.Id
                )
                ==
                exclude_viewport_id
            ):

                continue


        display_name = (
            viewport_display_name(
                viewport_data
            )
        )


        display_items.append(
            display_name
        )


        lookup[
            display_name
        ] = viewport_data


    display_items.sort()


    if not display_items:

        forms.alert(
            "No target viewports were found.",
            title="Viewport Position Manager"
        )

        return []


    selected_items = (
        forms.SelectFromList.show(
            display_items,
            title="Select Target Viewports",
            button_name="Apply Position",
            multiselect=True
        )
    )


    if not selected_items:

        return []


    return [
        lookup[item]
        for item in selected_items
    ]


# ============================================================
# READ VIEWPORT POSITION
# ============================================================

def get_viewport_position(
        viewport
):

    center = (
        viewport.GetBoxCenter()
    )


    return DB.XYZ(
        center.X,
        center.Y,
        0.0
    )


# ============================================================
# CHOOSE SAVED POSITION
# ============================================================

def choose_saved_position(
        positions,
        title="Select Saved Position"
):

    if not positions:

        forms.alert(
            "No saved positions exist for Revit {}."
            .format(
                REVIT_VERSION
            ),
            title="Viewport Position Manager"
        )

        return None


    display_items = []
    lookup = {}


    for index, position in enumerate(
            positions
    ):

        name = position.get(
            "name",
            "Position {}".format(
                index + 1
            )
        )


        x = float(
            position.get(
                "x",
                0.0
            )
        )


        y = float(
            position.get(
                "y",
                0.0
            )
        )


        source_sheet = (
            position.get(
                "source_sheet_number",
                ""
            )
        )


        display_name = (
            "{} | X: {:.4f} | Y: {:.4f}"
            .format(
                name,
                x,
                y
            )
        )


        if source_sheet:

            display_name += (
                " | Source: {}"
                .format(
                    source_sheet
                )
            )


        display_items.append(
            display_name
        )


        lookup[
            display_name
        ] = index


    selected = forms.SelectFromList.show(
        display_items,
        title=title,
        button_name="Use Position",
        multiselect=False
    )


    if not selected:

        return None


    return lookup[
        selected
    ]


# ============================================================
# CAPTURE REFERENCE POSITION
# ============================================================

def capture_reference_position():

    viewport_data = (
        select_reference_viewport()
    )


    if viewport_data is None:

        return None


    viewport = viewport_data[
        "viewport"
    ]

    view = viewport_data[
        "view"
    ]

    sheet = viewport_data[
        "sheet"
    ]


    center = (
        get_viewport_position(
            viewport
        )
    )


    return {
        "x":
            center.X,

        "y":
            center.Y,

        "viewport_id":
            id_value(
                viewport.Id
            ),

        "view_name":
            view.Name,

        "sheet_number":
            sheet.SheetNumber,

        "sheet_name":
            sheet.Name
    }


# ============================================================
# SAVE NEW POSITION
# ============================================================

def save_new_position():

    positions = (
        load_positions()
    )


    # --------------------------------------------------------
    # MAX 10
    # --------------------------------------------------------

    if len(positions) >= MAX_POSITIONS:

        forms.alert(
            "You already have {} saved positions "
            "for Revit {}.\n\n"
            "Delete or overwrite an existing position first."
            .format(
                MAX_POSITIONS,
                REVIT_VERSION
            ),
            title="Maximum Positions Reached"
        )

        return


    # --------------------------------------------------------
    # ONLY NOW ASK FOR REFERENCE VIEWPORT
    # --------------------------------------------------------

    captured = (
        capture_reference_position()
    )


    if captured is None:

        return


    # --------------------------------------------------------
    # SHOW ACQUIRED POSITION
    # --------------------------------------------------------

    continue_save = forms.alert(
        (
            "POSITION ACQUIRED\n\n"
            "View:\n{}\n\n"
            "Sheet:\n{} - {}\n\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Save this position?"
        ).format(
            captured["view_name"],
            captured["sheet_number"],
            captured["sheet_name"],
            captured["x"],
            captured["y"]
        ),
        title="Save Viewport Position",
        yes=True,
        no=True
    )


    if not continue_save:

        return


    # --------------------------------------------------------
    # ASK NAME
    # --------------------------------------------------------

    name = forms.ask_for_string(
        prompt=(
            "Enter a name for this viewport position.\n\n"
            "Examples:\n"
            "PLAN - CENTER\n"
            "PLAN - LEFT\n"
            "PLAN - RIGHT\n"
            "SECTION - TOP\n"
            "DETAIL - LOWER RIGHT"
        ),
        title="Position Name"
    )


    if not name:

        return


    name = name.strip()


    if not name:

        return


    # --------------------------------------------------------
    # DUPLICATE NAME CHECK
    # --------------------------------------------------------

    if name_exists(
            positions,
            name
    ):

        forms.alert(
            "A saved position named '{}' already exists."
            .format(
                name
            ),
            title="Duplicate Position Name"
        )

        return


    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    position_record = {

        "name":
            name,

        "x":
            captured["x"],

        "y":
            captured["y"],

        "revit_version":
            REVIT_VERSION,

        "source_view_name":
            captured["view_name"],

        "source_sheet_number":
            captured["sheet_number"],

        "source_sheet_name":
            captured["sheet_name"]
    }


    positions.append(
        position_record
    )


    save_positions(
        positions
    )


    forms.alert(
        (
            "POSITION SAVED\n\n"
            "Name: {}\n"
            "Revit: {}\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Saved Positions: {} / {}"
        ).format(
            name,
            REVIT_VERSION,
            captured["x"],
            captured["y"],
            len(positions),
            MAX_POSITIONS
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# APPLY POSITION TO TARGET VIEWPORTS
# ============================================================

def apply_position_to_targets(
        x,
        y,
        position_name,
        exclude_viewport_id=None
):

    target_data = (
        select_target_viewports(
            exclude_viewport_id
        )
    )


    if not target_data:

        return


    confirm = forms.alert(
        (
            "POSITION:\n"
            "{}\n\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "TARGET VIEWPORTS: {}\n\n"
            "Apply this position to all selected viewports?"
        ).format(
            position_name,
            x,
            y,
            len(target_data)
        ),
        title="Apply Viewport Position",
        yes=True,
        no=True
    )


    if not confirm:

        return


    successful = []
    failed = []


    # ========================================================
    # PROCESS EACH VIEWPORT
    # ========================================================

    for data in target_data:

        viewport = data[
            "viewport"
        ]

        view = data[
            "view"
        ]

        sheet = data[
            "sheet"
        ]


        transaction = DB.Transaction(
            doc,
            "Apply Viewport Position"
        )


        try:

            transaction.Start()


            # ------------------------------------------------
            # PIN STATE
            # ------------------------------------------------

            was_pinned = False


            try:

                was_pinned = viewport.Pinned

                if was_pinned:

                    viewport.Pinned = False

            except:

                pass


            # ------------------------------------------------
            # CURRENT CENTER
            # ------------------------------------------------

            current_center = (
                viewport.GetBoxCenter()
            )


            # ------------------------------------------------
            # TARGET POSITION
            # ------------------------------------------------

            target_center = DB.XYZ(
                x,
                y,
                current_center.Z
            )


            # ------------------------------------------------
            # MOVE
            # ------------------------------------------------

            viewport.SetBoxCenter(
                target_center
            )


            # ------------------------------------------------
            # RESTORE PIN
            # ------------------------------------------------

            try:

                if was_pinned:

                    viewport.Pinned = True

            except:

                pass


            transaction.Commit()


            successful.append(
                "{} | {} | {}".format(
                    sheet.SheetNumber,
                    sheet.Name,
                    view.Name
                )
            )


        except Exception as error:

            try:

                transaction.RollBack()

            except:

                pass


            failed.append(
                "{} | {} : {}".format(
                    sheet.SheetNumber,
                    view.Name,
                    error
                )
            )


    # ========================================================
    # RESULT
    # ========================================================

    message = (
        "VIEWPORT POSITION COMPLETE\n\n"
        "Position: {}\n"
        "X: {:.4f}\n"
        "Y: {:.4f}\n\n"
        "Selected: {}\n"
        "Updated: {}\n"
        "Failed: {}"
    ).format(
        position_name,
        x,
        y,
        len(target_data),
        len(successful),
        len(failed)
    )


    if failed:

        message += (
            "\n\nFAILED:\n"
            +
            "\n".join(
                failed
            )
        )


    forms.alert(
        message,
        title="Viewport Position Manager"
    )


# ============================================================
# APPLY SAVED POSITION
# ============================================================

def apply_saved_position():

    positions = (
        load_positions()
    )


    if not positions:

        forms.alert(
            (
                "No positions are saved for Revit {}.\n\n"
                "Use 'Save New Position' first."
            ).format(
                REVIT_VERSION
            ),
            title="Viewport Position Manager"
        )

        return


    # --------------------------------------------------------
    # GO STRAIGHT TO SAVED LIST
    #
    # DO NOT ask for a new viewport here.
    # --------------------------------------------------------

    index = (
        choose_saved_position(
            positions,
            "Select Saved Position - Revit {}".format(
                REVIT_VERSION
            )
        )
    )


    if index is None:

        return


    position = (
        positions[index]
    )


    x = float(
        position["x"]
    )


    y = float(
        position["y"]
    )


    name = position[
        "name"
    ]


    apply_position_to_targets(
        x,
        y,
        name
    )


# ============================================================
# CAPTURE NEW POSITION AND APPLY IMMEDIATELY
#
# Does NOT save unless user wants to.
# ============================================================

def capture_and_apply():

    captured = (
        capture_reference_position()
    )


    if captured is None:

        return


    # --------------------------------------------------------
    # ASK WHETHER TO SAVE
    # --------------------------------------------------------

    should_save = forms.alert(
        (
            "REFERENCE POSITION ACQUIRED\n\n"
            "View: {}\n"
            "Sheet: {}\n\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Do you also want to save this position "
            "for future use?"
        ).format(
            captured["view_name"],
            captured["sheet_number"],
            captured["x"],
            captured["y"]
        ),
        title="Save Position?",
        yes=True,
        no=True
    )


    position_name = (
        "Temporary Position"
    )


    # --------------------------------------------------------
    # SAVE IF YES
    # --------------------------------------------------------

    if should_save:

        positions = (
            load_positions()
        )


        if len(positions) >= MAX_POSITIONS:

            forms.alert(
                (
                    "The position will still be applied, "
                    "but it cannot be saved because Revit {} "
                    "already has {} saved positions."
                ).format(
                    REVIT_VERSION,
                    MAX_POSITIONS
                ),
                title="Position Memory Full"
            )


        else:

            name = forms.ask_for_string(
                prompt="Enter a name for this position:",
                title="Position Name"
            )


            if name:

                name = name.strip()


                if name:

                    if name_exists(
                            positions,
                            name
                    ):

                        forms.alert(
                            (
                                "A position named '{}' already exists.\n\n"
                                "The acquired position will still be applied "
                                "but will not be saved."
                            ).format(
                                name
                            ),
                            title="Duplicate Position Name"
                        )


                    else:

                        position_name = name


                        positions.append(
                            {
                                "name":
                                    name,

                                "x":
                                    captured["x"],

                                "y":
                                    captured["y"],

                                "revit_version":
                                    REVIT_VERSION,

                                "source_view_name":
                                    captured["view_name"],

                                "source_sheet_number":
                                    captured["sheet_number"],

                                "source_sheet_name":
                                    captured["sheet_name"]
                            }
                        )


                        save_positions(
                            positions
                        )


    # --------------------------------------------------------
    # APPLY
    # --------------------------------------------------------

    if position_name == "Temporary Position":

        position_name = (
            "From {} / {}".format(
                captured["sheet_number"],
                captured["view_name"]
            )
        )


    apply_position_to_targets(
        captured["x"],
        captured["y"],
        position_name,
        exclude_viewport_id=captured[
            "viewport_id"
        ]
    )


# ============================================================
# RENAME SAVED POSITION
# ============================================================

def rename_saved_position():

    positions = (
        load_positions()
    )


    index = (
        choose_saved_position(
            positions,
            "Select Position to Rename"
        )
    )


    if index is None:

        return


    old_name = (
        positions[index][
            "name"
        ]
    )


    new_name = forms.ask_for_string(
        default=old_name,
        prompt="Enter the new position name:",
        title="Rename Position"
    )


    if not new_name:

        return


    new_name = (
        new_name.strip()
    )


    if not new_name:

        return


    if name_exists(
            positions,
            new_name,
            ignore_index=index
    ):

        forms.alert(
            "A position named '{}' already exists."
            .format(
                new_name
            ),
            title="Duplicate Name"
        )

        return


    positions[
        index
    ]["name"] = new_name


    save_positions(
        positions
    )


    forms.alert(
        "'{}' renamed to '{}'."
        .format(
            old_name,
            new_name
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# OVERWRITE SAVED POSITION
# ============================================================

def overwrite_saved_position():

    positions = (
        load_positions()
    )


    index = (
        choose_saved_position(
            positions,
            "Select Position to Overwrite"
        )
    )


    if index is None:

        return


    old_position = (
        positions[index]
    )


    # --------------------------------------------------------
    # NOW SELECT NEW REFERENCE
    # --------------------------------------------------------

    captured = (
        capture_reference_position()
    )


    if captured is None:

        return


    confirm = forms.alert(
        (
            "OVERWRITE POSITION\n\n"
            "{}\n\n"
            "Old:\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "New:\n"
            "X: {:.4f}\n"
            "Y: {:.4f}\n\n"
            "Continue?"
        ).format(
            old_position["name"],
            float(
                old_position["x"]
            ),
            float(
                old_position["y"]
            ),
            captured["x"],
            captured["y"]
        ),
        title="Overwrite Position",
        yes=True,
        no=True
    )


    if not confirm:

        return


    old_position[
        "x"
    ] = captured["x"]


    old_position[
        "y"
    ] = captured["y"]


    old_position[
        "source_view_name"
    ] = captured["view_name"]


    old_position[
        "source_sheet_number"
    ] = captured["sheet_number"]


    old_position[
        "source_sheet_name"
    ] = captured["sheet_name"]


    old_position[
        "revit_version"
    ] = REVIT_VERSION


    save_positions(
        positions
    )


    forms.alert(
        (
            "'{}' has been overwritten successfully."
        ).format(
            old_position["name"]
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# DELETE SAVED POSITION
# ============================================================

def delete_saved_position():

    positions = (
        load_positions()
    )


    index = (
        choose_saved_position(
            positions,
            "Select Position to Delete"
        )
    )


    if index is None:

        return


    name = (
        positions[index][
            "name"
        ]
    )


    confirm = forms.alert(
        "Delete saved position '{}'?"
        .format(
            name
        ),
        title="Delete Position",
        yes=True,
        no=True
    )


    if not confirm:

        return


    del positions[
        index
    ]


    save_positions(
        positions
    )


    forms.alert(
        (
            "'{}' deleted.\n\n"
            "Saved Positions: {} / {}"
        ).format(
            name,
            len(positions),
            MAX_POSITIONS
        ),
        title="Viewport Position Manager"
    )


# ============================================================
# SHOW SAVED POSITIONS
# ============================================================

def show_saved_positions():

    positions = (
        load_positions()
    )


    if not positions:

        forms.alert(
            (
                "No saved positions exist for Revit {}."
            ).format(
                REVIT_VERSION
            ),
            title="Saved Positions"
        )

        return


    message = (
        "REVIT {}\n\n"
        "SAVED VIEWPORT POSITIONS\n"
        "--------------------------------\n\n"
    ).format(
        REVIT_VERSION
    )


    for index, position in enumerate(
            positions
    ):

        message += (
            "{}. {}\n"
            "   X: {:.4f}\n"
            "   Y: {:.4f}\n"
            "   Source Sheet: {}\n"
            "   Source View: {}\n\n"
        ).format(
            index + 1,
            position.get(
                "name",
                ""
            ),
            float(
                position.get(
                    "x",
                    0.0
                )
            ),
            float(
                position.get(
                    "y",
                    0.0
                )
            ),
            position.get(
                "source_sheet_number",
                "Unknown"
            ),
            position.get(
                "source_view_name",
                "Unknown"
            )
        )


    forms.alert(
        message,
        title="Saved Positions - Revit {}".format(
            REVIT_VERSION
        )
    )


# ============================================================
# MAIN MENU
# ============================================================

def main():

    positions = (
        load_positions()
    )


    menu_items = [
        "Apply Saved Position",
        "Save New Position",
        "Capture New Position + Apply",
        "Show Saved Positions",
        "Rename Saved Position",
        "Overwrite Saved Position",
        "Delete Saved Position"
    ]


    action = (
        forms.CommandSwitchWindow.show(
            menu_items,
            title=(
                "Viewport Position Manager - Revit {}"
                .format(
                    REVIT_VERSION
                )
            ),
            message=(
                "Saved Positions: {} / {}\n\n"
                "Apply = use an existing saved position.\n"
                "Save New = acquire a position from a viewport.\n"
                "Capture + Apply = use a new viewport position immediately."
                .format(
                    len(positions),
                    MAX_POSITIONS
                )
            )
        )
    )


    if not action:

        return


    # ========================================================
    # APPLY SAVED
    # ========================================================

    if action == "Apply Saved Position":

        apply_saved_position()


    # ========================================================
    # SAVE NEW
    # ========================================================

    elif action == "Save New Position":

        save_new_position()


    # ========================================================
    # CAPTURE AND APPLY
    # ========================================================

    elif action == "Capture New Position + Apply":

        capture_and_apply()


    # ========================================================
    # SHOW
    # ========================================================

    elif action == "Show Saved Positions":

        show_saved_positions()


    # ========================================================
    # RENAME
    # ========================================================

    elif action == "Rename Saved Position":

        rename_saved_position()


    # ========================================================
    # OVERWRITE
    # ========================================================

    elif action == "Overwrite Saved Position":

        overwrite_saved_position()


    # ========================================================
    # DELETE
    # ========================================================

    elif action == "Delete Saved Position":

        delete_saved_position()


# ============================================================
# RUN
# ============================================================

try:

    main()


except Exception as error:

    forms.alert(
        (
            "An error occurred.\n\n"
            "Revit Version: {}\n\n"
            "{}"
        ).format(
            REVIT_VERSION,
            error
        ),
        title="Viewport Position Manager - Error"
    )