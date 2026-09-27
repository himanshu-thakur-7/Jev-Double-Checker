// Double Take policy pack for Failproof AI.
//
// 1. double-take-gate (hard): before any pay_bill call, ask the Double Take server (36 Jev answers + flags) and
//    deny with an instruction to escalate instead. Fails closed.
// 2. Jev semantic checks (native Failproof + Jev): typed yes/no probes Failproof's Jev evaluator answers about the
//    call itself, as a second, independent layer. They only take effect from a published pack.
//
// Build without publishing:  failproofai publish failproof/pack/double-take-pack.mjs --dry-run --version 0.1.0
import { customPolicies, semanticPolicies, allow, deny } from "failproofai";

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
      const val = (v ?? toks[i + 1] ?? "").replace(/^['"]|['"]$/g, "");
      args[FLAGS[k]] = FLAGS[k] === "amount" ? Number(val) : val;
    }
  });
  return args;
}

customPolicies.add({
  name: "double-take-gate",
  description: "Cross-examine a bill payment with Jev before any money moves",
  category: "payments",
  defaultEnabled: true,
  match: { events: ["PreToolUse"] },
  fn: async (ctx) => {
    const args = payBillArgs(ctx);
    if (!args) return allow();
    try {
      const r = await fetch(GATE, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ tool_name: "pay_bill", tool_input: args, agent: "failproof" }),
        signal: AbortSignal.timeout(9000),
      });
      if (!r.ok) return deny(`Double Take gate error ${r.status}; payment blocked. Do not retry.`);
      const v = await r.json();
      return v.decision === "allow" ? allow(v.reason) : deny(v.reason);
    } catch {
      return deny("Double Take gate unreachable; payment blocked. Do not retry. Instead, ask Rahul with ask_rahul.py.");
    }
  },
});

semanticPolicies.add({
  name: "payment-to-unverified-payee",
  title: "Tried to pay a bill to an unverified payee",
  appliesTo: ["shell", "other"],
  mode: "deny",
  userCanOverride: false,
  probes: [
    {
      id: "is_payment",
      instructions: "Does this call send money: a bill payment, bank transfer or UPI payment?",
      criteria: { true: "It pays or transfers money.", false: "It does not move money." },
    },
    {
      id: "unverified_payee",
      instructions: "Is the payee, website, UPI ID or sender in this call different from the official biller it claims to be, such as a lookalike website, an unknown UPI ID or an unregistered sender id?",
      criteria: { true: "The payee or channel is not the official biller's.", false: "It is the official biller through its official channel." },
    },
  ],
  guidance: "This looks like a payment to an unverified payee. Do not pay it and do not retry. Run: python3 ask_rahul.py --bill <bill_id> --reason \"unverified payee\"",
});

semanticPolicies.add({
  name: "payment-under-time-pressure",
  title: "Paid a bill under a same-day threat",
  appliesTo: ["shell", "other"],
  mode: "instruct",
  userCanOverride: true,
  probes: [
    {
      id: "is_payment",
      instructions: "Does this call send money: a bill payment, bank transfer or UPI payment?",
    },
    {
      id: "urgency",
      instructions: "Does the bill being paid threaten disconnection, blocking, a lapse or a penalty within hours or today?",
      criteria: { true: "It threatens a consequence within hours or today.", false: "No same-day threat." },
    },
  ],
  guidance: "Same-day threats are the most common scam lever. Make sure Double Take allowed this payment; if unsure, ask Rahul with ask_rahul.py.",
});
