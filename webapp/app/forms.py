from django import forms
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError

MAX_UPLOAD_SIZE_MB = 10
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


class FileUploadForm(forms.Form):
    issue_file = forms.FileField(
        label="Select Issue File",
        help_text=f"Max. {MAX_UPLOAD_SIZE_MB}MB. Allowed: .md, .yml, .yaml, .json. "
                  f"Upload a Markdown, YAML, or JSON file containing issue definitions.",
        allow_empty_file=False,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['md', 'yml', 'yaml', 'json'],
                message="Unsupported file extension. Allowed extensions are: .md, .yml, .yaml, .json"
            )
        ],
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'id': 'issue-file-input',
            'required': True  # Retained from issue#157_01, good for UX
        })
    )

    def clean_issue_file(self):
        file = self.cleaned_data.get('issue_file')
        if file:
            if file.size > MAX_UPLOAD_SIZE_BYTES:
                raise ValidationError(
                    f"File size cannot exceed {MAX_UPLOAD_SIZE_MB}MB. Current size is {file.size // (MAX_UPLOAD_SIZE_BYTES // MAX_UPLOAD_SIZE_MB):.2f}MB."
                )
        return file