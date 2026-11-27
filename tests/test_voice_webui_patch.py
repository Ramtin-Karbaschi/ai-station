import hashlib
import unittest

from apps.voice.webui.patch_compiled import (
    CLOSE_NEW,
    CLOSE_OLD,
    HELPER_ANCHOR,
    HELPER_REPLACEMENT,
    INTERRUPTION_DEFAULT,
    TRANSCRIPTION_NEW,
    TRANSCRIPTION_OLD,
    STT_CALL_NEW,
    STT_CALL_OLD,
    patch_text,
)


class CompiledPatchTests(unittest.TestCase):
    def test_fails_closed_on_unknown_bundle(self):
        with self.assertRaisesRegex(ValueError, "unexpected Open WebUI chunk"):
            patch_text("not the pinned bundle")

    def test_replacements_preserve_native_close_and_keep_interruption_opt_in(self):
        fixture = "\n".join((HELPER_ANCHOR, TRANSCRIPTION_OLD, CLOSE_OLD, STT_CALL_OLD,
                             INTERRUPTION_DEFAULT, INTERRUPTION_DEFAULT))
        digest = hashlib.sha256(fixture.encode()).hexdigest()
        patched = patch_text(fixture, expected_sha256=digest)
        self.assertIn(HELPER_REPLACEMENT, patched)
        self.assertIn(TRANSCRIPTION_NEW, patched)
        self.assertIn(CLOSE_NEW, patched)
        self.assertNotIn(CLOSE_OLD, patched)
        self.assertIn(STT_CALL_NEW, patched)
        self.assertNotIn("station.call.language", patched)
        self.assertNotIn("s().audio.stt.language", patched)
        self.assertEqual(patched.count(".voiceInterruption)??!1"), 2)

    def test_refuses_changed_interruption_structure(self):
        fixture = "\n".join((HELPER_ANCHOR, TRANSCRIPTION_OLD, CLOSE_OLD, STT_CALL_OLD, INTERRUPTION_DEFAULT))
        with self.assertRaisesRegex(ValueError, "interruption defaults"):
            patch_text(fixture, expected_sha256=hashlib.sha256(fixture.encode()).hexdigest())
