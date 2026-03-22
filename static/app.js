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
  userRole: null,
  managedUsers: [],
  sessionActive: false,
  brushCategoryId: null,
  painting: false,
  dragStartDate: null,
  dragCurrentDate: null,
  previewDates: new Set(),
  lastSelectedDate: null,
  suppressNextClick: false,
};

const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");
const loginScreen = document.getElementById("loginScreen");
const appShell = document.getElementById("appShell");
const categoryList = document.getElementById("categoryList");
const categoryFilter = document.getElementById("categoryFilter");
const addCategoryBtn = document.getElementById("addCategory");
const calendarEl = document.getElementById("calendar");
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
const toggleConfig = document.getElementById("toggleConfig");
const toggleCategories = document.getElementById("toggleCategories");
const passwordForm = document.getElementById("passwordForm");
const passwordMessage = document.getElementById("passwordMessage");
const logoutButton = document.getElementById("logoutButton");
const categoryForm = document.getElementById("categoryForm");
const categoryNameInput = document.getElementById("categoryNameInput");
const categoryColorInput = document.getElementById("categoryColorInput");
const categoryMessage = document.getElementById("categoryMessage");
const suggestedColors = document.getElementById("suggestedColors");
const brushPalette = document.getElementById("brushPalette");
const paintToolbarTitle = document.getElementById("paintToolbarTitle");
const paintToolbarHint = document.getElementById("paintToolbarHint");
const userAdminSection = document.getElementById("userAdminSection");
const userForm = document.getElementById("userForm");
const userNameInput = document.getElementById("userNameInput");
const userRoleInput = document.getElementById("userRoleInput");
const userPasswordInput = document.getElementById("userPasswordInput");
const newUserPermissions = document.getElementById("newUserPermissions");
const newUserPermissionHint = document.getElementById("newUserPermissionHint");
const userMessage = document.getElementById("userMessage");
const userList = document.getElementById("userList");

const modals = {
  categoriesModal: document.getElementById("categoriesModal"),
  configModal: document.getElementById("configModal"),
  categoryModal: document.getElementById("categoryModal"),
  dayModal: document.getElementById("dayModal"),
};

let reconnectTimer = null;
let reconnectDelay = 500;
let calendarHandlersBound = false;

function isAdmin() {
  return state.userRole === "admin";
}

function setStatus(text, ok = false) {
  connectionStatus.textContent = text;
  connectionStatus.style.color = ok ? "#22c55e" : "#f97316";
}

function setButtonsDisabled(disabled, elements) {
  elements.forEach((element) => {
    if (!element) return;
    element.disabled = disabled;
  });
}

function syncAccessUI() {
  const admin = isAdmin();
  userAdminSection.classList.toggle("hidden", !admin);
  addCategoryBtn.classList.toggle("hidden", !admin);
  document.body.classList.toggle("read-only-user", !admin);
  setButtonsDisabled(!admin, [addCategoryBtn, saveDayBtn, clearDayBtn]);
  passwordForm.querySelectorAll("input, button").forEach((element) => {
    element.disabled = !admin;
  });
  paintToolbarTitle.textContent = admin ? "Quick assign" : "Filter";
  paintToolbarHint.textContent = admin
    ? "Click a category to arm it · drag like text selection · release to save the final range."
    : "Click a category chip to filter the calendar.";
  passwordMessage.textContent = admin
    ? (passwordMessage.textContent === "Read-only users cannot change system settings." ? "" : passwordMessage.textContent)
    : "Read-only users cannot change system settings.";
}

function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
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

function openModal(name) {
  Object.entries(modals).forEach(([key, modal]) => {
    modal.classList.toggle("hidden", key !== name);
    modal.setAttribute("aria-hidden", key === name ? "false" : "true");
  });
}

function closeModal(name) {
  const modal = modals[name];
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
}

function closeAllModals() {
  Object.keys(modals).forEach(closeModal);
}

function updateViewButtons() {
  viewButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === state.view);
  });
}

function getCategoryColor(categoryId) {
  if (categoryId === "") return "#0f172a";
  const category = state.categories.find((cat) => String(cat.id) === String(categoryId));
  return category?.color || "#1f2937";
}

function getEntry(dateIso) {
  return state.days.get(dateIso) || null;
}

function shouldDim(categoryId) {
  if (state.filterCategoryId === "all") return false;
  return String(categoryId) !== String(state.filterCategoryId);
}

function getSelectedPermissionIds(container) {
  return [...container.querySelectorAll('input[type="checkbox"]:checked')].map((input) =>
    Number(input.value)
  );
}

function renderPermissionSelector(container, selectedIds = [], disabled = false) {
  container.innerHTML = "";
  if (!state.categories.length) {
    const empty = document.createElement("p");
    empty.className = "helper";
    empty.textContent = "Create categories first to assign category visibility.";
    container.appendChild(empty);
    return;
  }
  state.categories.forEach((category) => {
    const label = document.createElement("label");
    label.className = "permission-chip";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = String(category.id);
    input.checked = selectedIds.includes(category.id);
    input.disabled = disabled;
    const dot = document.createElement("span");
    dot.className = "color-dot";
    dot.style.background = category.color;
    const text = document.createElement("span");
    text.textContent = category.name;
    label.append(input, dot, text);
    container.appendChild(label);
  });
}

function updateCategorySelects() {
  dayCategory.innerHTML = "";
  const unassigned = document.createElement("option");
  unassigned.value = "";
  unassigned.textContent = "Unassigned";
  dayCategory.appendChild(unassigned);
  state.categories.forEach((cat) => {
    const option = document.createElement("option");
    option.value = String(cat.id);
    option.textContent = cat.name;
    dayCategory.appendChild(option);
  });

  categoryFilter.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "All";
  categoryFilter.appendChild(allOption);
  state.categories.forEach((cat) => {
    const option = document.createElement("option");
    option.value = String(cat.id);
    option.textContent = cat.name;
    categoryFilter.appendChild(option);
  });
  categoryFilter.value = state.filterCategoryId;

  renderPermissionSelector(newUserPermissions, getSelectedPermissionIds(newUserPermissions));
  if (userRoleInput.value === "admin") {
    newUserPermissionHint.textContent = "Admins automatically see every category.";
  } else {
    newUserPermissionHint.textContent = "Read-only users only see the categories checked here. Admins always see everything.";
  }
}

function renderBrushPalette() {
  brushPalette.innerHTML = "";
  const options = isAdmin()
    ? [{ id: "", name: "Unassigned", color: "#020617" }, ...state.categories]
    : [{ id: "all", name: "All", color: "#020617" }, ...state.categories];
  options.forEach((option) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "brush-chip";
    const isActive = isAdmin()
      ? String(state.brushCategoryId) === String(option.id)
      : String(state.filterCategoryId) === String(option.id);
    button.classList.toggle("active", isActive);
    button.innerHTML = `<span class="color-dot" style="background:${option.color}"></span><span>${option.name}</span>`;
    button.addEventListener("click", () => {
      if (isAdmin()) {
        if (String(state.brushCategoryId) === String(option.id)) {
          state.brushCategoryId = null;
        } else {
          state.brushCategoryId = option.id;
        }
        renderBrushPalette();
        return;
      }
      state.filterCategoryId = String(option.id);
      categoryFilter.value = state.filterCategoryId;
      renderBrushPalette();
      renderCalendar();
    });
    brushPalette.appendChild(button);
  });
}

function renderSuggestedColors() {
  suggestedColors.innerHTML = "";
  const colors = suggestColors(
    state.palette,
    state.categories.map((cat) => cat.color)
  );
  colors.forEach((color) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggested-color ghost";
    button.innerHTML = `<span class="color-dot" style="background:${color}"></span><span>${color}</span>`;
    button.addEventListener("click", () => {
      categoryColorInput.value = color;
    });
    suggestedColors.appendChild(button);
  });
  if (colors[0]) {
    categoryColorInput.value = colors[0];
  }
}

function renderCategories() {
  categoryList.innerHTML = "";
  const categoryCounts = new Map();
  state.days.forEach((entry) => {
    categoryCounts.set(
      entry.category_id,
      (categoryCounts.get(entry.category_id) || 0) + 1
    );
  });
  state.categories.forEach((cat) => {
    const item = document.createElement("div");
    item.className = "category-item";

    const swatch = document.createElement("div");
    swatch.className = "category-swatch";
    swatch.style.background = cat.color;

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.value = cat.name;
    nameInput.disabled = !isAdmin();

    const count = document.createElement("div");
    count.className = "helper category-count";
    count.textContent = `${categoryCounts.get(cat.id) || 0} days`;

    const colorInput = document.createElement("input");
    colorInput.type = "color";
    colorInput.value = cat.color;
    colorInput.disabled = !isAdmin();

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.textContent = "Save";
    saveButton.disabled = !isAdmin();
    saveButton.addEventListener("click", () => {
      sendMessage({
        type: "update_category",
        id: cat.id,
        name: nameInput.value.trim(),
        color: colorInput.value,
        expectedVersion: cat.version,
      });
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "ghost";
    deleteButton.textContent = "✕";
    deleteButton.disabled = !isAdmin();
    deleteButton.addEventListener("click", () => {
      sendMessage({
        type: "delete_category",
        id: cat.id,
        expectedVersion: cat.version,
      });
    });

    item.append(swatch, nameInput, count, colorInput, saveButton, deleteButton);
    categoryList.appendChild(item);
  });
}

function renderManagedUsers() {
  userList.innerHTML = "";
  if (!isAdmin()) return;
  if (!state.managedUsers.length) {
    const empty = document.createElement("p");
    empty.className = "helper panel-block";
    empty.textContent = "No users found yet.";
    userList.appendChild(empty);
    return;
  }

  state.managedUsers.forEach((managedUser) => {
    const card = document.createElement("form");
    card.className = "user-card panel-block stack compact";

    const header = document.createElement("div");
    header.className = "user-card-header";

    const titleWrap = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = managedUser.name;
    const meta = document.createElement("p");
    meta.className = "helper";
    meta.textContent = managedUser.role === "admin"
      ? "Admin users can see everything and can edit the system."
      : "Read-only users can only view the categories selected below.";
    titleWrap.append(name, meta);

    const badge = document.createElement("span");
    badge.className = `role-badge ${managedUser.role}`;
    badge.textContent = managedUser.role;
    header.append(titleWrap, badge);

    const roleLabel = document.createElement("label");
    roleLabel.textContent = "Role";
    const roleSelect = document.createElement("select");
    roleSelect.innerHTML = `
      <option value="readonly">Read only</option>
      <option value="admin">Admin</option>
    `;
    roleSelect.value = managedUser.role;
    roleLabel.appendChild(roleSelect);

    const activeLabel = document.createElement("label");
    activeLabel.className = "toggle-row";
    const activeCheckbox = document.createElement("input");
    activeCheckbox.type = "checkbox";
    activeCheckbox.checked = Boolean(managedUser.isActive);
    const activeText = document.createElement("span");
    activeText.textContent = "User can sign in";
    activeLabel.append(activeCheckbox, activeText);

    const passwordLabel = document.createElement("label");
    passwordLabel.textContent = "Replace password (optional)";
    const passwordInput = document.createElement("input");
    passwordInput.type = "password";
    passwordInput.minLength = 8;
    passwordInput.placeholder = "Leave blank to keep current password";
    passwordLabel.appendChild(passwordInput);

    const permissionsBlock = document.createElement("div");
    permissionsBlock.className = "stack compact";
    const permissionsTitle = document.createElement("div");
    permissionsTitle.className = "helper";
    permissionsTitle.textContent = "Category access";
    const permissionsList = document.createElement("div");
    permissionsList.className = "permission-list";
    permissionsBlock.append(permissionsTitle, permissionsList);

    const syncPermissions = () => {
      const adminRole = roleSelect.value === "admin";
      renderPermissionSelector(
        permissionsList,
        managedUser.categoryIds,
        adminRole
      );
      permissionsTitle.textContent = adminRole
        ? "Admins always see every category."
        : "Checked categories are visible to this read-only user.";
    };
    syncPermissions();
    roleSelect.addEventListener("change", syncPermissions);

    const message = document.createElement("p");
    message.className = "helper";

    const saveButton = document.createElement("button");
    saveButton.type = "submit";
    saveButton.textContent = "Save user";

    card.addEventListener("submit", async (event) => {
      event.preventDefault();
      message.textContent = "";
      const nextRole = roleSelect.value;
      const payload = {
        name: managedUser.name,
        role: nextRole,
        categoryIds: nextRole === "admin" ? [] : getSelectedPermissionIds(permissionsList),
        expectedVersion: managedUser.version,
        isActive: activeCheckbox.checked,
      };
      if (passwordInput.value.trim()) {
        payload.password = passwordInput.value;
      }
      try {
        await apiFetch(`/api/users/${managedUser.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        passwordInput.value = "";
        message.textContent = "Saved.";
        await fetchManagedUsers();
      } catch (error) {
        message.textContent = error.message;
      }
    });

    card.append(header, roleLabel, activeLabel, passwordLabel, permissionsBlock, saveButton, message);
    userList.appendChild(card);
  });
}

async function fetchManagedUsers() {
  if (!isAdmin()) {
    state.managedUsers = [];
    renderManagedUsers();
    return;
  }
  try {
    const data = await apiFetch("/api/users");
    state.managedUsers = Array.isArray(data.users) ? data.users : [];
    renderManagedUsers();
  } catch (error) {
    userMessage.textContent = error.message;
  }
}

function setSelectedDate(date) {
  state.selectedDate = date;
  state.lastSelectedDate = formatDate(date);
  dayMessage.textContent = "";
  const iso = formatDate(date);
  const entry = getEntry(iso);
  dayTitle.textContent = date.toDateString();
  dayCategory.value = entry ? String(entry.category_id) : "";
  dayNote.value = entry?.note ?? "";
  dayCategory.disabled = !isAdmin();
  dayNote.disabled = !isAdmin();
  saveDayBtn.disabled = !isAdmin();
  clearDayBtn.disabled = !isAdmin();
  if (!isAdmin()) {
    dayMessage.textContent = "Read-only users can inspect day details but cannot edit them.";
  }
  openModal("dayModal");
  renderCalendar();
}

function buildDayCell(dateObj, compact = true) {
  const iso = formatDate(dateObj);
  const entry = getEntry(iso);
  const element = document.createElement("div");
  element.className = compact ? "day-cell" : "day-card";
  element.dataset.date = iso;
  const color = entry ? getCategoryColor(entry.category_id) : "#1e293b";
  element.style.background = color;
  if (entry && shouldDim(entry.category_id)) {
    element.classList.add("dim");
  } else if (!entry && state.filterCategoryId !== "all") {
    element.classList.add("dim");
  }
  if (state.selectedDate && formatDate(state.selectedDate) === iso) {
    element.classList.add("selected");
  }
  if (state.previewDates.has(iso)) {
    element.classList.add("painting");
  }

  const title = document.createElement(compact ? "span" : "h4");
  title.textContent = compact
    ? String(dateObj.getDate())
    : dateObj.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
  element.appendChild(title);

  if (entry?.note) {
    if (compact) {
      element.classList.add("note");
      element.dataset.note = entry.note;
    } else {
      const note = document.createElement("p");
      note.textContent = entry.note;
      element.appendChild(note);
    }
  }

  return element;
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
    title.textContent = new Date(year, month).toLocaleString(undefined, { month: "long" });
    const grid = document.createElement("div");
    grid.className = "month-grid";
    const totalDays = daysInMonth(year, month);
    const firstDay = new Date(year, month, 1);
    const offset = (firstDay.getDay() + 6) % 7;
    for (let i = 0; i < offset; i += 1) {
      const spacer = document.createElement("div");
      spacer.className = "day-cell dim";
      grid.appendChild(spacer);
    }
    for (let day = 1; day <= totalDays; day += 1) {
      grid.appendChild(buildDayCell(new Date(year, month, day), true));
    }
    monthEl.append(title, grid);
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
    const spacer = document.createElement("div");
    spacer.className = "day-card dim";
    grid.appendChild(spacer);
  }
  for (let day = 1; day <= totalDays; day += 1) {
    grid.appendChild(buildDayCell(new Date(year, month, day), false));
  }
  calendarEl.innerHTML = "";
  calendarEl.appendChild(grid);
}

function renderWeekView() {
  const start = startOfWeek(state.currentDate);
  currentLabel.textContent = `Week of ${start.toLocaleDateString()}`;
  const grid = document.createElement("div");
  grid.className = "week-grid";
  for (let index = 0; index < 7; index += 1) {
    grid.appendChild(buildDayCell(addDays(start, index), false));
  }
  calendarEl.innerHTML = "";
  calendarEl.appendChild(grid);
}

function bindCalendarHandlers() {
  if (calendarHandlersBound) return;
  calendarEl.addEventListener("pointerdown", handleCalendarPointerDown);
  calendarEl.addEventListener("click", handleCalendarClick);
  calendarHandlersBound = true;
}

function unbindCalendarHandlers() {
  if (!calendarHandlersBound) return;
  calendarEl.removeEventListener("pointerdown", handleCalendarPointerDown);
  calendarEl.removeEventListener("click", handleCalendarClick);
  calendarHandlersBound = false;
}

function syncCalendarHandlers() {
  if (isAdmin() && state.brushCategoryId !== null) {
    bindCalendarHandlers();
  } else {
    unbindCalendarHandlers();
  }
}

function renderCalendar() {
  updateViewButtons();
  renderBrushPalette();
  syncCalendarHandlers();
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
  return palette
    .map((candidate) => ({
      candidate,
      score: Math.min(...existing.map((color) => distance(candidate, color))),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((item) => item.candidate);
}

function applyLocalDayState(date, categoryId, note) {
  const existing = getEntry(date);
  if (categoryId === null || categoryId === "") {
    if (existing) {
      state.days.delete(date);
    }
    return;
  }
  const nextVersion = existing ? existing.version + 1 : 1;
  state.days.set(date, {
    date,
    category_id: Number(categoryId),
    note,
    version: nextVersion,
  });
}

function sendDayUpdate(date, categoryId, note = null) {
  if (!isAdmin()) return;
  const entry = getEntry(date);
  if ((categoryId === null || categoryId === "") && !entry) {
    return;
  }
  sendMessage({
    type: "set_day",
    date,
    categoryId,
    note,
    expectedVersion: entry ? entry.version : null,
  });
  applyLocalDayState(date, categoryId, note);
}

function dateRange(startIso, endIso) {
  const start = parseDate(startIso);
  const end = parseDate(endIso);
  const forward = start <= end;
  const dates = [];
  let current = forward ? start : end;
  const last = forward ? end : start;
  while (current <= last) {
    dates.push(formatDate(current));
    current = addDays(current, 1);
  }
  return dates;
}

function setPreviewRange(startIso, currentIso) {
  state.previewDates = new Set(dateRange(startIso, currentIso));
}

function commitPreviewRange() {
  if (!isAdmin() || !state.previewDates.size || state.brushCategoryId === null) return;
  const categoryId = state.brushCategoryId === "" ? null : state.brushCategoryId;
  state.previewDates.forEach((date) => {
    sendDayUpdate(date, categoryId);
  });
  state.lastSelectedDate = state.dragCurrentDate || state.dragStartDate;
}

function handleRangeAssign(targetIso) {
  if (!isAdmin() || !state.lastSelectedDate) return false;
  const range = dateRange(state.lastSelectedDate, targetIso);
  range.forEach((date) => {
    sendDayUpdate(date, state.brushCategoryId === "" ? null : state.brushCategoryId);
  });
  renderCalendar();
  return true;
}

function handleDayClick(event, iso) {
  if (state.suppressNextClick) {
    state.suppressNextClick = false;
    return;
  }
  if (state.painting) return;
  if (event.shiftKey && state.brushCategoryId !== null) {
    if (handleRangeAssign(iso)) {
      state.lastSelectedDate = iso;
      return;
    }
  }
  setSelectedDate(parseDate(iso));
}

function handleCalendarClick(event) {
  const target = event.target.closest?.("[data-date]");
  const iso = target?.dataset?.date;
  if (!iso) return;
  handleDayClick(event, iso);
}

function handleCalendarPointerDown(event) {
  const target = event.target.closest?.("[data-date]");
  const iso = target?.dataset?.date;
  if (!iso) return;
  handleDayPointerStart(event, iso);
}

function handleDayPointerStart(event, iso) {
  if (!isAdmin() || state.brushCategoryId === null) return;
  if (event.pointerType === "mouse" && event.button !== 0) return;
  event.preventDefault();
  state.painting = true;
  state.dragStartDate = iso;
  state.dragCurrentDate = iso;
  setPreviewRange(iso, iso);
  if (event.currentTarget?.setPointerCapture) {
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  renderCalendar();
}

function updatePaintingFromPoint(clientX, clientY, fallbackTarget = null) {
  if (!state.painting || !state.dragStartDate) return;
  const target =
    fallbackTarget?.closest?.("[data-date]") ||
    document.elementFromPoint(clientX, clientY)?.closest?.("[data-date]");
  const iso = target?.dataset?.date;
  if (!iso || iso === state.dragCurrentDate) return;
  state.dragCurrentDate = iso;
  setPreviewRange(state.dragStartDate, state.dragCurrentDate);
  renderCalendar();
}

function stopPainting() {
  if (!state.painting) return;
  commitPreviewRange();
  state.suppressNextClick = true;
  state.painting = false;
  state.dragStartDate = null;
  state.dragCurrentDate = null;
  state.previewDates = new Set();
  renderCalendar();
}

async function syncAdminData() {
  syncAccessUI();
  renderManagedUsers();
  if (isAdmin()) {
    await fetchManagedUsers();
  }
}

async function handleSnapshot(data) {
  state.categories = data.categories || [];
  state.days = new Map((data.days || []).map((entry) => [entry.date, entry]));
  state.palette = data.palette || [];
  state.userVersion = data.user?.version ?? null;
  state.userRole = data.user?.role ?? state.userRole;
  if (
    state.brushCategoryId !== null &&
    !["", ...state.categories.map((cat) => String(cat.id))].includes(String(state.brushCategoryId))
  ) {
    state.brushCategoryId = null;
  }
  updateCategorySelects();
  renderCategories();
  renderSuggestedColors();
  renderCalendar();
  await syncAdminData();
}

function sendMessage(payload) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify(payload));
}

async function apiFetch(url, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const response = await fetch(url, {
    ...options,
    headers,
  });
  if (!response.ok) {
    let message = response.statusText || "Request failed";
    try {
      message = await response.text();
    } catch (_error) {
      // ignore body parsing errors
    }
    throw new Error(message.replaceAll("_", " "));
  }
  return response.json();
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  state.ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

  state.ws.addEventListener("open", () => {
    setStatus("Connected", true);
    reconnectDelay = 500;
    if (state.token) sendMessage({ type: "auth", token: state.token });
  });

  state.ws.addEventListener("message", async (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "snapshot") await handleSnapshot(data);
    if (data.type === "category_created") {
      state.categories.push(data.category);
      updateCategorySelects();
      renderCategories();
      renderSuggestedColors();
      renderCalendar();
      renderManagedUsers();
    }
    if (data.type === "category_updated") {
      const index = state.categories.findIndex((cat) => cat.id === data.category.id);
      if (index !== -1) state.categories[index] = data.category;
      updateCategorySelects();
      renderCategories();
      renderSuggestedColors();
      renderCalendar();
      renderManagedUsers();
    }
    if (data.type === "category_deleted") {
      state.categories = state.categories.filter((cat) => cat.id !== data.id);
      updateCategorySelects();
      renderCategories();
      renderSuggestedColors();
      renderCalendar();
      renderManagedUsers();
    }
    if (data.type === "day_updated") {
      state.days.set(data.day.date, data.day);
      renderCategories();
      renderCalendar();
      if (state.selectedDate && formatDate(state.selectedDate) === data.day.date) {
        const selected = parseDate(data.day.date);
        setSelectedDate(selected);
      }
    }
    if (data.type === "day_deleted") {
      state.days.delete(data.date);
      renderCategories();
      renderCalendar();
      if (state.selectedDate && formatDate(state.selectedDate) === data.date) {
        closeModal("dayModal");
      }
    }
    if (data.type === "password_updated") {
      passwordMessage.textContent = "Password updated.";
      if (data.user?.version) state.userVersion = data.user.version;
    }
    if (data.type === "error") {
      const message = data.message.replaceAll("_", " ");
      if (["invalid_credentials", "password_too_short", "read_only"].includes(data.message)) {
        passwordMessage.textContent = message;
      } else if (data.message.startsWith("invalid_") || data.message === "category_in_use") {
        categoryMessage.textContent = message;
        dayMessage.textContent = message;
        userMessage.textContent = message;
      } else {
        dayMessage.textContent = message;
      }
    }
  });

  state.ws.addEventListener("close", () => {
    setStatus("Disconnected");
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (!state.sessionActive) return;
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
  if (!response.ok) throw new Error("Invalid credentials");
  const data = await response.json();
  state.token = null;
  state.userRole = data.role || null;
}

function showAppShell() {
  state.sessionActive = true;
  document.body.classList.remove("auth-only");
  loginScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
}

function showLoginScreen() {
  state.sessionActive = false;
  document.body.classList.add("auth-only");
  loginScreen.classList.remove("hidden");
  appShell.classList.add("hidden");
}

async function restoreSession() {
  try {
    const me = await apiFetch("/api/me", { headers: {} });
    state.userRole = me.role || null;
    state.userVersion = me.version ?? null;
    showAppShell();
    if (state.userRole === "admin") await fetchManagedUsers();
    connectWebSocket();
    return true;
  } catch (_error) {
    showLoginScreen();
    return false;
  }
}

async function logout() {
  try {
    await fetch("/api/logout", { method: "POST" });
  } finally {
    state.sessionActive = false;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    state.token = null;
    state.userRole = null;
    state.userVersion = null;
    state.managedUsers = [];
    state.categories = [];
    state.days = new Map();
    if (state.ws) state.ws.close();
    closeAllModals();
    renderManagedUsers();
    renderCategories();
    renderCalendar();
    showLoginScreen();
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  try {
    await login(String(new FormData(loginForm).get("password")));
    loginForm.reset();
    showAppShell();
    if (state.userRole === "admin") await fetchManagedUsers();
    connectWebSocket();
  } catch (_error) {
    loginError.textContent = "Login failed.";
  }
});

addCategoryBtn.addEventListener("click", () => {
  categoryForm.reset();
  categoryMessage.textContent = "";
  renderSuggestedColors();
  openModal("categoryModal");
  categoryNameInput.focus();
});

categoryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!isAdmin()) return;
  sendMessage({
    type: "create_category",
    name: categoryNameInput.value.trim(),
    color: categoryColorInput.value,
  });
  closeModal("categoryModal");
});

saveDayBtn.addEventListener("click", () => {
  if (!state.selectedDate || !isAdmin()) return;
  const iso = formatDate(state.selectedDate);
  sendDayUpdate(iso, dayCategory.value || null, dayNote.value.trim() || null);
  dayMessage.textContent = "Saved.";
  renderCalendar();
});

clearDayBtn.addEventListener("click", () => {
  if (!state.selectedDate || !isAdmin()) return;
  const iso = formatDate(state.selectedDate);
  if (!getEntry(iso)) {
    dayMessage.textContent = "No entry to clear.";
    return;
  }
  sendDayUpdate(iso, null);
  closeModal("dayModal");
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

passwordForm.addEventListener("submit", (event) => {
  event.preventDefault();
  passwordMessage.textContent = "";
  if (!isAdmin()) return;
  sendMessage({
    type: "update_password",
    currentPassword: document.getElementById("currentPassword").value,
    newPassword: document.getElementById("newPassword").value,
    expectedVersion: state.userVersion,
  });
  passwordForm.reset();
});

userRoleInput.addEventListener("change", () => {
  const role = userRoleInput.value;
  const disablePermissions = role === "admin";
  newUserPermissionHint.textContent = disablePermissions
    ? "Admins automatically see every category."
    : "Read-only users only see the categories checked here. Admins always see everything.";
  newUserPermissions.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.disabled = disablePermissions;
    if (disablePermissions) input.checked = false;
  });
});

userForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  userMessage.textContent = "";
  try {
    await apiFetch("/api/users", {
      method: "POST",
      body: JSON.stringify({
        name: userNameInput.value.trim(),
        role: userRoleInput.value,
        password: userPasswordInput.value,
        categoryIds: userRoleInput.value === "admin" ? [] : getSelectedPermissionIds(newUserPermissions),
      }),
    });
    userForm.reset();
    userRoleInput.value = "readonly";
    updateCategorySelects();
    userMessage.textContent = "User created.";
    await fetchManagedUsers();
  } catch (error) {
    userMessage.textContent = error.message;
  }
});

logoutButton.addEventListener("click", logout);

toggleConfig.addEventListener("click", async () => {
  if (isAdmin()) await fetchManagedUsers();
  openModal("configModal");
});
toggleCategories.addEventListener("click", () => openModal("categoriesModal"));
document.querySelectorAll("[data-close-modal]").forEach((element) => {
  element.addEventListener("click", () => closeModal(element.dataset.closeModal));
});

document.addEventListener("pointermove", (event) => {
  updatePaintingFromPoint(event.clientX, event.clientY, event.target);
});
document.addEventListener("pointerup", stopPainting);
document.addEventListener("pointercancel", stopPainting);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAllModals();
    stopPainting();
  }
});

setStatus("Offline");
syncAccessUI();
updateViewButtons();
renderBrushPalette();
renderCalendar();
renderManagedUsers();
restoreSession();
