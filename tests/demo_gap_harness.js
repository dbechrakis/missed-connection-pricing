// Drives the gap-cover section of site/index.html with a minimal DOM stub: every hub x month x minimum connection
// time x connection time the controls allow, recording what the page shows, so tests can compare it with the API.
// Usage: node demo_gap_harness.js <index.html> <prices.js> <prices_v3.js>
const fs = require("fs"), vm = require("vm");
const [, , htmlPath, pricesPath, v3Path] = process.argv;
const html = fs.readFileSync(htmlPath, "utf8");
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim());
const els = {};
const make = (id) => ({ id, value: "", textContent: "", innerHTML: "", className: "", checked: false, _l: {},
  addEventListener(t, f) { (this._l[t] = this._l[t] || []).push(f); }, setAttribute() {},
  fire(t, v) { (this._l[t] || []).forEach(f => f({ target: { value: v } })); } });
const radios = ["typical", "same", "next"].map(v => Object.assign(make("sc-" + v), { value: v }));
radios[0].checked = true;
const document = { getElementById: (id) => els[id] || (els[id] = make(id)), getElementsByName: () => radios };
const ctx = { document, console, Math, JSON, Number, parseInt, parseFloat, String, Array, Object, isFinite, isNaN };
ctx.window = ctx;
vm.createContext(ctx);
const errors = [];
const run = (code, label) => { try { vm.runInContext(code, ctx); } catch (e) { errors.push(label + ": " + e.message); } };
run(fs.readFileSync(pricesPath, "utf8"), "prices.js");
run(fs.readFileSync(v3Path, "utf8"), "prices_v3.js");
scripts.forEach((s, i) => { if (!/^\s*window\.PRICES/.test(s)) run(s, "page script " + i); });
const G = ctx.PRICES_V3, $ = document.getElementById, out = [];
for (const hub of G.hubs) { $("g-hub").fire("change", hub);
  for (const month of G.months) { $("g-month").fire("change", month);
    for (const mct of [35, 40, 45, 50, 55, 60]) { $("g-mct").fire("change", String(mct));
      for (let slack = 35; slack <= 240; slack += 5) {
        try { $("g-slack").fire("input", String(slack)); } catch (e) { errors.push(`${hub} ${month} ${mct} ${slack}: ${e.message}`); continue; }
        out.push({ hub, month, mct, slack, title: $("g-d-title").textContent, price: $("g-price").textContent,
                   p: $("g-p").textContent, cost: $("g-cost").textContent, share_text: $("g-price-s").textContent });
      } } } }
console.log(JSON.stringify({ errors, rows: out }));
