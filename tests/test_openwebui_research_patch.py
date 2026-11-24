import asyncio
import sys
import textwrap
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from apps.voice.webui import patch_research_backend as backend


class LongWriterResearchPatchTests(unittest.TestCase):
    def setUp(self):
        self.research = ModuleType("open_webui.utils.station_research")
        exec(backend.HELPER, vars(self.research))

    def test_longwriter_defaults_to_legacy_without_overriding_explicit_modes(self):
        run = (
            "def select_mode(form_data, request_params, model_info=None):\n"
            + textwrap.indent(textwrap.dedent(backend.LONGWRITER_PARAMS), "    ")
            + "    return request_params.get('function_calling')\n"
        )
        scope = {}
        with patch.dict(sys.modules, {self.research.__name__: self.research}):
            exec(run, scope)
            select_mode = scope["select_mode"]
            longwriter = {"model": self.research.LONGWRITER}
            self.assertEqual(select_mode(longwriter, {}), "legacy")
            for mode in ("native", "legacy"):
                self.assertEqual(select_mode(longwriter, {"function_calling": mode}), mode)
            self.assertIsNone(select_mode({"model": "another-model"}, {}))

    def test_strict_planner_accepts_only_short_structured_terms(self):
        parse = self.research.parse_public_queries
        persian = "\u0646\u0631\u062e \u062a\u0648\u0631\u0645 \u0627\u06cc\u0631\u0627\u0646"
        self.assertEqual(
            parse(f'{{"queries":[" {persian} ","Iran inflation rate"]}}'),
            [persian, "Iran inflation rate"],
        )
        self.assertEqual(parse('{"queries":["one","one"]}'), ["one"])
        self.assertEqual(
            parse('<think>Internal planning</think>\n<answer>{"queries":["public term"]}</answer>'),
            ["public term"],
        )
        self.assertEqual(
            parse('<answer>{"queries":["public term"]}</answer>\nExtra prose {"queries":["ignored"]}'),
            ["public term"],
        )
        self.assertEqual(
            parse('<think>Internal planning</think>\n{"queries":["public term"]}'),
            ["public term"],
        )

        for response in (
            '{"queries":[]}',
            'prefix {"queries":["one"]}',
            '{"queries":["one","two","three","four"]}',
            '{"queries":"one"}',
            '{"queries":["one",123]}',
            '{"queries":[" "]}',
            '{"queries":["one\\ntwo"]}',
            '{"queries":["one@example.com"]}',
            '{"queries":["/local/path"]}',
            '{"queries":["' + "a" * 121 + '"]}',
        ):
            with self.subTest(response=response):
                self.assertEqual(parse(response), [])

    def test_planner_error_does_not_forward_the_user_message_for_longwriter(self):
        code = (
            "async def queries(form_data, user_message, error):\n"
            "    from open_webui.utils.station_research import LONGWRITER\n"
            "    strict_planner = form_data['model'] == LONGWRITER\n"
            "    try:\n"
            "        raise error\n"
            "    except Exception as e:\n"
            + backend.LONGWRITER_SEARCH_FAILURE
            + "    return queries\n"
        )
        scope = {"log": Mock()}
        exec(code, scope)
        with patch.dict(sys.modules, {self.research.__name__: self.research}):
            error = RuntimeError("planner failed")
            for alias, expected in ((self.research.LONGWRITER, []), ("other", ["raw prompt"])):
                self.assertEqual(
                    asyncio.run(scope["queries"]({"model": alias}, "raw prompt", error)),
                    expected,
                )

    def test_excerpt_prefers_query_terms_over_unrelated_page_text(self):
        page = "Navigation and footer text. " * 20 + "Pathlib concrete filesystem paths. " * 4
        excerpt = self.research.select_source_excerpt(page, ["pathlib filesystem paths"], limit=70)
        self.assertIn("Pathlib concrete filesystem paths", excerpt)
        self.assertLessEqual(len(excerpt), 70)

    def test_backend_patch_refuses_missing_or_duplicate_anchors(self):
        for original in ("missing", "anchor anchor"):
            with self.subTest(original=original), self.assertRaises(ValueError):
                backend.replace_once(original, "anchor", "replacement")
