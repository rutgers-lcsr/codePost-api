# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from core.models import User, Organization

# Set up users
princeton = Organization.objects.create(name="Princeton University", shortname="Princeton",)
# f_users = open('./toMigrate/cleaned_users.txt', 'r')
# users = json.loads(f_users.read())
# for email in users:
#   if len(email) > 7:
#     if re.match(r"[^@]+@[^@]+\.[^@]+", email):
#       if not re.match(r".*@princeton.edu", email):
#         print(email)
#       me = User.objects.create(username=email, email=email)
#       me.save()

# Add james, rich, vinay as admins
superUsers = []
for name in ['richard@example.com', 'vinay@example.com', 'james@example.com']:
    newUser = User.objects.create(username=name, email=name, password="rootabega")
    newUser.profile.canCreateCourses = True
    newUser.profile.canModifyRosters = True
    newUser.set_password('rootabega')
    newUser.profile.organization = princeton
    newUser.is_superuser = True
    newUser.is_staff = True
    newUser.save()
    superUsers.append(newUser)