const authForm = document.querySelector("#auth-form");
const authMessage = document.querySelector("#auth-message");
const pathMode = window.location.pathname;
const query = new URLSearchParams(window.location.search);
const authTitle = document.querySelector("#auth-title");
const authDescription = document.querySelector("#auth-description");
const authSubmit = document.querySelector("#auth-submit");
const nameField = document.querySelector("#name-field");
const passwordField = document.querySelector("#password-field");
const authLinks = document.querySelector("#auth-links");
const googleButton = document.querySelector(".google-button");
let mode = "login";

fetch("/api/auth/options").then((response) => response.json()).then((options) => {
  if (options.google_enabled && ["login", "register"].includes(mode)) googleButton.hidden = false;
  if (mode === "forgot" && !options.password_recovery_enabled) {
    authMessage.className = "auth-message";
    authMessage.textContent = "Email recovery is not configured for this site yet. Contact the site operator for help.";
  }
}).catch(() => {});

if (pathMode === "/register") {
  mode = "register";
  authTitle.textContent = "Create your account";
  authDescription.textContent = "Save and reopen resumes in your private workspace.";
  authSubmit.textContent = "Create account";
  nameField.hidden = false;
  authLinks.innerHTML = '<span>Already have an account? <a href="/login">Sign in</a></span>';
} else if (pathMode === "/forgot-password") {
  mode = "forgot";
  authTitle.textContent = "Reset your password";
  authDescription.textContent = "We’ll send a reset link if that email can be recovered.";
  passwordField.hidden = true;
  document.querySelector("#password-help").hidden = true;
  authSubmit.textContent = "Send reset link";
  authLinks.innerHTML = '<a href="/login">Back to sign in</a>';
  googleButton.hidden = true;
} else if (pathMode === "/reset-password") {
  mode = "reset";
  authTitle.textContent = "Choose a new password";
  authDescription.textContent = "Use at least 12 characters. Your other sessions will be signed out.";
  document.querySelector('label:has(input[name="email"])').hidden = true;
  document.querySelector('input[name="email"]').required = false;
  document.querySelector('input[name="password"]').autocomplete = "new-password";
  authLinks.innerHTML = '<a href="/login">Back to sign in</a>';
  googleButton.hidden = true;
  document.querySelector("#password-help").textContent = "Use at least 12 characters.";
}

if (query.get("verified") === "1") document.querySelector("#verified-message").hidden = false;

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.className = "auth-message";
  authMessage.textContent = "";
  if (!authForm.reportValidity()) return;
  const values = new FormData(authForm);
  let endpoint = "/api/auth/login";
  let body = { email: values.get("email"), password: values.get("password") };
  if (mode === "register") { endpoint = "/api/auth/register"; body.display_name = values.get("name") || ""; }
  if (mode === "forgot") { endpoint = "/api/auth/forgot-password"; body = { email: values.get("email") }; }
  if (mode === "reset") { endpoint = "/api/auth/reset-password"; body = { token: query.get("token") || "", password: values.get("password") }; }
  authSubmit.disabled = true;
  authSubmit.textContent = "Please wait…";
  try {
    const response = await fetch(endpoint, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "This request could not be completed.");
    if (mode === "login") {
      const next = query.get("next") || "/workspace";
      window.location.assign(next.startsWith("/") && !next.startsWith("//") ? next : "/workspace");
      return;
    }
    if (mode === "register" && result.user) {
      window.location.assign("/workspace");
      return;
    }
    authMessage.className = "auth-message success";
    authMessage.textContent = result.message || (mode === "register" ? "Check your email for the verification link." : "Done. You can continue to sign in.");
    if (mode === "reset") window.setTimeout(() => window.location.assign("/login"), 1800);
  } catch (error) {
    authMessage.className = "auth-message error";
    authMessage.textContent = error.message;
  } finally {
    authSubmit.disabled = false;
    authSubmit.textContent = mode === "register" ? "Create account" : mode === "forgot" ? "Send reset link" : mode === "reset" ? "Update password" : "Sign in";
  }
});
