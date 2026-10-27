const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chooseNotices } = require('../docs/assets/news-ticker.js');
const scheduled = { title:'Next', status:'scheduled', start:'2026-12-02T00:00:00-07:00', end:'2026-12-04T00:00:00-07:00' };
test('scheduled window includes start and excludes end in Albuquerque time', () => {
  assert.deepEqual(chooseNotices([scheduled], Date.parse('2026-12-02T06:59:59Z')), [scheduled]);
  assert.deepEqual(chooseNotices([scheduled], Date.parse(scheduled.start)), [scheduled]);
  assert.deepEqual(chooseNotices([scheduled], Date.parse(scheduled.end)), []);
});
test('ongoing incidents stay visible; resolved and expired notices do not', () => {
  const active = { ...scheduled, status:'active' };
  assert.deepEqual(chooseNotices([scheduled, active, {...scheduled,status:'resolved'}], Date.parse('2027-01-01')), [active]);
});
test('show all current incidents, then only the earliest future window', () => {
  const active = { title:'Incident',status:'active' };
  const later = { ...scheduled, start:'2026-12-10T00:00:00-07:00', end:'2026-12-11T00:00:00-07:00' };
  assert.deepEqual(chooseNotices([later,scheduled,active], Date.parse('2026-10-27')), [active,scheduled]);
});
