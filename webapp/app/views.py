from django.shortcuts import render
from .forms import FileUploadForm


def top_page(request):
    form = FileUploadForm()
    context = {
        'upload_form': form,
    }
    return render(request, "top_page.html", context)
