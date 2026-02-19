const state = {
  token: null,
  ws: null,
  connected: false,
  categories: [],
  days: new Map(),
  view: "year",
  currentDate: new Date(),
  selectedDate: null,
  filterCategoryId: "all",
  palette: [],
  userVersion: null,
};

const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");
const loginPanel = document.getElementById("loginPanel");
const categoriesPanel = document.getElementById("categoriesPanel");
const categoryList = document.getElementById("categoryList");
const categoryFilter = document.getElementById("categoryFilter");
const addCategoryBtn = document.getElementById("addCategory");
const calendarEl = document.getElementById("calendar");
const dayPanel = document.getElementById("dayPanel");
const dayTitle = document.getElementById("dayTitle");
const dayCategory = document.getElementById("dayCategory");
const dayNote = document.getElementById("dayNote");
const dayMessage = document.getElementById("dayMessage");
const saveDayBtn = document.getElementById("saveDay");
const clearDayBtn = document.getElementById("clearDay");
const connectionStatus = document.getElementById("connectionStatus");
const currentLabel = document.getElementById("currentLabel");
const prevPeriod = document.getElementById("prevPeriod");
const nextPeriod = document.getElementById("nextPeriod");
const viewButtons = document.querySelectorAll(".view-btn");
const configPanel = document.getElementById("configPanel");
const toggleConfig = document.getElementById("toggleConfig");
const passwordForm = document.getElementById("passwordForm");
const passwordMessage = document.getElementById("passwordMessage");

let reconnectTimer = null;
let reconnectDelay = 500;

function setStatus(text, ok = false) {
  connectionStatus.textContent = text;
  connectionStatus.style.color = ok ? "#22c55e" : "#f97316";
}

function formatDate(date) {
  return date.toISOString().slice(0, 10);
}

function parseDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function startOfWeek(date) {
  const day = (date.getDay() + 6) % 7;
  const result = new Date(date);
  result.setDate(date.getDate() - day);
  return result;
}

function addDays(date, delta) {
  const result = new Date(date);
  result.setDate(result.getDate() + delta);
  return result;
}

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

function updateViewButtons() {
  viewButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === state.view);
  });
}

function setSelectedDate(date) {
  state.selectedDate = date;
  if (!date) {
    dayPanel.classList.add("hidden");
    return;
  }
  dayPanel.classList.remove("hidden");
  dayMessage.textContent = "";
  const iso = formatDate(date);
  const entry = state.days.get(iso);
  dayTitle.textContent = date.toDateString();
  dayCategory.value = entry ? String(entry.category_id) : "";
  dayNote.value = entry?.note ?? "";
}

function updateCategorySelects() {
  dayCategory.innerHTML = "";
  const option = document.createElement("option");
  option.value = "";
  option.textContent = "Unassigned";
  dayCategory.appendChild(option);
  state.categories.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = String(cat.id);
    opt.textContent = cat.name;
    dayCategory.appendChild(opt);
  });

  categoryFilter.innerHTML = "";
  const allOpt = document.createElement("option");
  allOpt.value = "all";
  allOpt.textContent = "All";
  categoryFilter.appendChild(allOpt);
  state.categories.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = String(cat.id);
    opt.textContent = cat.name;
    categoryFilter.appendChild(opt);
  });
  categoryFilter.value = state.filterCategoryId;
}

function renderCategories() {
  categoryList.innerHTML = "";
  state.categories.forEach((cat) => {
    const item = document.createElement("div");
    item.className = "category-item";
    const swatch = document.createElement("div");
    swatch.className = "category-swatch";
    swatch.style.background = cat.color;

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.value = cat.name;

    const colorInput = document.createElement("input");
    colorInput.type = "color";
    colorInput.value = cat.color;

    nameInput.addEventListener("change", () => {
      sendMessage({
        type: "update_category",
        id: cat.id,
        name: nameInput.value.trim(),
        color: colorInput.value,
        expectedVersion: cat.version,
      });
    });

    colorInput.addEventListener("change", () => {
      sendMessage({
        type: "update_category",
        id: cat.id,
        name: nameInput.value.trim(),
        color: colorInput.value,
        expectedVersion: cat.version,
      });
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.textContent = "✕";
    deleteBtn.className = "ghost";
    deleteBtn.addEventListener("click", () => {
      sendMessage({
        type: "delete_category",
        id: cat.id,
        expectedVersion: cat.version,
      });
    });

    item.appendChild(swatch);
    item.appendChild(nameInput);
    item.appendChild(colorInput);
    item.appendChild(deleteBtn);
    categoryList.appendChild(item);
  });
}

function getCategoryColor(categoryId) {
  const category = state.categories.find((cat) => cat.id === categoryId);
  return category?.color || "var(--panel-light)";
}

function shouldDim(categoryId) {
  if (state.filterCategoryId === "all") {
    return false;
  }
  return String(categoryId) !== String(state.filterCategoryId);
}

function renderYearView() {
  const year = state.currentDate.getFullYear();
  currentLabel.textContent = String(year);
  const yearGrid = document.createElement("div");
  yearGrid.className = "year-grid";
  for (let month = 0; month < 12; month += 1) {
    const monthEl = document.createElement("div");
    monthEl.className = "month";
    const title = document.createElement("h3");
    title.textContent = new Date(year, month).toLocaleString(undefined, {
      month: "long",
    });
    const grid = document.createElement("div");
    grid.className = "month-grid";
    const totalDays = daysInMonth(year, month);
    const firstDay = new Date(year, month, 1);
    const offset = (firstDay.getDay() + 6) % 7;
    for (let i = 0; i < offset; i += 1) {
      const empty = document.createElement("div");
      empty.className = "day-cell";
      empty.style.opacity = "0.15";
      grid.appendChild(empty);
    }
    for (let day = 1; day <= totalDays; day += 1) {
      const cell = document.createElement("div");
      cell.className = "day-cell";
      const dateObj = new Date(year, month, day);
      const iso = formatDate(dateObj);
      const entry = state.days.get(iso);
      if (entry) {
        cell.style.background = getCategoryColor(entry.category_id);
        if (entry.note) {
          cell.classList.add("note");
          cell.dataset.note = entry.note;
        }
        if (shouldDim(entry.category_id)) {
          cell.classList.add("dim");
        }
      } else if (state.filterCategoryId !== "all") {
        cell.classList.add("dim");
      }
      const label = document.createElement("span");
      label.textContent = String(day);
      cell.appendChild(label);
      cell.addEventListener("click", () => {
        setSelectedDate(dateObj);
      });
      grid.appendChild(cell);
    }
    monthEl.appendChild(title);
    monthEl.appendChild(grid);
    yearGrid.appendChild(monthEl);
  }
  calendarEl.innerHTML = "";
  calendarEl.appendChild(yearGrid);
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
  const totalDays = daysInMonth(year, month);
  const firstDay = new Date(year, month, 1);
  const offset = (firstDay.getDay() + 6) % 7;
  for (let i = 0; i < offset; i += 1) {
    const empty = document.createElement("div");
    empty.className = "day-card";
    empty.style.opacity = "0.15";
    grid.appendChild(empty);
  }
  for (let day = 1; day <= totalDays; day += 1) {
    const dateObj = new Date(year, month, day);
    grid.appendChild(createDayCard(dateObj));
  }
  calendarEl.innerHTML = "";
  calendarEl.appendChild(grid);
}

function createDayCard(dateObj) {
  const iso = formatDate(dateObj);
  const entry = state.days.get(iso);
  const card = document.createElement("div");
  card.className = "day-card";
  card.style.background = entry
    ? getCategoryColor(entry.category_id)
    : "var(--panel)";
  if (entry && shouldDim(entry.category_id)) {
    card.classList.add("dim");
  } else if (!entry && state.filterCategoryId !== "all") {
    card.classList.add("dim");
  }
  const title = document.createElement("h4");
  title.textContent = dateObj.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
  });
  card.appendChild(title);
  if (entry?.note) {
    const note = document.createElement("p");
    note.textContent = entry.note;
    card.appendChild(note);
  }
  card.addEventListener("click", () => {
    setSelectedDate(dateObj);
  });
  return card;
}

function renderWeekView() {
  const start = startOfWeek(state.currentDate);
  currentLabel.textContent = `Week of ${start.toLocaleDateString()}`;
  const grid = document.createElement("div");
  grid.className = "week-grid";
  for (let i = 0; i < 7; i += 1) {
    const dateObj = addDays(start, i);
    grid.appendChild(createDayCard(dateObj));
  }
  calendarEl.innerHTML = "";
  calendarEl.appendChild(grid);
}

function renderCalendar() {
  updateViewButtons();
  if (state.view === "year") {
    renderYearView();
  } else if (state.view === "month") {
    renderMonthView();
  } else {
    renderWeekView();
  }
}

function suggestColors(palette, existing, limit = 5) {
  if (!palette.length) return [];
  if (!existing.length) return palette.slice(0, limit);
  const toRgb = (hex) => {
    const value = hex.replace("#", "");
    return [
      parseInt(value.slice(0, 2), 16),
      parseInt(value.slice(2, 4), 16),
      parseInt(value.slice(4, 6), 16),
    ];
  };
  const distance = (a, b) => {
    const [ar, ag, ab] = toRgb(a);
    const [br, bg, bb] = toRgb(b);
    return Math.sqrt((ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2);
  };
  const scored = palette.map((candidate) => {
    const min = Math.min(...existing.map((c) => distance(candidate, c)));
    return { candidate, score: min };
  });
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, limit).map((item) => item.candidate);
}

function handleSnapshot(data) {
  state.categories = data.categories || [];
  state.days = new Map(
    (data.days || []).map((entry) => [entry.date, entry])
  );
  state.palette = data.palette || [];
  state.userVersion = data.user?.version ?? null;
  categoriesPanel.classList.remove("hidden");
  updateCategorySelects();
  renderCategories();
  renderCalendar();
}

function sendMessage(payload) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    return;
  }
  state.ws.send(JSON.stringify(payload));
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
  state.ws = ws;

  ws.addEventListener("open", () => {
    setStatus("Connected", true);
    reconnectDelay = 500;
    sendMessage({ type: "auth", token: state.token });
  });

  ws.addEventListener("message", (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "snapshot") {
      handleSnapshot(data);
    }
    if (data.type === "category_created") {
      state.categories.push(data.category);
      updateCategorySelects();
      renderCategories();
      renderCalendar();
    }
    if (data.type === "category_updated") {
      const index = state.categories.findIndex(
        (cat) => cat.id === data.category.id
      );
      if (index !== -1) {
        state.categories[index] = data.category;
      }
      updateCategorySelects();
      renderCategories();
      renderCalendar();
    }
    if (data.type === "category_deleted") {
      state.categories = state.categories.filter(
        (cat) => cat.id !== data.id
      );
      updateCategorySelects();
      renderCategories();
      renderCalendar();
    }
    if (data.type === "day_updated") {
      state.days.set(data.day.date, data.day);
      renderCalendar();
      if (state.selectedDate && formatDate(state.selectedDate) === data.day.date) {
        setSelectedDate(state.selectedDate);
      }
    }
    if (data.type === "day_deleted") {
      state.days.delete(data.date);
      renderCalendar();
      if (state.selectedDate && formatDate(state.selectedDate) === data.date) {
        setSelectedDate(state.selectedDate);
      }
    }
    if (data.type === "password_updated") {
      passwordMessage.textContent = "Password updated.";
      if (data.user?.version) {
        state.userVersion = data.user.version;
      }
    }
    if (data.type === "error") {
      if (["invalid_credentials", "password_too_short"].includes(data.message)) {
        passwordMessage.textContent = data.message.replaceAll("_", " ");
      } else {
        dayMessage.textContent = data.message.replaceAll("_", " ");
      }
    }
  });

  ws.addEventListener("close", () => {
    setStatus("Disconnected");
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
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
  if (!response.ok) {
    throw new Error("Invalid credentials");
  }
  const data = await response.json();
  state.token = data.token;
  return data.token;
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const password = new FormData(loginForm).get("password");
  try {
    await login(String(password));
    loginForm.reset();
    loginPanel.classList.add("hidden");
    categoriesPanel.classList.remove("hidden");
    configPanel.classList.remove("hidden");
    toggleConfig.disabled = false;
    connectWebSocket();
  } catch (error) {
    loginError.textContent = "Login failed.";
  }
});

addCategoryBtn.addEventListener("click", () => {
  const name = prompt("Category name?");
  if (!name) return;
  const suggestions = suggestColors(
    state.palette,
    state.categories.map((cat) => cat.color)
  );
  const color = prompt(
    `Hex color? Suggestions: ${suggestions.join(", ")}`
  );
  sendMessage({
    type: "create_category",
    name: name.trim(),
    color: color ? color.trim() : suggestions[0] || "#64748b",
  });
});

saveDayBtn.addEventListener("click", () => {
  if (!state.selectedDate) return;
  const iso = formatDate(state.selectedDate);
  const entry = state.days.get(iso);
  sendMessage({
    type: "set_day",
    date: iso,
    categoryId: dayCategory.value,
    note: dayNote.value.trim() || null,
    expectedVersion: entry ? entry.version : null,
  });
  dayMessage.textContent = "Saved.";
});

clearDayBtn.addEventListener("click", () => {
  if (!state.selectedDate) return;
  const iso = formatDate(state.selectedDate);
  const entry = state.days.get(iso);
  if (!entry) {
    dayMessage.textContent = "No entry to clear.";
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

categoryFilter.addEventListener("change", () => {
  state.filterCategoryId = categoryFilter.value;
  renderCalendar();
});

prevPeriod.addEventListener("click", () => {
  if (state.view === "year") {
    state.currentDate = new Date(state.currentDate.getFullYear() - 1, 0, 1);
  } else if (state.view === "month") {
    state.currentDate = new Date(
      state.currentDate.getFullYear(),
      state.currentDate.getMonth() - 1,
      1
    );
  } else {
    state.currentDate = addDays(state.currentDate, -7);
  }
  renderCalendar();
});

nextPeriod.addEventListener("click", () => {
  if (state.view === "year") {
    state.currentDate = new Date(state.currentDate.getFullYear() + 1, 0, 1);
  } else if (state.view === "month") {
    state.currentDate = new Date(
      state.currentDate.getFullYear(),
      state.currentDate.getMonth() + 1,
      1
    );
  } else {
    state.currentDate = addDays(state.currentDate, 7);
  }
  renderCalendar();
});

viewButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    state.view = btn.dataset.view;
    renderCalendar();
  });
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

toggleConfig.addEventListener("click", () => {
  configPanel.classList.toggle("hidden");
});

setStatus("Offline");
updateViewButtons();
renderCalendar();
