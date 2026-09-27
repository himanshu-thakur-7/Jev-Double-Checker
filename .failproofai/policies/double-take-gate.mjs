// Failproof AI policy: double-take-gate.
// Before any pay_bill tool call (or a Bash command running pay_bill), ask Double Take at POST /api/gate.
// Loaded automatically from .failproofai/policies/. Set DOUBLE_TAKE_URL if the server is not on localhost:8765.
import { customPolicies, deny, allow } from "failproofai";

const GATE = (process.env.DOUBLE_TAKE_URL || "http://localhost:8765").replace(/\/$/, "") + "/api/gate";
const FLAGS = { "--bill": "bill_id", "--payee": "payee", "--amount": "amount", "--sender": "message_sender", "--text": "message_text" };

function payBillArgs(ctx) {
  if (/pay_bill/i.test(ctx.toolName || "")) return { ...(ctx.toolInput || {}) };
  const cmd = ctx.toolInput?.command;
  if (typeof cmd !== "string" || !cmd.includes("pay_bill")) return null;
  const toks = cmd.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) || [];
  const args = {};
  toks.forEach((t, i) => {
    const [k, v] = t.split("=");
    if (FLAGS[k]) {
      let val = (v ?? toks[i + 1] ?? "").replace(/^['"]|['"]$/g, "");
      args[FLAGS[k]] = FLAGS[k] === "amount" ? Number(val) : val;
    }
  });
  return args;
}

customPolicies.add({
  name: "double-take-gate",
  match: { events: ["PreToolUse"] },
  fn: async (ctx) => {
    const args = payBillArgs(ctx);
    if (!args) return allow();
    try {
      const r = await fetch(GATE, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ tool_name: "pay_bill", tool_input: args, agent: "failproof" }),
      });
      if (!r.ok) return deny(`Double Take gate error ${r.status}; payment blocked. Do not retry.`);
      const v = await r.json();
      return v.decision === "allow" ? allow() : deny(v.reason);
    } catch (e) {
      return deny("Double Take gate unreachable; payment blocked. Do not retry.");
    }
  },
});
