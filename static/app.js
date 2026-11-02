// Gravity Fitness Club admin – small helpers (no framework).

document.addEventListener("click", (e) => {
  // Open a <dialog> bottom sheet: <button data-open="dialog-id">
  const opener = e.target.closest("[data-open]");
  if (opener) document.getElementById(opener.dataset.open)?.showModal();

  // Tap on the dark backdrop (or a close button) closes the sheet
  if (e.target.tagName === "DIALOG") e.target.close();
  if (e.target.closest("[data-close-dialog]")) e.target.closest("dialog")?.close();

  // Close flash message
  if (e.target.closest("[data-close-flash]")) e.target.closest("[data-flash]").remove();

  // "Send on WhatsApp": the link opens WhatsApp as usual; we only log the send in the background
  const send = e.target.closest("a[data-sent-url]");
  if (send) logReminderSent(send);

  // Desktop reminders: click a row to preview its WhatsApp message
  const row = e.target.closest("[data-preview-row]");
  if (row && !e.target.closest("a, button")) selectPreviewRow(row);

  // Show / hide password
  const toggle = e.target.closest("[data-toggle-password]");
  if (toggle) {
    const input = document.getElementById(toggle.dataset.togglePassword);
    input.type = input.type === "password" ? "text" : "password";
    toggle.setAttribute("aria-label", input.type === "password" ? "Show password" : "Hide password");
  }
});

// ---------- payment reminders ----------

function logReminderSent(link) {
  const id = link.dataset.sentFor;
  const wasSent = link.classList.contains("btn-sent");
  // keepalive: the request still finishes while the phone switches to WhatsApp
  fetch(link.dataset.sentUrl, { method: "POST", keepalive: true, credentials: "same-origin" })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((data) => {
      document.querySelectorAll(`[data-sent-for="${id}"]`).forEach((btn) => {
        btn.classList.replace("btn-wa", "btn-sent");
        btn.querySelector("[data-sent-text]").textContent = "Sent · Resend";
      });
      document.querySelectorAll(`[data-sent-label="${id}"]`).forEach((el) => (el.textContent = data.label));
      const counter = document.querySelector("[data-sent-count]");
      if (counter && !wasSent) counter.textContent = Number(counter.textContent) + 1;
    })
    .catch(() => {}); // WhatsApp still opened; the log just was not saved
}

function selectPreviewRow(row) {
  row.parentElement.querySelectorAll("[data-preview-row]").forEach((r) => {
    r.classList.remove("bg-zinc-50");
    r.removeAttribute("aria-selected");
  });
  row.classList.add("bg-zinc-50");
  row.setAttribute("aria-selected", "true");
  document.querySelector("[data-preview-text]").textContent = row.dataset.message;
  document.querySelector("[data-preview-name]").textContent = row.dataset.name;
}

// ---------- package form: end-date preview + fee (server recalculates on save) ----------

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Same rule as end_date() in utils.py: 1 Oct + 1 month -> 31 Oct, 31 Oct + 1 month -> 30 Nov
function packageEndDate(start, months) {
  const m = start.getMonth() + months;
  const year = start.getFullYear() + Math.floor(m / 12);
  const month = m % 12;
  const lastDay = new Date(year, month + 1, 0).getDate();
  if (start.getDate() > lastDay) return new Date(year, month, lastDay);
  return new Date(year, month, start.getDate() - 1);
}

function formatDate(d) {
  return String(d.getDate()).padStart(2, "0") + " " + MONTHS[d.getMonth()] + " " + d.getFullYear();
}

function formatRupees(value) {
  return "₹" + (parseInt(value, 10) || 0).toLocaleString("en-IN");
}

function updatePackageForm(form, fillFee) {
  const pkg = form.querySelector("input[name=package_id]:checked");
  // register form has a start date input; renew form gets its start from the server
  const startText = form.querySelector("[name=start_date]")?.value ?? form.dataset.start;
  const fee = form.querySelector("[data-fee-input]");
  if (pkg && fillFee && fee) fee.value = pkg.dataset.price;
  form.querySelectorAll("[data-package-name]").forEach((el) => (el.textContent = pkg ? pkg.dataset.name : ""));
  form.querySelectorAll("[data-fee-display]").forEach((el) => (el.textContent = formatRupees(fee?.value)));
  let end = "";
  if (pkg && /^\d{4}-\d{2}-\d{2}$/.test(startText || "")) {
    const [y, m, d] = startText.split("-").map(Number);
    end = formatDate(packageEndDate(new Date(y, m - 1, d), Number(pkg.dataset.months)));
  }
  form.querySelectorAll("[data-end-date]").forEach((el) => (el.textContent = end || "—"));
}

document.addEventListener("change", (e) => {
  const form = e.target.closest("[data-package-form]");
  if (form && ["package_id", "start_date"].includes(e.target.name)) {
    updatePackageForm(form, e.target.name === "package_id");
  }

  // Photo preview before upload
  if (e.target.matches("[data-photo-input]")) {
    const file = e.target.files[0];
    const img = e.target.closest("label").querySelector("[data-photo-preview]");
    if (file && img) {
      img.src = URL.createObjectURL(file);
      img.classList.remove("hidden");
    }
    if (file && file.size > PHOTO_MAX_BYTES) shrinkPhoto(e.target, file);
  }
});

// ---------- member photo: phone camera photos are often 3–6 MB, server allows < 2 MB ----------

const PHOTO_MAX_BYTES = 2 * 1024 * 1024;
const PHOTO_MAX_SIDE = 1200;

// Re-draw a big photo as a smaller JPEG and put it back into the file input
function shrinkPhoto(input, file) {
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(1, PHOTO_MAX_SIDE / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob || typeof DataTransfer === "undefined") return; // server will show the size error
      const files = new DataTransfer();
      files.items.add(new File([blob], "photo.jpg", { type: "image/jpeg" }));
      input.files = files.files;
    }, "image/jpeg", 0.85);
    URL.revokeObjectURL(img.src);
  };
  img.src = URL.createObjectURL(file);
}

document.addEventListener("input", (e) => {
  const form = e.target.closest("[data-package-form]");
  if (form && e.target.matches("[data-fee-input], [name=start_date]")) updatePackageForm(form, false);
});

function renewSummary(form) {
  const text = (sel) => form.querySelector(sel)?.textContent.trim();
  return "New period: " + text("[data-start-date]") + " – " + text("[data-end-date]") + ", " +
    formatRupees(form.querySelector("[data-fee-input]").value) + ", " + form.querySelector("[name=mode]").value;
}

// Stop double taps creating two members / payments
document.addEventListener("submit", (e) => {
  const form = e.target;
  // e.g. <form data-confirm="Delete Priya?"> (staff block / delete)
  if (form.dataset.confirm && !confirm(form.dataset.confirm)) return e.preventDefault();
  if (!form.matches("[data-submit-once]")) return;
  if (form.dataset.sending) return e.preventDefault();
  if (form.matches("[data-renew-form]") && !confirm(renewSummary(form) + "\n\nSave this payment?")) {
    return e.preventDefault();
  }
  form.dataset.sending = "1";
  form.querySelectorAll("button:not([type=button])").forEach((b) => {
    b.disabled = true;
    b.textContent = "Saving…";
  });
});

// Back/forward cache: re-enable buttons when the page is shown again
window.addEventListener("pageshow", (e) => {
  if (e.persisted && document.querySelector("form[data-sending]")) location.reload();
});

document.addEventListener("DOMContentLoaded", () => {
  // Flash message hides itself after 4 seconds
  const flash = document.querySelector("[data-flash]");
  if (flash) setTimeout(() => flash.remove(), 4000);

  document.querySelectorAll("[data-package-form]").forEach((form) => updatePackageForm(form, false));

  // e.g. renew sheet re-opened with errors, or opened from "Mark paid"
  document.querySelector("dialog[data-autoopen]")?.showModal();
});
