const form = document.querySelector("#resume-form");
const message = document.querySelector("#form-message");
const submitButton = document.querySelector("#generate-button");
const settingsDialog = document.querySelector("#settings-dialog");
const chatPanel = document.querySelector("#chat-panel");
const chatLog = document.querySelector("#chat-messages");
const layoutPicker = document.querySelector("#layout-select");
const aiStorageKey = "forma.ai-settings.v1";

let currentResumeId = null;
let currentResume = null;
let layouts = [];
let conversation = [];
let selectedLayout = null;

const clean = (value) => String(value ?? "").trim();
const valuesFor = (card, keys) => Object.fromEntries(keys.map((key) => [key, clean(card.querySelector(`[data-field="${key}"]`)?.value || "")]));
const collectEntries = (listId, kind, fields, required) =>
  [...document.querySelectorAll(`#${listId} [data-entry="${kind}"]`)]
    .map((card) => valuesFor(card, fields))
    .filter((item) => required.every((key) => item[key]));

function readAISettings() {
  try {
    return { provider: "openai", api_key: "", model: "", base_url: "", cloud_authorized: false, ...JSON.parse(localStorage.getItem(aiStorageKey) || "{}") };
  } catch {
    return { provider: "openai", api_key: "", model: "", base_url: "", cloud_authorized: false };
  }
}

function settingsFromForm() {
  return {
    provider: document.querySelector("#ai-provider").value,
    api_key: document.querySelector("#ai-key").value.trim(),
    model: document.querySelector("#ai-model").value.trim(),
    base_url: document.querySelector("#ai-base-url").value.trim(),
    cloud_authorized: document.querySelector("#cloud-consent").checked,
  };
}

function applySettingsToForm() {
  const config = readAISettings();
  document.querySelector("#ai-provider").value = config.provider;
  document.querySelector("#ai-key").value = config.api_key;
  document.querySelector("#ai-model").value = config.model;
  document.querySelector("#ai-base-url").value = config.base_url;
  document.querySelector("#cloud-consent").checked = Boolean(config.cloud_authorized);
  updateSettingsFields();
}

function updateSettingsFields() {
  const provider = document.querySelector("#ai-provider").value;
  document.querySelector("#api-key-field").hidden = provider === "ollama";
  document.querySelector("#base-url-field").hidden = !["openai", "groq", "ollama"].includes(provider);
  const modelPlaceholders = {
    openai: "gpt-4o-mini", anthropic: "claude-3-5-haiku-20241022",
    google: "gemini-2.0-flash", groq: "openai/gpt-oss-20b",
    openrouter: "meta-llama/llama-3.1-70b-instruct", ollama: "llama3.1",
  };
  document.querySelector("#ai-model").placeholder = modelPlaceholders[provider] || "Provider default";
  const baseUrls = { openai: "https://api.openai.com/v1", groq: "https://api.groq.com/openai/v1", ollama: "http://localhost:11434" };
  document.querySelector("#ai-base-url").placeholder = baseUrls[provider] || "Provider default";
  document.querySelector("#cloud-consent-field").hidden = provider === "ollama";
  const cloudAllowed = provider === "ollama" || (document.querySelector("#ai-key").value.trim() && document.querySelector("#cloud-consent").checked);
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

function safeFilename(name) {
  return clean(name).replace(/[^\p{L}\p{N}._ -]+/gu, "").trim().replace(/\s+/g, "-") || "resume";
}

function updateProgress() {
  const hasValue = (name) => clean(form.elements[name]?.value || "").length > 0;
  const identity = ["full_name", "email", "phone"].every(hasValue);
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
    layouts.forEach((layout) => {
      const option = document.createElement("option");
      option.value = layout.id;
      option.textContent = layout.built_in ? layout.name : `${layout.name} · AI`;
      layoutPicker.append(option);
    });
    const preferred = selectId || selectedLayout?.id || layouts[0]?.id;
    if (preferred && layouts.some((layout) => layout.id === preferred)) layoutPicker.value = preferred;
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
    portfolio: profile.portfolio || header.portfolio || header.github || "",
    target_role: resume.target_role,
    skills: Array.isArray(source.skills || resume.structured_data?.skills)
      ? (source.skills || resume.structured_data?.skills).join(", ")
      : (source.skills || resume.structured_data?.skills || ""),
  };
  Object.entries(values).forEach(([name, value]) => {
    if (form.elements[name]) form.elements[name].value = value || "";
  });
  const data = resume.structured_data || {};
  setEntryValues("experience-list", "experience", "experience-template", source.experience || data.experience, ["role", "company", "duration", "description"]);
  setEntryValues("education-list", "education", "education-template", source.education || data.education, ["degree", "institution", "graduation_year"]);
  setEntryValues("projects-list", "project", "project-template", source.projects || data.projects, ["name", "technologies", "description", "github_link"]);
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
  submitButton.querySelector("span:first-child").textContent = "Save changes";
  updateProgress();
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
    rows.forEach((row) => select.add(new Option(`${row.file_name} · ${row.target_role}`, row.id)));
    select.value = selectId || currentResumeId || "";
  } catch {
    // Keep the workspace usable if no files have been saved yet.
  }
}

document.querySelector("#saved-resumes").addEventListener("change", async (event) => {
  const id = event.target.value;
  if (!id) return;
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

function snapshotProfile() {
  const data = new FormData(form);
  return Object.fromEntries(["full_name", "email", "phone", "address", "linkedin", "portfolio"].map((key) => [key, data.get(key) || ""]));
}

function clearConversation() {
  conversation = [];
  chatLog.replaceChildren();
  appendBubble("assistant", "Hi! I can polish your resume wording, adjust its format, or create new layout ideas. What would you like to change?");
  document.querySelector("#layout-suggestions").hidden = true;
}

document.querySelector("#new-resume").addEventListener("click", () => {
  const profile = snapshotProfile();
  form.reset();
  Object.entries(profile).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value; });
  form.elements.file_name.value = "";
  resetEntries("experience-list", "experience", "experience-template");
  resetEntries("education-list", "education", "education-template");
  resetEntries("projects-list", "project", "project-template");
  currentResumeId = null;
  currentResume = null;
  submitButton.querySelector("span:first-child").textContent = "Create named resume";
  selectedLayout = layouts[0] || null;
  if (selectedLayout) layoutPicker.value = selectedLayout.id;
  document.querySelector("#template-name").value = selectedLayout?.template_name || "modern";
  document.querySelector("#saved-resumes").value = "";
  message.hidden = true;
  clearConversation();
  updateProgress();
  document.querySelector("#file-name").focus();
});

function buildPayload() {
  const values = new FormData(form);
  const profile = {
    full_name: clean(values.get("full_name")), email: clean(values.get("email")),
    phone: clean(values.get("phone")), address: clean(values.get("address")) || null,
    linkedin: clean(values.get("linkedin")) || null, github: null,
    portfolio: clean(values.get("portfolio")) || null,
  };
  for (const key of ["linkedin", "portfolio"]) {
    if (profile[key] && !/^https?:\/\//i.test(profile[key])) profile[key] = `https://${profile[key]}`;
  }
  const layout = layoutFromSelect() || layouts[0];
  return {
    file_name: clean(values.get("file_name")),
    layout_id: layout?.id || null,
    user_profile: profile,
    target_role: clean(values.get("target_role")),
    template_name: layout?.template_name || "modern",
    style: layout?.style || {},
    ai_config: readAISettings(),
    skills: clean(values.get("skills")).split(",").map(clean).filter(Boolean),
    experience: collectEntries("experience-list", "experience", ["company", "role", "duration", "description"], ["company", "role", "duration", "description"]),
    education: collectEntries("education-list", "education", ["degree", "institution", "graduation_year"], ["degree", "institution", "graduation_year"]),
    projects: collectEntries("projects-list", "project", ["name", "technologies", "description", "github_link"], ["name", "technologies", "description"]),
    certificates: [],
  };
}

function hasUsableAIConfig(config) {
  if (config.provider === "ollama") return true;
  return Boolean(config.api_key && config.cloud_authorized);
}

form.addEventListener("input", updateProgress);
form.addEventListener("change", updateProgress);
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const payload = buildPayload();
  if (!hasUsableAIConfig(payload.ai_config)) {
    settingsDialog.showModal();
    document.querySelector("#settings-status").textContent = "For cloud AI, enter a key you’re allowed to use and confirm permission. Or choose local Ollama.";
    document.querySelector("#settings-status").classList.add("error");
    return;
  }
  submitButton.disabled = true;
  submitButton.querySelector("span:first-child").textContent = currentResumeId ? "Updating file…" : "Creating your file…";
  message.hidden = true;
  try {
    const endpoint = currentResumeId ? `/api/resume/${encodeURIComponent(currentResumeId)}` : "/api/resume/create";
    const response = await fetch(endpoint, {
      method: currentResumeId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`);
    await loadLayouts(result.layout_id || "");
    populateForm(result);
    await loadResumes(result.id);
    showResult(result);
  } catch (error) {
    showMessage("error", "We couldn’t save this resume yet", error.message || "Check the AI settings and try again.");
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span:first-child").textContent = currentResumeId ? "Save changes" : "Create named resume";
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
  selectedLayout = layout;
  if (!layouts.some((item) => item.id === layout.id)) layouts.push(layout);
  await loadLayouts(layout.id);
  document.querySelector("#template-name").value = layout.template_name;
  if (!currentResumeId) {
    appendBubble("assistant", `${layout.name} is selected for your next resume file.`);
    return;
  }
  try {
    const response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}/apply-layout`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layout_id: layout.id }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Could not apply this layout.");
    currentResume = result;
    populateForm(result);
    await loadResumes(result.id);
    appendBubble("assistant", `${layout.name} has been applied to “${result.file_name}”.`);
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
    const allowedColors = new Set(["1F6FEB", "6F42C1", "0F766E", "B45309", "1F2937", "BE123C"]);
    const color = allowedColors.has(layout.style?.accent_color) ? layout.style.accent_color : "1F6FEB";
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
    const description = document.createElement("p");
    description.textContent = layout.description;
    const use = document.createElement("button");
    use.type = "button";
    use.textContent = currentResumeId ? "Apply layout" : "Choose layout";
    use.addEventListener("click", () => applyLayout(layout));
    card.append(preview, name, description, use);
    holder.append(card);
  });
  holder.hidden = false;
}

async function sendChatMessage(rawMessage) {
  const text = clean(rawMessage);
  if (!text) return;
  if (!currentResumeId && !/\b(layout|design|format|template)s?\b/i.test(text)) {
    appendBubble("assistant", "Choose or create a named resume file first and I can help edit its content. You can ask me for layout ideas at any time.");
    return;
  }
  const config = readAISettings();
  if (!hasUsableAIConfig(config)) {
    settingsDialog.showModal();
    document.querySelector("#settings-status").textContent = "For cloud AI, enter a key you’re allowed to use and confirm permission. Or choose local Ollama.";
    document.querySelector("#settings-status").classList.add("error");
    return;
  }
  appendBubble("user", text);
  conversation.push({ role: "user", content: text });
  const pending = appendBubble("assistant", "Thinking…", true);
  document.querySelector("#chat-send").disabled = true;
  try {
    let response;
    if (currentResumeId) {
      response = await fetch(`/api/resume/${encodeURIComponent(currentResumeId)}/chat`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, conversation: conversation.slice(0, -1), ai_config: config }),
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
      currentResume = result.resume;
      populateForm(result.resume);
      await loadResumes(result.resume.id);
      appendBubble("assistant", result.reply);
      conversation.push({ role: "assistant", content: result.reply });
      showLayouts(result.layouts);
      showResult(result.resume);
    } else {
      const reply = `I made ${result.length} new layout options. Choose one now, or create a named resume file when you’re ready.`;
      appendBubble("assistant", reply);
      conversation.push({ role: "assistant", content: reply });
      await loadLayouts();
      showLayouts(result);
    }
  } catch (error) {
    pending.remove();
    appendBubble("assistant", error.message || "Something went wrong. Check your AI settings and try again.");
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

document.querySelector("#settings-open").addEventListener("click", () => { applySettingsToForm(); settingsDialog.showModal(); });
document.querySelector("#ai-provider").addEventListener("change", updateSettingsFields);
document.querySelector("#cloud-consent").addEventListener("change", updateSettingsFields);
document.querySelector("#ai-key").addEventListener("input", updateSettingsFields);
document.querySelector("#save-ai").addEventListener("click", () => {
  const config = settingsFromForm();
  try {
    localStorage.setItem(aiStorageKey, JSON.stringify(config));
    document.querySelector("#settings-status").classList.remove("error");
    document.querySelector("#settings-status").textContent = "Saved in this browser. No key was written to the app’s data files.";
  } catch {
    document.querySelector("#settings-status").classList.add("error");
    document.querySelector("#settings-status").textContent = "This browser couldn’t save settings. Check its local storage permissions.";
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
    if (!response.ok) throw new Error(result.detail || "Connection failed.");
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
  applySettingsToForm();
  await loadLayouts();
  await loadResumes();
  updateProgress();
}

initialize();
