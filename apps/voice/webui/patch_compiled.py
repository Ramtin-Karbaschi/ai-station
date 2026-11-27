#!/usr/bin/env python3
"""Patch the pinned Open WebUI CallOverlay bundle without rebuilding WebUI.

The tool is deliberately fail-closed: it requires the exact known chunk hash
and every replacement anchor exactly once, and never edits the input file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_SHA256 = "ea3ddfe01c42955d1fbf195234a494b4f50749f35bdcb236c64c15b46c1f5443"

_HANGUP_PHRASES = (
    "end the call",
    "hang up",
    "please end the call",
    "please hang up",
    "\u067e\u0627\u06cc\u0627\u0646 \u0645\u06a9\u0627\u0644\u0645\u0647",
    "\u062a\u0645\u0627\u0633 \u0631\u0627 \u0642\u0637\u0639 \u06a9\u0646",
    "\u0642\u0637\u0639 \u062a\u0645\u0627\u0633",
    "\u062a\u0645\u0627\u0633 \u0631\u0627 \u0628\u0628\u0646\u062f",
    "\u062a\u0645\u0627\u0633 \u0631\u0648 \u0628\u0628\u0646\u062f",
    "\u0645\u06a9\u0627\u0644\u0645\u0647 \u0631\u0627 \u062a\u0645\u0627\u0645 \u06a9\u0646",
    "\u0645\u06a9\u0627\u0644\u0645\u0647 \u0631\u0648 \u062a\u0645\u0627\u0645 \u06a9\u0646",
    "\u0645\u06a9\u0627\u0644\u0645\u0647 \u0635\u0648\u062a\u06cc \u0631\u0627 \u062a\u0645\u0627\u0645 \u06a9\u0646",
)
_COMMANDS = f"new Set({json.dumps(_HANGUP_PHRASES, ensure_ascii=True)})"

TRANSCRIPTION_OLD = 'if(Me&&(Me.text,Me.text!=="")){const xt=await y()(Me.text,{_raw:!0})}'
TRANSCRIPTION_NEW = (
    'if(Me&&typeof Me.text==="string"&&Me.text.trim()!==""){const xtText=Me.text.trim();'
    'if(hp.has(hn(xtText))){await hu();return}const xt=await y()(xtText,{_raw:!0})}'
)

CLOSE_OLD = 'ue("click",Zr,async()=>{await fe(),await V(),r(w),r(J),oi.set(!1),g("close")})'
CLOSE_NEW = 'ue("click",Zr,hu)'

INTERRUPTION_DEFAULT = '.voiceInterruption)??!1'

# The CallOverlay recording path has its own STT request builder. Keep normal
# calls automatic: do not forward a fixed browser language preference into a
# mixed-language utterance. Omitting the optional hint preserves API behavior.
STT_CALL_OLD = 'd0(localStorage.token,ce,(ae=(Ge=(Ce=s())==null?void 0:Ce.audio)==null?void 0:Ge.stt)==null?void 0:ae.language).catch(xt=>(pt.error(`${xt}`),null))'
STT_CALL_NEW = 'd0(localStorage.token,ce).catch(xt=>(pt.error(`${xt}`),null))'

HELPER_ANCHOR = (
    'fe=async()=>{try{p&&p.stop()}catch($e){}r(w)&&(r(w).getAudioTracks().forEach('
    'function($e){$e.stop()}),h(w,null))},pe='
)
HELPER_REPLACEMENT = (
    'fe=async()=>{try{p&&p.stop()}catch($e){}r(w)&&(r(w).getAudioTracks().forEach('
    'function($e){$e.stop()}),h(w,null))},hu=async()=>{await fe(),await V(),r(w),'
    'r(J),oi.set(!1),g("close")},hn=$e=>$e.normalize("NFKC").toLocaleLowerCase("fa")'
    '.replace(/[\\u200c\\u200d\\ufeff]/gu," ").replace(/[.!?,;:\\u060c\\u061b\\u061f'
    '"`()[\\]{}<>\\u2026\\-\\u2013\\u2014]/gu," ").replace(/[\\u064a\\u0649]/g,"\\u06cc")'
    '.replace(/\\u0643/g,"\\u06a9").replace(/\\s+/gu," ").trim(),hp='
    + _COMMANDS + ',pe='
)


def patch_text(text: str, *, expected_sha256: str = EXPECTED_SHA256) -> str:
    digest = hashlib.sha256(text.encode()).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"unexpected Open WebUI chunk sha256: {digest}")

    for anchor in (HELPER_ANCHOR, TRANSCRIPTION_OLD, CLOSE_OLD, STT_CALL_OLD):
        count = text.count(anchor)
        if count != 1:
            raise ValueError(f"expected one compiled anchor, found {count}: {anchor[:80]}")
    if text.count(INTERRUPTION_DEFAULT) != 2:
        raise ValueError("expected two native voice interruption defaults")

    result = text.replace(HELPER_ANCHOR, HELPER_REPLACEMENT)
    result = result.replace(TRANSCRIPTION_OLD, TRANSCRIPTION_NEW)
    result = result.replace(CLOSE_OLD, CLOSE_NEW)
    result = result.replace(STT_CALL_OLD, STT_CALL_NEW)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    patched = patch_text(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(patched, encoding="utf-8", newline="")
    print(f"patched {args.output} sha256={hashlib.sha256(patched.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
