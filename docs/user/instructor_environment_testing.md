---
key: instructor-environment-testing
path: instructor-environment-testing
title: Environment & Testing Ops
category: Instructor Workflows
order: 11
---

# Environment & Testing Ops

This page explains how to run assignment code reliably and use tests effectively.

## Auto-Run environments

Auto-Run executes student submissions and captures outputs for instructors/graders.

It is execution infrastructure, not scoring policy by itself.

- Use it to evaluate runtime behavior.
- Pair it with rubric + script-based tests for consistent grading.

## Environment setup checklist

1. Go to **Assignments > Environment & Tests**.
2. Choose assignment language.
3. Configure build/run behavior (auto-detect or manual).
4. Attach required datasets/resources.
5. Validate with representative submissions.

### Dependency Management (Auto-Detect)

When using **Auto-Detect**, codePost looks for standard configuration files to install dependencies:

- **Python**: `requirements.txt` (installed via pip)
- **Node.js**: `package.json` (installed via npm)
- **Java**: `pom.xml` (Maven) or `build.gradle` (Gradle)

> [!TIP]
> Include these files in your **Starter Code** or upload them as **Instructor Resources** in the Environment settings to ensure they are present during the build.

## Environment shell

After environment setup, you can open an environment shell for troubleshooting:

- inspect filesystem and mounted resources
- run quick commands
- verify dependency/runtime assumptions

> [!NOTE]
> Environment shell sessions are short-lived. If a session expires, start a new one and re-run your checks.

### Pre-script (compile step) in the shell

If your environment defines a **compile / pre-script** (the command run on every submission before tests), you can execute it inside the shell to debug exactly what students see.

Tick **Run pre-script** before starting a shell session. The shell will run the pre-script once at session start, so subsequent commands operate in the same post-build state your tests will run in. Leave it unchecked for a clean shell that bypasses the pre-script entirely.

> [!TIP]
> Use the pre-script toggle when a student reports a compile-time error that doesn't reproduce in a fresh container — the pre-script may be silently failing, and running it in the shell exposes the output.

## Data Sets

Data Sets are large or static files (CSVs, model weights, reference data) that need to be present when student code or autograder tests run. Unless hidden, they are also **delivered to students** — bundled into the assignment download zip (see [What students receive](#what-students-receive) below).

### Adding a dataset

1. Open the assignment's **Settings > Resources > Datasets** panel.
2. Click **Upload Dataset**.
3. Provide:
   - **Name** — unique within the assignment (e.g. `mnist`, `housing.csv`).
   - **File** — the data to upload (up to 1 GB).
   - **Mount path** _(optional)_ — where the file appears in the execution environment.
   - **Active** — whether to mount during code execution. Toggle off to retire a dataset without deleting it. Active controls **execution mounting only** — a non-hidden dataset is included in the student download either way.

### What students receive

The student's **Download** button on an assignment returns a zip containing the assignment's starter files plus every non-hidden dataset, placed in a `data/` folder inside the zip.

- For a **per-student variant pool**, each student's zip contains **only their own variant** — assigned automatically the first time they download the assignment or list its datasets.
- Staff downloads include the shared datasets but no variants; download a specific variant from the Datasets panel instead.
- External environments that mount datasets themselves (e.g. JupyterHub) can call the download API with `?includeDatasets=false` to get starter files only; this also skips the variant auto-assignment side effect.

### Hidden datasets

A **hidden** dataset is never shown to students: it doesn't appear in their dataset listing and is not included in their assignment download. While **Active**, it is still mounted during code execution — use this for data student code needs at runtime but shouldn't take home.

Hidden is set at upload time and can't be toggled afterwards. The Datasets panel always uploads student-visible datasets; the **Upload Dataset** modal on the Environment & Tests page has a **Mark as Hidden** checkbox (on by default). Hidden datasets appear in the Datasets panel with a **Hidden** tag.

### Mount paths

- Leave **Mount path** blank to auto-mount at `~/shared/<name>`.
- A **relative path** (e.g. `mnist/` or `housing.csv`) mounts under `/shared/`.
- An **absolute path** (e.g. `/etc/config.json`) mounts at that exact location.

> [!IMPORTANT]
> A dataset mounted as a single file (e.g. `housing.csv`) and one mounted as a directory at the same parent path can conflict. Keep dataset roots distinct.

### Test resources

Datasets attached to a Test Category as a resource are grading fixtures — they are forced `hidden=true`, never included in the student's download, and never mounted in a student's own runs. They mount **only** during that test category's runs, at the resource's **target path**.

When a category has resources, its test runs mount *only* those resources — the assignment's normal datasets (including the student's variant) are not mounted. To grade against different data than the student received (e.g. a full or held-out dataset), give the resource a target path equal to the student dataset's mount path: student code reads the same path but sees your fixture. Manage resources from the **Test Resources** panel inside a test category on the Environment & Tests page.

### Per-student dataset variants

Sometimes you want **each student to work with different data** — so their results are unique and copied solutions are easy to spot. codePost supports this with a **variant pool**: a set of datasets that all mount at the **same path**, one assigned to each student.

- Mark a dataset **Per-student variant** to add it to the pool. Every variant in an assignment shares one mount path automatically, so student code reads the data by a fixed path regardless of which variant they got.
- Each student is **assigned exactly one** variant the first time they access the assignment, balanced evenly across the pool. Group submissions share a single variant.
- Manage assignments on the **Student assignments** tab (next to Data Sets) — see who has which variant, and override any student.

> [!TIP]
> **Split one file into variants.** Instead of uploading many files, upload one master CSV and use **Split into variants** on it. codePost divides it into non-overlapping row-chunks (you choose **rows per chunk**), one variant each. The chunk count is driven by rows-per-chunk, **not** current enrollment, so the pool stays stable as students add or drop the course.

### Variant robustness (autograder)

On a variant pool, turn on **Autograder checks every variant** to have the autograder rerun each finalized submission against *every other* variant — not just the student's own. If code is hardcoded to one dataset's numbers, it shows up as a failure. Results appear in the **Variant Check** panel on the grading screen. This is opt-in because it runs the autograder once per extra variant.

## Custom Docker environment

When the built-in language base images don't fit your assignment (specific compiler versions, system packages, third-party C libraries), you can extend the base image with your own Dockerfile snippet.

### Where to configure it

1. Open **Assignments > Environment & Tests**.
2. In the environment settings, set **Auto-detect** off and pick a **Build Type** (`default`, `alpine`, `ubuntu`, or `windows`).
3. Expand the **Dockerfile** section.
4. Add Dockerfile commands that will be **appended** to the codePost base image (e.g. `RUN apt-get install -y libgsl-dev`).
5. Save — codePost will rebuild the image. Watch the **Build status** and **Build logs** for failures.

### Other knobs

| Setting               | Use it for                                                                                          |
| --------------------- | --------------------------------------------------------------------------------------------------- |
| **Compile text**      | One-shot command run on every submission before tests (e.g. `javac *.java`, `pip install -r reqs`). |
| **Requirements**      | Python `requirements.txt` contents — installed during image build, not per-submission.              |
| **Env vars**          | Key/value environment variables exposed inside the container (e.g. `LC_ALL=C.UTF-8`).               |
| **Network access**    | Off by default. Enable only if students need outbound HTTP — slows runs and adds flakiness.         |
| **Max student runs**  | Cap how many times a student can trigger their own test run (for exposed tests).                    |
| **Max exposed fails** | Limit how many failing exposed tests are revealed to a student per run ("nudge mode").              |

### Image versioning & rollback

codePost keeps a history of every image build. If a new build of the environment breaks runs, you can roll back to a previous version from the **Image History** panel without losing your Dockerfile.

> [!TIP]
> Test changes against a representative student submission **before** the assignment opens for student-triggered runs. Convergence tracking will eventually flag a broken build, but you'll save students confusion by catching it early.

## Testing workflow

1. Create/open a test category.
2. Select target file context.
3. Author script tests in builder or code mode.
4. Validate parse/preview.
5. Save and run.

For exact parser-compatible syntax, use [Testing Guide](/docs/testing-guide).

## Common troubleshooting patterns

### Missing module or dependency

- Confirm language/environment selection.
- Check dataset/resource mounts.
- Rebuild environment if configuration changed.

### Tests not appearing in preview

- Confirm syntax matches parser expectations.
- Ensure each test includes parseable `name` and `points`.
- Re-open preview after save.

### Output mismatch between runs

- Check whether cached outputs are being reused.
- Re-run submission/tests when policy allows.

### Timeouts and Memory Limits

- **Timeout**: Default is 30s. If your tests are heavy, increase the timeout in the Test Script (`timeout=60`) or optimize the student code.
- **OOM (Out of Memory)**: If a container dies unexpectedly, it may have exceeded the memory limit (default 512MB). Check for infinite loops or massive data structures in the student solution.

## Related docs

- [Testing Guide](/docs/testing-guide)
- [Instructor Overview](/docs/instructor)
- [Grader Guide](/docs/grader)
