import base64
import io
import zipfile
from core.models import  Submission

class SubmissionVersionHandler:

    def __init__(self, submission: Submission):
        self.submission = submission
        self.assignment = submission.assignment
        self.course = submission.assignment.course

    def current_files(self):
        """
        Return current file versions for this submission
        """

        current_files = {}

        for file in self.submission.files.all():
            unique_path = "{}{}".format(file.path, file.name)
            if unique_path not in current_files:
                current_files[unique_path] = file
            else:
                if file.created > current_files[unique_path].created:
                    current_files[unique_path] = file

        return current_files.values()
    def encoded_zip(self):
        """
        Create zip from files in memory
        """

        files = self.current_files()

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for file in files:
                data = file.data

                # For binary files, data might be base64. Try to decode if it looks like base64 or is a binary extension.
                BINARY_EXTENSIONS = ['pdf', 'png', 'jpg', 'jpeg']
                if any(file.name.lower().endswith('.' + ext) for ext in BINARY_EXTENSIONS):
                    # Check for data URI prefix and strip it if present
                    if data.startswith('data:'):
                        try:
                            header, encoded = data.split(',', 1)
                            data = base64.b64decode(encoded)
                        except Exception:
                            pass
                    else:
                        # No prefix, try direct decode if it looks like base64
                        try:
                            data = base64.b64decode(data)
                        except Exception:
                            pass
                
                zip_file.writestr(file.name, data)

        return base64.b64encode(zip_buffer.getvalue()).decode()
