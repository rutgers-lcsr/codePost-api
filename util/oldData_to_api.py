
import json
import requests

# api_key = "Token 473f95fca268ca7451a3bef7451cb0f1b20abc2d"
api_key = "Token 648e8f8f111ffcc1511b0563ae5512a302ecf33a"
headers = {"Authorization": api_key}
# url = 'https://api.codepost-labs.io/'
url = 'http://localhost:8000/'

CODE_SUCCESS = 200
CODE_CREATED = 201
CODE_FORBIDDEN = 403

def getOldCourse(name):
  f_courses = open('./toMigrate/cleaned_data.txt', 'r')
  courses = json.loads(f_courses.read())

  try:
    oldCourse = [x for x in courses if x['name'] == name][0]
  except:
    print('No such course exists in old database.')

  # Get courses to which we have access
  me = requests.get(url + 'users/me/', headers=headers)
  if me.status_code != CODE_SUCCESS:
    print('FAILED: /users/me endpoint did not work as expected')
    return
  courseList = me.json()['courseadminCourses']

  try:
    newName = name.split('_')[0]
    period = name.split('_')[1]
    thisCourse = [x for x in courseList if (x['name'] == newName and x['period'] == period)][0]
  except:
    print('Either this course has not been created yet, or you do not have access to it.')
    return

  return (oldCourse, thisCourse['id'])

def createCourseFromName(name):
  f_courses = open('./toMigrate/cleaned_data.txt', 'r')
  courses = json.loads(f_courses.read())

  try:
    oldCourse = [x for x in courses if x['name'] == name][0]
  except:
    print('No such course exists in old database.')

  payload = {
    'name' : oldCourse['name'].split('_')[0],
    'period' : oldCourse['name'].split('_')[1],
  }

  r = requests.post(url + 'courses/', headers=headers, data=payload)
  if r.status_code != CODE_CREATED:
    print('FAILED: ' + r.text)
  else:
    print('Successfully created course.')

def createCourseRosters(courseName):
  (oldCourse, courseID) = getOldCourse(courseName)

  students = []
  for student in oldCourse['students']:
    if student not in ['jaevans@princeton.edu', 'vayyala@princeton.edu', 'isma@princeton.edu', 'rjfreling@gmail.com']:
      students.append(student)
  for student in oldCourse['inactive_students']: # to be removed later
    students.append(student)

  graders = []
  for grader in oldCourse['graders']:
    graders.append(grader)
  for grader in oldCourse['inactive_graders']: # to be removed later
    graders.append(grader)

  admins = []
  for admin in oldCourse['admins']:
    admins.append(admin)
  admins.append('james@codepost.io') # cannot patch roster without specifying self as admin

  payload = {
    'students' : students,
    'graders' : graders,
    'courseAdmins' : admins,
  }

  r = requests.patch(url + 'courses/' + str(courseID) + '/roster/', headers=headers, data=payload)
  if r.status_code != CODE_SUCCESS:
    print('FAILED : ' + r.text)
  else:
    print('Successfully updated roster.')


def inactiveRoster(courseName):
  (oldCourse, courseID) = getOldCourse(courseName)

  # Inactivate inactive students and graders
  students = []
  for student in oldCourse['students']:
    if student not in ['jaevans@princeton.edu', 'vayyala@princeton.edu', 'isma@princeton.edu', 'rjfreling@gmail.com']:
      students.append(student)

  graders = []
  for grader in oldCourse['graders']:
    graders.append(grader)

  payload = {
    'students' : students,
    'graders' : graders,
  }

  r = requests.patch(url + 'courses/' + str(courseID) + '/roster/', headers=headers, data=payload)
  if r.status_code != CODE_SUCCESS:
    print('FAILED : ' + r.text)
  else:
    print('Successfully inactivated inactive users.')

def createCourseSections(courseName):
  (oldCourse, courseID) = getOldCourse(courseName)

  r = requests.get(url + 'courses/' + str(courseID) + '/roster/', headers=headers)
  if r.status_code != CODE_SUCCESS:
    print('FAILED : ' + r.text)
  roster = r.json()

  payload = {}
  for oldSection in oldCourse['sections']:
    payload['name'] = oldSection['name']
    payload['course'] = courseID
    payload['students'] = []
    for student in oldSection['students']:
      if student not in roster['students']:
        print( 'Warning: ' + student + ' ignored because it was not present in student roster.')
      else:
        payload['students'].append(student)

    payload['leaders'] = []
    for grader in oldSection['leaders']:
      if grader not in roster['graders']:
        print('Warning: ' + grader + ' ignored because it was not present in grader roster.')
      else:
        payload['leaders'].append(grader)

    r = requests.post(url + 'sections/', headers=headers, data=payload)
    if r.status_code != CODE_CREATED:
      print("Error creating section: " + r.text)
      break

  print("Successfully created sections.")


def createAssignment(oldAssignment, courseID):
  payload = {
    'name' : oldAssignment['name'],
    'course' : courseID,
    'points' : oldAssignment['points'],
    'isReleased' : oldAssignment['isReleased']
  }

  r = requests.post(url + 'assignments/', headers=headers, data=payload)
  if r.status_code != CODE_CREATED:
    print("Error creating assignment: " + r.text)
    return
  assignmentID = r.json()['id']

  # Create rubric
  for category in oldAssignment['rubricCategories']:
    payload = {
      'assignment' : assignmentID,
      'name' : category['name'],
      'pointLimit' : category['pointLimit'],
    }

    r = requests.post(url + 'rubricCategories/', headers=headers, data=payload)
    if r.status_code != CODE_CREATED:
      print("Error creating rubric category: " + r.text)
      continue
    categoryID = r.json()['id']

    for comment in category['rubricComments']:
      payload = {
        'category' : categoryID,
        'text' : comment['text'],
        'pointDelta' : comment['pointDelta'],
      }
      r = requests.post(url + 'rubricComments/', headers=headers, data=payload)
      if r.status_code != CODE_CREATED:
        print("Error creating rubric comment: " + r.text)
        continue

  r = requests.get(url + 'assignments/' + str(assignmentID) + '/rubric/', headers=headers)
  if r.status_code != CODE_SUCCESS:
    print("Error retrieving rubric: " + r.text)
    return

  thisRubric = r.json()

  # Create submissions
  for oldSub in oldAssignment['submissions']:
    payload = {
      'assignment' : assignmentID,
      'grade' : oldSub['grade'],
      'isFinalized' : oldSub['isFinalized'],
    }

    if oldSub['grader']:
      payload['grader'] = oldSub['grader']

    payload['students'] = []
    for student in oldSub['students']:
      payload['students'].append(student)

    # If submission is finalized, ensure it has a grader
    if payload['isFinalized'] and 'grader' not in payload:
      print("Recalling finalized submission with no grader")
      payload['isFinalized'] = False

    # If the submission has no students, skip it
    if len(payload['students']) == 0:
      continue

    r = requests.post(url + 'submissions/', headers=headers, data=payload)
    if r.status_code != CODE_CREATED:
      print("Error creating submission: " + r.text)
      continue
    submissionID = r.json()['id']

    # Create files
    for oldFile in oldSub['files']:
      payload = {
        'submission' : submissionID,
        'code' : oldFile['code'],
        'name' : oldFile['name'],
        'extension' : oldFile['extension']
      }

      # If there's no code, skip the file
      if 'code' not in oldFile or not oldFile['code'] or oldFile['code'] == '':
        continue
      if payload['code'] == '\n':
        continue

      # If there's no extension, try to parse one
      if payload['extension'] == '':
        try:
          payload['extension'] = '.' + payload['name'].split('.')[1]
        except:
          payload['extension'] = '.txt'

      r = requests.post(url + 'files/', headers=headers, data=payload)
      if r.status_code != CODE_CREATED:
        print("Error creating file: " + r.text)
        print(oldFile)
        continue
      fileID = r.json()['id']

      # Create comments
      oldComments = oldFile['comments']
      for oldComment in oldComments:
        payload = {
          'text' : oldComment['text'],
          'pointDelta' : oldComment['pointDelta'],
          'startLine' : oldComment['startLine'],
          'endLine' : oldComment['endLine'],
          'startChar' : oldComment['startChar'],
          'endChar' : oldComment['endChar'],
          'file' : fileID,
        }

        # Fix malformatted comments
        try:
          if int(payload['startLine']) > int(payload['endLine']):
            temp = payload['startLine']
            payload['startLine'] = payload['endLine']
            payload['endLine'] = temp
        except:
          payload['startLine'] = 0
          payload['endLine'] = 1

        if (payload['startLine'] == payload['endLine']) and (oldComment['startChar'] > oldComment['endChar']):
          temp = payload['startChar']
          payload['startChar'] = payload['endChar']
          payload['endChar'] = temp

        # Link to rubric comments. Equality defined by text and deduction compare
        if oldComment['category']:
          matchingRubricComment = next((el for el in thisRubric['rubricComments'] if (el['text'] == payload['text'] and el['pointDelta'] == payload['pointDelta'])), None)
          if matchingRubricComment:
            payload['rubricComment'] = matchingRubricComment['id']
            payload['text'] = ''
            payload['pointDelta'] = None
          else:
            # Account for situations in which comment text might have been changed after comment was created (and linked with rubricComment)
            matchingCategory = next((el for el in thisRubric['rubricCategories'] if (el['name'] == oldComment['category'])), None)
            weakMatch = next((el for el in thisRubric['rubricComments'] if (el['category'] == matchingCategory['id'] and el['pointDelta'] == payload['pointDelta'])), None)
            if weakMatch:
              payload['rubricComment'] = weakMatch['id']
              payload['text'] = ''
              payload['pointDelta'] = None
            else:
              print("Error linking comment for submission with id %d: %s" % (submissionID, payload['text']))

        r = requests.post(url + 'comments/', headers=headers, data=payload)
        if r.status_code != CODE_CREATED:
          print("Error creating comment: " + r.text)
          continue

def createAssignmentByName(courseName, assignmentName):
  (oldCourse, courseID) = getOldCourse(courseName)

  for oldAssignment in oldCourse['assignments']:
    if oldAssignment['name'] == assignmentName:
      createAssignment(oldAssignment, courseID)
      break

  print("Successfully created %s." % (assignmentName))

def createAssignments(courseName):
  (oldCourse, courseID) = getOldCourse(courseName)

  for oldAssignment in oldCourse['assignments']:
    createAssignment(oldAssignment, courseID)

  print("Successfully created assignments.")

if __name__ == '__main__':
  # courses = ['COS126_F2018']
  # assignments = ['Hello', 'Loops', 'NBody', 'Sierpinski', 'Programming Exam 1', 'Hamming', 'LFSR', 'Guitar', 'Markov', 'TSP', 'Prgramming Exam 2', 'Atomic']
  courses = ['COS226_F2018']
  assignments = ['Percolation', 'Queues', 'Autocomplete', 'Slider Puzzle', 'Kd Tree', 'WordNet', 'Seam Carving', 'Burrows']
  # courses = ['COS126_S2016', 'COS226_S2016', 'COS126_F2016', 'COS226_F2016', 'COS326_F2016', 'COS126_S2017', 'COS226_S2017', 'COS126_F2017', 'COS226_F2017', 'COS326_F2017', 'COS432_F2017', 'COS226_S2018', 'COS126_S2018', 'COS461_S2018', 'COS333_S2018', 'COS126_SUMMER2018', 'COS226_F2018', 'COS126_F2018', 'COS326_F2018']
  for course in courses:
    print('----------------------------------------------')
    print(course)
    createCourseFromName(course)
    createCourseRosters(course)
    createCourseSections(course)
    for assignment in assignments:
      createAssignmentByName(course, assignment)
    # inactiveRoster(course)
