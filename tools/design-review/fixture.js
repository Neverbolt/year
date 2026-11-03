// Loaded only by the development comparison server. All edits stay in memory.
const fixture = {
  type: "snapshot", user: {role: "admin", version: 1}, palette: ["#38bdf8", "#a78bfa"],
  categories: [{id: 1, name: "Time off", color: "#38bdf8", version: 1}, {id: 2, name: "Focus", color: "#6d28d9", version: 1}],
  dayLabels: [{id: 1, name: "Weekend", color: "#a78bfa", marker_style: "corner", version: 1}, {id: 2, name: "Holiday", color: "#fbbf24", marker_style: "circle", version: 1}],
  days: [{date: "2026-01-05", category_id: 1, corner_label_id: null, circle_label_id: null, version: 1}, {date: "2026-01-06", category_id: 2, corner_label_id: null, circle_label_id: null, version: 1}, {date: "2026-01-10", category_id: 1, corner_label_id: null, circle_label_id: 2, version: 1}],
  noteRanges: [{id: 1, start_date: "2026-01-01", end_date: "2026-01-03", note: "A fresh start", version: 1}, {id: 2, start_date: "2026-01-05", end_date: "2026-01-05", note: "Day off", version: 1}, {id: 3, start_date: "2026-01-06", end_date: "2026-01-06", note: "Deep work", version: 1}, {id: 4, start_date: "2026-02-09", end_date: "2026-02-13", note: "Winter getaway", version: 1}],
};
window.fetch = async (url) => ({ok: true, json: async () => String(url).includes('/users') ? {users: []} : {role: "admin", version: 1}});
window.WebSocket = class extends EventTarget {
  static OPEN = 1;
  constructor() {
    super(); this.readyState = 1;
    setTimeout(() => { this.dispatchEvent(new Event('open')); this.emit(fixture); }, 0);
  }
  emit(data) { this.dispatchEvent(new MessageEvent('message', {data: JSON.stringify(data)})); }
  send(raw) {
    const data = JSON.parse(raw);
    if (data.type !== 'populate_weekends') return;
    const label = fixture.dayLabels.find(label => label.id === data.labelId);
    const slot = label.marker_style === 'circle' ? 'circle_label_id' : 'corner_label_id';
    let count = 0;
    for (let day = new Date(data.year, 0, 1); day.getFullYear() === data.year; day.setDate(day.getDate()+1)) {
      if (![0,6].includes(day.getDay())) continue;
      const iso = `${data.year}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;
      let entry = fixture.days.find(entry => entry.date === iso);
      if (entry?.[slot]) continue;
      if (!entry) { entry = {date: iso, category_id: null, corner_label_id: null, circle_label_id: null, version: 0}; fixture.days.push(entry); }
      entry[slot] = label.id; entry.version++; count++;
    }
    setTimeout(() => { this.emit(fixture); this.emit({type: 'weekends_populated', count, year: data.year}); }, 150);
  }
  close() { this.readyState = 3; this.dispatchEvent(new Event('close')); }
};
