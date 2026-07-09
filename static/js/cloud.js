const PROVIDER_BLURBS = {
  google_drive: "Create folders, upload files, and share with Google sign-in.",
  dropbox: "Sync folders and files with your Dropbox account.",
  onedrive: "Microsoft OneDrive and personal cloud storage.",
  cloud_link: "Paste any existing folder link for QR sharing only.",
};

const PROVIDER_CONSOLE = {
  google_drive: "https://console.cloud.google.com/apis/credentials",
  dropbox: "https://www.dropbox.com/developers/apps",
  onedrive: "https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps",
};

function updateProviderUi(select) {
  if (!select) return;
  const id = select.value;
  const blurb = document.getElementById("provider-blurb");
  if (blurb && PROVIDER_BLURBS[id]) blurb.textContent = PROVIDER_BLURBS[id];

  const oauthSetup = document.getElementById("oauth-setup");
  if (oauthSetup) {
    oauthSetup.style.display = id === "cloud_link" ? "none" : "grid";
  }

  const devLink = document.getElementById("dev-console-link");
  if (devLink && PROVIDER_CONSOLE[id]) {
    devLink.href = PROVIDER_CONSOLE[id];
    devLink.style.display = "inline";
  } else if (devLink) {
    devLink.style.display = "none";
  }
}

document.querySelectorAll("#cloud-provider-select, #settings-provider-select").forEach((select) => {
  updateProviderUi(select);
  select.addEventListener("change", () => updateProviderUi(select));
});
