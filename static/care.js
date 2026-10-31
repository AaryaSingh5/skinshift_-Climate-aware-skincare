const list = s => s.split(",").map(x => x.trim()).filter(Boolean);
function showTab(n) { document.querySelectorAll(".tab").forEach(t => t.hidden = t.id != "tab-" + n); document.querySelectorAll(".bnav [data-tab]").forEach(b => b.dataset.tab == n ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")); $("#menu").hidden = true; $("#mnu").setAttribute("aria-expanded", "false"); window.scrollTo(0, 0); }
document.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => showTab(b.dataset.tab));
function showSeg(n) { document.querySelectorAll(".pane").forEach(p => p.hidden = p.id != "pane-" + n); document.querySelectorAll("[data-seg]").forEach(b => b.setAttribute("aria-selected", b.dataset.seg == n)); }
document.querySelectorAll("[data-seg]").forEach(b => b.onclick = () => showSeg(b.dataset.seg));
$("#avt").onclick = () => showTab("care");
$("#mnu").onclick = () => { const m = $("#menu"); m.hidden = !m.hidden; $("#mnu").setAttribute("aria-expanded", String(!m.hidden)); };
showTab("home");
async function loadAll() { loadPhotos(); loadGallery(); loadProfile(); loadProducts(); loadHome(); loadAlerts(); }
async function loadHome() {
  try { const r = await api("/api/consumer/home?city=" + encodeURIComponent($("#city").value || "Mumbai"));
    $("#rt").textContent = r.title; $("#rw").textContent = r.why; $("#re").textContent = "Confidence: " + r.confidence + ". " + r.evidence; } catch (x) { $("#rt").textContent = "Couldn’t load today’s advice"; $("#rw").textContent = x.message; } }
$("#city").onchange = loadHome;
async function loadProfile() { const p = await api("/api/consumer/profile");
  $("#pst").value = p.skin_type || ""; $("#pco").value = p.concerns.join(", "); $("#pgo").value = p.goals.join(", "); $("#pse").value = p.sensitivities.concat(p.avoid).join(", "); $("#pff").checked = p.fragrance_free; $("#pqm").checked = p.quiet_mode; $("#pai").checked = p.ai_personalisation; $("#pem").checked = p.alert_email; }
$("#psv").onclick = async () => { try { await api("/api/consumer/profile", {method: "PUT", body: {skin_type: $("#pst").value || null, concerns: list($("#pco").value), goals: list($("#pgo").value), sensitivities: [], avoid: list($("#pse").value), fragrance_free: $("#pff").checked, quiet_mode: $("#pqm").checked, ai_personalisation: $("#pai").checked, alert_email: $("#pem").checked}}); $("#pmsg").textContent = "Saved."; loadProducts(); loadHome(); } catch (x) { $("#pmsg").textContent = x.message; } };
async function loadProducts() { const d = await api("/api/consumer/products"), box = $("#plist"), nb = $("#pnotes"); box.replaceChildren(); nb.replaceChildren();
  if (!d.products.length) add(box, "p", "No products yet. Add what you already use and I’ll check it before suggesting anything new.", "mu");
  d.products.forEach(p => { const w = add(box, "div", "", "box"); add(w, "b", p.name + " · " + p.category + " · " + p.slot);
    add(w, "p", p.functions.length ? "Contains: " + p.functions.join("; ") : p.no_ingredients ? "No ingredient list added, so I can’t check it." : "No known ingredients recognised.", "mu");
    p.flags.forEach(f => add(w, "p", f, "err")); const b = add(w, "button", "Remove", "alt"); b.onclick = async () => { await api("/api/consumer/products/" + p.id, {method: "DELETE"}); loadProducts(); loadHome(); }; });
  d.notes.forEach(n => add(nb, "p", n)); }
$("#pa").onclick = async () => { try { await api("/api/consumer/products", {body: {name: $("#pn").value, category: $("#pc").value, ingredients: $("#pl").value, slot: $("#ps").value}}); $("#pn").value = ""; $("#pl").value = ""; $("#pam").textContent = "Added."; loadProducts(); loadHome(); } catch (x) { $("#pam").textContent = x.message; } };
$("#ag").onclick = async () => { try { $("#aa").textContent = (await api("/api/consumer/ask", {body: {q: $("#aq").value}})).answer; } catch (x) { $("#aa").textContent = x.message; } };
async function loadAlerts() { const a = await api("/api/consumer/alerts"), box = $("#al"); box.replaceChildren();
  a.forEach(x => { const w = add(box, "div", "", "box notice"); add(w, "b", x.title); add(w, "p", x.body); const b = add(w, "button", "Dismiss", "alt"); b.onclick = async () => { await api("/api/consumer/alerts/" + x.id + "/read", {body: {}}); loadAlerts(); }; }); }

async function shrink(file, max = 1280) { const b = await createImageBitmap(file), s = Math.min(1, max / Math.max(b.width, b.height)), c = document.createElement("canvas"); c.width = Math.round(b.width * s); c.height = Math.round(b.height * s); c.getContext("2d").drawImage(b, 0, 0, c.width, c.height); return c.toDataURL("image/jpeg", .85); }
function fill(d) { if (d.name) $("#pn").value = d.name; if (d.category) $("#pc").value = d.category; $("#pl").value = d.ingredients || ""; $("#sm").textContent = (d.source || d.note || "") + " Review the fields below, then press Add product."; }
async function lookup() { try { fill(await api("/api/consumer/barcode/" + encodeURIComponent($("#bc").value.trim()))); } catch (x) { $("#sm").textContent = x.message; } }
$("#bl").onclick = lookup;
$("#bs").onclick = async () => { if (!("BarcodeDetector" in window)) { $("#sm").textContent = "Camera barcode scanning isn’t supported in this browser. Type the number instead."; return; }
  try { const det = new BarcodeDetector({formats: ["ean_13", "ean_8", "upc_a", "upc_e"]}), v = $("#bv"), st = await navigator.mediaDevices.getUserMedia({video: {facingMode: "environment"}}); v.srcObject = st; v.hidden = false; await v.play();
    const t = setInterval(async () => { const r = await det.detect(v).catch(() => []); if (r.length) { clearInterval(t); st.getTracks().forEach(x => x.stop()); v.hidden = true; $("#bc").value = r[0].rawValue; lookup(); } }, 400); } catch (x) { $("#sm").textContent = "Couldn’t open the camera. Type the number instead."; } };
$("#lf").onchange = async () => { const f = $("#lf").files[0]; if (!f) return; if (!$("#lag").checked) { $("#sm").textContent = "Tick the agreement above first, then choose the photo again."; $("#lf").value = ""; return; }
  $("#sm").textContent = "Reading the label…"; try { fill(await api("/api/consumer/label", {body: {image: await shrink(f), consent_image: true}})); } catch (x) { $("#sm").textContent = x.message; } $("#lf").value = ""; };
const u8 = k => Uint8Array.from(atob(k.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(k.length / 4) * 4, "=")), c => c.charCodeAt(0));
$("#pn2").onclick = async () => { try { const {key} = await api("/api/consumer/push/key");
  if (!key || !("serviceWorker" in navigator) || !("PushManager" in window)) { $("#pnm").textContent = "Push isn’t available here (not set up on the server or not supported by this browser)."; return; }
  const reg = await navigator.serviceWorker.register("/sw.js"); if (await Notification.requestPermission() != "granted") { $("#pnm").textContent = "Notifications were not allowed."; return; }
  const sub = await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: u8(key)}); await api("/api/consumer/push/subscribe", {body: sub.toJSON()}); $("#pnm").textContent = "Push notifications are on for this device."; } catch (x) { $("#pnm").textContent = x.message; } };
