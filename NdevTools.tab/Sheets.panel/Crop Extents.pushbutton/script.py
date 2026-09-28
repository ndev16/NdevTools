# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms

doc = revit.doc


# ============================================================
# MATCH CROP REGIONS
#
# WORKFLOW:
#
# 1. Select REFERENCE VIEW from list.
# 2. Select MULTIPLE TARGET VIEWS.
# 3. Prompt:
#       Apply same scale?
#
#       YES = Source scale is applied to all target views.
#       NO  = Target view scales remain unchanged.
#
# 4. Apply same model crop region to all selected views.
#
# Python 2.7 / IronPython compatible
# ============================================================


COPY_CROP_VISIBILITY = True
COPY_ANNOTATION_CROP_OFFSETS = True
REMOVE_TARGET_SPLIT_CROPS = True


# ============================================================
# ELEMENT ID VALUE
# ============================================================

def id_value(element_id):
    try:
        return element_id.IntegerValue
    except:
        return element_id.Value


# ============================================================
# CHECK VALID PLAN VIEW
# ============================================================

def is_valid_plan_view(view):

    if view is None:
        return False

    if view.IsTemplate:
        return False

    if not isinstance(view, DB.ViewPlan):
        return False

    try:
        crop_box = view.CropBox

        if crop_box is None:
            return False

    except:
        return False

    return True


# ============================================================
# GET SCOPE BOX NAME
# ============================================================

def get_scope_box_name(view):

    try:

        parameter = view.get_Parameter(
            DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP
        )

        if parameter is None:
            return None

        scope_id = parameter.AsElementId()

        if (
            scope_id is None
            or scope_id == DB.ElementId.InvalidElementId
        ):
            return None

        scope_box = doc.GetElement(scope_id)

        if scope_box is None:
            return None

        return scope_box.Name

    except:
        return None


# ============================================================
# BUILD VIEW -> SHEET MAP
# ============================================================

def build_view_sheet_map():

    result = {}

    viewports = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.Viewport)
        .ToElements()
    )

    for viewport in viewports:

        try:

            view_id = id_value(
                viewport.ViewId
            )

            sheet = doc.GetElement(
                viewport.OwnerViewId
            )

            if not isinstance(
                sheet,
                DB.ViewSheet
            ):
                continue

            result[view_id] = sheet

        except:
            pass

    return result


# ============================================================
# CREATE DISPLAY NAME
# ============================================================

def create_view_display_name(
        view,
        sheet_map
):

    view_id = id_value(
        view.Id
    )

    sheet = sheet_map.get(
        view_id
    )

    if sheet:

        location_text = "{} - {}".format(
            sheet.SheetNumber,
            sheet.Name
        )

    else:

        location_text = "UNPLACED"

    scale_text = "1:{}".format(
        view.Scale
    )

    scope_box_name = get_scope_box_name(
        view
    )

    scope_text = ""

    if scope_box_name:

        scope_text = " | Scope Box: {}".format(
            scope_box_name
        )

    return (
        "{} | {} | {}{} | ID {}"
        .format(
            location_text,
            view.Name,
            scale_text,
            scope_text,
            view_id
        )
    )


# ============================================================
# GET ALL VALID PLAN VIEWS
# ============================================================

def get_all_plan_views():

    views = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewPlan)
        .ToElements()
    )

    valid_views = []

    for view in views:

        if is_valid_plan_view(view):

            valid_views.append(
                view
            )

    return valid_views


# ============================================================
# SELECT REFERENCE VIEW
# ============================================================

def select_reference_view():

    sheet_map = build_view_sheet_map()

    views = get_all_plan_views()

    display_items = []
    lookup = {}

    for view in views:

        display_name = (
            create_view_display_name(
                view,
                sheet_map
            )
        )

        display_items.append(
            display_name
        )

        lookup[
            display_name
        ] = view

    display_items.sort()

    if not display_items:

        forms.alert(
            "No compatible plan views were found.",
            title="Match Crop Regions",
            exitscript=True
        )

    selected = forms.SelectFromList.show(
        display_items,
        title="Select Reference View",
        button_name="Use as Reference",
        multiselect=False
    )

    if not selected:
        return None

    return lookup[selected]


# ============================================================
# SELECT TARGET VIEWS
# ============================================================

def select_target_views(
        reference_view
):

    sheet_map = build_view_sheet_map()

    views = get_all_plan_views()

    display_items = []
    lookup = {}

    for view in views:

        if view.Id == reference_view.Id:
            continue

        display_name = (
            create_view_display_name(
                view,
                sheet_map
            )
        )

        display_items.append(
            display_name
        )

        lookup[
            display_name
        ] = view

    display_items.sort()

    if not display_items:

        forms.alert(
            "No target plan views were found.",
            title="Match Crop Regions",
            exitscript=True
        )

    selected_items = (
        forms.SelectFromList.show(
            display_items,
            title=(
                "Select Target Views\n"
                "Reference: {}"
                .format(
                    reference_view.Name
                )
            ),
            button_name="Select Target Views",
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
# SOURCE VIEW COORDINATE
# TO MODEL COORDINATE
# ============================================================

def source_view_point_to_model(
        source_view,
        point
):

    origin = source_view.Origin

    right = (
        source_view
        .RightDirection
        .Normalize()
    )

    up = (
        source_view
        .UpDirection
        .Normalize()
    )

    direction = (
        source_view
        .ViewDirection
        .Normalize()
    )

    model_point = (
        origin
        + right.Multiply(
            point.X
        )
        + up.Multiply(
            point.Y
        )
        + direction.Multiply(
            point.Z
        )
    )

    return model_point


# ============================================================
# MODEL COORDINATE
# TO TARGET VIEW COORDINATE
# ============================================================

def model_point_to_target_view(
        target_view,
        model_point
):

    origin = target_view.Origin

    right = (
        target_view
        .RightDirection
        .Normalize()
    )

    up = (
        target_view
        .UpDirection
        .Normalize()
    )

    vector = (
        model_point
        - origin
    )

    x_value = (
        vector.DotProduct(
            right
        )
    )

    y_value = (
        vector.DotProduct(
            up
        )
    )

    return DB.XYZ(
        x_value,
        y_value,
        0.0
    )


# ============================================================
# TRANSFORM SOURCE CROP POINT
# INTO TARGET VIEW
# ============================================================

def transform_crop_point(
        source_view,
        target_view,
        source_point
):

    model_point = (
        source_view_point_to_model(
            source_view,
            source_point
        )
    )

    return (
        model_point_to_target_view(
            target_view,
            model_point
        )
    )


# ============================================================
# CREATE TARGET CROP LOOP
# ============================================================

def create_target_crop_loop(
        source_view,
        target_view,
        source_loop
):

    target_loop = DB.CurveLoop()

    short_tolerance = (
        doc.Application.ShortCurveTolerance
    )

    for curve in source_loop:

        # ----------------------------------------------------
        # STRAIGHT LINE
        # ----------------------------------------------------

        if isinstance(
            curve,
            DB.Line
        ):

            source_start = (
                curve.GetEndPoint(0)
            )

            source_end = (
                curve.GetEndPoint(1)
            )

            target_start = (
                transform_crop_point(
                    source_view,
                    target_view,
                    source_start
                )
            )

            target_end = (
                transform_crop_point(
                    source_view,
                    target_view,
                    source_end
                )
            )

            if (
                target_start.DistanceTo(
                    target_end
                )
                <= short_tolerance
            ):

                raise Exception(
                    "Crop boundary contains "
                    "a very short line."
                )

            target_loop.Append(
                DB.Line.CreateBound(
                    target_start,
                    target_end
                )
            )

        # ----------------------------------------------------
        # FALLBACK FOR OTHER CURVES
        # ----------------------------------------------------

        else:

            points = list(
                curve.Tessellate()
            )

            if len(points) < 2:
                continue

            for index in range(
                len(points) - 1
            ):

                target_start = (
                    transform_crop_point(
                        source_view,
                        target_view,
                        points[index]
                    )
                )

                target_end = (
                    transform_crop_point(
                        source_view,
                        target_view,
                        points[index + 1]
                    )
                )

                if (
                    target_start.DistanceTo(
                        target_end
                    )
                    <= short_tolerance
                ):
                    continue

                target_loop.Append(
                    DB.Line.CreateBound(
                        target_start,
                        target_end
                    )
                )

    return target_loop


# ============================================================
# COPY ANNOTATION CROP OFFSETS
# ============================================================

def copy_annotation_offsets(
        source_manager,
        target_manager
):

    if not COPY_ANNOTATION_CROP_OFFSETS:
        return

    try:

        if not source_manager.CanHaveAnnotationCrop:
            return

        if not target_manager.CanHaveAnnotationCrop:
            return

        target_manager.LeftAnnotationCropOffset = (
            source_manager.LeftAnnotationCropOffset
        )

        target_manager.RightAnnotationCropOffset = (
            source_manager.RightAnnotationCropOffset
        )

        target_manager.TopAnnotationCropOffset = (
            source_manager.TopAnnotationCropOffset
        )

        target_manager.BottomAnnotationCropOffset = (
            source_manager.BottomAnnotationCropOffset
        )

    except:
        pass


# ============================================================
# APPLY CROP TO TARGET VIEW
# ============================================================

def apply_crop_to_target(
        source_view,
        source_loop,
        source_manager,
        target_view,
        copy_scale
):

    # --------------------------------------------------------
    # TARGET SCOPE BOX CHECK
    # --------------------------------------------------------

    scope_box_name = (
        get_scope_box_name(
            target_view
        )
    )

    if scope_box_name:

        raise Exception(
            "Crop is controlled by Scope Box '{}'."
            .format(
                scope_box_name
            )
        )

    target_manager = (
        target_view
        .GetCropRegionShapeManager()
    )

    # --------------------------------------------------------
    # COPY SCALE
    # --------------------------------------------------------

    if copy_scale:

        target_view.Scale = (
            source_view.Scale
        )

    # --------------------------------------------------------
    # REMOVE TARGET SPLIT CROP
    # --------------------------------------------------------

    if REMOVE_TARGET_SPLIT_CROPS:

        try:

            if (
                target_manager.NumberOfSplitRegions
                > 1
            ):

                target_manager.RemoveSplit()

        except:
            pass

    # --------------------------------------------------------
    # ACTIVATE TARGET CROP
    # --------------------------------------------------------

    target_view.CropBoxActive = True

    # --------------------------------------------------------
    # CREATE TARGET CROP
    # --------------------------------------------------------

    target_loop = (
        create_target_crop_loop(
            source_view,
            target_view,
            source_loop
        )
    )

    # --------------------------------------------------------
    # VALIDATE CROP
    # --------------------------------------------------------

    try:

        valid_crop = (
            target_manager
            .IsCropRegionShapeValid(
                target_loop
            )
        )

        if not valid_crop:

            raise Exception(
                "Converted crop region "
                "is not valid for this view."
            )

    except AttributeError:
        pass

    # --------------------------------------------------------
    # APPLY CROP
    # --------------------------------------------------------

    target_manager.SetCropShape(
        target_loop
    )

    # --------------------------------------------------------
    # COPY CROP VISIBILITY
    # --------------------------------------------------------

    if COPY_CROP_VISIBILITY:

        try:

            target_view.CropBoxVisible = (
                source_view.CropBoxVisible
            )

        except:
            pass

    # --------------------------------------------------------
    # COPY ANNOTATION CROP
    # --------------------------------------------------------

    copy_annotation_offsets(
        source_manager,
        target_manager
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # ========================================================
    # STEP 1
    # SELECT REFERENCE VIEW
    # ========================================================

    reference_view = (
        select_reference_view()
    )

    if reference_view is None:
        return


    # ========================================================
    # CHECK REFERENCE CROP
    # ========================================================

    try:

        if not reference_view.CropBoxActive:

            forms.alert(
                "The selected reference view "
                "does not have Crop View enabled.\n\n"
                "Turn Crop View ON and run the tool again.",
                title="Match Crop Regions",
                exitscript=True
            )

    except:

        forms.alert(
            "The selected reference view "
            "does not support crop regions.",
            title="Match Crop Regions",
            exitscript=True
        )


    source_manager = (
        reference_view
        .GetCropRegionShapeManager()
    )


    # ========================================================
    # CHECK SOURCE SPLIT CROP
    # ========================================================

    try:

        if (
            source_manager.NumberOfSplitRegions
            > 1
        ):

            forms.alert(
                "The reference view uses "
                "a SPLIT crop region.\n\n"
                "This version supports "
                "one crop region only.",
                title="Match Crop Regions",
                exitscript=True
            )

    except:
        pass


    # ========================================================
    # GET SOURCE CROP
    # ========================================================

    source_loops = list(
        source_manager.GetCropShape()
    )

    if len(source_loops) != 1:

        forms.alert(
            "Could not acquire one crop region "
            "from the reference view.",
            title="Match Crop Regions",
            exitscript=True
        )

    source_loop = (
        source_loops[0]
    )


    # ========================================================
    # STEP 2
    # SELECT TARGET VIEWS
    # ========================================================

    target_views = (
        select_target_views(
            reference_view
        )
    )

    if not target_views:
        return


    # ========================================================
    # STEP 3
    # ASK WHETHER SCALE SHOULD ALSO BE COPIED
    # ========================================================

    copy_scale = forms.alert(
        (
            "REFERENCE VIEW:\n"
            "{}\n\n"
            "Reference Scale: 1:{}\n\n"
            "Do you want to apply the SAME SCALE "
            "to all selected target views?\n\n"
            "YES = Crop + Scale\n"
            "NO = Crop only"
        ).format(
            reference_view.Name,
            reference_view.Scale
        ),
        title="Apply Same Scale?",
        yes=True,
        no=True
    )


    # ========================================================
    # FINAL CONFIRMATION
    # ========================================================

    if copy_scale:

        scale_status = (
            "YES - Apply 1:{} to targets"
            .format(
                reference_view.Scale
            )
        )

    else:

        scale_status = (
            "NO - Keep existing target scales"
        )


    confirmation = forms.alert(
        (
            "REFERENCE VIEW:\n"
            "{}\n\n"
            "TARGET VIEWS:\n"
            "{}\n\n"
            "COPY SCALE:\n"
            "{}\n\n"
            "Apply the reference crop "
            "to all selected target views?"
        ).format(
            reference_view.Name,
            len(target_views),
            scale_status
        ),
        title="Match Crop Regions",
        yes=True,
        no=True
    )

    if not confirmation:
        return


    # ========================================================
    # PROCESS VIEWS
    # ========================================================

    successful = []
    failed = []


    for target_view in target_views:

        transaction = DB.Transaction(
            doc,
            "Match Crop - {}".format(
                target_view.Name
            )
        )

        try:

            transaction.Start()

            apply_crop_to_target(
                reference_view,
                source_loop,
                source_manager,
                target_view,
                copy_scale
            )

            transaction.Commit()

            successful.append(
                target_view.Name
            )

        except Exception as error:

            try:
                transaction.RollBack()
            except:
                pass

            failed.append(
                "{}: {}".format(
                    target_view.Name,
                    error
                )
            )


    # ========================================================
    # RESULT
    # ========================================================

    message = (
        "MATCH CROP COMPLETE\n\n"
        "Reference View:\n"
        "{}\n\n"
        "Reference Scale:\n"
        "1:{}\n\n"
        "Selected Targets: {}\n"
        "Successfully Updated: {}\n"
        "Failed / Skipped: {}\n\n"
        "Scale Applied: {}"
    ).format(
        reference_view.Name,
        reference_view.Scale,
        len(target_views),
        len(successful),
        len(failed),
        "YES" if copy_scale else "NO"
    )


    if failed:

        message += (
            "\n\nFAILED / SKIPPED:\n"
            + "\n".join(
                failed
            )
        )


    forms.alert(
        message,
        title="Match Crop Regions"
    )


# ============================================================
# RUN
# ============================================================

try:

    main()

except Exception as error:

    forms.alert(
        "An error occurred:\n\n{}".format(
            error
        ),
        title="Match Crop Regions"
    )