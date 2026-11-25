(() => {
  document.querySelectorAll("[data-hltb-results]").forEach(async (container) => {
    try {
      const response = await fetch(container.dataset.hltbUrl, {
        headers: { Accept: "text/html" },
      });
      const html = await response.text();
      if (!response.ok && response.status !== 503) {
        throw new Error("Não foi possível buscar os tempos de conclusão.");
      }
      if (response.redirected) {
        throw new Error("Não foi possível buscar os tempos de conclusão.");
      }
      container.innerHTML = html;
    } catch {
      const status = document.createElement("p");
      status.className = "hltb-status";
      status.setAttribute("role", "status");
      status.textContent =
        "Não foi possível consultar o HowLongToBeat agora. Tente novamente mais tarde.";
      container.replaceChildren(status);
    } finally {
      container.setAttribute("aria-busy", "false");
    }
  });
})();
