"use strict";

const form = document.getElementById("login-form");
form.addEventListener("submit", async event => {
  event.preventDefault();
  const submit = event.submitter;
  const status = document.getElementById("login-status");
  submit.disabled = true;
  status.textContent = "";
  try {
    const response = await fetch("/api/v2/session", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-StreetView-Request": "1"},
      body: JSON.stringify(Object.fromEntries(new FormData(form)))
    });
    if (response.status === 401) throw Error("Username or password is incorrect.");
    if (!response.ok) throw Error("Could not sign in. Try again.");
    location.replace("/");
  } catch (error) {
    status.textContent = error.message;
    submit.disabled = false;
  }
});
