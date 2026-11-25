document.querySelectorAll("[data-game-cover]").forEach((image) => {
  image.addEventListener(
    "error",
    () => {
      image.hidden = true;
    },
    { once: true },
  );
});
