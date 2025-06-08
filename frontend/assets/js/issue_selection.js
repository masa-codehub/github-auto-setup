// Issue選択（全選択/解除・選択ID保持）用JS

// display_logic.jsをimport
import { displayIssues } from './display_logic.js';

// === APIエンドポイント定数 ===
const API_ENDPOINT = '/api/v1/parse-file';

// DOM依存部分を即時実行しないように分離
if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
        const headerCheckbox = document.getElementById('select-all-header-checkbox');
        const selectAllButton = document.getElementById('select-all-button');
        const deselectAllButton = document.getElementById('deselect-all-button');
        // itemCheckboxes は動的に生成されるため、イベントリスナー設定時に都度取得する
        const selectedIssueIdsInput = document.getElementById('selected-issue-ids-input');

        function updateSelectedIssueIds() {
            if (!selectedIssueIdsInput) return;
            const itemCheckboxes = document.querySelectorAll('.issue-checkbox'); // 再取得
            const selectedIds = [];
            itemCheckboxes.forEach(checkbox => {
                if (checkbox.checked) {
                    selectedIds.push(checkbox.value);
                }
            });
            selectedIssueIdsInput.value = selectedIds.join(',');
        }

        // DOMContentLoaded時に存在する要素にリスナーを設定
        if (headerCheckbox) {
            headerCheckbox.addEventListener('change', function () {
                document.querySelectorAll('.issue-checkbox').forEach(checkbox => checkbox.checked = this.checked);
                updateSelectedIssueIds();
            });
        }
        if (selectAllButton) {
            selectAllButton.addEventListener('click', function () {
                document.querySelectorAll('.issue-checkbox').forEach(checkbox => checkbox.checked = true);
                if (headerCheckbox) headerCheckbox.checked = true;
                updateSelectedIssueIds();
            });
        }
        if (deselectAllButton) {
            deselectAllButton.addEventListener('click', function () {
                document.querySelectorAll('.issue-checkbox').forEach(checkbox => checkbox.checked = false);
                if (headerCheckbox) headerCheckbox.checked = false;
                updateSelectedIssueIds();
            });
        }
        
        // 動的に生成されるチェックボックスのために、親要素でイベントを委任
        const issueTableBody = document.getElementById('issue-table-body');
        if (issueTableBody) {
            issueTableBody.addEventListener('change', function(event) {
                if (event.target.classList.contains('issue-checkbox')) {
                    if (!event.target.checked && headerCheckbox) {
                        headerCheckbox.checked = false;
                    } else if (headerCheckbox) {
                        const allCheckboxes = document.querySelectorAll('.issue-checkbox');
                        const allChecked = Array.from(allCheckboxes).every(cb => cb.checked);
                        headerCheckbox.checked = allChecked;
                    }
                    updateSelectedIssueIds();
                }
            });
        }

        // 初期化
        updateSelectedIssueIds();

        // === ファイルアップロードフォームの送信イベントリスナー追加 ===
        const uploadForm = document.getElementById('upload-form');
        if(uploadForm) {
            uploadForm.addEventListener('submit', handleUploadFormSubmit(uploadForm, uploadIssueFile, showUploadError));
        }
    });
}

// === APIクライアント関数 ===
async function uploadIssueFile(formData) {
    try {
        // パス末尾のスラッシュ有無を吸収
        const endpoint = API_ENDPOINT;
        const response = await fetch(endpoint + '/', {
            method: 'POST',
            body: formData,
            // CSRFトークンヘッダーを追加する必要がある場合
            // headers: { 'X-CSRFToken': getCookie('csrftoken') },
        });
        if (!response.ok) {
            let errorMsg = `APIエラー: ${response.status}`;
            try {
                const errJson = await response.json();
                if (errJson && errJson.detail) {
                    errorMsg = errJson.detail;
                } else if (errJson && errJson.message) {
                    errorMsg = errJson.message;
                }
            } catch (_) {
                // JSONデコードに失敗した場合は、ステータスコードベースのエラーを使用
            }
            throw new Error(errorMsg);
        }
        return await response.json();
    } catch (error) {
        throw error; // エラーを再スローして呼び出し元で捕捉
    }
}

// === エラー時のUI通知 ===
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
        // フォールバック
        alert(message);
    }
}

// submitイベントリスナー本体
function handleUploadFormSubmit(uploadForm, uploadIssueFileFn, showUploadErrorFn) {
    return async function (e) {
        e.preventDefault();
        const fileInput = uploadForm.querySelector('input[type="file"][name="issue_file"]');
        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            showUploadErrorFn('ファイルを選択してください。');
            return;
        }
        const formData = new FormData();
        formData.append('issue_file', fileInput.files[0]);

        const uploadSpinner = document.getElementById('upload-spinner');
        const uploadButton = document.getElementById('upload-button');

        if (uploadSpinner) uploadSpinner.style.display = 'inline-block';
        if (uploadButton) uploadButton.disabled = true;

        try {
            const data = await uploadIssueFileFn(formData);
            if (data && Array.isArray(data.issues)) {
                // display_logic.jsの描画関数を呼び出す
                displayIssues(data.issues);
            } else {
                showUploadErrorFn('受信データにIssueが含まれていません。');
            }
        } catch (e) {
            showUploadErrorFn(e.message || 'ファイル解析API呼び出しに失敗しました。ネットワークまたはサーバーエラーです。');
        } finally {
            if (uploadSpinner) uploadSpinner.style.display = 'none';
            if (uploadButton) uploadButton.disabled = false;
        }
    };
}

// テスト用エクスポート（Node.js環境/Jest用）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { uploadIssueFile, showUploadError, handleUploadFormSubmit };
}