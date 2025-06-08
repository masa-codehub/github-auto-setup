// apiClient.test.js
// uploadIssueFileの単体テスト（Jest）

const { uploadIssueFile } = require('../assets/js/issue_selection');

global.fetch = jest.fn();

describe('uploadIssueFile', () => {
  beforeEach(() => {
    fetch.mockClear();
  });

  it('成功時: レスポンスJSONを返す', async () => {
    const mockResponse = { session_id: 'abc123', issues: [] };
    fetch.mockResolvedValue({
      ok: true,
      json: async () => mockResponse
    });
    const formData = new FormData();
    formData.append('issue_file', new Blob(['dummy'], { type: 'text/markdown' }), 'test.md');
    const result = await uploadIssueFile(formData);
    expect(result).toEqual(mockResponse);
    expect(fetch).toHaveBeenCalledWith('/api/v1/parse-file/', expect.objectContaining({ method: 'POST' }));
  });

  it('失敗時: 例外を投げる', async () => {
    fetch.mockRejectedValue(new Error('network error'));
    const formData = new FormData();
    formData.append('issue_file', new Blob(['dummy'], { type: 'text/markdown' }), 'test.md');
    await expect(uploadIssueFile(formData)).rejects.toThrow('network error');
  });

  it('400エラー時: detailメッセージをthrow', async () => {
    fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'ファイル検証エラー: 不正なファイル形式' })
    });
    const formData = new FormData();
    formData.append('issue_file', new Blob(['dummy'], { type: 'text/markdown' }), 'test.md');
    await expect(uploadIssueFile(formData)).rejects.toThrow('ファイル検証エラー: 不正なファイル形式');
  });

  it('500エラー時: messageプロパティをthrow', async () => {
    fetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ message: 'Internal Server Error' })
    });
    const formData = new FormData();
    formData.append('issue_file', new Blob(['dummy'], { type: 'text/markdown' }), 'test.md');
    await expect(uploadIssueFile(formData)).rejects.toThrow('Internal Server Error');
  });

  it('AI解析エラー時: detailメッセージをthrow', async () => {
    fetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'AI解析エラー: パース失敗' })
    });
    const formData = new FormData();
    formData.append('issue_file', new Blob(['dummy'], { type: 'text/markdown' }), 'test.md');
    await expect(uploadIssueFile(formData)).rejects.toThrow('AI解析エラー: パース失敗');
  });
});
