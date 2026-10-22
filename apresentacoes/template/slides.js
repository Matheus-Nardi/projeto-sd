// =============================================================
// Navegação dos slides e preenchimento da capa.
// Teclas: → / espaço / PageDown avançam; ← / PageUp voltam;
// Home / End vão ao primeiro / último; F alterna tela cheia.
// O número do slide fica na URL (#3), então recarregar não perde a posição.
// =============================================================

(function () {
  const D = window.DADOS;
  const corpo = document.body;

  // ---- Capa e campos com data-dado="..." ------------------------
  document.querySelectorAll("[data-dado]").forEach((el) => {
    const chave = el.dataset.dado;
    if (chave === "integrantes") {
      el.innerHTML = D.integrantes.map((n) => `<li>${n}</li>`).join("");
    } else if (chave === "logo") {
      el.src = D.logo;
    } else if (chave === "entrega") {
      el.textContent = corpo.dataset.entrega;
    } else if (chave === "data") {
      el.textContent = `${D.local}, ${corpo.dataset.data}`;
    } else if (chave === "curso-linha") {
      el.textContent = `${D.curso} — ${D.disciplina} — ${D.periodo}, ${D.semestre}`;
    } else {
      el.textContent = D[chave];
    }
  });
  document.title = `${corpo.dataset.entrega} — ${D.disciplina}`;

  // ---- Escala: o slide tem 1280×720 e é ajustado à janela -------
  const palco = document.querySelector(".palco");
  function ajusta() {
    const s = Math.min(innerWidth / 1280, innerHeight / 720);
    palco.style.transform = `translate(-50%, -50%) scale(${s})`;
  }
  addEventListener("resize", ajusta);
  ajusta();

  // ---- Navegação ------------------------------------------------
  const slides = [...document.querySelectorAll(".slide")];
  const progresso = document.querySelector(".progresso");
  let atual = 0;

  slides.forEach((s, i) => {
    if (i === 0) return; // a capa não leva número
    const n = document.createElement("div");
    n.className = "numero";
    n.textContent = `${i + 1} / ${slides.length}`;
    s.appendChild(n);
  });

  function mostra(i) {
    atual = Math.max(0, Math.min(slides.length - 1, i));
    slides.forEach((s, j) => s.classList.toggle("ativo", j === atual));
    progresso.style.width = `${(atual / (slides.length - 1)) * 100}%`;
    history.replaceState(null, "", `#${atual + 1}`);
  }

  addEventListener("keydown", (e) => {
    if (["ArrowRight", " ", "PageDown", "Enter"].includes(e.key)) mostra(atual + 1);
    else if (["ArrowLeft", "PageUp", "Backspace"].includes(e.key)) mostra(atual - 1);
    else if (e.key === "Home") mostra(0);
    else if (e.key === "End") mostra(slides.length - 1);
    else if (e.key.toLowerCase() === "f") {
      document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
    } else return;
    e.preventDefault();
  });

  // Clique: metade direita avança, metade esquerda volta
  addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    mostra(atual + (e.clientX > innerWidth / 2 ? 1 : -1));
  });

  mostra((parseInt(location.hash.slice(1), 10) || 1) - 1);
})();
