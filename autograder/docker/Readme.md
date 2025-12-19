This directory contains the dockerfiles for the autograders executor environment.

These are meant to be used with the executor.py file as docker images.

for example, when a worker starts, it will create a image from the dockerfile, and then run the executor.py file inside of it. A new container is created for each execution, and is disposed of after the execution is complete. This allows us to have a clean already established environment for each execution.

This is mainly because package installs take a long time, and we don't want to do it for every execution.

Eventually, the goal is to have the docker images be built and pushed to a registry, this way only one of the workers/api servers needs to build the image, and then all the workers can use the same image.
