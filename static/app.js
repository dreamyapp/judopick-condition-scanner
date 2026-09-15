const state = {
  conditions: [],
  selectedId: null,
  draft: null,
  fields: [],
  operators: [],
  credentialsConfigured: false,
  activeJobId: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const unitDefinitions = {
  price: [{ value: 1, label: "원" }, { value: 10000, label: "만원" }],
  change_rate: [{ value: 1, label: "%" }],
  volume: [{ value: 1, label: "주" }, { value: 10000, label: "만 주" }, { value: 1000000, label: "백만 주" }],
  trading_value: [{ value: 1, label: "원" }, { value: 100000000, label: "억 원" }],
  market_cap: [{ value: 1, label: "원" }, { value: 100000000, label: "억 원" }],
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("프로그램 응답을 확인하지 못했습니다.");
  }
  if (!response.ok || !data.ok) throw new Error(data.message || "요청을 처리하지 못했습니다.");
  return data;
}

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 3500);
}

function setBusy(button, busy, busyText = "처리 중…") {
  if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? busyText : button.dataset.originalText;
}

function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

async function loadBootstrap(selectId = state.selectedId) {
  const data = await api("/api/bootstrap");
  state.conditions = data.conditions;
  state.fields = data.fields;
  state.operators = data.operators;
  state.credentialsConfigured = data.credentials.configured;
  updateConnectionStatus(data.credentials);
  renderConditionList();
  if (selectId) {
    const item = state.conditions.find((condition) => condition.id === selectId);
    if (item) selectCondition(item.id);
  }
  return data;
}

function updateConnectionStatus(credentials) {
  const status = $("#connectionStatus");
  if (credentials.configured) {
    if (credentials.mode === "mock") {
      status.textContent = "키움 모의투자 연결됨";
    } else {
      status.textContent = credentials.source === "personal" ? "개인 API 연결됨" : "주도픽 API 연결됨";
    }
    status.className = "status-pill status-on";
  } else {
    status.textContent = "키움 연결 필요";
    status.className = "status-pill status-off";
  }
}

function renderConditionList() {
  $("#conditionCount").textContent = `${state.conditions.length}개`;
  const list = $("#conditionList");
  if (!state.conditions.length) {
    list.innerHTML = '<div class="rule-empty">아직 저장된 조건식이 없습니다.</div>';
    return;
  }
  list.innerHTML = state.conditions.map((condition) => `
    <button class="condition-item ${state.selectedId === condition.id ? "active" : ""}" data-id="${escapeHtml(condition.id)}" type="button">
      ${condition.mode === "kiwoom" ? '<span class="condition-mode">영웅문</span>' : ""}
      <strong>${escapeHtml(condition.name)}</strong>
      <span>${escapeHtml(condition.summary)}</span>
    </button>
  `).join("");
  $$(".condition-item").forEach((button) => {
    button.addEventListener("click", () => selectCondition(button.dataset.id));
  });
}

function newCondition() {
  state.selectedId = null;
  state.draft = {
    id: null,
    name: "",
    mode: "custom",
    raw_text: "",
    rules: [{ field: "change_rate", operator: "gte", value: 3 }],
    markets: ["KOSPI", "KOSDAQ"],
    exclusions: ["ETF", "ETN", "스팩"],
  };
  renderConditionList();
  renderEditor();
  setTimeout(() => $("#conditionName").focus(), 0);
}

function selectCondition(conditionId) {
  const condition = state.conditions.find((item) => item.id === conditionId);
  if (!condition) return;
  state.selectedId = conditionId;
  state.draft = deepCopy(condition);
  renderConditionList();
  renderEditor();
}

function renderEditor() {
  $("#welcomePanel").classList.add("hidden");
  $("#editorPanel").classList.remove("hidden");
  $("#resultsSection").classList.add("hidden");
  $("#searchReady").classList.remove("hidden");
  $("#searchProgress").classList.add("hidden");

  const isKiwoom = state.draft.mode === "kiwoom";
  $("#conditionName").value = state.draft.name || "";
  $("#conditionName").disabled = isKiwoom;
  $("#conditionTypeBadge").textContent = isKiwoom ? "영웅문 조건식" : "직접 만든 조건식";
  $("#kiwoomInfo").classList.toggle("hidden", !isKiwoom);
  $("#customEditor").classList.toggle("hidden", isKiwoom);
  $("#saveButton").classList.toggle("hidden", isKiwoom);
  $("#copyButton").classList.toggle("hidden", isKiwoom);
  $("#deleteButton").classList.toggle("hidden", !state.draft.id);

  if (!isKiwoom) {
    $("#marketKospi").checked = state.draft.markets.includes("KOSPI");
    $("#marketKosdaq").checked = state.draft.markets.includes("KOSDAQ");
    $$(".exclusion-check").forEach((input) => {
      input.checked = state.draft.exclusions.includes(input.value);
    });
    $("#conditionText").value = state.draft.raw_text || "";
    $("#parsePreview").classList.add("hidden");
    activateTab("simple");
    renderRules();
  }
}

function chooseUnit(rule) {
  const units = unitDefinitions[rule.field] || [{ value: 1, label: "" }];
  if (rule._unit && units.some((item) => item.value === rule._unit)) return rule._unit;
  const preferred = [...units].reverse().find((item) => Math.abs(Number(rule.value || 0)) >= item.value);
  return (preferred || units[0]).value;
}

function renderRules() {
  const list = $("#ruleList");
  if (!state.draft.rules.length) {
    list.innerHTML = '<div class="rule-empty">조건을 한 개 이상 추가해 주세요.</div>';
    return;
  }
  list.innerHTML = state.draft.rules.map((rule, index) => {
    const unit = chooseUnit(rule);
    rule._unit = unit;
    const range = rule.operator === "between";
    const fieldOptions = state.fields.map((field) => `<option value="${field.value}" ${field.value === rule.field ? "selected" : ""}>${field.label}</option>`).join("");
    const operatorOptions = state.operators.map((operator) => `<option value="${operator.value}" ${operator.value === rule.operator ? "selected" : ""}>${operator.label}</option>`).join("");
    const unitOptions = (unitDefinitions[rule.field] || []).map((item) => `<option value="${item.value}" ${item.value === unit ? "selected" : ""}>${item.label}</option>`).join("");
    return `
      <div class="rule-row ${range ? "range" : ""}" data-index="${index}">
        <select class="rule-field" aria-label="조건 항목">${fieldOptions}</select>
        <select class="rule-operator" aria-label="비교 방법">${operatorOptions}</select>
        <input class="value-input rule-value" type="number" step="any" value="${Number(rule.value || 0) / unit}" aria-label="조건 값">
        ${range ? `<span class="range-separator">~</span><input class="value-input rule-value2" type="number" step="any" value="${Number(rule.value2 || 0) / unit}" aria-label="범위 끝 값">` : ""}
        <select class="rule-unit" aria-label="단위">${unitOptions}</select>
        <button class="remove-rule" type="button" aria-label="이 조건 삭제">×</button>
      </div>`;
  }).join("");

  $$(".rule-row").forEach((row) => {
    const index = Number(row.dataset.index);
    row.querySelector(".rule-field").addEventListener("change", (event) => {
      state.draft.rules[index] = { field: event.target.value, operator: "gte", value: 0 };
      renderRules();
    });
    row.querySelector(".rule-operator").addEventListener("change", (event) => {
      syncRuleRow(row, index);
      state.draft.rules[index].operator = event.target.value;
      if (event.target.value === "between" && state.draft.rules[index].value2 == null) {
        state.draft.rules[index].value2 = state.draft.rules[index].value;
      }
      renderRules();
    });
    row.querySelector(".rule-unit").addEventListener("change", (event) => {
      syncRuleRow(row, index);
      state.draft.rules[index]._unit = Number(event.target.value);
      renderRules();
    });
    row.querySelectorAll("input").forEach((input) => input.addEventListener("input", () => syncRuleRow(row, index)));
    row.querySelector(".remove-rule").addEventListener("click", () => {
      state.draft.rules.splice(index, 1);
      renderRules();
    });
  });
}

function syncRuleRow(row, index) {
  const unit = Number(row.querySelector(".rule-unit").value || 1);
  const rule = state.draft.rules[index];
  rule.value = Number(row.querySelector(".rule-value").value || 0) * unit;
  rule._unit = unit;
  const value2 = row.querySelector(".rule-value2");
  if (value2) rule.value2 = Number(value2.value || 0) * unit;
}

function syncDraftFromForm() {
  if (!state.draft || state.draft.mode === "kiwoom") return;
  $$(".rule-row").forEach((row) => syncRuleRow(row, Number(row.dataset.index)));
  state.draft.name = $("#conditionName").value.trim();
  state.draft.raw_text = $("#conditionText").value.trim();
  state.draft.markets = [
    $("#marketKospi").checked ? "KOSPI" : null,
    $("#marketKosdaq").checked ? "KOSDAQ" : null,
  ].filter(Boolean);
  state.draft.exclusions = $$(".exclusion-check:checked").map((input) => input.value);
}

function activateTab(name) {
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  $("#simpleTab").classList.toggle("hidden", name !== "simple");
  $("#pasteTab").classList.toggle("hidden", name !== "paste");
}

async function parsePastedCondition() {
  const button = $("#parseButton");
  const text = $("#conditionText").value.trim();
  setBusy(button, true, "확인 중…");
  try {
    const data = await api("/api/parse", { method: "POST", body: JSON.stringify({ text }) });
    const parsed = data.parsed;
    state.draft.raw_text = text;
    state.draft.rules = parsed.rules;
    state.draft.markets = parsed.markets;
    state.draft.exclusions = parsed.exclusions;
    if (parsed.name) {
      state.draft.name = parsed.name;
      $("#conditionName").value = parsed.name;
    }
    renderParsePreview(parsed);
    showToast("조건식을 확인했습니다.");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function renderParsePreview(parsed) {
  const preview = $("#parsePreview");
  const marketLabel = parsed.markets.map((item) => item === "KOSPI" ? "코스피" : "코스닥").join(", ");
  const chips = [
    marketLabel ? `시장: ${marketLabel}` : "",
    ...parsed.rules.map((rule) => rule.label),
    parsed.exclusions.length ? `제외: ${parsed.exclusions.join(", ")}` : "",
  ].filter(Boolean);
  const warnings = parsed.warnings.length
    ? `<ul class="warning-list">${parsed.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>`
    : "";
  preview.innerHTML = `
    <h3>이렇게 이해했습니다</h3>
    <div class="preview-chips">${chips.map((chip) => `<span class="preview-chip">${escapeHtml(chip)}</span>`).join("")}</div>
    ${warnings}`;
  preview.classList.remove("hidden");
}

async function saveCondition() {
  if (!state.draft) return null;
  if (state.draft.mode === "kiwoom") return state.draft;
  syncDraftFromForm();
  if (!state.draft.name) {
    showToast("조건식 이름을 입력해 주세요.", true);
    $("#conditionName").focus();
    return null;
  }
  if (!state.draft.markets.length) {
    showToast("코스피 또는 코스닥을 선택해 주세요.", true);
    return null;
  }
  if (!state.draft.rules.length) {
    showToast("검색 조건을 한 개 이상 추가해 주세요.", true);
    return null;
  }
  const payload = { ...state.draft, id: undefined };
  const url = state.draft.id ? `/api/conditions/${state.draft.id}` : "/api/conditions";
  const method = state.draft.id ? "PUT" : "POST";
  try {
    const data = await api(url, { method, body: JSON.stringify(payload) });
    state.selectedId = data.condition.id;
    state.draft = deepCopy(data.condition);
    await loadBootstrap(state.selectedId);
    showToast("조건식을 저장했습니다.");
    return data.condition;
  } catch (error) {
    showToast(error.message, true);
    return null;
  }
}

async function deleteCondition() {
  if (!state.draft?.id) return;
  if (!confirm(`'${state.draft.name}' 조건식을 삭제할까요?`)) return;
  try {
    await api(`/api/conditions/${state.draft.id}`, { method: "DELETE" });
    state.selectedId = null;
    state.draft = null;
    $("#editorPanel").classList.add("hidden");
    $("#welcomePanel").classList.remove("hidden");
    await loadBootstrap(null);
    showToast("조건식을 삭제했습니다.");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function copyCondition() {
  const saved = await saveCondition();
  if (!saved) return;
  try {
    const data = await api(`/api/conditions/${saved.id}/export`);
    await copyText(data.text);
    showToast("조건식을 복사했습니다.");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const textarea = document.createElement("textarea");
  textarea.value = text;
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

async function importKiwoomConditions() {
  if (!state.credentialsConfigured) {
    openSettings();
    showToast("먼저 키움 연결 정보를 설정해 주세요.", true);
    return;
  }
  const button = $("#importKiwoomButton");
  setBusy(button, true, "불러오는 중…");
  try {
    const data = await api("/api/conditions/import-kiwoom", { method: "POST", body: "{}" });
    await loadBootstrap();
    showToast(data.message);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

async function startSearch() {
  if (!state.credentialsConfigured) {
    openSettings();
    showToast("먼저 키움 연결 정보를 설정해 주세요.", true);
    return;
  }
  const condition = await saveCondition();
  if (!condition) return;
  $("#resultsSection").classList.add("hidden");
  $("#searchReady").classList.add("hidden");
  $("#searchProgress").classList.remove("hidden");
  updateProgress(1, "검색을 시작합니다.");
  try {
    const data = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({ condition_id: condition.id }),
    });
    state.activeJobId = data.job_id;
    pollSearch(data.job_id);
  } catch (error) {
    finishSearchError(error.message);
  }
}

function updateProgress(percent, message) {
  $("#progressBar").style.width = `${Math.max(0, Math.min(100, percent))}%`;
  $("#progressPercent").textContent = `${percent}%`;
  $("#progressMessage").textContent = message;
}

async function pollSearch(jobId) {
  if (state.activeJobId !== jobId) return;
  try {
    const data = await api(`/api/search/${jobId}`);
    const job = data.job;
    updateProgress(job.progress || 0, job.message || "종목을 찾고 있습니다.");
    if (job.status === "done") {
      state.activeJobId = null;
      renderResults(job.results || [], job.finished_at);
      return;
    }
    if (job.status === "error") {
      state.activeJobId = null;
      finishSearchError(job.message);
      return;
    }
    setTimeout(() => pollSearch(jobId), 700);
  } catch (error) {
    state.activeJobId = null;
    finishSearchError(error.message);
  }
}

function finishSearchError(message) {
  $("#searchProgress").classList.add("hidden");
  $("#searchReady").classList.remove("hidden");
  showToast(message, true);
}

function formatNumber(value) {
  return Math.round(Number(value || 0)).toLocaleString("ko-KR");
}

function formatMoney(value) {
  const number = Number(value || 0);
  if (number >= 1_000_000_000_000) return `${(number / 1_000_000_000_000).toFixed(1)}조`;
  if (number >= 100_000_000) return `${(number / 100_000_000).toFixed(1)}억`;
  if (number >= 10_000) return `${(number / 10_000).toFixed(0)}만`;
  return formatNumber(number);
}

function renderResults(results, finishedAt) {
  $("#searchProgress").classList.add("hidden");
  $("#searchReady").classList.remove("hidden");
  $("#resultsSection").classList.remove("hidden");
  $("#resultsTitle").textContent = `${results.length.toLocaleString("ko-KR")}개 종목을 찾았습니다`;
  const date = finishedAt ? new Date(finishedAt) : new Date();
  $("#resultsTime").textContent = `${date.toLocaleString("ko-KR")} 기준`;
  $("#resultsEmpty").classList.toggle("hidden", results.length > 0);
  $("#resultsTableWrap").classList.toggle("hidden", results.length === 0);
  $("#resultsBody").innerHTML = results.map((stock) => {
    const rate = Number(stock.change_rate || 0);
    const rateClass = rate > 0 ? "rate-up" : rate < 0 ? "rate-down" : "";
    const ratePrefix = rate > 0 ? "+" : "";
    return `<tr>
      <td class="stock-name"><strong>${escapeHtml(stock.name || stock.code)}</strong><span>${escapeHtml(stock.code)}</span></td>
      <td>${formatNumber(stock.price)}원</td>
      <td class="${rateClass}">${ratePrefix}${rate.toFixed(2)}%</td>
      <td>${formatNumber(stock.volume)}주</td>
      <td>${formatMoney(stock.trading_value)}원</td>
      <td>${escapeHtml(stock.found_at || "-")}</td>
    </tr>`;
  }).join("");
  $("#resultsSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

function openSettings() {
  const message = $("#settingsMessage");
  message.className = "inline-message hidden";
  message.textContent = "";
  $("#appKey").value = "";
  $("#secretKey").value = "";
  $("#keyFilesInput").value = "";
  $("#manualKeyDetails").open = false;
  $("#settingsTitle").textContent = state.credentialsConfigured ? "API 키 변경" : "키움 API 키 연결";
  $("#settingsIntro").textContent = state.credentialsConfigured
    ? "새 키를 입력하면 기존 연결 정보가 변경됩니다."
    : "처음 한 번만 입력하면 다음부터 자동으로 연결됩니다.";
  delete $("#saveSettingsButton").dataset.originalText;
  $("#saveSettingsButton").textContent = state.credentialsConfigured ? "변경하고 시작" : "저장하고 시작";
  $("#settingsModal").classList.remove("hidden");
  setTimeout(() => $("#autoFindKeysButton").focus(), 0);
}

function closeSettings() {
  $("#settingsModal").classList.add("hidden");
}

function openGuide() {
  $("#guideModal").classList.remove("hidden");
  $("#guideModal .guide-scroll").scrollTop = 0;
  setTimeout(() => $("#closeGuideButton").focus(), 0);
}

function closeGuide() {
  $("#guideModal").classList.add("hidden");
}

function showSettingsMessage(text, isError = false) {
  const message = $("#settingsMessage");
  message.textContent = text;
  message.className = `inline-message${isError ? " error" : ""}`;
}

async function connectAndStoreKeys(appKey, secretKey, useMock) {
  return api("/api/settings/credentials", {
    method: "POST",
    body: JSON.stringify({ app_key: appKey, secret_key: secretKey, use_mock: useMock }),
  });
}

async function autoFindDownloadedKeys() {
  const button = $("#autoFindKeysButton");
  setBusy(button, true, "키 파일 찾는 중…");
  showSettingsMessage("다운로드 폴더에서 키움 키 파일 2개를 찾고 있습니다.");
  try {
    const result = await api("/api/settings/import-downloaded", {
      method: "POST",
      body: JSON.stringify({ use_mock: $("#useMock").checked }),
    });
    await loadBootstrap();
    showSettingsMessage(`✓ ${result.message} 계좌 ${result.account_hint}`);
    showToast("키 파일을 자동으로 찾아 연결했습니다.");
    setTimeout(closeSettings, 1400);
  } catch (error) {
    showSettingsMessage(`${error.message} 아래의 ‘키 파일 2개 직접 선택’을 눌러도 됩니다.`, true);
  } finally {
    setBusy(button, false);
  }
}

function keyValueFromFileText(text) {
  const lines = String(text).split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (const line of lines) {
    if (line.includes("=")) return line.slice(line.indexOf("=") + 1).trim().replace(/^["']|["']$/g, "");
    if (line.includes(":")) {
      const value = line.slice(line.indexOf(":") + 1).trim().replace(/^["']|["']$/g, "");
      if (value && !value.includes(" ")) return value;
    }
  }
  if (lines.length === 1) return lines[0].replace(/^["']|["']$/g, "");
  const candidates = String(text).match(/[A-Za-z0-9_-]{20,}/g) || [];
  return candidates.sort((a, b) => b.length - a.length)[0] || "";
}

async function importSelectedKeyFiles(event) {
  const files = Array.from(event.target.files || []);
  const appKeyFile = files.find((file) => /_appkey(?: \(\d+\))?\.txt$/i.test(file.name));
  const appSecretFile = files.find((file) => /_appsecret(?: \(\d+\))?\.txt$/i.test(file.name));
  if (!appKeyFile || !appSecretFile) {
    showSettingsMessage("App Key 파일과 App Secret 파일을 2개 모두 선택해 주세요.", true);
    return;
  }

  const button = $("#selectKeyFilesButton");
  setBusy(button, true, "파일 확인 중…");
  try {
    const [appKeyText, appSecretText] = await Promise.all([appKeyFile.text(), appSecretFile.text()]);
    const appKey = keyValueFromFileText(appKeyText);
    const secretKey = keyValueFromFileText(appSecretText);
    if (!appKey || !secretKey) throw new Error("선택한 파일에서 키 값을 찾지 못했습니다.");
    const result = await connectAndStoreKeys(appKey, secretKey, $("#useMock").checked);
    await loadBootstrap();
    showSettingsMessage(`✓ ${result.message}`);
    showToast("선택한 키 파일로 연결했습니다.");
    setTimeout(closeSettings, 1400);
  } catch (error) {
    showSettingsMessage(error.message, true);
  } finally {
    setBusy(button, false);
    event.target.value = "";
  }
}

async function openDownloads() {
  try {
    await api("/api/settings/open-downloads", { method: "POST", body: "{}" });
  } catch (error) {
    showSettingsMessage(error.message, true);
  }
}

async function saveSettings(testAfter = false) {
  const appKey = $("#appKey").value.trim();
  const secretKey = $("#secretKey").value.trim();
  const useMock = $("#useMock").checked;
  const button = testAfter ? $("#testConnectionButton") : $("#saveSettingsButton");
  setBusy(button, true, testAfter ? "확인 중…" : "저장 중…");
  try {
    if (appKey || secretKey) {
      const result = await connectAndStoreKeys(appKey, secretKey, useMock);
      showSettingsMessage(`✓ ${result.message}`);
    } else if (!testAfter) {
      throw new Error("변경할 App Key와 App Secret을 입력해 주세요.");
    } else if (!state.credentialsConfigured) {
      throw new Error("App Key와 App Secret을 모두 입력해 주세요.");
    } else {
      const result = await api("/api/settings/test", { method: "POST", body: "{}" });
      showSettingsMessage(`✓ ${result.message}`);
    }
    await loadBootstrap();
    if (!testAfter) {
      closeSettings();
      showToast("API 키를 저장하고 연결했습니다.");
    }
  } catch (error) {
    showSettingsMessage(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function bindEvents() {
  $("#newConditionButton").addEventListener("click", newCondition);
  $("#welcomeNewButton").addEventListener("click", newCondition);
  $("#importKiwoomButton").addEventListener("click", importKiwoomConditions);
  $("#addRuleButton").addEventListener("click", () => {
    state.draft.rules.push({ field: "price", operator: "gte", value: 10000 });
    renderRules();
  });
  $$(".tab").forEach((button) => button.addEventListener("click", () => activateTab(button.dataset.tab)));
  $("#parseButton").addEventListener("click", parsePastedCondition);
  $("#saveButton").addEventListener("click", saveCondition);
  $("#deleteButton").addEventListener("click", deleteCondition);
  $("#copyButton").addEventListener("click", copyCondition);
  $("#searchButton").addEventListener("click", startSearch);
  $("#searchAgainButton").addEventListener("click", startSearch);
  $("#settingsButton").addEventListener("click", openSettings);
  $("#autoFindKeysButton").addEventListener("click", autoFindDownloadedKeys);
  $("#selectKeyFilesButton").addEventListener("click", () => $("#keyFilesInput").click());
  $("#keyFilesInput").addEventListener("change", importSelectedKeyFiles);
  $("#openDownloadsButton").addEventListener("click", openDownloads);
  $("#guideButton").addEventListener("click", openGuide);
  $("#openGuideFromSettings").addEventListener("click", openGuide);
  $("#closeGuideButton").addEventListener("click", closeGuide);
  $("#closeSettingsButton").addEventListener("click", closeSettings);
  $("#settingsModal").addEventListener("click", (event) => {
    if (event.target === $("#settingsModal")) closeSettings();
  });
  $("#guideModal").addEventListener("click", (event) => {
    if (event.target === $("#guideModal")) closeGuide();
  });
  $("#saveSettingsButton").addEventListener("click", () => saveSettings(false));
  $("#testConnectionButton").addEventListener("click", () => saveSettings(true));
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!$("#guideModal").classList.contains("hidden")) closeGuide();
    else if (!$("#settingsModal").classList.contains("hidden")) closeSettings();
  });
}

async function initialize() {
  bindEvents();
  try {
    const data = await loadBootstrap();
    if (!data.credentials.configured) openSettings();
  } catch (error) {
    showToast(error.message, true);
  }
}

initialize();
