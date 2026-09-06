const rows = [...document.querySelectorAll('.finding')];
const search = document.getElementById('search');
const rule = document.getElementById('rule');
const state = document.getElementById('state');
function filter() {
  const query = search.value.toLowerCase().trim();
  let visible = 0;
  rows.forEach(row => {
    const text = row.closest('.file-group').querySelector('.path').textContent + ' ' + row.textContent;
    row.hidden = !!((rule.value && row.dataset.rule !== rule.value) ||
      (state.value && row.dataset.state !== state.value) || !text.toLowerCase().includes(query));
    if (!row.hidden) visible++;
  });
  document.querySelectorAll('.file-group').forEach(group => {
    group.hidden = ![...group.querySelectorAll('.finding')].some(row => !row.hidden);
  });
  document.getElementById('visible-count').textContent = `${visible} of ${rows.length} findings shown`;
  document.getElementById('no-match').hidden = visible !== 0 || rows.length === 0;
}
search.addEventListener('input', filter);
rule.addEventListener('change', filter);
state.addEventListener('change', filter);
document.getElementById('expand').onclick = () => rows.filter(r => !r.hidden).forEach(r => r.open = true);
document.getElementById('collapse').onclick = () => rows.filter(r => !r.hidden).forEach(r => r.open = false);
let printState = [];
window.addEventListener('beforeprint', () => {
  printState = [...document.querySelectorAll('details')].map(d => [d, d.open]);
  printState.forEach(([d]) => { if (!d.hidden) d.open = true; });
});
window.addEventListener('afterprint', () => printState.forEach(([d, open]) => d.open = open));
document.getElementById('print').onclick = () => window.print();
filter();
