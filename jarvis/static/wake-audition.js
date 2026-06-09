(function () {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const state = {
    recognition: null,
    trialRecognition: null,
    mediaRecorder: null,
    mediaStream: null,
    chunks: [],
    lastBlob: null,
    lastBlobUrl: "",
    lastMimeType: "",
    runs: loadRuns(),
    runIndex: 0,
  };

  const els = {
    apiStatus: document.getElementById("api-status"),
    micStatus: document.getElementById("mic-status"),
    recognizerStatus: document.getElementById("recognizer-status"),
    threshold: document.getElementById("threshold-slider"),
    thresholdOutput: document.getElementById("threshold-output"),
    startListener: document.getElementById("start-listener"),
    stopListener: document.getElementById("stop-listener"),
    recordSample: document.getElementById("record-sample"),
    stopRecording: document.getElementById("stop-recording"),
    saveSample: document.getElementById("save-sample"),
    copyExport: document.getElementById("copy-export"),
    manualTranscript: document.getElementById("manual-transcript"),
    wakeResult: document.getElementById("wake-result"),
    scoreValue: document.getElementById("score-value"),
    phraseValue: document.getElementById("phrase-value"),
    commandValue: document.getElementById("command-value"),
    sampleStatus: document.getElementById("sample-status"),
    samplePlayer: document.getElementById("sample-player"),
    noise: document.getElementById("noise-slider"),
    noiseOutput: document.getElementById("noise-output"),
    playNoise: document.getElementById("play-noise"),
    loopbackTrial: document.getElementById("loopback-trial"),
    downloadSample: document.getElementById("download-sample"),
    trialStatus: document.getElementById("trial-status"),
    detectedSummary: document.getElementById("detected-summary"),
    noiseSummary: document.getElementById("noise-summary"),
    nextStepSummary: document.getElementById("next-step-summary"),
    runTable: document.getElementById("run-table"),
    runCount: document.getElementById("run-count"),
  };

  init();

  async function init() {
    setPill(els.recognizerStatus, SpeechRecognition ? "Ready" : "No Web Speech", SpeechRecognition ? "ok" : "fail");
    updateThreshold();
    updateNoise();
    renderRuns();
    bindEvents();
    await loadStatus();
  }

  function bindEvents() {
    els.threshold.addEventListener("input", () => {
      updateThreshold();
      scoreCurrentTranscript();
    });
    els.noise.addEventListener("input", updateNoise);
    els.manualTranscript.addEventListener("input", debounce(scoreCurrentTranscript, 180));
    els.startListener.addEventListener("click", startLiveListener);
    els.stopListener.addEventListener("click", stopLiveListener);
    els.recordSample.addEventListener("click", startRecording);
    els.stopRecording.addEventListener("click", stopRecording);
    els.saveSample.addEventListener("click", saveLastSample);
    els.copyExport.addEventListener("click", copyExport);
    els.playNoise.addEventListener("click", playNoiseMix);
    els.loopbackTrial.addEventListener("click", runLoopbackTrial);
    els.downloadSample.addEventListener("click", downloadLastSample);
  }

  async function loadStatus() {
    try {
      const response = await fetch("/api/wake-audition/status", { cache: "no-store" });
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      const data = await response.json();
      setPill(els.apiStatus, "API OK", "ok");
      if (typeof data.default_threshold === "number") {
        els.threshold.value = String(data.default_threshold);
        updateThreshold();
      }
    } catch (error) {
      setPill(els.apiStatus, "API Fail", "fail");
      els.trialStatus.textContent = "Wake audition API is unavailable: " + error;
    }
  }

  function startLiveListener() {
    if (!SpeechRecognition) {
      setPill(els.recognizerStatus, "No Web Speech", "fail");
      return;
    }
    stopLiveListener();
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onstart = () => {
      setPill(els.recognizerStatus, "Listening", "ok");
      els.startListener.disabled = true;
      els.stopListener.disabled = false;
    };
    recognition.onerror = (event) => {
      setPill(els.recognizerStatus, event.error || "Error", "fail");
    };
    recognition.onend = () => {
      if (state.recognition === recognition) {
        els.startListener.disabled = false;
        els.stopListener.disabled = true;
        setPill(els.recognizerStatus, "Stopped", "warn");
      }
    };
    recognition.onresult = (event) => {
      const text = transcriptFromEvent(event);
      if (text) {
        els.manualTranscript.value = text;
        scoreCurrentTranscript();
      }
    };
    state.recognition = recognition;
    recognition.start();
  }

  function stopLiveListener() {
    if (state.recognition) {
      const recognition = state.recognition;
      state.recognition = null;
      try {
        recognition.stop();
      } catch (_) {
        // Recognition may already be stopped.
      }
    }
    els.startListener.disabled = false;
    els.stopListener.disabled = true;
  }

  async function startRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      setPill(els.micStatus, "Unavailable", "fail");
      return;
    }
    try {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setPill(els.micStatus, "Recording", "ok");
      state.chunks = [];
      const mimeType = preferredMimeType();
      state.lastMimeType = mimeType || "audio/webm";
      state.mediaRecorder = new MediaRecorder(state.mediaStream, mimeType ? { mimeType } : undefined);
      state.mediaRecorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size > 0) {
          state.chunks.push(event.data);
        }
      });
      state.mediaRecorder.addEventListener("stop", finishRecording);
      state.mediaRecorder.start();
      els.recordSample.disabled = true;
      els.stopRecording.disabled = false;
      els.saveSample.disabled = true;
      if (SpeechRecognition && !state.recognition) {
        startLiveListener();
      }
    } catch (error) {
      setPill(els.micStatus, "Denied", "fail");
      els.trialStatus.textContent = "Microphone recording failed: " + error;
    }
  }

  function stopRecording() {
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      state.mediaRecorder.stop();
    }
    if (state.mediaStream) {
      for (const track of state.mediaStream.getTracks()) {
        track.stop();
      }
      state.mediaStream = null;
    }
    els.recordSample.disabled = false;
    els.stopRecording.disabled = true;
  }

  function finishRecording() {
    if (!state.chunks.length) {
      setPill(els.sampleStatus, "Empty", "fail");
      return;
    }
    state.lastBlob = new Blob(state.chunks, { type: state.lastMimeType || state.chunks[0].type || "audio/webm" });
    if (state.lastBlobUrl) {
      URL.revokeObjectURL(state.lastBlobUrl);
    }
    state.lastBlobUrl = URL.createObjectURL(state.lastBlob);
    els.samplePlayer.src = state.lastBlobUrl;
    els.saveSample.disabled = false;
    els.playNoise.disabled = false;
    els.loopbackTrial.disabled = false;
    els.downloadSample.disabled = false;
    setPill(els.sampleStatus, Math.round(state.lastBlob.size / 1024) + " KB", "ok");
    setPill(els.micStatus, "Ready", "ok");
    scoreCurrentTranscript();
  }

  async function saveLastSample() {
    if (!state.lastBlob) {
      return;
    }
    try {
      const sampleId = "wake-" + new Date().toISOString().replace(/[^0-9]/g, "").slice(0, 14) + "-" + shortId();
      const audioBase64 = await blobToDataURL(state.lastBlob);
      const transcript = els.manualTranscript.value.trim();
      const payload = {
        sample_id: sampleId,
        mime_type: state.lastBlob.type || state.lastMimeType || "audio/webm",
        audio_base64: audioBase64,
        transcript,
        threshold: numericThreshold(),
        noise_db: null,
        source: "wake-audition-page",
      };
      const response = await fetch("/api/wake-audition/sample", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "HTTP " + response.status);
      }
      addRun({
        type: "recording",
        transcript,
        score: data.score,
        noise_db: null,
        detected: data.score && data.score.detected,
        audio_path: data.audio_path,
        metadata_path: data.metadata_path,
      });
      setPill(els.sampleStatus, "Saved", "ok");
    } catch (error) {
      setPill(els.sampleStatus, "Save failed", "fail");
      els.trialStatus.textContent = "Save failed: " + error;
    }
  }

  async function scoreCurrentTranscript() {
    const transcript = els.manualTranscript.value.trim();
    if (!transcript) {
      applyScore({ detected: false, score: 0, phrase: null, command: "" });
      return null;
    }
    try {
      const response = await fetch("/api/wake-audition/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript,
          threshold: numericThreshold(),
          noise_db: null,
        }),
      });
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      const data = await response.json();
      applyScore(data);
      return data;
    } catch (error) {
      setPill(els.wakeResult, "Score error", "fail");
      return null;
    }
  }

  function applyScore(data) {
    const score = typeof data.score === "number" ? data.score : 0;
    els.scoreValue.textContent = score.toFixed(3);
    els.phraseValue.textContent = data.phrase || "none";
    els.commandValue.textContent = data.command || "none";
    setPill(els.wakeResult, data.detected ? "Detected" : "Below", data.detected ? "ok" : "warn");
  }

  async function playNoiseMix() {
    if (!state.lastBlob) {
      return;
    }
    await playBlobWithNoise(state.lastBlob, numericNoiseDb());
  }

  async function runLoopbackTrial() {
    if (!state.lastBlob || !SpeechRecognition) {
      return;
    }
    els.trialStatus.textContent = "Loopback trial running...";
    const transcript = await recognizeDuringPlayback(() => playBlobWithNoise(state.lastBlob, numericNoiseDb()));
    els.manualTranscript.value = transcript;
    const score = await scoreCurrentTranscript();
    addRun({
      type: "noise trial",
      transcript,
      score,
      noise_db: numericNoiseDb(),
      detected: score && score.detected,
      audio_path: "browser playback loopback",
      metadata_path: "",
    });
    els.trialStatus.textContent = transcript
      ? "Loopback transcript: " + transcript
      : "Loopback trial produced no transcript.";
  }

  async function recognizeDuringPlayback(playback) {
    return new Promise((resolve) => {
      const recognition = new SpeechRecognition();
      let best = "";
      let done = false;
      const finish = () => {
        if (done) {
          return;
        }
        done = true;
        try {
          recognition.stop();
        } catch (_) {
          // Recognition may already be stopped.
        }
        state.trialRecognition = null;
        resolve(best.trim());
      };
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";
      recognition.onresult = (event) => {
        const text = transcriptFromEvent(event);
        if (text) {
          best = text;
        }
      };
      recognition.onerror = finish;
      recognition.onend = () => {
        if (!done) {
          setTimeout(finish, 250);
        }
      };
      state.trialRecognition = recognition;
      recognition.start();
      setTimeout(async () => {
        try {
          await playback();
        } catch (_) {
          // Playback failure is surfaced by the empty transcript/state below.
        }
        setTimeout(finish, 950);
      }, 250);
      setTimeout(finish, 9000);
    });
  }

  async function playBlobWithNoise(blob, noiseDb) {
    const context = new AudioContext();
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await context.decodeAudioData(arrayBuffer.slice(0));
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    const noise = context.createBufferSource();
    noise.buffer = noiseBuffer(context, audioBuffer.duration || 1);
    const speechGain = context.createGain();
    const noiseGain = context.createGain();
    speechGain.gain.value = 0.78;
    noiseGain.gain.value = Math.max(0, Math.min(1.2, Math.pow(10, noiseDb / 20)));
    source.connect(speechGain).connect(context.destination);
    noise.connect(noiseGain).connect(context.destination);
    source.start();
    noise.start();
    await new Promise((resolve) => {
      source.onended = resolve;
    });
    noise.stop();
    await context.close();
  }

  function noiseBuffer(context, seconds) {
    const length = Math.max(1, Math.floor(context.sampleRate * seconds));
    const buffer = context.createBuffer(1, length, context.sampleRate);
    const data = buffer.getChannelData(0);
    for (let index = 0; index < data.length; index += 1) {
      data[index] = (Math.random() * 2 - 1) * 0.55;
    }
    return buffer;
  }

  function downloadLastSample() {
    if (!state.lastBlobUrl) {
      return;
    }
    const link = document.createElement("a");
    link.href = state.lastBlobUrl;
    link.download = "hey-jarvis-" + shortId() + extensionForMime(state.lastBlob.type);
    link.click();
  }

  async function copyExport() {
    const payload = {
      artifact: "Jarvis Wake Audition",
      exported_at: new Date().toISOString(),
      threshold: numericThreshold(),
      runs: state.runs,
    };
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    els.runCount.textContent = state.runs.length + " copied";
  }

  function addRun(run) {
    const item = {
      id: ++state.runIndex,
      created_at: new Date().toISOString(),
      type: run.type,
      transcript: run.transcript || "",
      score: run.score || null,
      noise_db: run.noise_db,
      detected: Boolean(run.detected),
      audio_path: run.audio_path || "",
      metadata_path: run.metadata_path || "",
    };
    state.runs.unshift(item);
    state.runs = state.runs.slice(0, 80);
    saveRuns();
    renderRuns();
  }

  function renderRuns() {
    els.runTable.innerHTML = "";
    state.runs.forEach((run, index) => {
      const row = document.createElement("tr");
      const scoreText = run.score && typeof run.score.score === "number" ? run.score.score.toFixed(3) : "";
      const fileText = run.audio_path ? run.audio_path.split("/").slice(-1)[0] : "";
      row.append(
        cell(String(index + 1)),
        cell(run.type),
        cell(run.transcript),
        cell(scoreText),
        cell(run.noise_db === null || run.noise_db === undefined ? "" : String(run.noise_db) + " dB"),
        cell(run.detected ? "yes" : "no"),
        cell(fileText)
      );
      els.runTable.appendChild(row);
    });
    els.runCount.textContent = state.runs.length + " saved";
    renderDecisionSummary();
  }

  function renderDecisionSummary() {
    const total = state.runs.length;
    const detectedRuns = state.runs.filter((run) => run.detected);
    els.detectedSummary.textContent = detectedRuns.length + " / " + total;
    const noisyDetected = detectedRuns
      .filter((run) => typeof run.noise_db === "number")
      .sort((a, b) => b.noise_db - a.noise_db);
    if (noisyDetected.length) {
      const best = noisyDetected[0];
      const score = best.score && typeof best.score.score === "number" ? " at " + best.score.score.toFixed(3) : "";
      els.noiseSummary.textContent = best.noise_db + " dB" + score;
    } else {
      els.noiseSummary.textContent = "none";
    }
    els.nextStepSummary.textContent = recommendationForRuns(total, detectedRuns.length, noisyDetected);
  }

  function recommendationForRuns(total, detectedCount, noisyDetected) {
    if (total === 0) {
      return "record a clean sample";
    }
    if (detectedCount === 0) {
      return "lower threshold or improve mic placement";
    }
    if (detectedCount < Math.ceil(total * 0.7)) {
      return "record more clean samples before raising threshold";
    }
    if (!noisyDetected.length) {
      return "run noise trials";
    }
    if (noisyDetected[0].noise_db >= -12) {
      return "threshold looks usable; test real room noise";
    }
    return "try stronger noise trials";
  }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text || "";
    return td;
  }

  function transcriptFromEvent(event) {
    let finalText = "";
    let interimText = "";
    for (let index = 0; index < event.results.length; index += 1) {
      const result = event.results[index];
      const text = result[0] && result[0].transcript ? result[0].transcript.trim() : "";
      if (result.isFinal) {
        finalText += " " + text;
      } else {
        interimText += " " + text;
      }
    }
    return (finalText || interimText).replace(/\s+/g, " ").trim();
  }

  function preferredMimeType() {
    const options = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    return options.find((value) => MediaRecorder.isTypeSupported(value)) || "";
  }

  function blobToDataURL(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  function updateThreshold() {
    els.thresholdOutput.textContent = numericThreshold().toFixed(3);
  }

  function updateNoise() {
    els.noiseOutput.textContent = String(numericNoiseDb()) + " dB";
  }

  function numericThreshold() {
    return Number.parseFloat(els.threshold.value || "0.82");
  }

  function numericNoiseDb() {
    return Number.parseInt(els.noise.value || "-18", 10);
  }

  function setPill(element, text, kind) {
    element.textContent = text;
    element.classList.remove("ok", "warn", "fail");
    if (kind) {
      element.classList.add(kind);
    }
  }

  function shortId() {
    return Math.random().toString(36).slice(2, 8);
  }

  function extensionForMime(mime) {
    if ((mime || "").includes("mp4")) {
      return ".m4a";
    }
    if ((mime || "").includes("mpeg") || (mime || "").includes("mp3")) {
      return ".mp3";
    }
    if ((mime || "").includes("wav")) {
      return ".wav";
    }
    if ((mime || "").includes("ogg")) {
      return ".ogg";
    }
    return ".webm";
  }

  function loadRuns() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem("jarvis-wake-audition-runs") || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function saveRuns() {
    window.localStorage.setItem("jarvis-wake-audition-runs", JSON.stringify(state.runs));
  }

  function debounce(fn, wait) {
    let timer = 0;
    return function debounced() {
      window.clearTimeout(timer);
      timer = window.setTimeout(fn, wait);
    };
  }
})();
