# Create a docker file from a set of dependencies and a language
import os
import json

buildSpecs = json.load(open(os.path.join(os.path.dirname(__file__), "buildSpecs.json")))


def createDockerFile(
    language, build_type, customDockerFile="", dependencies=[], environmentID=0
):
    """
    Helper function to create a dockerfile string from a language, build_type, and dependencies
    """
    # FIXME: Currently still running a root user, not doing USER app because it doesn't work
    #  for some reason
    lookup = language if build_type == "default" else build_type
    baseStr = ""
    if lookup in buildSpecs:
        # Apt-get update gets cached, which causes some problems for new package installs
        # To get a cachce miss for this layer, we need to make it unqiue
        # However it takes some time, so we only want to do it if we are installing packages
        # This is a pretty ugly solution, but it's a common problem with ubuntu docker files and might be
        # the most elegant we can get
        uniqueStr = (
            " && echo {}".format(environmentID)
            if (len(dependencies) > 0 or len(customDockerFile) > 0)
            else ""
        )
        baseStr = buildSpecs[lookup]["base"].format(updateID=uniqueStr)
    installCmd = buildSpecs[lookup]["install"] if lookup in buildSpecs else None
    userAddCmd = buildSpecs[lookup]["useradd"] if lookup in buildSpecs else ""

    dirStr = "\nRUN mkdir -m 777 /outputs\n{}\nRUN chown -R app:app /outputs\n".format(
        userAddCmd
    )

    dependencyStr = ""
    for d in dependencies:
        if len(d.strip()) > 0:
            dependencyStr += "RUN {}\n".format(d)

    return baseStr + dirStr + dependencyStr + customDockerFile
