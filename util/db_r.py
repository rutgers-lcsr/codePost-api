# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
from django.contrib.auth.models import User
from core.models import Profile
from core.models import Organization, Course
from core.models import Section, Assignment
from core.models import Submission, File, Comment
from core.models import RubricCategory, RubricComment
import random

## Create an organization, course, and assignment
princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
hellos2019 = Assignment.objects.create(course=cos126s2019, points=20, isReleased=True, name="Hello")


## Create some superusers
james = User.objects.create(username='james.alb.evans@gmail.com', email='james.alb.evans@gmail.com', password="rootabega")
richard = User.objects.create(username='rjfreling@gmail.com', email='rjfreling@gmail.com', password="rootabega")
vinay = User.objects.create(username='vayyala@gmail.com', email='vayyala@gmail.com', password="rootabega")
vinay.profile.organization = princeton
richard.profile.organization = princeton
vinay.profile.organization = princeton
richard.profile.canCreateCourses = True
richard.profile.canModifyRosters = True
james.set_password("rootabega")
richard.set_password("rootabega")
vinay.set_password("rootabega")
james.is_superuser = True
james.is_staff = True
james.save()
richard.is_superuser = True
richard.is_staff = True
richard.save()
vinay.is_superuser = True
vinay.is_staff = True
vinay.save()

## Add some graders to the course
cos126s2019.graders.add(richard)
cos126s2019.graders.add(vinay)
cos126s2019.save()

## Add some courseadmins to the course
cos126s2019.courseAdmins.add(richard)
cos126s2019.courseAdmins.add(vinay)
cos126s2019.save()

section1 = Section.objects.create(name="P01", course=cos126s2019)
section1.leaders.add(richard)
section1.save()

code = """public class BinaryConverter {
  public static void main(String[] args){
    for(int i = -5; i < 33; i++){
      System.out.println(i + ": " + toBinary(i));
      System.out.println(i);
      //always another way
      System.out.println(i + ": " + Integer.toBinaryString(i));
    }
  }
  /*
  * pre: none
  * post: returns a String with base10Num in base 2
  */
  public static String toBinary(int base10Num){
    boolean isNeg = base10Num < 0;
    base10Num = Math.abs(base10Num);
    String result = "";

    while(base10Num > 1){
      result = (base10Num % 2) + result;
      base10Num /= 2;
    }
    assert base10Num == 0 || base10Num == 1 : "value is not <= 1: " + base10Num;

    result = base10Num + result;
    assert all0sAnd1s(result);

    if( isNeg )
      result = "-" + result;
    return result;
  }
  /*
  * pre: cal != null
  * post: return true if val consists only of characters 1 and 0, false otherwise
  */
  public static boolean all0sAnd1s(String val){
    assert val != null : "Failed precondition all0sAnd1s. parameter cannot be null";
    boolean all = true;
    int i = 0;
    char c;

    while(all && i < val.length()){
      c = val.charAt(i);
      all = c == '0' || c == '1';
      i++;
    }
    return all;
  }
}"""


## Create some students and add them to the course
for i in range(0, 5):
  username = "user" + str(i) + "@gmail.com"
  tmpUser = User.objects.create(username=username, email=username, password="rootabega")
  tmpUser.profile.organization = princeton
  tmpUser.set_password("rootabega")
  cos126s2019.students.add(tmpUser)
  tmpUser.save()
  cos126s2019.save()
  sub = Submission.objects.create(assignment=hellos2019)
  sub.students.add(tmpUser)
  tmpFile = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
  Comment.objects.create(text="good job, " + username, author=vinay, file=tmpFile, startChar=1, endChar=4, startLine=1, endLine=1)
  sub.isFinalized = True
  sub.grade = random.randint(0,20)
  sub.grader = richard
  section1.students.add(tmpUser)
  section1.save()
  sub.save()

for i in range(0, 1):
  name = "general"+str(i)
  rubricCategory = RubricCategory.objects.create(assignment=hellos2019,name=name,pointLimit=10)
  rubricComment1 = RubricComment.objects.create(text='Missing a semicolon', pointDelta=2, category=rubricCategory)
  rubricComment2 = RubricComment.objects.create(text='Need more comments1', pointDelta=3, category=rubricCategory)
  rubricComment3 = RubricComment.objects.create(text='Need more comments2', pointDelta=3, category=rubricCategory)
  rubricComment4 = RubricComment.objects.create(text='Need more comments3', pointDelta=3, category=rubricCategory)
  rubricComment5 = RubricComment.objects.create(text='Need more comments4', pointDelta=3, category=rubricCategory)

  name2="algos"+str(i)
  rubricCategory2 = RubricCategory.objects.create(assignment=hellos2019,name=name2,pointLimit=20)
  rubricComment1 = RubricComment.objects.create(text='Missing a semicolon', pointDelta=2, category=rubricCategory2)
  rubricComment2 = RubricComment.objects.create(text='Need more comments1', pointDelta=3, category=rubricCategory2)
  rubricComment3 = RubricComment.objects.create(text='Need more comments2', pointDelta=3, category=rubricCategory2)
  rubricComment4 = RubricComment.objects.create(text='Need more comments3', pointDelta=3, category=rubricCategory2)
  rubricComment5 = RubricComment.objects.create(text='Need more comments4', pointDelta=3, category=rubricCategory2)

users = User.objects.all()
for user in users:
  user.profile.organization = princeton
  user.save()

# sub = Submission.objects.create(assignment=hellos2019)
# sub.grader = richard
# cos126s2019.students.add(vinay)
# vinay.save()
# cos126s2019.save()
# sub.students.set([vinay])
# tmpFile = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
# Comment.objects.create(text="good job,", author=vinay, file=tmpFile, pointDelta=1, startChar=1, endChar=4, startLine=1, endLine=1)
# sub.isFinalized = True
# sub.grade = 20
# sub.save()

# cos126s2019.students.add(richard)
# richard.save()
# cos126s2019.save()
# sub = Submission.objects.create(assignment=hellos2019)
# sub.students.add(richard)
# tmpFile = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
# Comment.objects.create(text="good job, ", author=vinay, file=tmpFile, startChar=1, endChar=4, startLine=1, endLine=1)
# sub.isFinalized = True
# sub.grade = random.randint(0,20)
# sub.grader = vinay
# section1.students.add(richard)
# section1.save()
# sub.save()
