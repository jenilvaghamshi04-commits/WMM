// In the Google Sheet: Extensions > Apps Script. Paste this code.
// Project Settings > Script properties: GATEWAY_URL and DASHBOARD_KEY.
// Add an INSTALLABLE trigger: teamRadarOnEdit > From spreadsheet > On edit.
function teamRadarOnEdit(e) {
  const range = e.range;
  if (range.getSheet().getName() !== 'TeamRadar' || range.getColumn() !== 7 || range.getRow() < 2 || e.value !== 'TRUE' || range.getNumRows() !== 1 || range.getNumColumns() !== 1) return;
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return;
  try {
    const sheet = range.getSheet();
    const status = sheet.getRange(range.getRow(), 8);
    if (status.getValue() === 'Sent' || status.getValue() === 'Sending' || status.getValue() === 'Uncertain') return;
    const props = PropertiesService.getScriptProperties();
    const url = props.getProperty('GATEWAY_URL');
    const key = props.getProperty('DASHBOARD_KEY');
    if (!url || !key) { status.setValue('Configure Apps Script properties'); return; }
    status.setValue('Sending');
    try {
      const response = UrlFetchApp.fetch(url.replace(/\/$/, '') + '/sheet-send', {
        method: 'post', contentType: 'application/json',
        headers: {Authorization: 'Bearer ' + key},
        payload: JSON.stringify({id: String(sheet.getRange(range.getRow(),1).getValue())}),
        muteHttpExceptions: true
      });
      const body = JSON.parse(response.getContentText());
      status.setValue(response.getResponseCode() === 200 ? 'Sent' : (body.detail || 'Failed'));
    } catch (err) { status.setValue('Uncertain: check Telegram before retry'); }
  } finally { lock.releaseLock(); }
}
