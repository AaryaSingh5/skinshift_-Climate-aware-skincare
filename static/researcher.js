const ack = $("#ack"); loadNotice("researcher").catch(e => $("#msg").textContent = e.message);
ack.onchange = () => $("#go").disabled = !ack.checked;
$("#f").onsubmit = async e => { e.preventDefault(); $("#msg").textContent = "";
  try { await api("/api/researcher/auth/login", {body: {email: $("#em").value, password: $("#pw").value, ack: ack.checked}}); $("#pw").value = ""; load(); } catch (x) { $("#msg").textContent = x.message; } };
async function load() {
  try { const d = await api("/api/researcher/cohort"); $("#gate").hidden = true; $("#dash").hidden = false;
    $("#k").textContent = "Opted-in participants only. Groups under " + d.k_min + " are hidden. This view was logged."; const tb = $("#tb"); tb.replaceChildren();
    const h = tb.insertRow(); ["City", "People", "Check-ins", "Comfort", "PM2.5", "UV", "Humidity", "Mean effects (PM2.5 / UV / humidity)"].forEach(t => add(h, "th", t));
    d.cities.forEach(c => { const r = tb.insertRow(); const ef = c.mean_effects && typeof c.mean_effects == "object" ? Object.values(c.mean_effects).join(" / ") : (c.mean_effects || "–");
      [c.city, c.participants, c.checkins ?? "–", c.mean_comfort ?? "–", c.mean_pm25 ?? "–", c.mean_uv ?? "–", c.mean_humidity ?? "–", ef].forEach(v => r.insertCell().textContent = v); });
    extras();
  } catch { $("#gate").hidden = false; $("#dash").hidden = true; } }
$("#out").onclick = async () => { await api("/api/researcher/auth/logout", {method: "POST", body: {}}); location.reload(); };
load();
async function extras() {
  const q = await api("/api/researcher/quality"), qt = $("#qt"), qw = $("#qw"); qt.replaceChildren(); qw.replaceChildren();
  q.warnings.forEach(w => add(qw, "p", "⚠ " + w, "err"));
  const h = qt.insertRow(); ["City", "People", "Check-ins", "Median/person", "Env complete", "Active 7d"].forEach(t => add(h, "th", t));
  q.cities.forEach(c => { const r = qt.insertRow(); [c.city, c.participants, c.checkins ?? "–", c.median_checkins_per_person ?? "–", c.environment_complete ?? "–", c.active_last_7_days ?? "–"].forEach(v => r.insertCell().textContent = v); });
  const hy = await api("/api/researcher/hypotheses"), hb = $("#hy"); hb.replaceChildren();
  if (!hy.hypotheses.length) add(hb, "p", "No hypotheses yet. Cohorts need 5+ participants with enough check-ins.", "mu");
  hy.hypotheses.forEach(x => { add(hb, "p", x.city + ": " + x.observation); add(hb, "p", "Research question: " + x.research_question, "mu"); }); $("#hc").textContent = hy.caveat;
  const m = await api("/api/researcher/model-report"); $("#mr").textContent = m.message || JSON.stringify({best: m.best_model_cv, beats_baseline: m.beats_global_mean_baseline, cv: m.held_out_participants_cv}, null, 1);
}
