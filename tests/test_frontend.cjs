const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/app.js', 'utf8');
// Exercise production date/contrast/summary functions without a browser dependency.
const names = ['readableInk', 'formatDate', 'parseDate', 'addDays', 'dateRange', 'getEntry', 'getNoteRangeForDate', 'getDayLabel', 'isAdmin', 'renderYearOverview'];
const extracted = names.map(name => {
  const start = source.indexOf(`function ${name}(`);
  const next = source.indexOf('\nfunction ', start + 1);
  // renderYearOverview is the last function; other function bodies end at column zero.
  return source.slice(start, source.indexOf('\n}', start) + 2);
}).join('\n');
class Element {
  constructor() { this.children = []; this.value = ''; this.textContent = ''; this.style = {}; this.classList = {toggle(){}}; }
  replaceChildren(...children) { this.children = children; if (children[0]?.value) this.value = String(children[0].value); }
  append(...children) { this.children.push(...children); }
}
const elements = new Map();
const context = vm.createContext({
  document: {getElementById(id){ if (!elements.has(id)) elements.set(id,new Element()); return elements.get(id); }, createElement(){ return new Element(); }},
  state: {currentDate:new Date(2026,0,1),userRole:'admin',days:new Map([['2026-01-03',{category_id:1,corner_label_id:1}]]),categories:[{id:1,name:'Time off',color:'#38bdf8'}], dayLabels:[{id:1,name:'Weekend',marker_style:'corner',color:'#a78bfa'}],noteRanges:[{start_date:'2025-12-30',end_date:'2026-01-02'}],ws:{readyState:1}},
  yearMessage:new Element(), weekendLabelSelect:new Element(), populateWeekendsBtn:new Element(), weekendPending:false, WebSocket:{OPEN:1},
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
console.log('Frontend checks passed: dark/bright contrast, leap year, DST, year-scoped notes, statistics, weekend preview and access state.');
