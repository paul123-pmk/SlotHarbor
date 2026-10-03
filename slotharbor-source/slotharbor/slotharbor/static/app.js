"use strict";

function payloadFor(form) {
  const result = {};
  for (const control of form.elements) {
    if (!control.name || control.disabled) continue;
    const value = control.value;
    switch (control.dataset.type) {
      case "int": result[control.name] = Number(value); break;
      case "nullable-int": result[control.name] = value === "" ? null : Number(value); break;
      case "ints": result[control.name] = [...control.selectedOptions].map(o => Number(o.value)); break;
      case "bool": result[control.name] = control.type === "checkbox" ? control.checked : value === "true"; break;
      default: result[control.name] = value;
    }
  }
  return result;
}

for (const input of document.querySelectorAll("[data-request-key]")) {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  input.value = [...bytes].map(b => b.toString(16).padStart(2, "0")).join("");
}

for (const form of document.querySelectorAll("form[data-api]")) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;
    const error = form.querySelector(".form-error");
    const button = form.querySelector("button[type=submit], button:not([type])");
    const payload = payloadFor(form);
    error.textContent = "";
    if (button) button.disabled = true;
    form.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(form.dataset.api, {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content},
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok) {
        const fields = result.fields ? " " + result.fields.map(f => `${f.field}: ${f.message}`).join("; ") : "";
        throw new Error((result.error || "The request could not be completed.") + fields);
      }
      window.location.assign(result.redirect || form.dataset.redirect || window.location.pathname);
    } catch (failure) {
      error.textContent = failure.message || "Connection interrupted. Your request key is preserved; retry to check the result.";
      error.tabIndex = -1;
      error.focus();
    } finally {
      if (button) button.disabled = false;
      form.removeAttribute("aria-busy");
    }
  });
}
