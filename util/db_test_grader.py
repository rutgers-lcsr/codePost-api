# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rutgers Non-Commercial License, included with this software.
from django.contrib.auth.models import User
from core.models import *

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

long_code = code + code + code + code + code

TEST = 7
print ("==========\n== TEST #%d\n==========" % TEST)

if (TEST == 0):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

if (TEST == 1):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

  cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
  cos126s2019.graders.add(user)
  cos126s2019.save()

if (TEST == 2):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

  cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
  cos126s2019.graders.add(user)
  cos126s2019.save()

  hellos2019 = Assignment.objects.create(course=cos126s2019, points=20, isReleased=True, name="Hello")

  username = 'student@student.io'
  student = User.objects.create(username=username, email=username, password="rootabega")
  student.profile.organization = princeton
  cos126s2019.students.add(student)
  cos126s2019.save()

  sub = Submission.objects.create(assignment=hellos2019)
  sub.students.add(student)
  file = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
  Comment.objects.create(text="good job!", author=user, file=file, startChar=4, endChar=10, startLine=1, endLine=1)
  sub.isFinalized = True
  sub.grader = user
  sub.save()

  cos126s2019.graders.remove(user)
  cos126s2019.inactive_graders.add(user)
  cos126s2019.save()

if (TEST == 3):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

  cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
  cos126s2019.graders.add(user)
  cos126s2019.superGraders.add(user)
  cos126s2019.save()

  hellos2019 = Assignment.objects.create(course=cos126s2019, points=20, isReleased=True, name="Hello")

if (TEST == 4):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

  cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
  cos126s2019.graders.add(user)
  cos126s2019.save()

  hellos2019 = Assignment.objects.create(course=cos126s2019, points=20, isReleased=True, name="Hello")

  username = 'student@student.io'
  student = User.objects.create(username=username, email=username, password="rootabega")
  student.profile.organization = princeton
  cos126s2019.students.add(student)
  cos126s2019.save()

  sub = Submission.objects.create(assignment=hellos2019)
  sub.students.add(student)
  file = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
  sub.isFinalized = False
  sub.save()

if (TEST == 5):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

  cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
  cos126s2019.graders.add(user)
  cos126s2019.superGraders.add(user)
  cos126s2019.save()

  username = 'student@student.io'
  student = User.objects.create(username=username, email=username, password="rootabega")
  student.profile.organization = princeton
  cos126s2019.students.add(student)
  cos126s2019.save()

  hellos2019 = Assignment.objects.create(course=cos126s2019, points=20, isReleased=True, name="Hello")

  sub = Submission.objects.create(assignment=hellos2019)
  sub.students.add(student)
  file = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
  sub.isFinalized = False
  sub.save()

if (TEST == 6):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

  cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
  cos126s2019.graders.add(user)
  cos126s2019.save()

  hellos2019 = Assignment.objects.create(course=cos126s2019, points=20, isReleased=True, name="Hello")

  username = 'student@student.io'
  student = User.objects.create(username=username, email=username, password="rootabega")
  student.profile.organization = princeton
  cos126s2019.students.add(student)
  cos126s2019.save()

  sub = Submission.objects.create(assignment=hellos2019)
  sub.students.add(student)
  file = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
  sub.isFinalized = False
  sub.grader = user
  sub.save()

if (TEST == 7):
  princeton = Organization.objects.create(name="Princeton University", shortname="Princeton")
  username = 'simon@sample.io'
  user = User.objects.create(username=username, email=username, password="rootabega")
  user.profile.organization = princeton
  user.set_password("rootabega")
  user.save()

  cos126s2019 = Course.objects.create(organization=princeton, period="S2019", name="COS126")
  cos126s2019.graders.add(user)
  cos126s2019.superGraders.add(user)
  cos126s2019.save()

  username = 'student@student.io'
  student = User.objects.create(username=username, email=username, password="rootabega")
  student.profile.organization = princeton
  cos126s2019.students.add(student)
  cos126s2019.save()

  hellos2019 = Assignment.objects.create(course=cos126s2019, points=20, isReleased=True, name="Hello")

  sub = Submission.objects.create(assignment=hellos2019)
  sub.students.add(student)
  file = File.objects.create(name="hello.java", code=code, submission=sub, extension='java')
  sub.isFinalized = False
  sub.grader = user
  sub.save()
