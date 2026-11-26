const form = document.querySelector("#resume-form");
const message = document.querySelector("#form-message");
const submitButton = document.querySelector("#generate-button");
const settingsDialog = document.querySelector("#settings-dialog");
const fileNameInput = document.querySelector("#file-name-input");
const fileNameValue = document.querySelector("#file-name");
const chatPanel = document.querySelector("#chat-panel");
const chatLog = document.querySelector("#chat-messages");
const layoutPicker = document.querySelector("#layout-select");
const aiStorageKey = "nhyapu.ai-settings.v1";
let chatCacheKey = "nhyapu.chat-cache.uninitialized";
let undoCacheKey = "nhyapu.undo-cache.uninitialized";
let aiKeyPrefix = "nhyapu.ai-key.uninitialized.";

let currentResumeId = null;
let currentResume = null;
let layouts = [];
let conversation = [];
let selectedLayout = null;
let draftUndoStack = [];
let editorDirty = false;

function readLocalMap(key) {
  try { return JSON.parse(localStorage.getItem(key) || "{}"); }
  catch { return {}; }
}

function writeLocalMap(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); }
  catch { /* Keep the workspace usable if browser storage is unavailable or full. */ }
}

function parseSkillItems(value) {
  const values = Array.isArray(value) ? value : String(value || "").split(/[,;|\n]+/);
  return values.map((item) => clean(item).replace(/^[*•·\-]\s*/, "")).filter(Boolean);
}

function chatContextKey() { return currentResumeId || "new-layout"; }

function cacheConversation() {
  const cache = readLocalMap(chatCacheKey);
  cache[chatContextKey()] = conversation.slice(-100);
  writeLocalMap(chatCacheKey, cache);
}

function restoreConversation() {
  const cache = readLocalMap(chatCacheKey);
  conversation = Array.isArray(cache[chatContextKey()]) ? cache[chatContextKey()].slice(-100) : [];
  chatLog.replaceChildren();
  if (!conversation.length) {
    appendBubble("assistant", "Hi! I can polish your resume wording, adjust the format, or create new layout ideas. What would you like to change?");
  } else {
    conversation.forEach((item) => appendBubble(item.role, item.content));
  }
}

function undoStackFor(resumeId = currentResumeId) {
  const cache = readLocalMap(undoCacheKey);
  return resumeId ? (Array.isArray(cache[resumeId]) ? cache[resumeId] : []) : [];
}

function updateUndoButton() {
  const button = document.querySelector("#chat-undo");
  if (button) button.disabled = currentResumeId ? undoStackFor().length === 0 : draftUndoStack.length === 0;
}

function makeUndoSnapshot(resume, conversationLength = conversation.length) {
  if (!resume?.id || !resume?.structured_data) return null;
  return {
    structured_data: JSON.parse(JSON.stringify(resume.structured_data)),
    template_name: resume.template_name || "modern",
    style: JSON.parse(JSON.stringify(resume.style || {})),
    conversation_length: conversationLength,
  };
}

function resumeVersionKey(resume) {
  return JSON.stringify({ data: resume?.structured_data, template: resume?.template_name, style: resume?.style });
}

function saveUndoSnapshot(snapshot) {
  if (!currentResumeId || !snapshot) return;
  const cache = readLocalMap(undoCacheKey);
  const stack = Array.isArray(cache[currentResumeId]) ? cache[currentResumeId] : [];
  stack.push(snapshot);
  cache[currentResumeId] = stack.slice(-20);
  writeLocalMap(undoCacheKey, cache);
  updateUndoButton();
}

function isInlineContactRequest(text) {
  return /\b(one|same|single)\s+line\b|\binline\b/i.test(text)
    && /\b(link|contact|github|portfolio|linkedin|url)\b/i.test(text);
}

function applyInlineContactFormatLocally(messageText, contextText = messageText) {
  const baseLayout = layoutFromSelect() || selectedLayout || layouts[0];
  const priorLayout = selectedLayout ? JSON.parse(JSON.stringify(selectedLayout)) : null;
  const priorLinks = collectEntries("links-list", "link", ["label", "url"], ["label", "url"]);
  const priorLayoutId = layoutPicker.value;
  const conversationLength = conversation.length;
  draftUndoStack.push({ layout: priorLayout, layout_id: priorLayoutId, links: priorLinks, conversation_length: conversationLength });

  const githubUrl = contextText.match(/https?:\/\/(?:www\.)?github\.com\/[^\s,;]+/i)?.[0]?.replace(/[).\]}!?]+$/, "");
  if (githubUrl) {
    const links = priorLinks.length ? priorLinks : [];
    const existing = links.findIndex((link) => /github/i.test(link.label) || /github\.com/i.test(link.url));
    const githubLink = { label: "GitHub", url: githubUrl };
    if (existing >= 0) links[existing] = githubLink;
    else links.push(githubLink);
    setEntryValues("links-list", "link", "link-template", links, ["label", "url"]);
  }

  selectedLayout = {
    id: "custom", name: "Custom format",
    template_name: baseLayout?.template_name || "modern",
    style: { ...(baseLayout?.style || {}), contact_layout: "inline" },
  };
  if (![...layoutPicker.options].some((option) => option.value === "custom")) layoutPicker.add(new Option("Custom format", "custom"));
  layoutPicker.value = "custom";
  document.querySelector("#template-name").value = selectedLayout.template_name;
  refreshPreview();
  appendBubble("user", messageText);
  conversation.push({ role: "user", content: messageText });
  const reply = githubUrl
    ? "Done — the contact details and links are on one line. I updated the GitHub link and kept your other links."
    : "Done — I set the contact details and links to display on one line.";
  appendBubble("assistant", reply);
  conversation.push({ role: "assistant", content: reply });
  cacheConversation();
  updateUndoButton();
}

const clean = (value) => String(value ?? "").trim();
const valuesFor = (card, keys) => Object.fromEntries(keys.map((key) => [key, clean(card.querySelector(`[data-field="${key}"]`)?.value || "")]));
const collectEntries = (listId, kind, fields, required) =>
  [...document.querySelectorAll(`#${listId} [data-entry="${kind}"]`)]
    .map((card) => valuesFor(card, fields))
    .filter((item) => required.every((key) => item[key]));

function readAIStore() {
  try {
    const legacyKey = "forma.ai-settings.v1";
    const stored = JSON.parse(localStorage.getItem(aiStorageKey) || localStorage.getItem(legacyKey) || "{}");
    const activeProvider = stored.active_provider || stored.provider || "openai";
    const source = stored.providers || (stored.provider ? { [stored.provider]: stored } : {});
    const providers = Object.fromEntries(Object.entries(source).map(([provider, config]) => [provider, {
      model: typeof config?.model === "string" ? config.model.slice(0, 160) : "",
      cloud_authorized: Boolean(config?.cloud_authorized),
    }]));
    const safeStore = { active_provider: activeProvider, providers };
    localStorage.removeItem(legacyKey);
    localStorage.setItem(aiStorageKey, JSON.stringify(safeStore));
    return safeStore;
  } catch {
    return { active_provider: "openai", providers: {} };
  }
}

function readAISettings() {
  const store = readAIStore();
  const provider = store.active_provider;
  let api_key = "";
  try { api_key = sessionStorage.getItem(`${aiKeyPrefix}${provider}`) || ""; } catch { /* Key entry remains usable for the current request. */ }
  return { provider, model: "", cloud_authorized: false, ...(store.providers[provider] || {}), api_key };
}

function settingsFromForm() {
  return {
    provider: document.querySelector("#ai-provider").value,
    model: document.querySelector("#ai-model").value.trim(),
    cloud_authorized: document.querySelector("#cloud-consent").checked,
    api_key: document.querySelector("#ai-api-key").value.trim(),
  };
}

function applySettingsToForm() {
  const config = readAISettings();
  document.querySelector("#ai-provider").value = config.provider;
  document.querySelector("#ai-model").value = config.model;
  document.querySelector("#ai-api-key").value = config.api_key || "";
  document.querySelector("#cloud-consent").checked = Boolean(config.cloud_authorized);
  updateSettingsFields();
}

function saveAISettings(config) {
  const store = readAIStore();
  store.active_provider = config.provider;
  store.providers[config.provider] = {
    model: config.model,
    cloud_authorized: config.cloud_authorized,
  };
  localStorage.setItem(aiStorageKey, JSON.stringify(store));
  try {
    const keyName = `${aiKeyPrefix}${config.provider}`;
    if (config.api_key) sessionStorage.setItem(keyName, config.api_key);
    else sessionStorage.removeItem(keyName);
  } catch {
    if (config.api_key) throw new Error("This browser could not keep the key in tab storage.");
  }
}

function switchProvider(provider) {
  const store = readAIStore();
  store.active_provider = provider;
  try { localStorage.setItem(aiStorageKey, JSON.stringify(store)); } catch { /* Saving remains available below. */ }
  const config = readAISettings();
  document.querySelector("#ai-model").value = config.model;
  document.querySelector("#ai-api-key").value = config.api_key || "";
  document.querySelector("#cloud-consent").checked = Boolean(config.cloud_authorized);
  updateSettingsFields();
}

function updateSettingsFields() {
  const provider = document.querySelector("#ai-provider").value;
  const modelPlaceholders = {
    openai: "gpt-4o-mini", anthropic: "claude-3-5-haiku-20241022",
    google: "gemini-2.0-flash", groq: "openai/gpt-oss-20b",
    openrouter: "meta-llama/llama-3.1-70b-instruct", ollama: "llama3.1",
  };
  document.querySelector("#ai-model").placeholder = modelPlaceholders[provider] || "Provider default";
  document.querySelector("#cloud-consent-field").hidden = provider === "ollama";
  document.querySelector("#ai-key-field").hidden = provider === "ollama";
  const cloudAllowed = provider === "ollama" || document.querySelector("#cloud-consent").checked;
  document.querySelector("#test-ai").disabled = !cloudAllowed;
  document.querySelector("#save-ai").disabled = !cloudAllowed;
}

function showMessage(kind, title, detail = "") {
  message.className = `form-message ${kind}`;
  message.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = title;
  message.append(heading);
  if (detail) {
    const text = document.createElement("p");
    text.textContent = detail;
    message.append(text);
  }
  message.hidden = false;
  message.scrollIntoView({ behavior: "smooth", block: "center" });
}

function readableApiError(detail, fallback = "The request could not be completed.") {
  if (Array.isArray(detail)) {
    return detail.map((item) => {
      const field = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "settings";
      return `${field || "settings"}: ${item.msg || "invalid value"}`;
    }).join("; ") || fallback;
  }
  return typeof detail === "string" && detail ? detail : fallback;
}

function addDownloadLink(label, href, filename) {
  const link = document.createElement("a");
  link.href = href;
  link.textContent = label;
  if (filename) link.download = filename;
  return link;
}

function showResult(resume) {
  message.className = "form-message success";
  message.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = `${resume.file_name || "Your resume"} is ready ✨`;
  const detail = document.createElement("p");
  detail.textContent = "Your named resume file is saved. Download a copy or ask the assistant to refine it.";
  const actions = document.createElement("div");
  actions.className = "result-actions";
  if (resume.pdf_path) actions.append(addDownloadLink("↓ PDF", `/api/resume/${encodeURIComponent(resume.id)}/pdf`));
  if (resume.docx_path) actions.append(addDownloadLink("↓ Word document", `/api/resume/${encodeURIComponent(resume.id)}/docx`));
  if (resume.latex_content) {
    const url = URL.createObjectURL(new Blob([resume.latex_content], { type: "text/x-tex;charset=utf-8" }));
    const link = addDownloadLink("↓ LaTeX source", url, `${safeFilename(resume.file_name)}.tex`);
    link.addEventListener("click", () => setTimeout(() => URL.revokeObjectURL(url), 1000), { once: true });
    actions.append(link);
  }
  if (!actions.childElementCount) detail.textContent = "Saved. PDF and Word downloads need a renderer installed; the LaTeX source is available when provided by the app.";
  message.append(heading, detail);
  if (actions.childElementCount) message.append(actions);
  message.hidden = false;
}

function previewSection(sheet, title, rows, fields) {
  if (!rows || (Array.isArray(rows) && !rows.length)) return;
  const section = document.createElement("section");
  section.className = "resume-preview-section";
  const heading = document.createElement("h3");
  heading.textContent = title;
  section.append(heading);
  const items = Array.isArray(rows) ? rows : [rows];
  items.forEach((row) => {
    const item = document.createElement("div");
    item.className = "resume-preview-item";
    if (typeof row === "string") {
      item.textContent = row;
    } else {
      const lead = document.createElement("strong");
      lead.textContent = fields.map((key) => clean(row?.[key])).filter(Boolean).join(" · ");
      if (lead.textContent) item.append(lead);
      Object.entries(row || {}).forEach(([key, value]) => {
        if (!fields.includes(key) && value) {
          const line = document.createElement("p");
          line.textContent = Array.isArray(value) ? value.join(", ") : String(value);
          item.append(line);
        }
      });
    }
    section.append(item);
  });
  sheet.append(section);
}

function refreshPreview(resume = currentResume) {
  const formValues = new FormData(form);
  const profile = resume?.structured_data?.header || {};
  const field = (name, fallback = "") => formValues.has(name) ? clean(formValues.get(name)) : clean(fallback);
  const fullName = field("full_name", profile.full_name || profile.name) || "Your name";
  const titleText = field("target_role", profile.title) || "Your target role";
  const extraLinks = collectEntries("links-list", "link", ["label", "url"], ["label", "url"])
    .map((link) => `${link.label}: ${link.url}`);
  const linkedin = field("linkedin", profile.linkedin);
  const contact = [field("email", profile.email), field("phone", profile.phone), field("address", profile.address), linkedin && `LinkedIn: ${linkedin}`, ...extraLinks].filter(Boolean);
  const sheet = document.querySelector("#resume-preview");
  sheet.replaceChildren();
  const layout = selectedLayout || layouts.find((item) => item.id === layoutPicker.value);
  const templateName = layout?.template_name || resume?.template_name || "modern";
  sheet.dataset.template = templateName;
  const rawAccent = clean(layout?.style?.accent_color).replace(/^#/, "");
  const accent = /^[0-9a-f]{6}$/i.test(rawAccent) ? rawAccent.toUpperCase() : "1F6FEB";
  sheet.style.setProperty("--resume-accent", `#${accent}`);
  sheet.classList.toggle("resume-centered", layout?.style?.header_alignment === "center");
  const header = document.createElement("header");
  header.className = "resume-preview-header";
  const name = document.createElement("h1");
  name.textContent = fullName;
  if (layout?.style?.show_logo === "yes") {
    const monogram = document.createElement("span");
    monogram.className = "resume-monogram";
    monogram.textContent = fullName.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
    name.prepend(monogram);
  }
  const role = document.createElement("p");
  role.className = "resume-preview-role";
  role.textContent = titleText;
  const contacts = document.createElement("p");
  contacts.className = "resume-preview-contact";
  contacts.textContent = contact.join("  |  ");
  header.append(name, role);
  if (contact.length) header.append(contacts);
  sheet.append(header);

  const savedData = resume?.structured_data || {};
  const summary = field("summary", savedData.summary);
  if (summary) {
    const section = document.createElement("section");
    section.className = "resume-preview-section";
    const heading = document.createElement("h3");
    heading.textContent = templateName === "research" ? "Research Profile" : templateName === "creative" ? "Creative Profile" : templateName === "ats" ? "Professional Summary" : "Summary";
    const paragraph = document.createElement("p");
    paragraph.textContent = summary;
    section.append(heading, paragraph);
    sheet.append(section);
  }
  const skillsText = field("skills", savedData.skills);
  const experiences = collectEntries("experience-list", "experience", ["role", "company", "duration", "description"], ["role", "company", "duration", "description"]);
  const education = collectEntries("education-list", "education", ["degree", "institution", "graduation_year"], ["degree", "institution", "graduation_year"]);
  const projects = collectEntries("projects-list", "project", ["name", "technologies", "description", "github_link"], ["name", "technologies", "description"]);
  const publications = collectEntries("publications-list", "publication", ["title", "venue", "date", "url", "description"], ["title"]);
  const skills = () => {
    if (!skillsText) return;
    const section = document.createElement("section");
    section.className = "resume-preview-section";
    const heading = document.createElement("h3");
    heading.textContent = templateName === "research" ? "Technical Skills & Methods" : templateName === "developer" ? "Technical Skills" : "Skills";
    const list = document.createElement("ul");
    list.className = "resume-preview-skills";
    list.style.setProperty("--skill-columns", String(Math.min(3, Math.max(2, Math.ceil(parseSkillItems(skillsText).length / 12)))));
    parseSkillItems(skillsText).forEach((skill) => {
      const item = document.createElement("li");
      item.textContent = skill;
      list.append(item);
    });
    section.append(heading, list);
    sheet.append(section);
  };
  const experience = (label = "Experience") => previewSection(sheet, label, experiences, ["role", "company", "duration"]);
  const projectsSection = (label = "Projects") => previewSection(sheet, label, projects, ["name", "technologies"]);
  const educationSection = () => previewSection(sheet, "Education", education, ["degree", "institution", "graduation_year"]);
  const certificates = () => previewSection(sheet, "Certifications", collectEntries("certificates-list", "certificate", ["name", "issuer", "date"], ["name"]), ["name", "issuer", "date"]);
  const awards = () => previewSection(sheet, "Awards", collectEntries("awards-list", "award", ["name", "issuer", "date", "description"], ["name"]), ["name", "issuer", "date"]);
  const languages = () => previewSection(sheet, "Languages", collectEntries("languages-list", "language", ["name", "proficiency"], ["name"]), ["name"]);
  const publicationSection = () => previewSection(sheet, "Publications", publications, ["title", "venue", "date"]);
  const sectionOrders = {
    ats: [experience, educationSection, skills, projectsSection, certificates, publicationSection, awards, languages],
    modern: [experience, projectsSection, educationSection, skills, certificates, publicationSection, awards, languages],
    student: [educationSection, () => projectsSection("Academic & Selected Projects"), () => experience("Internships & Experience"), skills, certificates, awards, publicationSection, languages],
    developer: [skills, () => projectsSection("Software Projects"), experience, educationSection, certificates, publicationSection, awards, languages],
    research: [educationSection, () => experience("Research Experience"), () => projectsSection("Research & AI/ML Projects"), publicationSection, skills, certificates, awards, languages],
  };
  (sectionOrders[templateName] || sectionOrders.modern).forEach((render) => render());
  document.querySelector("#preview-title").textContent = resume?.file_name || field("file_name") || "Live preview";
  document.querySelector("#preview-subtitle").textContent = currentResumeId ? "Chat edits and form changes update this preview." : "Your edits appear here as you work.";
}

function refreshPdfPreview(resume = currentResume) {
  const frame = document.querySelector("#resume-pdf-frame");
  const empty = document.querySelector("#pdf-empty");
  const button = document.querySelector("#pdf-preview-button");
  const download = document.querySelector("#preview-download");
  const available = Boolean(resume?.id && resume?.pdf_path);
  button.disabled = !available;
  empty.hidden = available;
  frame.hidden = !available;
  if (available) frame.src = `/api/resume/${encodeURIComponent(resume.id)}/pdf?inline=true&preview=${Date.now()}#toolbar=0&view=FitH`;
  download.replaceChildren();
  download.hidden = !available;
  if (available) download.append(addDownloadLink("↓ Download PDF", `/api/resume/${encodeURIComponent(resume.id)}/pdf`, `${safeFilename(resume.file_name)}.pdf`));
}

function setPreviewMode(mode) {
  const pdfMode = mode === "pdf";
  document.querySelector("#live-preview-viewport").hidden = pdfMode;
  document.querySelector("#pdf-preview-viewport").hidden = !pdfMode;
  document.querySelector("#live-preview-button").classList.toggle("active", !pdfMode);
  document.querySelector("#pdf-preview-button").classList.toggle("active", pdfMode);
}

document.querySelector("#live-preview-button").addEventListener("click", () => setPreviewMode("live"));
document.querySelector("#pdf-preview-button").addEventListener("click", () => setPreviewMode("pdf"));

function safeFilename(name) {
  return clean(name).replace(/[^\p{L}\p{N}._ -]+/gu, "").trim().replace(/\s+/g, "-") || "resume";
}

function updateProgress() {
  const hasValue = (name) => clean(form.elements[name]?.value || "").length > 0;
  const identity = hasValue("full_name");
  const direction = hasValue("target_role");
  const experience = collectEntries("experience-list", "experience", ["role", "company", "duration", "description"], ["role", "company", "duration", "description"]).length > 0;
  const education = collectEntries("education-list", "education", ["degree", "institution", "graduation_year"], ["degree", "institution", "graduation_year"]).length > 0;
  const complete = { identity, direction, experience, education };
  const percent = Math.round(Object.values(complete).filter(Boolean).length * 25);
  document.querySelector("#progress-count").textContent = `${percent}%`;
  document.querySelector("#progress-bar").style.width = `${percent}%`;
  Object.entries(complete).forEach(([key, done]) => document.querySelector(`[data-progress="${key}"]`)?.classList.toggle("complete", done));
}

function resetEntries(listId, kind, templateId) {
  const list = document.querySelector(`#${listId}`);
  list.replaceChildren(document.querySelector(`#${templateId}`).content.cloneNode(true));
  list.querySelectorAll("input, textarea").forEach((input) => { input.value = ""; });
}

function addEntry(listId, kind) {
  const template = document.querySelector(`#${kind}-template`);
  document.querySelector(`#${listId}`).append(template.content.cloneNode(true));
  document.querySelector(`#${listId} .entry-card:last-child input`)?.focus();
  updateProgress();
}

document.querySelectorAll(".add-entry").forEach((button) => button.addEventListener("click", () => addEntry(button.dataset.list, button.dataset.kind)));
document.addEventListener("click", (event) => {
  const moveButton = event.target.closest("[data-move]");
  if (moveButton) {
    const card = moveButton.closest(".entry-card");
    if (!card) return;
    if (moveButton.dataset.move === "up" && card.previousElementSibling) {
      card.parentElement.insertBefore(card, card.previousElementSibling);
    } else if (moveButton.dataset.move === "down" && card.nextElementSibling) {
      card.parentElement.insertBefore(card.nextElementSibling, card);
    }
    updateProgress();
    refreshPreview();
    scheduleAutosave();
    moveButton.focus();
    return;
  }
  const removeButton = event.target.closest(".remove-entry");
  if (!removeButton) return;
  const card = removeButton.closest(".entry-card");
  const list = card.parentElement;
  if (list.querySelectorAll(".entry-card").length > 1) card.remove();
  else card.querySelectorAll("input, textarea").forEach((input) => { input.value = ""; });
  updateProgress();
});

function layoutFromSelect() {
  const selected = layouts.find((item) => item.id === layoutPicker.value);
  if (selected) {
    selectedLayout = selected;
    document.querySelector("#template-name").value = selected.template_name;
  }
  return selectedLayout;
}

async function loadLayouts(selectId = "") {
  try {
    const response = await fetch("/api/layouts");
    if (!response.ok) return;
    layouts = await response.json();
    layoutPicker.replaceChildren();
    const formLayouts = layouts.filter((layout) => layout.form_choice);
    const preferred = selectId || selectedLayout?.id || formLayouts[0]?.id;
    const visibleLayouts = [...formLayouts];
    const preferredLayout = layouts.find((layout) => layout.id === preferred);
    if (preferredLayout && !visibleLayouts.some((layout) => layout.id === preferredLayout.id)) visibleLayouts.push(preferredLayout);
    visibleLayouts.forEach((layout) => {
      const option = document.createElement("option");
      option.value = layout.id;
      const kind = layout.template_name === "ats" ? " · ATS-conscious" : layout.form_choice ? "" : " · assistant";
      option.textContent = `${layout.name}${kind}`;
      layoutPicker.append(option);
    });
    if (preferred && visibleLayouts.some((layout) => layout.id === preferred)) layoutPicker.value = preferred;
    layoutFromSelect();
  } catch {
    // Keep the built-in Modern Blue choice available when the layouts endpoint is offline.
  }
}

layoutPicker.addEventListener("change", () => {
  const layout = layoutFromSelect();
  if (layout && currentResumeId) {
    document.querySelector("#template-name").value = layout.template_name;
  }
  refreshPreview();
});

function setEntryValues(listId, kind, templateId, rows, fields) {
  const list = document.querySelector(`#${listId}`);
  list.replaceChildren();
  const values = Array.isArray(rows) ? rows : [];
  (values.length ? values : [{}]).forEach((row) => {
    const fragment = document.querySelector(`#${templateId}`).content.cloneNode(true);
    const card = fragment.querySelector(`[data-entry="${kind}"]`);
    fields.forEach((field) => {
      const control = card.querySelector(`[data-field="${field}"]`);
      if (control) control.value = row?.[field] || "";
    });
    list.append(fragment);
  });
}

function populateForm(resume) {
  const source = resume.source_data || {};
  const header = resume.structured_data?.header || {};
  const profile = source.user_profile || {};
  const values = {
    file_name: resume.file_name,
    full_name: profile.full_name || header.full_name || header.name || "",
    email: profile.email || header.email || "",
    phone: profile.phone || header.phone || "",
    address: profile.address || header.address || "",
    linkedin: profile.linkedin || header.linkedin || "",
    target_role: resume.target_role,
    summary: source.summary || resume.structured_data?.summary || "",
    skills: Array.isArray(source.skills || resume.structured_data?.skills)
      ? (source.skills || resume.structured_data?.skills).join(", ")
      : (source.skills || resume.structured_data?.skills || ""),
  };
  Object.entries(values).forEach(([name, value]) => {
    if (form.elements[name]) form.elements[name].value = value || "";
  });
  fileNameInput.value = resume.file_name || "";
  fileNameValue.value = resume.file_name || "";
  let links = profile.links || header.links || [];
  if (!links.length) {
    links = [
      (profile.portfolio || header.portfolio) && { label: "Portfolio", url: profile.portfolio || header.portfolio },
      (profile.github || header.github) && { label: "GitHub", url: profile.github || header.github },
    ].filter(Boolean);
  }
  setEntryValues("links-list", "link", "link-template", links, ["label", "url"]);
  const data = resume.structured_data || {};
  setEntryValues("experience-list", "experience", "experience-template", source.experience || data.experience, ["role", "company", "duration", "description"]);
  setEntryValues("education-list", "education", "education-template", source.education || data.education, ["degree", "institution", "graduation_year"]);
  setEntryValues("projects-list", "project", "project-template", source.projects || data.projects, ["name", "technologies", "description", "github_link"]);
  setEntryValues("certificates-list", "certificate", "certificate-template", source.certificates || data.certificates, ["name", "issuer", "date"]);
  setEntryValues("languages-list", "language", "language-template", source.languages || data.languages, ["name", "proficiency"]);
  setEntryValues("awards-list", "award", "award-template", source.awards || data.awards, ["name", "issuer", "date", "description"]);
  setEntryValues("publications-list", "publication", "publication-template", source.publications || data.publications, ["title", "venue", "date", "url", "description"]);
  if (form.elements.page_size) form.elements.page_size.value = resume.page_size || "a4";
  const matched = layouts.find((item) => item.id === resume.layout_id)
    || layouts.find((item) => item.template_name === resume.template_name && JSON.stringify(item.style) === JSON.stringify(resume.style));
  if (matched) layoutPicker.value = matched.id;
  selectedLayout = matched || { id: "custom", name: "Custom", template_name: resume.template_name, style: resume.style || {} };
  if (!matched) {
    if (![...layoutPicker.options].some((option) => option.value === "custom")) {
      layoutPicker.add(new Option("Current custom layout", "custom"));
    }
    layoutPicker.value = "custom";
  }
  document.querySelector("#template-name").value = resume.template_name || "modern";
  currentResumeId = resume.id;
  currentResume = resume;
  editorDirty = false;
  restoreConversation();
  updateUndoButton();
  submitButton.querySelector("span:first-child").textContent = "Save changes";
  updateProgress();
  refreshPreview(resume);
  refreshPdfPreview(resume);
  showResult(resume);
}

async function loadResumes(selectId = "") {
  try {
    const response = await fetch("/api/resumes");
    if (!response.ok) return;
    const rows = await response.json();
    const select = document.querySelector("#saved-resumes");
    select.replaceChildren();
    if (!rows.length) {
      select.add(new Option("No saved resumes yet", ""));
      return;
    }
    select.add(new Option("Choose a saved file…", ""));
    rows.forEach((row) => {
      const option = new Option(`${row.file_name} · ${row.target_role}`, row.id);
      option.dataset.fileName = row.file_name;
      select.add(option);
    });
    select.value = selectId || currentResumeId || "";
  } catch {
    // Keep the workspace usable if no files have been saved yet.
  }
}

document.querySelector("#saved-resumes").addEventListener("change", async (event) => {
  const id = event.target.value;
  if (!id) return;
  if (editorDirty && currentResumeId) {
    window.clearTimeout(autosaveTimer);
    const saved = await saveResume(true);
    if (!saved) {
      event.target.value = currentResumeId;
      showMessage("error", "Your latest edits are not saved", "Fix the save issue before opening another resume.");
      return;
    }
  }
  try {
    const response = await fetch(`/api/resume/${encodeURIComponent(id)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not open this resume file.");
    await loadLayouts(result.layout_id || "");
    populateForm(result);
    document.querySelector("#saved-resumes").value = id;
  } catch (error) {
    showMessage("error", "Couldn’t open that file", error.message);
  }
});

document.querySelector("#rename-resume").addEventListener("click", async () => {
  if (!currentResumeId) return showMessage("error", "Choose a saved resume", "Open a resume before renaming it.");
  const title = window.prompt("New resume name", currentResume?.file_name || fileNameInput.value);
  if (title === null || !clean(title)) return;
  try {
    const response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}/title`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not rename this resume.");
    fileNameInput.value = result.file_name;
    currentResume.file_name = result.file_name;
    currentResume.updated_at = result.updated_at;
    await loadResumes(currentResumeId);
    refreshPreview(currentResume);
    showResult(currentResume);
  } catch (error) { showMessage("error", "Rename failed", error.message); }
});

document.querySelector("#duplicate-resume").addEventListener("click", async () => {
  if (!currentResumeId) return showMessage("error", "Choose a saved resume", "Open a resume before duplicating it.");
  try {
    const response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}/duplicate`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not duplicate this resume.");
    await loadResumes(result.id);
    await loadLayouts(result.layout_id || "");
    populateForm(result);
  } catch (error) { showMessage("error", "Duplicate failed", error.message); }
});

document.querySelector("#delete-resume").addEventListener("click", async () => {
  if (!currentResumeId) return showMessage("error", "Choose a saved resume", "Open a resume before deleting it.");
  if (!window.confirm(`Delete “${currentResume?.file_name || fileNameInput.value}”? This cannot be undone.`)) return;
  window.clearTimeout(autosaveTimer);
  try {
    const response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}`, { method: "DELETE" });
    if (!response.ok) { const error = await response.json(); throw new Error(error.detail || "Could not delete this resume."); }
    currentResumeId = null;
    currentResume = null;
    editorDirty = false;
    document.querySelector("#new-resume").click();
    await loadResumes();
    showMessage("success", "Resume deleted", "The saved resume and generated files were removed.");
  } catch (error) { showMessage("error", "Delete failed", error.message); }
});

function snapshotProfile() {
  const data = new FormData(form);
  return {
    ...Object.fromEntries(["full_name", "email", "phone", "address", "linkedin"].map((key) => [key, data.get(key) || ""])),
    links: collectEntries("links-list", "link", ["label", "url"], ["label", "url"]),
  };
}

function clearConversation() {
  conversation = [];
  cacheConversation();
  chatLog.replaceChildren();
  appendBubble("assistant", "Hi! I can polish your resume wording, adjust its format, or create new layout ideas. What would you like to change?");
  document.querySelector("#layout-suggestions").hidden = true;
}

document.querySelector("#new-resume").addEventListener("click", async () => {
  if (currentResumeId && editorDirty) {
    window.clearTimeout(autosaveTimer);
    if (!await saveResume(true)) return;
  } else if (!currentResumeId && editorDirty && !window.confirm("Discard this unsaved draft and start another resume?")) {
    return;
  }
  const profile = snapshotProfile();
  form.reset();
  Object.entries(profile).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value; });
  setEntryValues("links-list", "link", "link-template", profile.links, ["label", "url"]);
  fileNameInput.value = "";
  fileNameValue.value = "";
  resetEntries("experience-list", "experience", "experience-template");
  resetEntries("education-list", "education", "education-template");
  resetEntries("projects-list", "project", "project-template");
  resetEntries("certificates-list", "certificate", "certificate-template");
  resetEntries("languages-list", "language", "language-template");
  resetEntries("awards-list", "award", "award-template");
  resetEntries("publications-list", "publication", "publication-template");
  currentResumeId = null;
  currentResume = null;
  editorDirty = false;
  draftUndoStack = [];
  updateUndoButton();
  submitButton.querySelector("span:first-child").textContent = "Create named resume";
  selectedLayout = layouts[0] || null;
  if (selectedLayout) layoutPicker.value = selectedLayout.id;
  document.querySelector("#template-name").value = selectedLayout?.template_name || "modern";
  document.querySelector("#saved-resumes").value = "";
  message.hidden = true;
  clearConversation();
  updateProgress();
  refreshPreview(null);
  refreshPdfPreview(null);
  setPreviewMode("live");
  fileNameInput.focus();
});

fileNameInput.addEventListener("input", () => { fileNameValue.value = fileNameInput.value.trim(); });

function buildPayload() {
  const values = new FormData(form);
  const profile = {
    full_name: clean(values.get("full_name")), email: clean(values.get("email")) || null,
    phone: clean(values.get("phone")) || null, address: clean(values.get("address")) || null,
    linkedin: clean(values.get("linkedin")) || null, github: null, portfolio: null,
    links: collectEntries("links-list", "link", ["label", "url"], ["label", "url"]).map((link) => ({
      label: link.label,
      url: /^https?:\/\//i.test(link.url) ? link.url : `https://${link.url}`,
    })),
  };
  for (const key of ["linkedin"]) {
    if (profile[key] && !/^https?:\/\//i.test(profile[key])) profile[key] = `https://${profile[key]}`;
  }
  const layout = layoutFromSelect() || layouts[0];
  return {
    file_name: clean(fileNameInput.value),
    layout_id: layout?.id || null,
    user_profile: profile,
    target_role: clean(values.get("target_role")),
    summary: clean(values.get("summary")),
    template_name: layout?.template_name || "modern",
    style: layout?.style || {},
    page_size: clean(values.get("page_size")) || "a4",
    expected_updated_at: currentResume?.updated_at || null,
    skills: parseSkillItems(values.get("skills")),
    experience: collectEntries("experience-list", "experience", ["company", "role", "duration", "description"], ["company", "role", "duration", "description"]),
    education: collectEntries("education-list", "education", ["degree", "institution", "graduation_year"], ["degree", "institution", "graduation_year"]),
    projects: collectEntries("projects-list", "project", ["name", "technologies", "description", "github_link"], ["name", "technologies", "description"]),
    certificates: collectEntries("certificates-list", "certificate", ["name", "issuer", "date"], ["name"]),
    awards: collectEntries("awards-list", "award", ["name", "issuer", "date", "description"], ["name"]),
    languages: collectEntries("languages-list", "language", ["name", "proficiency"], ["name"]),
    publications: collectEntries("publications-list", "publication", ["title", "venue", "date", "url", "description"], ["title"]).map((item) => ({ ...item, url: item.url && !/^https?:\/\//i.test(item.url) ? `https://${item.url}` : item.url })),
  };
}

function hasUsableAIConfig(config) {
  if (config.provider === "ollama") return true;
  return Boolean(config.cloud_authorized);
}

let autosaveTimer = null;
let saveInFlight = false;
let saveRevision = 0;
function scheduleAutosave() {
  saveRevision += 1;
  editorDirty = true;
  if (!currentResumeId) return;
  window.clearTimeout(autosaveTimer);
  document.querySelector("#save-status").textContent = "Unsaved changes";
  autosaveTimer = window.setTimeout(() => saveResume(true), 1400);
}

form.addEventListener("input", () => {
  updateProgress();
  refreshPreview();
  if (document.querySelector("#pdf-preview-button").classList.contains("active")) setPreviewMode("live");
  scheduleAutosave();
});
form.addEventListener("change", () => {
  updateProgress();
  refreshPreview();
  scheduleAutosave();
});
fileNameInput.addEventListener("input", scheduleAutosave);
fileNameInput.addEventListener("change", scheduleAutosave);

async function saveResume(quiet = false) {
  if (saveInFlight) { scheduleAutosave(); return false; }
  if (!form.reportValidity()) return false;
  const requestedName = clean(fileNameInput.value);
  if (requestedName.length < 2) {
    if (!quiet) showMessage("error", "Name this resume first", "Enter its name in the left sidebar before creating the file.");
    return false;
  }
  const duplicate = [...document.querySelector("#saved-resumes").options].some((option) =>
    option.value && option.value !== currentResumeId && (option.dataset.fileName || "").trim().toLocaleLowerCase() === requestedName.toLocaleLowerCase(),
  );
  if (duplicate) {
    if (!quiet) showMessage("error", "That file name is already in use", "Choose a different name in the left sidebar.");
    return false;
  }
  fileNameValue.value = requestedName;
  const payload = buildPayload();
  const revision = saveRevision;
  saveInFlight = true;
  submitButton.disabled = true;
  if (!quiet) submitButton.querySelector("span:first-child").textContent = currentResumeId ? "Saving…" : "Creating…";
  if (!quiet) message.hidden = true;
  document.querySelector("#save-status").textContent = "Saving…";
  try {
    const endpoint = currentResumeId ? `/api/resume/${encodeURIComponent(currentResumeId)}` : "/api/resume/create";
    const response = await fetch(endpoint, { method: currentResumeId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) throw new Error(readableApiError(result.detail, `Request failed (${response.status})`));
    currentResumeId = result.id;
    currentResume = result;
    fileNameInput.value = result.file_name;
    fileNameValue.value = result.file_name;
    await loadResumes(result.id);
    refreshPreview(result);
    refreshPdfPreview(result);
    document.querySelector("#save-status").textContent = revision === saveRevision ? "All changes saved" : "Saving newer changes…";
    if (revision === saveRevision) editorDirty = false;
    if (!quiet) {
      await loadLayouts(result.layout_id || "");
      showResult(result);
    }
    if (revision !== saveRevision) scheduleAutosave();
    return revision === saveRevision;
  } catch (error) {
    document.querySelector("#save-status").textContent = "Save failed — your edits are still here";
    if (!quiet) showMessage("error", "We couldn’t save this resume yet", error.message || "Check your connection and try again.");
    return false;
  } finally {
    saveInFlight = false;
    submitButton.disabled = false;
    submitButton.querySelector("span:first-child").textContent = currentResumeId ? "Save changes" : "Create named resume";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  window.clearTimeout(autosaveTimer);
  await saveResume(false);
});

window.addEventListener("beforeunload", (event) => {
  if (editorDirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});

function appendBubble(role, text, pending = false) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role === "assistant" ? "assistant-bubble" : "user-bubble"}${pending ? " pending" : ""}`;
  bubble.textContent = text;
  chatLog.append(bubble);
  chatLog.scrollTop = chatLog.scrollHeight;
  return bubble;
}

async function applyLayout(layout) {
  if (!currentResumeId) {
    appendBubble("assistant", "Create and save a named resume first. Then I can apply layout changes to its live preview.");
    return;
  }
  selectedLayout = layout;
  if (!layouts.some((item) => item.id === layout.id)) layouts.push(layout);
  await loadLayouts(layout.id);
  document.querySelector("#template-name").value = layout.template_name;
  selectedLayout = layout;
  refreshPreview();
  if (!currentResumeId) {
    appendBubble("assistant", `${layout.name} is selected for your next resume file.`);
    return;
  }
  const undoBefore = makeUndoSnapshot(currentResume);
  try {
    const response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}/apply-layout`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layout_id: layout.id }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not apply this layout.");
    if (resumeVersionKey(currentResume) !== resumeVersionKey(result)) saveUndoSnapshot(undoBefore);
    currentResume = result;
    populateForm(result);
    await loadResumes(result.id);
    appendBubble("assistant", `${layout.name} has been applied to “${result.file_name}”.`);
    conversation.push({ role: "assistant", content: `${layout.name} has been applied to “${result.file_name}”.` });
    cacheConversation();
    showResult(result);
  } catch (error) {
    appendBubble("assistant", error.message || "Could not apply that layout.");
  }
}

function showLayouts(items) {
  const holder = document.querySelector("#layout-suggestions");
  holder.replaceChildren();
  if (!items?.length) {
    holder.hidden = true;
    return;
  }
  items.forEach((layout) => {
    const card = document.createElement("div");
    card.className = "layout-card";
    const preview = document.createElement("div");
    preview.className = `layout-preview preview-${layout.template_name || "modern"}`;
    const proposedColor = clean(layout.style?.accent_color).replace(/^#/, "");
    const color = /^[0-9a-f]{6}$/i.test(proposedColor) ? proposedColor.toUpperCase() : "1F6FEB";
    preview.style.setProperty("--layout-accent", `#${color}`);
    const paper = document.createElement("div");
    paper.className = "preview-paper";
    const nameLine = document.createElement("i");
    nameLine.className = "preview-name";
    const titleLine = document.createElement("i");
    titleLine.className = "preview-title";
    paper.append(nameLine, titleLine);
    for (let index = 0; index < 3; index += 1) {
      const sectionLine = document.createElement("i");
      sectionLine.className = `preview-section preview-section-${index + 1}`;
      const textLine = document.createElement("i");
      textLine.className = `preview-line preview-line-${index + 1}`;
      paper.append(sectionLine, textLine);
    }
    preview.append(paper);
    const name = document.createElement("strong");
    name.textContent = layout.name;
    const badge = document.createElement("span");
    badge.className = "layout-badge";
    badge.textContent = layout.template_name === "ats" ? "ATS-conscious" : "Visually expressive";
    const description = document.createElement("p");
    description.textContent = layout.description;
    const use = document.createElement("button");
    use.type = "button";
    use.textContent = currentResumeId ? "Apply layout" : "Choose layout";
    use.addEventListener("click", () => applyLayout(layout));
    card.append(preview, name, badge, description, use);
    holder.append(card);
  });
  holder.hidden = false;
}

function browseAssistantLayouts() {
  chatPanel.hidden = false;
  showLayouts(layouts.filter((layout) => !layout.form_choice));
}

async function sendChatMessage(rawMessage) {
  const text = clean(rawMessage);
  if (!text) return;
  const recentChatContext = [...conversation.slice(-4).map((item) => item.content), text].join("\n");
  const inlineContactRequest = isInlineContactRequest(recentChatContext);
  if (!currentResumeId && inlineContactRequest) {
    applyInlineContactFormatLocally(text, recentChatContext);
    return;
  }
  if (!currentResumeId) {
    appendBubble("assistant", "Create and save a named resume first. Then I can help edit its wording, colors, and layout while you review the live preview.");
    return;
  }
  const config = readAISettings();
  if (!inlineContactRequest && !hasUsableAIConfig(config)) {
    settingsDialog.showModal();
    document.querySelector("#settings-status").textContent = "For cloud AI, enter a key you’re allowed to use and confirm permission. Or choose local Ollama.";
    document.querySelector("#settings-status").classList.add("error");
    return;
  }
  const conversationLength = conversation.length;
  const undoBefore = currentResumeId ? makeUndoSnapshot(currentResume, conversationLength) : null;
  appendBubble("user", text);
  conversation.push({ role: "user", content: text });
  cacheConversation();
  const pending = appendBubble("assistant", "Thinking…", true);
  document.querySelector("#chat-send").disabled = true;
  try {
    let response;
    if (currentResumeId) {
      response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, conversation: conversation.slice(-20, -1), ai_config: inlineContactRequest ? { provider: "ollama" } : config }),
      });
    } else {
      response = await fetch("/api/layouts/generate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: text, ai_config: config }),
      });
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The assistant couldn’t complete that request.");
    pending.remove();
    if (currentResumeId) {
      if (resumeVersionKey(currentResume) !== resumeVersionKey(result.resume)) saveUndoSnapshot(undoBefore);
      currentResume = result.resume;
      populateForm(result.resume);
      await loadResumes(result.resume.id);
      appendBubble("assistant", result.reply);
      conversation.push({ role: "assistant", content: result.reply });
      cacheConversation();
      showLayouts(result.layouts);
      showResult(result.resume);
    }
  } catch (error) {
    pending.remove();
    const reply = error.message || "Something went wrong. Check your AI settings and try again.";
    appendBubble("assistant", reply);
    conversation.push({ role: "assistant", content: reply });
    cacheConversation();
  } finally {
    document.querySelector("#chat-send").disabled = false;
  }
}

document.querySelector("#chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.querySelector("#chat-input");
  const text = input.value;
  input.value = "";
  sendChatMessage(text);
});
document.querySelectorAll(".chat-shortcuts button").forEach((button) => button.addEventListener("click", () => sendChatMessage(button.dataset.prompt)));
document.querySelector("#chat-launch").addEventListener("click", () => { chatPanel.hidden = false; document.querySelector("#chat-input").focus(); });
document.querySelector("#chat-close").addEventListener("click", () => { chatPanel.hidden = true; });
document.querySelector("#browse-chat-layouts").addEventListener("click", browseAssistantLayouts);

document.querySelector("#chat-undo").addEventListener("click", async () => {
  if (!currentResumeId) {
    const previous = draftUndoStack.pop();
    if (!previous) return;
    setEntryValues("links-list", "link", "link-template", previous.links, ["label", "url"]);
    selectedLayout = previous.layout;
    if (previous.layout_id && [...layoutPicker.options].some((option) => option.value === previous.layout_id)) {
      layoutPicker.value = previous.layout_id;
    } else if (selectedLayout?.id === "custom") {
      if (![...layoutPicker.options].some((option) => option.value === "custom")) layoutPicker.add(new Option("Custom format", "custom"));
      layoutPicker.value = "custom";
    }
    document.querySelector("#template-name").value = selectedLayout?.template_name || "modern";
    conversation = conversation.slice(0, previous.conversation_length);
    cacheConversation();
    refreshPreview();
    appendBubble("assistant", "Undid the last formatting change in the live draft.");
    conversation.push({ role: "assistant", content: "Undid the last formatting change in the live draft." });
    cacheConversation();
    updateUndoButton();
    return;
  }
  const stack = undoStackFor();
  const previous = stack[stack.length - 1];
  if (!previous) return;
  const button = document.querySelector("#chat-undo");
  button.disabled = true;
  try {
    const response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}/undo`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ structured_data: previous.structured_data, template_name: previous.template_name, style: previous.style }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not undo the last resume change.");
    stack.pop();
    const cache = readLocalMap(undoCacheKey);
    cache[currentResumeId] = stack;
    writeLocalMap(undoCacheKey, cache);
    conversation = conversation.slice(0, previous.conversation_length);
    cacheConversation();
    populateForm(result);
    await loadResumes(result.id);
    appendBubble("assistant", "Undid the last resume change. The live preview is restored.");
    conversation.push({ role: "assistant", content: "Undid the last resume change. The live preview is restored." });
    cacheConversation();
    showResult(result);
  } catch (error) {
    appendBubble("assistant", error.message || "Could not undo the last change.");
  } finally {
    updateUndoButton();
  }
});

document.querySelector("#settings-open").addEventListener("click", () => { applySettingsToForm(); settingsDialog.showModal(); });
document.querySelector("#ai-provider").addEventListener("change", (event) => switchProvider(event.target.value));
document.querySelector("#cloud-consent").addEventListener("change", updateSettingsFields);
document.querySelector("#save-ai").addEventListener("click", () => {
  const config = settingsFromForm();
  try {
    saveAISettings(config);
    document.querySelector("#settings-status").classList.remove("error");
    document.querySelector("#settings-status").textContent = config.api_key ? "Saved for this tab only. The key is sent to the app only when you test or use AI." : "Settings saved in this browser. No API key is set for this provider.";
  } catch {
    document.querySelector("#settings-status").classList.add("error");
    document.querySelector("#settings-status").textContent = "This browser couldn’t save the settings or keep the key in this tab. Check its storage permissions.";
  }
});
document.querySelector("#test-ai").addEventListener("click", async () => {
  const status = document.querySelector("#settings-status");
  status.classList.remove("error");
  status.textContent = "Testing connection…";
  try {
    const response = await fetch("/api/ai/test", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settingsFromForm()),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(readableApiError(result.detail, `Connection failed (HTTP ${response.status}).`));
    status.textContent = result.message;
  } catch (error) {
    status.classList.add("error");
    status.textContent = error.message;
  }
});

document.querySelector("#chat-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    document.querySelector("#chat-form").requestSubmit();
  }
});

async function initialize() {
  chatCacheKey = "nhyapu.chat-cache.local";
  undoCacheKey = "nhyapu.undo-cache.local";
  aiKeyPrefix = "nhyapu.ai-key.local.";
  applySettingsToForm();
  await loadLayouts();
  await loadResumes();
  updateProgress();
  refreshPreview(null);
  refreshPdfPreview(null);
}

initialize();
