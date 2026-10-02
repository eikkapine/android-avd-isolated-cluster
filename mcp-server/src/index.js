/**
 * android-fleet-mcp — Native MCP server for driving an AVD phone cluster.
 *
 * Tool groups:
 *   fleet.*   — cluster lifecycle (status, boot, kill, rotate, capacity)
 *   phone.*   — per-phone control (tap, type, swipe, screenshot, shell, intent,
 *               install, uninstall, app mgmt, wake, scrcpy)
 *
 * Transport: stdio (Claude Desktop / Claude Code compatible).
 *
 * Configuration: paths resolve from ANDROID_FLEET_ROOT (repo checkout) and
 * ANDROID_SDK_ROOT; override ANDROID_FLEET_PYTHON if python isn't on PATH.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ErrorCode,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";
import { spawn, execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);

// ------------------------------------------------------------------ config
const HERE = resolve(fileURLToPath(new URL(".", import.meta.url)), "..", "..");
const ROOT = process.env.ANDROID_FLEET_ROOT ?? HERE;
const FLEET_CFG = resolve(ROOT, "cluster", "config", "fleet.json");
const SDK = process.env.ANDROID_SDK_ROOT ?? "C:/Android/Sdk";
const PYTHON = process.env.ANDROID_FLEET_PYTHON ?? "python";
const SCRCPY = process.env.ANDROID_FLEET_SCRCPY ?? resolve(SDK, "scrcpy", "scrcpy.exe");

function readJson(p) {
  if (!existsSync(p)) return null;
  const raw = readFileSync(p, "utf-8").replace(/^\uFEFF/, "");
  return JSON.parse(raw);
}

function fleetCfg() {
  const c = readJson(FLEET_CFG);
  if (!c) throw new McpError(ErrorCode.InternalError, "fleet.json missing — run the provisioner first");
  return c;
}

function serialOf(index) {
  return `emulator-${(fleetCfg().base_port ?? 5554) + index * 2}`;
}

/** Promise-wrapped adb invocation. */
function adb(serial, args, timeoutMs = 30000) {
  return new Promise((resolve_, reject) => {
    const p = spawn(resolve(SDK, "platform-tools", "adb.exe"), ["-s", serial, ...args],
      { windowsHide: true });
    let out = "", err = "";
    const t = setTimeout(() => {
      p.kill();
      reject(new Error(`adb timeout: ${args.join(" ")}`));
    }, timeoutMs);
    p.stdout.on("data", d => (out += d));
    p.stderr.on("data", d => (err += d));
    p.on("close", code => {
      clearTimeout(t);
      code === 0 ? resolve_(out) : reject(new Error(err || out || `rc=${code}`));
    });
  });
}

const shell = (serial, cmd, t) => adb(serial, ["shell", cmd], t);

/** Promise-wrapped generic exec (emulator console, orchestrator script). */
function runExe(exe, args, timeoutMs = 120000) {
  return new Promise((resolve_, reject) => {
    execFile(exe, args, { timeout: timeoutMs, windowsHide: true, maxBuffer: 32 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err && !stdout) reject(new Error(stderr || err.message));
        else resolve_(stdout || stderr || "");
      });
  });
}

const fleetPy = (...args) => runExe(PYTHON, [resolve(ROOT, "cluster", "scripts", "fleet.py"), ...args], 600000);

// ------------------------------------------------------------------ tools
const TOOLS = [
  // ---- cluster lifecycle
  {
    name: "fleet.status",
    description: "Full fleet table: every phone slot and its live/booting/off state.",
    inputSchema: { type: "object", properties: {}, required: [] },
    handler: async () => {
      const out = await fleetPy("status");
      return { content: [{ type: "text", text: out || "(no state)" }] };
    },
  },
  {
    name: "fleet.boot",
    description: "Boot phones. index=N boots one specific slot by number; count=N boots the first N (default: memory-safe live budget). Post-boot device setup runs automatically when installed.",
    inputSchema: {
      type: "object",
      properties: {
        count: { type: "number", description: "how many phones to boot (default from fleet.json)" },
        index: { type: "number", description: "boot exactly this slot number instead of the first count" },
        wait: { type: "boolean", description: "block until booted (default true)" },
      },
      required: [],
    },
    handler: async (args) => {
      const out = await fleetPy(
        "boot",
        ...(args.index !== undefined ? ["--index", String(args.index)] : ["--count", String(args.count ?? 12)]),
        ...(args.wait === false ? ["--no-wait"] : ["--wait"]),
      );
      return { content: [{ type: "text", text: out || "boot wave dispatched" }] };
    },
  },
  {
    name: "fleet.kill",
    description: "Kill phone by index. Verifies the emulator actually left adb before returning.",
    inputSchema: { type: "object", properties: { index: { type: "number" } }, required: ["index"] },
    handler: async (args) => {
      const out = await fleetPy("kill", "--index", String(args.index));
      return { content: [{ type: "text", text: (out || "").trim() || `phone ${args.index} killed` }] };
    },
  },
  {
    name: "fleet.rotate",
    description: "Hot-swap: kill oldest live phone, boot next queued one.",
    inputSchema: { type: "object", properties: {}, required: [] },
    handler: async () => {
      const out = await fleetPy("rotate");
      return { content: [{ type: "text", text: out || "rotated" }] };
    },
  },
  {
    name: "fleet.capacity",
    description: "Host memory snapshot + how many more phones fit right now.",
    inputSchema: { type: "object", properties: {}, required: [] },
    handler: async () => {
      const profiles = readJson(resolve(ROOT, "fleet-state", "profiles.json")) ?? [];
      const live = readJson(resolve(ROOT, "fleet-state", "live.json")) ?? { live: [], booting: [] };
      let ramFreeGb = null, ramTotalGb = null;
      try {
        const { stdout } = await execFileAsync("powershell", [
          "-NoProfile", "-Command",
          "(Get-CimInstance Win32_OperatingSystem) | ForEach-Object { '{0:N2}|{1:N2}' -f ($_.TotalVisibleMemorySize/1MB), ($_.FreePhysicalMemory/1MB) }",
        ], { timeout: 30000 });
        const [tot, free] = stdout.trim().split("|").map(Number);
        ramTotalGb = tot; ramFreeGb = free;
      } catch { /* non-Windows or CIM unavailable — report nulls */ }
      const perPhoneGb = 1.9;
      const fits = ramFreeGb !== null ? Math.max(0, Math.floor(ramFreeGb / perPhoneGb)) : null;
      return { content: [{ type: "text", text: JSON.stringify({
        host_ram_total_gb: ramTotalGb,
        host_ram_free_gb: ramFreeGb,
        live: live.live ?? [],
        booting: live.booting ?? [],
        room_for_more_phones: fits,
      }, null, 2) }] };
    },
  },

  // ---- per-phone control
  {
    name: "phone.shell",
    description: "Run any adb shell command on one phone.",
    inputSchema: {
      type: "object",
      properties: { index: { type: "number" }, command: { type: "string" } },
      required: ["index", "command"],
    },
    handler: async (a) => {
      const out = await shell(serialOf(a.index), a.command, 60000);
      return { content: [{ type: "text", text: out || "(no output)" }] };
    },
  },
  {
    name: "phone.tap",
    description: "Tap the screen at x,y.",
    inputSchema: {
      type: "object",
      properties: { index: { type: "number" }, x: { type: "number" }, y: { type: "number" } },
      required: ["index", "x", "y"],
    },
    handler: async (a) => {
      await shell(serialOf(a.index), `input tap ${a.x} ${a.y}`);
      return { content: [{ type: "text", text: `tapped ${a.x},${a.y} on phone ${a.index}` }] };
    },
  },
  {
    name: "phone.swipe",
    description: "Swipe from (x1,y1) to (x2,y2) over duration_ms.",
    inputSchema: {
      type: "object",
      properties: {
        index: { type: "number" }, x1: { type: "number" }, y1: { type: "number" },
        x2: { type: "number" }, y2: { type: "number" }, duration_ms: { type: "number" },
      },
      required: ["index", "x1", "y1", "x2", "y2"],
    },
    handler: async (a) => {
      await shell(serialOf(a.index),
        `input swipe ${a.x1} ${a.y1} ${a.x2} ${a.y2} ${a.duration_ms ?? 300}`);
      return { content: [{ type: "text", text: `swiped on phone ${a.index}` }] };
    },
  },
  {
    name: "phone.type",
    description: "Type text into the focused field. Waits for focus, verifies the text landed, and self-heals on input-dispatcher races.",
    inputSchema: {
      type: "object",
      properties: { index: { type: "number" }, text: { type: "string" } },
      required: ["index", "text"],
    },
    handler: async (a) => {
      // one device-shell parse: wrap in single quotes, escape embedded quotes;
      // control chars aren't typeable via `input text` — flatten to spaces
      const safe = a.text.replace(/[\r\n\t]+/g, " ").replace(/'/g, "'\\''");
      const s = serialOf(a.index);
      const dump = "uiautomator dump /sdcard/focus.xml >/dev/null 2>&1; cat /sdcard/focus.xml";
      // a freshly tapped editor takes a moment to take focus — typing into
      // the transition swallows leading chars. wait for a focused field.
      for (let i = 0; i < 4; i++) {
        const d = await shell(s, dump, 30000);
        if (/EditText[^>]*focused="true"/.test(d)) break;
        await shell(s, "sleep 1", 5000);
      }
      await shell(s, `input text '${safe}'`);
      // verify the text actually landed — the input dispatcher can lag a
      // dismissed dialog and eat leading keyevents even with focus shown.
      // on mismatch: clear the field and retype (bounded).
      let fieldText = "";
      for (let t = 0; t < 2; t++) {
        await shell(s, "sleep 1", 5000);
        const d = await shell(s, dump, 30000);
        const node = (d.split("<node").find(
          (n) => /class="[^"]*EditText/.test(n) && /focused="true"/.test(n)) || "");
        const m = node.match(/text="([^"]*)"/);
        fieldText = m ? m[1]
          .replace(/&/g, "&").replace(/</g, "<").replace(/>/g, ">")
          .replace(/"/g, '"').replace(/'/g, "'") : "";
        if (fieldText === a.text) {
          return { content: [{ type: "text", text: `typed ${a.text.length} chars on phone ${a.index} (verified)` }] };
        }
        // clear from the end, then retype — one shell round-trip
        const n = fieldText.length + 2;
        await shell(s, `input keyevent 123; for i in $(seq 1 ${n}); do input keyevent 67; done; input text '${safe}'`, 30000);
      }
      return { content: [{ type: "text", text: `typed on phone ${a.index} — verify: field shows "${fieldText}" not "${a.text}"` }] };
    },
  },
  {
    name: "phone.key",
    description: "Press a key: HOME, BACK, APP_SWITCH, ENTER, DEL, VOLUP, VOLDN, POWER, TAB, ESC, MENU.",
    inputSchema: {
      type: "object",
      properties: { index: { type: "number" }, key: { type: "string" } },
      required: ["index", "key"],
    },
    handler: async (a) => {
      const map = {
        HOME: 3, BACK: 4, APP_SWITCH: 187, ENTER: 66, DEL: 67,
        VOLUP: 24, VOLDN: 25, POWER: 26, TAB: 61, ESC: 27, MENU: 82,
      };
      const code = map[a.key.toUpperCase()] ?? parseInt(a.key, 10);
      if (!code) throw new McpError(ErrorCode.InvalidParams, `unknown key ${a.key}`);
      await shell(serialOf(a.index), `input keyevent ${code}`);
      return { content: [{ type: "text", text: `key ${a.key} on phone ${a.index}` }] };
    },
  },
  {
    name: "phone.screenshot",
    description: "Capture screenshot PNG (returns image content + local path).",
    inputSchema: {
      type: "object",
      properties: { index: { type: "number" }, name: { type: "string" } },
      required: ["index"],
    },
    handler: async (a) => {
      const fname = `phone_${a.index}_${a.name ?? "shot"}.png`;
      const local = resolve(ROOT, "fleet-state", "screens", fname);
      await adb(serialOf(a.index), ["shell", "screencap -p /sdcard/shot.png"]);
      await adb(serialOf(a.index), ["pull", "/sdcard/shot.png", local.replace(/\\/g, "/")]);
      await shell(serialOf(a.index), "rm /sdcard/shot.png");
      return {
        content: [
          { type: "text", text: `screenshot saved: ${local}` },
          { type: "image", data: readFileSync(local).toString("base64"), mimeType: "image/png" },
        ],
      };
    },
  },
  {
    name: "phone.uidump",
    description: "Dump UI hierarchy (uiautomator XML) — element bounds, text, IDs for targeting taps.",
    inputSchema: { type: "object", properties: { index: { type: "number" } }, required: ["index"] },
    handler: async (a) => {
      const out = await shell(serialOf(a.index),
        "(uiautomator dump /sdcard/uidump.xml 2>/dev/null || (sleep 2 && uiautomator dump /sdcard/uidump.xml)) >/dev/null 2>&1; cat /sdcard/uidump.xml",
        45000);
      return { content: [{ type: "text", text: out.slice(0, 50000) || "(empty dump)" }] };
    },
  },
  {
    name: "phone.install",
    description: "Install an APK on one phone.",
    inputSchema: {
      type: "object",
      properties: { index: { type: "number" }, apk: { type: "string" } },
      required: ["index", "apk"],
    },
    handler: async (a) => {
      const out = await adb(serialOf(a.index), ["install", "-r", a.apk], 180000);
      return { content: [{ type: "text", text: out || "installed" }] };
    },
  },
  {
    name: "phone.uninstall",
    description: "Uninstall a package from one phone.",
    inputSchema: {
      type: "object",
      properties: { index: { type: "number" }, pkg: { type: "string" } },
      required: ["index", "pkg"],
    },
    handler: async (a) => {
      const out = await adb(serialOf(a.index), ["uninstall", a.pkg]);
      return { content: [{ type: "text", text: out || "uninstalled" }] };
    },
  },
  {
    name: "phone.launch",
    description: "Launch an app by package (optionally activity).",
    inputSchema: {
      type: "object",
      properties: {
        index: { type: "number" }, pkg: { type: "string" }, activity: { type: "string" },
      },
      required: ["index", "pkg"],
    },
    handler: async (a) => {
      if (a.activity) {
        await shell(serialOf(a.index), `am start -n ${a.pkg}/${a.activity}`);
      } else {
        await shell(serialOf(a.index),
          `monkey -p ${a.pkg} -c android.intent.category.LAUNCHER 1`);
      }
      return { content: [{ type: "text", text: `launched ${a.pkg} on phone ${a.index}` }] };
    },
  },
  {
    name: "phone.apps",
    description: "List installed third-party packages.",
    inputSchema: { type: "object", properties: { index: { type: "number" } }, required: ["index"] },
    handler: async (a) => {
      const out = await shell(serialOf(a.index), "pm list packages -3");
      return { content: [{ type: "text", text: out || "(none)" }] };
    },
  },
  {
    name: "phone.wake",
    description: "Wake screen + dismiss keyguard.",
    inputSchema: { type: "object", properties: { index: { type: "number" } }, required: ["index"] },
    handler: async (a) => {
      await shell(serialOf(a.index), "input keyevent KEYCODE_WAKEUP");
      await shell(serialOf(a.index), "input keyevent 82");
      return { content: [{ type: "text", text: `phone ${a.index} awake` }] };
    },
  },
  {
    name: "phone.scrcpy",
    description: "Open live visual window of one phone via scrcpy (for human-in-the-loop moments).",
    inputSchema: { type: "object", properties: { index: { type: "number" } }, required: ["index"] },
    handler: async (a) => {
      spawn(SCRCPY, ["-s", serialOf(a.index)], { detached: true, stdio: "ignore",
        windowsHide: false }).unref();
      return { content: [{ type: "text", text: `scrcpy window opening for phone ${a.index}` }] };
    },
  },
];

// ------------------------------------------------------------------ server
const server = new Server(
  { name: "android-fleet-mcp", version: "1.0.0" },
  { capabilities: { tools: {} } },
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })),
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args = {} } = request.params;
  const tool = TOOLS.find(t => t.name === name);
  if (!tool) throw new McpError(ErrorCode.MethodNotFound, `unknown tool ${name}`);
  try {
    return await tool.handler(args ?? {});
  } catch (e) {
    throw new McpError(ErrorCode.InternalError, `${name} failed: ${e.message}`);
  }
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  process.stderr.write("android-fleet-mcp: online (stdio)\n");
}

main().catch(e => {
  process.stderr.write(`fatal: ${e.message}\n`);
  process.exit(1);
});
