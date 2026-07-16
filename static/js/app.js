function assignFilesToInput(input, fileList) {
  const transfer = new DataTransfer();
  Array.from(fileList).forEach((file) => transfer.items.add(file));
  input.files = transfer.files;
}

function updateDropzoneLabel(label, files) {
  const span = label.querySelector("span");
  if (!span) return;
  if (!files?.length) {
    span.textContent = "or click to browse";
    return;
  }
  const names = Array.from(files)
    .map((file) => file.name)
    .slice(0, 3)
    .join(", ");
  span.textContent = `${files.length} file(s) ready: ${names}`;
}

function setDropzoneStatus(zone, message, isError = false) {
  let status = zone.querySelector(".dropzone-status");
  if (!status) {
    status = document.createElement("p");
    status.className = "dropzone-status muted small";
    zone.appendChild(status);
  }
  status.textContent = message;
  status.classList.toggle("error", isError);
}

document.querySelectorAll(".dropzone").forEach((zone) => {
  const form = zone;
  const input = zone.querySelector('input[type="file"]');
  const label = zone.querySelector(".dropzone-inner");
  if (!input || !label) return;

  const handleFiles = (files, autoUpload = false) => {
    if (!files?.length) return;
    assignFilesToInput(input, files);
    updateDropzoneLabel(label, input.files);
    setDropzoneStatus(zone, `${input.files.length} file(s) selected.`);
    if (autoUpload) {
      setDropzoneStatus(zone, "Uploading...");
      form.requestSubmit();
    }
  };

  ["dragenter", "dragover"].forEach((eventName) => {
    zone.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "copy";
      }
      zone.classList.add("dragover");
    });
  });

  zone.addEventListener("dragleave", (event) => {
    event.preventDefault();
    if (zone.contains(event.relatedTarget)) return;
    zone.classList.remove("dragover");
  });

  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    zone.classList.remove("dragover");
    const files = event.dataTransfer?.files;
    if (!files?.length) {
      setDropzoneStatus(zone, "No files detected in drop. Try Browse files instead.", true);
      return;
    }
    handleFiles(files, true);
  });

  input.addEventListener("change", () => {
    if (!input.files?.length) return;
    updateDropzoneLabel(label, input.files);
    setDropzoneStatus(zone, `${input.files.length} file(s) selected. Click Upload to sync.`);
  });

  form.addEventListener("submit", () => {
    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.disabled = true;
      button.textContent = "Uploading...";
    }
  });

  const browseBtn = zone.querySelector(".browse-files-btn");
  const dropTarget = zone.querySelector(".drop-target");
  if (browseBtn) {
    browseBtn.addEventListener("click", () => input.click());
  }
  if (dropTarget) {
    dropTarget.addEventListener("click", () => input.click());
  }
});

function initFileDeleteControls() {
  const bulkForm = document.getElementById("bulk-delete-files-form");
  const selectAll = document.getElementById("select-all-files");
  const bulkButton = document.getElementById("bulk-delete-files-btn");
  if (!bulkForm || !selectAll || !bulkButton) return;

  const checkboxes = () =>
    Array.from(document.querySelectorAll('input[name="file_ids"][form="bulk-delete-files-form"]'));

  const syncBulkState = () => {
    const boxes = checkboxes();
    const selected = boxes.filter((box) => box.checked);
    bulkButton.disabled = selected.length === 0;
    selectAll.indeterminate =
      selected.length > 0 && selected.length < boxes.length;
    selectAll.checked = boxes.length > 0 && selected.length === boxes.length;
  };

  selectAll.addEventListener("change", () => {
    checkboxes().forEach((box) => {
      box.checked = selectAll.checked;
    });
    syncBulkState();
  });

  checkboxes().forEach((box) => {
    box.addEventListener("change", syncBulkState);
  });

  syncBulkState();
}

initFileDeleteControls();

(function initQrAssetControls() {
  const borderStyle = document.getElementById("border-style");
  const borderWrap = document.getElementById("border-upload-wrap");
  const borderInput = document.getElementById("border-png");
  if (!borderStyle || !borderWrap) return;

  const syncBorderUpload = () => {
    const custom = borderStyle.value === "custom";
    borderWrap.hidden = !custom;
    if (borderInput) {
      borderInput.required = custom;
      if (!custom) borderInput.value = "";
    }
  };

  borderStyle.addEventListener("change", syncBorderUpload);
  syncBorderUpload();
})();
