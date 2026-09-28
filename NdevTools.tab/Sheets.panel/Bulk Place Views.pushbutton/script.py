# -*- coding: utf-8 -*-

# ============================================================
# PLACE VIEWS ON SHEET
#
# Created by Nataraj Devaraj
#
# pyRevit / IronPython 2.7
# Revit 2022 - 2027
#
# WORKFLOW
# ------------------------------------------------------------
# 1. Read saved viewport positions.
# 2. Show ONLY views not already placed on sheets.
# 3. Multi-select views.
# 4. Select target sheet.
# 5. Select viewport type.
# 6. Select a saved position for each selected view.
# 7. Confirm.
# 8. Place all views.
# 9. Apply viewport type.
# 10. Move each viewport to exact saved X/Y position.
# 11. Ask whether user wants to repeat.
#
# YES = Run workflow again.
# NO  = Close tool.
#
# ============================================================


from pyrevit import revit, DB, forms, script

import json


# ============================================================
# DOCUMENT
# ============================================================

doc = revit.doc


# ============================================================
# REVIT VERSION
# ============================================================

REVIT_VERSION = str(
    doc.Application.VersionNumber
)


SUPPORTED_VERSIONS = [
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
    "2027"
]


# ============================================================
# SAVED POSITION CONFIG
# ============================================================

VIEWPORT_POSITION_CONFIG = (
    "NDEV_VIEWPORT_POSITION_MANAGER_{}"
    .format(
        REVIT_VERSION
    )
)


CROP_POSITION_CONFIG = (
    "NDEV_CROP_POSITION_MANAGER_{}"
    .format(
        REVIT_VERSION
    )
)


POSITIONS_KEY = "positions_json"


# ============================================================
# ELEMENT ID VALUE
# ============================================================

def id_value(element_id):

    try:

        return element_id.IntegerValue

    except:

        try:

            return element_id.Value

        except:

            return str(
                element_id
            )


# ============================================================
# GET CONFIG VALUE
# ============================================================

def get_config_value(
        cfg,
        option_name,
        default_value
):

    # --------------------------------------------------------
    # ATTRIBUTE
    # --------------------------------------------------------

    try:

        value = getattr(
            cfg,
            option_name
        )

        if value is not None:

            return value

    except:

        pass


    # --------------------------------------------------------
    # GET OPTION
    # --------------------------------------------------------

    try:

        value = cfg.get_option(
            option_name,
            default_value
        )

        if value is not None:

            return value

    except:

        pass


    return default_value


# ============================================================
# NORMALIZE ONE SAVED POSITION
# ============================================================

def normalize_position(
        position,
        fallback_name
):

    if not isinstance(
        position,
        dict
    ):

        return None


    name = position.get(
        "name",
        fallback_name
    )


    # --------------------------------------------------------
    # FIND X
    # --------------------------------------------------------

    x_value = None


    for key in [
        "x",
        "X",
        "pos_x",
        "sheet_x"
    ]:

        if key in position:

            x_value = (
                position[key]
            )

            break


    # --------------------------------------------------------
    # FIND Y
    # --------------------------------------------------------

    y_value = None


    for key in [
        "y",
        "Y",
        "pos_y",
        "sheet_y"
    ]:

        if key in position:

            y_value = (
                position[key]
            )

            break


    if (
        x_value is None
        or
        y_value is None
    ):

        return None


    try:

        x_value = float(
            x_value
        )

        y_value = float(
            y_value
        )

    except:

        return None


    result = dict(
        position
    )


    result["name"] = str(
        name
    )

    result["x"] = (
        x_value
    )

    result["y"] = (
        y_value
    )


    return result


# ============================================================
# PARSE POSITION DATA
# ============================================================

def parse_position_data(
        raw_data
):

    data = raw_data


    # --------------------------------------------------------
    # JSON STRING
    # --------------------------------------------------------

    if isinstance(
        raw_data,
        basestring
    ):

        try:

            data = json.loads(
                raw_data
            )

        except:

            return []


    result = []


    # --------------------------------------------------------
    # LIST FORMAT
    # --------------------------------------------------------

    if isinstance(
        data,
        list
    ):

        for index, item in enumerate(
            data
        ):

            position = (
                normalize_position(
                    item,
                    "Position {}".format(
                        index + 1
                    )
                )
            )


            if position:

                result.append(
                    position
                )


        return result


    # --------------------------------------------------------
    # DICTIONARY FORMAT
    # --------------------------------------------------------

    if isinstance(
        data,
        dict
    ):

        for key in data:

            value = (
                data[key]
            )


            # ------------------------------------------------
            # DICTIONARY VALUE
            # ------------------------------------------------

            if isinstance(
                value,
                dict
            ):

                temp = dict(
                    value
                )


                if "name" not in temp:

                    temp["name"] = (
                        str(
                            key
                        )
                    )


                position = (
                    normalize_position(
                        temp,
                        str(
                            key
                        )
                    )
                )


                if position:

                    result.append(
                        position
                    )


            # ------------------------------------------------
            # LIST / TUPLE VALUE
            # ------------------------------------------------

            elif isinstance(
                value,
                (list, tuple)
            ):

                if len(
                    value
                ) >= 2:

                    try:

                        result.append(
                            {
                                "name": str(
                                    key
                                ),
                                "x": float(
                                    value[0]
                                ),
                                "y": float(
                                    value[1]
                                )
                            }
                        )

                    except:

                        pass


        return result


    return []


# ============================================================
# LOAD POSITIONS FROM CONFIG
# ============================================================

def load_positions_from_config(
        config_section
):

    try:

        cfg = (
            script.get_config(
                config_section
            )
        )

    except:

        return []


    raw_data = (
        get_config_value(
            cfg,
            POSITIONS_KEY,
            "[]"
        )
    )


    return (
        parse_position_data(
            raw_data
        )
    )


# ============================================================
# LOAD SAVED POSITIONS
# ============================================================

def load_saved_positions():

    # --------------------------------------------------------
    # VIEWPORT POSITION MANAGER
    # --------------------------------------------------------

    positions = (
        load_positions_from_config(
            VIEWPORT_POSITION_CONFIG
        )
    )


    if positions:

        return positions


    # --------------------------------------------------------
    # CROP POSITION MANAGER FALLBACK
    # --------------------------------------------------------

    positions = (
        load_positions_from_config(
            CROP_POSITION_CONFIG
        )
    )


    return positions


# ============================================================
# GET VIEW TYPE NAME
# ============================================================

def get_view_type_name(
        view
):

    try:

        return (
            view.ViewType.ToString()
        )

    except:

        try:

            return str(
                view.ViewType
            )

        except:

            return "View"


# ============================================================
# CHECK SUPPORTED VIEW
# ============================================================

def is_supported_view(
        view
):

    if view is None:

        return False


    # --------------------------------------------------------
    # TEMPLATE
    # --------------------------------------------------------

    try:

        if view.IsTemplate:

            return False

    except:

        pass


    view_type_name = (
        get_view_type_name(
            view
        )
    )


    excluded_types = [

        "DrawingSheet",

        "Schedule",

        "ColumnSchedule",

        "PanelSchedule",

        "ProjectBrowser",

        "SystemBrowser",

        "Report",

        "CostReport",

        "LoadsReport",

        "Internal",

        "Undefined"

    ]


    if (
        view_type_name
        in
        excluded_types
    ):

        return False


    return True


# ============================================================
# GET VIEWS ALREADY PLACED
# ============================================================

def get_placed_view_ids():

    result = (
        set()
    )


    viewports = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    for viewport in viewports:

        try:

            result.add(
                id_value(
                    viewport.ViewId
                )
            )

        except:

            pass


    return result


# ============================================================
# GET UNPLACED VIEWS
# ============================================================

def get_unplaced_views():

    placed_ids = (
        get_placed_view_ids()
    )


    views = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.View)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    result = []


    for view in views:

        if not is_supported_view(
            view
        ):

            continue


        try:

            view_id = (
                id_value(
                    view.Id
                )
            )

        except:

            continue


        if view_id in placed_ids:

            continue


        result.append(
            view
        )


    return result


# ============================================================
# VIEW DISPLAY NAME
# ============================================================

def view_display_name(
        view
):

    view_type = (
        get_view_type_name(
            view
        )
    )


    scale_text = ""


    try:

        if view.Scale > 0:

            scale_text = (
                " | Scale 1:{}"
                .format(
                    view.Scale
                )
            )

    except:

        pass


    return (
        "{} | {}{} | ID {}"
        .format(
            view.Name,
            view_type,
            scale_text,
            id_value(
                view.Id
            )
        )
    )


# ============================================================
# SELECT UNPLACED VIEWS
# ============================================================

def select_unplaced_views():

    views = (
        get_unplaced_views()
    )


    if not views:

        forms.alert(
            (
                "No unplaced views were found.\n\n"
                "All compatible views appear to "
                "already be placed on sheets."
            ),
            title="Place Views on Sheet"
        )

        return []


    try:

        views = sorted(
            views,
            key=lambda x:
                x.Name.lower()
        )

    except:

        pass


    items = []

    lookup = {}


    for view in views:

        display = (
            view_display_name(
                view
            )
        )


        items.append(
            display
        )


        lookup[
            display
        ] = view


    selected = (
        forms.SelectFromList.show(
            items,
            title="Select Unplaced Views",
            button_name="Select Views",
            multiselect=True
        )
    )


    if not selected:

        return []


    return [
        lookup[item]
        for item in selected
    ]


# ============================================================
# GET SHEETS
# ============================================================

def get_sheets():

    sheets = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewSheet)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    result = []


    for sheet in sheets:

        try:

            if sheet.IsPlaceholder:

                continue

        except:

            pass


        result.append(
            sheet
        )


    return result


# ============================================================
# SELECT TARGET SHEET
# ============================================================

def select_target_sheet():

    sheets = (
        get_sheets()
    )


    if not sheets:

        forms.alert(
            "No sheets were found.",
            title="Place Views on Sheet"
        )

        return None


    try:

        sheets = sorted(
            sheets,
            key=lambda x:
                x.SheetNumber.lower()
        )

    except:

        pass


    items = []

    lookup = {}


    for sheet in sheets:

        display = (
            "{} | {} | ID {}"
            .format(
                sheet.SheetNumber,
                sheet.Name,
                id_value(
                    sheet.Id
                )
            )
        )


        items.append(
            display
        )


        lookup[
            display
        ] = sheet


    selected = (
        forms.SelectFromList.show(
            items,
            title="Select Target Sheet",
            button_name="Select Sheet",
            multiselect=False
        )
    )


    if not selected:

        return None


    return (
        lookup[
            selected
        ]
    )


# ============================================================
# GET ELEMENT TYPE NAME
# ============================================================

def get_element_type_name(
        element_type
):

    # --------------------------------------------------------
    # NAME PROPERTY
    # --------------------------------------------------------

    try:

        value = (
            element_type.Name
        )


        if value:

            return value

    except:

        pass


    # --------------------------------------------------------
    # SYMBOL NAME
    # --------------------------------------------------------

    try:

        parameter = (
            element_type.get_Parameter(
                DB.BuiltInParameter.SYMBOL_NAME_PARAM
            )
        )


        if parameter:

            value = (
                parameter.AsString()
            )


            if value:

                return value

    except:

        pass


    # --------------------------------------------------------
    # TYPE NAME
    # --------------------------------------------------------

    try:

        parameter = (
            element_type.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_TYPE_NAME
            )
        )


        if parameter:

            value = (
                parameter.AsString()
            )


            if value:

                return value

    except:

        pass


    return (
        "Viewport Type {}".format(
            id_value(
                element_type.Id
            )
        )
    )


# ============================================================
# GET VIEWPORT FAMILY NAME
# ============================================================

def get_viewport_family_name(
        element_type
):

    try:

        family_name = (
            element_type.FamilyName
        )


        if family_name:

            return family_name

    except:

        pass


    try:

        parameter = (
            element_type.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_FAMILY_NAME
            )
        )


        if parameter:

            value = (
                parameter.AsString()
            )


            if value:

                return value

    except:

        pass


    return "Viewport"


# ============================================================
# ADD VIEWPORT TYPE
# ============================================================

def add_viewport_type(
        result,
        seen_ids,
        element_type
):

    if element_type is None:

        return


    try:

        type_id = (
            id_value(
                element_type.Id
            )
        )

    except:

        return


    if type_id in seen_ids:

        return


    seen_ids.add(
        type_id
    )


    result.append(
        element_type
    )


# ============================================================
# GET VIEWPORT TYPES
# ============================================================

def get_viewport_types():

    result = []

    seen_ids = (
        set()
    )


    # ========================================================
    # EXISTING VIEWPORTS
    # ========================================================

    viewports = list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    # ========================================================
    # METHOD 1
    # GETVALIDTYPES
    # ========================================================

    for viewport in viewports:

        try:

            valid_type_ids = (
                viewport.GetValidTypes()
            )


            for type_id in valid_type_ids:

                element_type = (
                    doc.GetElement(
                        type_id
                    )
                )


                add_viewport_type(
                    result,
                    seen_ids,
                    element_type
                )

        except:

            pass


    # ========================================================
    # METHOD 2
    # CURRENT VIEWPORT TYPES
    # ========================================================

    for viewport in viewports:

        try:

            element_type = (
                doc.GetElement(
                    viewport.GetTypeId()
                )
            )


            add_viewport_type(
                result,
                seen_ids,
                element_type
            )

        except:

            pass


    # ========================================================
    # METHOD 3
    # SEARCH ALL ELEMENT TYPES
    # ========================================================

    try:

        viewport_category = (
            DB.Category.GetCategory(
                doc,
                DB.BuiltInCategory.OST_Viewports
            )
        )


        if viewport_category:

            viewport_category_id = (
                id_value(
                    viewport_category.Id
                )
            )


            element_types = (
                DB.FilteredElementCollector(doc)
                .WhereElementIsElementType()
                .ToElements()
            )


            for element_type in element_types:

                try:

                    category = (
                        element_type.Category
                    )


                    if category is None:

                        continue


                    if (
                        id_value(
                            category.Id
                        )
                        !=
                        viewport_category_id
                    ):

                        continue


                    add_viewport_type(
                        result,
                        seen_ids,
                        element_type
                    )


                except:

                    pass


    except:

        pass


    # ========================================================
    # SORT
    # ========================================================

    try:

        result = sorted(
            result,
            key=lambda x:
                get_element_type_name(
                    x
                ).lower()
        )

    except:

        pass


    return result


# ============================================================
# SELECT VIEWPORT TYPE
# ============================================================

def select_viewport_type():

    viewport_types = (
        get_viewport_types()
    )


    if not viewport_types:

        forms.alert(
            (
                "No viewport types could be found.\n\n"
                "Make sure the project contains at least "
                "one normal viewport on a sheet."
            ),
            title="Place Views on Sheet"
        )

        return None


    items = []

    lookup = {}


    for viewport_type in viewport_types:

        family_name = (
            get_viewport_family_name(
                viewport_type
            )
        )


        type_name = (
            get_element_type_name(
                viewport_type
            )
        )


        display = (
            "{} : {} | ID {}"
            .format(
                family_name,
                type_name,
                id_value(
                    viewport_type.Id
                )
            )
        )


        if display in lookup:

            display = (
                "{} | {}"
                .format(
                    display,
                    id_value(
                        viewport_type.Id
                    )
                )
            )


        items.append(
            display
        )


        lookup[
            display
        ] = viewport_type


    items.sort()


    selected = (
        forms.SelectFromList.show(
            items,
            title="Select Viewport Type",
            button_name="Use Viewport Type",
            multiselect=False
        )
    )


    if not selected:

        return None


    return (
        lookup[
            selected
        ]
    )


# ============================================================
# CAN PLACE VIEW
# ============================================================

def can_place_view(
        sheet,
        view
):

    try:

        return (
            DB.Viewport.CanAddViewToSheet(
                doc,
                sheet.Id,
                view.Id
            )
        )

    except:

        return False


# ============================================================
# FILTER PLACEABLE VIEWS
# ============================================================

def filter_placeable_views(
        views,
        sheet
):

    valid = []

    invalid = []


    for view in views:

        if can_place_view(
            sheet,
            view
        ):

            valid.append(
                view
            )

        else:

            invalid.append(
                view
            )


    if invalid:

        message = (
            "These views cannot be placed "
            "on the selected sheet:\n\n"
        )


        for view in invalid:

            message += (
                "- {}\n"
                .format(
                    view.Name
                )
            )


        if valid:

            message += (
                "\n{} other view(s) can still be placed."
                .format(
                    len(
                        valid
                    )
                )
            )


        forms.alert(
            message,
            title="Place Views on Sheet"
        )


    return valid


# ============================================================
# POSITION DISPLAY NAME
# ============================================================

def position_display_name(
        position,
        index
):

    name = (
        position.get(
            "name",
            "Position {}".format(
                index + 1
            )
        )
    )


    return (
        "{} | X: {:.4f} | Y: {:.4f}"
        .format(
            name,
            position["x"],
            position["y"]
        )
    )


# ============================================================
# CHOOSE POSITION
# ============================================================

def choose_position(
        available_positions,
        view
):

    items = []

    lookup = {}


    for index, position in enumerate(
        available_positions
    ):

        display = (
            position_display_name(
                position,
                index
            )
        )


        unique_display = (
            "{} | #{}"
            .format(
                display,
                index + 1
            )
        )


        items.append(
            unique_display
        )


        lookup[
            unique_display
        ] = position


    selected = (
        forms.SelectFromList.show(
            items,
            title=(
                "Select Saved Position\n\n"
                "View: {}"
            ).format(
                view.Name
            ),
            button_name="Use Position",
            multiselect=False
        )
    )


    if not selected:

        return None


    return (
        lookup[
            selected
        ]
    )


# ============================================================
# ASSIGN POSITIONS
# ============================================================

def assign_positions(
        views,
        saved_positions
):

    if (
        len(
            views
        )
        >
        len(
            saved_positions
        )
    ):

        forms.alert(
            (
                "You selected {} views, but only {} "
                "saved positions are available.\n\n"
                "Each selected view needs its own "
                "saved position.\n\n"
                "Save more positions or select fewer views."
            ).format(
                len(
                    views
                ),
                len(
                    saved_positions
                )
            ),
            title="Place Views on Sheet"
        )

        return []


    available_positions = (
        list(
            saved_positions
        )
    )


    assignments = []


    for view in views:

        position = (
            choose_position(
                available_positions,
                view
            )
        )


        if position is None:

            return []


        assignments.append(
            (
                view,
                position
            )
        )


        try:

            available_positions.remove(
                position
            )

        except:

            pass


    return assignments


# ============================================================
# PLACE ONE VIEW
# ============================================================

def place_one_view(
        sheet,
        view,
        viewport_type,
        position
):

    x_value = float(
        position["x"]
    )


    y_value = float(
        position["y"]
    )


    insertion_point = (
        DB.XYZ(
            x_value,
            y_value,
            0.0
        )
    )


    # --------------------------------------------------------
    # CREATE VIEWPORT
    # --------------------------------------------------------

    viewport = (
        DB.Viewport.Create(
            doc,
            sheet.Id,
            view.Id,
            insertion_point
        )
    )


    if viewport is None:

        raise Exception(
            "Viewport.Create returned None."
        )


    # --------------------------------------------------------
    # APPLY VIEWPORT TYPE
    # --------------------------------------------------------

    try:

        if (
            viewport.GetTypeId()
            !=
            viewport_type.Id
        ):

            viewport.ChangeTypeId(
                viewport_type.Id
            )

    except Exception as error:

        raise Exception(
            (
                "Viewport created, but selected "
                "viewport type could not be applied: {}"
            ).format(
                error
            )
        )


    # --------------------------------------------------------
    # EXACT SAVED POSITION
    # --------------------------------------------------------

    current_center = (
        viewport.GetBoxCenter()
    )


    exact_center = (
        DB.XYZ(
            x_value,
            y_value,
            current_center.Z
        )
    )


    viewport.SetBoxCenter(
        exact_center
    )


    return viewport


# ============================================================
# BUILD CONFIRMATION
# ============================================================

def build_confirmation(
        sheet,
        viewport_type,
        assignments
):

    message = (
        "PLACE VIEWS ON SHEET\n\n"
        "TARGET SHEET:\n"
        "{} - {}\n\n"
        "VIEWPORT TYPE:\n"
        "{}\n\n"
        "VIEW / POSITION:\n"
    ).format(
        sheet.SheetNumber,
        sheet.Name,
        get_element_type_name(
            viewport_type
        )
    )


    for view, position in assignments:

        message += (
            "\n{}  ->  {}"
            .format(
                view.Name,
                position.get(
                    "name",
                    "Saved Position"
                )
            )
        )


    message += (
        "\n\nPlace {} view(s)?"
        .format(
            len(
                assignments
            )
        )
    )


    return message


# ============================================================
# PROCESS ALL VIEWS
# ============================================================

def process_views(
        sheet,
        viewport_type,
        assignments
):

    successful = []

    failed = []


    for view, position in assignments:

        transaction = (
            DB.Transaction(
                doc,
                "Place View - {}".format(
                    view.Name
                )
            )
        )


        try:

            transaction.Start()


            place_one_view(
                sheet,
                view,
                viewport_type,
                position
            )


            transaction.Commit()


            successful.append(
                (
                    view.Name,
                    position.get(
                        "name",
                        "Saved Position"
                    )
                )
            )


        except Exception as error:

            try:

                transaction.RollBack()

            except:

                pass


            failed.append(
                (
                    view.Name,
                    str(
                        error
                    )
                )
            )


    return (
        successful,
        failed
    )


# ============================================================
# SHOW RESULTS
# ============================================================

def show_results(
        sheet,
        successful,
        failed
):

    message = (
        "PLACE VIEWS COMPLETE\n\n"
        "SHEET:\n"
        "{} - {}\n\n"
        "PLACED: {}\n"
        "FAILED / SKIPPED: {}"
    ).format(
        sheet.SheetNumber,
        sheet.Name,
        len(
            successful
        ),
        len(
            failed
        )
    )


    if successful:

        message += (
            "\n\nPLACED:\n"
        )


        for view_name, position_name in successful:

            message += (
                "\n{} -> {}"
                .format(
                    view_name,
                    position_name
                )
            )


    if failed:

        message += (
            "\n\nFAILED / SKIPPED:\n"
        )


        for view_name, error in failed:

            message += (
                "\n{}: {}"
                .format(
                    view_name,
                    error
                )
            )


    forms.alert(
        message,
        title="Place Views on Sheet"
    )


# ============================================================
# MAIN WORKFLOW
# ============================================================

def main():

    # ========================================================
    # CHECK REVIT VERSION
    # ========================================================

    if (
        REVIT_VERSION
        not in
        SUPPORTED_VERSIONS
    ):

        forms.alert(
            (
                "This tool supports Revit 2022 - 2027.\n\n"
                "Current Version: {}"
            ).format(
                REVIT_VERSION
            ),
            title="Place Views on Sheet"
        )

        return False


    # ========================================================
    # STEP 0
    # LOAD SAVED POSITIONS
    # ========================================================

    saved_positions = (
        load_saved_positions()
    )


    if not saved_positions:

        forms.alert(
            (
                "No saved viewport positions were found "
                "for Revit {}.\n\n"
                "Please use the Viewport Position Manager "
                "or Crop Position Manager to save at least "
                "one position first.\n\n"
                "Then run this tool again."
            ).format(
                REVIT_VERSION
            ),
            title="No Saved Positions"
        )

        return False


    # ========================================================
    # STEP 1
    # SELECT UNPLACED VIEWS
    # ========================================================

    selected_views = (
        select_unplaced_views()
    )


    if not selected_views:

        return False


    # ========================================================
    # STEP 2
    # SELECT TARGET SHEET
    # ========================================================

    target_sheet = (
        select_target_sheet()
    )


    if target_sheet is None:

        return False


    # ========================================================
    # FILTER PLACEABLE VIEWS
    # ========================================================

    selected_views = (
        filter_placeable_views(
            selected_views,
            target_sheet
        )
    )


    if not selected_views:

        forms.alert(
            (
                "None of the selected views can "
                "be placed on this sheet."
            ),
            title="Place Views on Sheet"
        )

        return False


    # ========================================================
    # STEP 3
    # SELECT VIEWPORT TYPE
    # ========================================================

    viewport_type = (
        select_viewport_type()
    )


    if viewport_type is None:

        return False


    # ========================================================
    # STEP 4
    # ASSIGN SAVED POSITIONS
    # ========================================================

    assignments = (
        assign_positions(
            selected_views,
            saved_positions
        )
    )


    if not assignments:

        return False


    # ========================================================
    # STEP 5
    # CONFIRM
    # ========================================================

    confirmation = (
        forms.alert(
            build_confirmation(
                target_sheet,
                viewport_type,
                assignments
            ),
            title="Place Views on Sheet",
            yes=True,
            no=True
        )
    )


    if not confirmation:

        return False


    # ========================================================
    # STEP 6
    # PLACE VIEWS
    # ========================================================

    successful, failed = (
        process_views(
            target_sheet,
            viewport_type,
            assignments
        )
    )


    # ========================================================
    # STEP 7
    # SHOW RESULTS
    # ========================================================

    show_results(
        target_sheet,
        successful,
        failed
    )


    # ========================================================
    # COMPLETE
    #
    # TRUE TELLS THE OUTER LOOP THAT THE WORKFLOW FINISHED.
    # ========================================================

    return True


# ============================================================
# RUN
# REPEAT WORKFLOW UNTIL USER SAYS NO
# ============================================================

try:

    while True:

        # ----------------------------------------------------
        # RUN COMPLETE WORKFLOW
        # ----------------------------------------------------

        completed = (
            main()
        )


        # ----------------------------------------------------
        # USER CANCELLED / WORKFLOW DID NOT COMPLETE
        # ----------------------------------------------------

        if not completed:

            break


        # ----------------------------------------------------
        # ASK WHETHER TO REPEAT
        # ----------------------------------------------------

        repeat_process = (
            forms.alert(
                (
                    "VIEW PLACEMENT COMPLETE\n\n"
                    "Do you want to place more views "
                    "on another sheet?\n\n"
                    "YES = Repeat the process\n"
                    "NO = Close the tool"
                ),
                title="Place More Views?",
                yes=True,
                no=True
            )
        )


        # ----------------------------------------------------
        # NO
        # CLOSE
        # ----------------------------------------------------

        if not repeat_process:

            break


        # ----------------------------------------------------
        # YES
        #
        # LOOP STARTS AGAIN AUTOMATICALLY.
        #
        # The views placed during the previous run will no
        # longer appear because get_unplaced_views() is run
        # again from Revit.
        # ----------------------------------------------------


except Exception as error:

    forms.alert(
        (
            "Place Views on Sheet Error:\n\n{}"
        ).format(
            error
        ),
        title="Place Views on Sheet"
    )