const runtimeCard = document.getElementById("runtimeCard");
const experimentsEl = document.getElementById("experiments");
const experimentSelect = document.getElementById("experimentId");
const backendSelect = document.getElementById("backendName");
const braketBackendSelect = document.getElementById("braketBackendName");
const runsEl = document.getElementById("runs");
const scorecardEl = document.getElementById("scorecard");
const ibmProofEl = document.getElementById("ibmProof");
const domainProofEl = document.getElementById("domainProof");
const latestResultEl = document.getElementById("latestResult");
const runStatusEl = document.getElementById("runStatus");

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `Request failed: ${response.status}`);
  }
  return data;
}

function renderRuntime(brief) {
  runtimeCard.innerHTML = `
    <p class="eyebrow">Runtime posture</p>
    <h2>${brief.mode === "hardware-ready" ? "Hardware-ready" : "Local review mode"}</h2>
    <p>${brief.summary}</p>
    <ul class="meta-list">
      <li><strong>IBM token:</strong> ${brief.hardware_support.ibm_quantum.token_configured ? "yes" : "no"}</li>
      <li><strong>AWS creds:</strong> ${brief.hardware_support.aws_braket.credentials_configured ? "yes" : "no"}</li>
      <li><strong>AWS region:</strong> ${brief.hardware_support.aws_braket.region}</li>
    </ul>
  `;
}

function renderExperiments(experiments) {
  experimentsEl.innerHTML = "";
  experimentSelect.innerHTML = "";
  experiments.forEach((experiment, index) => {
    const article = document.createElement("article");
    article.className = "card";
    article.innerHTML = `
      <p class="eyebrow">${experiment.category}</p>
      <h3>${experiment.title}</h3>
      <p>${experiment.summary}</p>
      <ul class="meta-list">
        <li><strong>Qubits:</strong> ${experiment.qubits}</li>
        <li><strong>Default shots:</strong> ${experiment.default_shots}</li>
      </ul>
    `;
    experimentsEl.appendChild(article);

    const option = document.createElement("option");
    option.value = experiment.experiment_id;
    option.textContent = experiment.title;
    option.selected = index === 0;
    experimentSelect.appendChild(option);
  });
}

function renderBackends(payload) {
  backendSelect.innerHTML = '<option value="">Auto-select least busy backend</option>';
  braketBackendSelect.innerHTML = '<option value="">Auto-select least busy Braket QPU</option>';
  if (payload.ibm_quantum?.configured) {
    payload.ibm_quantum.backends.forEach((backend) => {
      const option = document.createElement("option");
      option.value = backend.name;
      option.textContent = `${backend.name} · ${backend.num_qubits ?? "?"}q · pending ${backend.pending_jobs ?? "?"}`;
      backendSelect.appendChild(option);
    });
  }
  if (payload.aws_braket?.configured) {
    payload.aws_braket.backends.forEach((backend) => {
      const option = document.createElement("option");
      option.value = backend.arn;
      option.textContent = `${backend.provider_name || "QPU"} · ${backend.name} · ${backend.num_qubits ?? "?"}q`;
      braketBackendSelect.appendChild(option);
    });
  }
}

function renderRuns(runs) {
  runsEl.innerHTML = "";
  if (!runs.length) {
    runsEl.innerHTML = "<p class='muted'>No runs yet.</p>";
    return;
  }

  runs.forEach((run) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "run-row";
    row.innerHTML = `
      <span>
        <strong>${run.experiment_id}</strong>
        <small>${run.mode} · ${run.backend_name}</small>
      </span>
      <span>
        <strong>${run.status}</strong>
        <small>${new Date(run.updated_at).toLocaleString()}</small>
      </span>
    `;
    row.addEventListener("click", async () => {
      const detail = await fetchJson(`/api/runs/${run.run_id}`);
      latestResultEl.textContent = JSON.stringify(detail, null, 2);
    });
    runsEl.appendChild(row);
  });
}

function renderScorecard(scorecard) {
  scorecardEl.innerHTML = "";
  const summary = document.createElement("div");
  summary.className = "card";
  summary.innerHTML = `
    <h3>Summary</h3>
    <ul class="meta-list">
      <li><strong>Total runs:</strong> ${scorecard.summary.total_runs}</li>
      <li><strong>Completed local runs:</strong> ${scorecard.summary.completed_local_runs}</li>
      <li><strong>Completed hardware runs:</strong> ${scorecard.summary.completed_hardware_runs}</li>
    </ul>
  `;
  scorecardEl.appendChild(summary);

  scorecard.experiments.forEach((entry) => {
    const card = document.createElement("article");
    card.className = "card";
    card.innerHTML = `
      <p class="eyebrow">${entry.category}</p>
      <h3>${entry.title}</h3>
      <div class="meta-grid">
        ${renderScorecardCell("Qiskit local", entry.qiskit_local)}
        ${renderScorecardCell("Braket local", entry.braket_local)}
        ${renderScorecardCell("IBM hardware", entry.ibm_hardware)}
        ${renderScorecardCell("Braket hardware", entry.braket_hardware)}
      </div>
      ${entry.local_metric_delta !== undefined ? `<p class="muted">Local metric delta: ${entry.local_metric_delta}</p>` : ""}
    `;
    scorecardEl.appendChild(card);
  });
}

function renderIbmProof(proof) {
  ibmProofEl.textContent = JSON.stringify(proof, null, 2);
}

function renderDomainProof(proof) {
  domainProofEl.textContent = JSON.stringify(proof, null, 2);
}

function renderScorecardCell(label, item) {
  if (!item) {
    return `<div><strong>${label}</strong><small>no run yet</small></div>`;
  }
  const metric = item.metric_value !== undefined && item.metric_value !== null
    ? `${item.metric_name}: ${item.metric_value}`
    : item.status;
  const usage = item.usage_quantum_seconds !== undefined && item.usage_quantum_seconds !== null
    ? `<small>quantum_seconds: ${item.usage_quantum_seconds}</small>`
    : "";
  const options = item.ibm_options && (item.ibm_options.enable_twirling || item.ibm_options.enable_dynamical_decoupling)
    ? `<small>options: ${item.ibm_options.enable_twirling ? "twirling " : ""}${item.ibm_options.enable_dynamical_decoupling ? "dd" : ""}</small>`
    : "";
  return `<div><strong>${label}</strong><small>${item.backend_name}</small><small>${metric}</small>${usage}${options}</div>`;
}

function currentPayload(provider = "ibm") {
  return {
    experiment_id: experimentSelect.value,
    shots: Number(document.getElementById("shots").value || 1024),
    backend_name: provider === "braket" ? (braketBackendSelect.value || null) : (backendSelect.value || null),
    parameters: {
      gamma: Number(document.getElementById("gamma").value || 0.9),
      beta: Number(document.getElementById("beta").value || 0.35),
    },
    ibm_options: {
      enable_twirling: false,
      enable_dynamical_decoupling: false,
      job_tags: ["quantum-workbench", "review-surface"],
    },
  };
}

async function loadAll() {
  const [brief, experiments, backends, runs, scorecard] = await Promise.all([
    fetchJson("/api/runtime/brief"),
    fetchJson("/api/experiments"),
    fetchJson("/api/backends"),
    fetchJson("/api/runs"),
    fetchJson("/api/evidence/scorecard"),
  ]);
  renderRuntime(brief);
  renderExperiments(experiments);
  renderBackends(backends);
  renderRuns(runs);
  renderScorecard(scorecard);
  try {
    const ibmProof = await fetchJson("/api/ibm/proof-pack");
    renderIbmProof(ibmProof);
  } catch (error) {
    ibmProofEl.textContent = `IBM proof unavailable: ${error.message}`;
  }
  try {
    const domainProof = await fetchJson("/api/domain/h2-vqe-pack");
    renderDomainProof(domainProof);
  } catch (error) {
    domainProofEl.textContent = `Domain proof unavailable: ${error.message}`;
  }
}

async function runExperiment(path, provider = "ibm") {
  runStatusEl.textContent = "Running...";
  try {
    const payload = currentPayload(provider);
    const data = await fetchJson(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    latestResultEl.textContent = JSON.stringify(data, null, 2);
    runStatusEl.textContent = `${path.includes("hardware") ? "Hardware job submitted" : "Local run completed"}: ${data.run_id}`;
    const [runs, scorecard] = await Promise.all([fetchJson("/api/runs"), fetchJson("/api/evidence/scorecard")]);
    renderRuns(runs);
    renderScorecard(scorecard);
  } catch (error) {
    runStatusEl.textContent = error.message;
  }
}

document.getElementById("refreshExperiments").addEventListener("click", loadAll);
document.getElementById("refreshRuns").addEventListener("click", async () => {
  const runs = await fetchJson("/api/runs");
  renderRuns(runs);
});
document.getElementById("refreshScorecard").addEventListener("click", async () => {
  const scorecard = await fetchJson("/api/evidence/scorecard");
  renderScorecard(scorecard);
});
document.getElementById("refreshIbmProof").addEventListener("click", async () => {
  try {
    const proof = await fetchJson("/api/ibm/proof-pack");
    renderIbmProof(proof);
  } catch (error) {
    ibmProofEl.textContent = `IBM proof unavailable: ${error.message}`;
  }
});
document.getElementById("refreshDomainPack").addEventListener("click", async () => {
  try {
    const proof = await fetchJson("/api/domain/h2-vqe-pack");
    renderDomainProof(proof);
  } catch (error) {
    domainProofEl.textContent = `Domain proof unavailable: ${error.message}`;
  }
});
document.getElementById("runLocal").addEventListener("click", () => runExperiment("/api/runs/local", "ibm"));
document.getElementById("runBraketLocal").addEventListener("click", () => runExperiment("/api/runs/braket-local", "braket"));
document.getElementById("compareLocal").addEventListener("click", () => runExperiment("/api/compare/local-backends", "ibm"));
document.getElementById("runHardware").addEventListener("click", () => runExperiment("/api/runs/hardware", "ibm"));
document.getElementById("runBraketHardware").addEventListener("click", () => runExperiment("/api/runs/braket-hardware", "braket"));

loadAll().catch((error) => {
  runStatusEl.textContent = error.message;
});
