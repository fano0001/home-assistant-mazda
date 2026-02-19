// Read auth code from URL parameters
const params = new URLSearchParams(window.location.search);
const code = params.get("code");

if (code) {
  document.getElementById("success").style.display = "block";
  // Mask the code, showing only last 4 characters
  const masked = "•".repeat(Math.max(0, code.length - 4)) + code.slice(-4);
  document.getElementById("authCode").textContent = masked;
} else {
  document.getElementById("noCode").style.display = "block";
}

// Copy handler
document.getElementById("copyCode").addEventListener("click", async () => {
  await navigator.clipboard.writeText(code);
  const toast = document.getElementById("toast");
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
});
