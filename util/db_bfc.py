from django.contrib.auth.models import User
from core.models import Profile
from core.models import Organization, Course
from core.models import Section, Assignment
from core.models import Submission, File, Comment
from core.models import RubricCategory, RubricComment
import decimal

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


import random

# Create an organization, course, and assignment
huge = Organization.objects.create(
    name="huge", shortname="huge")
course = Course.objects.create(
    organization=huge, period="IRL2020", name="B.F.C.")

assignments = []
hellos2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="Hello", allowStudentUpload=True)
assignments.append(hellos2019)
loopss2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="loops", allowStudentUpload=True)
assignments.append(loopss2019)
nbodys2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="nbody", allowStudentUpload=True)
assignments.append(nbodys2019)
sierpinskis2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="sierpinski", allowStudentUpload=True)
assignments.append(sierpinskis2019)
hammings2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="hamming", allowStudentUpload=True)
assignments.append(hammings2019)
lfsrs2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="lfsr", allowStudentUpload=True)
assignments.append(lfsrs2019)
guitars2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="guitar", allowStudentUpload=True)
assignments.append(guitars2019)
markovs2019 = Assignment.objects.create(
    course=course, points=20, isReleased=True, name="markov", allowStudentUpload=True)
assignments.append(markovs2019)

# Create some superusers
admin = User.objects.create(
    username='admin@codepost.io', email='admin@codepost.io', password="rootabega")
superadmin = User.objects.create(
    username='superadmin@codepost.io', email='superadmin@codepost.io', password="rootabega")
superadmin.profile.organization = huge
admin.profile.organization = huge
admin.profile.canCreateCourses = True
superadmin.profile.canCreateCourses = True
admin.profile.canModifyRosters = True
superadmin.profile.canModifyRosters = True
superadmin.set_password("rootabega")
superadmin.save()
admin.set_password("rootabega")
admin.save()
superadmin.is_superuser = True
superadmin.is_staff = True
superadmin.save()

course.save()

course.courseAdmins.add(superadmin)

for assignment in course.assignments.all():
  for i in range(0, 5):
    print("\033[92m rubric\t{}\033[00m" .format(i))
    name = "Category ({})".format(i)
    rubricCategory = RubricCategory.objects.create(assignment=assignment, name=name, pointLimit=10)
    rubricComment1 = RubricComment.objects.create(text='Rubric comment 1', pointDelta=2, category=rubricCategory)
    rubricComment2 = RubricComment.objects.create(text='Rubric comment 2', pointDelta=2, category=rubricCategory)
    rubricComment3 = RubricComment.objects.create(text='Rubric comment 3', pointDelta=2, category=rubricCategory)
    rubricComment4 = RubricComment.objects.create(text='Rubric comment 4', pointDelta=2, category=rubricCategory)


for i in range(700):
  student = User.objects.create(username="student{}@codepost.io".format(
      i), email="student{}@codepost.io".format(i), password="rootabega")
  student.profile.organization = huge
  student.set_password("rootabega")
  student.save()
  course.students.add(student)

  print("\033[92m student\t{}\033[00m" .format(i))

  for assignment in course.assignments.all():
    if random.randint(0, 10) != 5:
      sub = Submission.objects.create(assignment=assignment)
      sub.students.add(student)
      sub.grader = superadmin

      category_index = random.randint(0, 4)
      category = assignment.rubricCategories.all()[category_index]
      rubricComment = category.rubricComments.all()[0]

      file = File.objects.create(name="BinaryConverter.java", code=code, submission=sub, extension='java')
      Comment.objects.create(text="Small fish in a big pond...", author=superadmin, file=file,
                             startChar=1, endChar=4, startLine=1, endLine=1, pointDelta=4)

      Comment.objects.create(text="Small fish in a big pond...", author=superadmin, file=file,
                             startChar=5, endChar=9, startLine=2, endLine=2, rubricComment=rubricComment)

      Comment.objects.create(text="Small fish in a big pond...", author=superadmin, file=file,
                             startChar=5, endChar=9, startLine=3, endLine=3, rubricComment=rubricComment)

      if bool(random.getrandbits(1)):
        sub.isFinalized = True
        sub.grade = 12
      else:
        sub.isFinalized = False

      sub.save()


for i in range(100):
  grader = User.objects.create(username="grader{}@codepost.io".format(
      i), email="grader{}@codepost.io".format(i), password="rootabega")
  grader.profile.organization = huge
  grader.set_password("rootabega")
  grader.save()
  course.graders.add(grader)
  print("\033[92m grader - {}\033[00m" .format(i))

course.save()
