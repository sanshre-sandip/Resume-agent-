const form = document.querySelector("#resume-form");
const message = document.querySelector("#form-message");
const submitButton = document.querySelector("#generate-button");

const clean = (value) => value.trim();
const valuesFor = (card, keys) => Object.fromEntries(keys.map((key) => [key, clean(card.querySelector(`[data-field="${key}"]`)?.value || "")]));
const collectEntries = (listId, kind, fields, required) =>
  [...document.querySelectorAll(`#${listId} [data-entry="${kind}"]`)]
    .map((card) => valuesFor(card, fields))
    .filter((item) => required.every((key) => item[key]));

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

function showResult(result) {
  message.className = "form-message success";
  message.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = "Your resume is ready ✨";
  const detail = document.createElement("p");
  detail.textContent = "Your new resume has been created. Pick a format to save a copy.";
  const actions = document.createElement("div");
  actions.className = "result-actions";
  if (result.pdf_path && result.pdf_path !== "#pending") {
    actions.append(addDownloadLink("↓ PDF", `/api/resume/${encodeURIComponent(result.id)}/pdf`));
  }
  if (result.docx_path && result.docx_path !== "#pending") {
    actions.append(addDownloadLink("↓ Word document", `/api/resume/${encodeURIComponent(result.id)}/docx`));
  }
  if (result.latex_content) {
    const blob = new Blob([result.latex_content], { type: "text/x-tex;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = addDownloadLink("↓ LaTeX source", url, `resume-${result.id}.tex`);
    link.addEventListener("click", () => setTimeout(() => URL.revokeObjectURL(url), 1000), { once: true });
    actions.append(link);
  }
  if (!actions.childElementCount) {
    detail.textContent = "The resume is saved, but no downloadable format was produced. Check the app’s PDF and DOCX rendering setup.";
  }
  message.append(heading, detail);
  if (actions.childElementCount) message.append(actions);
  message.hidden = false;
  message.scrollIntoView({ behavior: "smooth", block: "center" });
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
  Object.entries(complete).forEach(([key, done]) => {
    document.querySelector(`[data-progress="${key}"]`)?.classList.toggle("complete", done);
  });
}

document.querySelectorAll(".add-entry").forEach((button) => {
  button.addEventListener("click", () => {
    const kind = button.dataset.kind;
    const template = document.querySelector(`#${kind}-template`);
    document.querySelector(`#${button.dataset.list}`).append(template.content.cloneNode(true));
    document.querySelector(`#${button.dataset.list} .entry-card:last-child input`)?.focus();
    updateProgress();
  });
});

document.addEventListener("click", (event) => {
  const removeButton = event.target.closest(".remove-entry");
  if (!removeButton) return;
  const card = removeButton.closest(".entry-card");
  const list = card.parentElement;
  if (list.querySelectorAll(".entry-card").length > 1) card.remove();
  else card.querySelectorAll("input, textarea").forEach((input) => { input.value = ""; });
  updateProgress();
});

form.addEventListener("input", updateProgress);
form.addEventListener("change", updateProgress);

async function loadTemplates() {
  try {
    const response = await fetch("/api/templates");
    if (!response.ok) return;
    const templates = await response.json();
    const select = document.querySelector("#template-select");
    select.replaceChildren();
    templates.filter((template) => template.available).forEach((template) => {
      const option = document.createElement("option");
      option.value = template.name;
      option.textContent = template.name.charAt(0).toUpperCase() + template.name.slice(1);
      select.append(option);
    });
    if (!select.options.length) select.add(new Option("Modern", "modern"));
  } catch {
    // Keep the built-in template choices if the templates endpoint is unavailable.
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const values = new FormData(form);
  const profile = {
    full_name: clean(values.get("full_name")),
    email: clean(values.get("email")),
    phone: clean(values.get("phone")),
    address: clean(values.get("address")) || null,
    linkedin: clean(values.get("linkedin")) || null,
    github: null,
    portfolio: clean(values.get("portfolio")) || null,
  };
  if (profile.linkedin && !/^https?:\/\//i.test(profile.linkedin)) profile.linkedin = `https://${profile.linkedin}`;
  if (profile.portfolio && !/^https?:\/\//i.test(profile.portfolio)) profile.portfolio = `https://${profile.portfolio}`;

  const payload = {
    user_profile: profile,
    target_role: clean(values.get("target_role")),
    template_name: values.get("template_name") || "modern",
    skills: clean(values.get("skills")).split(",").map(clean).filter(Boolean),
    experience: collectEntries("experience-list", "experience", ["company", "role", "duration", "description"], ["company", "role", "duration", "description"]),
    education: collectEntries("education-list", "education", ["degree", "institution", "graduation_year"], ["degree", "institution", "graduation_year"]),
    projects: collectEntries("projects-list", "project", ["name", "technologies", "description", "github_link"], ["name", "technologies", "description"]),
    certificates: [],
  };

  submitButton.disabled = true;
  submitButton.querySelector("span:first-child").textContent = "Putting it together…";
  message.hidden = true;
  try {
    const response = await fetch("/api/resume/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || `Request failed (${response.status})`);
    showResult(result);
  } catch (error) {
    showMessage("error", "We couldn’t create your resume yet", error.message || "Check your connection and try again.");
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span:first-child").textContent = "Shape my resume";
  }
});

loadTemplates();
updateProgress();
