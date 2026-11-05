"""Host-free tests for the complete NdevTools Renumber command."""

import ast
from contextlib import nullcontext
from decimal import Decimal
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

BUNDLE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ndev_numbering", BUNDLE / "numbering.py")
numbering = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(numbering)
REFERENCE = (
    Path(
        os.environ.get(
            "PYREVIT_ROOT", str(Path(os.environ["APPDATA"]) / "pyRevit-Master")
        )
    )
    / "pyrevitlib/pyrevit/coreutils/__init__.py"
)
COUNTER = {}
tree = ast.parse(REFERENCE.read_text(encoding="utf-8"))
tree.body = [
    node
    for node in tree.body
    if getattr(node, "name", None) in ("increment_str", "_inc_or_dec_string")
]
exec(compile(tree, str(REFERENCE), "exec"), COUNTER)


class Plan:
    ViewType = "FloorPlan"


class Sheet:
    pass


class Section:
    ViewType = "Section"


class View3D:
    ViewType = "ThreeD"


CATEGORIES = (
    "OST_Rooms",
    "OST_MEPSpaces",
    "OST_Doors",
    "OST_Walls",
    "OST_Windows",
    "OST_Parking",
    "OST_Levels",
    "OST_Grids",
    "OST_Areas",
    "OST_Viewports",
)
BIC = NS(**dict((name, name) for name in CATEGORIES))
NAMESPACE = {
    "NumberSequence": numbering.NumberSequence,
    "parse_exclusions": numbering.parse_exclusions,
    "is_excluded": numbering.is_excluded,
    "next_room_number": numbering.next_room_number,
    "coreutils": NS(
        increment_str=COUNTER["increment_str"], extend_counter=lambda value: value + "A"
    ),
    "forms": NS(WPFWindow=object),
    "UI": NS(IExternalEventHandler=object),
    "DB": NS(ViewSheet=Sheet, ViewType=NS(AreaPlan="AreaPlan")),
    "BIC": BIC,
    "ALLOWED_VIEW_CLASSES": (Plan, Sheet, Section, View3D),
    "Visibility": NS(Visible="visible", Collapsed="collapsed"),
    "DUPE_MODE_SWEEP": "sweep",
    "DUPE_MODE_ALERT": "alert",
    "DUPE_MODE_SKIP": "skip",
    "revit": NS(query=NS(get_category=lambda category: NS(Name=category))),
    "applocales": NS(get_host_applocale=lambda: NS(lang_name="english")),
}
tree = ast.parse((BUNDLE / "script.py").read_text(encoding="utf-8"))
tree.body = [
    node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
]
exec(compile(tree, str(BUNDLE / "script.py"), "exec"), NAMESPACE)


def sequence(start="5", step="1", direction="increase", exclusions=""):
    return numbering.NumberSequence(
        start,
        step,
        direction,
        numbering.parse_exclusions(exclusions),
        NAMESPACE["increment"],
    )


def values(start, step, direction, exclusions="", count=3):
    seq = sequence(start, step, direction, exclusions)
    result = [seq.number]
    for _ in range(count - 1):
        result.append(seq.advance())
    return result


class ArithmeticTests(unittest.TestCase):
    def test_integer_and_decimal_steps_in_both_directions(self):
        for args, expected in [
            (("5", "2", "increase"), ["5", "7", "9"]),
            (("5", "2", "decrease"), ["5", "3", "1"]),
            (("5.0", "0.2", "increase"), ["5.0", "5.2", "5.4"]),
            (("5.0", "0.3", "decrease"), ["5.0", "4.7", "4.4"]),
            (("10", "1", "decrease"), ["10", "9", "8"]),
            (("001.00", "0.30", "decrease"), ["001.00", "000.70", "000.40"]),
            (("1", "2", "decrease"), ["1", "-1", "-3"]),
        ]:
            with self.subTest(args=args):
                self.assertEqual(values(*args), expected)

    def test_fractional_steps_never_accumulate_float_artifacts(self):
        seq = sequence("0.0", "0.2")
        for _ in range(500):
            seq.advance()
        self.assertEqual(seq.number, "100.0")
        seq = sequence("0.0", "0.3", "decrease")
        for _ in range(100):
            seq.advance()
        self.assertEqual(seq.number, "-30.0")

    def test_ranges_follow_step_lattice_in_both_directions(self):
        self.assertEqual(values("4", "2", "increase", "5-10"), ["4", "12", "14"])
        self.assertEqual(values("11", "2", "decrease", "5 to 10"), ["11", "3", "1"])
        self.assertEqual(values("4.8", "0.2", "increase", "5-6"), ["4.8", "6.2", "6.4"])
        self.assertEqual(
            values("6.1", "0.3", "decrease", "5 to 6"), ["6.1", "4.9", "4.6"]
        )

    def test_individual_exclusions_do_not_turn_into_decimal_intervals(self):
        self.assertEqual(
            values("5.0", "0.2", "increase", "5, 6"), ["5.2", "5.4", "5.6"]
        )
        self.assertEqual(values("5.0", "0.2", "increase", "5-6"), ["6.2", "6.4", "6.6"])

    def test_mixed_signed_decimal_intervals_and_inclusive_endpoints(self):
        parsed = numbering.parse_exclusions("-5--1, 5, 8-10, 12 to 15, 8.5")
        self.assertEqual(
            parsed,
            [
                (Decimal(-5), Decimal(-1)),
                (Decimal(5), Decimal(5)),
                (Decimal(8), Decimal(10)),
                (Decimal(12), Decimal(15)),
            ],
        )
        self.assertTrue(numbering.is_excluded("005", parsed))
        self.assertTrue(numbering.is_excluded("10.0", parsed))
        self.assertFalse(numbering.is_excluded("5.1", parsed))
        self.assertEqual(sequence("005", "1", "increase", "5-9").number, "010")
        self.assertEqual(sequence("10", "1", "decrease", "5-10").number, "4")

    def test_large_ranges_are_jumped_without_enumeration(self):
        self.assertEqual(
            sequence("0", "0.2", "increase", "0-1000000000").number, "1000000000.2"
        )

    def test_bad_settings_and_malformed_exclusions_are_rejected(self):
        for step in ("0", "-1", "NaN", "Infinity", "abc", "1e2"):
            with self.subTest(step=step), self.assertRaises(ValueError):
                sequence(step=step)
        for text in ("10-5", "C to A"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                numbering.parse_exclusions(text)
        for args in [
            ("A05", "2", "increase"),
            ("A05", "1", "decrease"),
            ("A05", "0.2", "increase"),
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                sequence(*args)
        with self.assertRaises(ValueError):
            sequence("")

    def test_literal_identifiers_and_special_characters_are_accepted(self):
        parsed = numbering.parse_exclusions('A01, Room@1, #, *, A-101, "x,y", "A-C"')
        for identifier in ("A01", "Room@1", "#", "*", "A-101", "x,y", "A-C"):
            self.assertTrue(numbering.is_excluded(identifier, parsed), identifier)
        self.assertFalse(numbering.is_excluded("AnythingElse", parsed))
        self.assertTrue(numbering.is_excluded("word", numbering.parse_exclusions("word")))

    def test_alphabetic_and_alphanumeric_ranges_skip_sequence_values(self):
        self.assertEqual(values("A", "1", "increase", "A to C"), ["D", "E", "F"])
        self.assertEqual(values("A01", "1", "increase", "A01-A03, A05"), ["A04", "A06", "A07"])
        self.assertEqual(values("Y", "1", "increase", "Z to AB"), ["Y", "AC", "AD"])
        self.assertEqual(sequence("A05", exclusions="5").number, "A05")

    def test_quoted_numeric_identifiers_match_exact_format(self):
        self.assertEqual(sequence("005", exclusions='"005"').number, "006")
        self.assertEqual(sequence("5", exclusions='"005"').number, "5")

    def test_room_identifiers_can_be_excluded_literally_or_by_range(self):
        for text in ("A105", "A100-A110"):
            window, write, _ = WorkflowTests()._room_run(room_number="A105", exclusions=text)
            write.assert_not_called()
            self.assertEqual(window.skipped_count, 1)

    def test_default_alphanumeric_and_room_suffix_behavior_is_preserved(self):
        for start in ("A09", "Z", "100A", "A319z"):
            with self.subTest(start=start):
                self.assertEqual(
                    sequence(start).advance(),
                    COUNTER["increment_str"](start, expand=True),
                )
        exclusions = numbering.parse_exclusions("5-10")
        self.assertEqual(
            numbering.next_room_number("004", exclusions, NAMESPACE["increment"]), "011"
        )
        self.assertEqual(
            numbering.next_room_number("105A", exclusions, NAMESPACE["increment"]),
            "105B",
        )


class WorkflowTests(unittest.TestCase):
    def test_window_resources_preserve_the_palette_initialized_by_pyrevit(self):
        root = ET.parse(BUNDLE / "Renumber.xaml").getroot()
        ns = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"
        resources = root.find(ns + "Window.Resources")
        self.assertIsNotNone(resources)
        # WPFWindow seeds these keys before IronPython loads our markup.
        # Redeclaring them throws; replacing the dictionary removes its brushes.
        reserved = {
            "pyRevitWindowForegroundColor", "pyRevitWindowBackgroundColor",
            "pyRevitWindowForegroundBrush", "pyRevitWindowBackgroundBrush",
        }
        authored = {item.attrib.get("{http://schemas.microsoft.com/winfx/2006/xaml}Key") for item in resources}
        self.assertFalse(reserved.intersection(authored))
        self.assertIsNone(resources.find(ns + "ResourceDictionary"))

    def test_displayed_category_names_resolve_to_the_original_category(self):
        window = self._window("OST_Walls")
        option = NAMESPACE["RNOpts"]("OST_Walls")
        window.category_options = {"Walls": option}
        window.category_cb.SelectedItem = "Walls"
        self.assertIs(window._selected_option(), option)
        self.assertFalse(window._room_mode())

    def test_modeless_event_routes_picking_and_restores_window(self):
        document = NS(Equals=lambda other: other is document)
        for room_mode in (False, True):
            window = NS(
                closed=False, request=NS(by_bicat=room_mode), start_document=document,
                begin_run=Mock(), finish_run=Mock(),
            )
            sequential, by_room = Mock(), Mock()
            with patch.dict(NAMESPACE, pick_and_renumber=sequential, door_by_room_renumber=by_room):
                handler = NAMESPACE["RenumberHandler"](window)
                handler.Execute(NS(ActiveUIDocument=NS(Document=document)))
            (by_room if room_mode else sequential).assert_called_once()
            (sequential if room_mode else by_room).assert_not_called()
            window.begin_run.assert_called_once()
            window.finish_run.assert_called_once_with(None)
            self.assertIsNone(window.request)

    def test_view_rules_preserve_all_original_supported_categories(self):
        self.assertEqual(
            [item.bicat for item in NAMESPACE["get_options"](Plan())],
            list(CATEGORIES[:8]),
        )
        area = Plan()
        area.ViewType = "AreaPlan"
        self.assertEqual(
            [item.bicat for item in NAMESPACE["get_options"](area)],
            ["OST_Rooms", "OST_Areas"] + list(CATEGORIES[1:8]),
        )
        self.assertEqual(
            [item.bicat for item in NAMESPACE["get_options"](Sheet())],
            ["OST_Viewports"],
        )
        self.assertEqual(NAMESPACE["get_options"](object()), [])
        for view in (Section(), View3D()):
            self.assertEqual(len(NAMESPACE["get_options"](view)), 8)

    def _window(self, cat="OST_Doors", room=False):
        window = object.__new__(NAMESPACE["RenumberWindow"])
        window.category_cb = NS(SelectedItem=NS(bicat=cat))
        window.room_checkbox = NS(IsChecked=room, Visibility=None)
        window.sequence_settings = NS(IsEnabled=True)
        window.mode_hint = NS(Text="")
        window.next_value = NS(Text="")
        window.skip_button = NS(ToolTip="")
        window.status_text = NS(Text="")
        window.running = False
        return window

    def test_doors_checkbox_is_visible_only_for_doors(self):
        for cat in CATEGORIES:
            window = self._window(cat, True)
            window.category_changed(None, None)
            self.assertEqual(
                window.room_checkbox.Visibility,
                "visible" if cat == "OST_Doors" else "collapsed",
            )
            self.assertEqual(bool(window.room_checkbox.IsChecked), cat == "OST_Doors")
            self.assertEqual(window.sequence_settings.IsEnabled, cat != "OST_Doors")

    def test_skip_uses_configured_step_with_no_document_available(self):
        window = self._window()
        window.running = True
        window.sequence = sequence("5.0", "0.3", "decrease", "4-4.9")
        window.skipped_count = 0
        window.skip_clicked(None, None)
        self.assertEqual(window.sequence.number, "3.8")
        self.assertEqual(window.next_value.Text, "3.8")
        self.assertEqual(window.skipped_count, 1)

    def test_room_skip_does_not_advance_an_independent_counter(self):
        window = self._window(room=True)
        window.running = True
        window.sequence = None
        window.skipped_count = 0
        window.skip_clicked(None, None)
        self.assertTrue(window.consume_door_skip())
        self.assertFalse(window.consume_door_skip())
        self.assertEqual(window.skipped_count, 1)
        self.assertIsNone(window.sequence)

    def test_all_sequential_categories_use_same_step_and_exclusions(self):
        for category in CATEGORIES:
            with self.subTest(category=category):
                window = self._window(category)
                window.stop_requested = False
                window.changed_count = 0
                window.dupe_mode = "sweep"
                window.sequence = sequence("5.0", "0.2", "increase", "5,5.4")
                element = NS(Id=20)
                view = NS(Id=1, GetElementOverrides=lambda _: "old")
                write = Mock(return_value=True)
                with patch.dict(
                    NAMESPACE,
                    revit=NS(
                        active_view=view,
                        Transaction=lambda *a: nullcontext(),
                        TransactionGroup=lambda *a: nullcontext(),
                        get_picked_elements_by_category=lambda *a, **kw: iter(
                            [element]
                        ),
                    ),
                    get_open_views=lambda: [view],
                    get_elements_dict=lambda *a: {},
                    EasilySelectableElements=lambda *a: nullcontext(),
                    renumber_element=write,
                    _unmark=Mock(),
                ):
                    NAMESPACE["pick_and_renumber"](
                        NS(bicat=category, name=category), window
                    )
                self.assertEqual(write.call_args.args[2], "5.2")
                self.assertEqual(window.sequence.number, "5.6")

    def _room_run(
        self,
        room_number="105",
        exclusions="",
        skip=False,
        multiple=False,
        skip_during_room=False,
    ):
        window = self._window(room=True)
        window.stop_requested = False
        window.skip_next_door = skip
        window.skipped_count = 0
        window.changed_count = 0
        window.dupe_mode = "sweep"
        window.exclusions = numbering.parse_exclusions(exclusions)
        door = NS(Id=2, Number="old")
        room = NS(Id=3, Number=room_number)
        write = Mock(return_value=True)
        picks = iter([door, room, None]) if skip_during_room else iter([door, None])

        def pick(*args, **kwargs):
            item = next(picks)
            if skip_during_room and item is room:
                window.skip_next_door = True
            return item

        with patch.dict(
            NAMESPACE,
            revit=NS(
                Transaction=lambda *a: nullcontext(),
                TransactionGroup=lambda *a: nullcontext(),
                pick_element_by_category=pick,
                query=NS(
                    get_door_rooms=lambda _: (
                        (None, None) if skip_during_room else (room, None)
                    ),
                    get_doors=lambda **kw: (
                        [NS(Number="105A"), door] if multiple else [door]
                    ),
                ),
            ),
            get_open_views=lambda: [],
            get_elements_dict=lambda *a: {},
            EasilySelectableElements=lambda *a: nullcontext(),
            _remember=Mock(),
            _unmark=Mock(),
            renumber_element=write,
        ):
            NAMESPACE["door_by_room_renumber"](
                NS(bicat="OST_Doors", by_bicat="OST_Rooms"), window
            )
        return window, write, door

    def test_room_mode_preserves_single_and_multiple_door_numbering(self):
        window, write, _ = self._room_run()
        self.assertEqual(write.call_args.args[2], "105")
        self.assertEqual(window.changed_count, 1)
        _, write, _ = self._room_run(multiple=True)
        self.assertEqual(write.call_args.args[2], "105B")
        _, write, _ = self._room_run(room_number="A105", exclusions="5-10")
        self.assertEqual(write.call_args.args[2], "A105")

    def test_room_mode_exclusion_and_skip_leave_affected_door_unchanged(self):
        for settings in (
            {"exclusions": "100-110"},
            {"skip": True},
            {"skip_during_room": True},
        ):
            with self.subTest(settings=settings):
                window, write, door = self._room_run(**settings)
                write.assert_not_called()
                self.assertEqual(door.Number, "old")
                self.assertEqual(window.skipped_count, 1)

    def test_duplicate_modes_and_configured_replacement_are_preserved(self):
        for mode in ("sweep", "alert", "skip"):
            target = NS(Id=1, Number="001")
            conflict = NS(Id=2, Number="005")
            data = {"001": 1, "005": 2}
            feedback = Mock()
            seq = sequence("005", "2", "decrease", "1-4")
            with patch.dict(
                NAMESPACE,
                revit=NS(doc=NS(GetElement=lambda _: conflict)),
                mark_element_as_renumbered=Mock(),
            ):
                changed = NAMESPACE["renumber_element"](
                    [], target, "005", data, mode, seq.next_from, feedback
                )
            if mode == "sweep":
                self.assertTrue(changed)
                self.assertEqual(target.Number, "005")
                self.assertEqual(conflict.Number, "-001")
            else:
                self.assertFalse(changed)
                self.assertEqual((target.Number, conflict.Number), ("001", "005"))
                feedback.assert_called_once()

    def test_one_window_has_all_controls_and_no_prompt_chain(self):
        root = ET.parse(BUNDLE / "Renumber.xaml").getroot()
        names = {
            item.attrib.get("{http://schemas.microsoft.com/winfx/2006/xaml}Name")
            for item in root.iter()
        }
        self.assertTrue(
            {
                "category_cb",
                "start_tb",
                "direction_cb",
                "step_tb",
                "exclusions_tb",
                "duplicate_cb",
                "room_checkbox",
                "skip_button",
                "status_text",
            }.issubset(names)
        )
        source = (BUNDLE / "script.py").read_text(encoding="utf-8")
        self.assertNotIn("ask_for_string", source)
        self.assertNotIn("CommandSwitchWindow", source)
        self.assertNotIn("forms.alert", source)
        self.assertEqual(source.count("window = RenumberWindow()"), 1)


if __name__ == "__main__":
    unittest.main()
