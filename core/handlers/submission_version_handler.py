# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
import base64
import io
import zipfile
from core.models import Submission

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

                # Data URI content ("data:<mime>;base64,...") is binary — decode before adding to zip.
                if data.startswith('data:'):
                    try:
                        _header, encoded = data.split(',', 1)
                        data = base64.b64decode(encoded)
                    except Exception:
                        pass
                
                zip_file.writestr(file.name, data)

        return base64.b64encode(zip_buffer.getvalue()).decode()
