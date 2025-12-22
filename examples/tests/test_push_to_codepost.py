from codePost_upload_utils import *

BASE_URL = 'http://localhost:8000'
USERNAME = 'admin@codepost.io'
PASSWORD = 'rootabega'

ASSIGNMENT = {'id': 1, 'name': 'Hello', 'points': 20, 'isReleased': True,
              'course': 1, 'rubricCategories': [1, 2, 3, 4], 'mean': 20.0, 'median': 20.0}

OLD_FILE = {'name': 'hello.java', 'code': '<div> simple code </div>\n<div className=style> another simple code </div>',
            'extension': 'java'}
NEW_FILE = {'name': 'new.java', 'code': 'public new static void main{\n  system.out.println()\n}',
            'extension': 'java'}
OLD_FILE_WITH_CHANGE = {'name': 'hello.java', 'code': 'updated',
                        'extension': 'java'}


class Tests:

    def get_api_token(self):
        return requests.post('%s/users/requestAPIToken/' % BASE_URL,
                             auth=(USERNAME, PASSWORD)).json()['api_token']

    def test_get_assignment_info(self):
        api_token = self.get_api_token()
        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019', 'Hello')
        print(assignment)
        assert assignment['name'] == 'Hello'
        assert 'mean' in assignment
        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019', 'Hellooo')
        assert assignment == None
        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126000', 'S2019', 'Hello')
        assert assignment == None
        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019000', 'Hello')
        assert assignment == None

    def test_upload_submission_cautious(self):
        api_token = self.get_api_token()

        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019', 'Hello')

        # Collision with existing submission
        students = ['student0@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_CAUTIOUS)
        assert response == UF_ABORTED

        # Multiple collisions (partners)
        students = ['partner2@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_CAUTIOUS)
        assert response == UF_ABORTED

        # No collisions
        students = ['student15@princeton.edu']
        files = [NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_CAUTIOUS)
        assert response == UF_UPLOADED

    def test_upload_submission_extend(self):
        api_token = self.get_api_token()

        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019', 'Hello')

        # Multiple collisions
        students = ['partner2@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_EXTEND)
        assert response == UF_ABORTED

        # Collision with no new files
        students = ['student0@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_EXTEND)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()
        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 1

        # Collision with new file
        students = ['student0@princeton.edu']
        files = [OLD_FILE, NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_EXTEND)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()
        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] != None

        # Collision with new file (partners)
        students = ['partner1@princeton.edu', 'partner2@princeton.edu']
        files = [OLD_FILE, NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_EXTEND)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()
        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] != None

        # Collision with new file, remove old file
        # (should just append the file)
        students = ['student4@princeton.edu']
        files = [NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_EXTEND)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] != None

        # No collisions
        students = ['student16@princeton.edu']
        files = [OLD_FILE, NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_EXTEND)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()
        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] == None

    def test_upload_submission_diffscan(self):
        api_token = self.get_api_token()

        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019', 'Hello')

        # Multiple collisions
        students = ['partner2@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_DIFFSCAN)
        assert response == UF_ABORTED

        # Collision with no new files
        students = ['student6@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_DIFFSCAN)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()
        assert response == UF_UPLOADED
        assert submissions[0]['grader'] != None  # don't unclaim
        assert len(submissions[0]['files']) == 1

        # Collision with new file
        students = ['student6@princeton.edu']
        files = [OLD_FILE, NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_DIFFSCAN)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] != None  # don't unclaim
        assert len(file['comments']) == 1  # don't delete comments

        # Collision with new file, edit old file
        students = ['student7@princeton.edu']
        files = [OLD_FILE_WITH_CHANGE, NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_DIFFSCAN)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()
        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] != None
        assert 'updated' in file['code']
        assert len(file['comments']) == 0

        # Collision with new file
        # Should append to existing file list
        students = ['student8@princeton.edu']
        files = [NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_DIFFSCAN)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] != None

    def test_upload_submission_overwrite(self):
        api_token = self.get_api_token()

        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019', 'Hello')

        # Multiple collisions
        students = ['partner3@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_OVERWRITE)

        submissions1 = requests.get('%s/assignments/%d/submissions?student=%s' %
                                    (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()
        submissions2 = requests.get('%s/assignments/%d/submissions?student=%s' %
                                    (BASE_URL, assignment['id'], 'partner4@princeton.edu'), auth=(USERNAME, PASSWORD)).json()

        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions1[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert submissions1[0]['grader'] == None
        assert len(submissions1[0]['files']) == 1
        assert len(file['comments']) == 0

        # Single collision, reset old file
        students = ['student10@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_OVERWRITE)

        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert submissions[0]['grader'] == None
        assert len(submissions[0]['files']) == 1
        assert len(file['comments']) == 0

        # Single collision, new file
        students = ['student10@princeton.edu']
        files = [NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_OVERWRITE)

        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert submissions[0]['grader'] == None
        assert len(submissions[0]['files']) == 1
        assert 'new' in file['code']

        # No collisions
        students = ['student17@princeton.edu']
        files = [OLD_FILE, NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_OVERWRITE)
        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 2
        assert submissions[0]['grader'] == None

    def test_upload_submission_pregrade(self):
        api_token = self.get_api_token()

        assignment = get_assignment_info(
            BASE_URL, api_token, 'COS126', 'S2019', 'Hello')

        # Multiple collisions, grader assigned
        students = ['partner1@princeton.edu']
        files = [OLD_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_PREGRADE)

        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_ABORTED

        # Multiple collisions, no grader assigned
        students = ['partner5@princeton.edu']
        files = [NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_PREGRADE)

        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 1
        assert submissions[0]['grader'] == None
        assert 'new' in file['code']

        # Single collision, grader assigned
        students = ['student11@princeton.edu']
        files = [NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_PREGRADE)

        assert response == UF_ABORTED

        # Single collision, no grader assigned
        students = ['student12@princeton.edu']
        files = [NEW_FILE]

        response = upload_submission(BASE_URL, api_token,
                                     assignment, students, files, UF_PREGRADE)

        submissions = requests.get('%s/assignments/%d/submissions?student=%s' %
                                   (BASE_URL, assignment['id'], students[0]), auth=(USERNAME, PASSWORD)).json()

        file = requests.get('%s/files/%d/' %
                            (BASE_URL, submissions[0]['files'][0]), auth=(USERNAME, PASSWORD)).json()

        assert response == UF_UPLOADED
        assert len(submissions[0]['files']) == 1
        assert submissions[0]['grader'] == None
        assert 'new' in file['code']
