// Issue選択（全選択/解除・選択ID保持）用JS

// DOM依存部分を即時実行しないように分離
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
        const headerCheckbox = document.getElementById('select-all-header-checkbox');
        const selectAllButton = document.getElementById('select-all-button');
        const deselectAllButton = document.getElementById('deselect-all-button');
        const itemCheckboxes = document.querySelectorAll('.issue-checkbox');
        const selectedIssueIdsInput = document.getElementById('selected-issue-ids-input');

        function updateSelectedIssueIds() {
            if (!selectedIssueIdsInput) return;
            const selectedIds = [];
            itemCheckboxes.forEach(checkbox => {
                if (checkbox.checked) {
                    selectedIds.push(checkbox.value);
                }
            });
            selectedIssueIdsInput.value = selectedIds.join(',');
        }

        if (headerCheckbox) {
            headerCheckbox.addEventListener('change', function () {
                itemCheckboxes.forEach(checkbox => checkbox.checked = this.checked);
                updateSelectedIssueIds();
            });
        }
        if (selectAllButton) {
            selectAllButton.addEventListener('click', function () {
                itemCheckboxes.forEach(checkbox => checkbox.checked = true);
                if (headerCheckbox) headerCheckbox.checked = true;
                updateSelectedIssueIds();
            });
        }
        if (deselectAllButton) {
            deselectAllButton.addEventListener('click', function () {
                itemCheckboxes.forEach(checkbox => checkbox.checked = false);
                if (headerCheckbox) headerCheckbox.checked = false;
                updateSelectedIssueIds();
            });
        }
        itemCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', function () {
                if (!this.checked && headerCheckbox) {
                    headerCheckbox.checked = false;
                } else if (headerCheckbox) {
                    const allChecked = Array.from(itemCheckboxes).every(cb => cb.checked);
                    headerCheckbox.checked = allChecked;
                }
                updateSelectedIssueIds();
            });
        });
        // 初期化
        updateSelectedIssueIds();

        // === [STEP1] ファイルアップロードフォームの送信イベントリスナー追加 ===
        const uploadForm = document.getElementById('upload-form');

        uploadForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            const fileInput = uploadForm.querySelector('input[type="file"][name="issue_file"]');
            if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
                alert('ファイルを選択してください');
                return;
            }
            const formData = new FormData();
            formData.append('issue_file', fileInput.files[0]);
            // スピナー表示・ボタン無効化
            const uploadSpinner = document.getElementById('upload-spinner');
            const uploadButton = document.getElementById('upload-button');
            if (uploadSpinner) uploadSpinner.style.display = 'inline-block';
            if (uploadButton) uploadButton.disabled = true;
            try {
                const data = await uploadIssueFile(formData);
                // display_logic.jsの描画関数を呼び出し
                if (data && Array.isArray(data.issues)) {
                    displayIssues(data.issues);
                }
            } catch (e) {
                showUploadError('ファイル解析API呼び出しに失敗しました。ネットワークまたはサーバーエラーです。');
            } finally {
                // スピナー非表示・ボタン有効化
                if (uploadSpinner) uploadSpinner.style.display = 'none';
                if (uploadButton) uploadButton.disabled = false;
            }
        });
    });
}

// === [STEP2] FormData生成とAPIクライアント関数 ===
async function uploadIssueFile(formData) {
    try {
        const response = await fetch('/api/v1/parse-file', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        return data;
    } catch (error) {
        throw error;
    }
}

// === [STEP4] エラー時のUI通知 ===
function showUploadError(message) {
    const area = document.getElementById('result-notification-area');
    if (area) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show';
        alert.role = 'alert';
        alert.innerHTML = `
            <span>${message}</span>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        area.appendChild(alert);
    } else {
        alert(message);
    }
}

// テスト用エクスポート（Node.js環境/Jest用）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { uploadIssueFile, showUploadError };
}

// display_logic.jsをimport
import { displayIssues } from './display_logic.js';
