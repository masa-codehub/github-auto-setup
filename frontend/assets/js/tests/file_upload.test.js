// file_upload.test.js
// Jest + jsdom前提の単体テスト例

const { validateFile } = require('../file_upload.js');

describe('ファイルアップロードバリデーション関数', () => {
  function mockFile(name, size, type = 'text/markdown') {
    return new File(['a'.repeat(size)], name, { type });
  }
  test('許可拡張子（.md）かつ10MB以下はOK', () => {
    const file = mockFile('test.md', 100, 'text/markdown');
    expect(validateFile(file)).toEqual({ valid: true });
  });
  test('サポート外拡張子（.txt）はエラー', () => {
    const file = mockFile('test.txt', 100, 'text/plain');
    expect(validateFile(file)).toEqual({ valid: false, error: expect.stringMatching(/許可されていない/) });
  });
  test('10MB超ファイルはエラー', () => {
    const file = mockFile('test.md', 11 * 1024 * 1024, 'text/markdown');
    expect(validateFile(file)).toEqual({ valid: false, error: expect.stringMatching(/10MB/) });
  });
  test('ファイル未選択はエラー', () => {
    expect(validateFile(undefined)).toEqual({ valid: false, error: expect.stringMatching(/ファイルを選択/) });
  });
});

describe('ファイルアップロードUIバリデーション', () => {
  let fileInput, uploadForm, fileHelp;
  beforeEach(() => {
    document.body.innerHTML = `
      <form id="upload-form">
        <input type="file" id="issue-file-input">
        <div id="fileHelp">ヘルプテキスト</div>
      </form>
    `;
    // file_upload.jsをrequireで実行（グローバル副作用）
    jest.resetModules();
    require('../file_upload.js');
    fileInput = document.getElementById('issue-file-input');
    uploadForm = document.getElementById('upload-form');
    fileHelp = document.getElementById('fileHelp');
  });
  afterEach(() => {
    document.body.innerHTML = '';
  });

  function mockFile(name, size, type = 'text/markdown') {
    return new File(['a'.repeat(size)], name, { type });
  }

  test('許可拡張子（.md）はエラーにならない', () => {
    const file = mockFile('test.md', 100, 'text/markdown');
    Object.defineProperty(fileInput, 'files', { value: [file] });
    fileInput.value = '';
    fileInput.dispatchEvent(new Event('change'));
    expect(fileHelp.classList.contains('text-danger')).toBe(false);
  });

  test('サポート外拡張子（.txt）はエラー', () => {
    const file = mockFile('test.txt', 100, 'text/plain');
    Object.defineProperty(fileInput, 'files', { value: [file] });
    fileInput.value = '';
    fileInput.dispatchEvent(new Event('change'));
    expect(fileHelp.textContent).toMatch(/許可されていない/);
    expect(fileHelp.classList.contains('text-danger')).toBe(true);
  });

  test('10MB超ファイルはエラー', () => {
    const file = mockFile('test.md', 11 * 1024 * 1024, 'text/markdown');
    Object.defineProperty(fileInput, 'files', { value: [file] });
    fileInput.value = '';
    fileInput.dispatchEvent(new Event('change'));
    expect(fileHelp.textContent).toMatch(/10MB/);
    expect(fileHelp.classList.contains('text-danger')).toBe(true);
  });

  test('ファイル未選択でsubmit時はエラー', () => {
    Object.defineProperty(fileInput, 'files', { value: [] });
    const event = new Event('submit');
    event.preventDefault = jest.fn();
    uploadForm.dispatchEvent(event);
    expect(fileHelp.textContent).toMatch(/ファイルを選択/);
    expect(event.preventDefault).toBeCalled();
  });
});
