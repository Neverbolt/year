const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/app.js', 'utf8');
// Exercise production date/contrast/summary functions without a browser dependency.
const names = ['readableInk', 'getSelectedPermissionIds', 'daysInMonth', 'formatDate', 'parseDate', 'addDays', 'dateRange', 'getEntry', 'getNoteRangeForDate', 'getDayLabel', 'isAdmin', 'navigateOverviewYear', 'renderYearOverview', 'shouldDim', 'setCategoryFilter', 'buildDayCell', 'getCategoryColor', 'getDayLabelColor', 'renderDayLabelValueSummary', 'getNoteRangeShape', 'dayDiff', 'startOfWeek', 'todayIso', 'renderYearView', 'renderMonthView', 'renderWeekView', 'updateCategorySelects'];
const extracted = names.map(name => {
  const start = source.indexOf(`function ${name}(`);
  const next = source.indexOf('\nfunction ', start + 1);
  // renderYearOverview is the last function; other function bodies end at column zero.
  return source.slice(start, source.indexOf('\n}', start) + 2);
}).join('\n');
class Element {
  constructor() {
    this.children = []; this.value = ''; this.textContent = ''; this.dataset = {}; this.attributes = {};
    this.style = {setProperty(name, value){this[name] = value;}};
    const classes = new Set();
    this.classList = {
      add(...names){names.forEach(name => classes.add(name));},
      contains(name){return classes.has(name);},
      toggle(name, enabled){if(enabled) classes.add(name); else classes.delete(name);},
    };
  }
  set innerHTML(value) { this.children = []; }
  replaceChildren(...children) { this.children = children; if (children[0]?.value) this.value = String(children[0].value); }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); }
  setAttribute(name, value) { this.attributes[name] = value; }
  querySelectorAll() { return []; }
}

const elements = new Map();
const context = vm.createContext({
  document: {getElementById(id){ if (!elements.has(id)) elements.set(id,new Element()); return elements.get(id); }, createElement(){ return new Element(); }},
  state: {currentDate:new Date(2026,0,1),userRole:'admin',days:new Map([['2026-01-03',{category_id:1,corner_label_id:1}]]),categories:[{id:1,name:'Time off',color:'#38bdf8'}], dayLabels:[{id:1,name:'Weekend',marker_style:'corner',color:'#a78bfa'}],noteRanges:[{start_date:'2025-12-30',end_date:'2026-01-02'}],ws:{readyState:1}},
  yearMessage:new Element(), weekendLabelSelect:new Element(), populateWeekendsBtn:new Element(), weekendPending:false, WebSocket:{OPEN:1},
  calendarEl: new Element(), currentLabel: new Element(), categoryFilter: new Element(), newUserPermissions: new Element(), userRoleInput: new Element(), newUserPermissionHint: new Element(),
  renderPermissionSelector(){},
  Option: function(text,value){this.text=text;this.value=value;}, Date,
});
vm.runInContext(extracted, context);
const call = code => vm.runInContext(code, context);
assert.equal(call('readableInk("#1e293b")'),'#ffffff');
assert.equal(call('readableInk("#6d28d9")'),'#ffffff');
assert.equal(call('readableInk("#38bdf8")'),'#000000');
assert.equal(call('readableInk("#ffffff")'),'#000000');
assert.equal(call('dateRange("2028-01-01","2028-12-31").length'),366);
assert.equal(call('dateRange("2026-03-07","2026-03-10").length'),4);
call('renderYearOverview()');
assert.deepEqual(elements.get('yearStats').children.map(card=>card.children[0].textContent),[365,1,2,104]);
assert.equal(elements.get('weekendPreview').textContent,'103 weekends to label · 1 existing markers kept.');
assert.equal(context.populateWeekendsBtn.disabled,false);
context.state.ws.readyState=3;
call('renderYearOverview()');
assert.equal(context.populateWeekendsBtn.disabled,true);
context.state.userRole='readonly';
call('renderYearOverview()');
assert.equal(context.populateWeekendsBtn.disabled,true);
context.renderCalendar = () => call('renderYearOverview()');
call('navigateOverviewYear(-1)');
assert.equal(context.state.currentDate.getFullYear(), 2025);
assert.equal(elements.get('yearOverviewTitle').textContent, '2025');
assert.equal(elements.get('yearStats').children[2].children[0].textContent, 2);
call('navigateOverviewYear(1)');
assert.equal(context.state.currentDate.getFullYear(), 2026);
context.state.currentDate = new Date(2027, 0, 1);
call('navigateOverviewYear(1)');
assert.equal(elements.get('yearStats').children[0].children[0].textContent, 366);
context.state.currentDate = new Date(1000, 0, 1);
call('navigateOverviewYear(-1)');
assert.equal(context.state.currentDate.getFullYear(), 1000);
// Filtering is local, leaves painting/data intact, and applies in every calendar view.
context.state.categories.push({id:2,name:'Focus',color:'#6d28d9'});
context.state.days.set('2026-01-04',{category_id:2});
context.state.days.set('2026-01-06',{category_id:null,corner_label_id:1});
context.state.noteRanges.push({start_date:'2026-01-05',end_date:'2026-01-05',note:'Keep this note'});
context.state.previewDates = new Set();
context.state.brushCategoryId = 2;
context.state.currentDate = new Date(2026,0,1);
context.state.filterCategoryId = 'all';
const savedDays = JSON.stringify([...context.state.days]);
const savedNotes = JSON.stringify(context.state.noteRanges);
const cells = element => element.dataset.date ? [element] : element.children.flatMap(cells);
for(const render of ['renderYearView', 'renderMonthView', 'renderWeekView']) {
  context.renderCalendar = () => call(`${render}()`);
  call('setCategoryFilter("1")');
  let dates = cells(context.calendarEl);
  assert.equal(dates.find(el=>el.dataset.date==='2026-01-03').classList.contains('dim'), false);
  assert.equal(dates.find(el=>el.dataset.date==='2026-01-04').classList.contains('dim'), true);
  call('setCategoryFilter("__unassigned__")');
  dates = cells(context.calendarEl);
  assert.equal(dates.find(el=>el.dataset.date==='2026-01-03').classList.contains('dim'), true);
  assert.equal(dates.find(el=>el.dataset.date==='2026-01-01').classList.contains('dim'), false);
  if(render !== 'renderWeekView') {
    assert.equal(dates.find(el=>el.dataset.date==='2026-01-06').classList.contains('dim'), false);
    const noteDay = dates.find(el=>el.dataset.date==='2026-01-05');
    assert.equal(noteDay.classList.contains('dim'), false);
    assert.equal(noteDay.children.some(child=>child.textContent==='Keep this note'), true);
  }
  call('setCategoryFilter("all")');
  assert.equal(cells(context.calendarEl).some(el=>el.classList.contains('dim')), false);
}
assert.equal(context.state.brushCategoryId, 2);
assert.equal(JSON.stringify([...context.state.days]), savedDays);
assert.equal(JSON.stringify(context.state.noteRanges), savedNotes);
call('setCategoryFilter("999")');
assert.equal(context.state.filterCategoryId, 'all');
call('setCategoryFilter("2")');
context.state.categories = context.state.categories.filter(cat=>cat.id!==2);
call('updateCategorySelects()');
assert.equal(context.state.filterCategoryId, 'all');
assert.equal(context.categoryFilter.children.some(option=>option.value==='__unassigned__'),true);
console.log('Frontend checks passed: dark/bright contrast, leap year, DST, year-scoped notes, statistics, weekend preview, access state, year navigation and local filtering in year/month/week views.');
