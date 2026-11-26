(() => {
  const nativeFetch = window.fetch.bind(window);
  const readCookie = (name) => document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${name}=`))?.slice(name.length + 1) || "";
  let csrfRequest;

  window.fetch = async (resource, options = {}) => {
    const target = new URL(typeof resource === "string" ? resource : resource.url, window.location.href);
    const method = (options.method || (typeof resource !== "string" && resource.method) || "GET").toUpperCase();
    const headers = new Headers(options.headers || (typeof resource !== "string" ? resource.headers : undefined));
    const init = { ...options, headers, credentials: options.credentials || "same-origin" };
    if (target.origin === window.location.origin && !["GET", "HEAD", "OPTIONS"].includes(method) && target.pathname !== "/api/auth/csrf") {
      let token = decodeURIComponent(readCookie("nhyapu_csrf"));
      if (!token) {
        csrfRequest ||= nativeFetch("/api/auth/csrf", { credentials: "same-origin" }).finally(() => { csrfRequest = null; });
        await csrfRequest;
        token = decodeURIComponent(readCookie("nhyapu_csrf"));
      }
      if (token) headers.set("X-CSRF-Token", token);
    }
    return nativeFetch(resource, init);
  };
})();
