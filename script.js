// ---------------------------------------------------------------
// CONFIG: paste your API Gateway endpoint here (include /contact)
// Example: https://abc123xyz.execute-api.ap-south-1.amazonaws.com/contact
// ---------------------------------------------------------------
const API_URL = "https://abc123xyz.execute-api.ap-south-1.amazonaws.com/contact";

const form = document.getElementById("contact-form");
const submitBtn = document.getElementById("submit-btn");
const btnText = submitBtn.querySelector(".btn-text");
const statusBox = document.getElementById("status");
const messageField = document.getElementById("message");
const charCount = document.getElementById("char-count");

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Live character counter for the message box
messageField.addEventListener("input", () => {
  charCount.textContent = messageField.value.length;
});

function showStatus(type, text) {
  statusBox.className = "status " + type;
  statusBox.textContent = text;
}

function clearStatus() {
  statusBox.className = "status";
  statusBox.textContent = "";
}

function setLoading(isLoading) {
  submitBtn.disabled = isLoading;
  submitBtn.classList.toggle("loading", isLoading);
  btnText.textContent = isLoading ? "Sending..." : "Send message";
}

function markInvalid(field, isInvalid) {
  field.classList.toggle("invalid", isInvalid);
}

// Basic client-side validation (the backend validates again)
function validate(data) {
  const nameField = form.elements["name"];
  const emailField = form.elements["email"];
  const messageInput = form.elements["message"];

  markInvalid(nameField, false);
  markInvalid(emailField, false);
  markInvalid(messageInput, false);

  if (data.name.length < 2) {
    markInvalid(nameField, true);
    return "Please enter your name (at least 2 characters).";
  }
  if (!EMAIL_PATTERN.test(data.email)) {
    markInvalid(emailField, true);
    return "Please enter a valid email address.";
  }
  if (data.message.length < 10) {
    markInvalid(messageInput, true);
    return "Please enter a message (at least 10 characters).";
  }
  return null;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearStatus();

  if (API_URL.includes("YOUR-API-ID")) {
    showStatus("error", "API URL is not configured yet. Edit script.js and set API_URL.");
    return;
  }

  const data = {
    name: form.elements["name"].value.trim(),
    email: form.elements["email"].value.trim(),
    subject: form.elements["subject"].value.trim(),
    message: form.elements["message"].value.trim(),
    website: form.elements["website"].value, // honeypot
  };

  const problem = validate(data);
  if (problem) {
    showStatus("error", problem);
    return;
  }

  setLoading(true);

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    let result = {};
    try {
      result = await response.json();
    } catch (_) {
      // Response was not JSON; fall through to the generic messages below
    }

    if (response.ok) {
      showStatus("success", result.message || "Thank you! Your message has been received.");
      form.reset();
      charCount.textContent = "0";
    } else {
      showStatus("error", result.message || "Something went wrong. Please try again.");
    }
  } catch (error) {
    // Network failure or CORS problem (check the browser console for details)
    console.error("Request failed:", error);
    showStatus("error", "Could not reach the server. Check your connection and try again.");
  } finally {
    setLoading(false);
  }
});
