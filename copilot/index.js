/**
 * workflow-generator — GitHub Copilot Extension
 * Exposes /agent endpoint for Copilot Chat integration.
 *
 * Start: npm install && npm start
 * Expose: ngrok http 3000
 */
const express = require("express");
const { execFileSync } = require("child_process");
const path = require("path");
const os = require("os");

const app = express();
app.use(express.json());

const ANALYZE_PY = path.join(os.homedir(), ".claude", "skills", "workflow-generator", "scripts", "analyze.py");

app.post("/agent", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("X-Accel-Buffering", "no");

  const userMsg = (req.body.messages || []).findLast(m => m.role === "user")?.content || "";
  const projectDirMatch = userMsg.match(/\/[^\s]+/);
  const projectDir = projectDirMatch ? projectDirMatch[0] : process.cwd();
  const outputFile = path.join(projectDir, "WORKFLOW.html");

  res.write(`data: {"choices":[{"delta":{"content":"Scanning project at \`${projectDir}\`...\\n\\n"}}]}\n\n`);

  try {
    const out = execFileSync("python3", [ANALYZE_PY, projectDir, outputFile], { encoding: "utf8" });
    const lines = out.trim().split("\n").map(l => `> ${l}`).join("\n");
    res.write(`data: {"choices":[{"delta":{"content":"${lines.replace(/"/g,'\\"').replace(/\n/g,'\\n')}\\n\\nWorkflow diagram written to \`${outputFile}\`"}}]}\n\n`);
  } catch (err) {
    res.write(`data: {"choices":[{"delta":{"content":"Error: ${String(err.message).replace(/"/g,'\\"')}"}}]}\n\n`);
  }

  res.write(`data: {"choices":[{"finish_reason":"stop","delta":{}}]}\n\n`);
  res.write("data: [DONE]\n\n");
  res.end();
});

app.get("/", (req, res) => res.json({ name: "workflow-generator", version: "1.0.0" }));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`workflow-generator Copilot Extension listening on :${PORT}`));
