(function () {
  const banner = document.getElementById("update-banner");
  if (!banner) return;

  const version = banner.dataset.version;
  const storageKey = `qrfileshare_dismissed_update_${version}`;
  if (localStorage.getItem(storageKey) === "1") {
    banner.hidden = true;
    return;
  }

  const dismissButton = document.getElementById("dismiss-update");
  if (!dismissButton) return;

  dismissButton.addEventListener("click", () => {
    localStorage.setItem(storageKey, "1");
    banner.hidden = true;
  });
})();
