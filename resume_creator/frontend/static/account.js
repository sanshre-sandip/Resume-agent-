const accountMessage = document.querySelector("#account-message");
const deleteDialog = document.querySelector("#delete-dialog");
let currentAccount = null;

async function accountRequest(url, options = {}) {
  const response = await fetch(url, options);
  const result = response.status === 204 ? {} : await response.json();
  if (!response.ok) throw new Error(result.detail || "This request could not be completed.");
  return result;
}

function clearAccountCache() {
  if (!currentAccount?.id) return;
  localStorage.removeItem(`nhyapu.chat-cache.${currentAccount.id}`);
  localStorage.removeItem(`nhyapu.undo-cache.${currentAccount.id}`);
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(`nhyapu.ai-key.${currentAccount.id}.`)) sessionStorage.removeItem(key);
    }
  } catch { /* Session key cleanup is best-effort; the browser clears it when the tab closes. */ }
}

function showAccountError(message, success = false) {
  accountMessage.className = `account-message${success ? " success" : ""}`;
  accountMessage.textContent = message;
}

async function loadAccount() {
  try {
    const account = await accountRequest("/api/auth/account");
    currentAccount = account;
    const name = account.name || "Craft account";
    const initial = [...name.trim()][0]?.toLocaleUpperCase() || "N";
    document.querySelector("#account-avatar").textContent = initial;
    document.querySelector("#account-name").textContent = name;
    document.querySelector("#profile-name").textContent = name;
    document.querySelector("#account-email").textContent = account.email;
    document.querySelector("#profile-email").textContent = account.email;
    const date = account.created_at ? new Date(account.created_at) : null;
    document.querySelector("#account-created").textContent = date && !Number.isNaN(date.valueOf())
      ? new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(date)
      : "—";
  } catch {
    window.location.assign("/login?next=/account");
  }
}

document.querySelector("#logout-button").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  showAccountError("");
  try {
    await accountRequest("/api/auth/logout", { method: "POST" });
    clearAccountCache();
    window.location.assign("/login");
  } catch (error) {
    showAccountError(error.message);
    button.disabled = false;
  }
});

document.querySelector("#delete-account").addEventListener("click", () => deleteDialog.showModal());
document.querySelector("#cancel-delete").addEventListener("click", () => deleteDialog.close());
document.querySelector("#confirm-delete").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  showAccountError("");
  try {
    await accountRequest("/api/auth/account", { method: "DELETE" });
    clearAccountCache();
    window.location.assign("/");
  } catch (error) {
    showAccountError(error.message);
    button.disabled = false;
    deleteDialog.close();
  }
});

loadAccount();
