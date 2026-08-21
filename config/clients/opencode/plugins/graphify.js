// graphify OpenCode plugin (AI Station).
// One reminder per session, only when graph.json exists in the workspace.
// Keep the reminder free of backticks and dollar-paren command
// substitution. OpenCode prepends echo "<reminder>" ; <cmd>.
import { existsSync } from "fs";
import { join } from "path";

export const GraphifyPlugin = async ({ directory }) => {
  let reminded = false;

  return {
    "tool.execute.before": async (input, output) => {
      if (reminded) return;
      const localGraph = join(directory, "graphify-out", "graph.json");
      if (!existsSync(localGraph)) return;
      if (input.tool !== "bash") return;
      output.args.command =
        'echo "[graphify] graphify-out/graph.json is present. For architecture questions run: ai graphify query YOUR-QUESTION (scoped subgraph). Read GRAPH_REPORT.md only for a broad overview." ; ' +
        output.args.command;
      reminded = true;
    },
  };
};
