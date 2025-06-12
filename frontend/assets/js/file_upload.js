// file_upload.js
// ファイルアップロードUIのクライアントサイドバリデーション
// 対象: input#issue-file-input, button#upload-button, div#fileHelp

(function() {
  const fileInput = document.getElementById('issue-file-input');
  const uploadForm = document.getElementById('upload-form');
  const fileHelp = document.getElementById('fileHelp');
  const allowedExts = ['.md', '.yml', '.yaml', '.json'];
  const maxSize = 10 * 1024 * 1024; // 10MB
  const API_SERVER = window.API_SERVER_URL || 'http://localhost:8000';

  function getExt(filename) {
    // 末尾のドット区切り拡張子を返す（例: 'test.md'→'md'）
    const parts = filename.split('.');
    return parts.length > 1 ? parts.pop().toLowerCase() : '';
  }

  function showError(msg) {
    fileHelp.classList.add('text-danger');
    fileHelp.textContent = msg;
  }
  function clearError(defaultMsg) {
    fileHelp.classList.remove('text-danger');
    fileHelp.textContent = defaultMsg;
  }

  if (fileInput && uploadForm && fileHelp) {
    const defaultHelp = fileHelp.textContent;
    fileInput.addEventListener('change', function() {
      clearError(defaultHelp);
      const file = fileInput.files[0];
      if (!file) return;
      const ext = '.' + getExt(file.name);
      if (!allowedExts.includes(ext)) {
        showError('許可されていないファイル形式です（.md, .yml, .yaml, .json のみ可）');
        fileInput.value = '';
        return;
      }
      if (file.size > maxSize) {
        showError('ファイルサイズが10MBを超えています');
        fileInput.value = '';
        return;
      }
    });
    uploadForm.addEventListener('submit', async function(e) {
      clearError(defaultHelp);
      const file = fileInput.files[0];
      if (!file) {
        showError('ファイルを選択してください');
        e.preventDefault();
        return;
      }
      const ext = '.' + getExt(file.name);
      if (!allowedExts.includes(ext)) {
        showError('許可されていないファイル形式です（.md, .yml, .yaml, .json のみ可）');
        e.preventDefault();
        return;
      }
      if (file.size > maxSize) {
        showError('ファイルサイズが10MBを超えています');
        e.preventDefault();
        return;
      }
      // --- fetch+FormData+POSTでAPI呼び出し ---
      e.preventDefault(); // ページリロード防止
      const formData = new FormData();
      formData.append('issue_file', file); // ←キー名を統一
      try {
        const csrfToken = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
        const response = await fetch(API_SERVER + '/api/v1/parse-file', {
          method: 'POST',
          body: formData,
          headers: csrfToken ? { 'X-CSRFToken': csrfToken } : undefined
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          showError(err.detail || 'アップロードに失敗しました');
          return;
        }
        // 成功時の処理（例: 結果表示ロジックへデータ渡し）
        const result = await response.json();
        // window.dispatchEventやコールバックでdisplay_logic.js等に通知してもよい
        window.dispatchEvent(new CustomEvent('fileUploadSuccess', { detail: result }));
      } catch (err) {
        showError('ネットワークエラーが発生しました');
      }
    });
  }

  // バリデーション関数を外部からもテスト可能にエクスポート
  function validateFile(file) {
    const allowedExts = ['md', 'yml', 'yaml', 'json'];
    const maxSize = 10 * 1024 * 1024;
    if (!file) return { valid: false, error: 'ファイルを選択してください' };
    const ext = getExt(file.name);
    if (!allowedExts.includes(ext)) {
      return { valid: false, error: '許可されていないファイル形式です（.md, .yml, .yaml, .json のみ可）' };
    }
    if (file.size > maxSize) {
      return { valid: false, error: 'ファイルサイズが10MBを超えています' };
    }
    return { valid: true };
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports.validateFile = validateFile;
  }
})();
