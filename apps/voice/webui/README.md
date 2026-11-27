# Open WebUI spoken hangup patch

`patch_compiled.py` is a fail-closed build-time patch for the exact installed
Open WebUI bundle. It does not modify the running container or require a full
frontend rebuild.

Recognized commands are exact standalone transcripts after normalization:

- `end the call`
- `hang up`
- `\u067e\u0627\u06cc\u0627\u0646 \u0645\u06a9\u0627\u0644\u0645\u0647`
- `\u062a\u0645\u0627\u0633 \u0631\u0627 \u0642\u0637\u0639 \u06a9\u0646`
- `\u0642\u0637\u0639 \u062a\u0645\u0627\u0633`

Substring matches are rejected, so a sentence such as "do not end the call"
remains an ordinary prompt. The command is evaluated only after server
transcription of the user's recording; assistant playback is never parsed.
Normal calls use automatic STT detection with no call-specific language menu
or persisted browser language preference. The optional API language field
remains available to other clients.
The existing native cleanup (`stopAudioStream`, `stopVideoStream`,
`showCallOverlay=false`, `dispatch('close')`) is reused by the spoken path.

## Apply and verify

```bash
python3 apps/voice/webui/patch_compiled.py \
  --input /path/to/D4rfk4Lu.js \
  --output /path/to/D4rfk4Lu.spoken-hangup.js
node --check /path/to/D4rfk4Lu.spoken-hangup.js
```

The exact installed revision is
`ecd48e2f718220a6400ecf49eafd4867a38feb10`. The current CallOverlay chunk is
`D4rfk4Lu.js`, SHA-256
`ea3ddfe01c42955d1fbf195234a494b4f50749f35bdcb236c64c15b46c1f5443`.
The tool verifies this checksum and the expected anchors before writing output.
It preserves native voice interruption as an explicit user setting; when no preference
exists, playback interruption remains disabled to prevent assistant audio recapture.

No new service or frontend is required. In a derived image build, run the
patch after frontend assets are produced and replace only the verified chunk
in the image layer. Point the existing `open-webui` service at that derived
image; do not write into the live data volume. The native End call button is
the fallback.
