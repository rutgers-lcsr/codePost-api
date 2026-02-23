#!/bin/bash
# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
# exit on error
set -o errexit

poetry install

python manage.py collectstatic --no-input
python manage.py migrate

# if printenv | grep -q RDS_HOSTNAME; then
#   echo NOT MIGRATING
# else
#   echo MIGRATING
#   python manage.py migrate
#   cat << EOF > init.py
# u = User.objects.create(username='rjfreling@gmail.com', email='rjfreling@gmail.com', password="rootabega")
# u.set_password("rootabega")
# u.is_superuser = True
# u.is_staff = True
# u.save()
# if Organization.objects.all().count() == 0:
#   org = Organization.objects.create(name="SQLite Org", shortname="sqlite")
#   course = Course.objects.create(organization=org, period="F2023", name="CS10")
#   for i in range(1,40):
#     Assignment.objects.create(course=course, points=20, isReleased=True, name="assignment-"+str(i))

# EOF
#   python manage.py shell_plus < init.py
# fi



