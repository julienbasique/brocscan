"use strict";
/* BrocScan — logique d'interface. Aucune dépendance, fetch classique.

   Parcours :
   1. 1 à 3 photos du même objet (+ précisions optionnelles du vendeur),
   2. analyse locale (Gemma 4 via Ollama),
   3. résultat : estimation + pour chaque plateforme un TITRE et un TEXTE
      D'ANNONCE prêts à copier, le lien du formulaire de dépôt et le lien
      "ventes terminées" pour vérifier les prix. */

const $ = (id) => document.getElementById(id);
const elPhotoInput = $("photo-input");
const elDropzone = $("dropzone");
const elPreviews = $("previews");
const elHint = $("dropzone-hint");
const elContexte = $("contexte");
const elAnalyse = $("analyze-btn");
const elLoading = $("loading");
const elElapsed = $("elapsed");
const elResult = $("result");
const elHistorySection = $("history-section");
const elHistory = $("history");

const MAX_PHOTOS = 3;
let fichiers = [];        // File[] sélectionnées (max 3)
let annoncesCourantes = []; // [{nom, titre, description, url_vendre, url_recherche}]
let objetPhoto = null;    // URL de la photo 1 (aperçu du résultat)
let prixDernierScan = null;  // {min,max} : la fourchette du dernier scan

// Code d'accès (démo fermée par son propriétaire, optionnel) : demandé
// une seule fois par visiteur, mémorisé dans le navigateur.
let codeAcces = localStorage.getItem("brocscan_code") || "";
function enteteCode() {
  const h = {};
  if (codeAcces) h["x-code-acces"] = codeAcces;
  return h;
}
function codeRejete(contexte) {
  localStorage.removeItem("brocscan_code");
  codeAcces = (prompt((contexte || "") + "Quel est le code d'accès ?") || "").trim();
  if (codeAcces) localStorage.setItem("brocscan_code", codeAcces);
}
let modelePret = false;
let chrono = null;

function majBouton() {
  elAnalyse.disabled = !(fichiers.length > 0 && modelePret);
}

// ---------- Statut du modèle ----------
async function verifierStatut() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();
    modelePret = s.ollama_actif;
    if (s.code_requis && !codeAcces) {
      codeAcces = (prompt("Cette démonstration est protégée par un code d'accès. Quel est le code ?") || "").trim();
      if (codeAcces) localStorage.setItem("brocscan_code", codeAcces);
    }
    $("mode-badge").textContent = s.cloud ? "CLOUD + LOCAL" : "100% LOCAL";
    $("status-dot").className = "dot " + (s.ollama_actif ? "dot-ok" : "dot-bad");
    $("status-text").textContent = s.ollama_actif ? "modèle prêt" : "modèle absent";
    if (!s.ollama_actif) {
      $("status-text").textContent = "ollama pull " + s.modele + " requis";
    }
    majBouton();
  } catch {
    $("status-dot").className = "dot dot-bad";
    $("status-text").textContent = "serveur coupé";
  }
}

// ---------- Sélection / glisser-déposer (1 à 3 photos) ----------
function ajouterFichiers(liste) {
  const images = Array.from(liste).filter((f) => f.type.startsWith("image/"));
  for (const f of images) {
    if (fichiers.length >= MAX_PHOTOS) break;
    fichiers.push(f);
  }
  if (images.length > MAX_PHOTOS) {
    alert(MAX_PHOTOS + " photos maximum (même objet, angles différents).");
  }
  rendreApercus();
  majBouton();
}

function retirerFichier(index) {
  fichiers.splice(index, 1);
  rendreApercus();
  majBouton();
}

function rendreApercus() {
  elPreviews.innerHTML = fichiers
    .map(
      (f, i) => `<figure class="mini${i === 0 ? " mini-main" : ""}">
        <img src="${url(f)}" alt="">
        <button class="mini-del" title="Retirer" data-del="${i}">✕</button>
        <figcaption class="mini-tag mono-caption">${i === 0 ? "principale" : "angle " + i}</figcaption>
      </figure>`
    )
    .join("");
  elPreviews.classList.toggle("hidden", fichiers.length === 0);
  elHint.classList.toggle("hidden", fichiers.length > 0);
}

function url(fichier) {
  return URL.createObjectURL(fichier);
}

elPreviews.addEventListener("click", (e) => {
  const index = e.target.dataset.del;
  if (index !== undefined) retirerFichier(Number(index));
});

elDropzone.addEventListener("click", () => elPhotoInput.click());
elDropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") elPhotoInput.click();
});
elPhotoInput.addEventListener("change", () => {
  ajouterFichiers(elPhotoInput.files);
  elPhotoInput.value = "";   // permet de repartir de l'explorateur proprement
});
["dragover", "dragenter"].forEach((evt) =>
  elDropzone.addEventListener(evt, (e) => { e.preventDefault(); elDropzone.classList.add("drag"); })
);
["dragleave", "drop"].forEach((evt) =>
  elDropzone.addEventListener(evt, (e) => { e.preventDefault(); elDropzone.classList.remove("drag"); })
);
elDropzone.addEventListener("drop", (e) => ajouterFichiers(e.dataTransfer.files));

// ---------- Analyse ----------
elAnalyse.addEventListener("click", () => {
  if (fichiers.length === 0) return;
  if (elAnalyse.disabled) return;        // garde anti double-clic
  elAnalyse.disabled = true;
  elLoading.classList.remove("hidden");
  elResult.classList.add("hidden");
  const debut = Date.now();
  chrono = setInterval(() => {
    elElapsed.textContent = Math.round((Date.now() - debut) / 1000) + " s";
  }, 500);

  const donnees = new FormData();
  fichiers.forEach((f) => donnees.append("photos", f, f.name));
  donnees.append("contexte", elContexte.value.trim());

  fetch("/api/scan", { method: "POST", body: donnees, headers: enteteCode() })
    .then(async (r) => {
      if (r.status === 401) codeRejete("Code d'accès manquant ou faux. ");
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      return r.json();
    })
    .then(afficherResultat)
    .catch((e) => {
      clearInterval(chrono);
      elLoading.classList.add("hidden");
      alert("Analyse impossible : " + e.message);
    })
    .finally(() => {
      majBouton();
    });
});

// ---------- Copier (clipboard avec repli ancien navigateur) ----------
async function copier(texte, bouton) {
  const avant = bouton.textContent;
  try {
    await navigator.clipboard.writeText(texte);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = texte;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  bouton.textContent = "copié ✓";
  bouton.disabled = true;
  setTimeout(() => { bouton.textContent = avant; bouton.disabled = false; }, 1400);
}

// ---------- Résultat ----------
function badge(classe, texte) {
  return `<span class="badge ${classe}">${texte}</span>`;
}

function afficherResultat(data) {
  clearInterval(chrono);
  elLoading.classList.add("hidden");
  elResult.classList.remove("hidden");

  const i = data.identification;
  objetPhoto = data.photo;
  $("result-photo").src = data.photo;
  $("result-thumbs").innerHTML = (data.photos_extra || [])
    .map((p, n) => `<img class="thumb" src="${p}" data-src="${p}" alt="angle ${n + 2}" title="Voir en grand">`)
    .join("");
  $("result-thumbs").classList.toggle("hidden", !(data.photos_extra || []).length);

  $("result-title").textContent =
    [i.marque, i.modele || i.objet]
      .filter((p, n, liste) => p && liste.findIndex((q) => (q || "").toLowerCase() === (p || "").toLowerCase()) === n)
      .filter((p) => !(i.objet || "").toLowerCase().includes(p.toLowerCase()) || p === i.objet)
      .join(" ")
    || i.objet;
  $("result-descr").textContent = i.description || "";

  const texteVisible = (i.texte_visible || "").trim();
  const elTexte = $("result-texte");
  if (texteVisible) {
    elTexte.textContent = "sur l'objet : " + texteVisible;
    elTexte.classList.remove("hidden");
  } else {
    elTexte.classList.add("hidden");
  }

  // badges : fiabilité, catégorie, état, précisions du vendeur
  const fiab = Math.round((i.confiance || 0) * 100);
  const fiable = fiab >= 70;
  $("badges").innerHTML = [
    badge(fiable ? "badge-blue" : "", fiable ? `fiabilité ${fiab}%` : `confiance faible (${fiab}%)`),
    i.categorie ? badge("", i.categorie) : "",
    i.etat ? badge("", "état : " + i.etat) : "",
    i.rarete && i.rarete !== "commun" ? badge("badge-blue", i.rarete) : "",
    i.moteur ? badge("", "via " + i.moteur) : "",
    data.contexte ? badge("", "précision : « " + escapeHtml(data.contexte) + " »") : "",
  ].filter(Boolean).join("");

  // fourchette
  $("result-value").textContent = (i.valeur_min_eur === 0 && i.valeur_max_eur === 0)
    ? "—"
    : `${i.valeur_min_eur} – ${i.valeur_max_eur} €`;

  // mots-clés pour la recherche marché + reset du bloc prix réels
  motsClesDernierScan = i.mots_cles || [i.marque, i.objet].filter(Boolean).join(" ");
  prixDernierScan = { min: i.valeur_min_eur, max: i.valeur_max_eur };
  $("market-block").classList.add("hidden");
  $("market-ligne").textContent = "";
  $("market-details").innerHTML = "";

  // plateformes + annonces prêtes
  annoncesCourantes = data.plateformes || [];
  $("plateformes").innerHTML = annoncesCourantes
    .map(
      (p, n) => `<div class="plateforme">
        <div class="plateforme-head">
          <strong>${p.nom}</strong><span class="plateforme-conseil">${p.conseil}</span>
        </div>
        <div class="plateforme-boutons">
          <button class="btn-mini" data-copier-titre="${n}">Copier le titre</button>
          <button class="btn-mini" data-copier-desc="${n}">Copier la description</button>
          ${p.url_vendre ? `<a class="btn-mini btn-mini-go" href="${p.url_vendre}" target="_blank" rel="noopener">Ouvrir le formulaire ↗</a>` : ""}
          <a class="lien-prix" href="${p.url_recherche}" target="_blank" rel="noopener">prix réels ↗</a>
        </div>
      </div>`
    )
    .join("");

  elResult.scrollIntoView({ behavior: "smooth", block: "start" });
  chargerHistorique().catch(() => {});
}

// clic sur une miniature : la mettre en grand
$("result-thumbs").addEventListener("click", (e) => {
  const src = e.target.dataset && e.target.dataset.src;
  if (src) {
    $("result-photo").src = src;
  }
});

// boutons copier d'annonce
$("plateformes").addEventListener("click", (e) => {
  const bouton = e.target.closest("button");
  if (!bouton) return;
  const nT = bouton.dataset.copierTitre;
  const nD = bouton.dataset.copierDesc;
  if (nT !== undefined) {
    copier(annoncesCourantes[nT].titre, bouton);
  } else if (nD !== undefined) {
    const p = annoncesCourantes[nD];
    copier(p.titre + "\n\n" + p.description, bouton);
  }
});

// ---------- Marché réel (Vinted via Chrome, à la demande) ----------
let motsClesDernierScan = "";
$("market-btn").addEventListener("click", async () => {
  const bouton = $("market-btn");
  bouton.disabled = true;
  bouton.textContent = "Recherche du marché… (10-20 s)";
  const bloc = $("market-block");
  bloc.classList.remove("hidden");
  $("market-ligne").textContent = "";
  $("market-details").innerHTML = "";
  try {
    const q = encodeURIComponent(motsClesDernierScan || "dualsense");
    const p = (prixDernierScan && prixDernierScan.max > 0)
      ? `&v_min=${prixDernierScan.min}&v_max=${prixDernierScan.max}` : "";
    const r = await fetch("/api/marche?mots_cles=" + q + p, { headers: enteteCode() });
    const d = await r.json();
    if (r.status === 401) codeRejete("Code d'accès manquant ou faux. ");
    if (!d.ok) throw new Error(d.detail || d.erreur || "marché indisponible");
    $("market-ligne").textContent =
      `${d.nombre} annonces Vinted aujourd'hui — de ${d.min} € à ${d.max} €, médiane ${d.mediane} €` +
      (d.cache ? " (résultat récent)" : "");
    $("market-details").innerHTML =
      (d.prix_conseille
        ? `<div class="p-conseille">→ Prix conseillé : <strong>${d.prix_conseille} €</strong> — ${escapeHtml(d.ancrage || "")}</div>`
        : "")
      + (d.echantillon || [])
          .map((t) => `<div>· ${escapeHtml(t)}</div>`).join("");
  } catch (e) {
    $("market-ligne").textContent = "Marché indisponible : " + e.message;
  } finally {
    bouton.disabled = false;
    bouton.textContent = "Prix réels du marché (Vinted)";
  }
});

// ---------- Remise à zéro ----------
$("reset-btn").addEventListener("click", () => {
  fichiers = [];
  elPhotoInput.value = "";
  rendreApercus();
  elContexte.value = "";
  elAnalyse.disabled = true;
  elResult.classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

// ---------- Historique ----------
async function chargerHistorique() {
  const liste = await fetch("/api/scans").then((r) => r.json());
  elHistorySection.classList.toggle("hidden", liste.length === 0);
  elHistory.innerHTML = liste
    .map(
      (s) => `<div class="history-item" data-id="${s.id}">
        <img src="${s.photo}" alt="">
        <button class="history-delete" title="Supprimer" data-del="${s.id}">✕</button>
        <h3>${escapeHtml(s.objet || "objet inconnu")}</h3>
        <div class="val">${s.valeur_min_eur} – ${s.valeur_max_eur} €</div>
        <div class="date">${(s.created_at || "").slice(0, 16).replace("T", " ")}</div>
      </div>`
    )
    .join("");
}

elHistory.addEventListener("click", (e) => {
  const id = e.target.dataset.del;
  if (!id) return;
  if (confirm("Supprimer ce scan ?")) {
    fetch("/api/scans/" + id, { method: "DELETE" }).then(chargerHistorique);
  }
});

function escapeHtml(texte) {
  const div = document.createElement("div");
  div.textContent = texte;
  return div.innerHTML;
}

chargerHistorique().catch(() => {});
verifierStatut();
