from core.models import Course, Assignment, Submission, Comment, CommentTag


class SubmissionVersionHandler:

    def __init__(self, submission):
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
