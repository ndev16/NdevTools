# -*- coding: utf-8 -*-

from pyrevit import revit, DB, forms

import clr
import re
import uuid


# ============================================================
# .NET REFERENCES
# ============================================================

clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")


from System.Windows.Forms import (
    Form,
    TabControl,
    TabPage,
    TextBox,
    Button,
    Label,
    ComboBox,
    ComboBoxStyle,
    ScrollBars,
    MessageBox,
    MessageBoxButtons,
    MessageBoxIcon,
    FormStartPosition,
    DockStyle,
    AnchorStyles,
    TableLayoutPanel,
    FlowLayoutPanel,
    RowStyle,
    ColumnStyle,
    SizeType,
    Padding,
    AutoScaleMode,
    FlowDirection
)

from System.Drawing import (
    Size,
    Font
)


# ============================================================
# REVIT DOCUMENT
# ============================================================

doc = revit.doc


# ============================================================
# SHEET MANAGER
#
# FEATURES:
#
# CREATE SHEETS
# ------------------------------------------------------------
#
# Enter:
#
# S1.1 - FOUNDATION SLAB PLAN
# S1.2 - LEVEL 1 FRAMING PLAN
# S1.3 - ROOF FRAMING PLAN
#
# Then click CREATE SHEETS.
#
# All sheets are created at once.
#
#
# RENAME SHEETS
# ------------------------------------------------------------
#
# Select multiple existing sheets.
#
# They load like:
#
# S1.1 - FOUNDATION SLAB PLAN
# S1.2 - LEVEL 1 FRAMING PLAN
#
# Edit the lines.
#
# Click APPLY RENAME.
#
#
# Python 2.7 / IronPython compatible.
# Revit 2022 - 2027.
# ============================================================


# ============================================================
# ELEMENT ID VALUE
# ============================================================

def id_value(element_id):

    try:

        return element_id.IntegerValue

    except:

        return element_id.Value


# ============================================================
# PARSE SHEET LINE
#
# Preferred:
#
# S1.1 - FOUNDATION PLAN
#
# Sheet Number:
# S1.1
#
# Sheet Name:
# FOUNDATION PLAN
#
#
# Also supports:
#
# S-101 - FOUNDATION PLAN
#
# because it looks first for a dash with spaces around it.
# ============================================================

def parse_sheet_line(line):

    if line is None:

        return None


    line = line.strip()


    if not line:

        return None


    # --------------------------------------------------------
    # FIRST TRY:
    #
    # Number [space]-[space] Name
    #
    # Example:
    #
    # S-101 - FOUNDATION PLAN
    # --------------------------------------------------------

    match = re.match(
        r"^\s*(.*?)\s+-\s+(.*?)\s*$",
        line
    )


    if match:

        sheet_number = (
            match.group(1).strip()
        )

        sheet_name = (
            match.group(2).strip()
        )


    else:

        # ----------------------------------------------------
        # FALLBACK
        #
        # Example:
        #
        # S1.1-FOUNDATION PLAN
        # ----------------------------------------------------

        if "-" not in line:

            return None


        parts = line.split(
            "-",
            1
        )


        sheet_number = (
            parts[0].strip()
        )

        sheet_name = (
            parts[1].strip()
        )


    if not sheet_number:

        return None


    if not sheet_name:

        return None


    return (
        sheet_number,
        sheet_name
    )


# ============================================================
# GET ALL SHEETS
# ============================================================

def get_all_sheets():

    sheets = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.ViewSheet)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    return list(
        sheets
    )


# ============================================================
# GET TITLE BLOCK TYPES
# ============================================================

def get_titleblock_types():

    titleblocks = list(
        DB.FilteredElementCollector(doc)
        .OfCategory(
            DB.BuiltInCategory.OST_TitleBlocks
        )
        .WhereElementIsElementType()
        .ToElements()
    )


    result = []


    for titleblock in titleblocks:

        # ----------------------------------------------------
        # FAMILY NAME
        # ----------------------------------------------------

        try:

            family_name = (
                titleblock.Family.Name
            )

        except:

            family_name = (
                "Title Block"
            )


        # ----------------------------------------------------
        # TYPE NAME
        # ----------------------------------------------------

        try:

            type_name = (
                titleblock.Name
            )

        except:

            try:

                parameter = (
                    titleblock.get_Parameter(
                        DB.BuiltInParameter.SYMBOL_NAME_PARAM
                    )
                )


                type_name = (
                    parameter.AsString()
                )

            except:

                type_name = (
                    str(
                        id_value(
                            titleblock.Id
                        )
                    )
                )


        display_name = (
            "{} : {}"
            .format(
                family_name,
                type_name
            )
        )


        result.append(
            (
                display_name,
                titleblock
            )
        )


    result.sort(
        key=lambda item:
            item[0].lower()
    )


    return result


# ============================================================
# SHEET DISPLAY NAME
# ============================================================

def sheet_display_name(sheet):

    return (
        "{} - {}"
        .format(
            sheet.SheetNumber,
            sheet.Name
        )
    )


# ============================================================
# MESSAGE BOX
# ============================================================

def show_message(
        text,
        title="Sheet Manager",
        icon=MessageBoxIcon.Information
):

    MessageBox.Show(
        text,
        title,
        MessageBoxButtons.OK,
        icon
    )


# ============================================================
# MAIN SHEET MANAGER WINDOW
# ============================================================

class SheetManagerForm(Form):


    # ========================================================
    # INITIALIZE
    # ========================================================

    def __init__(self):

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.Text = (
            "Sheet Manager"
        )


        self.Size = Size(
            900,
            700
        )


        self.MinimumSize = Size(
            800,
            600
        )


        self.StartPosition = (
            FormStartPosition.CenterScreen
        )


        # ----------------------------------------------------
        # DPI SCALING
        #
        # Fixes overlapping controls at
        # 125%, 150%, etc.
        # ----------------------------------------------------

        self.AutoScaleMode = (
            AutoScaleMode.Dpi
        )


        self.Font = Font(
            "Segoe UI",
            9
        )


        self.Padding = Padding(
            8
        )


        # ----------------------------------------------------
        # DATA
        # ----------------------------------------------------

        self.titleblock_items = (
            get_titleblock_types()
        )


        self.rename_sheets = []


        # ----------------------------------------------------
        # TAB CONTROL
        # ----------------------------------------------------

        self.tabs = (
            TabControl()
        )


        self.tabs.Dock = (
            DockStyle.Fill
        )


        # ----------------------------------------------------
        # CREATE TAB
        # ----------------------------------------------------

        self.create_tab = (
            TabPage(
                "Create Sheets"
            )
        )


        # ----------------------------------------------------
        # RENAME TAB
        # ----------------------------------------------------

        self.rename_tab = (
            TabPage(
                "Rename Sheets"
            )
        )


        self.tabs.TabPages.Add(
            self.create_tab
        )


        self.tabs.TabPages.Add(
            self.rename_tab
        )


        self.Controls.Add(
            self.tabs
        )


        # ----------------------------------------------------
        # BUILD UI
        # ----------------------------------------------------

        self.build_create_tab()

        self.build_rename_tab()


    # ========================================================
    # CREATE SHEETS TAB
    # ========================================================

    def build_create_tab(self):

        # ====================================================
        # MAIN TABLE LAYOUT
        # ====================================================

        layout = (
            TableLayoutPanel()
        )


        layout.Dock = (
            DockStyle.Fill
        )


        layout.Padding = Padding(
            15
        )


        layout.ColumnCount = 1

        layout.RowCount = 4


        # ----------------------------------------------------
        # TITLE BLOCK ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # INSTRUCTION ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # TEXT BOX ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.Percent,
                100
            )
        )


        # ----------------------------------------------------
        # BUTTON ROW
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        self.create_tab.Controls.Add(
            layout
        )


        # ====================================================
        # TITLE BLOCK PANEL
        # ====================================================

        titleblock_panel = (
            TableLayoutPanel()
        )


        titleblock_panel.Dock = (
            DockStyle.Top
        )


        titleblock_panel.AutoSize = True

        titleblock_panel.ColumnCount = 2

        titleblock_panel.RowCount = 1


        titleblock_panel.ColumnStyles.Add(
            ColumnStyle(
                SizeType.AutoSize
            )
        )


        titleblock_panel.ColumnStyles.Add(
            ColumnStyle(
                SizeType.Percent,
                100
            )
        )


        # ----------------------------------------------------
        # TITLE BLOCK LABEL
        # ----------------------------------------------------

        titleblock_label = (
            Label()
        )


        titleblock_label.Text = (
            "Title Block Type:"
        )


        titleblock_label.AutoSize = True


        titleblock_label.Anchor = (
            AnchorStyles.Left
        )


        titleblock_label.Margin = Padding(
            0,
            7,
            10,
            7
        )


        # ----------------------------------------------------
        # TITLE BLOCK COMBOBOX
        # ----------------------------------------------------

        self.titleblock_combo = (
            ComboBox()
        )


        self.titleblock_combo.Dock = (
            DockStyle.Fill
        )


        self.titleblock_combo.DropDownStyle = (
            ComboBoxStyle.DropDownList
        )


        self.titleblock_combo.Margin = Padding(
            0,
            3,
            0,
            8
        )


        # ----------------------------------------------------
        # POPULATE TITLE BLOCKS
        # ----------------------------------------------------

        for (
            display_name,
            titleblock
        ) in self.titleblock_items:

            self.titleblock_combo.Items.Add(
                display_name
            )


        if (
            self.titleblock_combo
            .Items
            .Count
            > 0
        ):

            self.titleblock_combo.SelectedIndex = (
                0
            )


        titleblock_panel.Controls.Add(
            titleblock_label,
            0,
            0
        )


        titleblock_panel.Controls.Add(
            self.titleblock_combo,
            1,
            0
        )


        layout.Controls.Add(
            titleblock_panel,
            0,
            0
        )


        # ====================================================
        # CREATE INSTRUCTIONS
        # ====================================================

        create_label = (
            Label()
        )


        create_label.Text = (
            "Enter one sheet per line using:\n"
            "S1.1 - FOUNDATION SLAB PLAN\n\n"
            "Press Enter for the next sheet. "
            "You can paste as many sheets as needed."
        )


        create_label.AutoSize = True


        create_label.Dock = (
            DockStyle.Top
        )


        create_label.Margin = Padding(
            0,
            8,
            0,
            12
        )


        layout.Controls.Add(
            create_label,
            0,
            1
        )


        # ====================================================
        # CREATE TEXTBOX
        # ====================================================

        self.create_textbox = (
            TextBox()
        )


        self.create_textbox.Multiline = (
            True
        )


        self.create_textbox.AcceptsReturn = (
            True
        )


        self.create_textbox.AcceptsTab = (
            False
        )


        self.create_textbox.ScrollBars = (
            ScrollBars.Both
        )


        self.create_textbox.WordWrap = (
            False
        )


        self.create_textbox.Dock = (
            DockStyle.Fill
        )


        self.create_textbox.Margin = Padding(
            0,
            0,
            0,
            12
        )


        layout.Controls.Add(
            self.create_textbox,
            0,
            2
        )


        # ====================================================
        # CREATE BUTTON PANEL
        # ====================================================

        button_panel = (
            FlowLayoutPanel()
        )


        button_panel.Dock = (
            DockStyle.Fill
        )


        button_panel.AutoSize = (
            True
        )


        button_panel.FlowDirection = (
            FlowDirection.RightToLeft
        )


        # ----------------------------------------------------
        # CREATE BUTTON
        # ----------------------------------------------------

        self.create_button = (
            Button()
        )


        self.create_button.Text = (
            "Create Sheets"
        )


        self.create_button.Size = Size(
            160,
            38
        )


        self.create_button.Click += (
            self.create_sheets_click
        )


        button_panel.Controls.Add(
            self.create_button
        )


        layout.Controls.Add(
            button_panel,
            0,
            3
        )


    # ========================================================
    # RENAME SHEETS TAB
    # ========================================================

    def build_rename_tab(self):

        # ====================================================
        # MAIN TABLE LAYOUT
        # ====================================================

        layout = (
            TableLayoutPanel()
        )


        layout.Dock = (
            DockStyle.Fill
        )


        layout.Padding = Padding(
            15
        )


        layout.ColumnCount = 1

        layout.RowCount = 4


        # ----------------------------------------------------
        # INSTRUCTIONS
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # SELECT BUTTON
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        # ----------------------------------------------------
        # TEXTBOX
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.Percent,
                100
            )
        )


        # ----------------------------------------------------
        # APPLY BUTTON
        # ----------------------------------------------------

        layout.RowStyles.Add(
            RowStyle(
                SizeType.AutoSize
            )
        )


        self.rename_tab.Controls.Add(
            layout
        )


        # ====================================================
        # RENAME INSTRUCTIONS
        # ====================================================

        rename_label = (
            Label()
        )


        rename_label.Text = (
            "1. Click Select Sheets to Rename.\n"
            "2. Edit the sheet number and/or sheet name below.\n"
            "3. Keep one sheet per line.\n"
            "4. Click Apply Rename."
        )


        rename_label.AutoSize = True


        rename_label.Dock = (
            DockStyle.Top
        )


        rename_label.Margin = Padding(
            0,
            0,
            0,
            10
        )


        layout.Controls.Add(
            rename_label,
            0,
            0
        )


        # ====================================================
        # SELECT SHEETS PANEL
        # ====================================================

        select_panel = (
            FlowLayoutPanel()
        )


        select_panel.Dock = (
            DockStyle.Top
        )


        select_panel.AutoSize = (
            True
        )


        # ----------------------------------------------------
        # SELECT SHEETS BUTTON
        # ----------------------------------------------------

        self.select_rename_button = (
            Button()
        )


        self.select_rename_button.Text = (
            "Select Sheets to Rename"
        )


        self.select_rename_button.Size = Size(
            190,
            38
        )


        self.select_rename_button.Click += (
            self.select_rename_sheets_click
        )


        select_panel.Controls.Add(
            self.select_rename_button
        )


        layout.Controls.Add(
            select_panel,
            0,
            1
        )


        # ====================================================
        # RENAME TEXTBOX
        # ====================================================

        self.rename_textbox = (
            TextBox()
        )


        self.rename_textbox.Multiline = (
            True
        )


        self.rename_textbox.AcceptsReturn = (
            True
        )


        self.rename_textbox.AcceptsTab = (
            False
        )


        self.rename_textbox.ScrollBars = (
            ScrollBars.Both
        )


        self.rename_textbox.WordWrap = (
            False
        )


        self.rename_textbox.Dock = (
            DockStyle.Fill
        )


        self.rename_textbox.Margin = Padding(
            0,
            10,
            0,
            12
        )


        layout.Controls.Add(
            self.rename_textbox,
            0,
            2
        )


        # ====================================================
        # APPLY RENAME BUTTON PANEL
        # ====================================================

        rename_button_panel = (
            FlowLayoutPanel()
        )


        rename_button_panel.Dock = (
            DockStyle.Fill
        )


        rename_button_panel.AutoSize = (
            True
        )


        rename_button_panel.FlowDirection = (
            FlowDirection.RightToLeft
        )


        # ----------------------------------------------------
        # APPLY RENAME BUTTON
        # ----------------------------------------------------

        self.rename_button = (
            Button()
        )


        self.rename_button.Text = (
            "Apply Rename"
        )


        self.rename_button.Size = Size(
            160,
            38
        )


        self.rename_button.Click += (
            self.rename_sheets_click
        )


        rename_button_panel.Controls.Add(
            self.rename_button
        )


        layout.Controls.Add(
            rename_button_panel,
            0,
            3
        )


    # ========================================================
    # CREATE SHEETS CLICK
    # ========================================================

    def create_sheets_click(
            self,
            sender,
            event
    ):

        # ====================================================
        # CHECK TITLE BLOCK
        # ====================================================

        if (
            self.titleblock_combo
            .SelectedIndex
            < 0
        ):

            show_message(
                "Select a title block type first.",
                icon=MessageBoxIcon.Warning
            )

            return


        titleblock = (
            self.titleblock_items[
                self.titleblock_combo
                .SelectedIndex
            ][1]
        )


        # ====================================================
        # READ ENTERED LINES
        # ====================================================

        raw_lines = (
            self.create_textbox
            .Text
            .replace(
                "\r\n",
                "\n"
            )
            .replace(
                "\r",
                "\n"
            )
            .split(
                "\n"
            )
        )


        parsed_sheets = []

        invalid_lines = []


        for (
            line_number,
            line
        ) in enumerate(
            raw_lines,
            1
        ):

            # ------------------------------------------------
            # IGNORE EMPTY LINES
            # ------------------------------------------------

            if not line.strip():

                continue


            parsed = (
                parse_sheet_line(
                    line
                )
            )


            if parsed is None:

                invalid_lines.append(
                    "Line {}: {}".format(
                        line_number,
                        line
                    )
                )

                continue


            parsed_sheets.append(
                parsed
            )


        # ====================================================
        # NOTHING VALID
        # ====================================================

        if not parsed_sheets:

            show_message(
                (
                    "No valid sheets were entered.\n\n"
                    "Use this format:\n\n"
                    "S1.1 - FOUNDATION SLAB PLAN"
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # GET EXISTING SHEET NUMBERS
        # ====================================================

        existing_sheets = (
            get_all_sheets()
        )


        existing_numbers = (
            set()
        )


        for sheet in existing_sheets:

            existing_numbers.add(
                sheet.SheetNumber
                .strip()
                .lower()
            )


        # ====================================================
        # CHECK INPUT DUPLICATES
        # ====================================================

        seen_numbers = set()

        valid_sheets = []

        skipped = []


        for (
            sheet_number,
            sheet_name
        ) in parsed_sheets:

            normalized = (
                sheet_number
                .strip()
                .lower()
            )


            # ------------------------------------------------
            # ALREADY EXISTS IN REVIT
            # ------------------------------------------------

            if normalized in existing_numbers:

                skipped.append(
                    (
                        "{} - {} : "
                        "Sheet number already exists"
                    ).format(
                        sheet_number,
                        sheet_name
                    )
                )

                continue


            # ------------------------------------------------
            # DUPLICATE INSIDE INPUT
            # ------------------------------------------------

            if normalized in seen_numbers:

                skipped.append(
                    (
                        "{} - {} : "
                        "Duplicate number in input"
                    ).format(
                        sheet_number,
                        sheet_name
                    )
                )

                continue


            seen_numbers.add(
                normalized
            )


            valid_sheets.append(
                (
                    sheet_number,
                    sheet_name
                )
            )


        # ====================================================
        # NOTHING TO CREATE
        # ====================================================

        if not valid_sheets:

            message = (
                "No sheets can be created."
            )


            if skipped:

                message += (
                    "\n\nSkipped:\n"
                    +
                    "\n".join(
                        skipped
                    )
                )


            show_message(
                message,
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # CONFIRM
        # ====================================================

        confirmation = (
            MessageBox.Show(
                (
                    "Create {} new sheet(s)?"
                ).format(
                    len(
                        valid_sheets
                    )
                ),
                "Create Sheets",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question
            )
        )


        if str(
            confirmation
        ) != "Yes":

            return


        # ====================================================
        # CREATE SHEETS
        # ====================================================

        transaction = (
            DB.Transaction(
                doc,
                "Batch Create Sheets"
            )
        )


        created = []

        failed = []


        try:

            transaction.Start()


            for (
                sheet_number,
                sheet_name
            ) in valid_sheets:

                try:

                    # ----------------------------------------
                    # CREATE SHEET
                    # ----------------------------------------

                    sheet = (
                        DB.ViewSheet.Create(
                            doc,
                            titleblock.Id
                        )
                    )


                    # ----------------------------------------
                    # SET NUMBER
                    # ----------------------------------------

                    sheet.SheetNumber = (
                        sheet_number
                    )


                    # ----------------------------------------
                    # SET NAME
                    # ----------------------------------------

                    sheet.Name = (
                        sheet_name
                    )


                    created.append(
                        "{} - {}".format(
                            sheet_number,
                            sheet_name
                        )
                    )


                except Exception as error:

                    failed.append(
                        (
                            "{} - {} : {}"
                        ).format(
                            sheet_number,
                            sheet_name,
                            error
                        )
                    )


            transaction.Commit()


        except Exception as error:

            try:

                transaction.RollBack()

            except:

                pass


            show_message(
                (
                    "Could not create sheets.\n\n{}"
                ).format(
                    error
                ),
                icon=MessageBoxIcon.Error
            )

            return


        # ====================================================
        # RESULT
        # ====================================================

        message = (
            "BATCH SHEET CREATION COMPLETE\n\n"
            "Created: {}\n"
            "Skipped: {}\n"
            "Failed: {}"
        ).format(
            len(
                created
            ),
            len(
                skipped
            ),
            len(
                failed
            )
        )


        # ----------------------------------------------------
        # INVALID FORMAT
        # ----------------------------------------------------

        if invalid_lines:

            message += (
                "\n\nINVALID FORMAT:\n"
                +
                "\n".join(
                    invalid_lines
                )
            )


        # ----------------------------------------------------
        # SKIPPED
        # ----------------------------------------------------

        if skipped:

            message += (
                "\n\nSKIPPED:\n"
                +
                "\n".join(
                    skipped
                )
            )


        # ----------------------------------------------------
        # FAILED
        # ----------------------------------------------------

        if failed:

            message += (
                "\n\nFAILED:\n"
                +
                "\n".join(
                    failed
                )
            )


        show_message(
            message
        )


        # ====================================================
        # CLEAR TEXT BOX IF SUCCESSFUL
        # ====================================================

        if (
            created
            and
            not failed
            and
            not invalid_lines
        ):

            self.create_textbox.Clear()


    # ========================================================
    # SELECT SHEETS TO RENAME
    # ========================================================

    def select_rename_sheets_click(
            self,
            sender,
            event
    ):

        # ====================================================
        # GET SHEETS
        # ====================================================

        sheets = (
            get_all_sheets()
        )


        if not sheets:

            show_message(
                "No sheets were found.",
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # SORT BY SHEET NUMBER
        # ====================================================

        sheets = sorted(
            sheets,
            key=lambda sheet:
                sheet.SheetNumber.lower()
        )


        display_items = []

        lookup = {}


        # ====================================================
        # BUILD SELECTION LIST
        # ====================================================

        for sheet in sheets:

            display_name = (
                sheet_display_name(
                    sheet
                )
            )


            unique_display = (
                "{} | ID {}"
                .format(
                    display_name,
                    id_value(
                        sheet.Id
                    )
                )
            )


            display_items.append(
                unique_display
            )


            lookup[
                unique_display
            ] = sheet


        # ====================================================
        # SHOW MULTISELECT WINDOW
        # ====================================================

        selected_items = (
            forms.SelectFromList.show(
                display_items,
                title="Select Sheets to Rename",
                button_name="Load Sheets",
                multiselect=True
            )
        )


        if not selected_items:

            return


        # ====================================================
        # PRESERVE SORTED DISPLAY ORDER
        # ====================================================

        selected_sheets = []


        for display_item in display_items:

            if display_item in selected_items:

                selected_sheets.append(
                    lookup[
                        display_item
                    ]
                )


        self.rename_sheets = (
            selected_sheets
        )


        # ====================================================
        # LOAD INTO TEXTBOX
        # ====================================================

        lines = []


        for sheet in (
            self.rename_sheets
        ):

            lines.append(
                "{} - {}".format(
                    sheet.SheetNumber,
                    sheet.Name
                )
            )


        self.rename_textbox.Text = (
            "\r\n".join(
                lines
            )
        )


    # ========================================================
    # APPLY RENAME
    # ========================================================

    def rename_sheets_click(
            self,
            sender,
            event
    ):

        # ====================================================
        # CHECK SELECTION
        # ====================================================

        if not self.rename_sheets:

            show_message(
                "Select sheets to rename first.",
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # READ TEXTBOX
        # ====================================================

        raw_lines = (
            self.rename_textbox
            .Text
            .replace(
                "\r\n",
                "\n"
            )
            .replace(
                "\r",
                "\n"
            )
            .split(
                "\n"
            )
        )


        lines = []


        for line in raw_lines:

            if line.strip():

                lines.append(
                    line
                )


        # ====================================================
        # NUMBER OF LINES MUST MATCH
        # ====================================================

        if (
            len(
                lines
            )
            !=
            len(
                self.rename_sheets
            )
        ):

            show_message(
                (
                    "The number of edited lines must match "
                    "the number of selected sheets.\n\n"
                    "Selected Sheets: {}\n"
                    "Edited Lines: {}"
                ).format(
                    len(
                        self.rename_sheets
                    ),
                    len(
                        lines
                    )
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # PARSE NEW VALUES
        # ====================================================

        new_values = []


        for (
            index,
            line
        ) in enumerate(
            lines
        ):

            parsed = (
                parse_sheet_line(
                    line
                )
            )


            if parsed is None:

                show_message(
                    (
                        "Invalid format on line {}:\n\n"
                        "{}\n\n"
                        "Use this format:\n\n"
                        "S1.1 - FOUNDATION SLAB PLAN"
                    ).format(
                        index + 1,
                        line
                    ),
                    icon=MessageBoxIcon.Warning
                )

                return


            new_values.append(
                parsed
            )


        # ====================================================
        # CHECK DUPLICATES INSIDE RENAME BATCH
        # ====================================================

        new_numbers = []


        for (
            sheet_number,
            sheet_name
        ) in new_values:

            new_numbers.append(
                sheet_number
                .strip()
                .lower()
            )


        if (
            len(
                new_numbers
            )
            !=
            len(
                set(
                    new_numbers
                )
            )
        ):

            show_message(
                (
                    "Two or more edited sheets have "
                    "the same Sheet Number.\n\n"
                    "Every Sheet Number must be unique."
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # IDS OF SHEETS BEING RENAMED
        # ====================================================

        selected_ids = set()


        for sheet in (
            self.rename_sheets
        ):

            selected_ids.add(
                id_value(
                    sheet.Id
                )
            )


        # ====================================================
        # GET NUMBERS USED BY SHEETS OUTSIDE THE SELECTION
        # ====================================================

        outside_numbers = set()


        for sheet in (
            get_all_sheets()
        ):

            if (
                id_value(
                    sheet.Id
                )
                in
                selected_ids
            ):

                continue


            outside_numbers.add(
                sheet.SheetNumber
                .strip()
                .lower()
            )


        # ====================================================
        # CHECK EXTERNAL CONFLICTS
        # ====================================================

        conflicts = []


        for (
            sheet_number,
            sheet_name
        ) in new_values:

            if (
                sheet_number
                .strip()
                .lower()
                in
                outside_numbers
            ):

                conflicts.append(
                    sheet_number
                )


        if conflicts:

            show_message(
                (
                    "These Sheet Numbers are already "
                    "used by other sheets:\n\n{}"
                ).format(
                    "\n".join(
                        conflicts
                    )
                ),
                icon=MessageBoxIcon.Warning
            )

            return


        # ====================================================
        # FIND CHANGED SHEETS
        # ====================================================

        changed_count = 0


        for (
            index,
            sheet
        ) in enumerate(
            self.rename_sheets
        ):

            new_number = (
                new_values[
                    index
                ][0]
            )


            new_name = (
                new_values[
                    index
                ][1]
            )


            if (
                sheet.SheetNumber
                !=
                new_number
                or
                sheet.Name
                !=
                new_name
            ):

                changed_count += 1


        # ====================================================
        # NOTHING CHANGED
        # ====================================================

        if changed_count == 0:

            show_message(
                "No sheet changes were detected."
            )

            return


        # ====================================================
        # CONFIRM
        # ====================================================

        confirmation = (
            MessageBox.Show(
                (
                    "Apply changes to {} sheet(s)?"
                ).format(
                    changed_count
                ),
                "Rename Sheets",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question
            )
        )


        if str(
            confirmation
        ) != "Yes":

            return


        # ====================================================
        # TRANSACTION
        #
        # TEMPORARY SHEET NUMBERS ARE USED FIRST.
        #
        # THIS ALLOWS:
        #
        # S1.1 -> S1.2
        # S1.2 -> S1.1
        #
        # WITHOUT DUPLICATE NUMBER ERRORS.
        # ====================================================

        transaction = (
            DB.Transaction(
                doc,
                "Batch Rename Sheets"
            )
        )


        try:

            transaction.Start()


            # =================================================
            # GENERATE UNIQUE TEMP PREFIX
            # =================================================

            temporary_prefix = (
                "__NDEV_TMP_{}"
                .format(
                    str(
                        uuid.uuid4()
                    )
                    .replace(
                        "-",
                        ""
                    )[:8]
                )
            )


            # =================================================
            # TEMPORARILY RENUMBER ALL SELECTED SHEETS
            # =================================================

            for (
                index,
                sheet
            ) in enumerate(
                self.rename_sheets
            ):

                sheet.SheetNumber = (
                    "{}_{}"
                    .format(
                        temporary_prefix,
                        index + 1
                    )
                )


            # =================================================
            # APPLY FINAL NUMBERS AND NAMES
            # =================================================

            for (
                index,
                sheet
            ) in enumerate(
                self.rename_sheets
            ):

                new_number = (
                    new_values[
                        index
                    ][0]
                )


                new_name = (
                    new_values[
                        index
                    ][1]
                )


                # ---------------------------------------------
                # SHEET NUMBER
                # ---------------------------------------------

                sheet.SheetNumber = (
                    new_number
                )


                # ---------------------------------------------
                # SHEET NAME
                # ---------------------------------------------

                sheet.Name = (
                    new_name
                )


            transaction.Commit()


        except Exception as error:

            try:

                transaction.RollBack()

            except:

                pass


            show_message(
                (
                    "Could not rename sheets.\n\n{}"
                ).format(
                    error
                ),
                icon=MessageBoxIcon.Error
            )

            return


        # ====================================================
        # SUCCESS MESSAGE
        # ====================================================

        show_message(
            (
                "{} sheet(s) updated successfully."
            ).format(
                changed_count
            )
        )


        # ====================================================
        # REFRESH TEXTBOX WITH LIVE REVIT VALUES
        # ====================================================

        refreshed_lines = []


        for sheet in (
            self.rename_sheets
        ):

            refreshed_lines.append(
                "{} - {}".format(
                    sheet.SheetNumber,
                    sheet.Name
                )
            )


        self.rename_textbox.Text = (
            "\r\n".join(
                refreshed_lines
            )
        )


# ============================================================
# RUN
# ============================================================

try:

    window = (
        SheetManagerForm()
    )


    window.ShowDialog()


except Exception as error:

    forms.alert(
        (
            "Sheet Manager Error:\n\n{}"
        ).format(
            error
        ),
        title="Sheet Manager"
    )