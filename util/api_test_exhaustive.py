import requests

###############################################################################
# Testing Code
#
###############################################################################

BASE_URL = 'http://127.0.0.1:8000/api/'
CODE_SUCCESS = 200
CODE_CREATED = 201
CODE_FORBIDDEN = 403


PASSWORD = 'rootabega'

ADMIN_EMAIL = 'admin@gmail.com'
GRADER_EMAIL = 'user0@gmail.com'
SECTION_LEADER_EMAIL = 'user1@gmail.com'
PARTNER1_EMAIL = 'user2@gmail.com'
PARTNER2_EMAIL = 'user3@gmail.com'
OTHER_STUDENT_EMAIL = 'user4@gmail.com'
USERS = [ADMIN_EMAIL, GRADER_EMAIL, SECTION_LEADER_EMAIL, PARTNER1_EMAIL, PARTNER2_EMAIL, OTHER_STUDENT_EMAIL]

def testUsers(endpoint, users, expected_behavior, req_type, payload=None):
  '''
  expected_behavior = array of status codes, where the i'th element
  corresponds to the expected status code received from endpoint
  for the n-th user
  '''
  i = 0
  for user in users:
    if req_type == "GET":
      r = requests.get(BASE_URL+endpoint, auth=(user, PASSWORD))
    elif req_type == "PATCH":
      r = requests.patch(BASE_URL+endpoint, data=payload, auth=(user, PASSWORD))
    elif req_type == "POST":
      r = requests.post(BASE_URL+endpoint, data=payload, auth=(user, PASSWORD))
    elif req_type == "DELETE":
      r = requests.delete(BASE_URL+endpoint, auth=(user, PASSWORD))
    else:
      # raise error
      pass

    if r.status_code != expected_behavior[i]:
      return False
    i += 1

  return True

def testMethods(endpoint, users, expected_behavior_post,
  expected_behavior_patch, expected_behavior_get, payload_post, payload_patch):

  print("Testing POST permissions.")
  res1 = testUsers(endpoint, users, expected_behavior_post, "POST", payload=payload_post)
  if not res1:
    print("Failed POST test.")

  print("Testing PATCH permissions.")
  res2 = testUsers(endpoint + '1/', users, expected_behavior_patch, "PATCH", payload=payload_patch)
  if not res2:
    print("Failed PATCH test.")

  print("Testing GET permissions.")
  res3 = testUsers(endpoint + '1/', users, expected_behavior_get, "GET")
  if not res3:
    print("Failed GET test.")

  return (res1, res2, res3)

###############################################################################
# Set up course toplogy for testing.
###############################################################################

print('')
print("Setting up course topology.")

course1 = {
  'organization': 'Princeton',
  'name' : 'COS101',
  'period' : 'Spring',
  'courseAdmins' : ['admin0@princeton.edu'],
  'graders' : ['grader0@princeton.edu', 'grader1@princeton.edu'],
  'students': [
    'student0@princeton.edu',
    'student1@princeton.edu',
    'student2@princeton.edu',
    'student3@princeton.edu',
    'student4@princeton.edu',
    'student5@princeton.edu',
    'student6@princeton.edu',
    'student7@princeton.edu',
  ]
}

course2 = {
  'organization': 'Princeton',
  'name' : 'COS201',
  'period' : 'Spring',
  'courseAdmins' : ['admin1@princeton.edu'],
  'graders' : ['grader2@princeton.edu'],
  'students': [
    'student8@princeton.edu',
    'student9@princeton.edu',
  ]
}

course3 = {
  'organization': 'Yale',
  'name' : 'COS101',
  'period' : 'Spring',
  'courseAdmins' : ['admin0@yale.edu'],
  'graders' : ['grader0@yale.edu'],
  'students': [
    'student0@yale.edu',
  ]
}

courses = [course1, course2, course3]

# Create courses
for course in courses:
  payload = {
    'name' : course['name'],
    'period' : course['period'],
  }

  admin = course['courseAdmins'][0]

  r = requests.post(BASE_URL+'courses/', data=payload, auth=(admin, PASSWORD))
  if r.status_code != CODE_CREATED:
    print("ERROR: Failed to create course")
    print(r.status_code)

  created = r.json()
  course['id'] = created['id']

  payload = {
    'graders' : course['graders'],
    'students' : course['students'],
  }

  r = requests.patch(BASE_URL+'courses/' + str(created['id']) + '/roster/', data=payload, auth=(admin, PASSWORD))
  if r.status_code != CODE_SUCCESS:
    print("ERROR: Failed to set course roster.")

print('')

###############################################################################
# Testing course object.
###############################################################################

print('Testing <Course> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

# GET test
print("Testing GET permissions.")
expected_behavior = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]
res = testUsers('courses/' + str(courses[0]['id']) + '/', users, expected_behavior, "GET")
if not res:
  print("FAILED: course failed GET test")

# PATCH test
print("Testing PATCH permissions.")
payload = {
  'name' : '0xDEADBEEF',
}

expected_behavior = [
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]
res = testUsers('courses/' + str(courses[0]['id']) + '/', users, expected_behavior, "PATCH", payload=payload)
if not res:
  print("FAILED: course failed PATCH test")

print('')

###############################################################################
# Testing section object.
###############################################################################

print('Testing <Section> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'grader1@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

# Define section objects
section1 = {
  'name' : 'Section 1',
  'course' : courses[0]['id'],
  'students' : ['student0@princeton.edu', 'student1@princeton.edu']
}

section2 = {
  'name' : 'Section 2',
  'course' : courses[0]['id'],
}

# Test POST
print("Testing POST permissions.")

expected_behavior = [
  CODE_CREATED,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]
res = testUsers('sections/', users, expected_behavior, "POST", payload=section1)
if not res:
  print("FAILED: section failed POST test")

res = testUsers('sections/', users, expected_behavior, "POST", payload=section2)
if not res:
  print("FAILED: section failed POST test")

# Test PATCH
print("Testing PATCH permissions.")

expected_behavior = [
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

payload = {
  'leaders' : ['grader0@princeton.edu']
}

res = testUsers('sections/1/', users, expected_behavior, "PATCH", payload=payload)
if not res:
  print("FAILED: section failed PATCH test")

payload = {
  'leaders' : ['grader1@princeton.edu']
}

res = testUsers('sections/2/', users, expected_behavior, "PATCH", payload=payload)
if not res:
  print("FAILED: section failed PATCH test")

# Test GET
print("Testing GET permissions.")

expected_behavior = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

res = testUsers('sections/1/', users, expected_behavior, "GET")
if not res:
  print("FAILED: section failed GET test")

print('')

###############################################################################
# Testing Assignment object.
###############################################################################

print('Testing <Assignment> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'grader1@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

assignment = {
  'name' : 'Hello',
  'course' : courses[0]['id'],
  'points' : 20,
}

# Test POST
print("Testing POST permissions.")

expected_behavior = [
  CODE_CREATED,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]
res = testUsers('assignments/', users, expected_behavior, "POST", payload=assignment)
if not res:
  print("FAILED: assignment failed POST test")

# Test PATCH
print("Testing PATCH permissions.")

expected_behavior = [
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

payload = {
  'name' : '0xDEADBEEF',
}

res = testUsers('assignments/1/', users, expected_behavior, "PATCH", payload=payload)
if not res:
  print("FAILED: assignment failed PATCH test")

# Test GET
print("Testing GET permissions.")

expected_behavior = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

res = testUsers('assignments/1/', users, expected_behavior, "GET")
if not res:
  print("FAILED: assignment failed GET test")

print('')

###############################################################################
# Testing RubricCategory object.
###############################################################################

print('Testing <RubricCategory> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'grader1@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

category = {
  'name' : 'Style',
  'assignment' : 1,
  'pointLimit' : 10,
}

# Test POST
print("Testing POST permissions.")

expected_behavior = [
  CODE_CREATED,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]
res = testUsers('rubriccategories/', users, expected_behavior, "POST", payload=category)
if not res:
  print("FAILED: rubricCategory failed POST test")
  print(r.text)

# Test PATCH
print("Testing PATCH permissions.")

expected_behavior = [
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

payload = {
  'name' : '0xDEADBEEF',
}

res = testUsers('rubriccategories/1/', users, expected_behavior, "PATCH", payload=payload)
if not res:
  print("FAILED: rubricCategory failed PATCH test")

# Test GET
print("Testing GET permissions.")

expected_behavior = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

res = testUsers('rubriccategories/1/', users, expected_behavior, "GET")
if not res:
  print("FAILED: rubricCategory failed GET test")

print('')

###############################################################################
# Testing RubricComment object.
###############################################################################

print('Testing <RubricComment> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'grader1@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

rubricComment = {
  'text' : 'Bad style!',
  'category' : 1,
  'pointDelta' : -1,
}

payload = {
  'name' : '0xDEADBEEF',
}

expected_behavior_post = [
  CODE_CREATED,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_patch = [
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_get = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

testMethods('rubriccomments/', users, expected_behavior_post,
  expected_behavior_patch, expected_behavior_get, rubricComment, payload)

print('')

###############################################################################
# Testing Submission object.
###############################################################################

print('Testing <Submission> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'grader1@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

submission = {
  'assignment' : 1,
  'students' : ['student0@princeton.edu'],
  'grader' : 'grader1@princeton.edu'
}

payload = {
  'students' : ['student0@princeton.edu', 'student1@princeton.edu'],
}

expected_behavior_post = [
  CODE_CREATED,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_patch = [
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_get = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

testMethods('submissions/', users, expected_behavior_post,
  expected_behavior_patch, expected_behavior_get, submission, payload)

print('')

###############################################################################
# Testing File object.
###############################################################################

print('Testing <File> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'grader1@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

file = {
  'submission' : 1,
  'code' : 'Hello, World!',
  'name' : 'hello.java',
  'ext' : 'java'
}

payload = {
  'name' : '0xDEADBEEF'
}

expected_behavior_post = [
  CODE_CREATED,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_patch = [
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_get = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

testMethods('files/', users, expected_behavior_post,
  expected_behavior_patch, expected_behavior_get, file, payload)

print('')

###############################################################################
# Testing Comment object.
###############################################################################

print('Testing <Comment> object permissions')

users = [
  'admin0@princeton.edu', # COS101 - Princeton
  'grader0@princeton.edu', # COS101 - Princeton
  'grader1@princeton.edu', # COS101 - Princeton
  'student0@princeton.edu', # COS101 - Princeton
  'admin1@princeton.edu', # COS201 - Princeton
  'grader2@princeton.edu', # COS201 - Princeton
  'student8@princeton.edu', # COS201 - Princeton
  'admin0@yale.edu', # COS101 - Yale
  'grader0@yale.edu', # COS101 - Yale
  'student0@yale.edu', # COS101 - Yale
]

comment = {
  'text' : 'Boo!',
  'pointDelta' : -1,
  'file' : 1,
  'startChar' : 1,
  'endChar' : 2,
  'startLine' : 0,
  'endLine' : 0,
}

payload = {
  'text' : '0xDEADBEEF'
}

expected_behavior_post = [
  CODE_CREATED,
  CODE_CREATED,
  CODE_CREATED,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_patch = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

expected_behavior_get = [
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_SUCCESS,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
  CODE_FORBIDDEN,
]

testMethods('comments/', users, expected_behavior_post,
  expected_behavior_patch, expected_behavior_get, comment, payload)

print('')

payload = {
  'grader' : [],
  'students' : [],
}

r = requests.patch(BASE_URL+'submissions/1/', data=payload, auth=('admin0@princeton.edu', PASSWORD))
if r.status_code == 200:
  print(r.json())
else:
  print(r.text)
