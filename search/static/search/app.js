(() => {
  const form = document.getElementById("search-form");
  const server = document.getElementById("id_server");
  const mode = document.getElementById("id_mode");
  const scopes = JSON.parse(document.getElementById("server-scopes").textContent);
  function update() {
    document.getElementById("scope-label").textContent = scopes[server.value] || "Configured search directory";
    document.getElementById("query-hint").textContent = mode.value === "files"
      ? "Match filenames with fd. Plain text by default."
      : "Match text inside files. Plain text by default.";
  }
  server.addEventListener("change", update);
  mode.addEventListener("change", update);
  update();
  form.addEventListener("submit", () => {
    const button = document.getElementById("search-button");
    button.disabled = true;
    document.getElementById("button-label").textContent = "Searching…";
    document.getElementById("search-status").textContent = "Connecting over SSH. Large searches may take up to a minute.";
    form.setAttribute("aria-busy", "true");
  });
  // Restore controls if the browser returns to a cached form after navigation.
  window.addEventListener("pageshow", () => {
    document.getElementById("search-button").disabled = false;
    document.getElementById("button-label").textContent = "Search server";
    form.removeAttribute("aria-busy");
  });
})();
