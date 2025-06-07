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
    uploadForm.addEventListener('submit', function(e) {
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
