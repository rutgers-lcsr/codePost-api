# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.

import json
import copy

f_users = open('./toMigrate/userList.txt', 'r')
f_courses = open('./toMigrate/courseList.txt', 'r')
f_sections = open('./toMigrate/sectionList.txt', 'r')
f_assignments = open('./toMigrate/assignmentList.txt', 'r')
f_submissions = open('./toMigrate/submissionList.txt', 'r')

# Eliminate invalid emails
users = json.loads(f_users.read())
cleaned_users = []
for email in users:
  if len(email.split('@')) == 2:
    cleaned_users.append(email)

toWrite = open('./toMigrate/cleaned_users.txt', 'w')
json.dump(cleaned_users, toWrite)
toWrite.close()

courses = json.loads(f_courses.read())
cleaned_courses = []
submissions = json.loads(f_submissions.read())
for course in courses:
  matchingCourse = next((el for el in cleaned_courses if el['name'] == course['name']), None)
  if not matchingCourse:
    cleaned_course = {}
    cleaned_course['name'] = course['name']
    cleaned_course['organization'] = course['organization']

    cleaned_course['students'] = []
    for student in course['students']:
      if student in cleaned_users:
        cleaned_course['students'].append(student)

    cleaned_course['graders'] = []
    for grader in course['graders']:
      if grader in cleaned_users:
        cleaned_course['graders'].append(grader)

    cleaned_course['admins'] = []
    for admin in course['admins']:
      if admin in cleaned_users:
        cleaned_course['admins'].append(admin)

    # identify inactive students and graders
    cleaned_course['inactive_students'] = []
    cleaned_course['inactive_graders'] = []
    for sub in submissions:
      if sub['course'] == course['name']:
        for student in sub['students']:
          if student not in cleaned_course['students']:
            cleaned_course['inactive_students'].append(student)
        if sub['grader'] and sub['grader'] not in cleaned_course['graders']:
          cleaned_course['inactive_graders'].append(sub['grader'])

    # identify inactive graders
    cleaned_course['sections'] = []
    cleaned_course['assignments'] = []

    cleaned_courses.append(cleaned_course)

sections = json.loads(f_sections.read())
for section in sections:
  matchingCourse = next((el for el in cleaned_courses if el['name'] == section['course']), None)
  if matchingCourse:
    matchingSection = next((el for el in matchingCourse['sections'] if el['name'] == section['name']), None)
    if not matchingSection:
      cleaned_section = {}
      cleaned_section['name'] = section['name']

      cleaned_section['leaders'] = []
      if section['leader'] and section['leader'][0] in matchingCourse['graders']:
        cleaned_section['leaders'].append(section['leader'][0])

      cleaned_section['students'] = []
      for student in section['students']:
        if student in matchingCourse['students']:
          cleaned_section['students'].append(student)

      matchingCourse['sections'].append(cleaned_section)

assignments = json.loads(f_assignments.read())
for assignment in assignments:
  matchingCourse = next((el for el in cleaned_courses if el['name'] == assignment['course']), None)
  if matchingCourse:
    matchingAssignment = next((el for el in matchingCourse['assignments'] if el['name'] == assignment['name']), None)
    if not matchingAssignment:
      cleaned_assignment = {}
      cleaned_assignment['name'] = assignment['name']
      cleaned_assignment['points'] = assignment['points']
      cleaned_assignment['isReleased'] = assignment['isReleased']
      cleaned_assignment['submissions'] = []

      # Build rubric
      cleaned_assignment['rubricCategories'] = []
      if assignment['rubric']:
        rubric = json.loads(assignment['rubric'])
        for category in rubric:
          matchingCategory = next((el for el in cleaned_assignment['rubricCategories'] if el['name'] == category['name']), None)
          if not matchingCategory:
            cleaned_category = {}
            cleaned_category['name'] = category['name']
            try:
              if (float(category['cap']) > 0):
                cleaned_category['pointLimit'] = float(category['cap'])
              else:
                cleaned_category['pointLimit'] = None
            except:
              cleaned_category['pointLimit'] = None
            cleaned_category['rubricComments'] = []
            for comment in category['deductions']:
              matchingComment = next((el for el in cleaned_category['rubricComments'] if el['text'] == comment['desc']), None)
              if not matchingComment:
                cleaned_rubricComment = {}
                cleaned_rubricComment['text'] = comment['desc']
                try:
                  cleaned_rubricComment['pointDelta'] = float(comment['deduction'])
                except:
                  cleaned_rubricComment['pointDelta'] = 0
                cleaned_category['rubricComments'].append(cleaned_rubricComment)
            cleaned_assignment['rubricCategories'].append(cleaned_category)

      matchingCourse['assignments'].append(cleaned_assignment)

for sub in submissions:
  matchingCourse = next((el for el in cleaned_courses if el['name'] == sub['course']), None)
  if matchingCourse:
    matchingAssignment = next((el for el in matchingCourse['assignments'] if el['name'] == sub['assignment']), None)
    if matchingAssignment:
      cleaned_sub = {}
      cleaned_sub['grade'] = sub['grade']
      cleaned_sub['date_finalized'] = sub['date_finalized']
      cleaned_sub['isFinalized'] = sub['status'] == 'f'
      if sub['grader'] in matchingCourse['graders'] or sub['grader'] in matchingCourse['inactive_graders']:
        cleaned_sub['grader'] = sub['grader']
      else:
        cleaned_sub['grader'] = None

      cleaned_sub['students'] = []
      for student in sub['students']:
        if student in matchingCourse['students'] or student in matchingCourse['inactive_students']:
          cleaned_sub['students'].append(student)

      # Build files
      cleaned_sub['files'] = []
      for file in sub['files']:
        matchingFile = next((el for el in cleaned_sub['files'] if el['name'] == file['name']), None)
        if not matchingFile:
          cleaned_file = {}
          cleaned_file['name'] = file['name']
          cleaned_file['extension'] = file['extension']
          cleaned_file['code'] = file['code']

          # Build comments
          cleaned_file['comments'] = []
          fileComments = json.loads(file['standard_comments'])['results']
          for comment in fileComments:
            cleaned_comment = {}
            cleaned_comment['text'] = comment['text']

            try:
              cleaned_comment['pointDelta'] = float(comment['deduction'])
            except:
              cleaned_comment['pointDelta'] = 0

            if 'startLine' in comment:
              cleaned_comment['startLine'] = comment['startLine']
            else:
              cleaned_comment['startLine'] = 0

            if 'endLine' in comment:
              cleaned_comment['endLine'] = comment['endLine']
            else:
              cleaned_comment['endLine'] = 0

            if 'startChar' in comment and type(comment['startChar']) is int:
              cleaned_comment['startChar'] = comment['startChar']
            else:
              cleaned_comment['startChar'] = 0

            if 'endChar' in comment and type(comment['endChar']) is int:
              cleaned_comment['endChar'] = comment['endChar']
            else:
              cleaned_comment['endChar'] = 0

            if len(comment['tags']) > 0:
              cleaned_comment['category'] = comment['tags'][0]
            else:
              cleaned_comment['category'] = None

            cleaned_file['comments'].append(cleaned_comment)

          cleaned_sub['files'].append(cleaned_file)

      matchingAssignment['submissions'].append(cleaned_sub)

toWrite = open('./toMigrate/cleaned_data.txt', 'w')
json.dump(cleaned_courses, toWrite)
toWrite.close()

