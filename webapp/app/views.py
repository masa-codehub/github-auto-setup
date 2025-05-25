from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import FileUploadForm
import logging

logger = logging.getLogger(__name__)


def top_page(request):
    uploaded_file_content = None
    uploaded_file_name = None

    if request.method == 'POST':
        form = FileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['issue_file']
            try:
                uploaded_file_content_bytes = uploaded_file.read()
                try:
                    uploaded_file_content = uploaded_file_content_bytes.decode(
                        'utf-8')
                    logger.info(
                        f"File '{uploaded_file.name}' (type: {uploaded_file.content_type}, size: {uploaded_file.size} bytes) uploaded and read successfully."
                    )
                    messages.success(
                        request, f"File '{uploaded_file.name}' uploaded successfully. Content ready for parsing.")
                    # Store file content and name in session to pass to the next step (parsing)
                    # Note: Storing large file content in session is not recommended for production.
                    # This is a temporary measure for demonstration or small files.
                    # Consider alternative ways to pass data for larger files (e.g., temp storage, cache).
                    request.session['uploaded_file_content'] = uploaded_file_content
                    request.session['uploaded_file_name'] = uploaded_file.name
                    return redirect('app:top_page')
                except UnicodeDecodeError:
                    logger.error(
                        f"Failed to decode file '{uploaded_file.name}' as UTF-8.")
                    messages.error(
                        request, f"Failed to decode file '{uploaded_file.name}'. Please ensure it is UTF-8 encoded.")
            except Exception as e:
                logger.exception(
                    f"Error reading uploaded file '{uploaded_file.name}': {e}")
                messages.error(
                    request, f"An error occurred while reading the file: {e}")
        else:
            logger.warning(
                f"File upload form validation failed: {form.errors.as_json()}")
            messages.error(
                request, "File upload failed. Please check the errors below.")
    else:
        form = FileUploadForm()
        # Retrieve and clear file content from session if it exists (e.g., after a redirect)
        # This is for demonstration; actual display logic might be different.
        if 'uploaded_file_name' in request.session:
            uploaded_file_name = request.session.pop('uploaded_file_name')
            uploaded_file_content = request.session.pop('uploaded_file_content', None) # Content might be large
            # For demonstration, we might add a message or pass this to context
            # if we intend to display something about the previously uploaded file.
            # messages.info(request, f"Ready to process: {uploaded_file_name}")


    context = {
        'upload_form': form,
        # Optionally pass uploaded file info to template for display, if needed
        # 'uploaded_file_name': uploaded_file_name,
        # 'uploaded_file_content_preview': uploaded_file_content[:200] if uploaded_file_content else None, # Preview
    }
    return render(request, "top_page.html", context)