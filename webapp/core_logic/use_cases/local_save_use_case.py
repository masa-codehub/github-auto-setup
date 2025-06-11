from core_logic.domain.models import ParsedRequirementData


class LocalSaveUseCase:
    def execute(self, parsed_data: ParsedRequirementData, dry_run: bool = False):
        # 実際のローカル保存処理をここに実装
        # ここでは仮にファイル保存の例
        if dry_run:
            return {"success": True, "detail": "Dry run: no file written."}
        # 例: JSONとして保存
        import json
        import os
        save_path = os.path.join("/tmp", "github_issues_export.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(parsed_data.model_dump(), f,
                      ensure_ascii=False, indent=2)
        return {"success": True, "detail": f"Saved to {save_path}"}
