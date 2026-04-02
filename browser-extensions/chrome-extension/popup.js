const OAUTH_DOMAINS = [
  "na.id.mazda.com",
  "eu.id.mazda.com",
  "ap.id.mazda.com",
  "au.id.mazda.com",
];

document.getElementById("clear-cookies").addEventListener("click", () => {
  const statusEl = document.getElementById("clear-status");
  statusEl.textContent = "Clearing…";

  const getAllPromises = OAUTH_DOMAINS.map(
    (domain) =>
      new Promise((resolve) =>
        chrome.cookies.getAll({ domain }, (cookies) => resolve(cookies))
      )
  );

  Promise.all(getAllPromises).then((results) => {
    const allCookies = results.flat();

    if (!allCookies.length) {
      statusEl.textContent = "No Mazda cookies found.";
      return;
    }

    let removed = 0;
    allCookies.forEach((cookie) => {
      const url =
        "http" +
        (cookie.secure ? "s" : "") +
        "://" +
        cookie.domain.replace(/^\./, "") +
        cookie.path;
      chrome.cookies.remove({ url, name: cookie.name }, () => {
        removed++;
        if (removed === allCookies.length) {
          statusEl.textContent = `Cleared ${removed} cookie${removed !== 1 ? "s" : ""}. Ready for fresh login.`;
        }
      });
    });
  });
});
