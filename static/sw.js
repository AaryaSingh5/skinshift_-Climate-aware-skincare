self.addEventListener("push", e => { const d = e.data ? e.data.json() : {}; e.waitUntil(self.registration.showNotification(d.title || "SKINSHIFT", {body: d.body || "You have a new suggestion.", tag: "skinshift"})); });
self.addEventListener("notificationclick", e => { e.notification.close(); e.waitUntil(clients.openWindow("/app")); });
