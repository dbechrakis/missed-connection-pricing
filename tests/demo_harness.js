// Drives site/index.html's script with a minimal DOM stub: every hub x airline x connection time x
// scenario the controls allow, checking that nothing throws and nothing renders as NaN/undefined.
// Usage: node demo_harness.js <index.html> <prices.js>
const fs = require("fs"), vm = require("vm");
const [, , htmlPath, pricesPath] = process.argv;
const html = fs.readFileSync(htmlPath, "utf8");
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m => m[1]).filter(s => s.trim());

const sl = html.match(/<input id="slack"[^>]*>/)[0];
const attr = (n) => { const m = sl.match(new RegExp(n + '="([^"]+)"')); return m ? +m[1] : null; };
const slider = { min: attr("min"), max: attr("max"), step: attr("step"), value: attr("value") };

const els = {};
const make = (id) => ({ id, value: "", textContent: "", innerHTML: "", className: "", checked: false, _l: {},
  addEventListener(t, f) { (this._l[t] = this._l[t] || []).push(f); }, setAttribute() {}, fire(t, v) { (this._l[t] || []).forEach(f => f({ target: { value: v } })); } });
const radios = ["typical", "same", "next"].map(v => Object.assign(make("sc-" + v), { value: v }));
radios[0].checked = true;
const document = { getElementById: (id) => els[id] || (els[id] = make(id)), getElementsByName: () => radios };

const ctx = { document, console, Math, JSON, Number, parseInt, parseFloat, String, Array, Object, isFinite, isNaN };
ctx.window = ctx;
vm.createContext(ctx);
const errors = [];
let checks = 0;
function run(code, label) { try { vm.runInContext(code, ctx); } catch (e) { errors.push(label + ": " + e.message); } }
run(fs.readFileSync(pricesPath, "utf8"), "prices.js");
scripts.forEach((s, i) => { if (!/^\s*window\.PRICES/.test(s)) run(s, "page script " + i); });

function inspect(where) {
  checks++;
  for (const id of Object.keys(els)) {
    const t = String(els[id].textContent) + " " + String(els[id].innerHTML);
    if (/NaN|undefined|null|Infinity/.test(t)) errors.push(where + ": element " + id + " shows '" + t.slice(0, 80) + "'");
  }
  const price = els["m-price"].textContent;
  if (!/^\$\d/.test(price)) errors.push(where + ": price is '" + price + "'");
  if (!els["d-title"].textContent) errors.push(where + ": empty decision");
}

if (!errors.length) {
  inspect("initial");
  const P = ctx.window.PRICES;
  if (slider.value === null || slider.value < slider.min || slider.value > slider.max) errors.push("slider has no valid initial value: " + JSON.stringify(slider));
  for (const hub of P.hubs) {
    try { els["hub"].fire("change", hub); } catch (e) { errors.push(hub + ": hub change threw: " + e.message); }
    for (const carrier of ["ALL"].concat(P.carriers[hub])) {
      try { els["carrier"].fire("change", carrier); } catch (e) { errors.push(hub + "/" + carrier + ": carrier change threw: " + e.message); }
      for (let v = slider.min; v <= slider.max; v += slider.step) {
        try { els["slack"].fire("input", String(v)); } catch (e) { errors.push(hub + "/" + carrier + "/" + v + ": slider input threw: " + e.message); continue; }
        for (const r of radios) {
          try { r.fire("change", r.value); inspect(hub + "/" + carrier + "/" + v + "/" + r.value); }
          catch (e) { errors.push(hub + "/" + carrier + "/" + v + "/" + r.value + ": " + e.message); }
          if (errors.length > 20) break;
        }
      }
    }
  }
}
console.log(JSON.stringify({ checks, slider, errors: errors.slice(0, 20) }));
process.exitCode = errors.length ? 1 : 0;   // not process.exit(): on Windows it can cut off piped output
