from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def standardLog(user, title, text, event):
    logger.info(f"Event: {title} - {text} for user {user} in channel {event}")
    return    


def AutograderError(user, title, text):
    standardLog(user, title, text, "autograder_bugs")


def AutograderTestError(user, title, text):
    standardLog(user, title, text, "autograder_test_errors")


def AutograderBuild(user, title, text):
    standardLog(user, title, text, "autograder_build_usage")


def AutograderUsage(user, title, text):
    return


def AutograderRunAllUsage(user, title, text):
    standardLog(user, title, text, "autograder_runall_usage")
