# -*- coding: utf-8 -*-
"""NdevTools Renumber, adapted from pyRevit ReNumber (GPL-3.0).

Upstream: pyrevitlabs/pyRevit, commit 0ec3c5fa8b5088b435552c454dab4bad59d684cc.
See THIRD_PARTY_NOTICES.txt and LICENSE-pyRevit.txt.
"""

# pylint: disable=import-error,invalid-name,broad-except
import os

__persistentengine__ = True

from numbering import NumberSequence, parse_exclusions, is_excluded, next_room_number

from pyrevit.coreutils import applocales
from pyrevit import revit, DB, UI
from pyrevit import coreutils
from pyrevit import forms
from pyrevit import script
from System.Windows import Visibility

doc = revit.doc
uidoc = revit.uidoc
logger = script.get_logger()


# shortcut for DB.BuiltInCategory
BIC = DB.BuiltInCategory

ALLOWED_VIEW_CLASSES = (
    DB.View3D,
    DB.ViewPlan,
    DB.ViewSection,
    DB.ViewSheet,
)
DUPE_MODE_SWEEP = "Sweep (renumber displaced)"  # default behaviour
DUPE_MODE_ALERT = "Alert (warn and skip)"
DUPE_MODE_SKIP = "Skip (already numbered)"


class RNOpts(object):
    """Renumber tool option"""

    def __init__(self, cat, by_bicat=None):
        self.bicat = cat
        self._cat = revit.query.get_category(self.bicat)
        self.by_bicat = by_bicat
        self._by_cat = revit.query.get_category(self.by_bicat)

    @property
    def name(self):
        """Renumber option name derived from option categories."""
        if self.by_bicat:
            applocale = applocales.get_host_applocale()
            if "english" in applocale.lang_name.lower():
                return "{} by {}".format(self._cat.Name, self._by_cat.Name)
            return "{} <- {}".format(self._cat.Name, self._by_cat.Name)
        return self._cat.Name


def get_open_views():
    """
    Collect open views in the current document.
    Returns:
        list: A list of open views in the current document.
    """
    ui_views = uidoc.GetOpenUIViews()
    views = []
    for ui_View in ui_views:
        viewId = ui_View.ViewId
        view = doc.GetElement(viewId)
        if isinstance(view, ALLOWED_VIEW_CLASSES):
            views.append(view)
    return views


def toggle_element_selection_handles(target_views, bicat, state=True):
    """Toggle handles for spatial elements"""

    with revit.Transaction("Toggle handles"):
        rr_cat = revit.query.get_subcategory(bicat, "Reference")
        rr_int = revit.query.get_subcategory(bicat, "Interior Fill")
        # if view has template, toggle temp VG overrides
        if state and bicat != BIC.OST_Viewports:
            for target_view in target_views:
                if target_view.CanEnableTemporaryViewPropertiesMode():
                    target_view.EnableTemporaryViewPropertiesMode(target_view.Id)
                try:
                    rr_cat.Visible[target_view] = state
                except Exception as vex:
                    logger.debug(
                        'Failed changing category visibility for "%s" '
                        'to "%s" on view "%s" | %s',
                        bicat,
                        state,
                        target_view.Name,
                        str(vex),
                    )

                try:
                    rr_int.Visible[target_view] = state
                except Exception as vex:
                    logger.debug(
                        'Failed changing interior fill visibility for "%s" '
                        'to "%s" on view "%s" | %s',
                        bicat,
                        state,
                        target_view.Name,
                        str(vex),
                    )
            # disable the temp VG overrides after making changes to categories
        if not state:
            for target_view in target_views:
                target_view.DisableTemporaryViewMode(
                    DB.TemporaryViewMode.TemporaryViewProperties
                )
                try:
                    rr_int.Visible[target_view] = state
                except Exception as vex:
                    logger.debug(
                        'Failed changing interior fill visibility for "%s" '
                        'to "%s" on view "%s" | %s',
                        bicat,
                        state,
                        target_view.Name,
                        str(vex),
                    )


class EasilySelectableElements(object):
    """Expose spatial references, restoring their original visibility afterward.

    Never enable or disable Temporary View Properties or modify view templates.
    """

    def __init__(self, target_views, bicat):
        self.supported_categories = [BIC.OST_Rooms, BIC.OST_Areas, BIC.OST_MEPSpaces]
        self.target_views = target_views
        self.bicat = bicat
        self.original_visibility = []

    def __enter__(self):
        if self.bicat in self.supported_categories:
            with revit.Transaction("Show spatial selection references"):
                for view in self.target_views:
                    for name in ("Reference", "Interior Fill"):
                        category = revit.query.get_subcategory(self.bicat, name)
                        if category is None:
                            continue
                        try:
                            previous = category.Visible[view]
                            if not previous:
                                category.Visible[view] = True
                                self.original_visibility.append((category, view, previous))
                        except Exception as error:
                            logger.debug("Spatial references are controlled by this view: %s", error)
        return self

    def __exit__(self, exception, exception_value, traceback):
        if self.original_visibility:
            with revit.Transaction("Restore spatial selection references"):
                for category, view, previous in self.original_visibility:
                    category.Visible[view] = previous


def increment(number):
    """Increment given item number by one."""
    return coreutils.increment_str(number, expand=True)


def get_number(target_element):
    """Get target element number (might be from Number or other fields)"""
    if hasattr(target_element, "Number"):
        return target_element.Number

    # determine target parameter
    mark_param = target_element.Parameter[DB.BuiltInParameter.ALL_MODEL_MARK]
    if isinstance(target_element, (DB.Level, DB.Grid)):
        mark_param = target_element.Parameter[DB.BuiltInParameter.DATUM_TEXT]
    if isinstance(target_element, DB.Viewport):
        mark_param = target_element.Parameter[
            DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER
        ]
    # get now
    if mark_param:
        return mark_param.AsString()


def set_number(target_element, new_number):
    """Set target element number (might be at Number or other fields)"""
    if hasattr(target_element, "Number"):
        target_element.Number = new_number
        return

    # determine target parameter
    mark_param = target_element.Parameter[DB.BuiltInParameter.ALL_MODEL_MARK]
    if isinstance(target_element, (DB.Level, DB.Grid)):
        mark_param = target_element.Parameter[DB.BuiltInParameter.DATUM_TEXT]
    if isinstance(target_element, DB.Viewport):
        mark_param = target_element.Parameter[
            DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER
        ]
    # set now
    if mark_param:
        mark_param.Set(new_number)


def mark_element_as_renumbered(target_views, element):
    """Override element VG to transparent and halftone in each target view.

    Intended to mark processed renumbered elements visually.
    """
    ogs = DB.OverrideGraphicSettings()
    ogs.SetHalftone(True)
    ogs.SetSurfaceTransparency(100)
    for target_view in target_views:
        target_view.SetElementOverrides(element.Id, ogs)


def unmark_renamed_elements(target_views, marked_element_ids):
    """Reset element VG to previous state or default."""
    for elid, view_dict in marked_element_ids.items():
        for target_view in target_views:
            if target_view.Id in view_dict:
                ogs = view_dict[target_view.Id]
            else:
                ogs = DB.OverrideGraphicSettings()
            target_view.SetElementOverrides(elid, ogs)


def get_elements_dict(views, builtin_cat):
    """Collect number:id information about target elements."""
    # Note: on treating viewports differently
    # tool would fail to assign a new number to viewport
    # on current sheet, if a viewport with the same
    # number exists on any other sheet
    for view in views:
        if BIC.OST_Viewports == builtin_cat and isinstance(view, DB.ViewSheet):
            return {
                get_number(revit.doc.GetElement(vpid)): vpid
                for vpid in view.GetAllViewports()
            }

    all_elements = revit.query.get_elements_by_categories([builtin_cat])

    return {get_number(x): x.Id for x in all_elements}


def get_options(active_view):
    """Keep pyRevit's category order and active-view restrictions exactly."""
    if not isinstance(active_view, ALLOWED_VIEW_CLASSES):
        return []
    if isinstance(active_view, DB.ViewSheet):
        return [RNOpts(BIC.OST_Viewports)]
    categories = [
        BIC.OST_Rooms,
        BIC.OST_MEPSpaces,
        BIC.OST_Doors,
        BIC.OST_Walls,
        BIC.OST_Windows,
        BIC.OST_Parking,
        BIC.OST_Levels,
        BIC.OST_Grids,
    ]
    if active_view.ViewType == DB.ViewType.AreaPlan:
        categories.insert(1, BIC.OST_Areas)
    return [RNOpts(category) for category in categories]


def find_replacement_number(number, elements, next_number):
    """Find a free value using the active step, direction and exclusions."""
    candidate = next_number(number)
    while candidate in elements:
        candidate = next_number(candidate)
    return candidate


def renumber_element(
    target_views, element, number, elements, dupe_mode, next_number, feedback
):
    """Retain source duplicate semantics, reporting alerts in the same window."""
    if number in elements:
        conflict = revit.doc.GetElement(elements[number])
        if conflict and conflict.Id != element.Id:
            if dupe_mode == DUPE_MODE_ALERT:
                feedback("Number {} already exists. Element unchanged.".format(number))
                return False
            if dupe_mode == DUPE_MODE_SKIP and get_number(element):
                feedback("Element already numbered. Element unchanged.")
                return False
            replacement = find_replacement_number(
                get_number(conflict), elements, next_number
            )
            set_number(conflict, replacement)
            elements[replacement] = conflict.Id
    old_number = get_number(element)
    if old_number in elements:
        elements.pop(old_number)
    set_number(element, number)
    elements[number] = element.Id
    mark_element_as_renumbered(target_views, element)
    return True


def _remember(views, element, marked):
    if element.Id not in marked:
        marked[element.Id] = {
            view.Id: view.GetElementOverrides(element.Id) for view in views
        }


def _unmark(views, marked):
    if marked:
        with revit.Transaction("Restore renumber highlights"):
            unmark_renamed_elements(views, marked)


def pick_and_renumber(options, window):
    """Use the shared sequence for every original sequential category."""
    views = (
        [revit.active_view] if options.bicat == BIC.OST_Viewports else get_open_views()
    )
    marked = {}
    with revit.TransactionGroup("NdevTools Renumber {}".format(options.name)):
        with EasilySelectableElements(views, options.bicat):
            elements = get_elements_dict(views, options.bicat)
            try:
                for element in revit.get_picked_elements_by_category(
                    options.bicat,
                    message="Select {} in order. Esc to finish.".format(
                        options.name.lower()
                    ),
                ):
                    if window.stop_requested:
                        break
                    with revit.Transaction("Renumber {}".format(options.name)):
                        _remember(views, element, marked)
                        changed = renumber_element(
                            views,
                            element,
                            window.sequence.number,
                            elements,
                            window.dupe_mode,
                            window.sequence.next_from,
                            window.feedback,
                        )
                    if changed:
                        window.changed_count += 1
                        window.feedback(
                            "Assigned {}. Select another element or press Esc.".format(
                                window.sequence.number
                            )
                        )
                    if not changed:
                        window.skipped_count += 1
                    window.advance()
            finally:
                _unmark(views, marked)


def door_by_room_renumber(options, window):
    """Keep door numbers tied to rooms; skipped or excluded doors remain unchanged."""
    views = get_open_views()
    marked = {}

    def room_replacement(number):
        return next_room_number(number, window.exclusions, increment)

    with revit.TransactionGroup("NdevTools Renumber Doors by Room"):
        with EasilySelectableElements(views, options.bicat):
            with EasilySelectableElements(views, options.by_bicat):
                elements = get_elements_dict(views, options.bicat)
                try:
                    while not window.stop_requested:
                        door = revit.pick_element_by_category(
                            options.bicat, message="Select a door. Esc to finish."
                        )
                        if not door or window.stop_requested:
                            break
                        if window.consume_door_skip():
                            continue
                        from_room, to_room = revit.query.get_door_rooms(door)
                        if all([from_room, to_room]) or not any([from_room, to_room]):
                            room = revit.pick_element_by_category(
                                options.by_bicat,
                                message="Select the room for this door. Esc to finish.",
                            )
                            if not room or window.stop_requested:
                                break
                        else:
                            room = from_room or to_room
                        if window.consume_door_skip():
                            continue
                        room_number = get_number(room)
                        if is_excluded(room_number, window.exclusions):
                            window.skipped_count += 1
                            window.feedback(
                                "Room {} is excluded. Door unchanged.".format(
                                    room_number
                                )
                            )
                            continue
                        room_doors = revit.query.get_doors(room_id=room.Id)
                        if len(room_doors) == 1:
                            number = room_number
                        elif len(room_doors) > 1:
                            used_numbers = [get_number(item) for item in room_doors]
                            number = coreutils.extend_counter(room_number)
                            while number in used_numbers:
                                number = increment(number)
                        else:
                            window.feedback(
                                "No doors associated with that room. Door unchanged."
                            )
                            continue
                        with revit.Transaction("Renumber Door by Room"):
                            _remember(views, door, marked)
                            changed = renumber_element(
                                views,
                                door,
                                number,
                                elements,
                                window.dupe_mode,
                                room_replacement,
                                window.feedback,
                            )
                        if not changed:
                            window.skipped_count += 1
                        if changed:
                            window.changed_count += 1
                            window.feedback(
                                "Assigned {} from room {}. Select another door or press Esc.".format(
                                    number, room_number
                                )
                            )
                finally:
                    _unmark(views, marked)


class RenumberHandler(UI.IExternalEventHandler):
    """Run the original picking routines in Revit's API context."""

    def __init__(self, window):
        self.window = window

    def GetName(self):
        return "NdevTools Renumber"

    def Execute(self, application):
        window = self.window
        if window.closed or window.request is None:
            return
        error = None
        try:
            if application.ActiveUIDocument is None or not window.start_document.Equals(application.ActiveUIDocument.Document):
                raise ValueError("Return to the document where Renumber was opened.")
            window.begin_run()
            if window.request.by_bicat:
                door_by_room_renumber(window.request, window)
            else:
                pick_and_renumber(window.request, window)
        except Exception as exception:
            logger.exception("Renumber failed")
            error = str(exception)
        finally:
            window.request = None
            window.finish_run(error)


class RenumberWindow(forms.WPFWindow):
    """One modeless settings window, leaving Revit available for selection."""

    def __init__(self):
        self.running = False
        self.closed = False
        self.request = None
        self.sequence = None
        self.skip_next_door = False
        self.stop_requested = False
        self.changed_count = 0
        self.skipped_count = 0
        self.start_document = revit.doc
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "Renumber.xaml")
        )
        self.handler = RenumberHandler(self)
        self.external_event = UI.ExternalEvent.Create(self.handler)
        options = get_options(revit.active_view)
        self.category_options = dict((option.name, option) for option in options)
        self.category_cb.ItemsSource = [option.name for option in options]
        self.direction_cb.ItemsSource = ["Increase", "Decrease"]
        self.direction_cb.SelectedIndex = 0
        self.duplicate_cb.ItemsSource = [
            DUPE_MODE_SWEEP,
            DUPE_MODE_ALERT,
            DUPE_MODE_SKIP,
        ]
        self.duplicate_cb.SelectedIndex = 0
        if self.category_cb.Items.Count:
            self.category_cb.SelectedIndex = 0
        else:
            self.run_button.IsEnabled = False
            self.feedback(
                "Open a plan, section, 3D view or sheet supported by the original tool."
            )
        self._refresh_mode()
        self._load_brand()
        self._place_properties_panel()

    def _load_brand(self):
        """Use the same local NdevTools logo as FramePilot."""
        from System import Uri
        from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
        image = BitmapImage()
        image.BeginInit()
        image.CacheOption = BitmapCacheOption.OnLoad
        image.UriSource = Uri(os.path.join(os.path.dirname(__file__), "assets", "ndevtools-logo.png"))
        image.EndInit()
        image.Freeze()
        self.brand_image.Source = image

    def _place_properties_panel(self):
        """Start as a compact floating panel, matching FramePilot's placement."""
        from System.Windows import SystemParameters
        area = SystemParameters.WorkArea
        self.Height = min(self.Height, max(self.MinHeight, area.Height - 24))
        self.Left = max(area.Left, area.Right - self.Width - 12)
        self.Top = area.Top + max(12, (area.Height - self.Height) / 2)

    def drag_title(self, sender, args):
        """Move the floating panel from its branded header."""
        if args.ClickCount == 1:
            self.DragMove()

    def minimize_clicked(self, sender, args):
        """Minimize without losing settings."""
        from System.Windows import WindowState
        self.WindowState = WindowState.Minimized

    def help_clicked(self, sender, args):
        """Show instructions and creator links inside the same window."""
        self.help_panel.Visibility = (
            Visibility.Visible if self.help_panel.Visibility == Visibility.Collapsed
            else Visibility.Collapsed
        )

    def _open_link(self, url):
        """Open a requested profile without changing the numbering session."""
        import webbrowser
        try:
            if not webbrowser.open(url):
                from System.Diagnostics import Process
                Process.Start(url)
        except Exception as error:
            self.feedback("Could not open link: {}".format(error))

    def github_clicked(self, sender, args):
        """Open the NdevTools repository; starring remains the user's action."""
        self._open_link("https://github.com/ndev16/NdevTools")

    def linkedin_clicked(self, sender, args):
        """Open the creator's existing LinkedIn profile."""
        self._open_link("https://www.linkedin.com/in/nataraj016/")

    def _selected_option(self):
        """Resolve a displayed string without WPF binding to an IronPython object."""
        selected = self.category_cb.SelectedItem
        if hasattr(selected, "bicat"):
            return selected
        return self.category_options.get(selected)

    def _room_mode(self):
        option = self._selected_option()
        return bool(
            option and option.bicat == BIC.OST_Doors and self.room_checkbox.IsChecked
        )

    def category_changed(self, sender, args):
        if not hasattr(self, "room_checkbox"):
            return
        option = self._selected_option()
        show_room = bool(option and option.bicat == BIC.OST_Doors)
        self.room_checkbox.Visibility = (
            Visibility.Visible if show_room else Visibility.Collapsed
        )
        if not show_room:
            self.room_checkbox.IsChecked = False
        self._refresh_mode()

    def mode_changed(self, sender, args):
        if hasattr(self, "sequence_settings"):
            self._refresh_mode()

    def _refresh_mode(self):
        room_mode = self._room_mode()
        self.sequence_settings.IsEnabled = not room_mode
        self.mode_hint.Text = (
            "Doors keep their room number, with the original suffix rules. Excluded room numbers leave doors unchanged."
            if room_mode
            else "Skip advances one configured step without changing an element. Numeric ranges include both endpoints."
        )
        if not self.running:
            self.next_value.Text = "From selected room" if room_mode else u"\u2014"
        self.skip_button.ToolTip = (
            "Leave the next selected door unchanged."
            if room_mode
            else "Advance one step without modifying any element."
        )

    def feedback(self, message):
        """Display validation, duplicate warnings and selection feedback inline."""
        self.status_text.Text = message

    def start_clicked(self, sender, args):
        if self.running or self.request is not None:
            return
        try:
            if revit.doc != self.start_document:
                raise ValueError("Return to the document where this window was opened.")
            option = self._selected_option()
            if option is None:
                raise ValueError("Choose a category.")
            valid = [item.bicat for item in get_options(revit.active_view)]
            if option.bicat not in valid:
                raise ValueError(
                    "This category is not available in the current view. Return to the original view."
                )
            exclusions = parse_exclusions(self.exclusions_tb.Text)
            room_mode = self._room_mode()
            sequence = (
                None
                if room_mode
                else NumberSequence(
                    self.start_tb.Text,
                    self.step_tb.Text,
                    str(self.direction_cb.SelectedItem).lower(),
                    exclusions,
                    increment,
                )
            )
            self.exclusions = exclusions
            self.sequence = sequence
            self.dupe_mode = str(self.duplicate_cb.SelectedItem)
            self.request = RNOpts(BIC.OST_Doors, BIC.OST_Rooms) if room_mode else option
            result = self.external_event.Raise()
            if result not in (UI.ExternalEventRequest.Accepted, UI.ExternalEventRequest.Pending):
                self.request = None
                raise ValueError("Revit is busy. Finish its current command and try again.")
        except ValueError as error:
            self.feedback(str(error))

    def begin_run(self):
        """Keep this window modeless while the original Revit picker runs."""
        self.running = True
        self.stop_requested = False
        self.skip_next_door = False
        self.changed_count = 0
        self.skipped_count = 0
        self.setup_panel.IsEnabled = False
        self.run_button.IsEnabled = False
        self.skip_button.IsEnabled = True
        self.close_button.Content = "Finish (Esc)"
        self.next_value.Text = (
            self.sequence.number if self.sequence else "From selected room"
        )
        self.feedback("Select elements in Revit. Press Esc in Revit to finish.")
        self.ShowActivated = False
        self.Show()

    def advance(self):
        """Update only the sequence and label; no model API is called."""
        self.sequence.advance()
        self.next_value.Text = self.sequence.number

    def skip_clicked(self, sender, args):
        if not self.running:
            return
        if self.sequence is not None:
            self.advance()
            self.skipped_count += 1
            self.feedback(
                "Number skipped. Next: {}. No element changed.".format(
                    self.sequence.number
                )
            )
        else:
            self.skip_next_door = True
            self.feedback(
                "The next selected door will be left unchanged. Its room number will not be advanced."
            )

    def consume_door_skip(self):
        """Consume a room-mode Skip only after its affected door is known."""
        if not self.skip_next_door:
            return False
        self.skip_next_door = False
        self.skipped_count += 1
        self.feedback("Door skipped and left unchanged. Select another door.")
        return True

    def finish_run(self, error=None):
        """Return the same window to setup, without opening another prompt."""
        self.running = False
        self.setup_panel.IsEnabled = True
        self.run_button.IsEnabled = True
        self.skip_button.IsEnabled = False
        self.close_button.Content = "Close"
        self.ShowActivated = True
        if error:
            self.feedback(
                "Run rolled back: {}. Correct the issue and try again.".format(error)
            )
        else:
            self.feedback(
                "Finished. {} assigned; {} skipped. Settings are ready for another run.".format(
                    self.changed_count, self.skipped_count
                )
            )
            if self.sequence is not None:
                self.start_tb.Text = self.sequence.number

    def close_clicked(self, sender, args):
        if self.running:
            self.stop_requested = True
            self.feedback(
                "Press Esc in Revit to finish. No further picked element will be changed."
            )
        else:
            self.Close()

    def closing(self, sender, args):
        if self.running:
            args.Cancel = True
            self.close_clicked(sender, args)
        else:
            self.closed = True


def main():
    """Show one modeless window; Revit executes picking through ExternalEvent."""
    global window
    window = RenumberWindow()
    window.Show()


if __name__ == "__main__":
    main()
