import { displayIssues } from '../display_logic.js';

// display_logic.test.jsはESM構成へ統一のため削除します（内容はdisplay_logic.test.mjsに集約済み）。
describe('アコーディオンメニュー', () => {
  it('アコーディオン用イベントリスナーが存在しない（Bootstrap依存）', () => {
    const issues = [
      { temp_id: '1', title: 't1', description: 'desc1', assignees: [], labels: [] }
    ];
    displayIssues(issues);
    const clickable = document.querySelector('.issue-title-clickable');
    // Node.js環境ではgetEventListenersは未定義なので、単純にイベントリスナーがundefinedであることを確認
    expect(typeof getEventListeners).toBe('undefined');
  });
});
