// display_logic.js
// APIから受け取ったIssueData配列をテーブル描画・アコーディオン制御・件数インジケータ更新する純粋関数群

/**
 * IssueData型の配列を受け取り、テーブルtbodyのHTMLを生成する
 * @param {Array} issues - IssueData配列
 * @returns {string} tbody用HTML
 */
function renderIssueTableRows(issues) {
  if (!Array.isArray(issues)) return '';
  return issues.map((issue, idx) => `
    <tr data-bs-toggle="collapse" data-bs-target="#issueDetail${idx}" aria-expanded="false" aria-controls="issueDetail${idx}" class="issue-row-item">
      <td><input type="checkbox" class="form-check-input issue-checkbox" value="${issue.temp_id || ''}" onclick="event.stopPropagation();"></td>
      <td class="issue-title-clickable">${escapeHtml(issue.title)} <span class="ms-2 text-muted small">(Click to expand)</span></td>
      <td>${(issue.assignees||[]).map(a=>`<code>${escapeHtml(a)}</code>`).join(', ')}</td>
      <td>${(issue.labels||[]).map(l=>`<span class="badge bg-secondary">${escapeHtml(l)}</span>`).join(' ')}</td>
    </tr>
    <tr>
      <td colspan="4" class="p-0">
        <div class="collapse" id="issueDetail${idx}">
          <div class="card card-body bg-light">
            <strong>Description:</strong><br>${escapeHtml(issue.description||'').replace(/\n/g,'<br>')}<br>
            ${(issue.tasks && issue.tasks.length) ? `<strong>Tasks:</strong><ul>${issue.tasks.map(t=>`<li>${escapeHtml(t)}</li>`).join('')}</ul>` : ''}
            ${(issue.acceptance && issue.acceptance.length) ? `<strong>Acceptance Criteria:</strong><ul>${issue.acceptance.map(a=>`<li>${escapeHtml(a)}</li>`).join('')}</ul>` : ''}
          </div>
        </div>
      </td>
    </tr>
  `).join('');
}

/**
 * HTMLエスケープ
 */
function escapeHtml(str) {
  return String(str).replace(/[&<>'"]/g, function (c) {
    return {'&':'&amp;','<':'&lt;','>':'&gt;','\'':'&#39;','"':'&quot;'}[c];
  });
}

/**
 * テーブル描画・件数更新
 * @param {Array} issues - IssueData配列
 */
export function displayIssues(issues) {
  const tbody = document.querySelector('#issue-table tbody');
  const indicator = document.getElementById('issue-count-indicator');
  if (tbody) tbody.innerHTML = renderIssueTableRows(issues);
  if (indicator) indicator.textContent = `${issues.length} issues found.`;
  // Bootstrapのdata-bs-toggle属性でアコーディオン制御するため、独自イベントリスナーは不要
}

export { renderIssueTableRows, escapeHtml };
