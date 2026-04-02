document.addEventListener("DOMContentLoaded", () => {
  const btn    = document.getElementById("clearBtn");
  const status = document.getElementById("clearStatus");

  btn.addEventListener("click", handleClear);

  async function handleClear() {
    btn.disabled = true;
    setStatus("working", "Working…");

    const lines = [];
    let anySuccess = false;

    // ── Path 1: browser.cookies with storeId workaround (Safari 18 bug fix) ──
    // Safari 18 regression: browser.cookies.getAll() always returns empty unless
    // an explicit storeId is passed. We call getAllCookieStores() first and then
    // pass each store's .id into every getAll() and remove() call.
    try {
      const cApi = (typeof browser !== "undefined" && browser.cookies)
        ? browser.cookies
        : (typeof chrome !== "undefined" && chrome.cookies ? chrome.cookies : null);

      if (cApi && cApi.getAllCookieStores) {
        const stores = await bPromise(cb => cApi.getAllCookieStores(cb));

        const mazdaDomains = ["mazda.com"];
        const mazdaUrls    = [
          "https://na.id.mazda.com/",
          "https://eu.id.mazda.com",
          "https://ap.id.mazda.com",
          "https://au.id.mazda.com",
          "https://id.mazda.com/",
          "https://www.mazda.com/",
          "https://mazda.com/",
        ];

        let allCookies = [];
        for (const store of (stores || [])) {
          const domainResults = await Promise.all(
            mazdaDomains.flatMap(d => [
              bPromise(cb => cApi.getAll({ domain: d,      storeId: store.id }, cb)),
              bPromise(cb => cApi.getAll({ domain: `.${d}`, storeId: store.id }, cb)),
            ])
          );
          const urlResults = await Promise.all(
            mazdaUrls.map(url => bPromise(cb => cApi.getAll({ url, storeId: store.id }, cb)))
          );
          allCookies.push(...domainResults.flat(), ...urlResults.flat());
        }

        // Deduplicate by storeId + domain + name + path
        const seen = new Set();
        allCookies = allCookies.filter(c => {
          const key = `${c.storeId}|${c.domain}|${c.name}|${c.path}`;
          return seen.has(key) ? false : (seen.add(key), true);
        });

        if (allCookies.length > 0) {
          let removed = 0;
          for (const c of allCookies) {
            const scheme = c.secure ? "https" : "http";
            const host   = c.domain.startsWith(".") ? c.domain.slice(1) : c.domain;
            try {
              await bPromise(cb => cApi.remove(
                { url: `${scheme}://${host}${c.path}`, name: c.name, storeId: c.storeId }, cb
              ));
              removed++;
            } catch (_) {}
          }
          lines.push(`Cleared ${removed}/${allCookies.length} cookie(s)`);
          if (removed > 0) anySuccess = true;
        } else {
          lines.push(`0 visible cookies found (${(stores || []).length} store(s) checked)`);
          // Not a failure — HttpOnly cookies are invisible to the JS API
          anySuccess = true;
        }
      } else {
        lines.push("cookies API unavailable");
      }
    } catch (e) {
      lines.push(`Error: ${e.message}`);
    }

    const icon = anySuccess ? "✓" : "✗";
    setStatus(anySuccess ? "success" : "error", `${icon} ${lines.join("  |  ")}`);
    btn.disabled = false;
  }

  function bPromise(fn) {
    return new Promise((resolve, reject) => {
      fn(result => {
        const err = typeof browser !== "undefined"
          ? null
          : (chrome.runtime && chrome.runtime.lastError);
        if (err) reject(new Error(err.message));
        else     resolve(result);
      });
    });
  }

  function setStatus(cls, text) {
    status.className     = cls;
    status.style.display = "block";
    status.textContent   = text;
  }
});
