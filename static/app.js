const state = {
  token: null,
  ws: null,
  categories: [],
  days: new Map(),
  view: "year",
  currentDate: new Date(),
  selectedDate: null,
  filterCategoryId: "all",
  palette: [],
  userVersion: null,
  brushCategoryId: null,
  paintMode: true,
  paintAnchor: null,
  painting: false,
  paintedDates: new Set(),
};

const authScreen = document.getElementById("authScreen");
const appShell = document.getElementById("appShell");
const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");
const connectionStatus = document.getElementById("connectionStatus");
const calendarEl = document.getElementById("calendar");
const currentLabel = document.getElementById("currentLabel");
const categoryFilter = document.getElementById("categoryFilter");
const brushStrip = document.getElementById("brushStrip");
const rangeHint = document.getElementById("rangeHint");
const selectedDayLabel = document.getElementById("selectedDayLabel");
const dayNote = document.getElementById("dayNote");
const dayMessage = document.getElementById("dayMessage");
const saveDayNote = document.getElementById("saveDayNote");
const clearDayBtn = document.getElementById("clearDay");
const paintModeToggle = document.getElementById("paintModeToggle");
const clearBrushBtn = document.getElementById("clearBrush");
const categoryList = document.getElementById("categoryList");
const addCategoryBtn = document.getElementById("addCategory");
const passwordForm = document.getElementById("passwordForm");
const passwordMessage = document.getElementById("passwordMessage");
const categoryForm = document.getElementById("categoryForm");
const categoryName = document.getElementById("categoryName");
const categoryColorPicker = document.getElementById("categoryColorPicker");
const categoryColorText = document.getElementById("categoryColorText");
const categoryFormMessage = document.getElementById("categoryFormMessage");
const suggestedColorsEl = document.getElementById("suggestedColors");
const modalBackdrop = document.getElementById("modalBackdrop");
const categoriesModal = document.getElementById("categoriesModal");
const configModal = document.getElementById("configModal");
const categoryEditorModal = document.getElementById("categoryEditorModal");
const openCategories = document.getElementById("openCategories");
const openConfig = document.getElementById("openConfig");
const prevPeriod = document.getElementById("prevPeriod");
const nextPeriod = document.getElementById("nextPeriod");
const viewButtons = document.querySelectorAll(".view-btn");

let reconnectTimer = null;
let reconnectDelay = 500;

function setStatus(text, ok = false) {
  connectionStatus.textContent = text;
  connectionStatus.style.color = ok ? "#22c55e" : "#f97316";
}

function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function addDays(date, delta) {
  const result = new Date(date);
  result.setDate(result.getDate() + delta);
  return result;
}

function startOfWeek(date) {
  const result = new Date(date);
  const weekday = (result.getDay() + 6) % 7;
  result.setDate(result.getDate() - weekday);
  return result;
}

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

function compareIso(a, b) {
  return a.localeCompare(b);
}

function isoRange(a, b) {
  const start = compareIso(a, b) <= 0 ? a : b;
  const end = compareIso(a, b) <= 0 ? b : a;
  const dates = [];
  for (let cursor = parseDate(start); formatDate(cursor) <= end; cursor = addDays(cursor, 1)) {
    dates.push(formatDate(cursor));
  }
  return dates;
}

function getCategory(categoryId) {
  return state.categories.find((category) => category.id === categoryId) || null;
}

function getCategoryColor(categoryId) {
  return getCategory(categoryId)?.color || "#1e293b";
}

function getEntry(iso) {
  return state.days.get(iso) || null;
}

function shouldDim(categoryId) {
  return state.filterCategoryId !== "all" && String(categoryId) !== state.filterCategoryId;
}

function showApp() {
  authScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
}

function setSelectedDate(date) {
  state.selectedDate = date;
  const iso = date ? formatDate(date) : null;
  const entry = iso ? getEntry(iso) : null;
  selectedDayLabel.textContent = date ? date.toDateString() : "None";
  dayNote.value = entry?.note || "";
  dayMessage.textContent = "";
  renderCalendar();
}

function updateCategoryFilter() {
  categoryFilter.innerHTML = "";
  const all = document.createElement("option");
  all.value = "all";
  all.textContent = "All";
  categoryFilter.appendChild(all);
  state.categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = String(category.id);
    option.textContent = category.name;
    categoryFilter.appendChild(option);
  });
  categoryFilter.value = state.filterCategoryId;
}

function updateBrushStrip() {
  brushStrip.innerHTML = "";
  const chips = [
    { id: null, name: "Unassigned", color: "#475569" },
    ...state.categories,
  ];
  chips.forEach((chip) => {
    const button = document.createElement("button");
    button.className = "brush-chip ghost";
    if (chip.id === state.brushCategoryId) {
      button.classList.add("active");
    }
    button.type = "button";
    button.innerHTML = `<span class="brush-dot" style="background:${chip.color}"></span><span>${chip.name}</span>`;
    button.addEventListener("click", () => {
      state.brushCategoryId = chip.id;
      updateBrushStrip();
      renderCalendar();
    });
    brushStrip.appendChild(button);
  });
}

function renderCategories() {
  categoryList.innerHTML = "";
  state.categories.forEach((category) => {
    const row = document.createElement("div");
    row.className = "category-item";

    const swatch = document.createElement("div");
    swatch.className = "category-swatch";
    swatch.style.background = category.color;

    const name = document.createElement("input");
    name.type = "text";
    name.value = category.name;

    const color = document.createElement("input");
    color.type = "color";
    color.value = category.color;

    const save = () => {
      sendMessage({
        type: "update_category",
        id: category.id,
        name: name.value.trim(),
        color: color.value,
        expectedVersion: category.version,
      });
    };

    name.addEventListener("change", save);
    color.addEventListener("change", save);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "ghost";
    remove.textContent = "Delete";
    remove.addEventListener("click", () => {
      sendMessage({
        type: "delete_category",
        id: category.id,
        expectedVersion: category.version,
      });
    });

    row.append(swatch, name, color, remove);
    categoryList.appendChild(row);
  });
}

function updateViewButtons() {
  viewButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });
  paintModeToggle.classList.toggle("active", state.paintMode);
}

function suggestColors(palette, existing, limit = 6) {
  if (!palette.length) return [];
  if (!existing.length) return palette.slice(0, limit);
  const toRgb = (hex) => {
    const raw = hex.replace("#", "");
    return [
      parseInt(raw.slice(0, 2), 16),
      parseInt(raw.slice(2, 4), 16),
      parseInt(raw.slice(4, 6), 16),
    ];
  };
  const distance = (a, b) => {
    const [ar, ag, ab] = toRgb(a);
    const [br, bg, bb] = toRgb(b);
    return Math.sqrt((ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2);
  };
  return palette
    .map((candidate) => ({
      candidate,
      score: Math.min(...existing.map((other) => distance(candidate, other))),
    }))
    .sort((left, right) => right.score - left.score)
    .slice(0, limit)
    .map((item) => item.candidate);
}

function openModal(dialog) {
  modalBackdrop.classList.remove("hidden");
  dialog.showModal();
}

function closeModal(dialog) {
  dialog.close();
  const anyOpen = [categoriesModal, configModal, categoryEditorModal].some(
    (item) => item.open
  );
  modalBackdrop.classList.toggle("hidden", !anyOpen);
}

function refreshCategoryCreator() {
  const suggestions = suggestColors(
    state.palette,
    state.categories.map((category) => category.color)
  );
  const initial = suggestions[0] || "#64748b";
  categoryColorPicker.value = initial;
  categoryColorText.value = initial;
  suggestedColorsEl.innerHTML = "";
  suggestions.forEach((color) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggested-color";
    button.style.background = color;
    button.title = color;
    button.addEventListener("click", () => {
      categoryColorPicker.value = color;
      categoryColorText.value = color;
    });
    suggestedColorsEl.appendChild(button);
  });
}

function paintDate(iso, categoryId) {
  if (state.paintedDates.has(iso)) return;
  state.paintedDates.add(iso);
  const entry = getEntry(iso);
  sendMessage({
    type: "set_day",
    date: iso,
    categoryId,
    note: entry?.note || null,
    expectedVersion: entry ? entry.version : null,
  });
}

function paintRange(startIso, endIso, categoryId) {
  isoRange(startIso, endIso).forEach((iso) => paintDate(iso, categoryId));
}

function onDayInteract(iso, event) {
  const date = parseDate(iso);
  if (state.paintMode) {
    if (event.shiftKey && state.paintAnchor) {
      state.paintedDates.clear();
      paintRange(state.paintAnchor, iso, state.brushCategoryId);
    } else {
      paintDate(iso, state.brushCategoryId);
      state.paintAnchor = iso;
    }
    setSelectedDate(date);
    return;
  }
  state.paintAnchor = iso;
  setSelectedDate(date);
}

function cellClass(baseClass, iso, entry) {
  const classes = [baseClass];
  if (entry && shouldDim(entry.category_id)) classes.push("day-dim");
  if (!entry && state.filterCategoryId !== "all") classes.push("day-dim");
  if (state.selectedDate && formatDate(state.selectedDate) === iso) classes.push("day-selected");
  if (state.painting && state.brushCategoryId === null) classes.push("day-preview");
  return classes.join(" ");
}

function buildDayCell(dateObj, compact = false) {
  const iso = formatDate(dateObj);
  const entry = getEntry(iso);
  const category = entry ? getCategory(entry.category_id) : null;
  const element = document.createElement(compact ? "div" : "div");
  element.className = compact ? cellClass("day-cell", iso, entry) : cellClass("day-card", iso, entry);
  element.dataset.date = iso;
  element.style.background = category ? category.color : compact ? "#1e293b" : "#111827";

  if (compact) {
    const label = document.createElement("span");
    label.textContent = String(dateObj.getDate());
    element.appendChild(label);
    if (entry?.note) {
      element.classList.add("note");
      element.dataset.note = entry.note;
    }
  } else {
    const title = document.createElement("h4");
    title.textContent = dateObj.toLocaleDateString(undefined, {
      weekday: state.view === "week" ? "long" : "short",
      day: "numeric",
    });
    element.appendChild(title);
    if (category) {
      const label = document.createElement("small");
      label.textContent = category.name;
      element.appendChild(label);
    }
    if (entry?.note) {
      const note = document.createElement("p");
      note.textContent = entry.note;
      element.appendChild(note);
    }
  }

  const activate = (event) => onDayInteract(iso, event);
  element.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    state.painting = true;
    state.paintedDates.clear();
    activate(event);
  });
  element.addEventListener("mouseenter", () => {
    if (!state.paintMode || !state.painting) return;
    paintDate(iso, state.brushCategoryId);
  });
  element.addEventListener("click", (event) => {
    if (state.paintMode) return;
    activate(event);
  });
  return element;
}

function renderYearView() {
  const year = state.currentDate.getFullYear();
  currentLabel.textContent = String(year);
  const grid = document.createElement("div");
  grid.className = "year-grid";
  for (let month = 0; month < 12; month += 1) {
    const monthEl = document.createElement("section");
    monthEl.className = "month";
    const title = document.createElement("h3");
    title.textContent = new Date(year, month).toLocaleString(undefined, { month: "long" });
    const monthGrid = document.createElement("div");
    monthGrid.className = "month-grid";
    const offset = (new Date(year, month, 1).getDay() + 6) % 7;
    for (let filler = 0; filler < offset; filler += 1) {
      const empty = document.createElement("div");
      empty.className = "day-cell day-dim";
      monthGrid.appendChild(empty);
    }
    const totalDays = daysInMonth(year, month);
    for (let day = 1; day <= totalDays; day += 1) {
      monthGrid.appendChild(buildDayCell(new Date(year, month, day), true));
    }
    monthEl.append(title, monthGrid);
    grid.appendChild(monthEl);
  }
  calendarEl.replaceChildren(grid);
}

function renderMonthView() {
  const year = state.currentDate.getFullYear();
  const month = state.currentDate.getMonth();
  currentLabel.textContent = new Date(year, month).toLocaleString(undefined, {
    month: "long",
    year: "numeric",
  });
  const grid = document.createElement("div");
  grid.className = "month-view-grid";
  const offset = (new Date(year, month, 1).getDay() + 6) % 7;
  for (let filler = 0; filler < offset; filler += 1) {
    const empty = document.createElement("div");
    empty.className = "day-card day-dim";
    grid.appendChild(empty);
  }
  const totalDays = daysInMonth(year, month);
  for (let day = 1; day <= totalDays; day += 1) {
    grid.appendChild(buildDayCell(new Date(year, month, day)));
  }
  calendarEl.replaceChildren(grid);
}

function renderWeekView() {
  const start = startOfWeek(state.currentDate);
  currentLabel.textContent = `Week of ${start.toLocaleDateString()}`;
  const grid = document.createElement("div");
  grid.className = "week-grid";
  for (let offset = 0; offset < 7; offset += 1) {
    grid.appendChild(buildDayCell(addDays(start, offset)));
  }
  calendarEl.replaceChildren(grid);
}

function renderCalendar() {
  updateViewButtons();
  rangeHint.textContent = state.paintMode
    ? "Drag to paint. Shift-click paints a whole range from the last anchor."
    : "Selection mode: click a day to edit its note or clear it.";
  if (state.view === "year") renderYearView();
  else if (state.view === "month") renderMonthView();
  else renderWeekView();
}

function handleSnapshot(data) {
  state.categories = data.categories || [];
  state.days = new Map((data.days || []).map((entry) => [entry.date, entry]));
  state.palette = data.palette || [];
  state.userVersion = data.user?.version ?? null;
  if (state.brushCategoryId === null && state.categories[0]) {
    state.brushCategoryId = state.categories[0].id;
  }
  updateCategoryFilter();
  updateBrushStrip();
  renderCategories();
  renderCalendar();
}

function sendMessage(payload) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify(payload));
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

  state.ws.addEventListener("open", () => {
    setStatus("Connected", true);
    reconnectDelay = 500;
    sendMessage({ type: "auth", token: state.token });
  });

  state.ws.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "snapshot") {
      handleSnapshot(data);
      return;
    }
    if (data.type === "category_created") state.categories.push(data.category);
    if (data.type === "category_updated") {
      const index = state.categories.findIndex((category) => category.id === data.category.id);
      if (index !== -1) state.categories[index] = data.category;
    }
    if (data.type === "category_deleted") {
      state.categories = state.categories.filter((category) => category.id !== data.id);
      if (state.brushCategoryId === data.id) {
        state.brushCategoryId = null;
      }
    }
    if (data.type === "day_updated") state.days.set(data.day.date, data.day);
    if (data.type === "day_deleted") state.days.delete(data.date);
    if (data.type === "password_updated" && data.user?.version) {
      state.userVersion = data.user.version;
      passwordMessage.textContent = "Password updated.";
    }
    if (data.type === "error") {
      const human = data.message.replaceAll("_", " ");
      if (["invalid_credentials", "password_too_short"].includes(data.message)) {
        passwordMessage.textContent = human;
      } else if (data.message.startsWith("invalid_") || data.message === "category_in_use") {
        categoryFormMessage.textContent = human;
        dayMessage.textContent = human;
      } else {
        dayMessage.textContent = human;
      }
    }
    updateCategoryFilter();
    updateBrushStrip();
    renderCategories();
    renderCalendar();
  });

  state.ws.addEventListener("close", () => {
    setStatus("Disconnected");
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 5000);
      connectWebSocket();
    }, reconnectDelay);
  });
}

async function login(password) {
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!response.ok) throw new Error("login_failed");
  const data = await response.json();
  state.token = data.token;
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  try {
    await login(String(new FormData(loginForm).get("password")));
    loginForm.reset();
    showApp();
    connectWebSocket();
  } catch {
    loginError.textContent = "Login failed.";
  }
});

openCategories.addEventListener("click", () => openModal(categoriesModal));
openConfig.addEventListener("click", () => openModal(configModal));
addCategoryBtn.addEventListener("click", () => {
  categoryForm.reset();
  categoryFormMessage.textContent = "";
  refreshCategoryCreator();
  openModal(categoryEditorModal);
});

document.querySelectorAll("[data-close-modal]").forEach((button) => {
  button.addEventListener("click", () => closeModal(document.getElementById(button.dataset.closeModal)));
});

modalBackdrop.addEventListener("click", () => {
  [categoriesModal, configModal, categoryEditorModal].forEach((modal) => {
    if (modal.open) closeModal(modal);
  });
});

categoryColorPicker.addEventListener("input", () => {
  categoryColorText.value = categoryColorPicker.value;
});

categoryColorText.addEventListener("input", () => {
  if (/^#[0-9a-fA-F]{6}$/.test(categoryColorText.value)) {
    categoryColorPicker.value = categoryColorText.value;
  }
});

categoryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  categoryFormMessage.textContent = "";
  sendMessage({
    type: "create_category",
    name: categoryName.value.trim(),
    color: categoryColorText.value.trim(),
  });
  closeModal(categoryEditorModal);
});

passwordForm.addEventListener("submit", (event) => {
  event.preventDefault();
  passwordMessage.textContent = "";
  sendMessage({
    type: "update_password",
    currentPassword: document.getElementById("currentPassword").value,
    newPassword: document.getElementById("newPassword").value,
    expectedVersion: state.userVersion,
  });
  passwordForm.reset();
});

saveDayNote.addEventListener("click", () => {
  if (!state.selectedDate) {
    dayMessage.textContent = "Select a day first.";
    return;
  }
  const iso = formatDate(state.selectedDate);
  const entry = getEntry(iso);
  if (!entry) {
    dayMessage.textContent = "Paint a category onto the day before saving a note.";
    return;
  }
  sendMessage({
    type: "set_day",
    date: iso,
    categoryId: entry.category_id,
    note: dayNote.value.trim() || null,
    expectedVersion: entry.version,
  });
  dayMessage.textContent = "Saved.";
});

clearDayBtn.addEventListener("click", () => {
  if (!state.selectedDate) {
    dayMessage.textContent = "Select a day first.";
    return;
  }
  const iso = formatDate(state.selectedDate);
  const entry = getEntry(iso);
  if (!entry) {
    dayMessage.textContent = "Day already unassigned.";
    return;
  }
  sendMessage({
    type: "set_day",
    date: iso,
    categoryId: null,
    expectedVersion: entry.version,
  });
  dayMessage.textContent = "Cleared.";
});

paintModeToggle.addEventListener("click", () => {
  state.paintMode = !state.paintMode;
  renderCalendar();
});

clearBrushBtn.addEventListener("click", () => {
  state.brushCategoryId = null;
  updateBrushStrip();
});

categoryFilter.addEventListener("change", () => {
  state.filterCategoryId = categoryFilter.value;
  renderCalendar();
});

prevPeriod.addEventListener("click", () => {
  if (state.view === "year") state.currentDate = new Date(state.currentDate.getFullYear() - 1, 0, 1);
  else if (state.view === "month") state.currentDate = new Date(state.currentDate.getFullYear(), state.currentDate.getMonth() - 1, 1);
  else state.currentDate = addDays(state.currentDate, -7);
  renderCalendar();
});

nextPeriod.addEventListener("click", () => {
  if (state.view === "year") state.currentDate = new Date(state.currentDate.getFullYear() + 1, 0, 1);
  else if (state.view === "month") state.currentDate = new Date(state.currentDate.getFullYear(), state.currentDate.getMonth() + 1, 1);
  else state.currentDate = addDays(state.currentDate, 7);
  renderCalendar();
});

viewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.view = button.dataset.view;
    renderCalendar();
  });
});

document.addEventListener("mouseup", () => {
  state.painting = false;
  state.paintedDates.clear();
});

setStatus("Offline");
updateCategoryFilter();
updateBrushStrip();
renderCalendar();
