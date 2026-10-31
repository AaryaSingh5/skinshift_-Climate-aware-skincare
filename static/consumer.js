let mode = "login"; const ack = $("#ack");
loadNotice("consumer").catch(e => $("#msg").textContent = e.message);
ack.onchange = () => $("#go").disabled = !ack.checked;
document.querySelectorAll("[data-mode]").forEach(b => b.onclick = () => { mode = b.dataset.mode; $("#rc-row").hidden = mode != "register"; $("#go").textContent = mode == "login" ? "Sign in" : "Create account"; $("#pw").autocomplete = mode == "login" ? "current-password" : "new-password"; });
$("#f").onsubmit = async e => { e.preventDefault(); $("#msg").textContent = "";
  try { await api("/api/consumer/auth/" + mode, {body: {email: $("#em").value, password: $("#pw").value, ack: ack.checked, research_consent: $("#rc").checked}}); $("#pw").value = ""; dash(); } catch (x) { $("#msg").textContent = x.message; } };
$("#cm").oninput = () => $("#cmv").textContent = $("#cm").value;
async function dash() {
  try { const me = await api("/api/consumer/me"); $("#gate").hidden = true; $("#dash").hidden = false;
    $("#who").textContent = "Signed in as " + me.email + " · " + me.checkins + " check-ins"; $("#avl").textContent = me.email.charAt(0); $("#rs").checked = me.research_consent;
    if (!$("#city").options.length) me.cities.forEach(c => add($("#city"), "option", c)); twin(); if (window.loadAll) loadAll();
  } catch { $("#gate").hidden = false; $("#dash").hidden = true; } }
async function twin() { const t = await api("/api/consumer/twin"), box = $("#twin"); box.replaceChildren();
  if (!t.ready) { add(box, "p", t.message); add(box, "p", t.have + " of " + t.need + " check-ins with environment data.", "mu"); return; }
  add(box, "p", "Typical comfort: " + t.baseline + "/10 · " + t.n + " check-ins · confidence " + t.confidence);
  const tb = add(box, "table", ""); for (const [k, v] of Object.entries(t.effects)) { const r = tb.insertRow(); r.insertCell().textContent = k; r.insertCell().textContent = (v > 0 ? "+" : "") + v + (v < -.15 ? " comfort falls as this rises" : v > .15 ? " comfort rises as this rises" : " little effect seen"); }
  add(box, "p", t.note, "mu"); }
$("#ci").onclick = async () => { try { const r = await api("/api/consumer/checkin", {body: {city: $("#city").value, comfort: +$("#cm").value}});
  $("#cmsg").textContent = "Saved. Environment source: " + r.environment.source + "."; dash(); } catch (x) { $("#cmsg").textContent = x.message; } };
$("#rs").onchange = () => api("/api/consumer/consent/research", {method: "PUT", body: {granted: $("#rs").checked}});
$("#out").onclick = async () => { await api("/api/consumer/auth/logout", {method: "POST", body: {}}); location.reload(); };
$("#del").onclick = async () => { if (confirm("Delete your account and all your data? This cannot be undone.")) { if (window.clearPhotos) await clearPhotos(); await api("/api/consumer/account", {method: "DELETE"}); location.reload(); } };
dash();
