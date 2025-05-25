from django import forms


class FileUploadForm(forms.Form):
    issue_file = forms.FileField(
        label="Select Issue File",
        help_text="Upload a Markdown, YAML, or JSON file containing issue definitions.",
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'id': 'issue-file-input',
            'required': True
        })
    )
