# This is a template for running R Jupyter notebook code cells inside a Docker container.

# To use this template replace the placeholder {cells_b64} with a base64-encoded JSON array of cells, And packages_to_install with a list of packages to install.

MAX_CELLS <- 500  # Maximum number of cells allowed to prevent abuse

packages_to_install <- list()

# template_log is a function that logs the template to a file.
template_log <- function(message) {
   cat(paste0(message, "\n"), file = stderr())
}

file_exists <- function(file_path) {
   file.info(file_path)$size > 0
}
dir_exists <- function(dir_path) {
   file.info(dir_path)$isdir
}

template_log("Template started.")
start_time <- Sys.time()
template_log(paste("Initial working directory: ", getwd()))
template_log(paste("/work exists: ", dir_exists("/work")))
template_log(paste("/root/shared exists: ", dir_exists("/root/shared")))

# if /work exists, set it as the working directory
if (dir_exists("/work")) {
   setwd("/work")
   template_log(paste("Working directory set to: ", getwd()))
}
else {
   template_log("/work directory does not exist.")
   q(1)
}

library(base64enc)
library(jsonlite)


# install packages
if (length(packages_to_install) > 0) {
   install.packages(packages_to_install)
   template_log(paste("Packages installed: ", paste(packages_to_install, collapse = ", ")))
   # Log to stderr (using message or cat(file=stderr())) so Converger picks it up
   for (pkg in packages_to_install) {
       message(paste0("CODEPOST_AUTO_INSTALL_SUCCESS: ", pkg))
   }
}
else {
   template_log("No packages to install.")
}

# Security: Make cache read-only after installation to prevent notebook code from tampering
if (length(packages_to_install) > 0) {
   template_log("Making cache read-only after installation.")
   # Attempt to lock standard cache locations if they exist and are writable
   cache_dirs <- c(Sys.getenv("R_LIBS_USER"), "/tmp/pip-cache", "/tmp/npm-cache") 
   for (cache_dir in cache_dirs) {
       if (dir.exists(cache_dir)) {
           tryCatch({
               Sys.chmod(cache_dir, mode = "0555", use_umask = FALSE)
           }, error = function(e) {
               template_log(paste("Could not lock cache dir:", cache_dir))
           })
       }
   }
}

# flush console
flush.console()

# decode cells
decoded <- base64decode('{cells_b64}')

# parse cells
notebook_json <- fromJSON(decoded)

# check if cells are valid
if (!is.list(notebook_json) || !all(sapply(notebook_json, function(x) is.list(x) && "cell_type" %in% names(x)))) {
   template_log("Invalid cells.")
   q(1)
}
results <- list()

# check if cells are too many
if (length(notebook_json) > MAX_CELLS) {
   template_log(paste("Too many cells: ", length(notebook_json)))
   results <- list(
    type='markdown',
    source=paste("**Error:** Too many cells. Maximum allowed: ", MAX_CELLS, "\n\n", "Execution stopped.")
   )
} else {
    NBS_OUTPUT_LIMIT <- 10000  # Max characters in output 10kb
    execution_count <- 0
    
    # Environment for executing cells (shared namespace like Jupyter)
    cell_env <- new.env(parent = globalenv())
    
    for (cell in notebook_json) {
        if (cell$type == "markdown") {
            results <- c(results, list(list(
                cell_type = 'markdown',
                source = cell$source
            )))
        }
        if (cell$type == "code") {
            execution_count <- execution_count + 1
            cell_source <- cell$source
            
            outputs <- list()
            success <- TRUE
            error_msg <- NULL
            
            # Capture stdout
            stdout_file <- tempfile(fileext = ".txt")
            stderr_file <- tempfile(fileext = ".txt")
            
            # Create a temp file for potential plot output
            plot_file <- tempfile(fileext = ".png")
            
            tryCatch({
                # Open graphics device to capture plots
                png(plot_file, width = 800, height = 600, res = 100)
                
                # Capture stdout and stderr
                sink(stdout_file, type = "output")
                sink(stderr_file, type = "message")
                
                # Parse and evaluate the code
                # Split by newlines and evaluate each expression
                parsed <- tryCatch({
                    parse(text = cell_source)
                }, error = function(e) {
                    success <<- FALSE
                    error_msg <<- conditionMessage(e)
                    NULL
                })
                
                if (!is.null(parsed) && length(parsed) > 0) {
                    last_value <- NULL
                    for (i in seq_along(parsed)) {
                        expr <- parsed[[i]]
                        last_value <- eval(expr, envir = cell_env)
                        
                        # For the last expression, print if it's not invisible
                        if (i == length(parsed)) {
                            # Check if result should be displayed
                            if (!is.null(last_value)) {
                                # Use print for data frames, tibbles, etc.
                                if (inherits(last_value, c("data.frame", "tbl", "tbl_df"))) {
                                    print(last_value)
                                } else if (is.vector(last_value) || is.matrix(last_value) || is.array(last_value)) {
                                    print(last_value)
                                } else if (!is.function(last_value) && !is.environment(last_value)) {
                                    print(last_value)
                                }
                            }
                        }
                    }
                }
                
            }, error = function(e) {
                success <<- FALSE
                error_msg <<- conditionMessage(e)
            }, warning = function(w) {
                # Capture warnings but continue
                cat(paste("Warning:", conditionMessage(w), "\n"), file = stderr_file, append = TRUE)
                invokeRestart("muffleWarning")
            }, finally = {
                # Close sinks
                sink(type = "message")
                sink(type = "output")
                
                # Close graphics device
                dev.off()
            })
            
            # Read captured stdout
            stdout_text <- ""
            if (file.exists(stdout_file) && file.info(stdout_file)$size > 0) {
                stdout_text <- paste(readLines(stdout_file, warn = FALSE), collapse = "\n")
            }
            
            # Read captured stderr
            stderr_text <- ""
            if (file.exists(stderr_file) && file.info(stderr_file)$size > 0) {
                stderr_text <- paste(readLines(stderr_file, warn = FALSE), collapse = "\n")
            }
            
            # Check if a plot was created
            # Note: Empty PNG files from R are typically ~100-200 bytes
            # A real plot will be at least 1KB, so we use 1000 bytes as threshold
            EMPTY_PLOT_THRESHOLD <- 1000
            if (file.exists(plot_file) && file.info(plot_file)$size > EMPTY_PLOT_THRESHOLD) {
                # File is large enough to contain actual plot content
                tryCatch({
                    # Read plot and encode as base64
                    plot_data <- readBin(plot_file, "raw", file.info(plot_file)$size)
                    plot_base64 <- base64encode(plot_data)
                    
                    outputs <- c(outputs, list(list(
                        output_type = 'display_data',
                        data = list(
                            `image/png` = plot_base64
                        ),
                        metadata = list()
                    )))
                }, error = function(e) {
                    # If plot capture fails, add to stderr
                    stderr_text <- paste0(stderr_text, "\nPlot capture error: ", conditionMessage(e), "\n")
                })
            }
            
            # Clean up temp files
            unlink(c(stdout_file, stderr_file, plot_file))
            
            # Truncate stdout if too long
            if (nchar(stdout_text) > NBS_OUTPUT_LIMIT) {
                stdout_text <- paste0(substr(stdout_text, 1, NBS_OUTPUT_LIMIT), "\n...[ERROR output truncated]\n")
            }
            
            # Truncate stderr if too long
            if (nchar(stderr_text) > NBS_OUTPUT_LIMIT) {
                stderr_text <- paste0(substr(stderr_text, 1, NBS_OUTPUT_LIMIT), "\n...[ERROR output truncated]\n")
            }
            
            # Build outputs list
            if (nchar(stdout_text) > 0) {
                outputs <- c(outputs, list(list(
                    output_type = 'stream',
                    name = 'stdout',
                    text = stdout_text
                )))
            }
            
            if (nchar(stderr_text) > 0) {
                outputs <- c(outputs, list(list(
                    output_type = 'stream',
                    name = 'stderr',
                    text = stderr_text
                )))
            }
            
            if (!success) {
                # Truncate error message if too long
                if (!is.null(error_msg) && nchar(error_msg) > NBS_OUTPUT_LIMIT) {
                    error_msg <- paste0(substr(error_msg, 1, NBS_OUTPUT_LIMIT), "\n...[ERROR message truncated]\n")
                }
                
                outputs <- c(outputs, list(list(
                    output_type = 'error',
                    ename = 'ExecutionError',
                    evalue = if (!is.null(error_msg)) error_msg else stderr_text,
                    traceback = list(stderr_text)
                )))
            }
            
            results <- c(results, list(list(
                cell_type = 'code',
                source = cell_source,
                outputs = outputs,
                execution_count = execution_count
            )))
        }
    }
}

# Output results as JSON
end_time <- Sys.time()
execution_time <- as.numeric(difftime(end_time, start_time, units = "secs"))

final_result <- list(
    success = TRUE, # If we got here without crashing, we consider it a success at the notebook level
    stdout = "",
    stderr = "",
    error = NULL,
    execution_time = execution_time,
    output_data = list(
        cells = results
    )
)

cat('<<<RESULTS_START>>>\n')
cat(toJSON(final_result, auto_unbox = TRUE, null = "null"))
cat('\n<<<RESULTS_END>>>\n')



