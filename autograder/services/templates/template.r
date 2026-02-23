# Copyright © 2026 Rutgers, the State University of New Jersey. All rights reserved except as defined by the Rurtgers Non-Commercial Licensed, included with this software.
# CodePost R Plot Capture Wrapper
local({
    # Create a temp dir for plots
    plot_dir <- tempfile()
    dir.create(plot_dir)
    plot_pattern <- file.path(plot_dir, "plot_%03d.png")

    # Snapshot existing PNG files in working directory so we can detect
    # new student-generated PNG outputs (e.g. explicit png('file.png')).
    cwd <- getwd()
    existing_pngs <- if (dir.exists(cwd)) {
        list.files(cwd, pattern = "\\.png$", full.names = TRUE)
    } else {
        character(0)
    }
    
    # Open PNG device with pattern for multiple pages
    png(plot_pattern, width = 800, height = 600)

    tryCatch({
        # Execute student code expression-by-expression.
        # We selectively auto-print plot objects (e.g., ggplot/lattice) to preserve
        # notebook-like rendering, while suppressing noisy scalar returns such as
        # graphics device IDs (e.g., `png` -> `2`).
        parsed_exprs <- parse(file = "student.R")
        student_env <- globalenv()

        for (expr in parsed_exprs) {
            vis <- withVisible(eval(expr, envir = student_env))
            should_auto_print <- isTRUE(vis$visible) && (
                inherits(vis$value, "ggplot") ||
                inherits(vis$value, "gg") ||
                inherits(vis$value, "trellis")
            )

            if (should_auto_print) {
                print(vis$value)
            }
        }
        
    }, finally = {
        # Close device
        dev.off()

        emit_plot_file <- function(p_file) {
            if (!file.exists(p_file)) return(invisible(NULL))
            if (is.na(file.info(p_file)$size) || file.info(p_file)$size <= 1000) return(invisible(NULL))

            raw_data <- readBin(p_file, "raw", n = file.info(p_file)$size)
            encoded <- base64enc::base64encode(raw_data)
            cat(paste0("\n<<<CODEPOST_PLOT:", encoded, ">>>\n"))
            invisible(NULL)
        }
        
        # List all generated plot files
        plot_files <- list.files(plot_dir, pattern = "plot_\\d+\\.png", full.names = TRUE)
        # Sort to ensure order
        plot_files <- sort(plot_files)
        
        if (requireNamespace("base64enc", quietly = TRUE)) {
            if (length(plot_files) > 0) {
                for (p_file in plot_files) {
                    emit_plot_file(p_file)
                }
            }

            # Capture new PNG files created by student code in cwd, including
            # explicit png('file.png') usage.
            current_pngs <- if (dir.exists(cwd)) {
                list.files(cwd, pattern = "\\.png$", full.names = TRUE)
            } else {
                character(0)
            }
            new_pngs <- setdiff(current_pngs, existing_pngs)
            new_pngs <- sort(new_pngs)
            for (p_file in new_pngs) {
                emit_plot_file(p_file)
            }
        } else {
            message("[CodePost] Plots generated but 'base64enc' package missing. Cannot capture.")
        }
        
        # Cleanup
        unlink(plot_dir, recursive = TRUE)
    })
})

# ==========================================
# TEST FRAMEWORK (R Script)
# ==========================================
test_results <- list()

run_test <- function(name, points, description = NULL, fn = NULL, timeout = 30) {
    if (is.function(description)) {
        timeout <- fn
        fn <- description
        description <- NULL
    }

    result <- list(
        name = name,
        max_score = points,
        description = description,
        message = "",
        score = 0,
        passed = FALSE,
        status = "failed",
        error = ""
    )

    tryCatch({
        setTimeLimit(elapsed = timeout, transient = TRUE)
        on.exit(setTimeLimit(elapsed = Inf, transient = TRUE), add = TRUE)

        ret <- fn()
        if (is.numeric(ret) && length(ret) >= 1) {
            score <- as.numeric(ret[[1]])
            result$score <- max(0, min(score, points))
            result$passed <- result$score == points
            result$status <- if (result$passed) "passed" else "partial"
        } else if (is.list(ret) && length(ret) >= 2 && is.numeric(ret[[1]])) {
            score <- as.numeric(ret[[1]])
            result$score <- max(0, min(score, points))
            result$message <- if (!is.null(ret[[2]])) as.character(ret[[2]]) else ""
            result$passed <- result$score == points
            result$status <- if (result$passed) "passed" else "partial"
        } else if (is.list(ret) && !is.null(ret$score) && is.numeric(ret$score)) {
            score <- as.numeric(ret$score)
            result$score <- max(0, min(score, points))
            result$message <- if (!is.null(ret$message)) as.character(ret$message) else ""
            result$passed <- result$score == points
            result$status <- if (result$passed) "passed" else "partial"
        } else if (is.logical(ret) && length(ret) >= 1) {
            result$passed <- as.logical(ret[[1]])
            result$score <- if (result$passed) points else 0
            result$status <- if (result$passed) "passed" else "failed"
        } else if (is.character(ret) && length(ret) >= 1) {
            result$message <- as.character(ret[[1]])
            result$passed <- TRUE
            result$score <- points
            result$status <- "passed"
        } else {
            result$passed <- TRUE
            result$score <- points
            result$status <- "passed"
        }
    }, error = function(e) {
        result$error <<- conditionMessage(e)
        result$status <<- if (grepl("time limit|timed out|timeout", tolower(conditionMessage(e)))) "error" else "failed"
    })

    test_results <<- c(test_results, list(result))
}

output_test_results <- function() {
    if (!requireNamespace("jsonlite", quietly = TRUE)) {
        tryCatch({
            install.packages("jsonlite", repos = "https://cloud.r-project.org")
        }, error = function(e) {
            return()
        })
    }
    if (requireNamespace("jsonlite", quietly = TRUE)) {
        cat('<<<TEST_RESULT_JSON_START>>>')
        cat(jsonlite::toJSON(test_results, auto_unbox = TRUE))
        cat('<<<TEST_RESULT_JSON_END>>>')
    }
}

# Execute test code if provided
test_code <- "#{TEST_CODE}"
if (nchar(trimws(test_code)) > 0) {
    tryCatch({
        eval(parse(text = test_code), envir = globalenv())
    }, error = function(e) {
        run_test("Test Script Execution", 0, function() {
            stop(paste("Failed to run test script:", conditionMessage(e)))
        })
    })
}

# Output test results
output_test_results()
