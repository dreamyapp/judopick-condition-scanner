const state = {
  conditions: [],
  selectedId: null,
  draft: null,
  fields: [],
  operators: [],
  credentialsConfigured: false,
  activeJobId: null,
  resultJobId: null,
  resultOffset: 0,
  resultTotal: 0,
  resultMode: "custom",
  resultTimeframe: "",
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
      ${condition.mode === "kiwoom" ? '<span class="condition-mode">영웅문</span>' : condition.mode === "signal" ? '<span class="condition-mode">차트 수식</span>' : ""}
      <strong>${escapeHtml(condition.name)}</strong>
      <span>${escapeHtml(condition.summary)}</span>
    </button>
  `).join("");
  $$(".condition-item").forEach((button) => {
    button.addEventListener("click", () => selectCondition(button.dataset.id));
  });
}

function newCondition() {
  state.activeJobId = null;
  state.selectedId = null;
  state.draft = {
    id: null,
    name: "",
    mode: "signal",
    raw_text: "",
    rules: [],
    markets: ["KOSPI", "KOSDAQ"],
    exclusions: [],
    timeframe: "",
  };
  renderConditionList();
  renderEditor();
  setTimeout(() => $("#conditionName").focus(), 0);
}

function selectCondition(conditionId) {
  const condition = state.conditions.find((item) => item.id === conditionId);
  if (!condition) return;
  state.activeJobId = null;
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
  const isSignal = state.draft.mode === "signal";
  $("#searchDescription").textContent = isSignal
    ? "가장 최근 봉의 신호를 확인합니다. 장중에는 신호가 바뀔 수 있습니다."
    : "현재 시세를 기준으로 검색합니다.";
  $("#conditionName").value = state.draft.name || "";
  $("#conditionName").disabled = isKiwoom;
  $("#conditionTypeBadge").textContent = isKiwoom ? "영웅문 조건식" : isSignal ? "차트 수식" : "직접 만든 조건식";
  $("#kiwoomInfo").classList.toggle("hidden", !isKiwoom);
  $("#customEditor").classList.toggle("hidden", isKiwoom);
  $("#saveButton").classList.toggle("hidden", isKiwoom);
  $("#copyButton").classList.toggle("hidden", isKiwoom);
  $("#copyButton").textContent = isSignal ? "수식 복사" : "조건식 복사";
  $("#deleteButton").classList.toggle("hidden", !state.draft.id);

  if (!isKiwoom) {
    $("#marketKospi").checked = state.draft.markets.includes("KOSPI");
    $("#marketKosdaq").checked = state.draft.markets.includes("KOSDAQ");
    $$(".exclusion-check").forEach((input) => {
      input.checked = state.draft.exclusions.includes(input.value);
    });
    $("#conditionText").value = state.draft.raw_text || "";
    $("#signalTimeframe").value = state.draft.timeframe || "";
    $("#parsePreview").classList.add("hidden");
    renderRules();
  }
}

function chooseUnit(rule) {
  const units = unitDefinitions[rule.field] || [{ value: 1, label: "" }];
  if (rule._unit && units.some((item) => item.value === rule._unit)) return rule._unit;
  if (rule.field === "market_cap" || rule.field === "trading_value") return 100000000;
  const preferred = [...units].reverse().find((item) => Math.abs(Number(rule.value || 0)) >= item.value);
  return (preferred || units[0]).value;
}

function renderRules() {
  const list = $("#ruleList");
  if (!state.draft.rules.length) {
    list.innerHTML = '<div class="rule-empty">추가 필터 없음 · 수식만으로 검색합니다.</div>';
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
        <select class="rule-field" aria-label="필터 항목">${fieldOptions}</select>
        <select class="rule-operator" aria-label="비교 방법">${operatorOptions}</select>
        <input class="value-input rule-value" type="number" step="any" value="${rule.value == null ? "" : Number(rule.value) / unit}" placeholder="숫자 입력" aria-label="필터 값">
        ${range ? `<span class="range-separator">~</span><input class="value-input rule-value2" type="number" step="any" value="${rule.value2 == null ? "" : Number(rule.value2) / unit}" placeholder="숫자 입력" aria-label="범위 끝 값">` : ""}
        <select class="rule-unit" aria-label="단위">${unitOptions}</select>
        <button class="remove-rule" type="button" aria-label="이 필터 삭제">×</button>
      </div>`;
  }).join("");

  $$(".rule-row").forEach((row) => {
    const index = Number(row.dataset.index);
    row.querySelector(".rule-field").addEventListener("change", (event) => {
      state.draft.rules[index] = { field: event.target.value, operator: "gte", value: null };
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
  const firstValue = row.querySelector(".rule-value").value.trim();
  rule.value = firstValue === "" ? null : Number(firstValue) * unit;
  rule._unit = unit;
  const value2 = row.querySelector(".rule-value2");
  if (value2) rule.value2 = value2.value.trim() === "" ? null : Number(value2.value) * unit;
}

function syncDraftFromForm() {
  if (!state.draft || state.draft.mode === "kiwoom") return;
  state.draft.name = $("#conditionName").value.trim();
  state.draft.raw_text = $("#conditionText").value.trim();
  state.draft.timeframe = $("#signalTimeframe").value;
  $$(".rule-row").forEach((row) => syncRuleRow(row, Number(row.dataset.index)));
  state.draft.markets = [
    $("#marketKospi").checked ? "KOSPI" : null,
    $("#marketKosdaq").checked ? "KOSDAQ" : null,
  ].filter(Boolean);
  state.draft.exclusions = $$(".exclusion-check:checked").map((input) => input.value);
}

async function parsePastedCondition() {
  const button = $("#parseButton");
  const text = $("#conditionText").value.trim();
  setBusy(button, true, "확인 중…");
  try {
    const data = await api("/api/parse", { method: "POST", body: JSON.stringify({ text }) });
    const parsed = data.parsed;
    if (parsed.mode !== "signal") throw new Error("차트 수식을 붙여넣어 주세요. 시가총액 등은 아래 추가 필터에서 설정합니다.");
    state.draft.mode = "signal";
    state.draft.raw_text = text;
    $("#conditionTypeBadge").textContent = "차트 수식";
    $("#searchDescription").textContent = "가장 최근 봉의 신호를 확인합니다. 장중에는 신호가 바뀔 수 있습니다.";
    if (parsed.name) {
      state.draft.name = parsed.name;
      $("#conditionName").value = parsed.name;
    }
    renderParsePreview(parsed);
    showToast("수식을 확인했습니다. 추가 필터는 그대로 유지됩니다.");
    return true;
  } catch (error) {
    showToast(error.message, true);
    return false;
  } finally {
    setBusy(button, false);
  }
}

function renderParsePreview(parsed) {
  const preview = $("#parsePreview");
  preview.innerHTML = `
    <h3>수식 확인 완료</h3>
    <div class="preview-chips"><span class="preview-chip">${escapeHtml(parsed.description || "차트 수식")}</span></div>`;
  preview.classList.remove("hidden");
}

async function saveCondition() {
  if (!state.draft) return null;
  if (state.draft.mode === "kiwoom") return state.draft;
  const formulaText = $("#conditionText").value.trim();
  if (!formulaText && state.draft.mode === "signal") {
    showToast("검색할 수식을 붙여넣어 주세요.", true);
    $("#conditionText").focus();
    return null;
  }
  if (formulaText && formulaText !== state.draft.raw_text) {
    if (!await parsePastedCondition()) return null;
  }
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
  if (state.draft.mode === "signal" && !state.draft.timeframe) {
    showToast("검색할 차트 봉을 선택해 주세요.", true);
    $("#signalTimeframe").focus();
    return null;
  }
  if (state.draft.mode === "custom" && !state.draft.rules.length) {
    showToast("기존 필터 조건식에는 필터가 한 개 이상 필요합니다.", true);
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
  state.resultJobId = null;
  state.resultOffset = 0;
  state.resultTotal = 0;
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
      await showSearchResults(jobId, job);
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

async function showSearchResults(jobId, job, restore = false) {
  state.resultJobId = jobId;
  state.resultOffset = 0;
  state.resultTotal = Number(job.result_count || 0);
  if (!restore) updateProgress(100, "검색 결과를 표시하고 있습니다.");
  try {
    const page = await api(`/api/search/${jobId}/results?offset=0`);
    renderResults(page.results, page.total, page.finished_at,
      page.mode || job.mode, page.timeframe || job.timeframe);
    $("#searchProgress").classList.add("hidden");
    $("#searchReady").classList.remove("hidden");
  } catch (error) {
    showResultsError(error.message);
  }
}

function showResultsError(message, preserveRows = false) {
  $("#searchProgress").classList.add("hidden");
  $("#searchReady").classList.remove("hidden");
  $("#resultsSection").classList.remove("hidden");
  $("#resultsTitle").textContent = `${state.resultTotal.toLocaleString("ko-KR")}개 종목을 찾았습니다`;
  $("#resultsError").classList.remove("hidden");
  $("#resultsErrorMessage").textContent = message || "결과 다시 보기를 눌러 주세요.";
  $("#resultsEmpty").classList.add("hidden");
  if (!preserveRows) $("#resultsTableWrap").classList.add("hidden");
  $("#moreResultsButton").classList.add("hidden");
}

async function retryResults() {
  if (!state.resultJobId) return;
  if (state.resultOffset > 0) {
    await loadMoreResults();
  } else {
    await showSearchResults(state.resultJobId, {
      mode: state.resultMode,
      timeframe: state.resultTimeframe,
      result_count: state.resultTotal,
    }, true);
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

function formatBarTime(value) {
  const digits = String(value || "").replace(/\D/g, "");
  if (digits.length === 8) return `${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
  if (digits.length < 12) return "—";
  return `${digits.slice(4, 6)}-${digits.slice(6, 8)} ${digits.slice(8, 10)}:${digits.slice(10, 12)}`;
}

function resultRowsHtml(results, isSignal, timeframe) {
  return results.map((stock) => {
    const rate = Number(stock.change_rate || 0);
    const rateClass = rate > 0 ? "rate-up" : rate < 0 ? "rate-down" : "";
    const ratePrefix = rate > 0 ? "+" : "";
    return `<tr>
      <td class="stock-name"><strong>${escapeHtml(stock.name || stock.code)}</strong><span>${escapeHtml(stock.code)}</span></td>
      <td>${formatNumber(stock.price)}원</td>
      <td class="${rateClass}">${isSignal ? (timeframe === "D" ? "일봉" : `${escapeHtml(timeframe)}분`) : `${ratePrefix}${rate.toFixed(2)}%`}</td>
      <td>${formatNumber(stock.volume)}주</td>
      <td>${isSignal ? formatBarTime(stock.bar_time) : `${formatMoney(stock.trading_value)}원`}</td>
      <td>${escapeHtml(stock.found_at || "-")}</td>
    </tr>`;
  }).join("");
}

function renderResults(results, total, finishedAt, mode, timeframe) {
  if (!Array.isArray(results) || !Number.isInteger(total) || total < 0 || (total > 0 && !results.length)) {
    throw new Error("검색 결과가 올바르게 도착하지 않았습니다. 결과 다시 보기를 눌러 주세요.");
  }
  const isSignal = mode === "signal";
  state.resultMode = mode;
  state.resultTimeframe = timeframe;
  state.resultOffset = results.length;
  state.resultTotal = total;
  $("#priceHeading").textContent = isSignal ? "봉 종가" : "현재가";
  $("#rateHeading").textContent = isSignal ? "차트 봉" : "등락률";
  $("#volumeHeading").textContent = isSignal ? "봉 거래량" : "거래량";
  $("#tradingHeading").textContent = isSignal ? "신호 시각" : "거래대금";
  $("#foundHeading").textContent = isSignal ? "확인 시각" : "발견 시각";
  $("#resultsSection").classList.remove("hidden");
  $("#resultsError").classList.add("hidden");
  $("#resultsTitle").textContent = `${total.toLocaleString("ko-KR")}개 종목을 찾았습니다`;
  const date = finishedAt ? new Date(finishedAt) : new Date();
  const displayDate = Number.isNaN(date.getTime()) ? new Date() : date;
  $("#resultsTime").textContent = isSignal
    ? `${displayDate.toLocaleString("ko-KR")} 검색 완료 · 종목별 최신 봉 기준`
    : `${displayDate.toLocaleString("ko-KR")} 기준`;
  $("#resultsEmpty").classList.toggle("hidden", total > 0);
  $("#resultsTableWrap").classList.toggle("hidden", total === 0);
  $("#resultsBody").innerHTML = resultRowsHtml(results, isSignal, timeframe);
  updateMoreResultsButton();
  const section = $("#resultsSection");
  if (typeof section.scrollIntoView === "function") {
    try { section.scrollIntoView({ behavior: "smooth", block: "start" }); } catch { /* 결과 표시에는 영향이 없습니다. */ }
  }
}

function updateMoreResultsButton() {
  const button = $("#moreResultsButton");
  const remaining = state.resultTotal - state.resultOffset;
  button.classList.toggle("hidden", remaining <= 0);
  button.textContent = remaining > 0
    ? `다음 종목 보기 (${state.resultOffset.toLocaleString("ko-KR")} / ${state.resultTotal.toLocaleString("ko-KR")})`
    : "다음 종목 보기";
}

async function loadMoreResults() {
  if (!state.resultJobId || state.resultOffset >= state.resultTotal) return;
  const button = $("#moreResultsButton");
  setBusy(button, true, "불러오는 중…");
  try {
    const page = await api(`/api/search/${state.resultJobId}/results?offset=${state.resultOffset}`);
    if (!Array.isArray(page.results) || !page.results.length || page.offset !== state.resultOffset) {
      throw new Error("다음 종목을 불러오지 못했습니다.");
    }
    $("#resultsBody").insertAdjacentHTML("beforeend", resultRowsHtml(page.results,
      state.resultMode === "signal", state.resultTimeframe));
    state.resultOffset += page.results.length;
    $("#resultsError").classList.add("hidden");
    updateMoreResultsButton();
  } catch (error) {
    showResultsError(error.message, true);
  } finally {
    setBusy(button, false);
    if ($("#resultsError").classList.contains("hidden")) updateMoreResultsButton();
  }
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

function openShare() {
  $("#shareModal").classList.remove("hidden");
  setTimeout(() => $("#copyWindowsLinkButton").focus(), 0);
}

function closeShare() {
  $("#shareModal").classList.add("hidden");
}

async function copyDownloadLink(platform) {
  const filenames = {
    windows: "Judopick-ConditionScanner-Windows-x64-Setup.exe",
    mac: "Judopick-ConditionScanner-macOS-arm64.dmg",
  };
  const filename = filenames[platform];
  const link = `https://github.com/dreamyapp/judopick-condition-scanner/releases/download/v${window.APP_VERSION}/${filename}`;
  try {
    await copyText(link);
    const label = platform === "windows" ? "윈도우" : "맥 M1 이후";
    showToast(`${label} 다운로드 링크를 복사했습니다.`);
  } catch {
    showToast("링크를 복사하지 못했습니다. 잠시 후 다시 시도해 주세요.", true);
  }
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
    state.draft.rules.push({ field: "market_cap", operator: "gte", value: null, _unit: 100000000 });
    renderRules();
  });
  $("#parseButton").addEventListener("click", parsePastedCondition);
  $("#saveButton").addEventListener("click", saveCondition);
  $("#deleteButton").addEventListener("click", deleteCondition);
  $("#copyButton").addEventListener("click", copyCondition);
  $("#searchButton").addEventListener("click", startSearch);
  $("#searchAgainButton").addEventListener("click", startSearch);
  $("#retryResultsButton").addEventListener("click", retryResults);
  $("#moreResultsButton").addEventListener("click", loadMoreResults);
  $("#settingsButton").addEventListener("click", openSettings);
  $("#autoFindKeysButton").addEventListener("click", autoFindDownloadedKeys);
  $("#selectKeyFilesButton").addEventListener("click", () => $("#keyFilesInput").click());
  $("#keyFilesInput").addEventListener("change", importSelectedKeyFiles);
  $("#openDownloadsButton").addEventListener("click", openDownloads);
  $("#guideButton").addEventListener("click", openGuide);
  $("#shareAppButton").addEventListener("click", openShare);
  $("#closeShareButton").addEventListener("click", closeShare);
  $("#copyWindowsLinkButton").addEventListener("click", () => copyDownloadLink("windows"));
  $("#copyMacLinkButton").addEventListener("click", () => copyDownloadLink("mac"));
  $("#openGuideFromSettings").addEventListener("click", openGuide);
  $("#closeGuideButton").addEventListener("click", closeGuide);
  $("#closeSettingsButton").addEventListener("click", closeSettings);
  $("#settingsModal").addEventListener("click", (event) => {
    if (event.target === $("#settingsModal")) closeSettings();
  });
  $("#guideModal").addEventListener("click", (event) => {
    if (event.target === $("#guideModal")) closeGuide();
  });
  $("#shareModal").addEventListener("click", (event) => {
    if (event.target === $("#shareModal")) closeShare();
  });
  $("#saveSettingsButton").addEventListener("click", () => saveSettings(false));
  $("#testConnectionButton").addEventListener("click", () => saveSettings(true));
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!$("#guideModal").classList.contains("hidden")) closeGuide();
    else if (!$("#shareModal").classList.contains("hidden")) closeShare();
    else if (!$("#settingsModal").classList.contains("hidden")) closeSettings();
  });
}

async function initialize() {
  bindEvents();
  try {
    const data = await loadBootstrap();
    if (!data.credentials.configured) openSettings();
    const latest = await api("/api/search/latest");
    if (latest.available && state.conditions.some((item) => item.id === latest.condition_id)) {
      selectCondition(latest.condition_id);
      await showSearchResults(latest.job_id, latest, true);
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

initialize();
