###############################################################################
# codePost API Speed Test
# Purpose: Test to guage speed of various common API endpoints.
#
###############################################################################

import requests

# Assume the existence of a superuser named james.
superuser_email = 'james@codepost.io'
superuser_password = 'rootabega'

# Basic constants
BASE_URL = 'http://127.0.0.1:8000/api/'
CODE_SUCCESS = 200
CODE_CREATED = 201

# Testing paramters
numOrganizations = 2
numCourses = 2
numAssignmnents = 2
numStudents = 2
numGraders = 2
numAdmins = 1
numFiles = 1
numComments = 1

###############################################################################

# Create objects. It is important to consider the order in which objects are created,
# since interactions between object types can influence scaling behavior.
# For example, it might be much harder (i.e. resource intensive) to create a course
# object when there are many users. This limitation would not be evident if a test
# script created all course objects before creating all user objects.

# Methodology: Try to mimic sequencing of requests we expect to be made in real life.
# Organizations --> course --> users --> assignment --> submission --> assignment --> ...
# --> submission --> course

# Create organizations
for i in range(0, numOrganizations):
  payload = {
    'name' : 'organization' + str(i),
    'shortname' : 'org' + str(i),
  }
  r = requests.post(BASE_URL+'organizations/', data=payload, auth=(superuser_email, superuser_password))
  if r.status_code != CODE_CREATED:
    print("Failed to create organizations")
    print(r.text)
    quit()

courseDict = []
# Create courses
for i in range(0, numOrganizations):
    for j in range(0, numCourses):

      # Build roster
      students = []
      graders = []
      courseAdmins = []
      for k in range(0, numStudents):
        email = "student" + str(j*numCourses + k) + "@org" + str(i+1) + ".edu"
        payload = {'email' : email, 'password' : superuser_password, 'organization' : i+1}
        r = requests.post(BASE_URL+'users/', data=payload, auth=(superuser_email, superuser_password))
        students.append(email)
      for k in range(0, numGraders):
        email = "grader" + str(j*numCourses + k) + "@org" + str(i+1) + ".edu"
        payload = {'email' : email, 'password' : superuser_password, 'organization' : i+1}
        r = requests.post(BASE_URL+'users/', data=payload, auth=(superuser_email, superuser_password))
        graders.append(email)
      for k in range(0, numAdmins):
        email = "admin" + str(j*numCourses + k) + "@org" + str(i+1) + ".edu"
        payload = {'email' : email, 'password' : superuser_password, 'organization' : i+1}
        r = requests.post(BASE_URL+'users/', data=payload, auth=(superuser_email, superuser_password))
        courseAdmins.append(email)

      # Store in persistent object
      courseDict.append([])
      courseDict[i].append([])
      courseDict[i][j] = {}
      courseDict[i][j]["students"] = students
      courseDict[i][j]["graders"] = graders
      courseDict[i][j]["courseAdmins"] = courseAdmins

      # Create course
      creating_user = courseAdmins[0]
      payload = {
        'name' : 'COS10' + str(i*numCourses+j+1),
        'period' : 'N/A',
      }
      r = requests.post(BASE_URL+'courses/', data=payload, auth=(creating_user, superuser_password))
      if r.status_code != CODE_CREATED:
        print("Failed to create course")
        print(r.text)
        quit()
      else:
        courseID = r.json()['id']

      # Upload roster
      payload = {
        'students' : students,
        'graders' : graders,
        'courseAdmins' : courseAdmins
      }

      r = requests.patch(BASE_URL+'courses/' + str(courseID) + '/roster/', data=payload, auth=(creating_user, superuser_password))
      if r.status_code != CODE_SUCCESS:
        print("Failed to upload course roster")
        print(r.text)
        quit()

# Create assignments and submissions
for i in range(0, numAssignmnents):
  for j in range(0, numOrganizations):
    for k in range(0, numCourses):
      payload = {
        'course' : j*numCourses + k + 1,
        'name' : 'Assignment ' + str(i),
        'points' : 20,
      }
      creating_user = courseDict[j][k]["courseAdmins"][0]
      r = requests.post(BASE_URL+'assignments/', data=payload, auth=(creating_user, superuser_password))
      if r.status_code != CODE_CREATED:
        print("Failed to create assignment")
        print(r.text)
        quit()
      else:
        assignmentID = r.json()['id']

      for l in range(0, numStudents):
        payload = {
          'assignment' : assignmentID,
          'students' : [courseDict[j][k]["students"][l]],
        }
        r = requests.post(BASE_URL+'submissions/', data=payload, auth=(creating_user, superuser_password))
        if r.status_code != CODE_CREATED:
          print("Failed to create submission")
          print(r.text)
          quit()
        else:
          submissionID = r.json()['id']

        for m in range(0, numFiles):
          payload = {
            'name' : 'File ' + str(m),
            'extension' : '.js',
            'submission' : submissionID,
            'code' : 'Hello World!'
          }
          r = requests.post(BASE_URL+'files/', data=payload, auth=(creating_user, superuser_password))
          if r.status_code != CODE_CREATED:
            print("Failed to create submission")
            print(r.text)
            quit()
          else:
            fileID = r.json()['id']

          for n in range(0, numComments):
            payload = {
              'text' : 'nice!',
              'pointDelta' : 0,
              'startChar' : 1,
              'endChar' : 3,
              'startLine' : 0,
              'endLine' : 0,
              'file' : fileID,
            }

            r = requests.post(BASE_URL+'comments/', data=payload, auth=(creating_user, superuser_password))
            if r.status_code != CODE_CREATED:
              print("Failed to create comment")
              print(r.text)
              quit()

###############################################################################

# Get objects
for i in range(numOrganizations):
  for j in range(numCourses):
    user = courseDict[i][j]['courseAdmins'][0]

    r = requests.get(BASE_URL+'courses/' + str(i*numCourses+j+1) + '/', auth=(user, superuser_password))
    if r.status_code != CODE_SUCCESS:
      print("Failed to get course")
      print(r.text)
      quit()
    else:
      assignments = r.json()['assignments']

    r = requests.get(BASE_URL+'courses/' + str(i*numCourses+j+1) + '/roster/', auth=(user, superuser_password))
    if r.status_code != CODE_SUCCESS:
      print("Failed to get course")
      print(r.text)
      quit()

    for assignment in assignments:
      r = requests.get(BASE_URL+'assignments/' + str(assignment) + '/', auth=(user, superuser_password))
      if r.status_code != CODE_SUCCESS:
        print("Failed to get assignment")
        print(r.text)
        quit()
      r = requests.get(BASE_URL+'assignments/' + str(assignment) + '/submissions/', auth=(user, superuser_password))
      if r.status_code != CODE_SUCCESS:
        print("Failed to get assignment submissions")
        print(r.text)
        quit()
      else:
        submissions = r.json()

      for submission in submissions:
        r = requests.get(BASE_URL+'submissions/' + str(submission['id']) + '/', auth=(user, superuser_password))
        if r.status_code != CODE_SUCCESS:
          print("Failed to get submission")
          print(r.text)
          quit()
        else:
          files = r.json()['files']

        for file in files:
          r = requests.get(BASE_URL+'files/' + str(file) + '/', auth=(user, superuser_password))
          if r.status_code != CODE_SUCCESS:
            print("Failed to get file")
            print(r.text)
            quit()
          else:
            comments = r.json()['comments']

          for comment in comments:
            r = requests.get(BASE_URL+'comments/' + str(comment) + '/', auth=(user, superuser_password))
            if r.status_code != CODE_SUCCESS:
              print("Failed to get comment")
              print(r.text)
              quit()

###############################################################################

# Patch objects
for i in range(numOrganizations):
  for j in range(numCourses):
    user = courseDict[i][j]['courseAdmins'][0]

    r = requests.get(BASE_URL+'courses/' + str(i*numCourses+j+1) + '/', auth=(user, superuser_password))
    if r.status_code != CODE_SUCCESS:
      print("Failed to get course")
      print(r.text)
      quit()
    else:
      assignments = r.json()['assignments']

    for assignment in assignments:
      r = requests.get(BASE_URL+'assignments/' + str(assignment) + '/', auth=(user, superuser_password))
      if r.status_code != CODE_SUCCESS:
        print("Failed to get assignment")
        print(r.text)
        quit()
      r = requests.get(BASE_URL+'assignments/' + str(assignment) + '/submissions/', auth=(user, superuser_password))
      if r.status_code != CODE_SUCCESS:
        print("Failed to get assignment submissions")
        print(r.text)
        quit()
      else:
        submissions = r.json()

      for submission in submissions:
        r = requests.get(BASE_URL+'submissions/' + str(submission['id']) + '/', auth=(user, superuser_password))
        if r.status_code != CODE_SUCCESS:
          print("Failed to get submission")
          print(r.text)
          quit()
        else:
          files = r.json()['files']

        for file in files:
          r = requests.get(BASE_URL+'files/' + str(file) + '/', auth=(user, superuser_password))
          if r.status_code != CODE_SUCCESS:
            print("Failed to get file")
            print(r.text)
            quit()
          else:
            comments = r.json()['comments']

          for comment in comments:
            r = requests.get(BASE_URL+'comments/' + str(comment) + '/', auth=(user, superuser_password))
            if r.status_code != CODE_SUCCESS:
              print("Failed to get comment")
              print(r.text)
              quit()

#######################################################################
# Stuff that remains
# - sections, rubrics
# - assigning graders
# - add timing infrastructure
# - add graphing infrastructure to graph timing data
