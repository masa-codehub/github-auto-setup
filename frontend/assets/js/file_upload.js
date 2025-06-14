// file_upload.js
// ファイルアップロードUIのクライアントサイドバリデーション
// 対象: input#issue-file-input, button#upload-button, div#fileHelp

(function() {
  const fileInput = document.getElementById('issue-file-input');
  const uploadForm = document.getElementById('upload-form');
  const fileHelp = document.getElementById('fileHelp');
  const allowedExts = ['.md', '.yml', '.yaml', '.json'];
  const maxSize = 10 * 1024 * 1024; // 10MB

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
    // --- Backend API Key inputの値を絶対にクリアしないように明示的に防止 ---
    // localStorageに1分間だけ保存し、ページリロード時に自動復元
    const backendApiKeyInput = document.getElementById('backend-api-key-input');
    const STORAGE_KEY = 'backendApiKey';
    const STORAGE_TIME_KEY = 'backendApiKey_savedAt';
    const EXPIRE_MS = 60 * 1000; // 1分
    // localStorageからの復元はDOMContentLoaded後に実行
    window.addEventListener('DOMContentLoaded', function() {
      const backendApiKeyInput = document.getElementById('backend-api-key-input');
      if (backendApiKeyInput) {
        try {
          const saved = localStorage.getItem(STORAGE_KEY);
          const savedAt = parseInt(localStorage.getItem(STORAGE_TIME_KEY), 10);
          if (saved && savedAt && Date.now() - savedAt < EXPIRE_MS) {
            backendApiKeyInput.value = saved;
          } else {
            localStorage.removeItem(STORAGE_KEY);
            localStorage.removeItem(STORAGE_TIME_KEY);
          }
        } catch (e) {}
        // 入力時に保存
        backendApiKeyInput.addEventListener('input', function() {
          try {
            localStorage.setItem(STORAGE_KEY, backendApiKeyInput.value);
            localStorage.setItem(STORAGE_TIME_KEY, Date.now().toString());
          } catch (e) {}
        });
      }
    });
    // submit時やアップロード成功時にuploadForm.reset()やinput.value=''等は絶対に呼ばない
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
