# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
@factory.django.mute_signals(post_save)
class SubmissionFileFactory(factory.django.DjangoModelFactory):
  
  class Meta:
    model = SubmissionFile

  name = "hello.java"
  extension = ".java"
  data = """public class LoopUtils {

  // Find the max element of an array
  public static int max(int[] arr) {

  }
}"""
  submission = factory.SubFactory('core.tests.factories.user.SubmissionFactory')
