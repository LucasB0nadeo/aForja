(() => {
  document.querySelectorAll("[data-steam-game-search]").forEach((input) => {
    const form = input.closest("form");
    const appIdInput = form.querySelector('input[name="steam_app_id"]');
    const results = form.querySelector("[data-steam-search-results]");
    const status = form.querySelector("[data-steam-search-status]");
    let timer;
    let requestId = 0;

    input.addEventListener("input", () => {
      appIdInput.value = "";
      results.replaceChildren();
      const currentRequestId = ++requestId;
      const query = input.value.trim();
      window.clearTimeout(timer);

      if (query.length < 2) {
        status.textContent = query ? "Digite pelo menos 2 caracteres." : "";
        return;
      }

      timer = window.setTimeout(async () => {
        status.textContent = "Buscando jogos na Steam...";
        try {
          const response = await fetch(
            `${input.dataset.searchUrl}?q=${encodeURIComponent(query)}`,
            { headers: { Accept: "application/json" } },
          );
          const payload = await response.json();
          if (currentRequestId !== requestId) {
            return;
          }
          if (!response.ok) {
            throw new Error(payload.error || "Não foi possível buscar jogos.");
          }

          if (payload.results.length === 0) {
            status.textContent = "Nenhum jogo encontrado.";
            return;
          }

          status.textContent = "Escolha o jogo correto:";
          payload.results.forEach((game) => {
            const option = document.createElement("button");
            option.type = "button";
            option.className = "game-search-option";
            option.setAttribute("role", "option");
            option.textContent = `${game.name} (AppID ${game.steam_app_id})`;
            option.addEventListener("click", () => {
              input.value = game.name;
              appIdInput.value = String(game.steam_app_id);
              results.replaceChildren();
              status.textContent = `Jogo selecionado: ${game.name}`;
            });
            results.append(option);
          });
        } catch (error) {
          if (currentRequestId === requestId) {
            status.textContent = error.message;
          }
        }
      }, 300);
    });
  });
})();
