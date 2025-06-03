// Issue選択（全選択/解除・選択ID保持）用JS

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
});
