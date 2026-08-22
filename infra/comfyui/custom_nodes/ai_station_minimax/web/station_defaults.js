import { app } from "../../scripts/app.js";

const MUSIC_WORKFLOW = "/api/userdata/workflows%2Fmusic3-text-to-music.json";

function graphText() {
  try {
    return JSON.stringify(app.graph?.serialize?.() || {});
  } catch {
    return "";
  }
}

function isMiniMaxGraph(text) {
  return (
    text.includes("MiniMaxMusic3") ||
    text.includes("MiniMaxH3") ||
    text.includes("EmptyMiniMaxMusic3") ||
    text.includes("minimax_music3_") ||
    text.includes("minimax_h3_")
  );
}

function isFlux2Graph(text) {
  return (
    text.includes("UnetLoaderGGUF") ||
    text.includes("EmptyFlux2LatentImage") ||
    text.includes("flux2-dev-Q4_K_M.gguf") ||
    text.includes("mistral_3_small_flux2_")
  );
}

function isStationGraph(text) {
  return isMiniMaxGraph(text) || isFlux2Graph(text);
}

async function fetchWorkflow(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} HTTP ${response.status}`);
  }
  return response.json();
}

async function loadStationWorkflow(data) {
  if (data.nodes && typeof app.loadGraphData === "function") {
    await app.loadGraphData(data);
    return;
  }
  if (data.prompt && typeof app.loadApiJson === "function") {
    await app.loadApiJson(data.prompt);
    return;
  }
  throw new Error("workflow JSON has neither nodes nor prompt");
}

function missingLoaderFiles() {
  const missing = [];
  const nodes = app.graph?._nodes || [];
  for (const node of nodes) {
    const type = node.comfyClass || node.type || "";
    if (!/Loader/i.test(type) && type !== "LoraLoaderModelOnly") {
      continue;
    }
    for (const widget of node.widgets || []) {
      if (typeof widget.value !== "string") {
        continue;
      }
      if (
        !widget.value.endsWith(".safetensors") &&
        !widget.value.endsWith(".gguf")
      ) {
        continue;
      }
      const options = widget.options?.values || widget.options || [];
      if (Array.isArray(options) && options.length && !options.includes(widget.value)) {
        missing.push(`${type}: ${widget.value}`);
      }
    }
  }
  return missing;
}

app.registerExtension({
  name: "AIStation.MiniMaxDefaults",
  async setup() {
    const originalQueue = app.queuePrompt.bind(app);
    app.queuePrompt = async function queuedPrompt(number, batchCount) {
      const text = graphText();
      if (!isStationGraph(text)) {
        window.alert(
          "This canvas is not a station MiniMax or FLUX.2 workflow.\n\n" +
            "Open Workflows → music3-text-to-music.json, h3-text-to-video.json, or flux2-text-to-image.json."
        );
        return;
      }
      const missing = missingLoaderFiles();
      if (missing.length) {
        window.alert(
          "AI Station does not have those model files.\n\n" +
            missing.slice(0, 8).join("\n") +
            "\n\nOpen Workflows → music3-text-to-music.json, h3-text-to-video.json, or flux2-text-to-image.json."
        );
        return;
      }
      return originalQueue(number, batchCount);
    };

    const text = graphText();
    if (isStationGraph(text) && !text.includes("EmptySD3LatentImage")) {
      return;
    }
    try {
      const data = await fetchWorkflow(MUSIC_WORKFLOW);
      await loadStationWorkflow(data);
      console.info("[AI Station] Loaded MiniMax Music 3 instead of the stock Flux canvas");
    } catch (error) {
      console.error("[AI Station] Failed to load MiniMax default workflow", error);
    }
  },
});
