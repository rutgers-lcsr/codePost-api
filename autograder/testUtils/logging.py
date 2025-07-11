from util.slack import Slack


def standardLog(user, title, text, channel):
    sc = Slack()
    attachments = [{"title": title, "text": text}]
    sc.send_message(
        user,
        attachments=attachments,
        channel=channel,
        logInDebug=False,
        debugChannel=channel,
    )


def AutograderError(user, title, text):
    standardLog(user, title, text, "#autograder_bugs")


def AutograderTestError(user, title, text):
    standardLog(user, title, text, "#autograder_test_errors")


def AutograderBuild(user, title, text):
    return
    standardLog(user, title, text, "#autograder_build_usage")


def AutograderUsage(user, title, text):
    return
    sc = Slack()
    ignored_users = [
        "vinay@codepost.io",
        "james@codepost.io",
        "richard@codepost.io",
        "superadmin@codepost.io",
    ]

    if user in ignored_users:
        channel = "#autograder_team_usage"
    else:
        channel = "#autograder_usage"
    attachments = [{"title": title, "text": text}]
    sc.send_message(
        user,
        attachments=attachments,
        channel=channel,
        logInDebug=True,
        debugChannel=channel,
    )


def AutograderRunAllUsage(user, title, text):
    return
    standardLog(user, title, text, "#autograder_runall_usage")
