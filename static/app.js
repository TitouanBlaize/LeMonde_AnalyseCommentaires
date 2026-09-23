const $ = (id) => document.getElementById(id);

const els = {
  generate: $("generate"),
  loadLatest: $("load-latest"),
  count: $("count"),
  singleForm: $("single-form"),
  url: $("article-url"),
  summarize: $("summarize"),
  digestComments: $("digest-comments"),
  singleComments: $("single-comments"),
  progress: $("progress"),
  current: $("progress-current"),
  fill: $("progress-fill"),
  log: $("log"),
  banner: $("banner"),
  overview: $("overview"),
  articles: $("articles"),
  empty: $("empty"),
  meta: $("meta"),
};

let source = null;

function log(message, isError = false) {
  const li = document.createElement("li");
  li.textContent = message;
  if (isError) li.className = "error";
  els.log.appendChild(li);
  els.log.scrollTop = els.log.scrollHeight;
}

function showBanner(message, ok = false) {
  els.banner.textContent = message;
  els.banner.className = ok ? "banner ok" : "banner";
  els.banner.hidden = false;
}

function reset() {
  els.articles.innerHTML = "";
  els.overview.hidden = true;
  els.overview.innerHTML = "";
  els.banner.hidden = true;
  els.log.innerHTML = "";
  els.empty.hidden = true;
  els.meta.textContent = "";
  els.fill.style.width = "0%";
  els.progress.hidden = false;
  els.current.textContent = "Démarrage…";
}

function stop() {
  if (source) {
    source.close();
    source = null;
  }
  els.generate.disabled = false;
  els.summarize.disabled = false;
  els.progress.hidden = true;
}

function list(items) {
  if (!items || !items.length) return "";
  return `<ul>${items.map((i) => `<li>${md(i)}</li>`).join("")}</ul>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// Markdown « en ligne » produit par le modèle : gras, italique, code.
// Le texte est échappé d'abord, donc aucun HTML brut ne passe.
function md(value) {
  return escapeHtml(value)
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*(?!\s)([^*\n]+?)(?<!\s)\*\*/g, "<strong>$1</strong>")
    .replace(/__(?!\s)([^_\n]+?)(?<!\s)__/g, "<strong>$1</strong>")
    .replace(/\*(?!\s)([^*\n]+?)(?<!\s)\*/g, "<em>$1</em>")
    .replace(/(^|[^\w])_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)/g, "$1<em>$2</em>")
    .replace(/\n/g, "<br>");
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function renderComments(c) {
  if (!c || (!c.synthese && !(c.themes || []).length)) return "";

  const themes = (c.themes || [])
    .map((t) => `<li><b>${md(t.theme)}</b>${t.occurrences ? ` · ${escapeHtml(t.occurrences)}` : ""}</li>`)
    .join("");

  return `
    <div class="comments">
      <h3>Ce qu'en disent les lecteurs</h3>
      ${c.synthese ? `<p>${md(c.synthese)}</p>` : ""}
      ${c.tonalite ? `<p class="angle">Tonalité : ${md(c.tonalite)}</p>` : ""}
      ${themes ? `<ul class="themes">${themes}</ul>` : ""}
      ${c.clivages && c.clivages.length ? `<h3>Points de désaccord</h3>${list(c.clivages)}` : ""}
    </div>`;
}

function renderArticle(item) {
  const a = item.analysis || {};
  const card = document.createElement("article");
  card.className = "card";

  const tags = [`<span class="tag">${escapeHtml(item.rubrique || "Le Monde")}</span>`];
  if (item.published) tags.push(`<span>${escapeHtml(formatDate(item.published))}</span>`);
  if (item.author) tags.push(`<span>${escapeHtml(item.author)}</span>`);
  if (item.paywalled) tags.push(`<span class="tag tag--muted">extrait gratuit</span>`);
  if (item.nb_comments) {
    tags.push(`<span class="tag tag--muted">${item.nb_comments} commentaires</span>`);
  }

  card.innerHTML = `
    <div class="card__meta">${tags.join("")}</div>
    <h2><a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a></h2>
    <p>${md(a.resume)}</p>
    ${list(a.points_cles)}
    ${a.angle ? `<p class="angle">${md(a.angle)}</p>` : ""}
    ${renderComments(a.commentaires)}`;

  els.articles.appendChild(card);
}

function renderMeta(digest) {
  const parts = [
    `Généré le ${formatDate(digest.generated_at)}`,
    `${digest.articles.length} article${digest.articles.length > 1 ? "s" : ""}`,
    `${digest.duration_s}s`,
  ];
  if (digest.with_comments) parts.push("commentaires analysés");
  els.meta.textContent = parts.join(" · ");
}

function renderOverview(digest) {
  if (digest.single) {
    els.overview.hidden = true;
    renderMeta(digest);
    return;
  }

  const o = digest.overview || {};
  els.overview.innerHTML = `
    <h2>${md(o.titre || "Revue de presse du jour")}</h2>
    <p>${md(o.synthese)}</p>
    ${o.a_retenir && o.a_retenir.length ? `<h3>À retenir</h3>${list(o.a_retenir)}` : ""}
    ${o.tendances && o.tendances.length ? `<h3>Fils rouges</h3>${list(o.tendances)}` : ""}`;
  els.overview.hidden = false;
  renderMeta(digest);
}

function run(endpoint, params) {
  reset();
  els.generate.disabled = true;
  els.summarize.disabled = true;

  source = new EventSource(`${endpoint}?${params}`);

  source.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "status") {
      els.current.textContent = data.message;
      log(data.message);
      if (data.step === "login_failed") showBanner(data.message);
      if (data.step === "login_done") showBanner(data.message, true);
      if (data.index && data.total) {
        els.fill.style.width = `${Math.round((data.index / data.total) * 95)}%`;
      }
    } else if (data.type === "article") {
      renderArticle(data.data);
    } else if (data.type === "error") {
      log(data.message, true);
      showBanner(data.message);
      if (data.fatal) stop();
    } else if (data.type === "done") {
      els.fill.style.width = "100%";
      renderOverview(data.data);
      const target = data.data.single ? els.articles : els.overview;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      stop();
    }
  };

  source.onerror = () => {
    if (!source) return;
    log("Connexion au serveur interrompue.", true);
    stop();
  };
}

async function loadLatest() {
  const response = await fetch("/api/latest");
  if (!response.ok) {
    showBanner("Aucun résumé enregistré pour l'instant.");
    return;
  }
  const { digest } = await response.json();
  els.articles.innerHTML = "";
  els.empty.hidden = true;
  els.banner.hidden = true;
  digest.articles.forEach(renderArticle);
  renderOverview(digest);
}

function startDigest() {
  run(
    "/api/digest/stream",
    new URLSearchParams({
      count: els.count.value || "10",
      comments: els.digestComments.checked ? "1" : "0",
    })
  );
}

function startSingle(event) {
  event.preventDefault();
  const url = els.url.value.trim();
  if (!url) return;
  run(
    "/api/article/stream",
    new URLSearchParams({ url, comments: els.singleComments.checked ? "1" : "0" })
  );
}

els.generate.addEventListener("click", startDigest);
els.singleForm.addEventListener("submit", startSingle);
els.loadLatest.addEventListener("click", loadLatest);
