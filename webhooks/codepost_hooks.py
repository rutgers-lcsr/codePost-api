# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
codepost_hooks = {
    # 'any.event.name': 'App.Model.Action' (created/updated/deleted)
    'course.changed':           'core.Course.updated',
    'course.name':              'core.Course.name',
    'course.period':            'core.Course.period',
    'course.archived':          'core.Course.archived',

    # custom_event (views/course.py)
    'course.students':          'core.Course.students',
    'course.graders':           'core.Course.graders',
    'course.courseAdmins':      'core.Course.courseAdmins',

    'section.added':            'core.Section.created',
    'section.changed':          'core.Section.updated',
    'section.removed':          'core.Section.deleted',
    'section.name':             'core.Section.name',

    'assignment.added':         'core.Assignment.created',
    'assignment.changed':       'core.Assignment.updated',
    'assignment.removed':       'core.Assignment.deleted',
    'assignment.name':          'core.Assignment.name',
    'assignment.isVisible':     'core.Assignment.isVisible',
    'assignment.isReleased':    'core.Assignment.isReleased',
    'assignment.explanation':   'core.Assignment.explanation',
    'assignment.points':        'core.Assignment.points',

    'rubricCategory.added':     'core.RubricCategory.created',
    'rubricCategory.changed':   'core.RubricCategory.updated',
    'rubricCategory.removed':   'core.RubricCategory.deleted',
    'rubricCategory.name':      'core.RubricCategory.name',
    'rubricCategory.pointLimit': 'core.RubricCategory.pointLimit',
    'rubricCategory.helpText':  'core.RubricCategory.helpText',

    'rubricComment.added':     'core.rubricComment.created',
    'rubricComment.changed':   'core.rubricComment.updated',
    'rubricComment.removed':   'core.rubricComment.deleted',
    'rubricComment.text':      'core.rubricComment.text',
    'rubricComment.explanation': 'core.rubricComment.explanation',
    'rubricComment.instructionText': 'core.rubricComment.instructionText',
    'rubricComment.pointDelta': 'core.rubricComment.pointDelta',

    'submission.added':         'core.Submission.created',
    'submission.changed':       'core.Submission.updated',
    'submission.removed':       'core.Submission.deleted',
    'submission.grader':        'core.Submission.grader',
    'submission.isFinalized':   'core.Submission.isFinalized',
    'submission.questionIsOpen': 'core.Submission.questionIsOpen',

    'file.added':               'core.File.created',
    'file.changed':             'core.File.updated',
    'file.removed':             'core.File.deleted',
    'file.data':                'core.File.data',
    'file.name':                'core.File.name',
    'file.extension':           'core.File.extension',

    'fileTemplate.added':       'core.FileTemplate.created',
    'fileTemplate.changed':     'core.FileTemplate.updated',
    'fileTemplate.removed':     'core.FileTemplate.deleted',

    'comment.added':            'core.Comment.created',
    'comment.changed':          'core.Comment.updated',
    'comment.removed':          'core.Comment.deleted',
    'comment.text':             'core.Comment.text',
    'comment.pointDelta':       'core.Comment.pointDelta',
    'comment.rubricComment':    'core.Comment.rubricComment',

    'TestCategory.added':       'core.TestCategory.created',
    'TestCategory.changed':     'core.TestCategory.updated',
    'TestCategory.removed':     'core.TestCategory.deleted',

    'testCase.added':           'core.TestCase.created',
    'testCase.changed':         'core.TestCase.updated',
    'testCase.removed':         'core.TestCase.deleted',
    'testCase.description':     'core.TestCase.description',
    'testCase.type':            'core.TestCase.type',
    'testCase.pointsFail':      'core.TestCase.pointsFail',
    'testCase.pointsPass':      'core.TestCase.pointsPass',
    'testCase.text':            'core.TestCase.text',
    'testCase.explanation':     'core.TestCase.explanation',
    'testCase.exposed':         'core.TestCase.exposed',
    'testCase.lastSolutionRun': 'core.TestCase.lastSolutionRun',

    'submissionTest.added':     'core.SubmissionTest.created',

    'submissionHistory.changed': 'core.submissionHistory.updated',

    'environment.added':        'core.Environment.created',
    'environment.changed':      'core.Environment.updated',
    'environment.removed':      'core.Environment.deleted',
    'environment.isRunning':    'core.Environment.isRunning',

    'solutionFile.added':       'core.SolutionFile.created',
    'solutionFile.changed':     'core.SolutionFile.updated',
    'solutionFile.removed':     'core.SolutionFile.deleted',

    'helperFile.added':         'core.HelperFile.created',
    'helperFile.changed':       'core.HelperFile.updated',
    'helperFile.removed':       'core.HelperFile.deleted',
}

# Fields calculated by the system that should not trigger webhook updates
ignored_fields = {
    'core.Submission': ['dateEdited']
}
