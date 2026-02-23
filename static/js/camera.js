// ============================
// SecureVote Camera Script
// ============================

let streamRef = null;

// Start Camera
async function startCamera() {
  const video = document.getElementById("video");
  const status = document.getElementById("status");

  if (!video) {
    console.error("Video element not found.");
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (status) status.textContent = "Camera not supported in this browser.";
    return;
  }

  try {
    streamRef = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user" },
      audio: false
    });

    video.srcObject = streamRef;
    await video.play();

    if (status) status.textContent = "✅ Camera started successfully.";
  } catch (error) {
    console.error(error);
    if (status) status.textContent = "❌ Camera error: " + error.message;
  }
}

// Stop Camera
function stopCamera() {
  if (streamRef) {
    streamRef.getTracks().forEach(track => track.stop());
  }
}

// Capture Image (returns base64)
function captureImageBase64() {
  const video = document.getElementById("video");
  const canvas = document.getElementById("canvas");

  if (!video || !canvas) return null;

  const width = video.videoWidth;
  const height = video.videoHeight;

  if (!width || !height) return null;

  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, width, height);

  return canvas.toDataURL("image/jpeg", 0.9);
}

// ============================
// Registration Capture
// ============================
async function captureAndRegister() {
  const status = document.getElementById("status");
  const image = captureImageBase64();

  if (!image) {
    if (status) status.textContent = "⚠ Please start camera first.";
    return;
  }

  if (status) status.textContent = "Uploading face for registration...";

  try {
    const response = await fetch("/api/register-face", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ image: image })
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      if (status) status.textContent = "❌ " + (data.error || "Registration failed.");
      return;
    }

    if (status) status.textContent = "✅ Registration successful! Redirecting...";
    stopCamera();

    setTimeout(() => {
      window.location.href = "/elections";
    }, 1200);

  } catch (err) {
    console.error(err);
    if (status) status.textContent = "❌ Server error during registration.";
  }
}

// ============================
// Vote Face Verification
// ============================
async function captureAndVerifyVote() {
  const status = document.getElementById("status");
  const image = captureImageBase64();

  if (!image) {
    if (status) status.textContent = "⚠ Please start camera first.";
    return;
  }

  if (status) status.textContent = "Verifying face...";

  try {
    const response = await fetch("/api/vote-face-verify", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ image: image })
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      if (status) status.textContent = "❌ " + (data.error || "Verification failed.");
      return;
    }

    if (status) status.textContent = "✅ Face verified successfully!";
    stopCamera();

  } catch (err) {
    console.error(err);
    if (status) status.textContent = "❌ Server error during verification.";
  }
}
async function captureAndLogin() {
  const status = document.getElementById("status");
  const image = captureImageBase64();

  if (!image) {
    if (status) status.textContent = "⚠ Please start camera first.";
    return;
  }

  if (status) status.textContent = "Verifying face for login...";

  try {
    const response = await fetch("/api/login-face-verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image })
    });

    const data = await response.json();

    if (!response.ok || !data.ok) {
      if (status) status.textContent = "❌ " + (data.error || "Login failed.");
      return;
    }

    if (status) status.textContent = "✅ Login successful! Redirecting...";
    stopCamera();

    setTimeout(() => window.location.href = "/elections", 1000);
  } catch (err) {
    console.error(err);
    if (status) status.textContent = "❌ Server error during login.";
  }
}