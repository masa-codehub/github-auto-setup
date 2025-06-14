// Issue選択（全選択/解除・選択ID保持）用JS

// display_logic.jsをimport
// import { displayIssues } from './display_logic.js'; // 一時的にコメントアウト

// === APIエンドポイント定数 ===
const API_SERVER = window.API_SERVER_URL || 'http://localhost:8002';
const API_ENDPOINT = API_SERVER + '/api/v1/parse-file/';

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
        const uploadButton = document.getElementById('upload-button');
        if(uploadButton && uploadForm) {
            console.log("バインドOK"); // デバッグ用: clickバインド確認
            uploadButton.addEventListener('click', handleUploadFormSubmit(uploadForm, uploadIssueFile, showUploadError));
        }
        // === GitHub登録・ローカル保存ボタンのイベントリスナー追加 ===
        const githubSubmitButton = document.getElementById('github-submit-button');
        const localSaveButton = document.getElementById('local-save-button');
        if (githubSubmitButton) {
            githubSubmitButton.addEventListener('click', async function () {
                await handleGithubSubmit();
            });
        }
        if (localSaveButton) {
            localSaveButton.addEventListener('click', async function () {
                await handleLocalSave();
            });
        }
    });
}

// === APIクライアント関数 ===
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

async function uploadIssueFile(formData) {
    try {
        const endpoint = API_ENDPOINT;
        // CSRFトークンをヘッダーに付与
        const csrfToken = getCookie('csrftoken');
        const backendApiKeyInput = document.getElementById('backend-api-key-input');
        const headers = csrfToken ? { 'X-CSRFToken': csrfToken } : {};
        // Backend API KeyをX-API-KEYヘッダーに追加
        if (backendApiKeyInput && backendApiKeyInput.value) {
            headers['X-API-KEY'] = backendApiKeyInput.value;
        }
        // テスト用: .envのBACKEND_API_KEYとX-API-KEYをコンソール出力
        console.log('BACKEND_API_KEY (.env):', 'my_backend_api_key');
        console.log('X-API-KEY (request header):', headers['X-API-KEY']);
        // --- デバッグ用: API呼び出し前のチェック ---
        // --- デバッグ用ここまで ---
        // --- デバッグ: formData.appendやfor...ofで例外が出ても必ずcatchで表示 ---
        // --- デバッグ用ここまで ---
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData,
            headers: headers
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
            } catch (_) {}
            throw new Error(errorMsg);
        }
        // ここでAPIアクセス成功時のメッセージを出力
        console.log('APIアクセス成功: /api/v1/parse-file/ に正常にアクセスしました。');
        return await response.json();
    } catch (error) {
        throw error;
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
        e.preventDefault(); // 最優先でリロード抑止
        console.log("submit!"); // デバッグ用: submitイベント発火確認
        const fileInput = uploadForm.querySelector('input[type="file"]');
        const backendApiKeyInput = document.getElementById('backend-api-key-input');
        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            showUploadErrorFn('ファイルを選択してください。');
            return;
        }
        const formData = new FormData();
        formData.append('issue_file', fileInput.files[0]);
        // Backend API KeyもFormDataやfetchヘッダーに必要ならここで追加
        if (backendApiKeyInput && backendApiKeyInput.value) {
            // 例: ヘッダーで送る場合はfetch側で追加、FormDataで送る場合はここでappend
            // formData.append('backend_api_key', backendApiKeyInput.value); // ←API仕様に応じて
        }
        const uploadSpinner = document.getElementById('upload-spinner');
        const uploadButton = document.getElementById('upload-button');
        if (uploadSpinner) uploadSpinner.style.display = 'inline-block';
        if (uploadButton) uploadButton.disabled = true;
        try {
            const data = await uploadIssueFileFn(formData);
            if (data && Array.isArray(data.issues)) {
                // display_logic.jsの描画関数を呼び出す
                // displayIssues(data.issues); // ←一時的にコメントアウト
            } else {
                showUploadErrorFn('受信データにIssueが含まれていません。');
            }
        } catch (e) {
            showUploadErrorFn(e.message || 'ファイル解析API呼び出しに失敗しました。ネットワークまたはサーバーエラーです。');
        } finally {
            if (uploadSpinner) uploadSpinner.style.display = 'none';
            if (uploadButton) uploadButton.disabled = false;
            // フォームリセットやinput値クリアは行わない（Backend API Key欄を残すため）
        }
        // 最後にreturn falseで念のためリロード抑止
        return false;
    };
}

// GitHub登録API呼び出し
async function handleGithubSubmit() {
    const repoInput = document.getElementById('repo-name-input');
    const projectInput = document.getElementById('project-name-input');
    const dryRunCheckbox = document.getElementById('dry-run-checkbox');
    const selectedIdsInput = document.getElementById('selected-issue-ids-input');
    const area = document.getElementById('result-notification-area');
    if (!repoInput || !selectedIdsInput) return;
    const repoName = repoInput.value.trim();
    const projectName = projectInput ? projectInput.value.trim() : '';
    const dryRun = dryRunCheckbox ? dryRunCheckbox.checked : true;
    const selectedIds = selectedIdsInput.value.split(',').filter(Boolean);
    if (selectedIds.length === 0) {
        showUploadError('1件以上のIssueを選択してください。');
        return;
    }
    try {
        const csrfToken = getCookie('csrftoken');
        const res = await fetch(API_SERVER + '/api/v1/github-create-issues/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
            },
            body: JSON.stringify({
                repo_name: repoName,
                project_name: projectName,
                dry_run: dryRun,
                issue_ids: selectedIds
            })
        });
        const data = await res.json();
        if (res.ok) {
            showUploadError('GitHub登録成功: ' + (data.detail || '完了しました。'));
        } else {
            showUploadError('GitHub登録失敗: ' + (data.detail || 'エラー'));
        }
    } catch (e) {
        showUploadError('GitHub登録API呼び出し失敗: ' + (e.message || 'エラー'));
    }
}

// ローカル保存API呼び出し
async function handleLocalSave() {
    const localPathInput = document.getElementById('local-path-input');
    const selectedIdsInput = document.getElementById('selected-issue-ids-input');
    if (!selectedIdsInput) return;
    const localPath = localPathInput ? localPathInput.value.trim() : '';
    const selectedIds = selectedIdsInput.value.split(',').filter(Boolean);
    if (selectedIds.length === 0) {
        showUploadError('1件以上のIssueを選択してください。');
        return;
    }
    try {
        const csrfToken = getCookie('csrftoken');
        const res = await fetch(API_SERVER + '/api/v1/local-save-issues/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
            },
            body: JSON.stringify({
                local_path: localPath,
                issue_ids: selectedIds
            })
        });
        const data = await res.json();
        if (res.ok) {
            showUploadError('ローカル保存成功: ' + (data.detail || '完了しました。'));
        } else {
            showUploadError('ローカル保存失敗: ' + (data.detail || 'エラー'));
        }
    } catch (e) {
        showUploadError('ローカル保存API呼び出し失敗: ' + (e.message || 'エラー'));
    }
}

// === AI設定フォーム連携 ===
const AI_SETTINGS_API = API_SERVER + '/api/v1/ai-settings/';

async function loadAiSettings() {
    try {
        // Backend API Keyを取得
        const backendApiKeyInput = document.getElementById('backend-api-key-input');
        const headers = {};
        if (backendApiKeyInput && backendApiKeyInput.value) {
            headers['X-API-KEY'] = backendApiKeyInput.value;
        }
        const res = await fetch(AI_SETTINGS_API, { credentials: 'same-origin', headers });
        if (!res.ok) return;
        const data = await res.json();
        // プロバイダー
        if (data.ai_provider === 'gemini') {
            document.getElementById('ai_provider_gemini').checked = true;
            document.getElementById('gemini-model-selection-area').style.display = '';
            document.getElementById('openai-model-selection-area').style.display = 'none';
        } else {
            document.getElementById('ai_provider_openai').checked = true;
            document.getElementById('openai-model-selection-area').style.display = '';
            document.getElementById('gemini-model-selection-area').style.display = 'none';
        }
        // モデル
        if (data.openai_model) document.getElementById('openai-model-select').value = data.openai_model;
        if (data.gemini_model) document.getElementById('gemini-model-select').value = data.gemini_model;
        // APIキー
        if (data.ai_provider === 'openai' && data.openai_api_key)
            document.getElementById('api-key-input').value = data.openai_api_key;
        if (data.ai_provider === 'gemini' && data.gemini_api_key)
            document.getElementById('api-key-input').value = data.gemini_api_key;
    } catch (e) { /* 無視 */ }
}

async function saveAiSettings(e) {
    e.preventDefault();
    const aiProvider = document.querySelector('input[name="ai_provider"]:checked').value;
    const openaiModel = document.getElementById('openai-model-select').value;
    const geminiModel = document.getElementById('gemini-model-select').value;
    const apiKey = document.getElementById('api-key-input').value;
    const payload = {
        ai_provider: aiProvider,
        openai_model: aiProvider === 'openai' ? openaiModel : '',
        gemini_model: aiProvider === 'gemini' ? geminiModel : '',
        openai_api_key: aiProvider === 'openai' ? apiKey : '',
        gemini_api_key: aiProvider === 'gemini' ? apiKey : ''
    };
    const csrfToken = getCookie('csrftoken');
    try {
        const res = await fetch(AI_SETTINGS_API, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {})
            },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            showUploadError('AI設定を保存しました。');
        } else {
            showUploadError('AI設定保存に失敗しました。');
        }
    } catch (e) {
        showUploadError('AI設定保存API呼び出し失敗: ' + (e.message || 'エラー'));
    }
}

function setupAiSettingsForm() {
    // プロバイダー切替でモデル選択欄の表示切替
    document.getElementById('ai_provider_openai').addEventListener('change', function() {
        document.getElementById('openai-model-selection-area').style.display = '';
        document.getElementById('gemini-model-selection-area').style.display = 'none';
    });
    document.getElementById('ai_provider_gemini').addEventListener('change', function() {
        document.getElementById('openai-model-selection-area').style.display = 'none';
        document.getElementById('gemini-model-selection-area').style.display = '';
    });
    // フォームsubmit
    const aiForm = document.getElementById('ai-settings-form');
    if (aiForm) {
        aiForm.addEventListener('submit', saveAiSettings);
    }
    // 『AI設定を取得』ボタンのイベントリスナー
    const aiLoadButton = document.getElementById('ai-settings-load-button');
    if (aiLoadButton) {
        aiLoadButton.addEventListener('click', function(e) {
            e.preventDefault();
            loadAiSettings();
        });
    }
}

document.addEventListener('DOMContentLoaded', function () {
    // loadAiSettings(); // ←自動実行を削除
    setupAiSettingsForm();
});

// テスト用エクスポート（Node.js環境/Jest用）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { uploadIssueFile, showUploadError, handleUploadFormSubmit };
}