// issue_selection_ui.test.js
// submitイベントリスナーのエラー表示UIテスト

describe('Jest動作確認', () => {
  it('ダミーテスト', () => {
    expect(1 + 1).toBe(2);
  });
});

const { showUploadError } = require('../assets/js/issue_selection');

describe('showUploadError', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="result-notification-area"></div>';
  });

  it('エラーメッセージがBootstrap Alertで表示される', () => {
    showUploadError('テストエラー');
    const area = document.getElementById('result-notification-area');
    expect(area.innerHTML).toMatch(/alert-danger/);
    expect(area.textContent).toMatch('テストエラー');
  });
});

// submitイベントリスナーのtry...catch→showUploadError呼び出しの結合テスト
const { uploadIssueFile, handleUploadFormSubmit } = require('../assets/js/issue_selection');

describe('uploadForm submit error handling', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <form id="upload-form">
        <input type="file" name="issue_file">
        <button id="upload-button" type="submit">Upload</button>
        <span id="upload-spinner" style="display:none;"></span>
      </form>
      <div id="result-notification-area"></div>
    `;
    global.fetch = jest.fn();
  });

  it('APIエラー時にshowUploadErrorが呼ばれ、通知エリアに表示される', async () => {
    const uploadForm = document.getElementById('upload-form');
    const fileInput = uploadForm.querySelector('input[type="file"]');
    const file = new Blob(['dummy'], { type: 'text/markdown' });
    Object.defineProperty(fileInput, 'files', { value: [file] });
    // モック関数
    const mockUploadIssueFile = jest.fn().mockRejectedValue(new Error('APIエラー'));
    const mockShowUploadError = jest.fn((msg) => {
      const area = document.getElementById('result-notification-area');
      const div = document.createElement('div');
      div.textContent = msg;
      area.appendChild(div);
    });
    // submitイベントリスナー本体を直接呼び出し
    const handler = handleUploadFormSubmit(uploadForm, mockUploadIssueFile, mockShowUploadError);
    const event = new Event('submit');
    await handler(event);
    const area = document.getElementById('result-notification-area');
    expect(area.textContent).toMatch('APIエラー');
    expect(mockShowUploadError).toBeCalledWith('APIエラー');
  });
});
