import { JSDOM } from 'jsdom';
import fetchMock from 'jest-fetch-mock';

// issue_selection.jsの関数をimport（必要に応じて）
import '../js/issue_selection.js';

describe('AI設定フォームのUI連携', () => {
  let dom, document;
  beforeEach(() => {
    fetchMock.resetMocks();
    dom = new JSDOM(`<!DOCTYPE html><body>
      <form id="ai-settings-form">
        <input type="radio" name="ai_provider" id="ai_provider_openai" value="openai" checked>
        <input type="radio" name="ai_provider" id="ai_provider_gemini" value="gemini">
        <select id="openai-model-select"><option value="gpt-4o">gpt-4o</option></select>
        <select id="gemini-model-select"><option value="gemini-1.5-flash">gemini-1.5-flash</option></select>
        <input type="password" id="api-key-input">
        <div id="openai-model-selection-area"></div>
        <div id="gemini-model-selection-area"></div>
      </form>
    </body>`, { url: 'http://localhost' });
    document = dom.window.document;
    global.document = document;
    global.window = dom.window;
  });

  it('AI設定取得APIで値が反映される', async () => {
    fetchMock.mockResponseOnce(JSON.stringify({
      ai_provider: 'gemini',
      openai_model: '',
      gemini_model: 'gemini-1.5-flash',
      openai_api_key: '',
      gemini_api_key: 'test-gemini-key'
    }));
    // loadAiSettingsを直接呼ぶか、DOMContentLoadedをdispatch
    const { loadAiSettings } = await import('../js/issue_selection.js');
    await loadAiSettings();
    expect(document.getElementById('ai_provider_gemini').checked).toBe(true);
    expect(document.getElementById('gemini-model-select').value).toBe('gemini-1.5-flash');
    expect(document.getElementById('api-key-input').value).toBe('test-gemini-key');
  });

  it('AI設定保存APIが呼ばれる', async () => {
    fetchMock.mockResponseOnce(JSON.stringify({}));
    document.getElementById('ai_provider_openai').checked = true;
    document.getElementById('openai-model-select').value = 'gpt-4o';
    document.getElementById('api-key-input').value = 'test-openai-key';
    const { saveAiSettings } = await import('../js/issue_selection.js');
    const e = { preventDefault: jest.fn() };
    await saveAiSettings(e);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/ai-settings/',
      expect.objectContaining({ method: 'POST' })
    );
  });
});
